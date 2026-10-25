"""Read-only official NBA Injury Report snapshot inventory.

Stores ONLY immutable observed-at timestamps, source URLs and SHA256 PDFs.
It does NOT extract medical assertions, map player IDs or update expected FP.
Data in Firestore, user rosters, and price models are never accessed.
"""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse,urljoin
from pathlib import Path
from html import unescape
import hashlib,json,re,urllib.request
from src.sync import DATA

INDEX="https://official.nba.com/nba-injury-report-2026-27-season"
ALLOWED_HOST="ak-static.cms.nba.com"
ET=ZoneInfo("America/New_York")
OUT=DATA/"official_injury_snapshots.json"
PAT=re.compile(r'Injury-Report_(20\d{2}-\d{2}-\d{2})_(\d{2})_(\d{2})(AM|PM)\.pdf',re.I)
HREF=re.compile(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']',re.I)

def get(url,limit=6_000_000):
    host=urlparse(url).hostname
    if not url.startswith("https://") or host not in (ALLOWED_HOST,"official.nba.com"):
        raise ValueError("Unexpected official report host")
    req=urllib.request.Request(url,headers={"User-Agent":"NBA-Season-Lab/1.5 (research; non-commercial)",
                                           "Accept":"application/pdf,text/html"})
    with urllib.request.urlopen(req,timeout=35) as res:
        body=res.read(limit+1)
        if len(body)>limit:raise ValueError("Oversized NBA report")
        return body

def extract_index(page):
    html=page.decode("utf-8","replace")
    links={}
    for link in HREF.findall(html):
        url=urljoin(INDEX,unescape(link))
        if urlparse(url).hostname!=ALLOWED_HOST:continue
        basename=urlparse(url).path.rsplit("/",1)[-1]
        match=PAT.fullmatch(basename)
        if not match:continue
        day,hh,mm,ap=match.groups()
        hour=int(hh)%12+(12 if ap.upper()=="PM" else 0)
        try: local=datetime.fromisoformat(day).replace(hour=hour,minute=int(mm),tzinfo=ET)
        except ValueError:continue
        utc=local.astimezone(timezone.utc)
        key=utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        if key in links and links[key]!=url:raise ValueError("Conflicting reports with same timestamp")
        links[key]=url
    return [{"report_at_utc":k,"url":url} for k,url in sorted(links.items())]

def update(index_page,pdf_bytes,prior=None,now=None,keep_last=500):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError("Current time must have UTC offset")
    now=now.astimezone(timezone.utc)
    reports=extract_index(index_page)
    eligible=[r for r in reports if
              datetime.fromisoformat(r["report_at_utc"].replace("Z","+00:00")) <= now+timedelta(minutes=5)]
    if not eligible:raise ValueError("Official NBA report index empty or future dated")
    latest=eligible[-1]
    if len(pdf_bytes)<3000 or not pdf_bytes.startswith(b"%PDF-"):raise ValueError("Bad NBA PDF")
    old=(prior or {}).get("snapshots",[])
    seen={}
    for s in old:
        if not isinstance(s,dict):continue
        stamp=s.get("report_at_utc")
        if not stamp or stamp in seen:continue
        if not s.get("first_seen_at_utc") or not s.get("sha256"):continue
        seen[stamp]=s
    stamp=latest["report_at_utc"]
    digest=hashlib.sha256(pdf_bytes).hexdigest()
    first=now.strftime("%Y-%m-%dT%H:%M:%SZ")
    previous=seen.get(stamp)
    if previous and previous["sha256"]!=digest:
        # A revised report at the SAME nominal timestamp is a new observation.
        # Do not silently rewrite the historical known-at version.
        new={"report_at_utc":stamp,"url":latest["url"],"sha256":digest,
             "first_seen_at_utc":first,"revision_of_sha256":previous["sha256"]}
        key=stamp+"#"+digest[:12]
        seen[key]=new
    elif not previous:
        seen[stamp]={"report_at_utc":stamp,"url":latest["url"],"sha256":digest,
                     "first_seen_at_utc":first}
    values=sorted(seen.values(),key=lambda v:(v["report_at_utc"],v["first_seen_at_utc"]))[-keep_last:]
    return {"schema_version":1,"status":"official_pdf_inventory_not_player_predictions",
            "source":INDEX,"updated_at_utc":first,"snapshots":values,
            "latest_report_at_utc":stamp,"latest_report_url":latest["url"],
            "all_links_visible":len(reports),"archive_count":len(values),
            "point_in_time_rule":"report_at_utc and first_seen_at_utc must precede decision_time",
            "do_not_infer":"Missing player is unknown; NOT YET SUBMITTED is unknown",
            "model_integration":False}

def asof(records,decision_utc):
    t=datetime.fromisoformat(decision_utc.replace("Z","+00:00"))
    if t.utcoffset() is None:raise ValueError("Decision time must carry timezone")
    return [r for r in records
            if datetime.fromisoformat(r["report_at_utc"].replace("Z","+00:00"))<=t
            and datetime.fromisoformat(r["first_seen_at_utc"].replace("Z","+00:00"))<=t]

def run(fetch=get,now=None):
    page=fetch(INDEX)
    listed=extract_index(page)
    if not listed:raise ValueError("No official reports")
    now=now or datetime.now(timezone.utc)
    eligible=[r for r in listed if datetime.fromisoformat(r["report_at_utc"].replace("Z","+00:00")) <=now+timedelta(minutes=5)]
    if not eligible:raise ValueError("No eligible PDF")
    pdf=fetch(eligible[-1]["url"])
    old=json.loads(OUT.read_text()) if OUT.exists() else {}
    updated=update(page,pdf,old,now)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(updated,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(OUT)
    return {k:updated[k] for k in ["status","latest_report_at_utc","archive_count","all_links_visible"]}

if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False,indent=2))
