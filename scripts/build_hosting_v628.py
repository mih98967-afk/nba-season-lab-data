"""Build the existing Firebase Hosting site with verified public forecast snapshots.

No Firebase API, credentials, deployment, private state or training is involved.
Static assets are pinned separately from the current, expiring public data.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'site/hosting_v628'
MANIFEST = 'SOURCE_MANIFEST_v628.json'
BUNDLE_MANIFEST = 'BUNDLE_MANIFEST_v628.json'
GENERATED = {'data/model_forecasts_v1.json', 'data/matchup_difficulty_v1.json',
             'data/live.json', 'data/schedule.json'}
REQUIRED = {'index.html', 'app.js', 'styles.css', 'forecast_runtime.js',
            'schedule_difficulty.js', 'forecast_styles.css', 'firebase.json',
            'firebase-config.js', 'data/base.json'}
BROWSER_ASSETS = {'index.html', 'app.js', 'styles.css', 'forecast_runtime.js',
                  'schedule_difficulty.js', 'forecast_styles.css'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def static_files() -> dict[str, Path]:
    paths = {p.relative_to(SOURCE).as_posix(): p for p in SOURCE.rglob('*') if p.is_file()}
    assert not any(path.is_symlink() for path in paths.values()), 'Hosting source must not follow symlinks'
    return {name: path for name, path in paths.items()
            if name not in GENERATED | {MANIFEST, BUNDLE_MANIFEST}
            and '__pycache__' not in path.parts}


def source_manifest(write: bool = False) -> dict:
    paths = static_files()
    assert REQUIRED <= paths.keys(), f'Missing release assets: {REQUIRED - paths.keys()}'
    assert not any('private' in Path(name).parts for name in paths), 'Private files cannot enter Hosting'
    assert not any(any(part.startswith('.') for part in Path(name).parts) for name in paths), 'Hidden local configuration cannot enter Hosting'
    expected = {'schema_version': 1, 'release': '6.28', 'scope': 'static source assets; current public data added by builder',
                'files': {name: sha(path.read_bytes()) for name, path in sorted(paths.items())}}
    if write:
        (SOURCE / MANIFEST).write_text(json.dumps(expected, indent=2) + '\n')
    else:
        actual = json.loads((SOURCE / MANIFEST).read_text())
        assert actual == expected, 'Static source manifest differs; review changes before rebuilding manifest'
    html = (SOURCE / 'index.html').read_text()
    scripts = [s.split('?')[0] for s in re.findall(r'<script[^>]+src="([^"]+)"', html)]
    assert all((SOURCE / name).is_file() for name in scripts), 'Missing linked script'
    assert scripts.index('advice_readiness.js') < scripts.index('today_brief.js') < scripts.index('app.js')
    app = (SOURCE / 'app.js').read_text()
    for name in ('forecast_runtime.js', 'schedule_difficulty.js', 'forecast_styles.css'):
        assert name in app and name in paths, f'Missing dynamically loaded asset: {name}'
    config_source = (SOURCE / 'firebase-config.js').read_text()
    project = re.search(r"\bprojectId\s*:\s*['\"]([^'\"]+)['\"]", config_source)
    assert project and project.group(1) == 'nba-season-lab', 'Wrong Firebase project'
    config = json.loads((SOURCE / 'firebase.json').read_text())
    assert config['hosting']['public'] == '.', 'Full ZIP must have the existing Hosting root'
    return expected


def timestamp(value: str) -> dt.datetime:
    value = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    assert value.tzinfo is not None, 'Snapshot timestamps must have a timezone'
    return value.astimezone(dt.timezone.utc)


def snapshots(data_root: Path, now: dt.datetime | None = None) -> tuple[dict[str, bytes], dict]:
    now = now or dt.datetime.now(dt.timezone.utc)
    files = {name: (data_root / Path(name).name).read_bytes() for name in GENERATED}
    forecast = json.loads(files['data/model_forecasts_v1.json'])
    difficulty = json.loads(files['data/matchup_difficulty_v1.json'])
    live = json.loads(files['data/live.json'])
    schedule = json.loads(files['data/schedule.json'])
    assert forecast['schema_version'] == 1 and forecast['kind'] == 'nba_per_game_model_forecasts'
    assert forecast['status'] == 'ready', 'Stale model sources cannot become a release default'
    assert forecast['model_policy']['site_default'] is True, 'Site release gate has not passed'
    assert forecast['model_policy']['economic_gain_proven'] is False, 'Forecast release cannot certify fantasy economics'
    assert forecast['model_policy']['optimizer_policy_validated'] is False, 'Existing optimizer policy is not independently validated'
    assert forecast['model_policy']['day_ewma_selected'] is False
    assert forecast['model_policy']['fit_current_season'] is False
    assert forecast['model_policy']['intraday_injury_model_selected'] is False
    assert forecast['rows'], 'An empty forecast cannot become a release default'
    model_manifest = ROOT / 'research_extension/production_20261118/models/MANIFEST.json'
    assert forecast['model_manifest_sha256'] == sha(model_manifest.read_bytes()), 'Forecast weights manifest differs from release source'
    assert timestamp(forecast['source_capture_completed_at_utc']) <= timestamp(forecast['issued_at_utc']) <= now
    assert now < timestamp(forecast['valid_until_utc']), 'Regenerate expired forecast before making a full release ZIP'
    assert difficulty['schema'] == 'nba_matchup_difficulty_v1'
    assert dt.timedelta(0) <= now - timestamp(difficulty['as_of_utc']) <= dt.timedelta(hours=72)
    assert len(difficulty['opponents']) == 30, 'All thirty clubs must be represented'
    assert all(set(v) == {'ALL', 'PG', 'SG', 'SF', 'PF', 'C'} for v in difficulty['opponents'].values()), 'Every club needs general and five positional ratings'
    assert difficulty['production_forecasts_adjusted'] is False, 'Descriptive position ratings cannot change forecasts'
    assert live['schema_version'] == 4 and live['mode'] == 'live_sync'
    assert dt.timedelta(0) <= now - timestamp(live['updated_at_utc']) <= dt.timedelta(hours=24)
    assert schedule['schema_version'] == 1 and len(schedule['games']) >= 1100
    assert dt.timedelta(0) <= now - timestamp(schedule['updated_at_utc']) <= dt.timedelta(hours=72)
    meta = {'forecast_issued_at_utc': forecast['issued_at_utc'],
            'forecast_valid_until_utc': forecast['valid_until_utc'],
            'model_manifest_sha256': forecast['model_manifest_sha256'],
            'source_manifest_sha256': forecast['source_manifest_sha256'],
            'forecast_rows': len(forecast['rows']),
            'difficulty_as_of_utc': difficulty['as_of_utc'],
            'public_snapshots_sha256': {name: sha(value) for name, value in sorted(files.items())},
            'personal_state_included': False, 'firebase_deployed': False}
    return files, meta


def release_evidence(release_qa: Path, browser_qa: Path,
                     generated: dict[str, bytes], metadata: dict) -> dict:
    """Bind acceptance to exact generated data and browser-tested source bytes."""
    parity_bytes = release_qa.read_bytes()
    parity = json.loads(parity_bytes)
    assert parity.get('schema') == 'nba_frozen_release_qa_v1' and parity.get('status') == 'PASS', 'Frozen-weight release QA must pass'
    assert parity.get('feed_sha256') == sha(generated['data/model_forecasts_v1.json']), 'Release QA belongs to different forecast bytes'
    for key in ('model_manifest_sha256', 'source_manifest_sha256'):
        assert parity.get(key) == metadata[key], f'Release QA {key} mismatch'
    assert parity.get('feed_issued_at_utc') == metadata['forecast_issued_at_utc'], 'Release QA issuance mismatch'
    assert parity.get('feed_valid_until_utc') == metadata['forecast_valid_until_utc'], 'Release QA expiration mismatch'
    assert timestamp(parity['verified_at_utc']) >= timestamp(metadata['forecast_issued_at_utc'])
    browser_bytes = browser_qa.read_bytes()
    browser = json.loads(browser_bytes)
    assert browser.get('schema') == 'nba_hosting_browser_qa_v1' and browser.get('status') == 'PASS', 'Browser QA must pass'
    assert browser.get('mode') == 'actual', 'Synthetic browser fixtures cannot certify actual release snapshots'
    expected_data = {Path(name).name: sha(value) for name, value in generated.items()}
    assert browser.get('data_sha256') == expected_data, 'Browser QA belongs to different public data'
    tested_source = browser.get('source_sha256') or {}
    assert BROWSER_ASSETS <= tested_source.keys(), 'Browser QA omitted a required runtime asset'
    for name, expected_hash in tested_source.items():
        path = SOURCE / name
        assert not Path(name).is_absolute() and '..' not in Path(name).parts, 'Invalid browser QA source path'
        assert path.is_file() and sha(path.read_bytes()) == expected_hash, f'Browser-tested source changed: {name}'
    return {'release_qa_sha256': sha(parity_bytes), 'browser_qa_sha256': sha(browser_bytes),
            'weight_prediction_parity': 'PASS', 'actual_data_browser_qa': 'PASS',
            'browser_qa_verified_at_utc': browser['verified_at_utc']}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-source-manifest', action='store_true')
    parser.add_argument('--verify-source-only', action='store_true')
    parser.add_argument('--data-root', type=Path, default=ROOT / 'data')
    parser.add_argument('--output', type=Path, default=ROOT / 'nba-season-lab-v6.28-hosting.zip')
    parser.add_argument('--revision')
    parser.add_argument('--release-qa', type=Path, help='Passed exact-byte frozen-weight inference acceptance')
    parser.add_argument('--browser-qa', type=Path, help='Passed desktop/mobile QA of these exact current data and runtime bytes')
    args = parser.parse_args()
    manifest = source_manifest(args.write_source_manifest)
    print(f'PASS {len(manifest["files"])} complete static assets, hashes and runtime dependency references')
    if args.verify_source_only:
        return
    generated, metadata = snapshots(args.data_root)
    assert args.release_qa and args.browser_qa, 'Full Hosting ZIP requires --release-qa and --browser-qa'
    metadata.update(release_evidence(args.release_qa, args.browser_qa, generated, metadata))
    files = {name: path.read_bytes() for name, path in static_files().items()}
    assert {name: sha(content) for name, content in sorted(files.items())} == manifest['files'], 'Static source changed during bundle construction'
    files[MANIFEST] = (SOURCE / MANIFEST).read_bytes()
    files.update(generated)
    revision = args.revision or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert re.fullmatch(r'[0-9a-f]{40}', revision), 'Release revision must be a complete Git commit SHA'
    bundle = {'schema_version': 1, 'release': '6.28', 'source_revision': revision,
              'built_at_utc': dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z'),
              'metadata': metadata, 'files': {name: sha(content) for name, content in sorted(files.items())}}
    files[BUNDLE_MANIFEST] = (json.dumps(bundle, ensure_ascii=False, indent=2) + '\n').encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, 'w', compression=ZIP_DEFLATED, compresslevel=8) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(name, content)
    with ZipFile(args.output) as archive:
        assert set(archive.namelist()) == set(files), 'ZIP file inventory mismatch'
        assert archive.testzip() is None, 'ZIP CRC verification failed'
        for name, expected in bundle['files'].items():
            assert sha(archive.read(name)) == expected, name
    print(json.dumps({'status': 'FULL_HOSTING_ZIP_VERIFIED', 'file': str(args.output),
                      'bytes': args.output.stat().st_size, 'sha256': sha(args.output.read_bytes()),
                      'files': len(files), 'source_revision': revision, **metadata}, indent=2))


if __name__ == '__main__':
    main()
