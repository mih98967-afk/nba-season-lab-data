"""Sports.ru NBA weekly decision cutoff research (NOT a trade recommendation engine).

Tests estimates made on Monday 15:00 Europe/Moscow for games remaining in the
same calendar week, not the earlier Monday 00:00 week model. Includes a
deterministic 10-slot/3-move abstract decision proxy with <=2/team and identical
candidate pools for competing estimators.

IMPORTANT: No historical Sports.ru acquisition/sale prices or reliably
historical position eligibility is available. Therefore plans ARE NOT legal
replays of Sports.ru transfers and cannot be adopted as production advice.
All sources public; no Firebase access, no user data or paid APIs.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, date, time, timedelta, timezone
from statistics import fmean, stdev
from zoneinfo import ZoneInfo
import hashlib, json, math, pathlib, random

from src.history import get_csv, SCHEDULES
from src.sync import DATA
from src.weekly_model_validation import (
    SEASONS, schedule, joined, forecast, scores, quantile
)

MSK = ZoneInfo("Europe/Moscow")
UTC = timezone.utc
BASELINE = (10, 0.0, False)
HURDLES = (0, 5, 10)
MAX_MOVES = 3
MIN_HISTORY = 14
SCENARIOS_PER_WEEK = 32

def boundaries(week):
    """A fantasy calendar week begins Mon 00 MSK; decision is Mon 15 MSK.
    An unverified transfer-quota reset is NOT assumed by this function.
    """
    monday = date.fromisoformat(str(week))
    if monday.weekday() != 0:
        raise ValueError("Calendar week not Monday: " + str(week))
    decision = datetime.combine(monday, time(15), MSK).astimezone(UTC)
    end = datetime.combine(monday + timedelta(days=7), time(0), MSK).astimezone(UTC)
    return decision, end

def decision_cohort(fixtures, history, season):
    """Use only past observed player performances at decision time.

    Exclude players without sufficient prior activity (label selection risk).
    An individual player owned throughout the remaining week scores all his
    real games even if his real-world team changes inside that week.
    """
    by_id = {g["id"]: g for g in fixtures}
    if any(g["utc"] is None or g["utc"].utcoffset() is None for g in fixtures):
        raise ValueError("Every historical tipoff must be timestamped")
    player,team_games,rejected = joined(history,fixtures,season)
    for games in team_games.values():
        games.sort(key=lambda g:(g["utc"],g["id"]))
    for logs in player.values():
        logs.sort(key=lambda r:(by_id[r["id"]]["utc"],r["id"]))
    weeks = sorted({g["week"] for g in fixtures})
    rows,excluded = [],Counter()
    eligible_stamps = set()
    early_game_ids=set()
    for week in weeks[1:-1]:
        decision,stop=boundaries(week)
        if decision >= stop:raise ValueError("Cutoff beyond week")
        for game in fixtures:
            if game["week"]==week and game["utc"]<decision:
                early_game_ids.add(game["id"])
        before_team = {
            team:[g for g in games if g["utc"]<decision]
            for team,games in team_games.items()
        }
        remaining_team = {
            team:[g for g in games if decision<=g["utc"]<stop]
            for team,games in team_games.items()
        }
        for pid,logs in player.items():
            prior = [r for r in logs if by_id[r["id"]]["utc"]<decision]
            if len(prior)<MIN_HISTORY:
                excluded["short_player_history"]+=1
                continue
            last=prior[-1]
            club=last["team"]
            next_games=remaining_team.get(club,[])
            if not next_games:
                excluded["no_remaining_club_games"]+=1
                continue
            last_stamp=by_id[last["id"]]["utc"]
            if decision-last_stamp>timedelta(days=16):
                excluded["no_recent_team_activity"]+=1
                continue
            old_games=before_team.get(club,[])
            if len(old_games)<12:
                excluded["short_team_history"]+=1
                continue
            tenure=[]
            for r in reversed(prior):
                if r["team"] !=club:break
                tenure.append(r)
            tenure.reverse()
            if len(tenure)<8:
                excluded["new_team_tenure"]+=1
                continue
            since=by_id[tenure[0]["id"]]["utc"]
            club_history=[g for g in old_games if g["utc"]>=since]
            if len(club_history)<10:
                excluded["short_team_tenure"]+=1
                continue
            had={r["id"] for r in tenure}
            last20=club_history[-20:]
            last5=club_history[-5:]
            mu10=fmean(r["fp"] for r in prior[-10:])
            mu25=fmean(r["fp"] for r in prior[-25:]) if len(prior)>=25 else mu10
            mu_min=fmean(r["min"] for r in prior[-10:])
            min_diff=fmean(r["min"] for r in prior[-5:])-mu_min
            permin=sum(r["fp"] for r in prior[-10:])/max(75.,sum(r["min"] for r in prior[-10:]))
            sigma=stdev(r["fp"] for r in prior[-25:]) if len(prior)>=2 else 9.
            actual=sum(
                r["fp"] for r in logs
                if decision <= by_id[r["id"]]["utc"] < stop
            )
            played=sum(
                1 for r in logs
                if decision <= by_id[r["id"]]["utc"] < stop
            )
            row={
                "pid":pid,"team":club,"week":str(week),
                "games":len(next_games),"actual":round(actual,4),"played":played,
                "mu10":mu10,"mu25":mu25,"min_diff":min_diff,
                "per_min":permin,"sigma":max(3.,sigma),
                "played20":sum(g["id"] in had for g in last20),
                "team20":len(last20),
                "played5":sum(g["id"] in had for g in last5),
                "team5":len(last5),
            }
            rows.append(row)
            eligible_stamps.add((str(week),pid))
    rows.sort(key=lambda r:(r["week"],r["pid"]))
    if len(rows)<1000:raise ValueError("Too few at-deadline player weeks")
    return rows,{
        "sample_size":len(rows),
        "weeks":len({r["week"] for r in rows}),
        "players":len({r["pid"] for r in rows}),
        "early_week_matches_excluded":len(early_game_ids),
        "total_remaining_player_games":sum(r["games"] for r in rows),
        "zero_game_appearances_pct":round(
            sum(r["played"]==0 for r in rows)*100/len(rows),2),
        "excluded_as_of":dict(excluded),
        "rejected_game_logs":dict(rejected),
    }

def sample_scenarios(rows, seed_tag, count=SCENARIOS_PER_WEEK):
    """No outcome is used for eligibility or sampling."""
    rng = random.Random(
        int.from_bytes(hashlib.sha256(seed_tag.encode()).digest()[:8],"big")
    )
    if len(rows)<28:return []
    pairs=[]
    for _ in range(count):
        shuffled=rng.sample(rows,len(rows))
        owners=[];club_counts=Counter()
        for row in shuffled:
            if club_counts[row["team"]]>=2:continue
            owners.append(row)
            club_counts[row["team"]]+=1
            if len(owners)==10:break
        if len(owners)<10:continue
        owner_ids={r["pid"] for r in owners}
        alternatives=[r for r in shuffled if r["pid"] not in owner_ids][:10]
        if len(alternatives)<10:continue
        pairs.append(list(zip(owners,alternatives)))
    return pairs

def pick_moves(pairs, parameters, hurdle=0, max_moves=3):
    """Stage one move per abstract slot; budget and positions NOT checked."""
    offers=[]
    club_counts=Counter(a["team"] for a,b in pairs)
    for index,(a,b) in enumerate(pairs):
        gain=forecast(b,parameters)[0]-forecast(a,parameters)[0]
        if gain>hurdle:
            offers.append((gain,index,a,b))
    offers.sort(key=lambda t:(-t[0],t[1]))
    picked=[]
    for predicted,index,a,b in offers:
        if len(picked)>=max_moves:break
        if club_counts[b["team"]]+(b["team"]!=a["team"])>2:continue
        club_counts[a["team"]]-=1
        club_counts[b["team"]]+=1
        picked.append((index,predicted,b["actual"]-a["actual"]))
    return picked

def simulate(rows,baseline,candidate,hurdles=HURDLES,per_week=SCENARIOS_PER_WEEK):
    weekly=defaultdict(list)
    for r in rows:weekly[r["week"]].append(r)
    table={}
    for hurdle in hurdles:
        cases=[];perweek=defaultdict(list)
        for week,records in sorted(weekly.items()):
            scenarios=sample_scenarios(records,week+"|stable-pair-v2",per_week)
            for idx,pairs in enumerate(scenarios):
                origin=sum(a["actual"] for a,b in pairs)
                pbase=pick_moves(pairs,baseline,hurdle)
                pcand=pick_moves(pairs,candidate,hurdle)
                gainbase=sum(item[2] for item in pbase)
                gaincand=sum(item[2] for item in pcand)
                case={
                    "week":week,"case":idx,
                    "held_fp":origin,
                    "baseline_gain_fp":gainbase,
                    "candidate_gain_fp":gaincand,
                    "candidate_minus_baseline_fp":gaincand-gainbase,
                    "baseline_moves":len(pbase),"candidate_moves":len(pcand),
                    "different_decision":{x[0] for x in pbase}!={x[0] for x in pcand},
                }
                cases.append(case)
                perweek[week].append(case)
        if not cases:raise ValueError("No abstract transfer scenarios")
        rng=random.Random(88142+int(hurdle))
        weeks=sorted(perweek)
        bootstrap=[]
        for _ in range(400):
            sampled=[weeks[rng.randrange(len(weeks))] for _ in weeks]
            values=[v["candidate_minus_baseline_fp"] for w in sampled for v in perweek[w]]
            bootstrap.append(fmean(values))
        bootstrap.sort()
        diffs=[z["candidate_minus_baseline_fp"] for z in cases]
        table[str(hurdle)]={
            "decision_margin_required_fp":hurdle,
            "simulations":len(cases),"distinct_weeks":len(weeks),
            "avg_held_fp":round(fmean(z["held_fp"] for z in cases),2),
            "baseline_avg_actual_gain_fp":round(fmean(z["baseline_gain_fp"] for z in cases),3),
            "candidate_avg_actual_gain_fp":round(fmean(z["candidate_gain_fp"] for z in cases),3),
            "candidate_minus_baseline_avg_fp":round(fmean(diffs),3),
            "candidate_better_than_baseline_case_pct":round(
                100*sum(x>0 for x in diffs)/len(diffs),2),
            "different_decision_pct":round(100*fmean(z["different_decision"] for z in cases),2),
            "average_baseline_moves":round(fmean(z["baseline_moves"] for z in cases),3),
            "average_candidate_moves":round(fmean(z["candidate_moves"] for z in cases),3),
            "candidate_delta_week_bootstrap_95pct":[
                round(quantile(bootstrap,.025),3),
                round(quantile(bootstrap,.975),3)]
        }
    return table

def run():
    history=json.loads((DATA/"nba_history.json").read_text(encoding="utf-8"))
    historical=json.loads((DATA/"historical_tipoffs.json").read_text(encoding="utf-8"))
    if history.get("status")!="complete" or len(history.get("players",{}))<200:
        raise ValueError("Audited complete NBA history required")
    if historical.get("calendar_status")!="fully_matched_historical_tipoffs":
        raise ValueError("Exact historical UTC schedule required")
    all_rows,checks={},{}
    for season,year in SEASONS.items():
        fixtures,precision=schedule(
            get_csv(SCHEDULES.format(year)),season,
            (historical["seasons"] or {}).get(season))
        if precision["week_semantics"]!="moscow_start" or precision["missing_utc_tipoffs"]:
            raise ValueError("No approximate USA calendar allowed")
        rows,qc=decision_cohort(fixtures,history["players"],season)
        all_rows[season]=rows
        checks[season]={**precision,**qc}
    dev=all_rows["2024/25"]
    holdout=all_rows["2025/26"]
    options=[(k,w,m) for k in (0,5,10,20) for w in (0,.25,.5) for m in (False,True)]
    selected=min(options,key=lambda pars:(scores(dev,pars)["mae"],pars))
    base=scores(holdout,BASELINE)
    model=scores(holdout,selected)
    decisions=simulate(holdout,BASELINE,selected)
    improvement=100*(base["mae"]-model["mae"])/max(1e-6,base["mae"])
    result={
        "schema_version":1,
        "status":"research_only_not_deployed",
        "adopt_on_site":False,
        "updated_at_utc":datetime.now(UTC).isoformat(),
        "decision_time":"Monday 15:00 Europe/Moscow",
        "calendar_end":"Next Monday 00:00 Europe/Moscow",
        "weekly_transfer_quota_reset":"UNVERIFIED: do not infer from deadline",
        "development":"2024/25",
        "holdout":"2025/26 (reused after prior research; exploratory decision metric)",
        "baseline_params":BASELINE,
        "selected_params_on_development":selected,
        "qa":checks,
        "accuracy":{
            "baseline":base,
            "selected":model,
            "relative_mae_improvement_pct":round(improvement,2)},
        "abstract_transfer_comparison":decisions,
        "limitations":[
            "NOT a Sports.ru legal transfer simulation: historical prices and position eligibility unavailable.",
            "Current Sports.ru roster and user Firestore are NOT accessed or changed.",
            "Thirty-two synthetic ten-slot opportunities per week; incumbents randomly selected among eligible players.",
            "Team cap <=2 and three abstract moves are enforced, but positions and budget are not.",
            "No intraweek chains; decision is fixed Monday 15:00 MSK and owns full remaining calendar week.",
            "Both candidates have sufficient recent played games; long-term injured are systematically undercovered.",
            "Team tenure inferred from past appearances; transaction and injury membership not independently known.",
            "Calendar is the final historical schedule, not contemporaneously snapshotted future fixtures.",
            "Holdout 2025/26 has already informed earlier research; metrics exploratory, not final independent validation.",
            "No Telegram or pregame 1PM ET reports can leak into Monday 15:00 MSK decisions.",
            "Shadow margins 0/5/10 FP are decision thresholds, NOT transfer cost or Sports.ru price.",
        ]
    }
    path=DATA/"decision_deadline_research.json"
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(path)
    return result

if __name__=="__main__":
    x=run()
    print(json.dumps({
        "status":x["status"],"decision_time":x["decision_time"],
        "qa":x["qa"],"selected_params":x["selected_params_on_development"],
        "accuracy":x["accuracy"],
        "transfers":x["abstract_transfer_comparison"],
        "adopt_on_site":x["adopt_on_site"]},
        ensure_ascii=False,indent=2))
