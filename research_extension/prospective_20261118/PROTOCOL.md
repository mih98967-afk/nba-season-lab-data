# Prospective evaluation on 18 November 2026

Protocol before computing 18-Nov outcome errors. No fitting, recalibration or
hyperparameter choice uses the newly revealed outcomes.

1. Verify immutable old forecast SHA `5aa81fa5db8f8a4e240cce3ec2477fad17626822c5eea2c02f39dab1b932a0cb`
   and paired forecast SHA `9b3cd732075d06c99ff0c3a30a2bd861ff606b0787c6de98d15302f93fa61ebb`.
2. Capture fresh NBA-derived SportsDataverse sources with source URL, actual
   retrieval timestamps, exact bytes/hash and internal coherence QA. Retain a
   fixed public-main commit snapshot for ESPN positive-minute and explicit DNP
   cross-checks. These are NBA-style reconstructed FP, not Sports.ru credits.
3. Resolve exact NBA player/game IDs, team/opponent and NBA date. A missing
   player/game remains UNKNOWN. Only positive minutes or explicit DNP/inactive
   supplies a label. Disagreements in participation quarantine participation;
   disagreement in exact FP quarantines FP but preserves agreed participation.
4. Frozen scheduled tipoff is immutable. If a later final-game feed changes UTC
   time for the same unambiguous calendar ID, team pair and ET date, record the
   revision separately. Require both original and revised time after issuance
   plus30 minutes; use no revision to change the frozen prediction or issue time.
5. Evaluate old1741 records by role and lead separately, with cumulative and
   newest-date views. The new334 records are167 matched pairs; assert identical
   P(play), quantiles and baselines before comparing the two conditional means.
6. Report conditional MAE/RMSE/bias on resolved played FP; unconditional metrics
   on resolved played/explicit zero FP; Brier/log loss on verified participation;
   conditional/unconditional50/80/95 coverage, width and interval score. Report
   every denominator, UNKNOWN, source conflict and unelapsed forecast.
7. Compare original last10/history baseline for preserved studies. This is NOT
   the exact deployed application's learnedMean baseline; a deployment gate
   must separately evaluate the actual runtime on preserved pregame inputs.
8. Paired errors use game-cluster bootstrap (4000 draws, seed20261118), retaining
   all player records within each sampled game. Report game count and warn that
   five games are a weak sample. Date-cluster inference is withheld below five
   distinct NBA dates; show date-specific point differences instead. Never use
   repeated model rows as extra independent observations.
9. Results are early prospective evidence. No claim of stable superiority,
   weekly-total interval calibration, Sports.ru credited benefit or global
   optimality follows from one or two dates. No auto promotion/deployment.
