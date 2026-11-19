# Extended family challenge, fixed before its model fits

This is an explicitly exploratory follow-on to phase2, not a new untouched test.
Training and selection dates remain phase2's original boundaries. Candidate
selection uses only development RMSE (FP) or Brier (participation). Report all
candidates, including failures. No changes based on 2025/26 audit or 2026/27.

Conditional FP challengers: CatBoost RMSE depth4/6 with 600 iterations, 0.035
learning rate, L2=10; XGBoost square error depth3/5 with 400 trees, 0.035 learning
rate, minimum child weight30, L2=20; LightGBM 7/31 leaves with 600 iterations,
learning rate0.025, minimum child100, L2=20; a minutes-times-rate model using
LightGBM15, where rate training requires at least five actual minutes; a 50:50
ridge-context/CatBoost-depth4 blend. Features: full context, no current injury
features for FP. The phase2 ridge-context is the comparison anchor.

Participation challengers: CatBoost Logloss depth4/6 with600 trees and XGBoost
logistic depth3/5 with400 trees; same fixed regularization. Features: prior
history, rest and published injury information as in phase2. Compare phase2
LGBM injury anchor. Do not claim calibrated challenger probabilities before
separate calibration and subsequent evaluation. Freeze a selection manifest
before looking at current-season results.
