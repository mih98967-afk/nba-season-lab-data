#!/bin/sh
# Run from the root of the delivered research package, with a trusted environment.
# No network, model publishing, profile changes or automatic transfers.
set -eu
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
CODE=research/match_context
SOURCE=${1:-source}
ROOT=${2:-reproduced}
mkdir -p "$ROOT"
python -m unittest discover -s "$CODE" -p 'test_*.py'
python "$CODE/preflight.py" --source "$SOURCE" --output "$ROOT/RAW_SOURCE_PREFLIGHT.json"
python "$CODE/run_phase2.py" --source "$SOURCE" --output "$ROOT/results_phase2"
python "$CODE/diagnostic_opponent.py" --results "$ROOT/results_phase2"
python "$CODE/challenge_families.py" --phase2 "$ROOT/results_phase2" --output "$ROOT/results_challenge"
python "$CODE/finalize_near_game.py" --phase2 "$ROOT/results_phase2" --challenge "$ROOT/results_challenge" --output "$ROOT/results_near"
python "$CODE/refit_near_latest.py" --phase2 "$ROOT/results_phase2" --selected "$ROOT/results_near" --output "$ROOT/results_near_latest"
python "$CODE/train_horizons.py" --source "$SOURCE" --output "$ROOT/results_horizons"
python "$CODE/refit_latest.py" --historical "$ROOT/results_horizons" --output "$ROOT/results_latest"
python "$CODE/current_validation.py" --source "$SOURCE" --models "$ROOT/results_horizons" --output "$ROOT/results_current"
python "$CODE/score_current_frozen.py" --features "$ROOT/results_current/feature_frame.pkl" --models "$ROOT/results_near_latest" --output "$ROOT/results_current_near_latest"
python "$CODE/score_current_frozen.py" --features "$ROOT/results_current/feature_frame.pkl" --models "$ROOT/results_latest" --output "$ROOT/results_current_latest"
python "$CODE/choose_distribution.py" --phase2 "$ROOT/results_phase2" --near "$ROOT/results_near_latest" --output "$ROOT/results_near_distribution"
python "$CODE/score_current_frozen.py" --features "$ROOT/results_current/feature_frame.pkl" --models "$ROOT/results_near_distribution" --output "$ROOT/results_current_distribution"
