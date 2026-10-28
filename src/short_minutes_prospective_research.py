"""Append-only, truly prospective short-minutes risk shadow (research ONLY).

Issue after the frozen 2024/25 development parameters exist, *before each
individual 2026/27 player lock*. Only issue against immutable prelock
conditional-minutes first issues and the same first-issued p_play identity.
Absolutely no archived 2026/27 outcome, after-lock retroactive insertion,
DNP inference, live model adoption, Firebase or user-team mutation.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from math import isfinite
import json

from src.sync import DATA
from src.rolling_decision_research import canonical_hash, instant, stamp
from src.short_minutes_role_bands_research import (
    STATUS, MODEL, GROUPS, group_by_predicted_minutes,
)

LOCK = timedelta(minutes=30)
MAX_ISSUES = 20000


def validate_role(role, minute_source):
    if (role.get("schema_version") != 1 or role.get("status") != STATUS
            or role.get("adopt_on_site") is not False
            or role.get("historical_index_version") != minute_source.get(
                "historical_source_index_version")
            or role.get("immutable_2024_25_model_hash") != minute_source.get("frozen_rule_hash")
            or role.get("development_source") != "2024_25_rolling_same_team_past_played_only"
            or role.get("test_source") != "2025_26_first_five_played_only_already_inspected_by_PR65"
            or role.get("protocol",{}).get("no_selection_or_refitting_on_2025_26_holdout") is not True
            or role.get("protocol",{}).get("strata_selected_after_previous_2025_26_audit") is not True
            or role.get("protocol",{}).get("threshold_short_actual_minutes") != 10.0
            or role.get("quality_gate",{}).get("adopt_on_site") is not False
            or role.get("quality_gate",{}).get("fresh_unused_holdout_for_new_strata") is not False
            or role.get("quality_gate",{}).get("unconditional_FP_from_this_risk_allowed") is not False):
        raise ValueError("Untrusted or retroactively fitted short-minutes source")
    params = role["dev_only_fit"]
    if (params.get("development_cases") != 3032 or
            params.get("no_2025_26_outcome_used_for_fitting") is not True or
            set(params.get("group_parameters_fitted_on_dev_only", {})) != set(GROUPS)):
        raise ValueError("Unsealed development-only risk parameters")
    baseline = params["global_dev_played_only_short_baseline_probability"]
    if (type(baseline) not in (int, float) or not 0 < baseline < 1 or
            not isfinite(baseline)):
        raise ValueError("Illegal baseline probability")
    for group in GROUPS:
        row = params["group_parameters_fitted_on_dev_only"][group]
        p, q = (row["dev_only_smoothed_conditional_short_probability"],
                row["dev_only_residual_q90_minutes"])
        if (type(p) not in (int, float) or type(q) not in (int, float)
                or not isfinite(p) or not isfinite(q)
                or not (0 < p < 1 and q > 0)
                or row.get("dev_cases",0) < 100):
            raise ValueError("Illegal development-only prior")
    return params, canonical_hash(params)


def validate_minute_first_issue(issue, pplay, minute_source, now):
    tip = instant(issue["game_utc"])
    lock = instant(issue["individual_lock_utc"])
    minutes_issued = instant(issue["issued_at_utc"])
    pplay_first = instant(issue["p_play_first_issued_at_utc"])
    if (pplay is None or issue.get("game_id") != pplay.get("game_id")
            or issue.get("player_id") != pplay.get("player_id")
            or issue.get("team") != pplay.get("team")
            or issue["game_utc"] != pplay.get("tipoff_utc")
            or issue["individual_lock_utc"] != pplay.get("individual_lock_utc")
            or issue["p_play_first_issued_at_utc"] != pplay.get("issued_at_utc")
            or not (pplay_first <= minutes_issued < lock < tip)
            or tip-lock != LOCK or minutes_issued > now
            or issue.get("historical_training_season") != "2025/26"
            or issue.get("historical_source_last_game_date","9999") >= "2026-07-01"
            or issue.get("historical_source_index_version") != minute_source["historical_source_index_version"]
            or issue.get("frozen_rule_hash") != minute_source["frozen_rule_hash"]
            or issue.get("observed_game_outcome") != "UNKNOWN"
            or issue.get("research_only") is not True
            or issue.get("adopt_on_site") is not False
            or issue.get("p_play_population_calibrated") is not False
            or issue.get("unconditional_FP_calculated") is not False
            or issue.get("game_day_membership_verified") is not False):
        raise ValueError("Minutes first issue is not genuinely prelock/identical")
    value=issue["min_if_play"]
    if type(value) not in (int,float) or not isfinite(value) or value < 0:
        raise ValueError("Malformed frozen conditional minutes estimate")


def make_frozen_row(issue, params, seal, now):
    group = group_by_predicted_minutes(issue["min_if_play"])
    dev = params["group_parameters_fitted_on_dev_only"][group]
    q = float(dev["dev_only_residual_q90_minutes"])
    q0 = float(params["original_global_dev_q90_minutes"])
    predicted = float(issue["min_if_play"])
    return {
        "game_id":issue["game_id"],"player_id":issue["player_id"],"team":issue["team"],
        "game_utc":issue["game_utc"],
        "individual_lock_utc":issue["individual_lock_utc"],
        "minutes_first_issued_at_utc":issue["issued_at_utc"],
        "p_play_first_issued_at_utc":issue["p_play_first_issued_at_utc"],
        "risk_first_issued_at_utc":stamp(now),
        "minutes_source_issue_sha256":canonical_hash(issue),
        "dev_only_model_sha256":seal,
        "conditional_predicted_minutes":predicted,
        "preissue_predicted_minutes_group":group,
        "global_dev_short_given_played_probability":float(
            params["global_dev_played_only_short_baseline_probability"]),
        "group_dev_short_given_played_probability":float(
            dev["dev_only_smoothed_conditional_short_probability"]),
        "global_dev_q90_minutes_band":[round(max(0,predicted-q0),4),
                                       round(predicted+q0,4)],
        "group_dev_q90_minutes_band":[round(max(0,predicted-q),4),
                                      round(predicted+q,4)],
        "short_actual_minutes_threshold":10.0,
        "development_year":"2024/25",
        "new_historical_holdout_unseen":False,
        "game_day_roster_verified":False,
        "outcome_at_first_issue":"UNKNOWN",
        "observed_minutes_used_as_feature":False,
        "model_training_negative":False,
        "p_play_probability_multiplied":False,
        "research_only":True,
        "adopt_on_site":False,
    }


def build(minute_source, shadow, role, now, previous=None):
    if now.utcoffset() is None:
        raise ValueError("Naive research issue clock")
    now=now.astimezone(timezone.utc)
    if (minute_source.get("schema_version") != 1
            or minute_source.get("status") != STATUS
            or minute_source.get("adopt_on_site") is not False
            or minute_source.get("unconditional_FP_enabled") is not False
            or minute_source.get("p_play_assumed_calibrated") is not False
            or shadow.get("schema_version") != 1
            or shadow.get("status") != STATUS
            or shadow.get("adopt_on_site") is not False
            or shadow.get("population_brier_enabled") is not False):
        raise ValueError("Unsafe original research input")
    params,seal=validate_role(role, minute_source)
    if instant(role["updated_at_utc"]) > now:
        raise ValueError("Fitted role report not available at proposed issue time")
    minute_issues={}
    shadow_issues={}
    for p in shadow.get("issued",[]):
        key=p["game_id"],p["player_id"]
        if key in shadow_issues:
            raise ValueError("Duplicate first-issued p_play identity")
        shadow_issues[key]=p
    for m in minute_source.get("issued",[]):
        key=m["game_id"],m["player_id"]
        if key in minute_issues:
            raise ValueError("Duplicate original minutes issue")
        validate_minute_first_issue(m,shadow_issues.get(key),minute_source,now)
        minute_issues[key]=m
    if not minute_issues or len(minute_issues) != minute_source.get("issued_total"):
        raise ValueError("Frozen minutes source count drift")
    previous=previous or {}
    if previous and (previous.get("schema_version") != 1
                     or previous.get("status") != STATUS
                     or previous.get("adopt_on_site") is not False
                     or previous.get("dev_only_model_sha256") != seal
                     or previous.get("minutes_model_sha256") != minute_source["frozen_rule_hash"]
                     or previous.get("historical_source_index_version") != minute_source[
                        "historical_source_index_version"]):
        raise ValueError("Prior risk research parameters changed")
    old=list(previous.get("issued",[]))
    already={}
    for row in old:
        key=row["game_id"],row["player_id"]
        original=minute_issues.get(key)
        if original is None or key in already:
            raise ValueError("Prior immutable risk issue missing or duplicate")
        when=instant(row["risk_first_issued_at_utc"])
        minute_first=instant(original["issued_at_utc"])
        lock=instant(original["individual_lock_utc"])
        if (not minute_first <= when < lock or when > now or
                when < instant(role["updated_at_utc"])):
            raise ValueError("Earlier risk issue not genuinely issued prelock")
        expected=make_frozen_row(original,params,seal,when)
        if row != expected:
            raise ValueError("Already-issued risk forecast retrospectively modified")
        already[key]=row
    added=[]
    skipped=Counter()
    for key,m in sorted(minute_issues.items()):
        if key in already:
            skipped["already_issued"]+=1
            continue
        if now >= instant(m["individual_lock_utc"]):
            skipped["locked_cannot_backfill"]+=1
            continue
        row=make_frozen_row(m,params,seal,now)
        added.append(row)
        if len(added)+len(old)>MAX_ISSUES:
            raise ValueError("Unbounded prospective risk issuance")
    all_issued=old+added
    if (len(all_issued)+skipped["locked_cannot_backfill"] !=
            len(minute_issues)):
        raise ValueError("Prospective risk denominator lost")
    return {
        "schema_version":1,"status":STATUS,"model_status":STATUS,
        "adopt_on_site":False, "updated_at_utc":stamp(now),
        "target":"P(actual_minutes_below_10_given_verified_positive_minutes)",
        "population":"first_issued_frozen_minutes_same_team_p_play_proxy_only",
        "training_year":"2024/25",
        "already_inspected_2025_26_holdout_is_not_new_validation":True,
        "development_role_parameters_first_observed_at_utc":role["updated_at_utc"],
        "dev_only_model_sha256":seal,
        "minutes_model_sha256":minute_source["frozen_rule_hash"],
        "historical_source_index_version":minute_source["historical_source_index_version"],
        "issued":all_issued,
        "issued_total":len(all_issued),
        "issue_QA":{**dict(skipped),"new_genuine_prelock_issues":len(added),
                    "minutes_source_total":len(minute_issues)},
        "quality_gate":{
            "all_new_issued_before_individual_lock":True,
            "old_issues_unchanged":True,
            "missing_player_is_DNP":False,
            "p_play_population_calibrated":False,
            "new_individual_minutes_intervals_calibrated":False,
            "not_fresh_independent_2025_26_model_selection_holdout":True,
            "unconditional_FP_allowed":False,
            "adopt_on_site":False,
        },
        "limitations":[
            "No risk backfill after lock; new issues have real wall-clock commit/run timestamps.",
            "Risk conditional on playing with positive minutes; DNP handled separately and not imputed.",
            "2024/25-only dev parameters frozen in prior PR #66. No new 2025/26 holdout claims.",
            "Future evaluation must read only issued rows; it may not reconstruct unissued predictions.",
            "Same-team 2025/26 minutes prior is held frozen before 2026/27; unknown transfers abstain.",
            "No deploy, pricing, user roster/Firestore, Sports.ru credit or automatic transfers.",
        ],
    }


def run():
    read=lambda name:json.loads((DATA/name).read_text(encoding="utf8"))
    now=datetime.now(timezone.utc)
    output=DATA/"short_minutes_prospective_research.json"
    old=read(output.name) if output.exists() else {}
    result=build(read("conditional_minutes_fp_research.json"),
                 read("p_play_shadow_research.json"),
                 read("short_minutes_role_bands_research.json"),now,old)
    if not old or {
        k:v for k,v in result.items() if k!="updated_at_utc"
    } != {
        k:v for k,v in old.items() if k!="updated_at_utc"
    }:
        tmp=output.with_suffix(".tmp")
        tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
        tmp.replace(output)
    return {"issued_total":result["issued_total"],
            "issued_QA":result["issue_QA"],
            "adopt_on_site":False}


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
