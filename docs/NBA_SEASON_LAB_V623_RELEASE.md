# NBA Season Lab v6.23 — release candidate

Production currently user-confirmed v6.22 (Firebase project `nba-season-lab`). Do not create a new site.

## UX

The v6.23 candidate is an isolated copy of published v6.22. The optimizer score, timing, P(play), FP, transfer quota and private roster engines remain **byte-identical**. Only `styles.css` changes the presentation of the existing «Замены → Совет по составу» decision: stronger visual primary action and winner, better hierarchy, restrained warm palette, consistent mobile widths, and details on demand. Styles are no-cache in existing Firebase Hosting config. No automatic transfers.

## Minutes — independent prospective evidence

The already observed 19-Nov snapshot audit compared 1,337 identical verified played player-games: MAE 6.3928 → 5.2233 min. Those data were subject to research and model selection, and the positive-minute played-only cohort is not a random sample of all fantasy roster player-games. We DO NOT promote this result to production expected minutes.

The new protocol is frozen at `docs/NBA_MINUTES_FUTURE_PREREG_20261120.json`. Its cutoff is **2026-11-21 00:00:00 UTC** and its end is **2026-12-08 00:00:00 UTC**. The comparison uses only truly new first-issued player×game forecasts from the immutable earlier rule (model SHA256 `4f8357abadb37ae3fe3f1d5f4c10d502d8967737781fb4fb8039532dd867ff0d`), frozen pre-T−30 with confirmed timestamped prior observations. No retrospective backfill. DNP is not zero conditional minutes; missing/UNKNOWN never imputes an outcome. The exploratory reporting threshold is 12 ET dates, 60 NBA games and 600 positive-minute paired observations. Bootstrap resamples **whole ET dates**, not dependent player rows. Even a positive result cannot authorize site promotion or a policy change without independent complete-roster coverage, truthful P(play) and prospective economic testing.

The report from `scripts/evaluate_minutes_prereg_v623.py` is research only; expected initially to say `INSUFFICIENT_FUTURE_SAMPLE`. No automatic model selection.

## Release gate

Workflow `hosting-v623.yml` must pass deterministic unit tests, unchanged computational engines, all Node regressions, real Chromium checks at multiple desktop/mobile sizes, actual public JSON, fresh source timestamps, exact-byte frozen model QA and a source manifest. The release builder refuses stale/corrupt/inconsistent public data. The resulting verified ZIP is for the **existing** Firebase Hosting and must be explicitly published by its owner; no Firebase action is automated. `main` merge is not equivalent to publication.

## Outstanding

- Do not display currently research-only conditional minutes as a production expected-minute forecast.
- Audit true scheduled population denominator and injury-game status identity.
- Independently evaluate the future prospective cohort after the cutoff without changing the preregistered protocol.
- Recheck actual personal Sports.ru price and weekly transfer quota before a real roster transaction.
