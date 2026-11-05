# P0: Public NBA sync blocked by historical index rotation (2026-11-05)

## Live evidence
- Public `data/live.json` last updated **2026-11-01T15:12:20Z** when checked on 2026-11-05. Do not treat the on-site projections as fresh.
- Scheduled public sync runs `41900297191`, `41944756343`, `42026779541` failed in the *same* downstream step, after the source collection and early checks.
- Actual traceback: `src/conditional_minutes_fp_research.py:264` raised `Existing minutes research incompatible with immutable model`.
- Frozen previous minutes issue archive referenced historical source index `0d395ece015799c4`, while `data/history/index.json` now reports `09c47a4bc1bdb53d` (history backfill/index rebuild).
- Do **not** paper over this by deleting `data/conditional_minutes_fp_research.json`, mutating frozen issues, changing model weights, backdating first-issued forecasts, or suppressing the QA failure.

## Candidate repair
1. Preserve every old issue's original `historical_source_index_version`, original `issued_at_utc`, original forecasts and original model hash.
2. Accept a new **complete, audited** history index for **future, genuinely issued** forecasts. Store the sorted immutable list of archive versions in `historical_source_index_versions`. The top-level `historical_source_index_version` remains the latest index, but is **not** used to rewrite legacy forecasts.
3. The prospective importer and downstream evaluator both validate that each issue's original version belongs to the registered index-version set. Missing, duplicate, unexplained or unregistered lineages fail closed. New issued records use their actual current timestamp and newly read history index.
4. Regression tests cover real previous archive evaluation, index rotation, new issues, unchanged old bytes/values, idempotent rerun, and lineage tampering.

## Definition of done
- PR offline CI passes on the existing frozen public files.
- Merge only after CI passes. Check **real, scheduled or post-merge** `NBA public data sync` run on main, not just unit tests.
- Verify updated `data/live.json` and downstream research reports from public GitHub after the real writer succeeds, including `updated_at_utc`, `issued_total`, and source-version ledger.
- If a later stage of main fails, inspect logs and address that actual failure without bypassing gates. The repair is **not** proof that 2026/27 P(play), FP gain or Sports.ru quota is calibrated.
- Hosting and private Firebase state stay untouched. None of these research models should be adopted on the site automatically.
