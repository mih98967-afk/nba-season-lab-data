# NBA Season Lab v6.16 - reconciled FP explanation for transfer decisions

Source: exact uploaded v6.15 Hosting archive; no personal roster / account data was used.

- On the Transfers page, expand the explanation of the best modeled KEEP/NOW/LATER plan. It attributes the scenario delta to purchased players, players removed relative to KEEP, and individual upcoming games.
- The explanation **recalculates and reconciles** the projection against the existing multi-planner, its unrounded modeled FP, the expected per-game values, and heuristic net after reserved opportunity costs. Any mismatch, missing forecast, duplicate fixture, or invalid roster transition **blocks the numeric explanation and route actions**. No silent substitution of zero for a missing forecast.
- The full route list keeps its optional details behind a disclosure. A plan can still remain a bounded hypothesis, not a guarantee; dates, estimated prices, and attendance remain uncertain. The heuristic penalty is not Sports.ru scoring.
- Only read-only front-end presentation was changed. No new model, weights, public data publisher, personal budget, roster, saved transfers, Auth, Firestore, Firebase project, automatic Sports.ru transfers or paid services.

QA: 29 Node unit tests PASS including 14 new breakdown tests; JavaScript syntax PASS; three isolated Chromium widths (1440/390/320) PASS using **synthetic** schedule and **synthetic** non-owner roster, with no unhandled JS exceptions, horizontal scroll overflow or HTTP private writes. It does not test real owner Auth, production calendar, or official Sports.ru credits. Archived local fallback live.json may be older than GitHub live feed.
