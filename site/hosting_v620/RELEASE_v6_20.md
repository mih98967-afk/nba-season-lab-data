# NBA Season Lab v6.20 — Today / Transfers advice data-integrity gate

- No transfer advice until a structurally validated public NBA file is actually loaded from GitHub, a validated cache or a verified manual import. An embedded HTML seed is never automatically trusted just because its timestamp is recent.
- Only `live_sync` is eligible for transfer advice; partial/schedule-only/failed-sync sources are ineligible even when recently timestamped. The feed must be at most 24h old and not future-dated.
- Ten unique fantasy roster IDs, exact two per PG/SG/SF/PF/C, at most two per club and finite nonnegative cash are prerequisites for automatic advice, as is a complete calendar in the proposed decision window.
- Today clearly explains invalid roster/feed/calendar and hides unverified model FP. The Transfers page fails closed for Calculate, Apply to draft and Freeze journal when those prerequisites are not met. Manual history reconciliation and research tools remain accessible.
- Missing official injury update is shown as uncertainty, not a claim that players are healthy. No change to forecast weights, Sports.ru rules, Firebase, transfers or price provenance.
- Full Hosting candidate only. Publication to the existing site remains a separate owner action. Smoke and pure tests are offline/synthetic and are not proof of real Sports.ru transfer benefit.

## Unpublished source safety amendment (2026-11-09)
- Extend the same fresh public-feed, validated roster/cash, and complete calendar preflight to the previously unguarded Chain Planner and Budget Package. Block both calculation and subsequent draft application when data are ineligible; keep manual data/history browsing available.
- Chain/budget panels hide cached FP scenarios when readiness is lost, show a concrete blocked reason and disable automatic search. Fresh official injury report loading invalidates previously generated scenarios, without altering forecast probabilities or claiming that absence of OUT proves health.
- `test_today_advice_ui_vm.cjs` exercises all three automatic planner action handlers under unverified feed.
- No change to model weights, scoring, source collection, private Firebase or Sports.ru transactions. Still a source-only candidate; the site is not deployed by this change.


## Post-publication correction candidate — 10 November 2026
- Read-only historical FP totals now require a verified `live_sync` NBA feed and a complete, replayable 10-player ownership lineage (initial snapshot, transfer timestamps and roster consistency). An embedded seed or incomplete ledger cannot appear as a trustworthy numeric total.
- User-attested transfer timestamps remain unverified Sports.ru history; even successfully replayed ESPN FP is not the credited Sports.ru total.
- Team tile displays `н/д` with a reason when ownership/source is incomplete. No numbers guessed; no roster, history, Firestore, scoring model or Sports.ru mutations.
- Extended pure and UI-VM regression tests. Existing Hosting is untouched until a separate owner deploy.

## Owner-attested NOW readiness — follow-up (2026-11-10)
- The existing multi-slot optimizer remains a **hypothetical scenario search** using estimated price fallback; it must not be mistaken for a verified Sports.ru order.
- Today distinguishes a modelled NOW route from a route with manually rechecked pair prices, cash and actual remaining moves in a fresh, local, non-imported snapshot (up to 1 hour). No future quote or week-boundary assumption is ever certified.
- A focused link opens the existing manual price-proof form for the first proposed OUT/IN pair; receipts stay local and require an explicit owner checkbox. Nothing is sent to Firebase.
- Multi-route summary labels readiness, and the budget planner's apparent quota is explicitly an estimate from recorded transactions. All calls and fallback scenarios remain read-only; no pricing model, fantasy FP, transfer or database mutation.
