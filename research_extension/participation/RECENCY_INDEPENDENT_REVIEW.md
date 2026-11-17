# Independent recency review

Reviewed `research_extension/recency/features.py`, `run_study.py`, tests and preregistered historical protocol after the separate participation experiment. No modifications to recency candidate code were required.

## Passed checks

- All features use strictly earlier dates. Same-day and future outcomes are excluded by left-sided date search, not merely prior row order.
- DNP and UNKNOWN are excluded from conditional played-performance histories, rather than treated as zero FP.
- Baseline context features are enumerated before adding exponential features; target labels are excluded by the preserved metadata contract.
- Fold A trains 2023/24 and evaluates through November 2024; fold B trains through November 2024 and evaluates December 2024. The selected recipe uses pooled development RMSE.
- The selection manifest is written before confirmation/audit evaluation. The winning recipe is refitted only through December 2024; the additive bias correction uses January 1–23, 2025. Confirmation starts February 16, 2025.
- All candidates use the same Ridge penalty and normalization. Training-row weights are normalized to mean one. Exponential history weights and exponential training weights are separately compared.
- The confirmation/audit sequence does not select a second candidate and does not use 2026/27 labels.
- The anchor reproduces the saved phase2 selected-calibrated historical audit exactly: MAE 6.349007265360133, RMSE 8.168621902517087, calibration intercept 0.17240107596573. The common feature-frame SHA matches the archived value `d406041de5890933a0f420b91ae51d5388df49c53315182baec7f041e83c0b6b`.

## Interpretation limits

The selected day-weighted features improve confirmation RMSE, while confirmation MAE is effectively unchanged (6.4313657 → 6.4314603). Historical audit MAE improves by about 0.0171 FP, and signed bias worsens from +0.1820 to +0.2427 FP. The effect is incremental and small; it does not justify claims of a new level of accuracy or proven fantasy gains. Both historical seasons have prior project exposure.

The protocol's tie tolerance is implemented as rounded RMSE before comparing complexity. That can differ from an explicit absolute tolerance in near-boundary cases, but there is no material tie in this executed candidate set. No post-result candidate selection or source mutation was performed during this review.

This review does not extend to production inference, multi-game intervals, full-market participation or Sports.ru credit reconciliation.
