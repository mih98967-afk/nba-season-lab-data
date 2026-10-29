"""Reconstruct a research-only historical NBA T-30 decision *proxy*.

The target tipoff is independently reconciled from ESPN, then replayed with
previous-season priors and earlier positive-minute observations. Because the
original historical first-seen timestamps and changing schedules were not
archived, +12/+24/+48h boxscore availability is an explicit counterfactual
assumption, NOT verified PIT availability. No claim of true historical NBA
roster membership, DNP, official Sports.ru credit or transfer gains.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
import json

from src.sync import DATA
from src.rolling_decision_research import canonical_hash, instant, stamp
from src.conditional_minutes_fp_research import forecast, same_team_tail
from src.historical_current_minutes_walkforward_research import (
    load_history, paired_metrics, TRANSITIONS,
)
from src.historical_appearance_proxy_research import validated_fixtures
from src.current_season_minutes_shadow_research import MODEL as CHALLENGER

STATUS = "research_only_not_deployed"
LOCK = timedelta(minutes=30)
MAX_AGE = timedelta(days=16)
AVAILABILITY_LAGS_H = (12, 24, 48)
DEFAULT_LAG_H = 24


def attach_played_to_calendar(rows, games, label):
    """Verify target outcome independently against a historical final fixture."""
    indexed = {g["id"]: g for g in games}
    if len(indexed) != len(games):
        raise ValueError("Duplicate historical fixture")
    seen = set()
    result = []
    for row in rows:
        g = indexed.get(row["g"])
        if (g is None or row["g"] in seen or row["d"] != g["et_date"]
                or row["team"] not in (g["home"], g["away"])):
            raise ValueError("Historical "+label+" played row disagrees with fixture")
        seen.add(row["g"])
        result.append({**row, "tip": g["utc"]})
    result.sort(key=lambda x: (x["tip"], x["g"]))
    return result


def reconstruct_player(pid, baseline_prior, played, games, lag_hours):
    """Issue on previous-only as-of inputs, then join target outcomes separately."""
    if lag_hours not in AVAILABILITY_LAGS_H:
        raise ValueError("Availability assumption not registered")
    base = forecast(same_team_tail(baseline_prior))
    if base is None:
        return [], {"no_eligible_previous_season_baseline": 1}
    last_club = base["last_sample_team"]
    if len({g["id"] for g in games}) != len(games):
        raise ValueError("Duplicate fixtures")
    relevant = sorted(
        (g for g in games if last_club in (g["home"], g["away"])),
        key=lambda g: (g["utc"], g["id"]),
    )
    positives = sorted(played, key=lambda x: (x["tip"], x["g"]))
    outcomes = {x["g"]: x for x in positives}
    if len(outcomes) != len(positives):
        raise ValueError("Duplicate player-game outcomes")
    known = []
    cursor = 0
    out = []
    qa = Counter()
    for fixture in relevant:
        cutoff = fixture["utc"] - LOCK
        # Synthetic +N-hour lag: NEVER claim actual historical ingestion time.
        while (cursor < len(positives)
               and positives[cursor]["tip"] + timedelta(hours=lag_hours) <= cutoff):
            known.append(positives[cursor])
            cursor += 1
        if not known:
            qa["no_previously_assumed_available_current_played_game"] += 1
            continue
        latest = known[-1]
        if latest["team"] != last_club:
            qa["last_observed_club_changed_no_prelock_membership_proof"] += 1
            continue
        if cutoff - latest["tip"] > MAX_AGE:
            qa["last_positive_played_too_old_abstain"] += 1
            continue
        same_club = same_team_tail(known)
        sample = same_club[-CHALLENGER["max_recent_current_played_games"]:]
        if len(sample) < CHALLENGER["min_current_same_club_played_games"]:
            qa["insufficient_prior_same_club_played_minutes"] += 1
            continue
        # Every feature was observable in an earlier game under the assumed lag.
        if (sample[-1]["tip"] + timedelta(hours=lag_hours) > cutoff
                or any(r["tip"] >= cutoff for r in sample)
                or sample[-1]["g"] == fixture["id"]):
            raise ValueError("Future or target played event leaked into replay")
        strength = CHALLENGER["frozen_prior_strength_in_games"]
        n = len(sample)
        mean = sum(x["min"] for x in sample) / n
        baseline_minutes = base["minutes_if_play"]
        challenger_minutes = round((strength*baseline_minutes + n*mean)/(strength+n), 5)
        rate = base["fp_per_minute_if_play"]
        row = {
            "player_id": pid, "game_id": fixture["id"], "date": fixture["et_date"],
            "simulated_individual_lock_utc": stamp(cutoff),
            "source_last_played_tipoff_utc": stamp(sample[-1]["tip"]),
            "assumed_last_played_available_utc": stamp(
                sample[-1]["tip"] + timedelta(hours=lag_hours)),
            "club_from_previous_positive_game": last_club,
            "prior_current_same_team_n": n,
            "prior_current_appearances_total": len(same_club),
            "baseline_minutes": baseline_minutes,
            "challenger_minutes": challenger_minutes,
            "baseline_fp": base["decomposed_fp_if_play"],
            "challenger_fp": round(challenger_minutes*rate, 5),
            "historical_schedule_known_prelock": False,
            "historical_boxscore_first_seen_verified": False,
            "adopt_on_site": False,
        }
        # Outcome join is explicitly AFTER the features and candidate exist.
        actual = outcomes.get(fixture["id"])
        if actual is not None and actual["team"] == last_club:
            row.update({
                "result_label": "positive_minutes_verified_historical_boxscore",
                "actual_minutes": actual["min"], "actual_fp": actual["fp"],
            })
            qa["paired_positive_played_only"] += 1
        else:
            row["result_label"] = "UNKNOWN_no_positive_log_not_DNP"
            if actual is not None:
                qa["outcome_played_different_club_UNKNOWN"] += 1
            qa["no_positive_minutes_log_UNKNOWN"] += 1
        out.append(row)
        qa["simulated_prelock_proxy_opportunities"] += 1
    return out, dict(qa)


def summarize(rows):
    if len({(x["game_id"], x["player_id"]) for x in rows}) != len(rows):
        raise ValueError("Duplicated historical player-game research opportunities")
    positives = [r for r in rows
                 if r["result_label"] == "positive_minutes_verified_historical_boxscore"]
    unknown = [r for r in rows if r["result_label"] == "UNKNOWN_no_positive_log_not_DNP"]
    if len(rows) != len(positives) + len(unknown):
        raise ValueError("Missing outcome classification")
    if any("actual_minutes" in r or "actual_fp" in r for r in unknown):
        raise ValueError("UNKNOWN was silently assigned a scored outcome")
    dates = defaultdict(list)
    for r in positives:
        dates[r["date"]].append(r)
    subset = lambda fn: paired_metrics([r for r in positives if fn(r)])
    return {
        "simulated_prelock_opportunities": len(rows),
        "verified_positive_played_pairs": len(positives),
        "missing_positive_log_UNKNOWN_not_DNP": len(unknown),
        "proxy_played_selected_fraction_NOT_P_play": (
            round(len(positives)/len(rows), 6) if rows else None),
        "distinct_players_with_proxies": len({r["player_id"] for r in rows}),
        "distinct_fixture_games_with_proxies": len({r["game_id"] for r in rows}),
        "distinct_scored_ET_dates": len(dates),
        "paired_scored_only": paired_metrics(positives),
        "early_prelock_form_3_to_9_prior_appearances": subset(
            lambda r: 3 <= r["prior_current_appearances_total"] <= 9),
        "later_prelock_form_10_plus_prior_appearances": subset(
            lambda r: r["prior_current_appearances_total"] >= 10),
        "source_hash_issued_proxy_features_only": canonical_hash([
            {k:v for k,v in r.items() if k not in (
                "result_label", "actual_minutes", "actual_fp")}
            for r in rows]),
        "source_hash_postgame_joined": canonical_hash(rows),
        "first_three_issued_proxy_examples": [
            {k:v for k,v in r.items() if k not in ("actual_minutes", "actual_fp")}
            for r in rows[:3]],
    }


def build(index, shard_loader, identity, calendar):
    history, source_qa = load_history(index, shard_loader)
    fixtures = validated_fixtures(calendar)
    identity_players = identity.get("players")
    if not isinstance(identity_players, dict):
        raise ValueError("Missing audited identity")
    high_ids = {pid for pid,x in identity_players.items()
                if isinstance(x, dict) and x.get("confidence") == "high"}
    if len(high_ids & set(history)) < 200:
        raise ValueError("High-confidence player sample is not sufficient")
    by_year = {}
    summary_qa = Counter()
    for previous_year, target in TRANSITIONS:
        index_by_team = defaultdict(list)
        for game in fixtures[target]:
            index_by_team[game["home"]].append(game)
            index_by_team[game["away"]].append(game)
        if len(fixtures[target]) != 1230:
            raise ValueError("Incomplete historical NBA season")
        same_lag = {}
        all_players = []
        for pid in sorted(high_ids & set(history)):
            seasons = history[pid]
            base_logs = seasons.get(previous_year) or []
            original = forecast(same_team_tail(base_logs))
            if original is None:
                summary_qa["insufficient_previous_same_team_20_for_audited_player"] += 1
                continue
            current = attach_played_to_calendar(
                seasons.get(target) or [], fixtures[target], target)
            all_players.append((pid, base_logs, current, index_by_team[original["last_sample_team"]]))
        for lag_h in AVAILABILITY_LAGS_H:
            rows = []
            qa = Counter()
            for pid, previous, current, games in all_players:
                predicted, counters = reconstruct_player(pid, previous, current, games, lag_h)
                rows.extend(predicted)
                qa.update(counters)
            rows.sort(key=lambda r: (r["simulated_individual_lock_utc"],
                                      r["game_id"], r["player_id"]))
            stats = summarize(rows)
            if stats["simulated_prelock_opportunities"] != qa["simulated_prelock_proxy_opportunities"]:
                raise ValueError("Historical proxy issue denominator drift")
            if stats["verified_positive_played_pairs"] != qa["paired_positive_played_only"]:
                raise ValueError("Historical positive played evidence denominator drift")
            if stats["missing_positive_log_UNKNOWN_not_DNP"] != qa["no_positive_minutes_log_UNKNOWN"]:
                raise ValueError("Historical unknown evidence denominator drift")
            same_lag[str(lag_h)] = {"availability_assumption_hours_after_tipoff":lag_h,
                                    "issue_QA":dict(qa), **stats}
        by_year[target] = {
            "role": "historical_development_diagnostic" if target == "2024/25"
                    else "historical_reused_not_pristine_independent_holdout",
            "players_with_previous_year_same_club_prior":len(all_players),
            "by_assumed_history_availability_lag_hours":same_lag,
        }
    if not by_year:
        raise ValueError("No historical replay")
    return {
        "schema_version":1, "status":STATUS, "model_status":STATUS,
        "adopt_on_site":False,
        "source_history_version":index["version"],
        "source_identity_high_confidence_count":len(high_ids & set(history)),
        "source_rows_by_year":source_qa,
        "fixture_qa":calendar["qa"],
        "simulation":"historical_T_minus_30_with_retrospective_finals_and_assumed_boxscore_lag",
        "genuine_original_historical_issue":False,
        "exact_retrospective_tipoff_from_ESPN_verified":True,
        "fixture_schedule_asof_at_historical_lock_verified":False,
        "boxscore_first_seen_at_historical_lock_verified":False,
        "team_roster_asof_at_historical_lock_verified":False,
        "feature_assumption":"Prior played row usable only when tipoff + 12/24/48 hours <= simulated T-30; true ingestion unknown",
        "candidate_universe_selection":"same-club positive minute history known by lag + last played <=16d + 3 same-club previous played",
        "result_of_missing_positive_log":"UNKNOWN_not_explicit_DNP",
        "by_target_season":by_year,
        "qa":dict(summary_qa),
        "quality_gate":{
            "future_2026_27_prospective_still_required":True,
            "only_conditional_positive_minutes_FP_scored":True,
            "true_P_play_denominator_known":False,
            "unconditional_FP_or_transfers_proven":False,
            "retrospective_historical_parameters_not_independently_preregistered":True,
            "adopt_on_site":False,
        },
        "limitations":[
            "Actual historical tipoff is independently verified, but historical published schedule PIT is not.",
            "Past boxscore availability is ASSUMED at +12/+24/+48h after tipoff, not documented as first-seen.",
            "Historical current roster membership is inferred only from earlier positive minutes, never confirmed prelock.",
            "Absent positive game row is UNKNOWN, not a DNP or zero fantasy FP.",
            "The previous/current minutes mixture was designed after 2026/27 started; 2025/26 is reused, not untouched.",
            "Output is a selected researched population, not all Sports.ru fantasy-eligible players.",
            "Correlations within player, teams and game dates make row-level p-values invalid.",
            "Original Sports.ru credited fantasy FP may differ from reconstructed historical formula.",
            "No production adoption, Firebase writes, prices, transfers or web UI publication.",
        ],
    }


def run():
    def read(name):
        return json.loads((DATA/name).read_text(encoding="utf8"))
    index=read("history/index.json")
    result=build(index,lambda f:read("history/"+f),read("identity.json"),
                 read("historical_tipoffs.json"))
    target=DATA/"historical_prelock_minutes_replay_research.json"
    payload=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if not target.exists() or target.read_text(encoding="utf8")!=payload:
        tmp=target.with_suffix(".tmp")
        tmp.write_text(payload,encoding="utf8")
        tmp.replace(target)
    return {
        "research_only":True,
        "adopt_on_site":False,
        "source_history_version":result["source_history_version"],
        "by_target_season":{
            s:v["by_assumed_history_availability_lag_hours"][str(DEFAULT_LAG_H)]["paired_scored_only"]
            for s,v in result["by_target_season"].items()
        },
    }


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
