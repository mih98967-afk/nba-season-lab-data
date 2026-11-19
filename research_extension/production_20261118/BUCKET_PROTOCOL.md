# Frozen intermediate-lead eligibility audit — 18 November 2026

Declared before the run. No fitting or calibration. No 2026/27 target outcomes.

Use the preserved latest long bundle (SHA ee2fc118be2de60dd118cc5227ef519e699e3ed640b25a83816ba8e198140ea9). Historical audit rows have issue date >= 2026-03-22, target in season ending 2026, exact earlier-date source state and observed membership with >=5 earlier played games. This is an already exposed audit season, not a new independent holdout.

Input horizon is the **actual** integer 0…28 in every model feature. Fixed calibration bucket is the smallest saved lead >= actual horizon: 2→3,4–6→7,8–13→14,15–20→21,22–27→28. Use that bucket's frozen mean bias, sigmoid and interval offsets. No assumption that the upper bucket is mathematically conservative. Zero maps to original long-lead0 only for numerical parity checks; production near-game uses saved near bundle.

For each actual nonanchor day, accept the descriptive label `audited_lead_bucket` only if at least300 known participation cases and150 played cases; Brier and unconditional MAE no more than1% worse than the history-rate/last10 benchmark; and conditional/unconditional empirical coverage at each50/80/95 level at least nominal minus5 percentage points. These are operational eligibility thresholds, not a significance test or a proof of production superiority. Publish n/UNKNOWN, logloss, bias, MAE/RMSE, interval coverage/width/score for every actual day; no suppressing failures. No reselecting buckets after seeing results.

If a day fails or is unobservable, retain the model mean/P(play) as explicitly provisional and label the interval values `provisional_bucket_no_coverage_claim`; do not describe them as a calibrated80% predictive interval. Exact saved leads retain their own original calibration identity, with historical sample limitations disclosed. Aggregate windows never gain predictive intervals from per-game endpoints.

This does not approve optimizer/economic promotion, status-specific accuracy, NBA Cup schedule completeness or a global optimal model. New prospective evaluation remains required.
