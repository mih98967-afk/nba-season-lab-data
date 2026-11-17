# Fresh public NBA source snapshot — 17 November 2026

Captured the four original SportsDataverse release inputs with the preserved `collect_sources.collect((2027,), ...)` implementation. There were no retries, private inputs, model fits, candidate selections or feature-frame builds. The original November 16 snapshots were not changed.

Capture ran **19:34:33–19:35:23 UTC / 22:34:33–22:35:23 MSK**. All four files changed from the preserved snapshot and passed internal identity and team-total checks.

| Check | Result |
| --- | --- |
| Downloaded public sources | 4/4 |
| Regular-season schedule | 1,206 games, 20 October 2026–11 April 2027 |
| Completed games with schedule scores | 205 |
| Completed games with matching player team totals | 205 |
| Latest completed NBA game date | 16 November 2026 |
| Boxscore rows | 5,840 |
| Positive-minute rows | 4,618 |
| Explicit DNP-comment rows | 846 |
| Zero-minute rows without explicit negative comment | 376, remain UNKNOWN at this source stage |
| Explicit inactive records | 1,428 across 169 games |
| Positive-minute vs inactive conflicts | 0 |
| Latest injury report source timestamp | `2026-11-17 00:00:00` |

The score/minute checks do not convert missing inactive records or UNKNOWN boxscore rows into DNP. The inactive and boxscore inputs have different coverage and require the existing exact identity merge. The schedule remains incomplete and supplies NBA calendar dates, not UTC tipoff times. Its 1,206 rows must not be described as the complete 1,230-game regular-season schedule.

The injury timestamp is naive source time, not an explicit UTC timestamp. The snapshot contains report versions for games through 18 November, including unsubmitted team reports. Those placeholders do not mean Available. Original report-source time handling and strict pre-cutoff matching should be retained or explicitly versioned.

## Availability and timing

The manifest proves successful capture in this session; it does not prove all four upstream releases were atomically published. `SOURCE_QA.json` establishes internal consistency at join and team-total level, with source freshness separate from fetch time.

The original model constructs features by NBA date. Prior-date NBA games can end after midnight Eastern. Therefore, do not claim all prior-date game results were literally known at 00:00 Eastern without game-completion evidence. For a new real future freeze after this capture, use the capture/issuance timestamp as the conservative known-availability bound and disclose day-level feature semantics. Preserve original commitments unchanged.

## Files and next use

`source/current/` contains the four fetched inputs, the derived injury CSV, source manifest, and conversion manifest. `CAPTURE_SUMMARY.json` records capture timestamps and collector SHA. `SOURCE_QA.json` records schema/identity/count/timestamp/hash checks.

Historical `source/upstream/` files are reused by a symlink to the unchanged research archive. Packaging should dereference this link or supply the original archive alongside it.

## Completed feature build

`build_fresh_frame.py` ran the unchanged original `current_validation` implementation with an explicit `ASOF_DATE='2026-11-17'` and leads 0/1/3/7/14/21/28. It finished at 19:37:47 UTC. No fitting, calibration, model prediction or outcome scoring was performed.

- `feature_frame.pkl`: 26,443 rows, including reconstructed past-outcome rows. Do not pass the whole frame to future-only prediction/commitment code.
- `future_feature_frame.pkl`: 1,291 rows for 39 future games and 496 players. Future labels were asserted UNKNOWN, then the three outcome columns were removed. This is the safer input for new future inference.
- `FEATURE_BUILD_QA.json`: full/future hashes, capture availability bound, source provenance and build coverage.
- `FUTURE_UTC_SCHEDULE_QA.json`: exact date/home/away join to the current public UTC schedule. All 39 games joined uniquely with valid UTC/ET date agreement. Earliest tipoff is 18 November 2026 at 00:30 UTC / 03:30 MSK. All were before T−30 at the audit; recheck at actual forecast issuance.

| Lead days | Future rows |
| --- | ---: |
| 0 | 167 |
| 1 | 397 |
| 3 | 297 |
| 7 | 98 |
| 14 | 269 |
| 21 | 0 |
| 28 | 63 |

There are no scheduled lead-21 games in these incomplete NBA Cup calendar inputs. No fixtures were invented. The exact UTC schedule wrapper is explicitly derived from the 1,200 entries in the captured public `live.json`, updated at 13:28:44 UTC; the original entries and source hash are preserved. This does not prove a complete future calendar.

The fresh snapshot has not been used for any model training or scored against the original future commitment. For additional exponential features, load normalized histories from this fresh source root; the historical common `raw.pkl` contains no 2026/27 rows.
