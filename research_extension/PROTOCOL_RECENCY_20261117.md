# Incremental recency study, continuation of PR178

Declared before constructing candidate features or evaluating new candidates.
The prior matchup-aware Ridge is the anchor. Original sources, weights and the
1,741-record prospective commitment remain immutable. This is a new historical
development study using previously inspected seasons, not a virgin holdout.
No 2026/27 outcome, current-season replay file, or frozen prospective result is
used for choosing features, half-lives, hyperparameters or calibration.

## Data and target

Reuse the complete phase2 source reconstruction and feature contract: prior
observed team membership, at least five earlier played games, strictly earlier
NBA dates, explicit negatives and UNKNOWN separate. Conditional target is
reconstructed NBA FP when played. Actual target minutes and future boxscores
never enter target features. Eligibility restrictions and source-vintage limits
are retained and reported. Historical Sports.ru credited FP is not available.

## Fixed candidates

All candidates use the same imputation, standardization and Ridge alpha=500,
predicting a residual against last10. Existing fp3/5/10/25, min3/5/10/25, trends,
prior opponent and team context remain present.

1. Retained `ridge_context` feature recipe, equal training-row weights.
2. Add prior-game exponential summaries, half-lives 3, 8 and 20 played games.
3. Add calendar-day exponential summaries, half-lives 7, 21 and 60 days.
4. Add both sets of summaries.
5. Add only exponential minutes/role summaries from both sets.
6. Add only exponential fantasy-points-per-minute summaries from both sets.
7. Retained features, training-row recency weights with half-life 90 days.
8. Retained features, training-row recency weights with half-life 180 days.
9. Both feature sets plus training-row weights with half-life 180 days.

At most the last 100 earlier played games are used, matching the preserved
player history contract. Weights are nonnegative and normalized within player
history. Calendar gaps do not magically change a normalized player's mean;
days-since-play and effective count are carried separately. Training sample
weights are normalized to mean one so the effective Ridge penalty stays
comparable. Calendar weighting is relative to the latest training target date.
Each history produces weighted FP, minutes, sum(FP)/sum(minutes), effective
sample count and weighted deviations. No target result is observed until all
players' features for that NBA date have been emitted.

## Chronological selection and evaluation

- Development fold A: fit season 2023/24; score 2024/25 through 30 Nov 2024.
- Development fold B: fit through 30 Nov 2024; score Dec 2024.
- Select once by pooled development squared error / row count (RMSE).
  Tie tolerance 1e-8 favours fewer features, then the anchor.
- Lock the winning recipe and write the selection manifest before evaluating
  confirmation/audit. Refit anchor and selected candidate on dates through
  31 Dec 2024. Fit one mean bias intercept per model on 1–23 Jan 2025 only.
- Confirmation: 16 Feb 2025 through the end of 2024/25.
- Historical audit: complete 2025/26, explicitly previously exposed.
- Jan24–Feb15/2025 is left available for interval calibration and is not an
  additional candidate-selection window.

Report all development candidates, not only the winner. Later windows cannot
choose a second candidate if the selected one fails. Primary score is RMSE
because the point forecast is an expectation; also report MAE, signed bias,
date and player clustered paired bootstrap intervals (2,000 fixed-seed draws),
minutes/return/role-change groups, and descriptive daily ranking. Ranking is not
a budget/lock/transfer simulation. Report incremental gains against the retained
Ridge as well as against last10; a gain against last10 alone is insufficient.

## Release decision

The experiment may support a research candidate when pooled development RMSE
improves and confirmation does not reverse the improvement. Uncertainty and
the reused audit are disclosed. Production promotion remains false even after
a historical win. P(play), intervals and frozen future evaluation are separate;
this study cannot establish calibrated unconditional forecasts or fantasy
transfer utility by itself. No site, Firestore or owner-data mutation.
