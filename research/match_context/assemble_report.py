"""Summarize actual saved reports, not freshly selected best test outcomes."""
import json,pathlib,hashlib
R=pathlib.Path('.')
def load(p):return json.loads((R/p).read_text())
near=load('results_current_near_latest/CURRENT_SEASON_REPORT.json');long=load('results_current_latest/CURRENT_SEASON_REPORT.json');dist=load('results_current_distribution/CURRENT_SEASON_REPORT.json');op=load('results_phase2/OPPONENT_DIAGNOSTIC.json');v=near['per_lead']['0']
summary={'schema':'nba-match-model-research-summary-v1','asof':'2026-11-16','status':'best_tested_research_candidates_not_production','adopt_on_site':False,'real_KEEP_TRANSFER_gain_proven':False,'selection_scope':'Declared finite family tournament, not a global optimum','production_model_changed':False,'models':{'near_game':load('results_near_latest/MODEL_RESEARCH_REPORT.json')['model_sha256'],'long_lead':load('results_latest/MODEL_RESEARCH_REPORT.json')['model_sha256'],'exploratory_interval_challenger':load('results_near_distribution/MODEL_RESEARCH_REPORT.json')['model_sha256']},'current_near_game':v,'current_lead_table':{},'current_questionable':near['subgroups']['questionable'],'exploratory_questionable':dist['subgroups']['questionable'],'opponent_group_ablation':op['paired_gain']['no_opponent__full_context']['audit'],'prospective_commitment':load('prospective_20261116/COMMITMENT.json'),'unit_tests':41,'unit_tests_status':'PASS','limitations':['Current-season replay is not genuine pre-issued performance','Historical seasons have been reused in project research','Final archive revisions and historical schedule vintages not verified','Current near-game morning reports can be stale at eventual decision time','Observed prior-team membership and >=5 previous appearances; not all fantasy players','Questionable conditional intervals under-cover; exploratory follow-on does not fix it','Current 21-day test only 559 played rows; no current 28-day test','Per-game intervals, not weekly/roster intervals','No independent official Sports.ru credits or economic transfer test']}
for h,row in long['per_lead'].items():
 if 'fp_conditional' not in row:summary['current_lead_table'][h]=row;continue
 summary['current_lead_table'][h]={'played':row['played'],'known':row['known'],'baseline_mae':row['fp_conditional']['baseline_last10']['mae'],'candidate_mae':row['fp_conditional']['selected']['mae'],'baseline_brier':row['p_play']['history_baseline']['brier'],'candidate_brier':row['p_play']['selected']['brier'],'conditional80_coverage':row['intervals']['80']['conditional']['coverage']}
