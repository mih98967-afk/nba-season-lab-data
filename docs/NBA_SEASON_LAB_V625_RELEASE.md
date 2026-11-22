# NBA Season Lab v6.25 — actionable player calendar and freshness

Base is the **owner-published v6.24**. New Hosting source stays isolated at
`site/hosting_v625`. No Firebase deployment by automation.

## What the player page adds
- Three **independent** match-count filters for the remainder of the current
  Moscow calendar week and the next two full Monday–Sunday weeks. Select any,
  an exact count (0–6) or a minimum count (1–6) in each week. Combined filters
  use AND. The first week excludes already-started games.
- Show known fixture counts N1/N2/N3 in every player row on desktop and mobile,
  separate from computed FP. No inferred participation or strength adjustment.
- Presets 7/14/28 days, arbitrary duration 1–28 days from now, or inclusive
  future Moscow date interval up to 28 days. The horizon applies to both sorting
  and display. Data outside current supported model range is rejected, not
  extrapolated. Existing prediction/uncertainty weights are unchanged.
- A schedule window intersecting unassigned NBA Cup games, stale 72h
  calendar or unconfirmed fixtures returns **n/d**, never zero matches/FP.
  Individual week filter conditions requiring that unknown count match nothing.

## Freshness/owner-score distinction
- The Team dashboard now has a separately identified read-only **last ET game
  day NBA boxscore FP** for currently owned ten players (played rows only).
  This is *not* the Sports.ru credited season tally, does not imply ownership
  of those players at historical locks, and is not written to Firestore.
  The existing date-stamped owner-confirmed Sports.ru checkpoint remains
  unchanged even after fresh boxscores arrive.
- Data page displays last observed NBA provider capture, model issuance,
  expiry/availability and last final ET date; server action delays and
  owner-only scores are stated explicitly.
- NBA public sync cadence changes from every 4h to every 2h (best effort
  GitHub Actions). The existing successful-sync-triggered frozen-weight
  inference/release QA and browser 15min fetch remain; there is no guarantee
  of minute-real-time NBA score updates or current Sports.ru season credit.
- Do not automatically infer a transfer from roster differences, reconstruct
  missing transfer time, or overwrite a private balance.

## Safety / tests
New calendar filters and snapshot display are view-only; keep all original
forecast, participation, risk, transfer and private scoring engines identical
to v6.24. The new `test_market_calendar_v625.cjs` tests Monday UTC+3
boundaries, three-week counts, exact/at-least filters, invalid/long ranges,
unknown Cup calendar and read-only NBA FP. UI VM checks that a market filter
does not modify owner state.

Release gate: source tests, original frozen minutes prereg, unchanged model
bytes, JS regressions, actual browser at mobile/desktop, exact frozen model
SHA proof matching current public feed, forecast expiration, complete ZIP.
Deployment to existing Firebase project `nba-season-lab` requires owner action.

## Known limitations
The source synchronizes NBA/ESPN boxscores, **not** personal Sports.ru credited
FP; owner checkpoints may lag by design. A true current owner credited total
requires an authorized Sports.ru data integration or confirmed evidence.
Individual NBA injury status and future match count availability may be
incomplete; show coverage as n/d and never reinterpret UNKNOWN as DNP.
The preregistered prospective minutes test 21 Nov–8 Dec is unchanged
(`adopt_on_site=false`).
