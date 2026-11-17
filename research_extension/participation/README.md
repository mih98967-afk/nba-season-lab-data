# P(play) and interval calibration: completed historical extension, 17 November 2026

## Result

Retain the existing calibrated CatBoost and existing conditional intervals. The three predeclared calibration changes failed their acceptance rules on reused historical confirmation. No model, frozen forecast, production forecast or website was replaced. These are negative results of actual executed experiments, not evidence that improvement is impossible.

The experiment used the saved near-game model bundle with SHA256 `70d288d753184916f354e3916016c7c6b0907da32bfcbf92ddcdcb22fb536c25`. All parameters in its trees and conditional FP model remained fixed. Probability correction used 1–23 January 2026, interval correction used 24 January–15 February 2026, and confirmation used 16 February onwards in the 2025/26 season. No 2026/27 outcomes were loaded, scored, fitted or selected in this extension. Because 2025/26 was examined in earlier work, this confirmation is historical and reused, not independent prospective evidence.

## Reproduction and denominator

The rebuilt historical feature frame exactly reproduces the archived confirmation figures: 13,997 known participation outcomes, 8,711 played outcomes and 623 UNKNOWN among 14,620 eligible opportunities. Original Brier loss is 0.09682914053062895 and log loss is 0.3063187230612362, matching the saved report.

The full model cohort still requires prior observable club membership within 45 days and at least five previous played games. In the historical 2025/26 frame, 2,704 ex-ante opportunities have fewer than five prior appearances; another 700 player-game rows have no qualifying prior membership. These are explicit exclusions, not evaluated cold starts. Of 41,410 eligible opportunities, 1,288 have UNKNOWN outcomes. This does not describe the full Sports.ru population.

## Participation correction

One fixed challenger added a ridge-regularized logit intercept per report/status group. No report, unsubmitted report, unresolved identity, not-listed, Available and named injury statuses remained distinct. Penalty strength was fixed at 20 before execution; no search or retuning followed the results.

| Metric, 13,997 known confirmation outcomes | Retained CatBoost | Status intercept |
| --- | ---: | ---: |
| Brier loss, lower is better | 0.09682914 | 0.09713555 |
| Log loss, lower is better | 0.30631872 | 0.30695931 |
| ECE, descriptive and bin-dependent | 0.01737672 | 0.01662074 |

The improvement in ECE does not outweigh deterioration in both proper probability scores. The paired date-cluster Brier gain is −0.00030641, with 95% bootstrap interval [−0.00072624; +0.00012117] over 52 game dates. The correction fails the declared acceptance rule. Under arbitrary labels for the 623 UNKNOWN cases, the overall Brier gain bound is [−0.00118125; +0.00064093]; unknowns have not been converted to DNP.

For Questionable specifically, 752 known opportunities include 362 played outcomes. Its Brier loss changes from 0.22725243 to 0.22856183. The correction shifts average P(play) from 46.35% to 51.47%, while observed participation is 48.14%. A single status-specific intercept is insufficient here.

## Conditional intervals

Two fixed challengers used status-level calibration: conservative symmetric widening and separate conservative lower/upper tail widening. Groups needed at least 60 played calibration cases. Sparse groups retained global offsets. Wider intervals were nested at 50/80/95%; no intervals were narrowed.

| 80% conditional interval, 8,711 played confirmation outcomes | Retained | Status symmetric | Status asymmetric |
| --- | ---: | ---: | ---: |
| Empirical coverage | 80.77% | 81.20% | 81.69% |
| Mean full width, FP | 20.6136 | 20.8330 | 21.1097 |
| Interval score, lower is better | 28.18037 | 28.19546 | 28.24142 |

Both changes increase width and worsen interval score. Date-cluster 95% paired interval-score gains are [−0.02836; −0.00036] for symmetric widening and [−0.10637; −0.01348] for asymmetric widening. Both fail acceptance.

Questionable coverage on these 362 played historical confirmation cases is 81.77% for all three methods. Its 80% interval score is 28.33830 for retained/symmetric and 28.34098 for asymmetric. The 121 played Questionable calibration cases do not justify substantial extra widening. This result does not resolve the already disclosed ~71.6% current-season coverage weakness: the historical evidence and current-season subgroup differ. Widening bands merely to match the known current-season result would be post-hoc tuning.

These results concern one-game conditional intervals. This extension does not improve or validate unconditional, 7/14/21/28-day summed, or roster-level intervals. Quantile endpoints must not be summed to create weekly coverage claims.

## Code reliability and source audit

Original package validation passed 97/97 files; original tests passed 41/41. New calibration and inference guards passed 14/14 tests. The original forecast file remains SHA256 `5aa81fa5db8f8a4e240cce3ec2477fad17626822c5eea2c02f39dab1b932a0cb`.

The audit found two bounded implementation issues and supplies guarded extension functions without changing preserved originals:

- The archived conformal calculation passes `ceil((n+1)*(1-alpha))/n` to NumPy's `method='higher'`. This can select one rank above the intended kth order statistic. It is conservative; it does not explain undercoverage. `exact_order_quantile` uses the exact rank and returns infinity when a sample cannot support a finite calibrated bound.
- The archived mixture probability range test does not explicitly reject NaN probabilities. `validate_probabilities`/`validate_quantiles` reject nonfinite values, inconsistent shapes, invalid levels and probability ranges. These guards are available for later inference integration; production behavior is unchanged.

Historical positive-minute boxscore rows have no missing required FP components and no duplicate player-game rows in all three saved seasons. Exact game/team inactive joining, conflict quarantine, strict earlier-date injury snapshots and distinct UNKNOWN handling were preserved. Final-source vintage limitations remain.

## Reproduce

Use the original pinned dependencies from `research_base/research/match_context/requirements.txt`. From the workspace root:

```bash
python3 -m unittest discover -s research_extension/participation -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 research_extension/participation/run_experiment.py --frame research_extension/common/feature_frame.pkl --base research_base --output research_extension/participation/results
```

The common historical frame is built by `research_extension/common/build_frame.py` from the unchanged research sources. `NBA_RESEARCH_BASE` can set the default base directory when using another checkout layout; an explicit `--base` overrides it. `run_experiment.py` rejects any frame containing season 2026/27 or later, verifies the original model hash, and creates a machine report, calibration parameters and row-level predictions. The parameters describe rejected research challengers, not a release candidate.

Main outputs: `results/CALIBRATION_REPORT.json`, `results/CALIBRATION_PARAMETERS.json`, `results/historical_calibration_predictions.csv.gz`, `HISTORICAL_COHORT_COVERAGE.json`, `SOURCE_QA.json`, `VALIDATION_CHECKPOINT.json`.
