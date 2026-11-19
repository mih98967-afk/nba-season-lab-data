# Production inference package — 18 November 2026

This is a small CPU inference release for the existing NBA Season Lab. It reuses original fitted weights, independently hash checked. It does not train or overwrite any historical/frozen prediction. Model-quality and fantasy-economic acceptance remain separate; see RELEASE_ACCEPTANCE.md.

## Runtime

Use pinned `runtime_requirements.txt` for CPU inference; it includes pdfplumber0.11.9 for the optional current official PDF annotation/shadow. Historical training uses the preserved separate research requirements. The preserved scientific source code, `research_extension/recency/features.py`, `research_extension/prospective_20261118/derive_current_supplement.py`, its current-source validator, generic PDF mapper, and existing `src/official_*` modules must accompany this package. No binary files or separate downloadable weights are required: `models/*.b64` contains47 lossless trusted text chunks (~2.7MB total), reconstructed and SHA verified before Python inference.

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NBA_CODE_ROOT="$GITHUB_WORKSPACE" python research_extension/production_20261118/run_daily.py --work "$RUNNER_TEMP/nba-model-run" --cache "$RUNNER_TEMP/nba-model-history-cache" --snapshot-data data --base site/hosting_v620/data/base.json --out data/model_forecasts_v1.json --site-gate research_extension/production_20261118/SITE_DEFAULT_GATE.json
```

The work directory must be new for each run; completed snapshots are not silently overwritten. Cache the historical-source directory by the hash of HISTORICAL_SOURCE_MANIFEST.json. Never use the immutable research_base archive as a writable cache. Existing free Actions may run this after the public-data-sync workflow; no new cron/paid service is required. A failed primary source/identity/coherence check must leave the last successful public feed in place. The UI expires it by valid_until_utc. The optional newer PDF extension can fail independently: that leaves the unchanged base probability active and explicitly reports no fresh annotation, with no fabricated health/DNP.

Publication is an atomic file replacement after readiness, expiry and finite JSON checks. A fresh optional PDF does not reset the core model-history capture clock or its36-hour expiry. A failed source check leaves the previous public file unchanged, while the failed scientific result/report remains available for diagnosis in the run artifact.

For a prepared coherent snapshot, the inference-only invocation is:

```bash
python research_extension/production_20261118/export_feed.py --source /path/to/derived/source --capture /path/to/CAPTURE_SUMMARY.json --source-qa /path/to/SOURCE_QA.json --snapshot-data /path/to/public/data --base site/hosting_v620/data/base.json --out data/model_forecasts_v1.json --work /path/to/new/inference-work --bucket-report research_extension/production_20261118/BUCKET_ELIGIBILITY.json --site-gate research_extension/production_20261118/SITE_DEFAULT_GATE.json --injury-snapshot /path/to/FRESH_OFFICIAL_NBA_STATUS.json
```

Actual final generation UTC is stamped after inference. It is never replaced by an earlier source/asof time. Feature history stops before the issue NBA date. Inputs' exact hashes, actual source availability, UTC schedule and Moscow presentation dates are separate.

## What the UI consumes

`CONTRACT.md` specifies the versioned single JSON. The selected fields `p_play`, `mean_if_play`, `expected_fp`, conditional/unconditional50/80/95intervals are the unchanged base inference at supported leads or the explicitly labelled actual-day bucket adapter. `effective_p_play` and `effective_expected_fp` apply only a fresh, exact official OUT annotation; the zero interval is an explicit deterministic status overlay, not new calibration. `official_status` carries its evidence. Other fresh intraday status effects are `intraday_shadow`, marked timing_extension_not_validated and selected_for_production:false. DayEWMA is a separate mean-only `challenger`, also unselected.

For actual days18–20 and22–27, do not call provisional bucket bands calibrated80% intervals. For21/28days disclose limited/absent latest confirmation. Questionable subgroup uncertainty is explicitly flagged. Negative FP values are valid. Cold-start fallbacks have no calibrated range; contaminated catalog seed IDs are unavailable. Window expectations are arithmetic sums; window predictive intervals remain null.

## Reproduction and tests

```bash
python -m unittest discover -s research_extension/production_20261118 -p 'test_*.py' -v
```

All saved weights are included as verified text, so near/long weight parity tests run in CI instead of requiring the older companion artifact. This still does not claim full-retraining CI.

Before releasing a generated feed, run independent base-output parity and public-contract verification:

```bash
python research_extension/production_20261118/verify_release.py --feed data/model_forecasts_v1.json --research-feed "$RUNNER_TEMP/nba-model-run/inference/full_research_forecasts.json" --features "$RUNNER_TEMP/nba-model-run/inference/future_features.pkl" --snapshot-data data --base site/hosting_v620/data/base.json --out "$RUNNER_TEMP/nba-model-run/inference/RELEASE_QA.json"
```

The verifier independently assembles the original trusted weights and recomputes all supported scientific rows, including rows outside the UI catalog. It checks exact status identity/source/availability, immutable base probability/mean/intervals beneath the OUT overlay, source hashes, core expiry, shadow exclusion, fallback limits and arithmetic window expectations. Hosting must require a passing report whose exact feed SHA matches the packaged feed.

To reproduce the fixed intermediate-lead audit from the preserved sources (historical outcomes only):

```bash
python research_extension/production_20261118/audit_buckets.py --source /path/to/preserved/source --out /path/to/new/bucket-audit
```

`BUCKET_PROTOCOL.md` was written before execution. `BUCKET_ELIGIBILITY.json` contains all actual-day results without verbose reliability-bin arrays. The full audit/report/features remain in the reproducibility artifact. Eligibility applies only to an already exposed historical diagnostic, not a new holdout or proof of global optimality. No model choice is tuned on2026/27 outcomes.

## Publication scope

Publish Python, Markdown, model text chunks/manifests, the small parity fixture, frozen gate/evidence summaries and generated public model_forecasts_v1.json. Do not publish work directories, raw-source snapshots, large audit feature pickles, logs, private team/quote/ownership files or any private/ directory. The complete source/data checkpoint belongs in the existing scientific deliverable. Root integrates these files into the existing repository/release; this directory itself does not deploy Hosting.

## Refresh cadence and client size

The existing public-data and official-row workflows each run every4hours. This release adds no cron. A cheap stdlib fingerprint check runs before dependency installation or network intake; same NBA date, meaningful player/calendar content, official PDF hash, identity, seed and model/code hashes within12hours are skipped. One initial code push on main or an explicit force can refresh. Automatic refresh never fits a model. Pinned pip/historical source caches avoid repeat downloads. Verified Hosting and scientific run artifacts retain3days to bound storage; public forecast commits remain in repository history.

The live client feed contains catalog-mapped players only and omits all per-row challenger/intraday-shadow predictions. Complete scientific outputs, including unmapped NBA rows and shadow variants, remain in `inference/full_research_forecasts.json` inside the run artifact. A changed live projection is not achieved by altering any earlier frozen forecast.
