"""Historical NBA player-appearance frequency: audited RESEARCH PROXY, not DNP.

Data from three-season positive-minute NBA logs and independently matched
2024/25, 2025/26 ESPN tipoffs. Missing positive-minute entry in a fixture is
NOT a verified DNP, active-roster status, injury, or roster membership.
We call it "no logged appearance in last-observed club's fixture" and use
only an established, recently active, same-team tenure selected cohort.

Retrospective as-of statistical construction: never use a later GAME outcome
in features. The final schedule is retrospective and NOT evidence that all
fixtures or team memberships were published before historical decisions.
2024/25 development, 2025/26 untouched holdout. No Sports.ru account, price,
transfers, p_play calibration, or production deployment.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from random import Random
from statistics import fmean
from zoneinfo import ZoneInfo
import bisect
import json
import math
import sys

from src.sync import DATA
from src.rolling_decision_research import instant, stamp
from src.live_calendar_fallback import TEAMS

UTC = timezone.utc
ET = ZoneInfo("America/New_York")
STATUS = "research_only_not_deployed"
SEASONS = ("2024/25", "2025/26")
REQUIRED_HISTORY = {"2023/24", *SEASONS}
MIN_TENURE_APPEARANCES = 8
MIN_TENURE_TEAM_GAMES = 10
MAX_DAYS_SINCE_PLAYED = 16
PRIOR_MEAN = 0.85  # fixed, explicitly not selected on holdout
PARAMS = tuple((k, recent) for k in (0, 5, 10, 20)
               for recent in (0.0, 0.25, 0.5, 0.75, 1.0))
BASELINE = (10, 0.0)
BOOTSTRAP = 400


def validated_fixtures(calendar):
    if (calendar.get("schema_version") != 1 or
            calendar.get("calendar_status") != "fully_matched_historical_tipoffs"
            or calendar.get("status") != STATUS):
        raise ValueError("Independent historical calendar not validated")
    by_year = {}
    for year in SEASONS:
        fixtures = (calendar.get("seasons") or {}).get(year)
        qa = (calendar.get("qa") or {}).get(year, {})
        if (not isinstance(fixtures, dict) or len(fixtures) != 1230 or
                qa.get("matched_utc_tipoffs") != 1230 or
                qa.get("missing_utc_tipoffs") != 0 or
                qa.get("precision") != "exact_msk_complete"):
            raise ValueError("No complete independently matched season: "+year)
        games = []
        seen_espn = set()
        for gid, raw in fixtures.items():
            if not gid.startswith("002") or not isinstance(raw, dict):
                raise ValueError("Bad historical regular-season fixture identity")
            at = instant(raw.get("utc"))
            if at.tzinfo is None or at.utcoffset() != timedelta(0):
                raise ValueError("Historical tipoff not UTC aware")
            if (raw.get("et_date") != at.astimezone(ET).date().isoformat()
                    or raw.get("home") not in TEAMS
                    or raw.get("away") not in TEAMS
                    or raw["home"] == raw["away"]):
                raise ValueError("Final historical fixture / NBA date mismatch")
            espn = str(raw.get("espn_id") or "")
            if not espn.isdigit() or espn in seen_espn:
                raise ValueError("Missing / duplicate independently matched ESPN ID")
            seen_espn.add(espn)
            games.append({"id":gid, "utc":at, "home":raw["home"],
                          "away":raw["away"], "et_date":raw["et_date"]})
        by_year[year] = sorted(games, key=lambda g: (g["utc"], g["id"]))
    return by_year


def positive_logs(history, identity, fixtures):
    if (history.get("status") != "complete"
            or set(history.get("seasons") or []) != REQUIRED_HISTORY
            or len(history.get("players") or {}) < 300):
        raise ValueError("Audited three-season played-game archive required")
    identities = (identity or {}).get("players", {})
    by_year = {year: {g["id"]:g for g in fixtures[year]} for year in SEASONS}
    logs = defaultdict(lambda: defaultdict(list))
    qa = Counter()
    for pid, seasons in history["players"].items():
        ident = identities.get(pid)
        if not isinstance(ident, dict) or ident.get("confidence") != "high":
            qa["player_identity_not_high_confidence_excluded"] += 1
            continue
        if not isinstance(seasons, list):
            raise ValueError("Invalid individual history")
        for item in seasons:
            year = item.get("season")
            if year not in SEASONS:
                continue
            raw_logs = item.get("game_log")
            if not isinstance(raw_logs, list):
                raise ValueError("Full historical game log missing")
            seen = set()
            for row in raw_logs:
                if not isinstance(row, dict):
                    raise ValueError("Invalid historical played row")
                gid = row.get("g")
                if gid in seen:
                    raise ValueError("Duplicate historical played appearance")
                seen.add(gid)
                game = by_year[year].get(gid)
                if game is None:
                    qa["historical_positive_without_matched_fixture"] += 1
                    continue
                club = row.get("team")
                if club not in (game["home"], game["away"]):
                    raise ValueError("Historical active player's club mismatches game")
                if row.get("d") != game["et_date"]:
                    raise ValueError("Historical season date conflicts with independent ESPN clock")
                try:
                    played_minutes = float(row["min"])
                    fp = float(row["fp"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("Malformed positive-minute NBA game") from exc
                if not (math.isfinite(played_minutes) and played_minutes > 0 and math.isfinite(fp)):
                    raise ValueError("Incomplete historical played minute / FP")
                logs[year][pid].append({"id":gid,"utc":game["utc"],
                                        "club":club})
                qa["high_identity_verified_positive_rows"] += 1
    for year in SEASONS:
        for pid, rows in logs[year].items():
            rows.sort(key=lambda r: (r["utc"], r["id"]))
            if len({r["id"] for r in rows}) != len(rows):
                raise ValueError("Historical player-game joined twice")
    return logs, dict(qa)


def player_samples(fixtures, positive, pid, year):
    """Only past played outcomes and past club fixtures enter candidate features.

    y=0 means *no positive-minute game log for this specific game*, not DNP.
    Selection requires 8 prior same-club appearances, >=10 past club games,
    and positive-minute appearance within 16 days. This systematically
    EXCLUDES most long-term injuries, unsigned or newly traded players.
    """
    scheduled = sorted(fixtures, key=lambda g: (g["utc"],g["id"]))
    for i in range(1, len(scheduled)):
        if scheduled[i]["id"] == scheduled[i-1]["id"]:
            raise ValueError("Repeated fixture")
    active_by_game = {}
    for r in positive:
        if r["id"] in active_by_game:
            raise ValueError("Repeated positive player-game")
        active_by_game[r["id"]] = r
    team_schedule = defaultdict(list)
    for g in scheduled:
        for team in (g["home"],g["away"]):
            team_schedule[team].append(g)
    team_times = {t:[g["utc"] for g in rows] for t,rows in team_schedule.items()}
    prior = []
    qa = Counter()
    out = []
    for game in scheduled:
        stamp_now = game["utc"]
        latest = prior[-1] if prior else None
        if latest is None:
            qa["no_prior_appearance"] += 1
        elif (stamp_now - latest["utc"] > timedelta(days=MAX_DAYS_SINCE_PLAYED)):
            qa["inactive_older_than_16_days_excluded"] += 1
        elif latest["club"] not in (game["home"],game["away"]):
            qa["last_observed_club_not_playing"] += 1
        else:
            club = latest["club"]
            tenure = []
            for r in reversed(prior):
                if r["club"] != club:
                    break
                tenure.append(r)
            tenure.reverse()
            if len(tenure) < MIN_TENURE_APPEARANCES:
                qa["insufficient_prior_same_club_appearances"] += 1
            else:
                team_games = team_schedule[club]
                dates = team_times[club]
                first_idx = bisect.bisect_left(dates, tenure[0]["utc"])
                end_idx = bisect.bisect_left(dates, stamp_now)
                previous_fixtures = team_games[first_idx:end_idx]
                if len(previous_fixtures) < MIN_TENURE_TEAM_GAMES:
                    qa["insufficient_prior_club_fixtures"] += 1
                else:
                    seen = {r["id"] for r in tenure}
                    twenty = previous_fixtures[-20:]
                    five = previous_fixtures[-5:]
                    k20 = sum(g["id"] in seen for g in twenty)
                    k5 = sum(g["id"] in seen for g in five)
                    actual = active_by_game.get(game["id"])
                    if actual is not None and actual["club"] != club:
                        # A roster change in the *target* game is an observed
                        # out-of-scope outcome, not an injured/absent player.
                        qa["target_game_club_change_unknown_excluded"] += 1
                    else:
                        y = int(actual is not None)
                        out.append({"pid":pid, "season":year, "game_id":game["id"],
                                    "team_proxy":club, "utc":stamp_now,
                                    "appearance_logged_in_exact_game":y,
                                    "last20_appeared":k20, "last20_team_games":len(twenty),
                                    "last5_appeared":k5, "last5_team_games":len(five),
                                    "historical_team_membership_unverified":True,
                                    "negative_is_explicit_DNP":False})
                        qa["positive_logged_appearance" if y else
                           "no_logged_appearance_NOT_DNP"] += 1
        if game["id"] in active_by_game:
            # IMPORTANT: appending AFTER feature construction proves
            # no target-game played event leaks into the model.
            prior.append(active_by_game[game["id"]])
    return out, qa


def cohort(fixtures, logs):
    rows={}
    qa={}
    for year in SEASONS:
        samples=[]
        counts=Counter()
        for pid, positive in sorted(logs[year].items()):
            subset, cnt = player_samples(fixtures[year], positive, pid, year)
            samples.extend(subset)
            counts.update(cnt)
        samples.sort(key=lambda v:(v["utc"],v["pid"],v["game_id"]))
        if len({(v["pid"],v["game_id"]) for v in samples}) != len(samples):
            raise ValueError("Duplicate selected player x final game sample")
        rows[year] = samples
        qa[year] = {
            "eligible_proxy_player_games":len(samples),
            "distinct_players":len({v["pid"] for v in samples}),
            "distinct_NBA_games":len({v["game_id"] for v in samples}),
            "logged_appearances":sum(v["appearance_logged_in_exact_game"] for v in samples),
            "no_logged_appearance_NOT_DNP":sum(1-v["appearance_logged_in_exact_game"] for v in samples),
            "selection_qa":dict(counts)}
    return rows, qa


def estimate(row, params):
    shrink, recency = params
    a20, n20 = row["last20_appeared"], row["last20_team_games"]
    a5, n5 = row["last5_appeared"], row["last5_team_games"]
    if not (0 <= a20 <= n20 <= 20 and 0 <= a5 <= n5 <= 5 and n20 >= MIN_TENURE_TEAM_GAMES):
        raise ValueError("Invalid past game frequency")
    p20 = (a20 + PRIOR_MEAN*shrink)/(n20+shrink)
    p5 = (a5 + PRIOR_MEAN*shrink)/(n5+shrink)
    return max(0.001,min(0.999,(1-recency)*p20+recency*p5))


def score(rows, params):
    if not rows:
        raise ValueError("No eligible historical player-game cohort")
    se=0.0;ll=0.0
    by_player=defaultdict(list)
    calib=defaultdict(lambda:[0,0.0,0.0])
    for r in rows:
        y=r["appearance_logged_in_exact_game"]
        if y not in (0,1):
            raise ValueError("Incorrect appearance target")
        p=estimate(r,params)
        loss=(p-y)**2
        se+=loss
        ll+=-(y*math.log(p)+(1-y)*math.log1p(-p))
        by_player[r["pid"]].append(loss)
        bucket=min(4,int(p*5))
        calib[bucket][0]+=1
        calib[bucket][1]+=p
        calib[bucket][2]+=y
    n=len(rows)
    return {"n":n,"brier":se/n,"logloss":ll/n,
            "by_player":by_player,
            "calibration":{str(i):{"n":v[0],"mean_score":round(v[1]/v[0],3),
                                   "appearance_share":round(v[2]/v[0],3)}
                           for i,v in sorted(calib.items()) if v[0]}}


def uncertainty(rows, candidate, base, repeats=BOOTSTRAP, seed=20261027):
    by_person=defaultdict(list)
    for r in rows:
        y=r["appearance_logged_in_exact_game"]
        gain=(estimate(r,base)-y)**2 - (estimate(r,candidate)-y)**2
        by_person[r["pid"]].append(gain)
    ids=sorted(by_person)
    rng=Random(seed)
    estimates=[]
    for _ in range(repeats):
        drawn=[ids[rng.randrange(len(ids))] for __ in ids]
        val=[x for pid in drawn for x in by_person[pid]]
        estimates.append(fmean(val))
    estimates.sort()
    return [round(estimates[int((repeats-1)*0.025)],6),
            round(estimates[int((repeats-1)*0.975)],6)]


def report(history, identity, calendar, now):
    if now.utcoffset() is None:
        raise ValueError("Research audit time must be aware")
    fixtures=validated_fixtures(calendar)
    logs, historical_qa=positive_logs(history,identity,fixtures)
    samples, cohort_qa=cohort(fixtures,logs)
    dev=samples["2024/25"]
    test=samples["2025/26"]
    if (len(dev)<1000 or len(test)<1000 or
            cohort_qa["2024/25"]["distinct_players"]<100 or
            cohort_qa["2025/26"]["distinct_players"]<100):
        raise ValueError("Not enough selected retrospective historical observations")
    tuned=min(PARAMS,key=lambda p:(score(dev,p)["brier"],p))
    dev_base=score(dev,BASELINE)
    dev_best=score(dev,tuned)
    test_base=score(test,BASELINE)
    test_best=score(test,tuned)
    bounds=uncertainty(test,tuned,BASELINE)
    describe=lambda x:{"n":x["n"],"brier":round(x["brier"],6),
                        "logloss":round(x["logloss"],6)}
    return {
        "schema_version":1,"status":STATUS,"model_status":STATUS,
        "adopt_on_site":False,"updated_at_utc":stamp(now),
        "source":"Audited NBA positive-minute game logs and independently verified ESPN historical tipoffs",
        "source_seasons":list(SEASONS),
        "training_season":"2024/25","untouched_holdout_season":"2025/26",
        "sample_selection":"high_identity, >=8 previous same-club appearances, >=10 prior club games, played within 16 days",
        "target":"appearance_logged_in_exact_last_observed_club_game_NOT_explicit_DNP",
        "confirmed_DNP_observations":0,
        "target_is_true_game_day_eligibility":False,
        "retrospective_true_scheduled_asof_proven":False,
        "no_future_played_outcomes_used_as_features":True,
        "full_fantasy_population_covered":False,
        "p_play_probability_calibrated":False,
        "selected_sample_Brier_only":True,
        "transfer_value_proven":False,
        "eligible_sample_qa":cohort_qa,
        "source_positive_log_qa":historical_qa,
        "fixed_baseline_params":{"shrinkage":BASELINE[0],"recent_weight":BASELINE[1]},
        "selected_development_params":{"shrinkage":tuned[0],"recent_weight":tuned[1]},
        "development":{"baseline":describe(dev_base),"candidate":describe(dev_best)},
        "holdout":{"baseline":describe(test_base),"candidate":describe(test_best),
                   "candidate_minus_baseline_brier":
                        round(test_best["brier"]-test_base["brier"],6),
                   "player_cluster_95pct_gain_in_Brier":bounds,
                   "candidate_calibration_selected_proxy":test_best["calibration"],
                   "metric_cannot_be_used_for_pop_p_play":True},
        "candidate_beats_baseline_reliably_in_selected_proxy":
            bool(bounds[0]>0 and tuned!=BASELINE),
        "eligibility_or_DNP_model_adoption_allowed":False,
        "limitations":[
            "Target 'no logged appearance' is NOT a confirmed DNP, injury, out-of-game roster, or a game-day lineup.",
            "Historical team membership is inferred only from preceding positive-minute games.",
            "Highly selected recently active players exclude most long absences, new joiners, and many trades.",
            "2024/25 and 2025/26 final fixture times cannot prove the schedule was known at the historical decision time.",
            "Neither ESPN official historical Injury Reports nor verified historical DNP flags are in this dataset.",
            "2023/24 positive-minute history informs conditional FP research but lacks separately validated historical UTC fixture exposure here.",
            "Only heldout retrospective appearance-frequency Brier is measured; no prospective p_play calibration.",
            "No historical or personal Sports.ru transfer prices, no KEEP/TRANSFER improvement demonstrated."],
    }


def run(check_only=False):
    def read(name):
        return json.loads((DATA/name).read_text(encoding="utf8"))
    value=report(read("nba_history.json"),read("identity.json"),
                 read("historical_tipoffs.json"),datetime.now(UTC))
    if not check_only:
        dest=DATA/"historical_appearance_proxy_research.json"
        tmp=dest.with_suffix(".tmp")
        tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf8")
        tmp.replace(dest)
    return {"status":value["status"],
            "cohort":{k:{m:v[m] for m in ("eligible_proxy_player_games","distinct_players",
                                         "logged_appearances","no_logged_appearance_NOT_DNP")}
                      for k,v in value["eligible_sample_qa"].items()},
            "test":value["holdout"],"check_only":check_only,
            "adopt_on_site":value["adopt_on_site"]}


if __name__ == "__main__":
    print(json.dumps(run(check_only="--check" in sys.argv),
                     ensure_ascii=False,indent=2))
