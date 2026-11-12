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

## PR #151 candidate — finish main product route (10 November 2026)
- Make the 7-day Today horizon independent of the 21-day calendar, which can be incomplete across undetermined NBA Cup fixtures. Never extrapolate missing games or turn them into zero FP.
- Add strict per-player/per-game NBA Injury Report linkage. Only an exactly verified, fresh official OUT forces participation to zero for **that matching game**; stale, post-lock, wrong-team and other-game statuses cannot. QUESTIONABLE/PROBABLE and Telegram signals do not invent probabilities.
- At Today open, automatically calculate one bounded, read-only 7-day KEEP/NOW/LATER comparison, if and only if live source, roster, cash and 7-day schedule pass preflight. Results expire in 30 minutes and are invalidated on data changes. No automatic Sports.ru transactions.
- Display the best modelled route and up to two player pairs on Today; link to its detailed planner without unnecessary recomputation. Route scores still use estimated prices and a hypothetical transfer opportunity cost, not independently validated Sports.ru gains.
- Restore a clear user surface: three primary transfer tasks, with advanced chains/budget hidden in optional tools. Show caution for players with few games in 2025/26 without modifying forecasts. Add small visual interaction and accessible reduced-motion styles.
- No forecast weight refit, model promotion, account changes, paid services, new repo or Firebase project. Personal real-profile and deployment QA still required.

## Private Sports.ru journal date-only safety (PR #155 candidate, 11.11.2026)
- Personal Sports.ru transfer journal and Firebase backup can be reconciled privately. **No owner roster, prices, transactions, or private backup are checked into this public Hosting release**.
- A restored operation may carry `timePrecision: "date_only"`, `epochIsPlaceholder: true` and the owner-provided game date. Its `epoch` exists solely for legacy roster/planner sequence ordering, **not** as proof of the exact transaction time, Monday quota reset or T-30 possession.
- `NBAScoreAudit` refuses an exact NBA boxscore FP total when any completed transfer has an explicitly unverified timestamp; this does not treat an unknown FP as zero.
- Today's and Team's quota estimates display `n/d` if date-only transactions occurred during the relevant 14-day boundary-sensitive interval. Sports.ru owner-entered quota remains read-only evidence, not a backdated derived fact.
- KEEP/NOW/LATER with unknown historical quota stays a conditional model scenario requiring owner verification, including multi-step routes. Transfer guard exposes the uncertainty, never executes transfers.
- On JSON restore, the confirmation dialog explicitly warns about date-only clocks. Unrelated player data, scoring formula, predictions, injury model, current public source collector, Firestore schema v5, Hosting project and Firebase Spark remain unchanged.
- Tests added for synthetic date-only FP, conditional market scenario, quota reconciliation and draft guard. No real Sports.ru total is claimed.

## PR #158 candidate: observed played-FP range for date-only owner transfer clocks
- Pure read-only `ownership_bounds.js` exhaustively enumerates legal within-date orders and pre-lock timing scenarios (with cash/roster conservation) for up to four owner-attested transfers on one Moscow date. It never claims to recover true clocks.
- When date-only transfers prevent an exact personal attribution, the Team page displays the min–max of **observed played-only NBA boxscore FP**, grouped by the six relevant transaction dates. Exact Sports.ru credited FP and DNP remain explicitly unverified.
- Fresh independently verified public live data are mandatory (age <= 24h). A missing/duplicate/nonfinite played row, mixed unsupported clock evidence, or impossible ledger fails closed.
- No private Pythos backup, roster, market values, or transfer journal is committed in public source. No scoring model, player availability, Firebase state, or Sports.ru action changed.
