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

## Private prospective evidence export — PR #165 candidate (15 November 2026)
- On **Team → Sports.ru FP checkpoints**, an optional **full private economic-evidence packet** now exports the local FP reconciliation together with the independently stored frozen KEEP/NOW/LATER decision journal and manual Sports.ru quote receipts. The old FP-only button is unchanged.
- Consent names all included private local stores and warns that the quotes/journal could include entries for more than one team in that browser. No automatic upload or Firebase/Firestore write.
- For each previously frozen selected route, an **as-of descriptive owner-quote match** may be provided only when a same-pair, same-price receipt predates the capture by at most one hour and the receipt archive was never restored. A match does **not** authenticate Sports.ru price publication, future prices, locks, quota, ownership or realized FP. All routes remain `executable_transfer_plan_proven=false`, `realized_keep_now_later_gain_proven=false`.
- A corrupted local journal or failed source verification aborts the **full** export instead of silently producing a misleading incomplete research packet. The prior FP-only download remains available.
- Synthetic offline tests: no Firestore/network changes, price/evidence provenance, and corrupt-archive rejection. Real owner profile and official credited player-game outcomes remain unverified. Hosting publish requires the owner action.


## Daily decision integrity — PR #166 candidate (15 November 2026)
- Today computes the next actionable T-30m lock across all eligible games in the 7-day window, not just the four visible fixtures. The involved roster players and Moscow time are shown; Sports.ru remains the authority.
- Today, Team and Transfers explicitly show `н/д` for unprovable current quota when recent historical transfers have `date_only`/placeholder epochs. Shortlist does not invent available moves.
- Reusing a 7-day recommendation or opening a modelled market pair now requires an unchanged roster/source signature, successful public-data preflight, <=30 minute calculation age and a route whose planned start/moves have not elapsed. Expired scenarios must be recalculated; previous estimates cannot become current purchase prices.
- Existing privacy/provenance restrictions, forecast model and scoring retained. Changes are read-only, no automatic Sports.ru transfer, Firebase/Firestore/profile write or new resource. Local VM and pure regression tests cover unknown quotas, late-listed next locks and stale plans.


## PR #167 — explicit prospective decision capture from Today (2026-11-15)

- Owner-private report received at 2026-11-15T13:54:43Z: **0 frozen decision entries** and **0 manual price receipts**. The 10 transfer-history rows have only Sports.ru Moscow dates and placeholder epochs. It is invalid to label these historical moves as prospective KEEP/NOW/LATER validations.
- A new small, optional **Проверить полезность советов** section on **Сегодня** makes prospective research visible without displacing the primary daily decision. Two explicit choices: **Зафиксировать совет модели** and, when relevant, **Мой выбор — KEEP**. Both freeze all current KEEP/NOW/LATER alternatives plus the selected index, never invent Sports.ru execution.
- Only enabled when 7-day public preflight, current unchanged roster/signature, fresh plan (<30m), valid future start, consistent FP explanations and readable private local journal all pass. If not, shows why no snapshot can be recorded. No automatic storage just by opening Today; explicit consent remains mandatory.
- A private packet download is available from Today, reusing the existing opt-in economic export including owner-confirmed checkpoints. No personal records are added to GitHub, Firestore, or telemetry, and no live transfers are made.
- Preserves the same local v1 journal schema, the historical score discrepancy's bounded status, and the frozen 7/14/21/28-day plan evidence; user choice does not imply Sports.ru verification or a causal model effect. Repeated captures are not independent matches.
- Tests: full existing offline suite and a synthetic UI-VM asserting disabled capture without preflight, positive KEEP choice with all alternatives, lack of profile/Firestore mutation, and stale-route rejection.
- **Research interpretation:** still no proven real KEEP/NOW/LATER gain. DNP/credits, execution-time prices/locks and actual counterpart are missing. No new forecast model, retrospective forecast, score overwrite, or automatic trade.


