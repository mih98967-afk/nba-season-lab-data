# NBA Season Lab v6.17 - owner-attested Sports.ru comparison (candidate)

Base: the exact, SHA-256-locked v6.16 public Hosting source restored in PR #134.
Do not claim v6.17 is deployed merely because a source PR is merged.

## What changed
- Team page has a collapsible, three-field Sports.ru comparison: season FP,
  free cash and remaining weekly transfers. Values are supplied by the owner
  while viewing Sports.ru; no Sports.ru API, credentials or screenshots required.
- This comparison lives only in volatile JavaScript UI state. It is **not**
  saved to Firebase, localStorage, the team, public datasets or GitHub.
- FP is an *indicative* NBA boxscore reconstruction, not official credited FP.
  It always warns about ET-day assignment, partial data and source revisions.
- Quota shows Monday 15:00 and 00:00 MSK as competing hypotheses, not two
  independent allowances. An ambiguous Monday historical transfer is no
  longer rejected solely on the presumed 15:00 boundary. A history that
  violates BOTH hypotheses remains blocked for owner review.
- Existing money, roster, transfers, forecast weights, no-auto-trade policy
  and account storage are untouched by the comparison.

## QA
- Node syntax checks for all scripts.
- Pure regression tests of both quota hypotheses, missing vs zero inputs,
  stale source, unverified outcomes and non-persistence.
- Isolated Node VM test renders the actual Team template and exercises the
  two UI actions against synthetic roster and fields with no cloud writes.
- All relative JS references in the full index.html resolve locally.
- Chromium interactive validation was unavailable in this environment:
  ERR_BLOCKED_BY_ADMINISTRATOR even for a minimal blank/data page.

## Limits
- No owner Auth, real personal roster or official Sports.ru account was read.
- A matching number does not verify Sports.ru scoring or reset time.
- A mismatch does not automatically adjust the stored team or cash.
- Browser UI should be checked on the actual Hosting candidate before
  owner publication; a green CI is not real-world functional validation.
