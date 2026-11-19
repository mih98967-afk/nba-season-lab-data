"""Read-only 18-Nov snapshot using the preserved bounded four-source collector."""
from pathlib import Path
import datetime as dt, hashlib, importlib.util, json, os, sys
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(os.environ.get('NBA_RESEARCH_BASE',ROOT/'research_base'))
code=BASE/'research/match_context/collect_sources.py'
if not code.exists():code=ROOT/'research/match_context/collect_sources.py'
spec=importlib.util.spec_from_file_location('preserved_collector',code);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
out=Path(__file__).resolve().parent;current=out/'source/current'
if (current/'manifest.json').exists():raise ValueError('IMMUTABLE_CAPTURE_ALREADY_EXISTS')
started=dt.datetime.now(dt.timezone.utc).isoformat();manifest=module.collect((2027,),current)
(current/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
summary={'started_at_utc':started,'completed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'collector_sha256':hashlib.sha256(code.read_bytes()).hexdigest(),'expected_sources':4,'retrieved_sources':sum(r['status']=='retrieved' for r in manifest),'manifest':manifest,'original_sources_modified':False,'fit_or_selection_performed':False,'atomic_upstream_snapshot_guaranteed':False}
(out/'CAPTURE_SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