## PR #168 candidate - frozen as-of game ledger and conservative outcome coverage

- Evidence received on 15 Nov: 10 date-only historical transfers, 0 prospective decisions, 0 manual price receipts. No retrospective backfilled predictions.
- Future opt-in KEEP/NOW/LATER entries now carry a LOCAL immutable-at-click snapshot of the specific game IDs/tipoff UTC times, observed NBA club for involved players, the previous unexecuted draft, and calendar publication timestamp. All parties remain owner/device observed, not independent Sports.ru proof. The existing v1 journal remains backwards-readable: old entries without a slate are explicitly marked unevaluable.
- A pure, non-mutating outcome-coverage auditor checks the same frozen matchups against later public NBA game/played rows. Every scheduled player-game without a confirmed played FP remains UNKNOWN, not DNP or zero. Changed NBA game times, missing results, duplicate rows and incomplete coverage fail closed. Even when all played rows exist, reported numbers are NBA-only and **real Sports.ru FP/gain remains null**.
- The explicit owner-private economic JSON export now includes only the NBA game/row observations relevant to frozen future slates plus a descriptive coverage report. Neither private state nor these observations are written to public GitHub, Firestore, or any API by this code.
- Today shows one low-noise line for the latest local frozen decision: pending horizon / partial NBA coverage / old slate / schedule changed / no credited Sports.ru proof. No forecast model, score weights, real moves, account profile, or Firebase resource has changed.
- Consent now explicitly mentions the frozen calendar, clubs and local draft. The 7/14/21/28-day options and original prospective models remain unchanged. A current verified public calendar and a readable journal are prerequisites for new as-of slate capture.
- Tests added: immutable slate capture, validation, old-schema compatibility, partial DNP unknown, pending horizon, complete NBA-only still not Sports.ru, changed schedule, private export, Today synthetic browser VM. SHA manifest must retain its 43-file contract. Owner publication remains a separate Hosting deploy.

**Research gate remains BLOCKED for actual economic value.** Missing official per-player credited FP, game-day DNP/outcomes, independently observed execution quotes and actual performed Sports.ru transfers. Observed source is not an authoritative fantasy ledger.


## PR #169 - audit replay correctness under transfers, club changes and exact locks (15 Nov 2026)

- The frozen prospective journal remains opt-in, local-only and backwards compatible; capture behavior, projection model, prices, Firebase, profile, and actual Sports.ru transfers are not altered.
- During **post-horizon NBA-only coverage**, a played row for a player whose NBA team no longer matches the as-of frozen club (or has no verifiable team) now stops the hypothetical comparison with `PLAYER_CLUB_TENURE_CONFLICT`. This is preferable to falsely crediting points for an unaudited player tenure.
- Modelled multi-step transfers must form an internally coherent possession path. Selling someone already sold or buying someone already owned now reports `UNVERIFIED_OWNERSHIP_PATH`; no silently skipped transfer can produce a misleading complete outcome.
- The T-minus-30-minute fantasy lock is **exclusive** for any hypothetical purchase exactly on that boundary. This does not prove actual Sports.ru execution time; planned prices and prior drafts remain unverified.
- `Today` displays short explanations for these blocked comparisons and does not imply proven gain. If a finished horizon contains zero observed completed games, the message says results are not available rather than presenting an unhelpful `0/0` coverage ratio.
- Regression tests include club mismatch, missing NBA club, duplicate ownership, invalid sequential transfers, exact T-30 boundary, unchanged legacy journal, partial/DNP-unknown and NBA-only-not-official results. Full existing suite passes offline; SHA manifest and PR CI must also pass.
- **No adoption decision:** observed NBA rows are not official per-player Sports.ru credited FP, no independent execution-time quotes/locks/quota, and no validated real KEEP/NOW/LATER gain. Research models remain unpromoted.


## PR #170 — precise date-only weekly quota and honest historical timestamps (15 November 2026)

