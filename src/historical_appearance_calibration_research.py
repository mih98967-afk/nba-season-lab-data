"""Development-only calibration audit for the historical *logged-appearance* proxy.

Do not call this NBA p_play or a DNP model: no logged positive-minute
appearance does not establish that an athlete was on the active game-day
roster, injured or explicitly marked didNotPlay. The selected sample also
omits recently inactive players and many trades.

Raw candidate parameters were selected on 2024/25 in the frozen PR #35
research report. A one-parameter monotone shrink to the 2024/25 selected
appearance rate is fit exclusively on the SAME development year to improve
proper-score reliability. 2025/26 is touched only once for final evaluation.
The development fit is in-sample, not independently validated; this is
strictly research_only_not_deployed and cannot feed current production
p_play, FP or KEEP/TRANSFER.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from zoneinfo import ZoneInfo
import json
import math

from src.sync import DATA
from src.historical_appearance_proxy_research import (
    STATUS, BASELINE, cohort, estimate, positive_logs, validated_fixtures,
)

UTC = timezone.utc
ET = ZoneInfo("America/New_York")
SCHEMA = 1
# One prespecified calibration family; no holdout grid search.
SHRINK_GRID = (0.0, 0.01, 0.025, 0.05, 0.075, 0.1,
               0.15, 0.2, 0.25, 0.3, 0.4, 0.5)
REPEATS = 400
SEED = 20261027


def _score(value, label, metric):
    if not (isinstance(label, int) and label in (0, 1)
            and isinstance(value, (float, int))
            and 0 < value < 1 and math.isfinite(value)):
        raise ValueError("Strict probability/label validation failed")
    if metric == "brier":
        return (value-label)**2
    if metric == "logloss":
        return -(label*math.log(value)+(1-label)*math.log1p(-value))
    raise ValueError("Unknown proper score")


def _pairs(rows, param):
    pairs = []
    for row in rows:
        y = row.get("appearance_logged_in_exact_game")
        if type(y) is not int or y not in (0, 1):
            raise ValueError("Historical target is not binary observed log")
        player = row.get("pid")
        if not isinstance(player, str) or not player:
            raise ValueError("Historical sample lacks player ID")
        pairs.append((player, y, estimate(row, param)))
    if not pairs:
        raise ValueError("No historical appearances to score")
    return pairs


def _adjust(p, shrink, prevalence):
    """Preserve ranking; reduce extreme probabilities toward dev prevalence."""
    if not (0 < p < 1 and 0 <= shrink <= 1 and 0 < prevalence < 1):
        raise ValueError("Unusable calibration inputs")
    return (1-shrink)*p + shrink*prevalence


def fit_dev(dev):
    """Fit ONLY development data; test data is not an input to this function."""
    if len(dev)<1000:
        raise ValueError("Insufficient development observations")
    prevalence = (1+sum(y for _,y,_ in dev))/(2+len(dev))
    opts = []
    for shrink in SHRINK_GRID:
        dev_loss = sum(_score(_adjust(p,shrink,prevalence),y,"logloss")
                       for _,y,p in dev)/len(dev)
        opts.append((dev_loss,shrink))
    loss,shrink = min(opts)
    return {"selected_shrink":shrink,
            "development_smoothed_prevalence":prevalence,
            "development_logloss_after_fit":loss,
            "training_rows":len(dev),
            "grid":list(SHRINK_GRID),
            "objective":"minimum_development_selected_proxy_logloss_only"}


def _calibration_table(values, buckets=10):
    groups = defaultdict(lambda:[0,0.,0.])
    for p,y in values:
        k=min(buckets-1,int(p*buckets))
        a=groups[k]
        a[0]+=1
        a[1]+=p
        a[2]+=y
    n=len(values)
    return {
        "buckets":{str(i):{
            "n":groups[i][0],
            "mean_score":round(groups[i][1]/groups[i][0],4),
            "observed_positive_log_fraction":round(groups[i][2]/groups[i][0],4)}
            for i in sorted(groups) if groups[i][0]},
        "equal_width_10bin_ECE":sum(
            abs((a[1]-a[2])/a[0])*a[0]/n for a in groups.values()),
        "high_confidence_over_90_count":sum(1 for p,_ in values if p>=0.9),
        "high_confidence_over_90_observed_rate":(
            sum(y for p,y in values if p>=0.9)/
            sum(1 for p,y in values if p>=0.9)
            if any(p>=0.9 for p,_ in values) else None),
        "high_confidence_over_90_avg_predicted":(
            sum(p for p,_ in values if p>=0.9)/
            sum(1 for p,_ in values if p>=0.9)
            if any(p>=0.9 for p,_ in values) else None)
    }


def evaluate(baseline, candidate, calibration, metric_label):
    if not (len(baseline)==len(candidate) and
            len(candidate)==len(calibration) and len(baseline)>0):
        raise ValueError("Unpaired historical evaluations")
    labels=[y for _,y,_ in baseline]
    if labels!=[y for _,y,_ in candidate] or labels!=[y for _,y,_ in calibration]:
        raise ValueError("Different target order in paired comparisons")
    def score(pairs):
        return {
            "brier":sum(_score(p,y,"brier") for _,y,p in pairs)/len(pairs),
            "logloss":sum(_score(p,y,"logloss") for _,y,p in pairs)/len(pairs),
            "reliability":_calibration_table([(p,y) for _,y,p in pairs]),
        }
    return {metric_label:{"baseline":score(baseline),
                          "raw":score(candidate),
                          "calibrated":score(calibration)}}


def paired_player_ci(baseline, raw, calibrated, draws=REPEATS, seed=SEED):
    """Resample WHOLE players; never treat consecutive matches as iid."""
    if not(len(baseline)==len(raw)==len(calibrated)):
        raise ValueError("Paired player records required")
    by_player=defaultdict(lambda:[0,0.,0.,0.,0.,0.,0.])
    for (pid0,y0,b),(pid1,y1,p),(pid2,y2,c) in zip(baseline,raw,calibrated):
        if (pid0,y0)!=(pid1,y1) or (pid0,y0)!=(pid2,y2):
            raise ValueError("Unaligned paired player-game records")
        v=by_player[pid0]
        v[0]+=1
        v[1]+=_score(b,y0,"brier")-_score(p,y0,"brier")
        v[2]+=_score(p,y0,"brier")-_score(c,y0,"brier")
        v[3]+=_score(b,y0,"brier")-_score(c,y0,"brier")
        v[4]+=_score(b,y0,"logloss")-_score(p,y0,"logloss")
        v[5]+=_score(p,y0,"logloss")-_score(c,y0,"logloss")
        v[6]+=_score(b,y0,"logloss")-_score(c,y0,"logloss")
    ids=sorted(by_player)
    if len(ids)<2:
        return None
    rng=Random(seed)
    vals=[by_player[k] for k in ids]
    gains=[[] for _ in range(6)]
    for _ in range(draws):
        group=[vals[rng.randrange(len(vals))] for _ in vals]
        n=sum(v[0] for v in group)
        if not n:
            raise ValueError("Empty player bootstrap")
        for idx in range(6):
            gains[idx].append(sum(v[idx+1] for v in group)/n)
    for val in gains:
        val.sort()
    names=("brier_baseline_to_raw","brier_raw_to_calibrated",
           "brier_baseline_to_calibrated","logloss_baseline_to_raw",
           "logloss_raw_to_calibrated","logloss_baseline_to_calibrated")
    return {
        "independent_resampling_unit":"historical_NBA_player",
        "game_or_team_dependence_not_fully_accounted":True,
        "player_clusters":len(ids), "repeats":draws,"seed":seed,
        "positive_gain_means_lower_loss":True,
        "gain_intervals_95pct":{
            k:[round(x[int(0.025*(draws-1))],6),
               round(x[int(0.975*(draws-1))],6)]
            for k,x in zip(names,gains)}
    }


def run_report(history, identity, historical_calendar, frozen_model, now):
    if now.utcoffset() is None:
        raise ValueError("Timezone-aware audit timestamp required")
    if (frozen_model.get("schema_version") != 1 or
        frozen_model.get("status") != STATUS or
        frozen_model.get("adopt_on_site") is not False or
        frozen_model.get("training_season") != "2024/25" or
        frozen_model.get("untouched_holdout_season") != "2025/26" or
        frozen_model.get("confirmed_DNP_observations") != 0):
        raise ValueError("Untrusted or accidentally deployable frozen historical model")
    params = frozen_model.get("selected_development_params", {})
    candidate = (params.get("shrinkage"),params.get("recent_weight"))
    if any(type(x) not in (float,int) for x in candidate):
        raise ValueError("Invalid pretrained development parameters")
    games = validated_fixtures(historical_calendar)
    logs,qa = positive_logs(history,identity,games)
    by_year,cohort_qa = cohort(games,logs)
    dev=by_year["2024/25"]; test=by_year["2025/26"]
    for season,rows in (("2024/25",dev),("2025/26",test)):
        reference = frozen_model["eligible_sample_qa"][season]
        if (len(rows) != reference["eligible_proxy_player_games"]
            or len({r["pid"] for r in rows}) != reference["distinct_players"]
            or sum(r["appearance_logged_in_exact_game"] for r in rows)
            != reference["logged_appearances"]):
            raise ValueError("Historical sample changed: cannot reuse frozen parameters")
    dev_raw=_pairs(dev,candidate)
    fit=fit_dev(dev_raw)  # Deliberately no access to holdout yet.
    def prepare(rows,raw):
        base=_pairs(rows,BASELINE)
        calibrated=[(pid,y,_adjust(p,fit["selected_shrink"],
                                  fit["development_smoothed_prevalence"]))
                    for pid,y,p in raw]
        return base,calibrated
    dev_base,dev_cal = prepare(dev,dev_raw)
    test_raw = _pairs(test,candidate)
    test_base,test_cal=prepare(test,test_raw)
    dev_metric=evaluate(dev_base,dev_raw,dev_cal,"development_fit_in_sample")
    test_metric=evaluate(test_base,test_raw,test_cal,"holdout_never_used_for_fit")
    bootstrap=paired_player_ci(test_base,test_raw,test_cal)
    snap=lambda x:round(x,6)
    for panel in (dev_metric["development_fit_in_sample"],
                  test_metric["holdout_never_used_for_fit"]):
        for v in panel.values():
            v["brier"]=snap(v["brier"])
            v["logloss"]=snap(v["logloss"])
            v["reliability"]["equal_width_10bin_ECE"]=snap(v["reliability"]["equal_width_10bin_ECE"])
            for metric in ("high_confidence_over_90_observed_rate",
                           "high_confidence_over_90_avg_predicted"):
                if v["reliability"][metric] is not None:
                    v["reliability"][metric]=snap(v["reliability"][metric])
    metrics=test_metric["holdout_never_used_for_fit"]
    return {
        "schema_version":SCHEMA,"status":STATUS,"model_status":STATUS,
        "adopt_on_site":False,"evaluated_at_utc":now.astimezone(UTC).isoformat(),
        "scope":"retrospective_selected_logged_appearance_PROXY_NOT_DNP",
        "model":"development_only_monotone_prevalence_shrink",
        "target":"positive_minute_record_in_last_observed_team_fixture",
        "actual_DNP_label_count":0,
        "full_game_day_active_roster_verified":False,
        "p_play_calibrated_for_fantasy_population":False,
        "used_in_live_site_or_forecast":False,
        "keep_transfer_advantage_claim":False,
        "frozen_raw_parameters":{"shrinkage":candidate[0],"recent_weight":candidate[1]},
        "development_sample":cohort_qa["2024/25"],
        "holdout_sample":cohort_qa["2025/26"],
        "calibration_training_only_2024_25": {
            "selected_shrink":fit["selected_shrink"],
            "smoothed_development_appearance_rate":snap(fit["development_smoothed_prevalence"]),
            "objective":fit["objective"],"grid":fit["grid"],
            "development_fit_is_in_sample":True},
        "development":dev_metric["development_fit_in_sample"],
        "holdout":metrics,"player_cluster_uncertainty":bootstrap,
        "raw_to_calibrated_holdout_brier_gain":
            snap(metrics["raw"]["brier"]-metrics["calibrated"]["brier"]),
        "raw_to_calibrated_holdout_logloss_gain":
            snap(metrics["raw"]["logloss"]-metrics["calibrated"]["logloss"]),
        "calibrated_better_than_raw_on_both_proper_scores":
            (metrics["calibrated"]["brier"]<metrics["raw"]["brier"] and
             metrics["calibrated"]["logloss"]<metrics["raw"]["logloss"]),
        "calibration_not_an_adoption_gate":True,
        "limitations":[
            "A missing logged appearance is not a verified DNP, illness, inactive roster, or tenure proof.",
            "Only recently active high-identity players; long-term injured and transfers are underrepresented.",
            "Calibration shrinks scores toward development prevalence; not a universal p_play model.",
            "Raw parameters and shrink hyperparameter both fitted on development; development scores are optimistic.",
            "2025/26 is untouched holdout; no iteration based on its measured metrics is authorized.",
            "Bootstrap clusters by player, not by both player and NBA fixture/team, so dependence remains.",
            "Historical finalized fixture calendars do not prove historically-known pregame schedule.",
            "No individual Sports.ru acquisition/sale prices, moves, or verified KEEP/TRANSFER uplift.",
        ],
    }


def run():
    def read(n):return json.loads((DATA/n).read_text(encoding="utf8"))
    result=run_report(read("nba_history.json"),read("identity.json"),
                      read("historical_tipoffs.json"),
                      read("historical_appearance_proxy_research.json"),
                      datetime.now(UTC))
    target=DATA/"historical_appearance_calibration_research.json"
    tmp=target.with_suffix(".tmp")
    tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
    tmp.replace(target)
    return {"status":STATUS,"adopt_on_site":False,
            "calibrated_better_on_both":result["calibrated_better_than_raw_on_both_proper_scores"],
            "holdout_summary":{name:{"brier":item["brier"],"logloss":item["logloss"]}
                              for name,item in result["holdout"].items()},
            "preselected_shrink":result["calibration_training_only_2024_25"]["selected_shrink"]}


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
