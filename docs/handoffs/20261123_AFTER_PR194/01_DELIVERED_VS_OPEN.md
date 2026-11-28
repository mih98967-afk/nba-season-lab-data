# Delivered versus open — verified 23 Nov 2026

## Shipped and known

- **v6.21**: matchup-aware Ridge conditional FP, CatBoost P(play), LightGBM research-supported prediction intervals, opponent difficulty overall and by PG/SG/SF/PF/C, and 7/14/21/28-day views. \`expected_fp = p_play * mean_if_play\`; official timely OUT is a separate override. Opponent positional difficulty is descriptive, **not** an independently validated additional numerical FP adjustment.
- **v6.22**: warm, restrained Claude-like user-first navigation; Today, Transfers, Team, Calendar, Players, compact forecast-first cards, progressive details, responsive difficulty calendar. Do not confuse fixture QA with real private profile acceptance.
- **v6.23**: planner hierarchy, immutable future-only minutes preregistration. Expected minutes research **not promoted**.
- **v6.24**: concrete, bounded KEEP/NOW/LATER reasons, T-30 and immediate market checks for multi-slot/chain first moves.
- **v6.25**: week 1/2/3 match filters, custom schedule periods and incomplete NBA Cup guard, NBA boxscore versus owner Sports.ru FP separation; existing NBA public sync every 2 hours best-effort.
- **v6.26**: fail-closed full ET-date score tile rather than treating partially completed night as whole; independent boxscore freshness and model expiration.
- **v6.27**: browser-local owner-attested dated Sports.ru checkpoint deltas and conditional bank+roster value comparison; still no authenticated per-player credits.
- **v6.28**: exact matched player-game **model coverage vs fallback** for KEEP and best verified route on same 7-day T-30 window; observational transparency only, no accuracy claim.
- [PR #193](https://github.com/mih98967-afk/nba-season-lab-data/pull/193) daily read-only minutes prereg evaluation with strict independently checked NBA ET dates and source hashes.
- [PR #190](https://github.com/mih98967-afk/nba-season-lab-data/pull/190) guarded daily inference fallback in case a live-sync-triggered workflow is cancelled. Not real-time guaranteed.
- Model weights, FP, P(play), optimizer ranking, owner cash/roster, quota, private Firestore and historical minutes protocol were not changed by the recent UX-only releases.

## Live unfinished work (do not mark complete)

1. **Expected minutes**: prospective independent sample and coverage gate have not passed. The 23-Nov 10:47 UTC prereg baseline: 351 real prelock issues, 161 independently verified positive-minute pairs, 12 games and **2 ET dates**. Frozen exploratory minimums: 600 played pairs, 60 games, 12 ET dates, MAE improvement ≥0.5 min and lower ET-date cluster CI >0. Period 2026-11-21 00:00 UTC inclusive to 2026-12-08 00:00 UTC exclusive. Earlier 1,337 matched played pairs showing 6.3928→5.2233 MAE were exploratory/previously studied, **not a fresh independent confirmation**. Even passing the conditional gate does not license automatic site promotion.
2. **Participation denominator / injuries**: \`data/participation_evidence_ledger_research.json\` as of 23-Nov 10:47 UTC contains 4,522 finished checked selected opportunities, 3,203 played, 424 explicit DNP and **895 UNKNOWN** (19.79%). Some official-OUT cases remain unobserved; absence from team roster is not DNP. No fully calibrated player×scheduled-fantasy-game P(play) or unconditional FP proven.
3. **True Sports.ru credit reconciliation**: owner checkpoints in v6.27 show deltas but do not reveal independently verified per-player/game Sports.ru awarded FP, historical exact transfer execution clocks or true quota reset. Earlier residual 5 FP, including 4/1 discrepancies, remains unresolved, not silently corrected. Private only.
4. **Economic transfer validation**: KEEP/NOW/LATER model gain minus a heuristic move reserve does not prove net Sports.ru FP or credits; real prices, cash, transfer availability, ownership at each T-30 and comparable future outcomes required.
5. **Matchup & schedule**: general/position difficulty displayed, but incremental predictive gain over existing matchup-aware FP has not passed prospective validation. Incomplete/unassigned NBA Cup fixtures remain unknown, not zero games.
6. **UX real owner profile**: independent final QA under true profile, desktop/mobile hierarchy, safe backup, correctness of prices/quota/ownership windows, and reduction of excess detail/navigation still required. Never silently edit private data.
7. **Research branches**: open old PR #136 and #137 are superseded documentation drafts (do not merge as application code), open draft #177 is research-only; inspect before touching.
8. **Reliability**: monitor live source completeness, frozen inference coverage, best-effort workflows; passing CI is not proof of scoring correctness, genuine user profile QA or a successful Firebase deployment.

## Sources of truth

\`docs/NBA_SEASON_LAB_V623_RELEASE.md\` through \`docs/NBA_SEASON_LAB_V628_RELEASE.md\`, workflow files, current \`data/\` JSON snapshots, and PRs #190–194. \`README.md\` and the PR #115-era roadmap contained outdated early-stage descriptions until updated separately.
