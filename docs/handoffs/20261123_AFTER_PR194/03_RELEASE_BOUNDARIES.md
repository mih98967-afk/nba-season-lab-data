# Non-negotiable technical and privacy boundaries

- One existing repository \`mih98967-afk/nba-season-lab-data\`, existing Hosting \`nba-season-lab.web.app\` and existing Firebase project \`nba-season-lab\` / Spark. Do not create a second service, migrate to Blaze, spend paid API/Lovable/Actions credits or import KHL/NHL logic.
- No automatic Sports.ru transfers, no automatic deploy, no writes to personal Firestore, bank, roster, purchase prices, executed replacements, owner score checkpoints, saved settings or private archives without explicit owner instruction and audit.
- Public repo handoffs and PRs MUST exclude personal roster, bank, private player-level credited FP and exact personal transfer history/backup. Owner-only exports remain local/private. Never infer missing data as explicit DNP or certified zero score.
- Production v6.28 is immutable until owner opts into a separately verified full Hosting candidate. Research-only \`adopt_on_site=false\` for minutes, historical proxies, challenger rates, full P(play) population or economic effects.
- Frozen decisions: exact game-specific T-30; \`expected_fp = p_play * mean_if_play\` only once; official timely OUT is separate and expires; treat missing/partial NBA Cup calendar as incomplete, not 0; never sum independent game-level predictive interval bounds as a calibrated week interval.
- “Model exact-match coverage” is evidence availability, not accuracy. Actual Sports.ru credited scores and roster cash are NOT authenticated via public NBA boxscores. Selected played-only gains are NOT unconditional fantasy gains.
- Current root \`README.md\` and \`docs/NBA_SEASON_LAB_ACTIVE_ROADMAP.md\` have historical stages; prefer release documents, this handoff, PR status and real-time source checks.
