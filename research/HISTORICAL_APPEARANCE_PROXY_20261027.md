# Historical appearance frequency: scope and safety

Sports.ru NBA Season Lab **already uses historical played-game FP** from 2023/24–2025/26 and historical weekly player outcomes (2024/25 dev, 2025/26 test). Prospective p_play PR #34 was based on current-season explicitly verified outcomes only, since old positive-minute archive does not contain authoritative full game-day active or inactive NBA rosters.

New research evaluates a **different proxy target**: did the selected, recently active player have a positive-minute log for a fixture of their last *observed* team? A missing record is **not** a verified DNP, not a zero FP, and not evidence of team membership. Team membership is inferred before the game from played logs, and newly transferred / long-absent players are often excluded.

Exact historical UTC game starts are matched to independent ESPN scoreboard for 2024/25 and 2025/26. Only preceding performances construct features. Parameters are chosen on 2024/25; 2025/26 is frozen holdout. Outputs report selected-sample Brier, log-loss, player-cluster intervals and calibration without claims of real p_play calibration.

No site deploy, personal account, price/cash/transfers, paid APIs, or Firebase Blaze. Research status `research_only_not_deployed`, `adopt_on_site=false`. Do not feed retrospective selected-sample estimates directly into live p_play until independent game-day roster/DNP coverage is proven.
