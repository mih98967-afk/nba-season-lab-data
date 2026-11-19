# Phase 3: forecast lead-time validation (frozen before this experiment)

The phase-2 statistical champion is day-level pregame only. It must not be used
unchanged to claim calibrated forecasts made 7-28 days before each game.
Previous NBA-date box scores are treated as available on the issue morning;
original receipt/version timestamps are not reconstructed. This is a day-level
replay, not a proof of exact midnight or T-30 feed availability.

Generate separate immutable inputs at leads 0, 1, 3, 7, 14, 21, 28 calendar days.
For each issue date, all player history, club membership, team strengths and Elo
stop strictly before that issue date. Future scores, minutes, participation,
trades and team ratings never update the forecast. Target opponent/home and the
final known schedule supply planned rest and scheduled games before the target;
final-schedule vintage/rescheduling uncertainty remains a limitation.

Exact target-game injury reports and the club's next-game injury snapshot are
available only if published before issue-date midnight ET. Use the most recent
WHOLE TEAM snapshot, not a player's stale last mention. Future updates are
excluded. If no eligible report, mark missing instead of 'healthy'. All played,
explicit DNP and inactive labels still join the TARGET game by player/team ID.
UNKNOWN remains UNKNOWN, and club changes after issuance are not backfilled.

## Purged chronological selection/calibration
Train on END-2024 target games. Selection issues 1 October-30 November 2024,
with all targets on/before 28 December 2024. Refit chosen family on train plus
selection only. Thus every fitted label is known before calibration issuance.
Mean/probability calibration issues 29 December 2024-10 January 2025, whose
latest target is 7 February. Interval calibration issues 8-21 February 2025,
whose latest target is 21 March. Confirmation issues from 22 March onward in
END-2025. Historical audit END-2026 excludes issue dates before 1 July 2025.
No prediction in a calibration/evaluation block may predate the last target
outcome used to fit its upstream stage. This prevents multi-horizon boundary
leakage. Reused END-2026 is still a historical audit, never a pristine holdout.

## Fixed candidates and selection
FP: last10, previous v2, ridge form+lead, ridge full context+lead, LightGBM form,
full context, and context+reported health. Same fixed hyperparameters as phase2.
Select by mean development RMSE across the seven leads, not by 2025/26 score.
P(play): constant .87, personal explicit history, logistic and LightGBM history,
and each with reported health. Select by average development Brier across leads.
Refit only the selected families. Fit separate pcal sigmoid and mean intercept
per lead (fallback global if <100 labels). Conditional quantiles use LightGBM on
selected mean feature family. Calibrate conditional and zero-mixture prediction
intervals independently per lead using ical, not the mean/probability fit block.

Report each lead separately: coverage/UNKNOWN, mean MAE/RMSE/bias, Brier/log loss,
conditional 50/80/95% coverage/width, and corresponding no-play mixture intervals.
These are PER-GAME forecasts made in advance, not an aggregate-week distribution.
Do not sum per-game intervals. Repeated targets across issue dates are not
independent observations. No production promotion or economic claim.
