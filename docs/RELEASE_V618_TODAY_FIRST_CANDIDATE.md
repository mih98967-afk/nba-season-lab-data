# v6.18 user-first UX release candidate

Owner choices: default question is whether a transfer is needed today; short (7d) and long (21d) horizons; balanced risk; concise 2–3 reasons; desktop-first with mobile support; show player role and fantasy stats rather than biographies.

Full offline Hosting v6.18 source candidate is provided as a separate ZIP to the owner. **This PR is a design/QA handoff only** and does not deploy or claim to recover the entire HTML bundle. Its source is the unchanged v6.17 release plus new Today decision module, 5 primary routes and a secondary More menu.

Gate: never issue a transfer recommendation from stale or incomplete feed; absent future schedule is UNKNOWN, not zero games. Display conditional forecast FP as estimation, not a validated Sports.ru gain. Keep the current multi-planner, transfer guard, scoring, personal roster, account and model weights unchanged. Distinguish official NBA risk from Telegram.

Offline validation: prior 29 Node tests PASS; new Today module unit tests PASS; synthetic-profile Chromium tests at 1440/390/320 width PASS for 5 primary routes, secondary navigation, no JS errors or horizontal document overflow. No owner-authenticated production validation. No Firebase deploy.

Next PR must import exact complete ZIP, SHA-verify every asset, run browser smoke tests and CI before merge. After owner publication, test with current account data. Further separately validated work: calendar strength estimates and measured incremental KEEP/NOW/LATER accuracy.
