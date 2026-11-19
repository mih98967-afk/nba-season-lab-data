# NBA Season Lab v6.23: minutes evidence and optimizer hierarchy

**State:** prepublication candidate only. The user has published v6.22.

## Read-only minutes acceptance

The independently archived `current_season_minutes_shadow_research.json` includes genuinely issued prospective predictions of minutes *if the player takes the court*. The original frozen 2025/26 prior and a challenger with current-season same-team form are compared on **identical verified played cases** only. The frozen issue, individual T-30 lock, first-seen current inputs and postgame timestamps must all precede/follow their targets in the correct order. Missing rows are UNKNOWN, not DNP or zero minutes.

Run `python scripts/audit_minutes_readiness_v623.py --data-root data --output minutes-audit-v623.json`. It refuses source hash drift and nonchronological observations. MAE improvement is calculated paired on known played cases, with ET-date-cluster exploratory uncertainty, not independent-player-row confidence intervals.

**Important:** `promote_as_expected_minutes_on_site=false` by construction. Verified played-only results, even if improved, are insufficient to certify representative NBA player×game coverage, reliable minutes intervals, winning transfer policies or a fresh independent scientific selection sample. This is a protocol/readiness audit, not a newly trained or approved model.

## Planner refinement

The existing Planner/Optimizer has kept all original calculations and protected KEEP/NOW/LATER behavior. Only visual hierarchy changes: one primary calculation control, prominent best decision, shorter secondary statistics, warm neutral colors; details under user-requested disclosure. The live site and `site/hosting_v622` are unchanged. Private roster, cash, executed transfers, locked prices and Firestore are never used in CI.

## Release boundary

The v6.23 source is copied from published v6.22 to avoid altering production. A merge does **not** authorize deployment; full ZIP requires pinned source manifest, real-data browser acceptance and model parity from a coherent fresh evidence set. No Firebase deployment, paid actions, scheduler or new repo is introduced.

## Reproducible first real results (19 November 2026)

Run [44575864166](https://github.com/mih98967-afk/nba-season-lab-data/actions/runs/44575864166) passed. The immutable shadow snapshot contains 1,688 original forecasts, 1,337 independently verified positive-minute outcomes, 94 literal DNP excluded from conditional errors, 180 UNKNOWN retained unscored, and 77 awaiting checks. The covered outcomes span 106 distinct NBA games and 16 NBA ET dates.

On the same selected played observations, prior-season baseline MAE=6.3928 minutes, contemporaneous-form research challenger MAE=5.2233 minutes: absolute improvement 1.1695 minutes, 18.29% of baseline MAE. Predicted-minus-actual bias shifts from +0.9442 to +0.3365 minutes. Resampling **ET dates**, not player-game rows, yields an exploratory paired improvement interval [0.9902, 1.3280] minutes. This is not a predeclared independent confirmatory selection gate.

The separate `conditional_minutes_robustness_research.json` has a different issuance cohort and was **not pooled**. The QA explicitly labels `separate_robustness_report_same_cohort=false`.

**Decision:** Do not promote a personal expected-minutes claim or change the deployed FP model. The gains are played-only, selected, and researched after current-season observations; genuine independent model-selection evidence and representative scheduled-player denominator remain unproven. Do not turn UNKNOWN into 0 minutes.
