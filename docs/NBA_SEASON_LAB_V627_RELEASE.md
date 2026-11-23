# NBA Season Lab v6.27 — honest owner checkpoint comparison

## Scope
Existing NBA Season Lab (no new project). Starting point: owner-confirmed v6.26 and merged PR #191.

The owner-only **Team → Official FP checkpoints** section now has a compact, collapsed
comparison of consecutive manually attested Sports.ru totals. It shows:
- the **observed change in Sports.ru FP** between two dated owner entries;
- change of **roster value + cash** and residual only when *both* dated entries
  have both numbers, otherwise **n/d** (no mixed-date arithmetic);
- how many executed moves have date-only/placeholder/unresolved clocks;
- explicitly missing independently verified per-player/per-game Sports.ru credits.

No NBA-derived number is labeled official; an equality of owner-entered changes
is not proof of player-game credits or exact update-time alignment.
The existing local-only JSON export and earlier 5/4/1 FP uncertainty are not
silently altered.

## Safety gates
- No changes to production FP, P(play), interval, minutes, roster, money, quota,
  transfer engines, private Firestore, decision journal, or personal backup.
- All computational modules remain byte-identical to v6.26.
- Future-only minutes preregistration (21 Nov–8 Dec 2026) is unchanged;
  `adopt_on_site=false`.
- Owner inputs/checkpoints stay in the browser; no network upload or GitHub data.
- v6.27 lives in an isolated Hosting source; no Firebase auto-deployment.

## Acceptance
- UI regression: single checkpoint is not a verified total; paired dates
  show correct delta and same-date capital arithmetic, including a zero residual;
  unknown exact ownership still prevents a proven Sports.ru per-game score.
- Previous complete Node regressions, full source hash checks, actual public
  browser QA across mobile/desktop, frozen model SHA parity and expiry.
- Full Hosting ZIP is produced only on successful merged-main CI and only while
  current public data pass all release gates. Owner deploys it manually.

## Remaining blocker
Authenticated, source-authorized Sports.ru per-player/game credits and exact
execution timestamps are not available. Without them, exact credited historical
reconciliation is not scientifically established, including historic unexplained
4/1 FP and prospective transfer economics.
