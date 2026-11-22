# NBA Season Lab — handoff after PR #183 (20 November 2026)

**Purpose:** restore the existing Sports.ru Fantasy NBA 2026/27 project in a fresh ChatGPT conversation; do not restart development. This public copy contains **no private owner roster, cash, credited FP, transfer history, backups, or Firestore records**. The owner has a separate fuller private ZIP.

## Authoritative current state (verify live again)

- Repository: `mih98967-afk/nba-season-lab-data` (`main`), Hosting: https://nba-season-lab.web.app, Firebase project: `nba-season-lab` / Spark.
- Last user-confirmed live Hosting: **v6.22**. Prepared **v6.23**: PR [#183](https://github.com/mih98967-afk/nba-season-lab-data/pull/183) MERGED, complete Hosting ZIP from [successful CI run 44621295677](https://github.com/mih98967-afk/nba-season-lab-data/actions/runs/44621295677); **owner has NOT confirmed v6.23 deploy**. Never equate PR merge, CI, or an artifact with deployment.
- Snapshot of `main` observed on 20 November 2026: `d5126840026d16a4189d604b0aa840a058b9bd3a`, following automatic research-only data commits *after* PR #183. Reinspect `main`, Actions, and model freshness at the start of every new session.
- v6.23 build paths: `site/hosting_v623/`, `scripts/build_hosting_v623.py`, `.github/workflows/hosting-v623.yml`. Historic frozen v6.22 source: `site/hosting_v622/`.
- Read detailed release notes: [v6.23 release](../../NBA_SEASON_LAB_V623_RELEASE.md), [minutes and UX](../../NBA_SEASON_LAB_V623_MINUTES_UX.md), [frozen future minutes protocol](../../NBA_MINUTES_FUTURE_PREREG_20261120.json).

## What is already delivered

**Match-level model (since v6.21):** matchup-aware Ridge estimates FP conditional on playing; calibrated CatBoost estimates P(play); LightGBM produces conditional/unconditional FP intervals for supported leads. `expected_fp = p_play * mean_if_play`; official exact timely OUT is a separate overlay. The original model is retained as explicitly labelled comparison/fallback; EWMA recency remains an unselected research challenger. Public model schema: `research_extension/production_20261118/CONTRACT.md`; live source `data/model_forecasts_v1.json`. Never double-apply P(play) or opponent effects, sum game-level predictive interval endpoints into a week, or substitute UNKNOWN with zero.

**Opponent difficulty (since v6.21):** general opponent and PG/SG/SF/PF/C groups, 7/14/21/28-day horizons, descriptive ratings, uncertainty, calendar games and filters. The additional positional component is *not* accepted as a numerical adjustment to forecast FP. Source `data/matchup_difficulty_v1.json`, UI `site/hosting_v623/schedule_difficulty.js`.

**UX v6.22 (PR #181, user-confirmed deployment):** Claude-like warm neutral hierarchy, primary expected FP first in game cards, shorter player cards; optional historical/medical detail disclosure; adaptive opponent calendar without wide whole-page horizontal scroll; 10 teams first and 4 games per team initially with expand controls; quick access to difficulty from Today; hidden-by-default optional research journal. Tested at desktop/tablet/mobile widths with synthetic and actual public-data Chromium QA.

**Optimizer UX v6.23 (PR #182–183):** clearer prominent verdict/action and short 2–3 reasons, compact secondary stats, consistent warm palette, without modifying the computational engines. Optimizer supports KEEP/NOW/LATER, multi-target and chained plans, protected KEEP, manual draft, prices/limits/timing; **its financial/real-credit edge is not yet proven**.

## Expected minutes — research, not production

- Older played-only prospective matched cohort: 1,688 forecasts; 1,337 verified played outcomes over 106 NBA games and 16 ET dates; 94 explicit DNP excluded, 180 UNKNOWN not imputed, 77 awaiting. Mean absolute minutes error 6.3928 baseline vs 5.2233 challenger (paired gain 1.1695 minutes; about 18.3%). This does not validate a full scheduled fantasy population, player-level minute intervals, P(play), unconditional FP, or transfer gains.
- The live app may show actual recent minutes and a historical/catalog minute guide; those are **not** a validated `E(minutes | plays)` forecast.
- A **preregistered future-only** immutable comparison is frozen in `docs/NBA_MINUTES_FUTURE_PREREG_20261120.json`: issue times from **2026-11-21 00:00:00 UTC inclusive to 2026-12-08 00:00:00 UTC exclusive**. No backfill, no cutoff retuning. Validate precise first-seen feature clocks and individual T−30; use matched verified positive-minute outcomes only, keeping DNP/UNKNOWN/pending separate. Exploratory report gate: ≥12 ET dates, ≥60 games, ≥600 verified played pairs, ≥0.5 minutes MAE advantage and ET-date-cluster 95% CI lower>0. Even passing it **cannot auto-promote** research to the site without a separate representative population/decision gate. Evaluator: `scripts/evaluate_minutes_prereg_v623.py`.

## Next work, in priority order

1. Check actual GitHub data/Actions, and distinguish **confirmed Hosting v6.22** from **prepared v6.23**. Never reuse an expired ZIP snapshot as fresh public data; secure exact-byte model/parity and actual browser QA for a renewed release.
2. Observe the newly frozen minutes prospective window, with independent chronological evidence and no future leakage. Consider position, role, minutes strata, same-club sample and selection effects; do not rewrite the preregistered rules after outcomes.
3. Build the full player×game participation denominator and rigorous injury OUT/DNP/UNKNOWN evidence. Test whether minutes information improves unconditional fantasy FP *and real decisions*, not only played-only MAE.
4. Audit true KEEP/NOW/LATER value against owner-verified Sports.ru credited FP, actual prices, quota, T−30 and ownership windows in **private** mode; do not publish owner observations to GitHub.
5. Continue user-first UX: **«Нужно ли сегодня делать замены?»** → concise KEEP/NOW/LATER → 2–3 reasons → clear action, then details. Keep Today/Transfers/Team/Calendar/Players, clear data freshness, readable compact cards, responsive positional calendar. No gratuitous navigation expansion.

## Hard constraints

Existing project only; no new Firebase, GitHub repo, Lovable project or optimizer. No paid APIs, Lovable credits, Blaze, paid Actions, automatic Sports.ru transfers, unauthorized personal Firestore writes or publication of private files. All research challengers remain `adopt_on_site=false` until independent gates; UNKNOWN is never silently DNP or 0. Only owner deploys a fully verified ZIP with one existing Firebase Cloud Shell command. A CI PASS with synthetic guest is not a live private-profile acceptance.

**Beware:** the repository root `README.md` and `docs/NBA_SEASON_LAB_ACTIVE_ROADMAP.md` cover older milestones (v6.9 / PR #115). They are historical background, not the latest status.
