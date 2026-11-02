# NBA Season Lab v6.14 — Court-first UX candidate

Based on the existing v6.13 Hosting candidate. No new Firebase project, no modifications of Firestore, model weights, score rules or automatic Sports.ru transfers.

- Team: modern responsive two-half-court view, all ten slots (2 per PG/SG/SF/PF/C), no bench implied; click opens existing player details. Existing list retained.
- Players: quick views for affordable one-player replacement candidates (approximate prices only), my roster and all players; filters, compare and load more preserved.
- Calendar: my ten-player game counts over 7/14/28 days first; existing detailed ET week and arbitrary-date views kept. Unverified schedule is explicitly unknown, not zero.
- Status: official report for my roster first; other players and Telegram separately.
- Data/prices: current feed and owner quotes up front; technical source diagnostics and club corrections in disclosures.
- Profile: account access, backup and dangerous reset separated. Local decision/price evidence exports explained.
- Historical stats and task-based transfers remain functional.

QA: 12 pre-existing decision-journal Node tests + 3 new court tests; JS syntax checks; existing planner VM integration; isolated Chromium render at 1440/390/320 with all ten player cards, no positional card overlap and no horizontal document overflow; isolated UI navigation and clicks with mocked storage and no cloud writes. The mock browser does not verify real Sports.ru credentials or live Firebase.

IMPORTANT: bundled data/live.json remains an old fallback; verified current data must come from the existing public GitHub feed. User must back up personal data, deploy to existing Hosting only, check live sources/roster/quotas, and avoid saving mismatched data.
