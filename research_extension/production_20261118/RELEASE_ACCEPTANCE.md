# Release/inference acceptance, 18 November 2026

## Implemented engineering contract

The near/latest and long/latest fitted bundles are unchanged. The dayEWMA recipe is a mean-only shadow. Weight byte SHA256 is pinned in executable code, independently checked before Python unpickling; 47 small ASCII chunks losslessly reconstruct the original three bundles. Browser code consumes only JSON. There is no paid runtime, new Firebase service, training, automatic transfer or personal data write.

The future-only builder exactly reproduces 1,291 previously frozen-feature rows and 112 numeric columns from 17 November (maximum absolute difference0). Long adapter exact saved leads match original inference exactly (max difference0). Contract tests cover original near fixture, all saved long leads, hash corruption, future-label rejection, missing features, invalid probability, negative FP, actual lead preservation and no window interval endpoint summation. These are inference tests, not full retraining CI.

Free Actions refresh uses 12 SHA-pinned historical files with cache plus four fresh current-season archives. Archive retrieval time and sporting-data freshness are checked separately. When slow archives lag, a maximum18 prior-date games in the last3days can be supplemented from official NBA CDN. A full NBA schedule, exact home/away/time/player identities, full two-team final score and minutes/stat checks are required. ACTIVE with no minutes and no explicit nonplay evidence remains UNKNOWN. The generic intake was reproduced offline from all five captured18Nov official files:210 complete games through17Nov,4,721 played rows,0 original modifications. A failed/ambiguous source must stop refresh; the UI expires the last successful feed.

Seven catalog IDs with proven cross-player historical contamination (`n133`,`n266`,`n314`,`n326`,`n346`,`n406`,`n423`) cannot use a legacy seed fallback. Their exact NBA-ID research rows remain usable. The final supplied-roster audit found nine wrong season rows across these seven cards. The three additional IDs (`n266`,`n314`,`n423`) are absent from the original303-case baseline common cohort, so its frozen evidence report and hash remain unchanged. Other cold starts/identity gaps use a clearly marked existing seed estimate only if present; no calibrated interval or decision eligibility is invented.

The reviewed18November current catalog bridge maps459of484catalog cards to exact or preserved high-confidence NBA IDs;25remain unresolved. It adds or upgrades98links, checks catalog name/team/position and its source hash, and cannot be applied before its actual observation time. It is a current release input only: it does not relabel prior frozen forecasts, certify historical roster vintages or modify model weights. Its own exact file hash enters the feed input manifest.

## Exact intermediate-day policy and limits

Every tree sees the actual lead. Only existing mean bias, sigmoid and interval offsets use the smallest saved lead greater than or equal to it. This is not a mathematical guarantee that a later lead yields wider or conservative uncertainty. The predeclared exposed2025/26 audit approves the descriptive `audited_lead_bucket` label at days2,4–6,8–13,15–17. Days18–20 fail the fixed conditional-coverage criterion;22–27 have no confirmation cases and remain provisional. The saved21day lead itself has only289 played confirmation cases and conditional80% coverage74.4%; its limitation stays visible. The28day model has no latest confirmation cases. All failures and sample counts are retained in BUCKET_ELIGIBILITY.json and the full audit report.

The term calibrated identifies fitted historical offsets, not guaranteed current coverage. Conditional and unconditional predictive intervals are separate. A per-game range is never a confidence interval for a mean. Expected values can be added across known scheduled games without independence assumptions; calibrated sums/quantiles cannot. The feed publishes window expectations and completeness counts with predictive_intervals=null.

## Scientific acceptance and current production baseline

The saved original model is the best of its checked candidates under its declared development selection. It beat the historical last10/history-participation benchmarks on conditional FP, P(play) and unconditional FP, with exposed confirmations and incomplete UNKNOWN coverage documented in preserved reports. It is not proven globally optimal or economically beneficial.

The deployed default is **not** just last10. `site/hosting_v620/app.js` functions `oldGameProjection`, `learnedMean`, `probability` mix the saved seed/game prior with up to8 recent played values (0.87 decay and bounded blend), then apply saved participation/verified exact-game status and user modes. A benchmark against last10 cannot establish superiority over that runtime. Private user overrides are not part of public automatic comparison.

`model_policy.site_default` stays false unless a concrete reviewed gate report sets both `exact_deployed_default_replay:true` and `site_default_gate_passed:true`. That decision must use the same eligible identities, pre-game cutoff and future games for both models, and report:

1. Conditional FP MAE, RMSE and bias on played cases.
2. Participation Brier/logloss with explicit DNP, UNKNOWN denominator and sensitivity bounds.
3. Unconditional FP MAE/RMSE/bias, including explicit nonplay zero rather than played-only evaluation.
4. Conditional/unconditional50/80/95coverage, width and interval score; separately Questionable, low minutes, returns and actual lead.
5. Missing/cold-start coverage, old seed identity contamination and immutable source provenance.

Only verified seed histories can be replayed. The corrected current-season replay is an exposed diagnostic, not prospective evidence or a fair reconstruction of unknown historical UI state. If the exact baseline/vintage cannot be recovered or a key comparison fails, the named research view remains available while automatic default/optimizer promotion stays off. New intraday injury features have their own timing-extension label; the earlier midnight-cutoff calibration does not by itself validate that changed timing distribution.

## Separate fantasy-economic gate

KEEP/NOW/LATER requires frozen alternatives before T−30 with exact contemporaneous quotes, quota, roster ownership, team lock and independent Sports.ru per-player-game credits. Neither conditional MAE nor a one-night model result can satisfy it. `optimizer_policy_validated:false` and `economic_gain_proven:false` remain independent of whether the forecast view is released. No original1,741 forecasts, Nov17 paired334records or past user replacement history is overwritten.

## Recorded default-release decision

Root's18November review accepted the **original** near/latest and long/latest weights as default forecast inputs after corrected exact-runtime replayv2 (including `updatePlayerTeams`) and the inference gates; SITE_DEFAULT_GATE.json records the bounded decision and hashes its evidence. On the common near-primary cohort over two NBA dates/13games, unconditional MAE was6.725190 for the reconstructed public runtime versus6.080735 for the frozen model (288known FP outcomes); participation Brier0.10663169 versus0.06155360 (294known participation cases). The runtime comparator was reconstructed after outcomes from preserved pregame inputs and public defaults; it was not originally frozen and does not reproduce private user settings. There are303 common cases of428 frozen near forecasts;125 comparator cases are unavailable, separately reported. Identity-exclusion sensitivity retained the gain. Conditional gain remains small and uncertain. The decision combines this check with the already locked multiseason historical evidence; it is a practical release decision with these limitations.

Fresh official PDF annotations do **not** change the selected calibrated CatBoost probability or its saved intervals. An exact current OUT becomes a separate deterministic effective-zero overlay. Other fresher status effects are computed only in the labelled intraday shadow; a changed timing distribution is not silently called calibrated. DayEWMA is not selected. Default forecast inputs inform existing advisory comparisons (`forecast_inputs_for_advisory_comparisons:true`), while `optimizer_policy_validated:false` and `economic_gain_proven:false` remain explicit. No automatic transfers or personal Firestore changes are introduced.
