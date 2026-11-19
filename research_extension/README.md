# NBA model research continuation — 17 November 2026

Continuation of existing draft PR178, after merged PR176/v6.20. Research only:
`adopt_on_site=false`, `real_KEEP_TRANSFER_gain_proven=false`. No Hosting, owner
profile, Firestore or Sports.ru transfer changes. PR177 remains a separate
unmerged intake branch. Original public frozen commitment is preserved.

## Completed research

1. Rebuilt the preserved three-season feature pipeline (134,426 rows) and
   reproduced original Ridge and calibrated CatBoost historical metrics exactly.
2. Tested nine predeclared recency recipes on two chronological development
   blocks. Calendar-day EWMA(7/21/60) is a small conditional-mean improvement;
   simple training-row recency weights did not help. See `recency/REPORT.json`.
3. Tested two incremental adjusted-opponent residual variants. Neither beat
   the existing Ridge on development; both were rejected. Existing matchup
   context remains. No valid historical PG/SG/SF/PF/C mapping was found.
4. Created a conservative current-only mapping for 392/484 catalog players.
   It is not historical Sports.ru truth and cannot backfill old forecasts.
5. Tested status-specific participation and interval calibration. All three
   fixed challengers failed their declared gates; retain the original models.
6. Scored the original 1,741 frozen forecasts on the first completed eight-game
   slate. Known/outcome denominators, sources and cross-source conflicts are
   explicit. One NBA date cannot establish stable model quality or fantasy gain.
7. Captured internally coherent fresh current sources and froze 334 new paired
   records (167 player-games, five games) before tipoff. Only the conditional
   mean differs; P(play) and quantiles are identical between paired models.

## What is now in the repository

The full preserved scientific source, protocols and tests from the companion
archive are under `research/match_context/`. The original model cards are under
`research/match_context/models/20261116/`; original and new prospective
commitments are preserved in the respective prospective directories.

Large binary weights, complete frozen forecast bytes, source snapshots and
row-level outputs are supplied in the companion research checkpoint, with
SHA256 manifests. Large-file publication to GitHub was interrupted; these
artifacts are not claimed to be present in GitHub. The new conditional-mean
model SHA is `a76fdf1dc1d6d53a7abb008bc386f43dac942ce4aa1996cbf721635dd71c2012`.
Original forecast SHA remains
`5aa81fa5db8f8a4e240cce3ec2477fad17626822c5eea2c02f39dab1b932a0cb`;
new paired forecast SHA is
`9b3cd732075d06c99ff0c3a30a2bd861ff606b0787c6de98d15302f93fa61ebb`.

Default CI checks commitment metadata and scientific unit tests. The saved-weight
inference parity test is explicitly skipped when the companion weights are not
installed; it passed locally on20 historical feature rows ×15 outputs. Use
`verify_preserved.py --require-binaries` for the local full-byte verification.
Neither this validation nor historical reproduction is described as full
scientific re-training in CI. Fresh downloads define new source vintages.

## Reproduction

The original companion package extracted as `research_base/` is the default
source/model location for the extension. Alternatively set `NBA_RESEARCH_BASE`
to its absolute directory. This variable is a data path, not a new repository.
The retained package supplies original sources, source hashes and prior reports.

```bash
python -m pip install -r research/match_context/requirements.txt
python research/match_context/verify_preserved.py
python research_extension/common/build_frame.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python research_extension/recency/run_study.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python research_extension/position/run_general_opponent.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python research_extension/participation/run_experiment.py --frame research_extension/common/feature_frame.pkl
```

Run each `test_*.py` suite using unittest discovery from its respective directory.
Tests and local saved-weight inference parity are separate from training. Default PR CI runs
scientific safeguards and commitment metadata checks; it does not claim full model
retraining or saved-weight inference without the companion binaries. The existing bounded15-minute workflow exposes an explicit manual
`full_research` option for fresh source intake and phase2/lead experiments.
No schedule, paid service or automatic production promotion is added.

## Research interpretation and next gates

The recency development winner is the best of the declared candidates, not a
global optimum. Confirmation MAE was essentially unchanged; RMSE improved.
The reused2025/26 audit is exploratory, and the refreshed mean model remains a
future challenger. Do not tune on the newly scored original prospective slate.

P(play) is evaluated on proven participation labels. FP source disagreements
quarantine FP without turning known participation into UNKNOWN. Unlabelled
opportunities remain UNKNOWN. NBA-stat reconstruction is not Sports.ru credited
FP. Per-game50/80/95 intervals cannot be added to obtain a weekly interval.

Before any site model release: further genuinely prospective quality, current
source/identity coverage, Questionable and cold-start reliability, longer-lead
and joint horizon coverage, end-to-end inference parity, and separate executable
KEEP/NOW/LATER utility evidence are still needed. Position-calendar colours need
validated incremental position signal; no invented historical labels or raw-FP
defence ranking are accepted.
