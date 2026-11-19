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
