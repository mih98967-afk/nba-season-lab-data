"""Research-only observed participation cohort: played versus explicit ESPN DNP.

The unit is a UNIQUE Sports.ru player x finalized NBA game. One label requires
an actual positive-minute Sports.ru FP row or an explicit ESPN didNotPlay flag
in a previously verified two-team boxscore. Never label absent players as DNP.

Important: ESPN "checked" games are a selected subset, and boxscore-listed
players are a selected subset of the fantasy player pool. Do NOT fit or score
p_play on this sample as if it represented all player-games. Source observed
times are separate from game tipoffs and cannot be backdated.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json, math

from src.sync import DATA
from src.explicit_dnp_research import norm
from src.rolling_decision_research import (
    instant, stamp, official_asof, telegram_asof,
)

UTC=timezone.utc
POSITIONS=("C","PF","SF","SG","PG")
MIN_ACTIVE_PER_TEAM=5
ESPN="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event="

def utc_or_none(value):
    try:return stamp(instant(value))
    except (TypeError, ValueError):return None

def build(live, explicit, catalog, identity, rolling, official, telegram, now):
    if now.utcoffset() is None:
        raise ValueError("Aware evaluation time required")
    now=now.astimezone(UTC)
    if explicit.get("schema_version")!=1 or explicit.get("adopt_on_site") is not False:
        raise ValueError("Unverified explicit DNP archive")
    if rolling.get("schema_version")!=1 or rolling.get("adopt_on_site") is not False:
        raise ValueError("Unverified rolling observations")
    if official.get("status")!="official_report_observed_pit_research_only":
        raise ValueError("Unverified official injury provenance")
    if telegram.get("status")!="observed_unconfirmed_research_archive":
        raise ValueError("Unverified Telegram provenance")
    if not isinstance(live.get("games"),list) or not isinstance(live.get("rows"),list):
        raise ValueError("Incomplete public live feed")
    people=catalog.get("players")
    if not isinstance(people,list) or len(people)<400:
        raise ValueError("Missing Sports.ru full fantasy catalog")
    ids={}
    for p in people:
        pid=p.get("id")
        if not isinstance(pid,str) or pid in ids:
            raise ValueError("Nonunique catalog player identity")
        if p.get("pos") not in POSITIONS:
            raise ValueError("Unknown Sports.ru fantasy position")
        ids[pid]=p
    all_finals={}
    for g in live["games"]:
        if not isinstance(g,dict) or g.get("status")!="final":
            continue
        gid=g.get("id")
        if not isinstance(gid,str) or gid in all_finals:
            raise ValueError("Duplicate/invalid completed game")
        all_finals[gid]=g
    checked=explicit.get("checked_final_game_ids")
    if not isinstance(checked,list) or len(set(checked))!=len(checked):
        raise ValueError("Missing or repeated checked game ID")
    for gid in checked:
        if gid not in all_finals:
            raise ValueError("Checked ESPN game is not verified final: "+str(gid))
        g=all_finals[gid]
        if not g.get("espn_id") or instant(g["utc"])>now:
            raise ValueError("Invalid checked game's time or ESPN reference")
    checked_set=set(checked)
    positions=Counter()
    clubs=defaultdict(Counter)
    qa=Counter()
    records={}
    identity_people=identity.get("players",{})
    observed_first=(rolling.get("row_first_seen_at_utc") or {})
    for r in live["rows"]:
        if not isinstance(r,dict) or r.get("game_id") not in checked_set:
            continue
        if r.get("played") is not True:
            qa["ignored_unverified_positive"]+=1
            continue
        game=all_finals[r["game_id"]]
        pid=r.get("id")
        if not isinstance(pid,str) or pid not in ids:
            qa["active_identity_not_in_catalog"]+=1
            continue
        club=r.get("team")
        if club not in (game.get("home"),game.get("away")):
            raise ValueError("Positive boxscore team contradicts completed fixture")
        try:
            minutes=float(r["minutes"]);fp=float(r["fp"])
        except (KeyError,TypeError,ValueError) as exc:
            raise ValueError("Active boxscore lacks valid Sports.ru FP/minutes") from exc
        if not (math.isfinite(minutes) and minutes>0 and math.isfinite(fp)):
            raise ValueError("Active boxscore nonfinite/minutes <= 0")
        expected=(identity_people.get(pid) or {}).get("english") or ids[pid].get("english")
        if not expected or norm(expected)!=norm(r.get("name")):
            qa["unverified_active_name_match"]+=1
            continue
        key=(r["game_id"],pid)
        if key in records:
            raise ValueError("Duplicate positive player-game: "+str(key))
        seen=utc_or_none(observed_first.get(key[0]+"|"+key[1]))
        if seen is None:
            qa["positive_first_seen_not_archived"]+=1
        elif instant(seen)<instant(game["utc"]):
            raise ValueError("Observed final FP before game tipoff")
        records[key]={
            "game_id":key[0],"player_id":pid,"team":club,
            "position":ids[pid]["pos"],"game_utc":game["utc"],
            "played":True,"participation_label":1,
            "evidence":"positive_minutes_verified_sportsru_fp",
            "source_first_observed_at_utc":seen,
            "membership_evidence":"named_active_boxscore_same_club_and_fixture",
            "sportsru_fp_if_played":fp,"played_minutes":minutes,
            "catalog_team_matches_game":ids[pid].get("team")==club,
            "source_url":r.get("source_url"),
        }
    team_active=Counter((r["game_id"],r["team"]) for r in records.values())
    for gid in checked_set:
        g=all_finals[gid]
        for club in (g["home"],g["away"]):
            if team_active[gid,club]<MIN_ACTIVE_PER_TEAM:
                raise ValueError("Incomplete active team boxscore in checked game")
    for d in explicit.get("events",[]):
        if not isinstance(d,dict):
            raise ValueError("Malformed explicit DNP evidence")
        gid,pid=d.get("game_id"),d.get("player_id")
        if gid not in checked_set:
            raise ValueError("DNP event outside checked ESPN boxscore")
        game=all_finals[gid]
        if pid not in ids:
            qa["dnp_identity_not_in_catalog"]+=1
            continue
        if (d.get("team") not in (game["home"],game["away"]) or
            d.get("home")!=game["home"] or d.get("away")!=game["away"] or
            d.get("game_utc")!=game["utc"]):
            raise ValueError("Explicit DNP team/fixture contradiction")
        if (d.get("evidence")!="explicit_espn_didNotPlay_true" or
            d.get("source_url")!=ESPN+str(game["espn_id"])):
            raise ValueError("Explicit DNP source provenance missing or inconsistent")
        seen=utc_or_none(d.get("observed_at_utc"))
        if seen is None or instant(seen)>now or instant(seen)<instant(game["utc"]):
            raise ValueError("Invalid explicit DNP first-seen time")
        key=(gid,pid)
        if key in records:
            raise ValueError("Explicit DNP conflicts with played Sports.ru FP")
        records[key]={
            "game_id":gid,"player_id":pid,"team":d["team"],
            "position":ids[pid]["pos"],"game_utc":game["utc"],
            "played":False,"participation_label":0,
            "evidence":"explicit_espn_didNotPlay_true",
            "source_first_observed_at_utc":seen,
            "membership_evidence":"explicit_named_ESPN_boxscore_listing_same_team_game",
            "identity_evidence":"unique_normalized_english_name_not_independent_NBA_ID",
            "catalog_team_matches_game":ids[pid].get("team")==d["team"],
            "source_url":d["source_url"],
        }
    by_pos=defaultdict(Counter)
    by_team=defaultdict(Counter)
    matched_official=0
    matched_tg=0
    final_records=[]
    for (gid,pid),r in sorted(records.items()):
        game=all_finals[gid]
        tip=instant(game["utc"])
        lock=tip-timedelta(minutes=30)
        status=official_asof(official,gid,pid,r["team"],lock)
        context=telegram_asof(telegram,pid,lock)
        r["individual_lock_utc"]=stamp(lock)
        r["official_known_at_lock"]=status
        r["telegram_unverified_known_at_lock"]=context
        if status:matched_official+=1
        if context:matched_tg+=1
        by_pos[r["position"]]["played" if r["played"] else "explicit_dnp"]+=1
        by_team[r["team"]]["played" if r["played"] else "explicit_dnp"]+=1
        if not r["catalog_team_matches_game"]:qa["catalog_team_changed_or_stale"]+=1
        final_records.append(r)
    npos=sum(x["played"] for x in by_pos.values())
    nneg=sum(x["explicit_dnp"] for x in by_pos.values())
    total=npos+nneg
    if not total or nneg>0 and not checked:
        raise ValueError("No usable source evidence")
    selected_ids={r["player_id"] for r in final_records}
    summary={
        "final_games_available":len(all_finals),
        "verified_full_boxscores_checked":len(checked),
        "checked_team_games":len(checked)*2,
        "games_without_explicit_dnp_audit":len(all_finals)-len(checked),
        "active_played":npos,
        "explicit_dnp":nneg,
        "listed_player_game_labels":total,
        "distinct_labelled_players":len(selected_ids),
        "fantasy_population_cards":len(people),
        "fantasy_players_without_any_checked_game_label":len(ids)-len(selected_ids),
        "official_status_known_before_individual_lock":matched_official,
        "telegram_player_context_known_before_individual_lock":matched_tg,
    }
    return {
        "schema_version":1,
        "status":"research_only_not_deployed",
        "model_status":"research_only_not_deployed",
        "adopt_on_site":False,
        "updated_at_utc":stamp(now),
        "sample_definition":"only explicit ESPN boxscore-listed player-games in a verified checked final game",
        "unit_of_analysis":"unique_Sports_ru_player_id_x_final_game_id",
        "summary":summary,
        "by_position":{pos:{k:by_pos[pos][k] for k in ("played","explicit_dnp")} for pos in POSITIONS},
        "by_team":{club:{k:by_team[club][k] for k in ("played","explicit_dnp")}
                   for club in sorted({p["team"] for p in people if p.get("team")})},
        "qa":dict(qa),
        "records":final_records,
        "sample_sufficient_for_population_brier":False,
        "representative_of_full_fantasy_population":False,
        "full_population_dnp_recall_known":False,
        "adoption_gate_passed":False,
        "limitations":[
            "Checked games are selected; observed active/DNP listings are not the full at-risk roster.",
            "ESPN explicit DNP rows not mapped by unique name remain unknown; absence is NEVER a negative label.",
            "Sports.ru game/position eligibility and historical team roster membership are not independently verified.",
            "DNP identity used unique English name matching; ESPN athlete IDs differ from NBA Stats IDs.",
            "Official and Telegram observations only count if first seen before individual player lock.",
            "Unknown outcomes are not zeros; no trained p_play, Brier, clinical conclusion, FP gains or transfers.",
        ],
    }

def run():
    def read(name):
        return json.loads((DATA/name).read_text(encoding="utf8"))
    report=build(read("live.json"),read("explicit_dnp_research.json"),
                 read("catalog.json"),read("identity.json"),
                 read("rolling_decision_research.json"),
                 read("official_injury_status_archive.json"),
                 read("telegram_archive.json"),datetime.now(UTC))
    path=DATA/"participation_cohort_research.json"
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(report,ensure_ascii=False,separators=(",",":")),encoding="utf8")
    tmp.replace(path)
    return {"status":report["status"],"summary":report["summary"],"qa":report["qa"]}

if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
