"""Research-only historical ablation: can fresh FP/minute add to fresh minutes?

All variants share PR #115's PREOUTCOME candidate universe, exact retrospective
ESPN tipoff and simulated T-30. Historical positive boxscore availability is
assumed at +12/24/48h; it is NOT evidence of actual first-seen publication.
No DNP from missing rows, no historical roster membership assertion, no
unconditional expected FP or production model selection.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from math import isfinite, sqrt
from random import Random
import json

from src.sync import DATA
from src.rolling_decision_research import instant, canonical_hash
from src.conditional_minutes_fp_research import forecast, same_team_tail
from src.historical_current_minutes_walkforward_research import load_history, TRANSITIONS
from src.historical_appearance_proxy_research import validated_fixtures
from src.historical_prelock_minutes_replay_research import (
    attach_played_to_calendar, reconstruct_player, AVAILABILITY_LAGS_H,
    DEFAULT_LAG_H,
)

STATUS = "research_only_not_deployed"
RATE_PRIOR_GAMES = (5, 10)  # Fixed comparisons, not selected by holdout.
SCORE_FIELDS = (
    "frozen_previous_season_FP",
    "updated_minutes_frozen_rate_FP",
    "frozen_minutes_shrunk_current_rate_5_FP",
    "updated_minutes_shrunk_current_rate_5_FP",
    "updated_minutes_shrunk_current_rate_10_FP",
    "updated_minutes_current_rate_only_FP",
)
PRIMARY = "updated_minutes_shrunk_current_rate_5_FP"
CONTROL = "updated_minutes_frozen_rate_FP"
BOOTSTRAP_DRAWS = 200
BOOTSTRAP_SEED = 20261029


def enrich_issued_proxy(issued, positive, previous, lag_hours):
    """Attach ONLY previously available rate evidence; never select by outcome."""
    if lag_hours not in AVAILABILITY_LAGS_H:
        raise ValueError("Unregistered historical first-seen assumption")
    base = forecast(same_team_tail(previous))
    if base is None and issued:
        raise ValueError("Prelock proxy without frozen previous-season prior")
    observed = sorted(positive, key=lambda x:(x["tip"],x["g"]))
    extra = []
    for issued_row in issued:
        cutoff = instant(issued_row["simulated_individual_lock_utc"])
        known = [x for x in observed if x["tip"] + timedelta(hours=lag_hours) <= cutoff]
        tail = same_team_tail(known)
        last = tail[-5:]
        if (base is None or not last
                or base["last_sample_team"] != issued_row["club_from_previous_positive_game"]
                or tail[-1]["team"] != base["last_sample_team"]
                or len(last) != issued_row["prior_current_same_team_n"]
                or len(tail) != issued_row["prior_current_appearances_total"]
                or last[-1]["tip"] != instant(issued_row["source_last_played_tipoff_utc"])):
            raise ValueError("Changed replay cohort or mismatched earlier current form")
        if (any(x["tip"] >= cutoff or x["g"] == issued_row["game_id"]
                for x in last)
                or last[-1]["tip"] + timedelta(hours=lag_hours) > cutoff):
            raise ValueError("FP/minute source not available before simulated T-30")
        n = len(last)
        denom = sum(float(x["min"]) for x in last)
        if denom <= 0:
            raise ValueError("Zero earlier played-minute exposure")
        current_rate = sum(float(x["fp"]) for x in last) / denom
        historical_rate = base["fp_per_minute_if_play"]
        if not (isfinite(current_rate) and isfinite(historical_rate)):
            raise ValueError("Nonfinite FP-per-minute evidence")
        def blend(prior):
            return (prior*historical_rate+n*current_rate)/(prior+n)
        old_minutes = issued_row["baseline_minutes"]
        updated_minutes = issued_row["challenger_minutes"]
        variants = {
            SCORE_FIELDS[0]: float(issued_row["baseline_fp"]),
            SCORE_FIELDS[1]: float(issued_row["challenger_fp"]),
            SCORE_FIELDS[2]: round(old_minutes*blend(5),5),
            SCORE_FIELDS[3]: round(updated_minutes*blend(5),5),
            SCORE_FIELDS[4]: round(updated_minutes*blend(10),5),
            SCORE_FIELDS[5]: round(updated_minutes*current_rate,5),
        }
        result = {
            "player_id": issued_row["player_id"],
            "game_id": issued_row["game_id"],
            "et_date": issued_row["date"],
            "result_label": issued_row["result_label"],
            "predicted_minutes": updated_minutes,
            "prior_current_same_team_n": n,
            "prior_current_appearances_total": len(tail),
            "simulated_prelock_cutoff": issued_row["simulated_individual_lock_utc"],
            "last_feature_assumed_available_utc":
                (last[-1]["tip"]+timedelta(hours=lag_hours)).isoformat(),
            "variants": variants,
        }
        if issued_row["result_label"] == "positive_minutes_verified_historical_boxscore":
            if "actual_fp" not in issued_row or "actual_minutes" not in issued_row:
                raise ValueError("Claimed played outcome lacks audited stats")
            result["actual_FP"] = float(issued_row["actual_fp"])
        elif issued_row["result_label"] == "UNKNOWN_no_positive_log_not_DNP":
            if "actual_fp" in issued_row or "actual_minutes" in issued_row:
                raise ValueError("UNKNOWN supplied a postgame scoring label")
        else:
            raise ValueError("Unrecognized played/UNKNOWN label")
        extra.append(result)
    return extra


def _stats(rows, field):
    n = len(rows)
    if not n:
        return {"played_pairs":0}
    errors=[r["variants"][field]-r["actual_FP"] for r in rows]
    base_err=[abs(r["variants"][SCORE_FIELDS[0]]-r["actual_FP"]) for r in rows]
    control_err=[abs(r["variants"][CONTROL]-r["actual_FP"]) for r in rows]
    errs=[abs(x) for x in errors]
    return {
        "played_pairs":n,
        "MAE":round(sum(errs)/n,4),
        "RMSE":round(sqrt(sum(x*x for x in errors)/n),4),
        "prediction_minus_actual_bias":round(sum(errors)/n,4),
        "paired_MAE_gain_vs_frozen_previous_season_FP":round(
            sum(a-b for a,b in zip(base_err,errs))/n,4),
        "paired_MAE_gain_vs_updated_minutes_frozen_rate_FP":round(
            sum(a-b for a,b in zip(control_err,errs))/n,4),
        "fraction_better_than_updated_minutes_frozen_rate_FP":round(
            sum(b < a for a,b in zip(control_err,errs))/n,4),
    }


def _date_cluster_interval(rows, field, repeats=BOOTSTRAP_DRAWS):
    """Exploratory ET-date clustered interval; not a model-adoption criterion."""
    grouped=defaultdict(lambda:[0.0,0])
    for row in rows:
        gain=(abs(row["variants"][CONTROL]-row["actual_FP"])-
              abs(row["variants"][field]-row["actual_FP"]))
        pair=grouped[row["et_date"]]
        pair[0]+=gain
        pair[1]+=1
    dates=sorted(grouped)
    if len(dates)<20:
        return {"ET_dates":len(dates),"gain_95pct_exploratory":None}
    random=Random(BOOTSTRAP_SEED+len(dates)+len(rows))
    totals=[]
    values=[grouped[d] for d in dates]
    for _ in range(repeats):
        picked=[values[random.randrange(len(values))] for _ in dates]
        denominator=sum(x[1] for x in picked)
        totals.append(sum(x[0] for x in picked)/denominator)
    totals.sort()
    return {
        "ET_dates":len(dates),
        "gain_95pct_exploratory":[round(totals[int(.025*(repeats-1))],4),
                                  round(totals[int(.975*(repeats-1))],4)],
        "resampling_unit":"ET_date_not_independent_player_games",
        "repeats":repeats,
        "multiple_comparisons_not_corrected":True,
    }


def summary(rows):
    if len({(r["game_id"],r["player_id"]) for r in rows})!=len(rows):
        raise ValueError("Duplicate historical issued FP/game opportunity")
    played=[r for r in rows if "actual_FP" in r]
    unknown=[r for r in rows if "actual_FP" not in r]
    if (len(played)+len(unknown)!=len(rows)
            or any(r["result_label"]!="UNKNOWN_no_positive_log_not_DNP" for r in unknown)):
        raise ValueError("Unknown outcome was scored or omitted")
    def subset(sub):
        return {
            "paired_played_only":len(sub),
            "by_FP_variant":{field:_stats(sub,field) for field in SCORE_FIELDS},
        }
    report = {
        "prelock_proxy_issues":len(rows),
        "scored_positive_minutes_only":len(played),
        "UNKNOWN_not_DNP_or_zero":len(unknown),
        "distinct_proxy_players":len({r["player_id"] for r in rows}),
        "distinct_scored_ET_dates":len({r["et_date"] for r in played}),
        "all_positive_played":subset(played),
        "early_form_3_to_9_prior_appearances":subset([
            r for r in played if 3<=r["prior_current_appearances_total"]<=9]),
        "later_form_10_plus_prior_appearances":subset([
            r for r in played if r["prior_current_appearances_total"]>=10]),
        "prior_same_club_sample_n":{
            str(n):subset([r for r in played if r["prior_current_same_team_n"]==n])
            for n in (3,4,5)},
        "predicted_minutes_groups":{
            "below_18":subset([r for r in played if r["predicted_minutes"]<18]),
            "18_to_30":subset([r for r in played if 18<=r["predicted_minutes"]<30]),
            "30_plus":subset([r for r in played if r["predicted_minutes"]>=30]),
        },
        "date_cluster_exploratory_gain_vs_minutes_only":{
            name:_date_cluster_interval(played,name)
            for name in (
                "updated_minutes_shrunk_current_rate_5_FP",
                "updated_minutes_shrunk_current_rate_10_FP",
            )},
        "source_prediction_hash_without_postgame_labels":canonical_hash([
            {k:v for k,v in r.items() if k not in ("result_label","actual_FP")}
            for r in rows]),
    }
    if sum(report["predicted_minutes_groups"][x]["paired_played_only"]
           for x in ("below_18","18_to_30","30_plus"))!=len(played):
        raise ValueError("Predicted-minute stratification drift")
    return report


def build(index,loader,identity,calendar):
    history,hqa=load_history(index,loader)
    fixtures=validated_fixtures(calendar)
    high={pid for pid,p in (identity.get("players") or {}).items()
          if isinstance(p,dict) and p.get("confidence")=="high"}
    if len(high & set(history))<200:
        raise ValueError("Historical identity audit coverage insufficient")
    result={}
    qa=Counter()
    for previous_year,target in TRANSITIONS:
        by_club=defaultdict(list)
        for g in fixtures[target]:
            by_club[g["home"]].append(g)
            by_club[g["away"]].append(g)
        if len(fixtures[target])!=1230:
            raise ValueError("Incomplete historical fixture season")
        players=[]
        for pid in sorted(high&set(history)):
            year_data=history[pid]
            previous=year_data.get(previous_year,[])
            prior=forecast(same_team_tail(previous))
            if prior is None:
                qa["no_previous_frozen_same_team_prior"]+=1
                continue
            positive=attach_played_to_calendar(
                year_data.get(target,[]),fixtures[target],target)
            players.append((pid,previous,positive,by_club[prior["last_sample_team"]]))
        by_lag={}
        for lag in AVAILABILITY_LAGS_H:
            observations=[]
            for pid,previous,positive,club_games in players:
                issued,old_qa=reconstruct_player(
                    pid,previous,positive,club_games,lag)
                extended=enrich_issued_proxy(issued,positive,previous,lag)
                if len(extended)!=len(issued):
                    raise ValueError("Historical T-30 cohort altered by rate feature")
                observations.extend(extended)
            observations.sort(key=lambda x:(x["simulated_prelock_cutoff"],
                                            x["game_id"],x["player_id"]))
            by_lag[str(lag)]=summary(observations)
        result[target]={
            "role":"historical_development_diagnostic" if target=="2024/25"
                else "reused_historical_research_not_pristine_holdout",
            "high_confidence_players_with_previous_frozen_prior":len(players),
            "by_assumed_previous_boxscore_availability_hours":by_lag,
        }
    return {
        "schema_version":1,"status":STATUS,"model_status":STATUS,
        "adopt_on_site":False,
        "source_history_version":index["version"],
        "history_qa":hqa,
        "source_exact_historical_tipoff_status":calendar["calendar_status"],
        "source_T_minus_30_cohort":"historical_prelock_minutes_replay_research_v1",
        "previous_season_FP_per_minute_source":"fixed_2025_26_frozen_structure_applied_per_prior_season",
        "pre_registered_for_future_2026_27_evaluation":False,
        "rate_variants_predeclared_for_this_retro_analysis":list(SCORE_FIELDS),
        "rate_comparison":"historical FP/minute vs + prior same-team 3-5 games (sum FP / sum minutes)",
        "shrinkage_priors_in_games":list(RATE_PRIOR_GAMES),
        "by_target_season":result,
        "source_qa":dict(qa),
        "quality_gate":{
            "only_prelock_assumed_available_previous_game_stats_as_features":True,
            "missing_positive_log_not_DNP":True,
            "historical_source_timestamp_assumptions_not_verified":True,
            "2025_26_is_reused_not_independent_pristine_holdout":True,
            "no_full_P_play_or_unconditional_FP_validated":True,
            "future_2026_27_prospective_heldout_comparison_required":True,
            "ablation_does_not_select_production_model":True,
            "adopt_on_site":False,
        },
        "limitations":[
            "Retrospective ESPN tipoffs are confirmed, but historical publication timing is not.",
            "A past boxscore is ASSUMED available at +12/24/48h, not verified first-seen.",
            "Candidate player/team cohort inferred from earlier positive-minute played rows.",
            "No target-game played outcome used for candidate selection or rate calculation.",
            "Absent positive-minute row = UNKNOWN, never zero fantasy credit or DNP.",
            "Multiple correlated player games on same ET date; date intervals exploratory.",
            "FP-per-minute includes team W/L and location terms, not separate forecasts of those variables.",
            "Last 3-5 games may be noisy; previous prior strength 5/10 is exploratory.",
            "Historical 2025/26 has already been explored; comparisons cannot prove out-of-sample gain.",
            "No production model, Firebase, Sports.ru account, prices, transfers or Hosting changed.",
        ],
    }


def run():
    def read(p):
        return json.loads((DATA/p).read_text(encoding="utf8"))
    obj=build(read("history/index.json"),
              lambda name:read("history/"+name),
              read("identity.json"),read("historical_tipoffs.json"))
    target=DATA/"historical_fp_rate_prelock_ablation_research.json"
    contents=json.dumps(obj,ensure_ascii=False,indent=2)+"\n"
    if not target.exists() or target.read_text(encoding="utf8")!=contents:
        tmp=target.with_suffix(".tmp")
        tmp.write_text(contents,encoding="utf8")
        tmp.replace(target)
    return {
        "research_only":True,
        "adopt_on_site":False,
        "by_target_season":{
            s:v["by_assumed_previous_boxscore_availability_hours"][str(DEFAULT_LAG_H)]
             ["all_positive_played"]["by_FP_variant"]
            for s,v in obj["by_target_season"].items()},
    }


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
