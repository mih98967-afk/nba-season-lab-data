# PR #29: prospective paired played-FP reliability audit (research only)

This change does not develop or deploy a new model. It adds auditable uncertainty
and explicit longitudinal sample requirements to the **existing** v2 shadow
forecast audit. It never mutates historical predictions or personal accounts.

* Population: finalized verified positive-minute player-games only, each once.
* Baseline–candidate loss difference is paired **within the same player-game**.
* Confidence diagnostic: 2,000 seeded 95th percentile bootstrap resamples of
  **whole completed NBA games**, not independent player rows.
* Test gate checks source report first-observed timestamps and publication dates
  against the prediction issue time. A later source observation is quarantined.
* First vs latest revision value is not claimed until revisions are themselves
  evaluated on *played* finished games. Revisions on future/unknown games do not
  count as evidence.
* ET game dates and distinct games/players are explicit. Minimum 4 ET dates and
  20 complete games is only a screening floor; not independent calibration.
* No Brier, p_play, DNP absence inference, injury diagnosis or monetary profit.
* Report status remains research_only_not_deployed; adopt_on_site=false.
* No changes to live.json, schedule, current website, Firestore, transfers,
  user roster or cash, Lovable/Firebase billing or paid APIs.

Observed 26 October 2026 source baseline: 130 paired played player-games,
**7 actual NBA games, one ET date (Oct 25)**; 0 evaluated player-games with
usable revisions. MAE 7.3498 vs 7.3024, descriptive paired gain +0.0474 FP.
Game-level bootstrap 95% exploratory interval about [-0.1265,+0.2184]
FP/player-game; includes zero. No verified out-of-time superiority.
