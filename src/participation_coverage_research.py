"""Coverage QA for the full fantasy catalog across explicitly checked NBA games.

This is NOT a retrospective roster database. Current Sports.ru catalog clubs
are used only to build an *unverified candidate* player-game denominator.
Missing a boxscore row is UNKNOWN, never DNP or a zero-FP outcome.
Verified participation labels are imported only from participation_cohort QA.
Official PDF and Telegram evidence is attached with strictly as-of clocks;
neither can retroactively infer whether an unlisted player played.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json

from src.sync import DATA
from src.rolling_decision_research import instant, stamp, official_asof, telegram_asof

UTC=timezone.utc
POS=("C","PF","SF","SG","PG")
EXPECTED_CO = "research_only_not_deployed"
NOT_OBSERVED = "unknown_roster_membership_or_unlisted"


def coverage(live, cohort, explicit, catalog, official, telegram, now):
    if now.utcoffset() is None:
        raise ValueError("Evaluation time must include timezone")
    now=now.astimezone(UTC)
    if cohort.get("schema_version") != 1 or cohort.get("status") != EXPECTED_CO or cohort.get("adopt_on_site") is not False:
        raise ValueError("Cohort has not passed research evidence QA")
    if explicit.get("schema_version") != 1 or explicit.get("adopt_on_site") is not False:
        raise ValueError("Explicit DNP observations are untrusted")
    if official.get("status") != "official_report_observed_pit_research_only":
        raise ValueError("Official source provenance missing")
    if telegram.get("status") != "observed_unconfirmed_research_archive":
        raise ValueError("Telegram source provenance missing")
    if not isinstance(live.get("games"), list):
        raise ValueError("Final matches missing")
    checked=explicit.get("checked_final_game_ids")
    if not isinstance(checked,list) or len(set(checked))!=len(checked) or not checked:
        raise ValueError("No uniquely verified completed boxscores")
    if len(checked)!=cohort.get("summary",{}).get("verified_full_boxscores_checked"):
        raise ValueError("Cohort and DNP checked-game coverage disagree")
    finals={}
    for game in live["games"]:
        if not isinstance(game,dict) or game.get("status")!="final":
            continue
        gid=game.get("id")
        if not isinstance(gid,str) or gid in finals:
            raise ValueError("Duplicate final game identity")
        finals[gid]=game
    for gid in checked:
        game=finals.get(gid)
        if not game:
            raise ValueError("Previously checked game is not finalized")
        if not game.get("home") or not game.get("away") or game["home"]==game["away"]:
            raise ValueError("Invalid club fixtures")
        if instant(game["utc"])>now:
            raise ValueError("Future completed game")
    people=catalog.get("players")
    if not isinstance(people,list) or len(people)<400:
        raise ValueError("Full Sports.ru catalog is required")
    by_player={}
    clubs=defaultdict(list)
    for p in people:
        pid=p.get("id")
        if not pid or pid in by_player or p.get("pos") not in POS or not p.get("team"):
            raise ValueError("Catalog has missing/duplicate identity, club, or position")
        by_player[pid]=p
        clubs[p["team"]].append(p)
    if len(clubs)!=30:
        raise ValueError("Full 30-club NBA catalog required")
    labels={}
    for row in cohort.get("records",[]):
        key=(row.get("game_id"),row.get("player_id"))
        if not all(isinstance(x,str) and x for x in key) or key in labels:
            raise ValueError("Duplicate or malformed verified outcome")
        if key[0] not in checked or key[1] not in by_player:
            raise ValueError("Verified outcome outside current catalog/check scope")
        g=finals[key[0]]
        if row.get("team") not in (g["home"],g["away"]) or row.get("game_utc")!=g["utc"]:
            raise ValueError("Verified outcome conflicts with final fixture")
        if row.get("position")!=by_player[key[1]]["pos"]:
            raise ValueError("Verified outcome position mismatch")
        if row.get("participation_label") not in (0,1):
            raise ValueError("Unknown verified participation label")
        if (row["participation_label"]==1 and row.get("evidence")!="positive_minutes_verified_sportsru_fp") or (
            row["participation_label"]==0 and row.get("evidence")!="explicit_espn_didNotPlay_true"
        ):
            raise ValueError("Verified label has incorrect evidence")
        seen=row.get("source_first_observed_at_utc")
        if seen:
            moment=instant(seen)
            if moment>now or moment<instant(g["utc"]):
                raise ValueError("Outcome cannot be first observed before game")
        labels[key]=row
    if len(labels)!=cohort["summary"]["listed_player_game_labels"]:
        raise ValueError("Verified outcome totals do not reconcile")
    allRows=[]
    known={}
    team_stats=defaultdict(Counter)
    position_stats=defaultdict(Counter)
    game_stats=defaultdict(Counter)
    stats=Counter()
    for gid in sorted(checked,key=lambda x:(finals[x]["utc"],x)):
        g=finals[gid]
        lock=instant(g["utc"])-timedelta(minutes=30)
        for team in (g["home"],g["away"]):
            for p in sorted(clubs[team],key=lambda x:x["id"]):
                pid=p["id"]
                key=(gid,pid)
                evid=labels.get(key)
                if evid is not None and evid["team"] == team:
                    labels.pop(key)
                else:
                    evid=None
                outcome=(
                    "played_verified" if evid and evid["participation_label"]==1
                    else "explicit_dnp_verified" if evid else NOT_OBSERVED
                )
                status=official_asof(official,gid,pid,team,lock)
                news=telegram_asof(telegram,pid,lock)
                row={"game_id":gid,"player_id":pid,"catalog_club_asof_today":p["team"],
                     "match_team":team,"position":p["pos"],"game_utc":g["utc"],
                     "individual_lock_utc":stamp(lock),"roster_membership_at_game":"UNVERIFIED_CATALOG_PROXY",
                     "observed_outcome":outcome,
                     "evidence":evid.get("evidence") if evid else None,
                     "source_first_observed_at_utc":evid.get("source_first_observed_at_utc") if evid else None,
                     "official_status_known_at_lock":status.get("status") if status else None,
                     "official_event_id_known_at_lock":status.get("event_id") if status else None,
                     "telegram_player_context_known_at_lock":bool(news),
                     "no_medical_inference":True}
                allRows.append(row)
                known[key]=row
                for counter in (team_stats[team],position_stats[p["pos"]],game_stats[gid],stats):
                    counter["catalog_proxy_candidate_player_games"]+=1
                    counter[outcome]+=1
                    if status:counter["official_asof_known"]+=1
                    if news:counter["telegram_asof_context_unconfirmed"]+=1
    # Preserve verified labels for players whose CURRENT catalog club differs
    # from the club in their historical game. Do not silently move historical
    # outcomes into the wrong team or include them in proxy denominator.
    outside=[]
    for (gid,pid),e in sorted(labels.items()):
        p=by_player[pid]
        outside.append({"game_id":gid,"player_id":pid,"historical_game_club":e["team"],
                        "current_catalog_club":p["team"],"position":p["pos"],
                        "game_utc":e["game_utc"],
                        "participation_label":e["participation_label"],
                        "source_first_observed_at_utc":e.get("source_first_observed_at_utc"),
                        "evidence":e["evidence"],
                        "reason":"catalog_club_mismatch_not_proof_of_bad_historical_boxscore"})
    stats["verified_labels_outside_catalog_proxy"]=len(outside)
    if stats["played_verified"]+stats["explicit_dnp_verified"]+len(outside)!=len(cohort["records"]):
        raise ValueError("Lost confirmed outcomes when building opportunity denominator")
    stats["verified_labels_total"]=len(cohort["records"])
    stats["catalog_players_total"]=len(people)
    stats["checked_games"]=len(checked)
    stats["games_without_complete_dnp_audit"]=len(finals)-len(checked)
    stats["unknown_is_not_absent_or_injured"]=stats[NOT_OBSERVED]
    return {"schema_version":1,"status":EXPECTED_CO,
            "model_status":EXPECTED_CO,"adopt_on_site":False,
            "updated_at_utc":stamp(now),
            "sample_unit":"player_x_checked_game_using_current_catalog_club_proxy_not_confirmed_historical_roster",
            "summary":dict(stats),
            "by_position":{p:dict(position_stats[p]) for p in POS},
            "by_team":{t:dict(team_stats[t]) for t in sorted(clubs)},
            "by_game":{gid:dict(game_stats[gid]) for gid in sorted(checked)},
            "catalog_proxy_records":allRows,
            "verified_outcomes_outside_proxy":outside,
            "full_population_validated_participation_labels":False,
            "full_population_brier_enabled":False,
            "predictions_adopt_on_site":False,
            "limitations":[
                "All current catalog-team assignments are an unverified historical roster PROXY, even within a fully checked game.",
                "An unlisted player can be injured, traded, waived, ineligible, or playing for another club: label UNKNOWN, not DNP.",
                "A confirmed played or explicit DNP outcome is valid only for its exact final game and club.",
                "Official statuses are exact-game PDF evidence first observed before individual lock; Telegram is unconfirmed and fixture-unverified.",
                "No DNP denominator completeness, calibrated p_play, medical classification, price model or transfer advantage follows.",
                "Unreviewed games are excluded entirely; adding them with negative labels would create selection bias.",
            ]}


def run():
    load=lambda name:json.loads((DATA/name).read_text(encoding="utf8"))
    result=coverage(load("live.json"),load("participation_cohort_research.json"),
       load("explicit_dnp_research.json"),load("catalog.json"),
       load("official_injury_status_archive.json"),
       load("telegram_archive.json"),datetime.now(UTC))
    dest=DATA/"participation_coverage_research.json"
    tmp=dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":")),encoding="utf8")
    tmp.replace(dest)
    return {"status":result["status"],"summary":result["summary"]}


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
