# Per-game inference feed v1 — release 18 November 2026

Output target: `data/model_forecasts_v1.json`. One immutable as-of computation, no fitting.

Top-level keys: `schema_version: 1`, `kind: "nba_per_game_model_forecasts"`, `issued_at_utc`,
`asof_date_et`, `source_capture_completed_at_utc`, `source_manifest_sha256`, `model_manifest_sha256`,
`valid_until_utc`, `status` (`ready` or `stale_inputs`), `model_policy`, `source_quality`,
`coverage`, `rows`, `windows`. JSON contains finite numbers or null, never NaN.

`core_source_capture_completed_at_utc` records the intake clock for the model-history inputs. `source_capture_completed_at_utc` may be later if an optional current PDF was captured later. The separate core clock limits freshness/expiry; the PDF cannot make stale core inputs current. The exporter retains diagnostic stale results in its work directory and atomically replaces the public output only for ready, unexpired finite results.

Each `rows` object uses:

- `player_id`: Sports.ru catalog ID (`n002`) or null if identity unsupported; `nba_id`: exact NBA person ID or null.
- `game_id`: public app schedule ID; `nba_game_id`: exact NBA schedule ID or null; `team`, `opponent`, `home`.
- `game_utc`, `lock_utc` (T−30), `game_date_et`, `game_date_msk`, `actual_horizon_days`.
- `model_id`: `near_latest`, `long_latest`, `legacy_seed_fallback`, or `unavailable`.
- `support`: `exact_lead`, `provisional_lead_bucket`, `audited_lead_bucket`, `cold_start_fallback`, `identity_fallback`, `missing_features_fallback`, or `unavailable`.
- `calibration_lead_days`: 0/1/3/7/14/21/28 for saved models; actual horizon remains separate.
- `p_play`, `mean_if_play`, `expected_fp`: E(FP with zero for explicit nonparticipation) = P(play) × E(FP | plays). Negative FP are valid.
- `conditional_intervals` and `unconditional_intervals`: objects with keys `50`, `80`, `95`; each value `[lo, hi]`. Null if unsupported. These are **predictive**, not confidence intervals for the mean.
- `interval_status`: `historically_calibrated_exact_lead`, `historically_audited_bucket`, `provisional_bucket_no_coverage_claim`, or `unavailable_fallback`.
- `injury_status_at_feature_cutoff`: exact snapshot status; `history_n`, `recent_minutes`.
- `reasons`: 2–3 concrete human-readable reasons; `warnings`: explicit limitations.
- `challenger`: optional `{model_id: "day_ewma_shadow", mean_if_play, expected_fp, selected_for_production: false}` for near-game rows only. P(play) and intervals remain the original model's; this is a mean-only comparison.

Stale source captures (>36h), stale completed-game content (>3 NBA dates), stale UTC schedule (>72h), missing source time, identity conflict, missing finite model inputs, and passed T−30 cannot quietly become a new model recommendation. `eligible_for_decision` is false for stale/locked/unavailable rows. A current feed must still be invalidated in the UI after its `valid_until_utc`; old values may remain visible with a stale label.

`windows` contains player windows 7/14/21/28 days. Each has `expected_fp`, `conditional_sum_if_all_play`, `expected_games`, `scheduled_games`, `covered_games`, `fallback_games`, `schedule_complete`, `unavailable_games`, and `predictive_intervals: null`. `expected_fp` is a sum of per-game expectations; `conditional_sum_if_all_play` is a scenario, not a forecast of aggregate conditional distribution. Never sum interval endpoints. If any game is unavailable, full-window `expected_fp` is null and `known_games_expected_fp` gives the labelled partial sum. Calendar-known gaps are flagged; a zero-game window cannot be treated as complete when the schedule is incomplete.

This feed is advisory. `model_policy.optimizer_policy_validated: false`, `model_policy.economic_gain_proven: false` until the explicit deployment/economic gates are satisfied. The original model is not selected over the current deployed site's actual algorithm merely because it beats last10. Recency is a shadow challenger, not selected on current-season outcomes.

## Accepted original-model default and official status extension

The reviewed original-model gate now permits `model_policy.site_default:true`. `optimizer_policy_validated:false` and `economic_gain_proven:false` remain mandatory; `forecast_inputs_for_advisory_comparisons:true` refers only to existing advisory calculations.

Selected base fields remain unchanged. Per row, `official_status` carries a fresh exact report, `effective_p_play`/`effective_expected_fp` and `effective_unconditional_intervals` apply only the established deterministic OUT overlay. These effective zero bounds are status-policy outputs, not newly calibrated probabilities. `intraday_shadow` uses the newer exact status through the saved model but is explicitly `timing_extension_not_validated:true` and `selected_for_production:false`; it must not replace base fields. Other status updates are visible annotations. `fresh_official_snapshot_ready_at_utc` records normalized-artifact readiness separately from the raw source capture bound.

`source_manifest_sha256` hashes the canonical effective input manifest (archive, historical manifest, UTC schedule, live feed, identity, seed, optional current official artifact, and generation code hashes). The underlying current-archive manifest hash stays in `source_quality.current_manifest_sha256`. Final `issued_at_utc` is stamped from the actual clock after model inference.
