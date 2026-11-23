# NBA Season Lab v6.26 — complete-night score and source freshness

Base: owner-confirmed published v6.25, isolated candidate in `site/hosting_v626/`.

## Source observation (23 Nov 2026)
NBA CDN responded HTTP 403 in the verified 00:54:57 UTC public sync;
the existing fail-closed ESPN fallback supplied 242 final games and 4,682
player-boxscore rows. The latest ET day in that feed (22 Nov) contains
1 final/boxscore game of 7 scheduled games; six were still live or scheduled
according to the observed source. A number for this single match **is not**
the full ET day total. Frozen model forecast subsequently reached a separately
issued 22 Nov 22:12 UTC snapshot; never conflate model validity with boxscore
completeness.

## UX/safety changes
- The Team view's "Last NBA ET day · current ten" tile now displays verified
  boxscore FP **only when every scheduled game of that ET day is final,
  identity matched, and has at least five played rows from both teams**.
  Show n/d and explicit "x / y games" during an incomplete night.
- Reject repeated player-game rows, mismatched game team identities, non-finite
  played FP, missing schedule, and unverified public feeds. Signed negative FP
  remain valid. Missing rows and DNP/UNKNOWN are never silently zeroed.
- In the Today proof column separately show completeness of latest NBA ET
  game day, public boxscore age, and *actual model forecast expiration*, not
  just one generic "fresh" indicator.
- "Data" page explains provider/CI timing, daily inference safety net, and
  distinguishes public NBA boxscore from owner-confirmed Sports.ru season total.
- A source snapshot valid at its own issuance can still be incomplete for a
  newer sporting ET day. Neither static Hosting deploy nor a successful CI
  promises minute-live scoring.

## Immutable boundaries
The actual production model FP, P(play), uncertainty, optimizer,
transfer guard, monetary model, personal roster, private Firestore, ownership,
and the preregistered 21 Nov–8 Dec prospective minutes protocol are unchanged.
Research minutes remain `adopt_on_site=false`.

## Acceptance
- Calendar and score source synthetic regression: partial night, complete
  night, signed negative FP, duplicate player-game, mismatched teams,
  missing/unverified data.
- All existing Node/Python regression tests, source-manifest integrity and
  exact forecast inference SHA parity with published JSON.
- Real-browser fixture and current public-data QA on mobile and desktop.
- Complete verified v6.26 Hosting ZIP; only owner publishes to existing
  `nba-season-lab` Firebase project. Do not automate deployment.

### Outstanding
The site does not have authenticated Sports.ru personal scoring feed.
Current-roster NBA boxscores are not a replay of historical ownership.
An official running Sports.ru total still requires source-authorized
integration or confirmed owner-recorded credits. Do not overwrite checkpoint.
