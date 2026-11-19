# Phase 2 amendment, frozen before expanded-cohort results

Phase 1 was completed: ridge context won its declared selection, historical
played-only MAE 6.425 vs 6.623; incomplete participation labels prevented full
claims. This amendment is a follow-on experiment, NOT an untouched replication.

## New evidence
Join upstream game_rosters (the InactivePlayers result set, NOT a full active
roster) by exact game/person/team. Positive-minute conflict is quarantined as
UNKNOWN, never silently overwritten. Explicit inactive rows are negative NBA
participation labels, not medical diagnoses or official Sports.ru credits.
Rebuild all prior-state features and ex-ante opportunities from this expanded
archive. Preserve previous outputs; report denominators separately.

For official-derived injury reports, require an exact game match, strict player
identity method and matching team. Only report publication timestamps strictly
BEFORE 00:00 US/Eastern of game date are used in this experiment. Do not guess
AM/PM from the source's tipoff text. The last team report snapshot, not the last
player occurrence across older reports, determines the current reported status.
A missing listing is distinct from a confirmed 'Available'; no submitted team
report is a separate missing-source indicator. Raw reported Out status is a
feature and does not become an outcome label. Past published reports are a
retrospective archive, not proof we captured that version pre-lock at the time.

## Frozen expanded comparison
Keep phase-1 training/development/calibration/confirmation/audit date boundaries.
Keep all previous fixed FP candidates. Add ridge form+home/rest, ridge full
context+prior injury-report/teammate burden, and LightGBM full context+same injury
features. No tuning against 2025/26. Match group ablations separate form, rest,
opponent and known status; group importance is predictive, not causal.
Mean selection uses RMSE. Report MAE, bias, role subgroups and clustered paired
uncertainty, including comparisons against fixed v2 and same-family form model.

P(play) comparisons: fixed .87, smoothed observed history, logistic and LightGBM
with no official status, and corresponding models with as-of reported status.
Select by development Brier. Sigmoid calibration is fitted on pcal only.

Once selected, refit the chosen mean and participation family on train+selection
(year 2023/24 plus 2024/25 through December 31). Do not change its family based on
later scores. Mean bias correction is the mean pcal residual (intercept only).
Report both uncorrected and corrected means; final distribution uses this fixed
procedure. Quantile models use the selected feature family and train+selection.
Probability calibration uses January 1-23; interval calibration uses January
24-February 15 exclusively. Confirmation and reused 2025/26 historical audit
remain subsequent evaluation, not sources of parameter fitting.

## Distributions and checks
Provide conditional 50/80/95% intervals and a zero-at-no-play mixture that allows
negative played FP. Quantile interpolation respects the probability mass at zero;
never apply the shortcut 'q <= 1-p means zero' to distributions with negative FP.
Mixture interval calibration uses verified outcomes in ical. Report coverage,
width, interval score, return/injury/role subgroups and UNKNOWN sensitivity.
Do not label single-game intervals as weekly intervals or sum quantile endpoints.

All models remain research-only, with production adoption false. No auto
transfers, private data or Hosting writes. Retrospective gains do not establish
independent economic utility or universal optimality. Release complete code,
source hashes, tests and model card, including failures and exclusions.
