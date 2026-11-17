# Match-specific distribution research protocol, 16 November 2026

This is an isolated research extension after PR176. No Hosting, private account,
Firestore, production forecast or transfer automation changes.

## Scope and provenance
Use all identifiable NBA players from the existing SportsDataverse upstream
2023/24, 2024/25 and 2025/26 regular-season box scores and final schedules.
Reconstruct NBA-stat FP with the repository's frozen scoring formula; these are
NOT verified Sports.ru credited FP. Do not subset to today's fantasy catalog.
Record hashes and source capture times. Source is an archive retrieved now, not
proof of historical publication timestamps or original schedule versions.

Participation positives require positive minutes. Negatives require an explicit
DNP/DND/NWT comment in the exact player-game row with no positive minutes.
Missing rows, missing minutes without such a comment, and uncertain membership
remain UNKNOWN. Ex-ante opportunities are formed from previously observed club
membership (within 45 days), never future appearance or final-season rosters.
This is an observable-membership cohort, NOT all registered fantasy players.

## Leakage safeguards
Compute features at the start of NBA game date; include only strictly earlier
dates. No current-game minutes, starting position, comment, score, result or
teammate participation enter the features. Prior comments are allowed. Opponent
pace/defense features use only previous completed games. Same-day results are
excluded conservatively. Team membership changes and long gaps are audited.
No random row train/test split. No ID/name feature that memorizes future ability.

## Fixed comparisons before this run's results
Train: 2023/24. Development selection: 2024/25 through 31 December 2024.
Interval and probability calibration: 1 January to 15 February 2025.
Development confirmation: 16 February 2025 onward. Freeze candidate on selection.
Historical audit: 2025/26, already examined in previous project research, hence
NOT a pristine untouched holdout. A best score there cannot establish a globally
best model or replace future frozen-as-of evaluation.

FP candidates: last10 baseline; previous fixed v2; ridge residual player-form;
ridge residual player+context; fixed small LightGBM squared-loss residual models
(player-only, player+home/rest, player+opponent/team context); fixed deeper context
variant; equal-weight player/context blend. Mean FP selection by development RMSE,
with MAE, signed bias, daily ranking, high-minute subgroups and paired game-date
and player cluster bootstrap reported. Context adds value only if it beats a
matched no-context candidate; unequal match predictions are not an objective.

Participation candidates: fixed 0.87; smoothed prior explicit-observation rate;
regularized logistic; fixed small LightGBM; calibrated predictions fit on the
separate calibration block. Report Brier, log loss, reliability, selection/missing
label coverage, and UNKNOWN sensitivity bounds. Do not claim population-level
p(play) calibration from verified-only scores.

Intervals: conditional 50/80/95% quantiles, separate mean/median. Compare training
residual baseline with held-out-calibrated LightGBM quantiles. Split-conformal
correction uses only the calibration block; time dependence means coverage is
empirical, not a guaranteed probability for each player. Report actual coverage,
width, interval score, and role/subgroup coverage. DNP mixture evaluated only on
verified outcomes with the cohort caveat. Negative FP are valid. Do not sum
per-game quantile endpoints to claim a calibrated multi-game interval.

## Adoption
No automatic adoption. At minimum retain gains on confirmation and historical
audit, check uncertainty and calibration, compare current-season saved-as-of
observations, and verify actual economic usefulness before production promotion.
Unknown availability, missing schedule and unverified Sports.ru credits remain
explicit blockers. This run may deliver a trained, reproducible research winner,
not a claim that the entire production reliability problem has been solved.