**Problem:** The older frontend treated any `date_only` / `epochIsPlaceholder` transfer within the previous 14 days as permanently ambiguous. It also displayed its synthetic `epoch` as a real HH:mm timestamp in the most recent completed transfers. The historical case has ten owner-entered transfers with exact **Moscow dates** but unknown clock hours. The same ambiguity is not relevant to every future weekly reset.

**Safe fix:** Infer current-week membership from the entire [Moscow 00:00, next Moscow 00:00) interval of the explicit `sportsRuDateMoscow` ONLY. For each candidate reset (Monday 15:00 and Monday 00:00), compare week membership at both possible endpoints (clamped to the current observation time). If membership differs for either hypothesis, both results remain `н/д`. If neither endpoint belongs to the current week, the historical date does not contaminate its quota, even if it crossed a *past* reset. Never use placeholder epoch to decide an owner's week. Missing/malformed/future date or invalid actual timestamp fails closed. All counts remain private-history estimates, NOT verified actual Sports.ru remaining transfers.

**UX:** The last completed operations on Transfers now display Moscow `DD.MM.YYYY · часы неизвестны`, never placeholder HH:mm. If their day was not explicitly stored, the UI says the date/time are unverified. Shortlist and budget simulations evaluate the planned week independently of today's uncertainty and display `н/д` when a relevant date crosses the current week's reset. Scenario search remains possible, but its quota is not represented as official when uncertain.

**Measured, private-only fixture** (no private data in GitHub): ten dated operations through 9 November were indeterminate for the current reset before 16 November 15:00 MSK, but all unambiguously belong to *previous* weeks after that boundary; the next week's observed journal count is 0 for both hypotheses, still not official Sports.ru evidence. Full prior and new test suites pass locally: Monday before/after reset, old reset no longer in current week, same-day clipping, date format/future rejection, placeholder ignored, and rendered history date label. No model/FP changes, no user profile write, no auto transfers, no new Firebase resources.

## PR #172 — read-only readiness ledger for frozen decisions (15 Nov 2026)
- One private, on-device overview of **all** opt-in KEEP/NOW/LATER decision snapshots, shared by Today and Transfers. Shows pending horizons, partial or complete **NBA-only** played-row coverage, source uncertainty, legacy records and blocked replay; latest five decisions are collapsed by default.
- Time-overlapping prediction horizons form descriptive groups and cannot be treated as independent winning tests. Even non-overlapping windows do not prove statistical independence. The ledger cannot certify Sports.ru credited player-game FP, exact execution, real net transfer gains or forecast advantage.
- Added three pure regressions and one synthetic UI regression; zero changes to owner profile, Firestore, scoring, quotas, forecast model or transfer execution. Full hosting bundle and exact SHA manifest must pass CI. User publishes only after CI success.

## PR173 — minimal Sports.ru credit evidence checklist, private and conditional
- Keep and alternative routes are replayed on their frozen game IDs using the same T−30 ownership cutoff. Only player-game exposures where ownership differs from KEEP require a Sports.ru credited result; unchanged exposures cancel. Avoid asking for the entire ten-player match history.
- For every stored prospective snapshot, a read-only checklist exports missing official FP, validated DNP/participation, match club tenure and real execution/quotes/quota requirements. All credit slots are null and explicitly unverified; neither ESPN played rows nor reconstructed prices are accepted as official Sports.ru outcomes.
- On Today/Transfers the latest private snapshot shows differential credit count and a deliberate, consented local JSON download; the list is not posted to GitHub, Firebase or Firestore.
- Missing/legacy frozen schedule or impossible ownership path yields an explicit blocked state rather than a fabricated FP difference. Captured dates/scenarios are not independent evaluations and do not prove value, irrespective of number of rows.
- Maintains 44 release assets, stable journal schema, full manifest, test-suite and verified offline ZIP. No model change, no automatic transfer, no account mutation.
