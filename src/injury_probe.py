"""Read-only audit of public historical NBA injury datasets.

Not used as production data; prints schema/date coverage and validation metadata.
No PDFs are fetched, no roster state is modified, and no raw dataset is copied.
"""
from __future__ import annotations
import collections
import csv
import io
import json
import urllib.request

SOURCES = {
    "2024_25": "https://raw.githubusercontent.com/Professor-Pete/2024-2025-injury_analysis/main/data/season_rows.csv",
    "2025_26": "https://raw.githubusercontent.com/Torgo28/NBA_AI_Player_Analysis/main/data/rag/processed/injury_reports.csv",
}

def inspect_csv(source, fetch=None):
    if fetch is None:
        def fetch(url):
            req = urllib.request.Request(url, headers={
                "User-Agent": "NBASeasonLab/1.3 noncommercial-research",
                "Accept": "text/csv"})
            return urllib.request.urlopen(req, timeout=75)
    with fetch(source) as response:
        with io.TextIOWrapper(response, encoding="utf-8-sig", newline="") as stream:
            reader=csv.DictReader(stream)
            fields=reader.fieldnames or []
            if not fields or len(fields) < 3:raise ValueError("Insufficient CSV header")
            rows=0
            unique=collections.defaultdict(set)
            distributions=collections.defaultdict(collections.Counter)
            dates=collections.defaultdict(list)
            sample=[]
            for row in reader:
                rows+=1
                if rows<=3:sample.append({k:str(row.get(k,""))[:75] for k in fields[:14]})
                for key,value in row.items():
                    if value is None:continue
                    key=key or ""
                    if len(unique[key])<50:unique[key].add(str(value)[:120])
                    v=str(value)
                    if any(s in key.lower() for s in ("status","time","type","reason")):
                        if len(distributions[key])<50:distributions[key][v[:60]]+=1
                    if any(s in key.lower() for s in ("date","timestamp")) and len(v)>=10:
                        if len(dates[key])<2000: dates[key].append(v[:20])
            return {
                "rows":rows, "columns":fields,
                "sample":sample,
                "column_cardinalities_capped":{k:len(v) for k,v in unique.items()},
                "date_extrema":{k:[min(v),max(v)] for k,v in dates.items() if v},
                "status_samples":{k:c.most_common(10) for k,c in distributions.items()},
            }

def main():
    d={}
    for name,url in SOURCES.items():
        d[name]=inspect_csv(url)
    print(json.dumps(d,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