(R/'RESEARCH_SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
rows='\n'.join(f"| {h} | {r.get('played',0)} | {r.get('baseline_mae',float('nan')):.3f} | {r.get('candidate_mae',float('nan')):.3f} | {100*r.get('conditional80_coverage',float('nan')):.1f}% |" if 'candidate_mae' in r else f"| {h} | 0 | No finished current cohort | -- | -- |" for h,r in summary['current_lead_table'].items())
text=f'''# NBA Season Lab: match-specific distribution research

Date: 16 November 2026. Existing repository and project only. Draft research PR 178.

## Decision

**Retain production unchanged.** The best tested near-game research candidate is regularized linear regression with match context for conditional mean FP, calibrated CatBoost depth 4 for participation, and seven quantile regressors with held-out interval calibration. Long-lead research uses the separately selected Ridge + LightGBM participation stack. This is a best-tested finite candidate set, not a claim of a globally optimal or fully validated fantasy decision engine.

The research package contains runnable code, source hashes and snapshots, trained weights, protocols, reports, tests and frozen public forecasts. No personal owner information, Firestore records or executed transfers is included. The repository research branch publishes the report, provenance and prospective commitment; no Hosting deployment is performed.

## What was tested

Three historical regular seasons (2023/24, 2024/25, 2025/26), 3,690 NBA games. Features use preceding dates only. Existing NBA-derived boxscores were complemented with explicit DNP/DND and 32,923 inactive-player records. Missing rows remain UNKNOWN. An inactive list is not a full registered roster. Timestamped injury archives use the last complete team report strictly before the issue-date morning cutoff; a missing report is not an Available status.

Candidate families: last-10 mean, fixed previous v2, form/minutes, rest, opponent context, injury context, Ridge, LightGBM, CatBoost, XGBoost, bounded blends and minutes-times-rate. Conditional mean selection uses RMSE; MAE, bias, subgroups and ranking of variants are retained. Participation uses Brier/log loss plus reliability tables. Interval models are evaluated on coverage, width and interval score, not coverage alone.

The 2025/26 audit has been used elsewhere in this project: it is **not a newly untouched holdout**. All current-season training/calibration was prohibited. A later interval-feature follow-on was motivated by current subgroup undercoverage; it is labeled exploratory even though its numerical fitting/calibration still uses past seasons only.

## Additional 2026/27 replay: near-game primary

There are {v['opportunities']:,} ex-ante opportunities, {v['known']:,} known outcomes, {v['unknown']} UNKNOWN, and {v['played']:,} played-player-game outcomes over 24 dates. These counts are not counts of NBA fixtures. These are reconstructed morning-date forecasts, not predictions demonstrably issued at that historical time.

| Metric | Comparable simple baseline | Frozen candidate |
|---|---:|---:|
| Conditional FP MAE | {v['fp_conditional']['baseline_last10']['mae']:.4f} | {v['fp_conditional']['selected']['mae']:.4f} |
| Participation Brier loss | {v['p_play']['history_baseline']['brier']:.5f} | {v['p_play']['selected']['brier']:.5f} |
| Unconditional FP MAE | {v['unconditional_fp']['history_baseline']['mae']:.4f} | {v['unconditional_fp']['selected']['mae']:.4f} |

Conditional MAE gain: 0.2692 FP; descriptive date-cluster 95% bootstrap interval [0.1882, 0.3460], 24 date clusters. Mean forecast bias remains +0.613 FP. P(play) expected calibration error is about 1.68 percentage points, with subgroup weaknesses. The Brier reduction is not an accuracy percentage and does not isolate calibration from discrimination.

The baselines above are last-10 FP and personal participation history on the same cohort, **not a direct re-run of the current browser fallback formula**. No claim that published Hosting recommendations now have these results is warranted.

## Prediction intervals

The primary candidate's conditional 80% interval covers 79.84% of current played outcomes, average total width 20.83 FP; its 95% interval covers 95.06%. With explicit no-play outcomes included, the nominal 80% mixture interval covers 83.98%, partly conservative because zero has point mass. Negative played FP is retained. These are prediction intervals for individual outcomes, not confidence intervals for the mean and not summed-week intervals. NBA time-series data do not automatically satisfy exchangeability; empirical coverage is evidence, not a universal guarantee.

Questionable remains a weakness: 102 played cases, conditional 80% coverage only 71.57%; the mean also overpredicts by about 1.99 FP in that subgroup. The quantile-feature follow-on improves overall 80% coverage to 80.18% but Questionable coverage only to 73.53%; its interval score for this subgroup does not improve. **Do not claim this problem is solved.** Preserve the primary and challenger separately for prospective evaluation.

## Does the opponent matter?

In the separate matched diagnostic, removing the opponent-related feature group changes historical audit MAE from 6.4158 to 6.4991. The 0.0832 FP improvement has a descriptive date-cluster interval [0.0541, 0.1091]. This group includes opponent defense/pace/strength, rest interactions and shrunken head-to-head features; it is not a causal estimate of defense alone. Do not impose visually different numbers just for appearance. Some nearby match estimates should legitimately be similar.

Standalone rest-only and injury-to-conditional-mean extensions did not outperform the chosen context family. More complex nonlinear FP models did not beat Ridge on the declared development selection. Injury information is much more useful for participation than it was for conditional mean FP here.

## Days before the individual match, not length of a weekly total

| Lead days | Played cases | Last-10 MAE | Candidate MAE | Conditional 80% coverage |
|---:|---:|---:|---:|---:|
{rows}

For each lead, player history and injuries are frozen on the issue date, not refreshed with future results. The 21-day current cohort is small (559 played cases over only five dates). No current 28-day cohort exists yet, and the most recent refit's post-calibration 28-day confirmation cohort is empty. Older historical audits exist, but do not remove those limitations.

## Safeguards and retained boundaries

41 executable tests PASS: UNKNOWN != 0, explicit no-play, source conflict quarantine, negative FP, target/future-stat mutation invariance, strict whole-team injury snapshot selection, purged time windows, source/model hash validation, unsupported lead rejection and complete teammate context requirements. Raw-source preflight PASS. Inference parity tolerance is 1e-4 FP; observed maximum float32 batch-rounding difference was 9.54e-7.

Source archives are final reconstructed versions. Original receipt timestamps, exact historical schedule vintages and complete fantasy eligibility are not established. Five prior played games and observed prior-club membership are required by this research cohort. New players, trades, missing memberships and omitted schedule games need a separately verified fallback. Sports.ru official credited per-game FP is not independently reconciled. Price paths, quota, locks, roster ownership and actual economic transfer gain are outside this model validation.

## Frozen future evidence

At 2026-11-16T18:49:16.873587Z, froze 1,741 forecast records for 1,480 distinct player-game pairs across 45 future fixtures. Primary near-game and interval challenger share 261 player-games; the long-lead candidate contributes 1,219 records. First admitted tipoff: 2026-11-17T00:00:00Z. The feature cutoff is older, 2026-11-16T05:00:00Z, and is recorded separately. Forecast bytes SHA-256: `5aa81fa5db8f8a4e240cce3ec2477fad17626822c5eea2c02f39dab1b932a0cb`.

A hash commitment was published to the existing repository before these games. This starts a real prospective comparison; it does not prove future accuracy or transfer utility. The feature freshness limitation still applies. No background monitoring or automatic future evaluation has been scheduled.

## Production gate

Before replacing site estimates: validate the live feed/identity/time contract, handle cold starts and unknown labels explicitly, confirm current-injury freshness, evaluate the immutable forecasts, and test independent economic usefulness versus KEEP with real prices/limits/locks. Weekly totals need dependence-aware validation and cannot use a sum of per-game interval bounds. Until then `adopt_on_site=false` and `real_KEEP_TRANSFER_gain_proven=false` remain.

## Reproduction

Use the provided frozen source snapshots to reproduce these numbers; re-downloading may retrieve corrected archives and defines a new run. Install `research/match_context/requirements.txt` in a clean trusted Python environment, run the unit tests, and execute `sh research/match_context/reproduce.sh source reproduced`. Current evaluation is intentionally frozen to the 16 November 2026 snapshot, not a general production scheduler. Some fitted numeric values can vary slightly across scientific-library/platform versions; all saved weights are independently hash-checked. Never load untrusted pickle files.

The complete source capsule is `source_bundle.tar.xz` in the companion package; readable source files are also included. The public research branch's report and commitment do not imply the complete local training pipeline has been run by GitHub CI. Existing intake Actions and local scientific tests are separate evidence.
'''
(R/'MODEL_CARD.md').write_text(text)
print('REPORT_WRITTEN',len(text))
