"""Conservative positional parser for official NBA injury report PDFs.

Research-only. Uses native text coordinates (no OCR). Player statuses are
accepted only when PDF columns, matchup/team, ID, date and official UTC
schedule all agree. No missing-row healthy inference; no FP adjustment.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from io import BytesIO
from pathlib import Path
import hashlib,json,re,unicodedata
from src.official_injury_archive import get,DATA

ET=ZoneInfo("America/New_York")
STATUS={"Out","Doubtful","Questionable","Probable","Available"}
CLUBS={
 "Atlanta Hawks":"ATL","Boston Celtics":"BOS","Brooklyn Nets":"BKN",
 "Charlotte Hornets":"CHA","Chicago Bulls":"CHI","Cleveland Cavaliers":"CLE",
 "Dallas Mavericks":"DAL","Denver Nuggets":"DEN","Detroit Pistons":"DET",
 "Golden State Warriors":"GSW","Houston Rockets":"HOU","Indiana Pacers":"IND",
 "LA Clippers":"LAC","Los Angeles Clippers":"LAC","Los Angeles Lakers":"LAL",
 "Memphis Grizzlies":"MEM","Miami Heat":"MIA","Milwaukee Bucks":"MIL",
 "Minnesota Timberwolves":"MIN","New Orleans Pelicans":"NOP",
 "New York Knicks":"NYK","Oklahoma City Thunder":"OKC","Orlando Magic":"ORL",
 "Philadelphia 76ers":"PHI","Phoenix Suns":"PHX","Portland Trail Blazers":"POR",
 "Sacramento Kings":"SAC","San Antonio Spurs":"SAS","Toronto Raptors":"TOR",
 "Utah Jazz":"UTA","Washington Wizards":"WAS"}
ALIASES={"NY":"NYK","GS":"GSW","SA":"SAS","NO":"NOP"}
def norm(x):
    x=str(x or "").strip()
    if "," in x:
        a,b=x.split(",",1);x=b.strip()+" "+a.strip()
    x=unicodedata.normalize("NFKD",x).encode("ascii","ignore").decode().lower()
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9 ]"," ",x)).strip()

CLUBS={norm(k):v for k,v in CLUBS.items()}

def group_lines(words):
    lines=[]
    for w in sorted(words,key=lambda x:(x["top"],x["x0"])):
        # Discard header area, page footer and invisible fragments.
        if w["top"]<98 or w["top"]>580:continue
        if lines and abs(lines[-1][0]-w["top"])<2.2:
            lines[-1][1].append(w)
        else:lines.append([w["top"],[w]])
    return [sorted(t,key=lambda x:x["x0"]) for _,t in lines]

def col(words,lower,upper):
    return " ".join(w["text"] for w in words if lower<=w["x0"]<upper).strip()

def parse_pages(pages):
    events=[];qa=Counter()
    current_team=None;current_matchup=None;current_date=None
    for page in pages:
        for line in group_lines(page.extract_words(x_tolerance=2,y_tolerance=2)):
            date_text=col(line,19,109)
            if re.fullmatch(r"\d{1,2}/\d{1,2}/20\d{2}",date_text):
                try:current_date=datetime.strptime(date_text,"%m/%d/%Y").date().isoformat()
                except ValueError:qa["bad_date"]+=1;current_date=None
            matchup=col(line,192,258).upper().replace(" ","")
            if re.fullmatch(r"[A-Z]{2,4}@[A-Z]{2,4}",matchup):
                away,home=(ALIASES.get(t,t) for t in matchup.split("@"))
                current_matchup=(away,home);current_team=None
            club=col(line,263,418)
            if club:
                guessed=CLUBS.get(norm(club))
                if guessed:current_team=guessed
                elif not norm(club).startswith(("team","player")):
                    qa["unrecognized_team_fragment"]+=1
            player=col(line,420,575)
            status=col(line,580,663).title()
            if status=="Not Yet Submitted":
                qa["not_yet_submitted_team"]+=1
                continue
            if status not in STATUS:
                if status:qa["other_status_text"]+=1
                continue
            if not player or "," not in player:
                qa["status_without_player"]+=1;continue
            if not current_team or not current_matchup or not current_date:
                qa["missing_context"]+=1;continue
            if current_team not in current_matchup:
                qa["team_matchup_conflict"]+=1;continue
            events.append({"et_date":current_date,"team":current_team,
                           "away":current_matchup[0],"home":current_matchup[1],
                           "player_name":norm(player),"official_status":status.lower()})
    return events,dict(qa)

def strict_enrich(events,catalog,identity,schedule,report_info):
    available=defaultdict(set)
    for p in catalog.get("players",[]):
        pid=p.get("id")
        full=(identity.get("players",{}).get(pid) or {}).get("english") or p.get("english")
        if pid and full:available[norm(full)].add(pid)
    names={k:next(iter(v)) for k,v in available.items() if len(v)==1}
    games=defaultdict(list)
    for game in schedule.get("games",[]):
        if game.get("status") in ("canceled","cancelled"):continue
        key=(game.get("et_date"),game.get("away"),game.get("home"))
        games[key].append(game)
    accepted={};qc=Counter()
    for e in events:
        ids=names.get(e["player_name"])
        if not ids:qc["unknown_or_ambiguous_identity"]+=1;continue
        key=(e["et_date"],e["away"],e["home"])
        fixture=games.get(key)
        if not fixture or len(fixture)!=1:
            qc["missing_or_ambiguous_fixture"]+=1;continue
        g=fixture[0]
        report_time=datetime.fromisoformat(report_info["report_at_utc"].replace("Z","+00:00"))
        game_time=datetime.fromisoformat(g["utc"].replace("Z","+00:00"))
        if report_time>=game_time:
            qc["report_after_tipoff"]+=1;continue
        if e["team"] not in (g["away"],g["home"]):
            qc["team_fixture_mismatch"]+=1;continue
        # Cross-check with catalog may be stale after a trade; exact official
        # report team is retained, but never overwrite a Sports.ru club field.
        item={"player_id":ids,"team":e["team"],"home":e["home"],"away":e["away"],
              "game_id":g["id"],"tipoff_utc":g["utc"],"report_at_utc":report_info["report_at_utc"],
              "first_seen_at_utc":report_info["first_seen_at_utc"],
              "status":e["official_status"],"source_url":report_info["url"],
              "evidence":"official_pdf_exact_name_team_fixture"}
        rowkey=(ids,g["id"])
        if rowkey in accepted:
            qc["duplicate_player_game"]+=1
            accepted.pop(rowkey)
            continue
        accepted[rowkey]=item
    return sorted(accepted.values(),key=lambda x:(x["tipoff_utc"],x["player_id"])),dict(qc)

def run():
    from pdfplumber import open as pdfopen
    meta=json.loads((DATA/"official_injury_snapshots.json").read_text())
    if meta.get("status")!="official_pdf_inventory_not_player_predictions":
        raise ValueError("Official inventory unverified")
    report=meta["snapshots"][-1]
    raw=get(report["url"])
    if hashlib.sha256(raw).hexdigest()!=report["sha256"]:
        raise ValueError("Official PDF changed since first observed; do not backdate")
    with pdfopen(BytesIO(raw)) as doc:events,qa=parse_pages(doc.pages)
    if len(events)<15:raise ValueError("Too few official rows for validated extraction")
    catalog=json.loads((DATA/"catalog.json").read_text())
    identity=json.loads((DATA/"identity.json").read_text())
    schedule=json.loads((DATA/"schedule.json").read_text())
    mapped,joinqa=strict_enrich(events,catalog,identity,schedule,report)
    if len(mapped)<10 or len(mapped)/len(events)<.50:
        raise ValueError("Official row matching coverage below safe threshold")
    output={"schema_version":1,"status":"research_only_not_deployed",
      "updated_at_utc":datetime.now(timezone.utc).isoformat(),
      "report_at_utc":report["report_at_utc"],"first_seen_at_utc":report["first_seen_at_utc"],
      "source_url":report["url"],"raw_status_rows":len(events),"matched_count":len(mapped),
      "parser_qa":qa,"join_qa":joinqa,"events":mapped,
      "warning":"No status automatically changes FP; absent players are NOT healthy; timestamp is first observed, not guaranteed published availability",
      "adopt_on_site":False}
    # Append-only, first-seen provenance. Revisions of a PDF can never
    # overwrite previously observed status events.
    archive_path=DATA/"official_injury_status_archive.json"
    old=json.loads(archive_path.read_text()) if archive_path.exists() else {}
    observations={x["event_id"]:x for x in old.get("events",[]) if x.get("event_id")}
    for e in mapped:
        event_id=report["sha256"]+"|"+e["game_id"]+"|"+e["player_id"]
        observations.setdefault(event_id,{"event_id":event_id,**e})
    archive={"schema_version":1,"status":"official_report_observed_pit_research_only",
      "updated_at_utc":output["updated_at_utc"],"events":list(observations.values()),
      "n":len(observations),"adopt_on_site":False,
      "warning":"No historical backdating. Only report statuses, not full roster health status."}
    archive_tmp=archive_path.with_suffix(".tmp")
    archive_tmp.write_text(json.dumps(archive,ensure_ascii=False,separators=(",",":")),encoding="utf8")
    archive_tmp.replace(archive_path)
    dest=DATA/"official_injury_status_research.json";tmp=dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf8")
    tmp.replace(dest)
    return {"raw":len(events),"matched":len(mapped),"qa":qa,"joinqa":joinqa}
if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False,indent=2))
