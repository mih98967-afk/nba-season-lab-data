# NBA Season Lab v6.24 — bounded Today decision evidence

**Base:** owner-published v6.23. This is an isolated next Hosting candidate, not a production deployment.
**Change boundary:** only `site/hosting_v624/app.js` and `today_brief.js` change runtime behavior. Historical v6.23 stays unchanged.

## Why
Previously a NOW route explicitly required a manual Sports.ru market check, while a
multi-slot or same-slot chain with its first move in the coming 30 minutes could
be presented as a generic model scenario without the same market gate. Also
the Today reasons mostly repeated generic comparisons instead of explaining
the verified best route's conditional FP difference against KEEP.

## Exactly what is new
- Pure read-only scenario explanations from the *already reconciled* best route:
  expected gain before the heuristic move reserve, move count, heuristic reserve,
  and score after reserve; KEEP explicitly means the best within a bounded search,
  never a global optimization proof.
- Any first move scheduled within 30 minutes in a chain/multi-slot scenario
  activates the owner-price-and-quota review, as for NOW.
- Explanation is **withheld** when public source freshness, roster, calendar,
  official risk, route identity/explanation verification or numerical quality fails.
- Do not use model net gain as actual Sports.ru earned points, and do not treat
  4 FP per move as a proven market/economic cost.

## Immutable computational/research boundary
`forecast_runtime.js`, `multi_planner.js`, `chain_planner.js`,
`transfer_guard.js`, `schedule_difficulty.js`, `decision_breakdown.js`,
`decision_journal.js`, `price_evidence.js`, `sports_reconciliation.js`,
`score_audit.js`, `official_status.js` and `budget_package.js` must remain
SHA-256 identical to published v6.23. No FP/P(play)/minute weights, intervals,
roster, actual transfers, prices, cash or Firestore changes.

The prospective minutes contract `docs/NBA_MINUTES_FUTURE_PREREG_20261120.json`
remains unchanged: future-only 21 Nov to 08 Dec, played-only, no DNP imputation,
`adopt_on_site=false`. The evidence is not production expected minutes.

## Acceptance and delivery
`.github/workflows/hosting-v624.yml`: frozen minutes protocol tests,
core-byte checks, all Node regressions, Playwright desktop/mobile fixture and
actual-snapshot tests, same-data frozen-weight inference SHA proof, live
expiration and public provenance checks. Produce the complete verified
`nba-season-lab-v6.24-hosting.zip` artifact **only after** all gates pass.

Never deploy automatically. Owner must publish to the existing Firebase
project `nba-season-lab`, and confirm deployment. After publication inspect
the actual owner profile separately: synthetic-browser QA cannot certify
personal Sports.ru transfer credit, prices or the true remaining quota.
