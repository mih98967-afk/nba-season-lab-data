# NBA Season Lab v6.18 — Today-first UX candidate

Owner decisions: primary question 'Do I need a transfer today?', short and long windows, balanced risk, 2–3 reasons, desktop primary, player fantasy role/statistics rather than biographies.

## Scope
- Five main routes: Today / Team / Transfers / Calendar / Players. Legacy History, Statuses, Data & Prices, and Profile retain all functions in the 'More' popover.
- Today shows decision prerequisites, verified source freshness, upcoming 7/21-day schedule and conditional FP in separate groups, roster injury alerts, and optional multi-planner launch.
- When source data is missing/stale, Today fails closed instead of declaring zero games or a certain transfer gain.
- Optimizer now enters via a single task; alternative tasks are collapsed, but remain accessible. A completed result supplies three concise reasons. Original research tools unchanged.
- Cyrillic-compatible warm palette, spacing and desktop/mobile typography. This is an original restrained visual system, not an official Claude design.
- Calendar explains back-to-back (B2B) and refuses to fabricate opponent difficulty scores.
- Sports.ru reconciliation remains in Team page below roster; no direct Sports.ru writes.

## Do not overclaim
- All modelled expected FP are uncalibrated as transfer utilities; P(play) is not calibrated across the full field.
- Risk notices only describe source evidence; no no-news-is-healthy assumption.
- Simulated 21-day scenario must still be checked for exact Sports.ru prices, actual quota and player availability.
- No change in scoring rules, xFP weights, model selection, Firebase Auth/Firestore schema, automatic transfers, GitHub Actions pipeline, or published Hosting.

## Offline QA
- 29 existing Node regression tests pass.
- New pure Today decision unit tests pass, including fail-closed scenarios.
- Sports.ru reconciliation, history and Node-VM tests pass with synthetic data.
- Headless Chromium at 1440, 390 and 320 px: 5 navigation destinations reachable, secondary routes reachable via More; no page errors, horizontal overflow or hidden tabs.
- All tested screenshots used offline static seed and a synthetic 10-player roster; no claim about live owner-specific production data.

## Adoption
Full source under site/hosting_v618 only. Owner publication is separate through existing Firebase Hosting. Do not overwrite a live backup. Run tests and verify the actual user profile after publishing.
