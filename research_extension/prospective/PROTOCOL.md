# Frozen 16 November forecasts: outcome scoring protocol

Protocol written 17 November 2026 before computing forecast error metrics.
The model bytes and predictions are immutable. This is an evaluation, not fitting,
hyperparameter selection, recalibration or production adoption.

1. Verify forecast SHA-256 `5aa81fa5db8f8a4e240cce3ec2477fad17626822c5eea2c02f39dab1b932a0cb`.
2. Use the snapshot at GitHub commit `11d89bb61b56460d8f1d7aaa4214c9a12b77503a`.
   Match game by frozen calendar ID, UTC start, and team pair, and player by a unique,
   high-confidence NBA-ID-to-catalog mapping. Require matching team and positive
   minutes for PLAYED. Only explicit ESPN didNotPlay evidence can label DNP;
   absence from boxscore, injury OUT, or failure to map remains UNKNOWN.
   A separately labelled supplementary cohort may add exact-game official NBA
   inactive/nonplay evidence from the current archived `official_nba_nonout_unknown`
   report, only with matching NBA player ID, source NBA game ID, UTC, team,
   verified game-day membership, source URL/hash and no conflict. This changes
   evaluation coverage only; it must never alter the original forecast or any
   model-training labels. Report the ESPN-only and supplementary cohorts apart.
3. Direct official NBA endpoint retrieval returned HTTP 403 in this environment.
   The available final outcomes are ESPN fallback/reconstructed NBA fantasy FP,
   not independently verified official NBA outcomes or Sports.ru credited FP.
4. Keep FUTURE separately. Report total records, distinct player-games, completed
   games, PLAYED, explicit DNP, UNKNOWN and identity/match conflicts. Do not count
   the interval challenger as extra independent player-games.
5. Baseline comes from the original archived `results_current/feature_frame.pkl`:
   last10 played FP and observed-history play probability; match exact NBA player,
   game, lead and issue date and require missing future targets. No refit.
6. Metrics separately by frozen model role: conditional MAE/RMSE/bias on PLAYED;
   Brier/log loss on known PLAYED/DNP; unconditional MAE on the same known cohort;
   conditional/unconditional interval coverage, width and interval score 50/80/95.
   Show missing-label lower/upper bounds for paired Brier gain. Do not claim
   full-population calibration when missing labels remain.
7. One completed NBA date is insufficient for date-cluster uncertainty or a
   general prospective superiority claim. Results are an early diagnostic only.
8. Preserve sources, returned Git blob SHA, local byte SHA, source update times
   and per-row evidence. Never overwrite the original commitment or forecasts.

Separate maintenance fix: the current official-inactive pipeline must accept
missing exact NBA game IDs as unresolved rows, retain them in its denominator,
make no guessed requests and keep all negative-label gates. This fix does not
change the scoring model or forecast cohort.
