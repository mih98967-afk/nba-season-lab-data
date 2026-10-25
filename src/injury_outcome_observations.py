"""Point-in-time observational injury-status outcome QA (NOT a deployed p_play model).

Claims played only from matched NBA Sports.ru player boxscore rows, and missing
games only as UNKNOWN. Never interprets absence from a boxscore as a verified
DNP. Tests prospective source timing; does not adjust anyone's FP.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime,timezone,timedelta
import json
from src.sync import DATA

STATUS=("out","doubtful","questionable","probable","available")
UTC=timezone.utc

def instant(s):
    if not isinstance(s,str):raise ValueError("Missing timestamp")
    t=datetime.fromisoformat(s.replace("Z","+00:00"))
    if t.utcoffset() is None:raise ValueError("Naive timestamp")
    return t.astimezone(UTC)

def evaluate(archive,live,now):
    if now.utcoffset() is None:raise ValueError("UTC-aware current time required")
    if archive.get("status")!="official_report_observed_pit_research_only":
        raise ValueError("Wrong injury archive status")
    if not isinstance(live.get("rows"),list) or not isinstance(live.get("games"),list):
        raise ValueError("Missing live game outcomes")
    final={g["id"]:g for g in live["games"] if g.get("status")=="final"}
    rows=defaultdict(list)
    for row in live["rows"]:
        if row.get("game_id") and row.get("id"):
            rows[row["game_id"]].append(row)
    report=Counter();confirmed=Counter();by_status=defaultdict(Counter);seen=set()
    for event in archive.get("events",[]):
        if not isinstance(event,dict):
            report["malformed"]+=1;continue
        key=(event.get("game_id"),event.get("player_id"),event.get("event_id"))
        if key in seen:report["duplicate"]+=1;continue
        seen.add(key)
        try:
            report_at=instant(event["report_at_utc"])
            first_seen=instant(event["first_seen_at_utc"])
            tip=instant(event["tipoff_utc"])
        except (ValueError,KeyError,TypeError):
            report["invalid_timestamp"]+=1;continue
        # Must be known before Sports.ru 30-minute player lock.
        if first_seen>tip-timedelta(minutes=30) or report_at>tip-timedelta(minutes=30):
            report["not_known_before_lock"]+=1;continue
        if tip>now:
            report["future_game"]+=1;continue
        game=final.get(event["game_id"])
        if not game:
            report["not_verified_final"]+=1;continue
        if (game.get("home"),game.get("away"))!=(event.get("home"),event.get("away")):
            report["game_team_mismatch"]+=1;continue
        candidates=rows.get(event["game_id"],[])
        active_teams=Counter(x.get("team") for x in candidates)
        # Essential sanity gate; no missing row becomes a zero label.
        if active_teams[event.get("team")]<5:
            report["insufficient_team_boxscore"]+=1;continue
        matches=[x for x in candidates if x.get("id")==event.get("player_id") and x.get("team")==event.get("team")]
        status=event.get("status")
        if status not in STATUS:
            report["unknown_status"]+=1;continue
        if len(matches)==1 and matches[0].get("played") is True:
            by_status[status]["played_verified"]+=1
            confirmed["played_verified"]+=1
        elif len(matches)==0:
            by_status[status]["missing_row_unknown"]+=1
            report["missing_row_unknown"]+=1
        else:
            report["ambiguous_boxscore"]+=1
    usable=sum(v["played_verified"] for v in by_status.values())
    unknown=sum(v["missing_row_unknown"] for v in by_status.values())
    return {"schema_version":1,"status":"prospective_observation_only_no_model_adoption",
       "updated_at_utc":now.astimezone(UTC).isoformat(),
       "verified_played":usable,"unlisted_unknown":unknown,
       "qa":dict(report),"by_status":{k:dict(v) for k,v in sorted(by_status.items())},
       "sample_sufficient_for_brier":False,"adopt_on_site":False,
       "warning":"No true negative labels from missing boxscore rows. No Brier or model improvements claimed."}

def run():
    archive=json.loads((DATA/"official_injury_status_archive.json").read_text(encoding="utf8"))
    live=json.loads((DATA/"live.json").read_text(encoding="utf8"))
    result=evaluate(archive,live,datetime.now(UTC))
    p=DATA/"injury_outcome_observations.json"
    tmp=p.with_suffix(".tmp");tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8");tmp.replace(p)
    return {k:result[k] for k in ("status","verified_played","unlisted_unknown","qa")}
if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False,indent=2))
