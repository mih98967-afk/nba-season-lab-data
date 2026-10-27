"""Research-only decomposition: minutes-if-play x Sports.ru FP-per-minute.

Freeze structural parameters on 2024/25 chronological development. Evaluate
UNTOUCHED 2025/26 early-season played-game holdout against a direct FP prior;
issue 2026/27 player x game forecasts only while genuinely before individual
lock. 2025/26 becomes *past* training input for 2026/27 issuance, never a
2026 outcome. This study targets conditional played games only, NOT p_play.

All missing player-game rows stay UNKNOWN, never DNP/0. Sports.ru FP is used
as historically reconstructed (not generic NBA fantasy scoring). No site,
Firebase, personal roster, pricing, transfer, model adoption or refit.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from math import ceil, isfinite, sqrt
from pathlib import Path
import json

from src.sync import DATA
from src.rolling_decision_research import canonical_hash, instant, stamp

STATUS = "research_only_not_deployed"
SCHEMA = 1
LOCK = timedelta(minutes=30)
HORIZON = timedelta(hours=72)
TRAIN = "2024/25"
HOLDOUT = "2025/26"
MAX_PROSPECTIVE = 20000
MODEL = {
    "version": "conditional_minutes_x_fp_per_minute_v1",
    "2024_25_development_only": True,
    "played_game_target_only": True,
    "required_same_team_recent_played_games": 20,
    "minutes_recent10_weight": 0.7,
    "minutes_last20_weight": 0.3,
    "rate_last20_weight": 0.7,
    "rate_last40_weight": 0.3,
    "development_absolute_residual_quantile": 0.9,
    "2025_26_holdout_first_played_games_per_player": 5,
    "holdout_not_used_to_tune_parameters": True,
}


def _numbers(row, season):
    if not isinstance(row, dict):
        raise ValueError("Malformed historical boxscore")
    minutes, fp = row.get("min"), row.get("fp")
    if (type(minutes) not in (int, float) or not isfinite(minutes)
            or not 0 < minutes <= 70
            or type(fp) not in (int, float) or not isfinite(fp)
            or not -150 <= fp <= 250):
        raise ValueError("Nonfinite/implausible played minutes or Sports.ru FP")
    game_id = str(row.get("g") or "")
    if not game_id.startswith("00224" if season == TRAIN else "00225"):
        raise ValueError("Historical game ID not in expected season")
    d = date.fromisoformat(row["d"])
    team = row.get("team")
    if not isinstance(team, str) or not team:
        raise ValueError("Missing historical played team")
    return {"min": float(minutes), "fp": float(fp), "g": game_id,
            "d": d.isoformat(), "team": team}


def historical(index, loader):
    if (index.get("status") != "complete"
            or not index.get("version")
            or len(index.get("player_shards", {})) < 200):
        raise ValueError("Historical source is not complete")
    mapping = index["player_shards"]
    per_player = {}
    qa = Counter()
    for filename in sorted(set(mapping.values())):
        if (not filename.startswith("shard_") or not filename.endswith(".json")
                or "/" in filename or ".." in filename):
            raise ValueError("History source path unsafe")
        data = loader(filename)
        if (data.get("status") != "complete" or data.get("version") != index["version"]
                or not isinstance(data.get("players"), dict)):
            raise ValueError("Historical shard is not the audited index version")
        for pid, seasons in data["players"].items():
            if pid not in mapping or mapping[pid] != filename or pid in per_player:
                raise ValueError("Duplicate/cross-shard historical player")
            if not isinstance(seasons, list):
                raise ValueError("Malformed multi-season history")
            by_season = {}
            for entry in seasons:
                season = entry.get("season")
                if season not in (TRAIN, HOLDOUT):
                    continue
                if season in by_season or not isinstance(entry.get("game_log"), list):
                    raise ValueError("Bad 2024/25 or 2025/26 game log")
                logs = [_numbers(r, season) for r in entry["game_log"]]
                if len({r["g"] for r in logs}) != len(logs):
                    raise ValueError("Duplicate historical player-game")
                if len(logs) != entry["games"]:
                    raise ValueError("Historical played game count inconsistent")
                logs.sort(key=lambda x: (x["d"], x["g"]))
                by_season[season] = logs
            per_player[pid] = by_season
            qa["players_loaded"] += 1
            if TRAIN in by_season: qa["dev_season_players"] += 1
            if HOLDOUT in by_season: qa["holdout_season_players"] += 1
    if set(per_player) != set(mapping) or len(per_player) < 200:
        raise ValueError("Incomplete historical player identity coverage")
    return per_player, dict(qa)


def same_team_tail(logs):
    if not logs:
        return []
    club = logs[-1]["team"]
    i = len(logs)
    while i and logs[i-1]["team"] == club:
        i -= 1
    return logs[i:]


def forecast(logs):
    if len(logs) < MODEL["required_same_team_recent_played_games"]:
        return None
    recent = logs[-20:]
    if len({r["team"] for r in recent}) != 1:
        raise ValueError("Forecast training crosses a historical club change")
    last10 = recent[-10:]
    last40 = logs[-40:]
    if len({r["team"] for r in last40}) != 1:
        # The second efficiency prior must not cross a trade boundary.
        last40 = recent
    direct = sum(x["fp"] for x in recent)/len(recent)
    minutes = (0.7*sum(x["min"] for x in last10)/len(last10) +
               0.3*sum(x["min"] for x in recent)/len(recent))
    rate20 = sum(x["fp"] for x in recent)/sum(x["min"] for x in recent)
    rate40 = sum(x["fp"] for x in last40)/sum(x["min"] for x in last40)
    rate = 0.7*rate20 + 0.3*rate40
    return {"minutes_if_play": round(minutes, 5),
            "fp_per_minute_if_play": round(rate, 6),
            "decomposed_fp_if_play": round(minutes*rate, 5),
            "direct_last20_fp_if_play": round(direct, 5),
            "played_sample_n": len(recent),
            "last_sample_team": recent[-1]["team"],
            "sample_last_played_date": recent[-1]["d"]}


def _error(pred, actual):
    return {
        "minutes": abs(pred["minutes_if_play"] - actual["min"]),
        "fp_per_minute": abs(pred["fp_per_minute_if_play"] - actual["fp"]/actual["min"]),
        "decomposed_fp": abs(pred["decomposed_fp_if_play"] - actual["fp"]),
        "direct_fp": abs(pred["direct_last20_fp_if_play"] - actual["fp"]),
        "minutes_signed": pred["minutes_if_play"] - actual["min"],
        "decomposed_fp_signed": pred["decomposed_fp_if_play"] - actual["fp"],
    }


def _quantile(values, p):
    if len(values) < 100:
        raise ValueError("Insufficient calibration played-game support")
    s = sorted(values)
    return round(s[max(0, ceil(p*len(s))-1)], 5)


def calibration(players):
    """Rolling, only past 2024/25 played logs; zero access to 2025/26."""
    residuals = []
    cases = 0
    eligible = 0
    for pid, seasons in players.items():
        dev = seasons.get(TRAIN) or []
        if len(dev) < 25:
            continue
        eligible += 1
        # Evaluate up to last ten 2024/25 logs, with at least 20 past
        # same-team played games at each genuine chronological issue.
        for i in range(max(20, len(dev)-10), len(dev)):
            past = same_team_tail(dev[:i])
            pred = forecast(past)
            if pred is None:
                continue
            residuals.append(_error(pred, dev[i]))
            cases += 1
    if cases < 500:
        raise ValueError("Insufficient truly in-season dev calibration")
    q = {name:_quantile([r[name] for r in residuals], 0.9)
         for name in ("minutes", "fp_per_minute", "decomposed_fp", "direct_fp")}
    return q, {"2024_25_past_only_dev_cases":cases,
               "2024_25_eligible_players":eligible,
               "q90_absolute_residual_dev_only":q,
               "not_a_predictive_coverage_guarantee":True}


def _quality(records, q):
    if not records:
        return {"played_cases":0}
    n=len(records)
    errors=[r["errors"] for r in records]
    out={"played_cases":n}
    for field in ("minutes", "fp_per_minute", "decomposed_fp", "direct_fp"):
        v=[x[field] for x in errors]
        out[field+"_MAE"]=round(sum(v)/n,4)
        out[field+"_RMSE"]=round(sqrt(sum(e*e for e in v)/n),4)
        out[field+"_empirical_dev_q90_coverage"]=round(
            sum(x<=q[field] for x in v)/n,6)
    out["decomposed_minus_direct_FP_MAE"]=round(
        out["decomposed_fp_MAE"]-out["direct_fp_MAE"],4)
    out["decomposed_FP_forecast_bias"]=round(
        sum(r["errors"]["decomposed_fp_signed"] for r in records)/n,4)
    return out


def historical_holdout(players, q):
    """2025/26 first five actually PLAYED games. No missing games invented."""
    examples=[]
    strata=defaultdict(list)
    qa=Counter()
    for pid, seasons in players.items():
        dev=seasons.get(TRAIN) or []
        outcome=seasons.get(HOLDOUT) or []
        prior=forecast(same_team_tail(dev))
        if prior is None or not outcome:
            qa["missing_2024_25_same_team_sample_or_2025_26_played_log"] += 1
            continue
        same=outcome[0]["team"] == prior["last_sample_team"]
        group = "same_club_observed_at_2025_first_played" if same else "changed_club_between_seasons"
        qa[group+"_players"] += 1
        # All first five played outcomes use only the previous season.
        for row in outcome[:5]:
            e=_error(prior,row)
            item={"game_id":row["g"],"player_id":pid,"played_date":row["d"],
                  "first_2025_26_club_matches_prior":same,
                  "errors":e,"team_at_played_game":row["team"]}
            examples.append(item)
            strata[group].append(item)
    if len(examples) < 200:
        raise ValueError("Historical holdout sample insufficient")
    return {
        "definition":"2025_26_first_5_played_only_with_2024_25_frozen_prior",
        "selection_positive_played_game_only_NOT_DNP":True,
        "all":_quality(examples,q),
        "by_prior_club_stability":{
            name:_quality(group,q) for name,group in sorted(strata.items())},
        "distinct_players":len({r["player_id"] for r in examples}),
        "distinct_NBA_games":len({r["game_id"] for r in examples}),
        "outcomes_never_used_to_retrain_or_reselect_parameters":True,
        "qa":dict(qa),
    }


def prospective(prior, shadow, players, q, version, now):
    if now.utcoffset() is None:
        raise ValueError("Prospective research clock requires timezone")
    now=now.astimezone(timezone.utc)
    if (shadow.get("schema_version")!=1 or
            shadow.get("status")!=STATUS or
            shadow.get("adopt_on_site") is not False or
            shadow.get("population_brier_enabled") is not False):
        raise ValueError("Untrusted current first-issued p_play source")
    if (prior and (prior.get("schema_version") != SCHEMA
                   or prior.get("status") != STATUS
                   or prior.get("adopt_on_site") is not False
                   or prior.get("historical_source_index_version") != version
                   or prior.get("frozen_rule_hash") != canonical_hash(MODEL))):
        raise ValueError("Existing minutes research incompatible with immutable model")
    old=list((prior or {}).get("issued",[]))
    bykey={}
    source={}
    for p in shadow["issued"]:
        key=(p["game_id"],p["player_id"])
        if key in source:
            raise ValueError("Duplicate original p_play first issue")
        first=instant(p["issued_at_utc"])
        lock=instant(p["individual_lock_utc"])
        tip=instant(p["tipoff_utc"])
        if not (first<lock<tip and tip-lock==LOCK and first<=now):
            raise ValueError("Invalid original p_play provenance clock")
        source[key]=p
    for oldrow in old:
        key=(oldrow["game_id"],oldrow["player_id"])
        p=source.get(key)
        if (p is None or key in bykey
                or oldrow.get("p_play_first_issued_at_utc") != p["issued_at_utc"]
                or oldrow.get("team") != p["team"]
                or oldrow.get("frozen_rule_hash") != canonical_hash(MODEL)
                or oldrow.get("historical_source_index_version") != version
                or oldrow.get("observed_game_outcome") != "UNKNOWN"
                or oldrow.get("adopt_on_site") is not False
                or instant(oldrow["issued_at_utc"]) >= instant(p["individual_lock_utc"])):
            raise ValueError("Prior immutable minutes issue modified or invalid")
        bykey[key]=oldrow
    qa=Counter()
    additions=[]
    for key,p in sorted(source.items()):
        if key in bykey:
            qa["already_issued"]+=1
            continue
        if p.get("club_link_evidence")!="same_club_independent_ESPN_ID_observed":
            qa["weak_ESPN_identity_abstain"]+=1
            continue
        tip=instant(p["tipoff_utc"])
        lock=instant(p["individual_lock_utc"])
        if now>=lock or tip > now+HORIZON:
            qa["outside_new_prospective_issue_window"]+=1
            continue
        previous=(players.get(p["player_id"]) or {}).get(HOLDOUT) or []
        tail=same_team_tail(previous)
        pred=forecast(tail)
        if pred is None:
            qa["insufficient_2025_26_same_club_played_minutes"]+=1
            continue
        if pred["last_sample_team"]!=p["team"]:
            qa["prior_club_conflict_abstain"]+=1
            continue
        if pred["sample_last_played_date"]>="2026-07-01":
            raise ValueError("Historical source leaked future season")
        band = {
            "minutes_if_play":[round(max(0,pred["minutes_if_play"]-q["minutes"]),4),
                               round(pred["minutes_if_play"]+q["minutes"],4)],
            "fp_per_minute_if_play":[round(pred["fp_per_minute_if_play"]-q["fp_per_minute"],4),
                                    round(pred["fp_per_minute_if_play"]+q["fp_per_minute"],4)],
            "fp_if_play":[round(pred["decomposed_fp_if_play"]-q["decomposed_fp"],4),
                          round(pred["decomposed_fp_if_play"]+q["decomposed_fp"],4)],
        }
        item={
            "game_id":key[0],"player_id":key[1],"team":p["team"],
            "game_utc":p["tipoff_utc"],
            "individual_lock_utc":p["individual_lock_utc"],
            "p_play_first_issued_at_utc":p["issued_at_utc"],
            "issued_at_utc":stamp(now),
            "historical_source_index_version":version,
            "historical_training_season":"2025/26",
            "historical_source_last_game_date":pred["sample_last_played_date"],
            "frozen_rule_hash":canonical_hash(MODEL),
            "min_if_play":pred["minutes_if_play"],
            "fp_per_minute_if_play":pred["fp_per_minute_if_play"],
            "decomposed_fp_if_play":pred["decomposed_fp_if_play"],
            "direct_fp_if_play":pred["direct_last20_fp_if_play"],
            "historical_sample_played_n":pred["played_sample_n"],
            "development_2024_25_error_bands_not_guaranteed":band,
            "observed_game_outcome":"UNKNOWN",
            "game_day_membership_verified":False,
            "p_play_population_calibrated":False,
            "unconditional_FP_calculated":False,
            "research_only":True,"adopt_on_site":False,
        }
        bykey[key]=item
        additions.append(item)
        qa["new_minutes_rate_issues"]+=1
        if len(bykey)>MAX_PROSPECTIVE:
            raise ValueError("Research issuance report too large")
    return list(old)+additions, dict(qa)


def build(index, loader, pplay, now, previous=None):
    if now.utcoffset() is None:
        raise ValueError("Clock must be aware")
    now=now.astimezone(timezone.utc)
    people,hqa=historical(index,loader)
    quantiles,dev=calibration(people)
    holdout=historical_holdout(people,quantiles)
    issues,qa=prospective(previous,pplay,people,quantiles,index["version"],now)
    return {
        "schema_version":SCHEMA,"status":STATUS,"model_status":STATUS,
        "adopt_on_site":False,"updated_at_utc":stamp(now),
        "target":"positive_minutes_only_then_FP_per_minute_if_play",
        "full_game_day_roster_denominator_known":False,
        "historical_source_index_version":index["version"],
        "frozen_rule_hash":canonical_hash(MODEL),
        "frozen_structure_development_only":MODEL,
        "source_qa":hqa,
        "2024_25_chronological_development_residuals":dev,
        "2025_26_untouched_early_season_played_holdout":holdout,
        "issued":issues,
        "issued_total":len(issues),
        "issued_QA":qa,
        "model_selection_on_2025_26_holdout":False,
        "unconditional_FP_enabled":False,
        "p_play_assumed_calibrated":False,
        "actual_keep_transfer_backtest_run":False,
        "training_negative_from_UNKNOWN":False,
        "quality_gate":{
            "2025_26_holdout_is_played_game_only":True,
            "2026_27_prospective_game_labels_verified":False,
            "true_p_play_denominator_verified":False,
            "model_deployed":False,"adopt_on_site":False,
        },
        "limitations":[
            "Only historical positive-minute appearances; no true DNP denominator.",
            "Development 2024/25 chronological played games, 2025/26 untouched holdout.",
            "Prospective frozen 2025/26 same-team tail; absent player remains UNKNOWN.",
            "No current-season outcomes/features or medical status used to construct forecasts.",
            "FP/minute is noisy at short minutes and includes result/venue effects.",
            "2024/25 dev q90 absolute-error bands are NOT conformal calibrated future intervals.",
            "Every prospective forecast has its real issuance time before individual lock.",
            "No multiplication by unvalidated p_play; no claim of unconditional expected FP.",
            "No site, Firestore, team, Sports.ru transfers, prices, or deployment touched.",
        ],
    }


def run():
    read=lambda path:json.loads((DATA/path).read_text(encoding="utf8"))
    index=read("history/index.json")
    now=datetime.now(timezone.utc)
    path=DATA/"conditional_minutes_fp_research.json"
    old=read(path.name) if path.exists() else {}
    result=build(index,lambda f:read("history/"+f),
                 read("p_play_shadow_research.json"),now,old)
    if (not old or {k:v for k,v in result.items() if k!="updated_at_utc"}
            != {k:v for k,v in old.items() if k!="updated_at_utc"}):
        tmp=path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),
                       encoding="utf8")
        tmp.replace(path)
    return {
        "historical_2024_25_dev_cases":
            result["2024_25_chronological_development_residuals"]["2024_25_past_only_dev_cases"],
        "historical_2025_26_holdout_played_cases":
            result["2025_26_untouched_early_season_played_holdout"]["all"]["played_cases"],
        "first_issued_prospective_minutes":result["issued_total"],
        "issue_QA":result["issued_QA"],
        "model_deployed":False,
    }


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
