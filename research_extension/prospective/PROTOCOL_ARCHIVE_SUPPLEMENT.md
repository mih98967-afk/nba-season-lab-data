# Exact-NBA-ID supplementary scoring of the unchanged 16 November commitment

The strict ESPN report remains unchanged. Newly fetched 17 November 2026
SportsDataverse NBA-derived archives are a second, separately named outcome
source, not a new forecast and not direct official Sports.ru credited FP.

Before metrics: verify all downloaded source file hashes against capture manifest.
Reuse the preserved `current_validation.load_current_combined` with
`ASOF_DATE=2026-11-17`, without changing its code. Retain positive-minute played
labels and explicit DNP/inactive labels. Missing player/game entries remain
UNKNOWN. Join by exact NBA game and person IDs, frozen team/opponent and date.
Validate the source scheduled UTC timestamp against the frozen tipoff when the
source exposes a reliable UTC field. Otherwise report that date-level fixture
identity was checked, not a newly proven historical tipoff vintage.

Score every frozen record, including records absent from the fantasy-catalog
identity map. Never select the outcome cohort based on model errors. Compare all
overlapping strict ESPN known outcomes for participation and FP. Any disagreement
is quarantined as UNKNOWN, retained as a conflict record and excluded from known
metrics. Keep the unchanged baseline archived pregame feature values.

Report counts, conditional/unconditional FP, P(play), per-game 50/80/95 coverage
and missing-label Brier bounds separately from earlier evaluation. No refit,
recalibration, model choice or promotion follows from these 8 completed games.
One NBA date still cannot establish stable prospective superiority. Archive
source retrieval is after the games and can include statistical corrections;
it does not prove the original game-day source vintage.

Field-specific evidence clarification after observing four FP-only source
disagreements: retain their quarantine for conditional/unconditional FP and
interval metrics. Since both sources explicitly prove participation, also
report a separate P(play)-only metric retaining these positive labels. Do not
turn uncertainty about exact FP into uncertainty about already established
participation. This adds a transparent denominator, not parameter tuning.
