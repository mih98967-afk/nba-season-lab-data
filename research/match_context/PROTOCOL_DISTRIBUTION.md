# Distribution-specific follow-on, after current subgroup audit

Current testing found lower conditional80 coverage in Questionable cases.
This motivates an EXPLORATORY follow-on, not an untouched replication. Do not
select settings against these current outcomes. Mean and participation weights
remain frozen. Select the quantile feature family independently of mean RMSE.

Fixed quantile feature families: prior form only, full match context, full
context plus eligible published injury/teammate features. Seven fixed levels
.025,.1,.25,.5,.75,.9,.975; original LightGBM240/15/0.035/L2=10 settings.
Train END2024, select by mean pinball loss across levels on the original
END2025 development block through31December2024. Refit the selected family on
all played rows through31December2025. Calibrate on24January-15February2026,
without any current outcomes. Do not change chosen family after current test.

Additionally report optional conservative status-group widening. For each
of the existing five published status groups, require >=60 played calibration
rows; use max(global conformal offset, group offset) for conditional intervals.
Unknown/submitted-not-listed groups retain the global interval. This is based on
calibration labels only. Such post-hoc subgroup targeting is not independent
proof of current conditional validity and must be prospectively checked.
No post-hoc shift of means/probabilities. Do not claim all individual intervals
have exact nominal conditional coverage or sum per-game interval endpoints.
