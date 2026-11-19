"""Read-only public roster fields from the user snapshot; no ownership fields."""
from __future__ import annotations
import hashlib
import json
import re
import statistics
import xml.etree.ElementTree as ET
import zipfile

from ingest_positions import HERE, ROOT, NS, num


def workbook_cells(path):
    with zipfile.ZipFile(path) as archive:
        strings=[]
        if "xl/sharedStrings.xml" in archive.namelist():
            strings=["".join(x.itertext()) for x in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("m:si",NS)]
        rows={}
        for row in ET.fromstring(archive.read("xl/worksheets/sheet1.xml")).findall("m:sheetData/m:row",NS):
            cells={}
            for c in row:
                value,inline=c.find("m:v",NS),c.find("m:is",NS)
                text=value.text if value is not None else "".join(inline.itertext()) if inline is not None else ""
                if c.attrib.get("t")=="s":text=strings[int(text)]
                cells[re.sub(r"\d","",c.attrib.get("r",""))]=str(text or "").strip()
            rows[int(row.attrib["r"])]=cells
        return rows


def main():
    mapping=json.loads((HERE/"results/SEASON_POSITION_MAPPING.json").read_text())
    path=ROOT/"upload/NBA_2627.xlsx";cells=workbook_cells(path)
    output=[]
    for row in mapping["records"]:
        if row["season"]!=2027:continue
        source=cells[row["source_row"]]
        output.append({"nba_person_id":row["nba_person_id"],"russian_name":row["russian_name"],"english_name":row["english_name"],
                       "team":row["fantasy_team"],"team_ru":row["fantasy_team_ru"],"position":row["fantasy_position"],
                       "observed_price":num(source.get("E")),"price_kind":"current_quote_at_user_snapshot_not_start_price",
                       "season_total_fp":row["total_fp"],"season_games":row["games"],"season_avg_fp":row["avg_fp"],
                       "popularity_percent":num(source.get("F")),"identity_status":row["identity_status"],"identity_method":row["identity_method"],
                       "source_file":path.name,"source_sheet":row["sheet"],"source_row":row["source_row"],
                       "source_observed_at_utc":mapping["observed_at_utc"],"position_vintage":row["position_vintage"],
                       "official_price_asof_timestamp_verified":False,"person_game_credits_available":False})
    result={"schema":"user_supplied_public_fantasy_roster_v1","season":"2026/27","observed_at_utc":mapping["observed_at_utc"],
            "source_file":path.name,"source_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "rows":output,"counts":{"rows":len(output),"resolved_nba_ids":sum(bool(r["nba_person_id"]) for r in output)},
            "constraints":["No user ownership or transfer records. This is the public player listing supplied by the user.",
                           "Prices are observed current quotes from this snapshot, not starting prices and not a guaranteed real-time market feed.",
                           "Unresolved players remain UNKNOWN; new site IDs require an exact NBA-ID merge, not surname matching.",
                           "A short undated recent-game tail cannot independently identify per-player-game fantasy credits."]}
    (HERE/"results/CURRENT_ROSTER_PUBLIC.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    summaries=[]
    for meta in mapping["source_workbooks"]:
        rows=workbook_cells(ROOT/"upload"/meta["file"]);tails=[];counts=[]
        for index,row in rows.items():
            if index==1:continue
            values=[v for c,v in row.items() if (len(c)>1 or c>="S") and v]
            tails.append(sum(num(v) is not None for v in values));counts.append(len(values))
        summaries.append({"file":meta["file"],"rows":len(rows)-1,"recent_game_header":rows[1].get("S"),
                          "numeric_recent_cells_median":statistics.median(tails),"numeric_recent_cells_max":max(tails),
                          "nonempty_recent_cells_max":max(counts),"dated_game_headers":False,"game_id_headers":False})
    schema={"status":"season_totals_and_short_undated_tails_only","independent_player_game_credit_target_ready":False,
            "workbooks":summaries,"missing_mark_policy":"Dash, blank and omitted entries are not interpreted as DNP or matched to schedule games.",
            "price_column":"E/$ is the observed quote; not the starting price.",
            "provenance":"User-supplied XLSX, read directly from worksheet XML; no links or hidden date/game ID map found."}
    (HERE/"results/XLSX_SCHEMA_AND_CREDIT_QA.json").write_text(json.dumps(schema,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result["counts"]),json.dumps(summaries,ensure_ascii=False))


if __name__=="__main__":main()
