"""Research-only append-only archive of publicly observed Telegram injury signals.

An archive entry's first_seen_at is the first time OUR collector observed it,
not proof of when an external source made a medical claim. Backtests require
published_at <= decision_time AND first_seen_at <= decision_time, otherwise
signals are retrospective and not eligible for point-in-time evaluation.
"""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
import json,pathlib
from src.telegram_feed import DATA,utc

SOURCE=DATA/"telegram.json"
TARGET=DATA/"telegram_archive.json"

def canonical_event(event):
    """Reject malformed data and ambiguous name matching."""
    if not isinstance(event,dict):return None
    published=utc(event.get("published_at"))
    if not published:return None
    if event.get("verification")!="unconfirmed_telegram":return None
    if event.get("match_quality")!="full_name":return None
    ids=event.get("player_ids")
    if not isinstance(ids,list) or len(ids)!=1 or not str(ids[0]).startswith("n"):return None
    if event.get("status") not in ("out","doubtful","questionable","probable","available","injury_update"):return None
    if not str(event.get("url","")).startswith("https://t.me/nba_injurynews/"):return None
    if not event.get("id"):return None
    return {k:event[k] for k in ("id","url","published_at","player_ids","status","match_quality",
                                 "text","source","verification") if k in event}

def update(current,prior=None,now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError("UTC now required")
    now=now.astimezone(timezone.utc)
    prior=prior or {}
    if not isinstance(current,dict) or current.get("status")!="public_preview_unverified":raise ValueError("Invalid current feed")
    retained={}
    for event in prior.get("events",[]):
        e=canonical_event(event)
        if e and utc(event.get("first_seen_at")):
            retained[e["id"]]={**e,"first_seen_at":event["first_seen_at"]}
    added=0
    for event in current.get("events",[]):
        e=canonical_event(event)
        if not e:continue
        published=utc(e["published_at"])
        if published>now+timedelta(hours=2):continue
        if e["id"] not in retained:
            # Never backdate this first_seen timestamp to the publication time.
            retained[e["id"]]={**e,"first_seen_at":now.isoformat(timespec="seconds").replace("+00:00","Z")}
            added+=1
    events=sorted(retained.values(),key=lambda e:(e["published_at"],e["id"]))
    return {"schema_version":1,"status":"observed_unconfirmed_research_archive",
            "updated_at_utc":now.isoformat(timespec="seconds").replace("+00:00","Z"),
            "asof_rule":"both published_at and first_seen_at must predate the decision",
            "selection":"full_name only; other ambiguous matches omitted",
            "warning":"Absence of a post is NOT evidence a player was healthy; retrospective imports are NOT point-in-time data",
            "observations":len(events),"added":added,"events":events}

def asof(events,decision_time):
    t=utc(decision_time)
    if t is None:raise ValueError("Decision time must include UTC offset")
    return [e for e in events if utc(e.get("published_at")) and utc(e.get("first_seen_at"))
            and utc(e["published_at"])<=t and utc(e["first_seen_at"])<=t]

def run():
    src=json.loads(SOURCE.read_text(encoding="utf8"))
    old=json.loads(TARGET.read_text(encoding="utf8")) if TARGET.exists() else {}
    report=update(src,old)
    tmp=TARGET.with_suffix(".tmp")
    tmp.write_text(json.dumps(report,ensure_ascii=False,separators=(",",":")),encoding="utf8")
    tmp.replace(TARGET)
    return {k:report[k] for k in ("status","observations","added","updated_at_utc")}

if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
