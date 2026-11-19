"""Create a public UTF-8 package; never publishes or changes GitHub itself."""
from __future__ import annotations
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
PLAIN_RESULTS=("GENERAL_REFERENCE.json","POSITION_RESEARCH_REPORT.json","DEVELOPMENT_SELECTION.json",
               "MAPPING_COVERAGE.json","FEATURE_POSITION_COVERAGE.json","catalog_history_corrections.json",
               "XLSX_SCHEMA_AND_CREDIT_QA.json","INGEST_PROVENANCE.json","position_subgroup_metrics.csv")
ENCODED=("results/general_ridge_reference.pkl","results/general_reference_covariance.npz",
         "results/historical_residual_anchor.csv.gz","results/SEASON_POSITION_MAPPING.json",
         "results/NBA_IDENTITY_INDEX.json","results/CURRENT_ROSTER_PUBLIC.json",
         "results/matchup_difficulty.json","reviewed_aliases.json")
TEXT=("PROTOCOL.md","ACCEPTANCE_SUMMARY.md","README.md")


def sha(data):return hashlib.sha256(data).hexdigest()


def build(destination):
    destination.mkdir(exist_ok=True,parents=True)
    (destination/"results").mkdir(exist_ok=True)
    (destination/"packed_data").mkdir(exist_ok=True)
    if destination.resolve()!=HERE.resolve():
        for source in HERE.glob("*.py"):
            shutil.copy2(source,destination/source.name)
        for name in TEXT:
            shutil.copy2(HERE/name,destination/name)
    manifest={"schema":"nba-position-public-assets-v1","chunk_limit_bytes":59001,"files":{}}
    for name in PLAIN_RESULTS:
        relative="results/"+name;data=(HERE/relative).read_bytes()
        if len(data)>60000:raise ValueError("PLAIN_RESULT_TOO_LARGE:"+name)
        if destination.resolve()!=HERE.resolve():(destination/relative).write_bytes(data)
        manifest["files"][relative]={"size_bytes":len(data),"sha256":sha(data),"encoding":"plain","storage":[{"path":relative,"sha256":sha(data)}]}
    for relative in ENCODED:
        data=(HERE/relative).read_bytes()
        encoded_data=data if relative.endswith((".gz",".npz")) else gzip.compress(data,mtime=0)
        encoding="base64" if relative.endswith((".gz",".npz")) else "gzip+base64"
        encoded=base64.b64encode(encoded_data)
        stem=relative.replace("/","__");storage=[]
        for i,start in enumerate(range(0,len(encoded),59000)):
            path=f"packed_data/{stem}.{i:03d}.b64";chunk=encoded[start:start+59000]+b"\n"
            (destination/path).write_bytes(chunk);storage.append({"path":path,"sha256":sha(chunk)})
        manifest["files"][relative]={"size_bytes":len(data),"sha256":sha(data),"encoding":encoding,"storage":storage}
    (destination/"PUBLIC_ASSETS_MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n")
    full=json.loads((HERE/"results/CURRENT_ROSTER_PUBLIC.json").read_text())
    columns=["nba_person_id","russian_name","team","position","observed_price","season_total_fp","season_games","season_avg_fp","popularity_percent","source_row"]
    compact={"schema":"user_public_fantasy_roster_compact_v1","season":"2026/27","source_file":full["source_file"],"source_sha256":full["source_sha256"],
             "observed_at_utc":full["observed_at_utc"],"price_kind":"observed_current_quote_not_start_price_not_T_minus30_verified", "columns":columns,
             "rows":[[r.get(k) for k in columns] for r in full["rows"]],
             "identity_policy":"Non-null NBA IDs are exact season identities. Null is UNKNOWN and must not be forced to a surname match.",
             "full_provenance_asset":"results/CURRENT_ROSTER_PUBLIC.json"}
    compact_bytes=(json.dumps(compact,ensure_ascii=False,separators=(",",":"))+"\n").encode()
    if len(compact_bytes)>60000:raise ValueError("COMPACT_CURRENT_ROSTER_TOO_LARGE")
    (destination/"results/CURRENT_ROSTER_COMPACT.json").write_bytes(compact_bytes)
    (destination/".gitignore").write_text("__pycache__/\n*.pyc\ndaily_work/\nresults/*.pkl\nresults/*.npz\nresults/*.csv.gz\nresults/SEASON_POSITION_MAPPING.json\nresults/NBA_IDENTITY_INDEX.json\nresults/CURRENT_ROSTER_PUBLIC.json\nresults/matchup_difficulty.json\nreviewed_aliases.json\n")
    files=[p for p in destination.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    print(json.dumps({"destination":str(destination),"encoded_parts":sum(len(v["storage"]) for v in manifest["files"].values() if v["encoding"]!="plain"),
                      "compact_roster_bytes":len(compact_bytes),"largest_encoded_part_bytes":max(p.stat().st_size for p in (destination/"packed_data").glob("*.b64")),
                      "plain_control_and_code_max_bytes":max(p.stat().st_size for p in files if p.suffix in (".py",".md") or p.name in ("PUBLIC_ASSETS_MANIFEST.json","CURRENT_ROSTER_COMPACT.json"))},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--destination",type=Path,required=True);args=parser.parse_args();build(args.destination)
