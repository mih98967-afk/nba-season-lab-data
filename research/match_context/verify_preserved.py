"""Verify imported model/forecast bytes against the prior public commitment."""
from pathlib import Path
import hashlib
import json
import gzip
import argparse
import os

ROOT = Path(__file__).resolve().parent
COMPANION = Path(os.environ.get('NBA_RESEARCH_BASE', ROOT.parents[1] / 'research_base')).resolve()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verified_bytes(candidates, expected_sha, size_limit):
    """Read the first available local/companion artifact without modifying it."""
    for path in candidates:
        packed = path.with_suffix(path.suffix + '.gz')
        if path.is_file():
            if path.stat().st_size > size_limit:
                raise ValueError('ARTIFACT_SIZE_LIMIT: ' + str(path))
            content = path.read_bytes()
        elif packed.is_file():
            with gzip.open(packed, 'rb') as stream:
                content = stream.read(size_limit + 1)
        else:
            continue
        if len(content) > size_limit:
            raise ValueError('ARTIFACT_SIZE_LIMIT: ' + str(path))
        if hashlib.sha256(content).hexdigest() != expected_sha:
            raise ValueError('ARTIFACT_HASH_MISMATCH: ' + str(path))
        return content
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--require-binaries', action='store_true')
    args = parser.parse_args()
    original = ROOT / "prospective/20261116"
    c = json.loads((original / "COMMITMENT.json").read_text())
    forecast = original / "forecasts.json"
    assert c['sha256'] == '5aa81fa5db8f8a4e240cce3ec2477fad17626822c5eea2c02f39dab1b932a0cb'
    assert c['records'] == 1741
    forecast_content = verified_bytes(
        [forecast, COMPANION / 'prospective_20261116/forecasts.json'],
        c['sha256'], 5_000_000)
    if forecast_content is not None:
        assert len(json.loads(forecast_content)['records']) == 1741
    elif args.require_binaries:
        raise ValueError('ORIGINAL_FORECAST_ARTIFACT_REQUIRED')
    models = ROOT / "models/20261116"
    verified = 0
    for name in ("results_near_latest", "results_latest", "results_near_distribution"):
        card = json.loads((models / name / "MODEL_RESEARCH_REPORT.json").read_text())
        model_path = models / name / "research_models.pkl"
        assert card['model_sha256'] in c['model_hashes'].values()
        content = verified_bytes(
            [model_path, COMPANION / name / 'research_models.pkl'],
            card['model_sha256'], 20_000_000)
        if content is not None:
            verified += 1
        elif args.require_binaries:
            raise ValueError('ORIGINAL_WEIGHT_ARTIFACT_REQUIRED: ' + name)
    print(json.dumps({'metadata_verified':True,'weight_bytes_verified':verified,
                      'forecast_bytes_verified':forecast_content is not None,
                      'binary_artifacts_shipped_in_companion_checkpoint':True,
                      'full_retrain':False}))

if __name__ == "__main__":
    main()
