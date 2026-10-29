"""Date-ordered historical analogue of the frozen current-season minutes challenger.

Research only. A past NBA game DATE is not a verified timestamp of source
availability or real T-30 issuance. The retrospective cohort is conditional
on a positive-minute appearance and observed club at that game. It does not
measure P(play), missing/DNP, personal Sports.ru credit or transfer gain.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from math import isfinite, sqrt
from pathlib import Path
import json

from src.sync import DATA
from src.rolling_decision_research import canonical_hash
from src.conditional_minutes_fp_research import (
    forecast, same_team_tail, MODEL as PREVIOUS_SEASON_MODEL,
)
from src.current_season_minutes_shadow_research import (
    MODEL as CHALLENGER, MODEL_HASH as CHALLENGER_HASH,
)

STATUS = "research_only_not_deployed"
YEARS = {"2023/24": "00223", "2024/25": "00224", "2025/26": "00225"}
TRANSITIONS = (("2023/24", "2024/25"), ("2024/25", "2025/26"))


def _number(value, low, high):
    if type(value) not in (int, float) or not isfinite(value) or not low <= value <= high:
        raise ValueError("Invalid historical played observation")
    return float(value)


def _row(raw, season):
    if not isinstance(raw, dict) or not str(raw.get("g", "")).startswith(YEARS[season]):
        raise ValueError("Historical NBA game belongs to wrong season")
    d = date.fromisoformat(raw["d"])
    start = int(season[:4])
    if not date(start, 9, 1) <= d < date(start + 1, 8, 1):
        raise ValueError("Game date outside NBA historical season")
    team = raw.get("team")
    if not isinstance(team, str) or not team:
        raise ValueError("Played observation lacks club")
    return {
        "d": d.isoformat(), "g": raw["g"], "team": team,
        "min": _number(raw.get("min"), 0.00001, 70),
        "fp": _number(raw.get("fp"), -150, 250),
    }


def load_history(index, loader):
    mapping = index.get("player_shards")
    version = index.get("version")
    if (index.get("status") != "complete" or not isinstance(version, str)
            or not version or not isinstance(mapping, dict) or len(mapping) < 200):
        raise ValueError("Incomplete public historical source")
    players = {}
    count = Counter()
    for filename in sorted(set(mapping.values())):
        if (not isinstance(filename, str)
                or not filename.startswith("shard_") or not filename.endswith(".json")
                or "/" in filename or ".." in filename):
            raise ValueError("Unsafe historical shard name")
        shard = loader(filename)
        if (shard.get("status") != "complete" or shard.get("version") != version
                or not isinstance(shard.get("players"), dict)):
            raise ValueError("Historical shard and source version differ")
        for player_id, years in shard["players"].items():
            if (player_id in players or mapping.get(player_id) != filename
                    or not isinstance(years, list)):
                raise ValueError("Untrusted or duplicated historical player identity")
            output = {}
            for season in years:
                key = season.get("season")
                if key not in YEARS:
                    continue
                if key in output or not isinstance(season.get("game_log"), list):
                    raise ValueError("Duplicated historical season or missing log")
                rows = [_row(r, key) for r in season["game_log"]]
                if len(rows) != season.get("games") or len({x["g"] for x in rows}) != len(rows):
                    raise ValueError("Incomplete or duplicate historical played games")
                rows.sort(key=lambda r: (r["d"], r["g"]))
                output[key] = rows
                count[key] += len(rows)
            players[player_id] = output
    if set(players) != set(mapping):
        raise ValueError("Player/shard membership drift")
    return players, dict(count)


def evaluate_player(player_id, previous_logs, current_logs, target_season):
    """No feature has date >= target played-game date; target club is only a cohort filter."""
    baseline = forecast(same_team_tail(previous_logs))
    pairs = []
    qa = Counter()
    for i, row in enumerate(current_logs):
        qa["positive_played_game_rows"] += 1
        if baseline is None:
            qa["no_previous_season_same_club_20_game_prior"] += 1
            continue
        if row["team"] != baseline["last_sample_team"]:
            qa["observed_club_differs_from_previous_year_prior"] += 1
            continue
        past = [x for x in current_logs[:i]
                if x["team"] == row["team"] and x["d"] < row["d"]]
        sample = past[-CHALLENGER["max_recent_current_played_games"]:]
        if len(sample) < CHALLENGER["min_current_same_club_played_games"]:
            qa["fewer_than_three_prior_played_games_same_club"] += 1
            continue
        old_minutes = baseline["minutes_if_play"]
        rate = baseline["fp_per_minute_if_play"]
        mean_current = sum(x["min"] for x in sample) / len(sample)
        strength = CHALLENGER["frozen_prior_strength_in_games"]
        updated_minutes = round(
            (strength * old_minutes + len(sample) * mean_current) /
            (strength + len(sample)), 5,
        )
        pairs.append({
            "player_id": player_id, "game_id": row["g"],
            "date": row["d"], "season": target_season,
            "player_season_played_game_number": i + 1,
            "prior_current_same_team_n": len(sample),
            "prior_current_last_date": sample[-1]["d"],
            "prior_previous_season_last_date": baseline["sample_last_played_date"],
            "actual_minutes": row["min"], "actual_fp": row["fp"],
            "baseline_minutes": old_minutes,
            "challenger_minutes": updated_minutes,
            "baseline_fp": baseline["decomposed_fp_if_play"],
            "challenger_fp": round(updated_minutes * rate, 5),
        })
        qa["paired_played_only"] += 1
    return pairs, dict(qa)


def paired_metrics(rows):
    if not rows:
        return {"paired_played_only": 0}
    n = len(rows)
    report = {
        "paired_played_only": n,
        "distinct_players": len({r["player_id"] for r in rows}),
        "distinct_games": len({r["game_id"] for r in rows}),
        "distinct_game_dates": len({r["date"] for r in rows}),
    }
    for name, actual, base, challenger in (
        ("minutes_if_play", "actual_minutes", "baseline_minutes", "challenger_minutes"),
        ("FP_given_played", "actual_fp", "baseline_fp", "challenger_fp"),
    ):
        old = [r[base] - r[actual] for r in rows]
        new = [r[challenger] - r[actual] for r in rows]
        improvements = [abs(a) - abs(b) for a, b in zip(old, new)]
        report[name] = {
            "baseline_MAE": round(sum(abs(e) for e in old) / n, 4),
            "challenger_MAE": round(sum(abs(e) for e in new) / n, 4),
            "baseline_RMSE": round(sqrt(sum(e * e for e in old) / n), 4),
            "challenger_RMSE": round(sqrt(sum(e * e for e in new) / n), 4),
            "baseline_prediction_minus_actual_bias": round(sum(old) / n, 4),
            "challenger_prediction_minus_actual_bias": round(sum(new) / n, 4),
            "paired_MAE_gain_positive_favors_challenger": round(sum(improvements) / n, 4),
            "challenger_better_fraction": round(sum(x > 1e-9 for x in improvements) / n, 4),
        }
    return report


def build(index, loader):
    people, source_rows = load_history(index, loader)
    by_season = {}
    all_pairs = []
    global_qa = Counter()
    for previous_season, target in TRANSITIONS:
        qa = Counter()
        pairs = []
        for pid, seasons in sorted(people.items()):
            selected, info = evaluate_player(
                pid, seasons.get(previous_season, []),
                seasons.get(target, []), target,
            )
            pairs.extend(selected)
            qa.update(info)
        pairs.sort(key=lambda r: (r["date"], r["game_id"], r["player_id"]))
        if len({(r["game_id"], r["player_id"]) for r in pairs}) != len(pairs):
            raise ValueError("Duplicate historical paired outcome")
        all_pairs.extend(pairs)
        global_qa.update(qa)
        by_season[target] = {
            "role": "historical_development_diagnostic" if target == "2024/25"
                    else "reused_historical_check_not_new_untouched_holdout",
            "qa": dict(qa),
            "all_eligible_historical_played": paired_metrics(pairs),
            "early_player_appearances_4_to_10": paired_metrics([
                r for r in pairs if 4 <= r["player_season_played_game_number"] <= 10
            ]),
            "later_player_appearances_11_plus": paired_metrics([
                r for r in pairs if r["player_season_played_game_number"] >= 11
            ]),
            "by_prior_current_same_team_games": {
                str(n): paired_metrics([
                    r for r in pairs if r["prior_current_same_team_n"] == n
                ]) for n in (3, 4, 5)
            },
        }
    if global_qa["paired_played_only"] != len(all_pairs):
        raise ValueError("Historical research denominator drift")
    return {
        "schema_version": 1,
        "status": STATUS,
        "model_status": STATUS,
        "adopt_on_site": False,
        "source_history_index_version": index["version"],
        "source_historical_positive_played_rows_by_season": source_rows,
        "previous_season_frozen_model_hash": canonical_hash(PREVIOUS_SEASON_MODEL),
        "current_season_challenger_model_sha256": CHALLENGER_HASH,
        "research_question": "Does same-team observed season form improve previous-season conditional minutes and FP?",
        "method": "date_ordered_retrospective_positive_played_only_not_actual_prelock_issuance",
        "past_feature_cutoff": "strictly_before_target_NBA_calendar_date",
        "observed_game_team_is_selection_not_prelock_roster_proof": True,
        "historical_first_seen_timestamps_available": False,
        "cohort_no_DNP_or_missing_rows_inferred": True,
        "all_paired_source_rows_sha256": canonical_hash(all_pairs),
        "qa": dict(global_qa),
        "by_target_season": by_season,
        "pooled_descriptive_only": paired_metrics(all_pairs),
        "quality_gate": {
            "historical_retrospective_not_prospective": True,
            "2025_26_not_new_untouched_holdout_after_prior_analysis": True,
            "future_2026_27_issued_evaluation_still_required": True,
            "full_P_play_or_unconditional_FP_validated": False,
            "actual_KEEP_TRANSFER_gain_proven": False,
            "adopt_on_site": False,
        },
        "limitations": [
            "History contains played-game dates, not actual first-seen ingestion or T-30 issue times.",
            "An observed played-game team is not proof of roster membership before lock.",
            "No DNP, absent row or OUT is converted into a negative label.",
            "Multiple games of a player and a date are correlated; large row counts are not independent days.",
            "The weight 5 was proposed after initial 2026/27 results; neither historical season is a pristine independent validation.",
            "Only prospective 2026/27 issues after challenger creation can establish future value.",
            "Reconstructed Sports.ru FP is not guaranteed to match official personal credited FP.",
            "This is not a full fantasy population or a net transfer-gain evaluation.",
        ],
    }


def run():
    index = json.loads((DATA / "history/index.json").read_text(encoding="utf8"))
    def shard(name):
        return json.loads((DATA / "history" / name).read_text(encoding="utf8"))
    report = build(index, shard)
    target = DATA / "historical_current_minutes_walkforward_research.json"
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if not target.exists() or target.read_text(encoding="utf8") != payload:
        temp = target.with_suffix(".tmp")
        temp.write_text(payload, encoding="utf8")
        temp.replace(target)
    return {
        "research_only": True,
        "adopt_on_site": False,
        "source_history_index_version": report["source_history_index_version"],
        "by_target_season": {
            s: r["early_player_appearances_4_to_10"]
            for s, r in report["by_target_season"].items()
        },
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
