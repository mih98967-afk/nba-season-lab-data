# NBA Season Lab — continuation after published v6.28 (23 November 2026)

**Continue the existing Sports.ru Fantasy NBA 2026/27 service. Do not restart.** This is a public technical handoff; it has no owner roster, bank, credited fantasy FP, personal transfers, backup or Firestore records.

## Verified starting point

- Live site: https://nba-season-lab.web.app. **v6.28 published, confirmed by owner.**
- Existing repository: https://github.com/mih98967-afk/nba-season-lab-data ; observed main at handoff: \`6a3038ab5c4f1d04fcc1d575018df09d5d39b53e\`. Always re-check current main before changing it.
- Release [PR #194](https://github.com/mih98967-afk/nba-season-lab-data/pull/194) merged, merge commit \`87b5c2b8e862871d0d52eda99a70823202075750\`. Research [PR #193](https://github.com/mih98967-afk/nba-season-lab-data/pull/193) merged. Subsequent automated research/data commits do **not** mean a new Hosting release.
- Released source: \`site/hosting_v628/\`; corresponding builder \`scripts/build_hosting_v628.py\`, workflow \`.github/workflows/hosting-v628.yml\`, and \`docs/NBA_SEASON_LAB_V628_RELEASE.md\`.
- Existing Firebase project: \`nba-season-lab\`, Spark. **Owner alone manually deploys a fully validated Hosting ZIP.** PR merge, data sync and Hosting deployment are three different events.

## Read in order

1. [Delivered versus unfinished](01_DELIVERED_VS_OPEN.md).
2. [Priorities and scientific gates](02_PRIORITIES_AND_GATES.md).
3. [Privacy and release boundaries](03_RELEASE_BOUNDARIES.md).
4. Frozen scientific protocol: \`docs/NBA_MINUTES_FUTURE_PREREG_20261120.json\`, and v6.23–v6.28 release notes.

Previous public handoff: \`docs/handoffs/20261120_AFTER_PR183/00_README_FIRST.md\`; it described an earlier v6.22/v6.23 state and should **not** be treated as the current deployed version. \`docs/NBA_SEASON_LAB_ACTIVE_ROADMAP.md\` is historical PR #115-era planning, not an up-to-date implementation map.

Do not confuse Sports.ru individual **credited** FP with NBA-calculated fantasy points. Retain P(play)/DNP/UNKNOWN distinctions, source timestamps and current model validity checks. No KHL/NHL code, paid services, automatic Sports.ru transfers or personal state changes.
