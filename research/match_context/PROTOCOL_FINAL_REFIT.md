# Final current-season candidate refit -- frozen before current-season scoring

The family selection is complete. The extra family challenge did not beat
ridge-context for conditional FP. CatBoost-depth4 narrowly won the near-game
participation challenge; the pooled multi-lead tournament selected LightGBM
injury/history. Keep the two horizon-specific recipes and disclose them.
No 2026/27 observations are used to select families, fit parameters, calibrate
probabilities, correct means or calibrate intervals.

Refresh the multi-lead selected family on all feature rows whose target occurs
before 29 December 2025. Per-lead probability/mean calibration uses issue dates
29 December 2025-10 January 2026 and targets through 7 February. Interval
calibration uses issues 8-21 February 2026 and targets through 21 March.
Confirmation issues start 22 March 2026. Current-season replay remains an
additional test, not source of tuning. Fitted target dates must strictly precede
each following calibration/confirmation issue window. No retrospective score
from the earlier 2025/26 audit is relabelled independent for this refreshed fit.

Refresh the near-game ridge/CatBoost recipe on targets through 31 December2025;
mean/probability calibration is 1-23 January2026; interval calibration is
24 January-15 February2026; confirmation is from16 February. Quantile models are
refitted on the same training rows, never on calibration or current outcomes.

The historical tournament identifies families. These refits identify current
candidate weights. Record both; do not silently mix metrics and weight versions.
No automatic promotion, official Sports.ru credit proof or real-transfer gain.
