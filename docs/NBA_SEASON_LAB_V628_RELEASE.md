# NBA Season Lab v6.28 candidate — exact model coverage in advice

Base: owner-published v6.27. PR #193 independently audits future-only research.

## Problem
Today previously proved freshness of the public forecast snapshot, but did not
show whether each actual player-game had a USABLE exact match in the newer
frozen model. Missing exact rows use the existing fallback calculation.
Fresh source alone never proves full player-game coverage.

## Change
- Count exact modeled vs fallback player-games for the current ten over seven
  days. If a verified best route exists, compare KEEP against that route on
  exactly the same window, using the lock T-30 before EACH game.
- Display the counts in Today -> Data reliability and a brief fallback warning
  beneath the quick proposed route (if applicable).
- Unknown/malformed inputs fail closed as n/d. Valid empty window is
  explicitly labeled "no games"; no imaginary confidence threshold added.
- Coverage is not model accuracy, calibrated uncertainty, true Sports.ru FP,
  independent proof of game participation, or actual expected cash benefit.

## Immutable
No changes to production FP, P(play), expected minutes, ranges, model weights,
optimizer scoring/ranking, quotas, prices, executed transfers, owner state,
private Firestore, journals, or future minutes preregistration.
Isolated complete Hosting candidate; published v6.27 untouched.

## QA
- Read-only deterministic oracle: 10 players, 2 games, exact T-30 ownership
  transitions, valid missing models, malformed/duplicate feeds fail closed.
- Existing Today UI VM, full JS/Python regressions, frozen source SHA parity
  and real-browser mobile/desktop fixture + public-snapshot tests.
- Complete Hosting ZIP only after postmerge main passes. Owner publishes
  separately; no Firebase deploy from CI.

## Scientific limitation
Coverage is descriptive, and a larger fraction does NOT imply better accuracy.
The economic benefit of KEEP/NOW/LATER remains unverified without authorized
personal Sports.ru prices, credits, true quota and a population-level p-play.
