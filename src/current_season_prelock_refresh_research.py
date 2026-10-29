"""Research-only prospective near-lock REFRESH, never a retroactively issued challenger.

The existing strict original-issue-coincident minutes/FP challenger stays unchanged.
This SEPARATE experiment issues a NEW forecast at the actual current GitHub run
time, within 12h before individual T-30. The original 2025/26 frozen forecast
remains an immutable, earlier-timed control. Current-season positive-minute
rows are first observed <= THIS refresh (not falsely as of original issue).

It measures *value of refreshing later* versus the previously frozen forecast,
not a same-time information-set contest. Outcome must be independently
postgame verified, and missing/DNP must never become conditional FP=0.
No Sports.ru roster, personal prices, Firestore, or model deployment.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from math import isfinite, sqrt
from pathlib import Path
import json

from src.sync import DATA
from src.rolling_decision_research import canonical_hash, instant, stamp
from src.current_season_minutes_shadow_research import (
    source_rows, unique, STATUS,
)

LOCK = timedelta(minutes=30)
NEAR_LOCK = timedelta(hours=12)
MAX_ISSUES = 10000
MODEL = {
    "name": "new_issued_nearlock_minutes_rate_refresh_v1",
    "issue_window_before_individual_Tminus30_hours": 12,
    "min_verified_current_same_club_played": 3,
    "max_verified_current_same_club_played": 5,
    "frozen_previous_season_minutes_prior_strength_games": 5,
    "frozen_previous_season_rate_prior_strength_games": 10,
    "model_chosen_after_2026_27_season_started": True,
    "baseline_and_refresh_info_times_differ": True,
    "no_backdated_refresh_issuance": True,
    "unknown_is_not_DNP_or_FP_zero": True,
    "adopt_on_site": False,
}
MODEL_HASH = canonical_hash(MODEL)
FIELDS = (
    "original_2025_26_frozen_conditional_FP",
    "refresh_minutes_times_old_FP_rate",
    "refresh_minutes_times_shrunk_recent_FP_rate",
)
OLD = FIELDS[0]


def number(value, *, min_val=-150, max_val=250):
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError("Nonfinite public FP/minutes")
    value = float(value)
    if not min_val <= value <= max_val:
        raise ValueError("Out-of-range public FP/minutes")
    return value


def verified_form(base, by_player, live, rolling, now):
    """Verify clock, club, final fixture and currently observed FP row hash."""
    pid, club = base["player_id"], base["team"]
    all_rows = [
        x for (player, _), rows in by_player.items()
        if player == pid for x in rows
        if instant(x["first_seen_at_utc"]) <= now
    ]
    all_rows.sort(key=lambda x: (x["game_utc"], x["game_id"]))
    if not all_rows or all_rows[-1]["game_id"] is None:
        return [], "no_current_season_played_rows_observed"
    by_club = [x for x in all_rows if x in by_player.get((pid, club), [])]
    if not by_club:
        return [], "no_current_season_played_rows_in_frozen_club"
    latest = all_rows[-1]
    if latest not in by_club:
        return [], "latest_observed_club_differs_from_original_prior"
    # A change-of-club and return may require a new historical prior;
    # take only the contiguous current-club tail, not an earlier tenure.
    index = len(all_rows)
    while index and all_rows[index-1] in by_club:
        index -= 1
    tenure = all_rows[index:]
    sample = tenure[-MODEL["max_verified_current_same_club_played"]:]
    if len(sample) < MODEL["min_verified_current_same_club_played"]:
        return [], "insufficient_verified_same_club_prelock_form"
    live_rows = {}
    for row in live.get("rows", []):
        key = (row.get("game_id"), row.get("id"))
        if key[1] != pid:
            continue
        if key in live_rows:
            raise ValueError("Duplicated live FP game for selected player")
        live_rows[key] = row
    hashes = rolling.get("row_hashes")
    first = rolling.get("row_first_seen_at_utc")
    if not isinstance(hashes, dict) or not isinstance(first, dict):
        raise ValueError("Missing rolling first seen and source hashes")
    verified=[]
    for sampled in sample:
        gid = sampled["game_id"]
        observed = live_rows.get((gid, pid))
        if observed is None:
            raise ValueError("Prior played minutes missing corresponding FP")
        seen = instant(sampled["first_seen_at_utc"])
        when = instant(sampled["game_utc"])
        if (not when < now or not when <= seen <= now
                or first.get(f"{gid}|{pid}") != stamp(seen)
                or observed.get("played") is not True
                or observed.get("team") != club
                or stamp(instant(observed["utc"])) != stamp(when)):
            raise ValueError("Prior played source fails actual capture clock/identity")
        mins = number(observed.get("minutes"), min_val=0.00001, max_val=70)
        if mins != number(sampled["minutes"], min_val=0.00001, max_val=70):
            raise ValueError("Prior played FP/minutes do not match")
        fp = number(observed.get("fp"))
        raw = {
            "game_id": gid, "player_id": pid, "team": club,
            "fp": observed["fp"], "minutes": observed["minutes"], "utc": stamp(when),
        }
        key = f"{gid}|{pid}"
        if hashes.get(key) != canonical_hash(raw):
            raise ValueError("Prior played FP source differs from rolling hash")
        verified.append({
            "game_id":gid,"team":club,"game_utc":stamp(when),
            "row_first_seen_at_utc":stamp(seen),
            "minutes":mins,"fp_reconstructed":fp,
            "rolling_row_sha256":hashes[key],
        })
    return verified, None


def make_issue(base, sample, now):
    """Only genuinely NEW issue at now; original prediction unchanged."""
    tip, lock, old_at = [instant(base[k]) for k in
                          ("game_utc", "individual_lock_utc", "issued_at_utc")]
    if (tip-lock != LOCK or not old_at <= now < lock
            or not timedelta(0) < lock-now <= NEAR_LOCK):
        raise ValueError("New refresh may only issue in real near-lock window")
    n = len(sample)
    if not MODEL["min_verified_current_same_club_played"] <= n <= MODEL["max_verified_current_same_club_played"]:
        raise ValueError("No sufficient preissue played form")
    prior_minutes = number(base["min_if_play"], min_val=0, max_val=70)
    old_rate = number(base["fp_per_minute_if_play"], min_val=-100, max_val=100)
    prior_fp = number(base["decomposed_fp_if_play"])
    if abs(prior_minutes*old_rate-prior_fp) > .0001:
        raise ValueError("Frozen baseline FP and rate disagree")
    current_mins = sum(x["minutes"] for x in sample)/n
    minutes = ((MODEL["frozen_previous_season_minutes_prior_strength_games"]*prior_minutes)
               + n*current_mins)/(MODEL["frozen_previous_season_minutes_prior_strength_games"]+n)
    old_r = MODEL["frozen_previous_season_rate_prior_strength_games"]
    current_rate = sum(x["fp_reconstructed"] for x in sample)/sum(x["minutes"] for x in sample)
    blended_rate = (old_r*old_rate+n*current_rate)/(old_r+n)
    variants = {
        FIELDS[0]:prior_fp,
        FIELDS[1]:round(minutes*old_rate,5),
        FIELDS[2]:round(minutes*blended_rate,5),
    }
    for value in variants.values():
        number(value, min_val=-500, max_val=500)
    return {
        "game_id":base["game_id"],"player_id":base["player_id"],
        "team":base["team"],"game_utc":base["game_utc"],
        "individual_lock_utc":base["individual_lock_utc"],
        "original_frozen_issued_at_utc":base["issued_at_utc"],
        "refresh_issued_at_utc":stamp(now),
        "hours_from_refresh_to_lock":round((lock-now).total_seconds()/3600,3),
        "original_frozen_issue_sha256":canonical_hash(base),
        "model_sha256":MODEL_HASH,
        "source_current_played_rows_first_seen_before_refresh":sample,
        "source_current_played_rows_sha256":canonical_hash(sample),
        "current_form_first_seen_after_original_count":sum(
            instant(x["row_first_seen_at_utc"]) > old_at for x in sample),
        "source_current_played_n":n,
        "historical_prior_minutes":prior_minutes,
        "historical_prior_fp_per_minute":old_rate,
        "current_observed_minutes_mean":round(current_mins,5),
        "current_observed_fp_per_minute":round(current_rate,6),
        "minutes_refresh_predicted":round(minutes,5),
        "FP_variants_frozen":variants,
        "comparison_type":"later_real_prelock_refresh_vs_unchanged_earlier_original",
        "outcome_at_issue":"UNKNOWN",
        "adopt_on_site":False,
    }


def metrics(rows):
    if not rows:
        return {"scored_positive_played":0}
    n=len(rows)
    actual=[number(x["actual_fp_reconstructed"]) for x in rows]
    baseline=[abs(x["FP_variants_frozen"][OLD]-act) for x,act in zip(rows,actual)]
    out={"scored_positive_played":n}
    for variant in FIELDS:
        errors=[number(x["FP_variants_frozen"][variant],min_val=-500,max_val=500)-act
                for x,act in zip(rows,actual)]
        out[variant] = {
            "MAE":round(sum(abs(e) for e in errors)/n,4),
            "RMSE":round(sqrt(sum(e*e for e in errors)/n),4),
            "predicted_minus_actual_bias":round(sum(errors)/n,4),
            "paired_MAE_gain_vs_original_frozen":round(
                sum(b-abs(e) for b,e in zip(baseline,errors))/n,4),
        }
    mbase=[abs(x["original_predicted_minutes"]-x["actual_minutes"]) for x in rows]
    mnew=[abs(x["refreshed_predicted_minutes"]-x["actual_minutes"]) for x in rows]
    out["minutes_MAE"]={
        "original":round(sum(mbase)/n,4),"refreshed":round(sum(mnew)/n,4),
        "paired_gain":round(sum(a-b for a,b in zip(mbase,mnew))/n,4),
    }
    return out


def build(previous, frozen, evaluation, rolling, live, now):
    if now.utcoffset() is None:
        raise ValueError("Aware UTC live capture time required")
    now=now.astimezone(timezone.utc)
    if (frozen.get("schema_version") != 1
            or frozen.get("status") != STATUS
            or frozen.get("adopt_on_site") is not False
            or frozen.get("unconditional_FP_enabled") is not False
            or evaluation.get("status") != STATUS
            or evaluation.get("adopt_on_site") is not False
            or evaluation.get("quality_gate",{}).get("adopt_on_site") is not False
            or live.get("schema_version") != 4
            or rolling.get("schema_version") != 1
            or rolling.get("adopt_on_site") is not False):
        raise ValueError("Untrusted public research source")
    original = unique(frozen.get("issued"),"original prelock frozen issues")
    if (evaluation.get("frozen_minutes_issue_sha256") != canonical_hash(frozen["issued"])
            or len(evaluation.get("scored_played",[])) != evaluation.get("summary",{}).get("played")):
        raise ValueError("Incoherent frozen original and independent played evaluation")
    scored=unique(evaluation["scored_played"],"independently verified played results")
    dnp=unique(evaluation.get("explicit_DNP_not_in_conditional_metrics",[]),"literal DNP")
    unknown=unique(evaluation.get("UNKNOWN_unscored",[]),"UNKNOWN")
    if set(scored)&set(dnp) or set(scored)&set(unknown) or set(dnp)&set(unknown):
        raise ValueError("Overlapping played/DNP/UNKNOWN label")
    if previous and (previous.get("schema_version") != 1
                     or previous.get("status") != STATUS
                     or previous.get("adopt_on_site") is not False
                     or previous.get("model_sha256") != MODEL_HASH):
        raise ValueError("Previous refresh archive schema/model changed")
    old_issues=unique((previous or {}).get("issued",[]),"previous immutable refresh issues")
    old_observed=unique((previous or {}).get("observed",[]),"previous refresh outcomes")
    if not set(old_observed).issubset(old_issues):
        raise ValueError("Orphan historical refresh outcome")
    for key,item in old_issues.items():
        base=original.get(key)
        if (base is None or item.get("original_frozen_issue_sha256") != canonical_hash(base)
                or item.get("model_sha256") != MODEL_HASH
                or item.get("adopt_on_site") is not False
                or item.get("source_current_played_rows_sha256") != canonical_hash(
                    item.get("source_current_played_rows_first_seen_before_refresh"))):
            raise ValueError("Previously issued refresh data were modified")
        issue, original_at, lock=[instant(item[k]) for k in
                                 ("refresh_issued_at_utc","original_frozen_issued_at_utc",
                                  "individual_lock_utc")]
        if (original_at != instant(base["issued_at_utc"])
                or not original_at <= issue < lock
                or not timedelta(0) < lock-issue <= NEAR_LOCK):
            raise ValueError("Archived refresh after individual lock/backdated")
    byplayer=source_rows(live,rolling,now)
    qa=Counter()
    for key,base in sorted(original.items()):
        if key in old_issues:
            qa["already_immutable"]+=1
            continue
        tip,lock,original_at=[instant(base[k]) for k in
                              ("game_utc","individual_lock_utc","issued_at_utc")]
        if tip-lock != LOCK or original_at >= lock:
            raise ValueError("Frozen original has invalid player lock")
        if now>=lock:
            qa["original_opportunity_already_locked_no_backfill"]+=1
            continue
        if lock-now>NEAR_LOCK:
            qa["await_near_lock_window"]+=1
            continue
        if original_at>now:
            qa["original_issued_in_future"]+=1
            continue
        # Always use current information first-observed <= NOW, never pretend
        # the refreshed sources were known at original baseline issuance.
        sample,reason=verified_form(base,byplayer,live,rolling,now)
        if reason:
            qa[reason]+=1
            continue
        item=make_issue(base,sample,now)
        old_issues[key]=item
        qa["new_true_asof_nearlock_refreshes"]+=1
        if len(old_issues)>MAX_ISSUES:
            raise ValueError("Research archive exceeds limit")
    for key,proof in scored.items():
        item=old_issues.get(key)
        if item is None:
            continue
        seen=instant(proof["postgame_first_seen_at_utc"])
        tip=instant(item["game_utc"])
        issue=instant(item["refresh_issued_at_utc"])
        if (seen < tip or seen > now or seen < issue
                or proof.get("team") != item["team"]
                or proof.get("game_utc") != item["game_utc"]
                or number(proof["actual_minutes"],min_val=0.00001,max_val=70)<=0):
            raise ValueError("Postgame positive played result fails clock/identity")
        outcome={
            "game_id":key[0],"player_id":key[1],
            "et_date":proof["et_date"],
            "team":item["team"],"position":proof["position"],
            "postgame_first_seen_at_utc":stamp(seen),
            "actual_minutes":number(proof["actual_minutes"],min_val=0.00001,max_val=70),
            "actual_fp_reconstructed":number(proof["actual_fp_reconstructed"]),
            "original_predicted_minutes":item["historical_prior_minutes"],
            "refreshed_predicted_minutes":item["minutes_refresh_predicted"],
            "FP_variants_frozen":item["FP_variants_frozen"],
            "source_original_issue_sha256":item["original_frozen_issue_sha256"],
        }
        if key in old_observed and old_observed[key]!=outcome:
            raise ValueError("Previously paired refresh result changed")
        old_observed[key]=outcome
    if not set(old_observed).issubset(scored):
        raise ValueError("Previously verified refresh result disappeared from source")
    keys=set(old_issues)
    played=len(old_observed)
    verified_dnp=len(keys & set(dnp))
    genuinely_unknown=len(keys & set(unknown))
    remaining=len(keys)-played-verified_dnp-genuinely_unknown
    if remaining<0:
        raise ValueError("Refresh cohort denominator drift")
    issues=sorted(old_issues.values(),key=lambda q:(q["game_utc"],q["game_id"],q["player_id"]))
    results=sorted(old_observed.values(),key=lambda q:(q["et_date"],q["game_id"],q["player_id"]))
    by_date=defaultdict(list)
    for record in results:by_date[record["et_date"]].append(record)
    return {
        "schema_version":1,"status":STATUS,"model_status":STATUS,
        "adopt_on_site":False,"model_sha256":MODEL_HASH,
        "frozen_design":MODEL,"updated_at_utc":stamp(now),
        "issued":issues,"observed":results,
        "summary":{
            "issued_total":len(issues),
            "new_issued_this_run":qa["new_true_asof_nearlock_refreshes"],
            "played_verified":played,
            "explicit_DNP_excluded":verified_dnp,
            "UNKNOWN_not_imputed":genuinely_unknown,
            "awaiting_or_unchecked":remaining,
            "distinct_ET_dates_with_scored":len(by_date),
            "distinct_games_scored":len({r["game_id"] for r in results}),
            "issued_with_additional_source_after_original":sum(
                i["current_form_first_seen_after_original_count"]>0 for i in issues),
        },
        "issuance_QA":dict(qa),
        "played_only_paired_metrics":metrics(results),
        "by_ET_date":{day:metrics(group) for day,group in sorted(by_date.items())},
        "quality_gate":{
            "true_new_refresh_first_issued_prelock":True,
            "original_issue_not_rewritten":True,
            "different_info_clock_original_vs_refresh_not_same_asof_AB_test":True,
            "at_least_8_independent_ET_dates":len(by_date)>=8,
            "at_least_24_NBA_games":len({r["game_id"] for r in results})>=24,
            "at_least_100_played_pairs":played>=100,
            "not_full_fantasy_roster_or_calibrated_P_play":True,
            "no_unconditional_expected_FP":True,
            "model_selected_after_original_2026_27_outcomes":True,
            "adopt_on_site":False,
        },
        "limitations":[
            "This is an actual fresh prediction at its own UTC timestamp, not a backdated replay.",
            "The frozen original control may have less recent information than the refreshed candidate.",
            "Therefore benefits measure the value of updating later, not a same-time fair algorithm comparison.",
            "ESPN and Sports.ru public club proxies do not establish game-day player eligibility.",
            "Only independently verified positive-minute boxscores can be scored for conditional FP.",
            "Official DNP and unknown are counted separately; neither is scored with FP=0.",
            "First-seen current source timestamps are conservative observations, not guaranteed original provider publication.",
            "Multiple player-games share dates and correlated match shocks.",
            "Model settings chosen after the early 2026/27 season are exploratory; no site adoption.",
            "No Firebase, Hosting, Sports.ru personal data, prices or transfers modified.",
        ],
    }


def run():
    def read(name):
        return json.loads((DATA/name).read_text(encoding="utf8"))
    target=DATA/"current_season_prelock_refresh_research.json"
    prior=read(target.name) if target.exists() else {}
    obj=build(prior,read("conditional_minutes_fp_research.json"),
              read("conditional_minutes_fp_evaluation_research.json"),
              read("rolling_decision_research.json"),read("live.json"),
              datetime.now(timezone.utc))
    if (not prior or {k:v for k,v in obj.items() if k!="updated_at_utc"} !=
            {k:v for k,v in prior.items() if k!="updated_at_utc"}):
        tmp=target.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
        tmp.replace(target)
    return {"summary":obj["summary"],"issuance_QA":obj["issuance_QA"],
            "research_only":True,"adopt_on_site":False}


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
