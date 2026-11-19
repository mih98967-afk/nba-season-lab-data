"""Apply the reviewed current catalog bridge without changing old forecasts."""
from __future__ import annotations
import copy
import datetime as dt
import json
from pathlib import Path
import re
from model_store import ROOT,sha256

OVERLAY_PATH=ROOT/'research_extension/position_20261118/results/CURRENT_CATALOG_IDENTITY_OVERLAY.json'


def _time(value):
    stamp=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('NAIVE_IDENTITY_OBSERVATION_TIME')
    return stamp.astimezone(dt.timezone.utc)


def apply_reviewed_identity(identity,catalog,issued_at,*,overlay=None,source_catalog_sha256=None):
    overlay=overlay if overlay is not None else json.loads(OVERLAY_PATH.read_text())
    if overlay.get('schema')!='nba_catalog_identity_overlay_v1':raise ValueError('INVALID_IDENTITY_OVERLAY_SCHEMA')
    if _time(overlay['observed_at_utc'])>_time(issued_at):raise ValueError('IDENTITY_EVIDENCE_NOT_YET_OBSERVED')
    # Provenance hashes raw data/catalog.json, not Hosting's larger base wrapper.
    # The exact per-player fingerprints below bind the bridge to Hosting's IDs.
    if source_catalog_sha256 is not None and overlay.get('source_sha256',{}).get('catalog')!=source_catalog_sha256:
        raise ValueError('IDENTITY_OVERLAY_CATALOG_HASH_CHANGED')
    result=copy.deepcopy(identity);seen=set()
    for cid,item in overlay['players'].items():
        player=catalog.get(cid)
        if player is None:raise ValueError('IDENTITY_OVERLAY_UNKNOWN_CATALOG_ID')
        for source,target in [('catalog_name','name'),('catalog_team','team'),('catalog_position','pos')]:
            if item.get(source)!=player.get(target):raise ValueError('IDENTITY_CATALOG_FINGERPRINT_MISMATCH:'+cid)
        nba=str(item.get('nba_id',''))
        if item.get('confidence')!='high' or not re.fullmatch(r'[1-9]\d*',nba):raise ValueError('IDENTITY_OVERLAY_UNVERIFIED_ID')
        if nba in seen:raise ValueError('IDENTITY_OVERLAY_DUPLICATE_NBA_ID')
        seen.add(nba)
        result[cid]=dict(result.get(cid,{}),nba_id=nba,confidence='high',
                         reviewed_current_identity=True,reviewed_identity_method=item.get('method'),
                         reviewed_identity_observed_at_utc=overlay['observed_at_utc'])
    return result,{'schema':overlay['schema'],'observed_at_utc':overlay['observed_at_utc'],
                   'mapped_catalog_players':len(overlay['players']),'unresolved_catalog_players':len(overlay.get('unresolved',[])),
                   'historical_vintage_verified':False,'old_frozen_forecasts_changed':False}
