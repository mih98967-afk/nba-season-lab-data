# NBA Season Lab v6.6 — US game dates, period totals and full team matrix

**Continuation** of confirmed v6.5, not a new application. Current user state and Firebase project are untouched. This release retains the expensive-player funding planner, personal Firestore isolation and all existing tabs.

## Changes in Calendar

- **Tour assignments use the NBA league date (America/New_York, ET)** with daylight saving transitions handled by `Intl.DateTimeFormat` and Monday–Sunday ET weeks. A game starting at 01:00 Moscow on Monday can be part of Sunday in the USA and is shown in the previous tour. This is a carefully labeled *display grouping*, not a claim about the Sports.ru official score-reset rules.
- **Visible Moscow times** inside each game cell; `+1` indicates that the Moscow date is one day after the American NBA date in the column heading. `@` means away.
- **TOTAL GP** for the entire selected period is the **second column**, immediately after team. Both columns stay visible during horizontal browsing. Individual weekly totals remain at the end of each displayed tour.
- **All 30 clubs** appear in one continuous table: compact single-line fixtures and **no separately vertically scrolling inner table**. Horizontal scrolling of game-day columns is still available for long periods, especially on mobile.
- **Sort by total GP** across the whole selected span: descending (default), ascending or alphabetic. The sorting scope is the entire window, not just the first week.
- **Tours:** choose any 1–12 consecutive tours and jump backward, forward or to current NBA week.
- **Arbitrary day window:** choose **date from**, **date to** and optionally specify any integer number of days (from 1 up to the available regular-season remainder, maximum 185), with dates inclusive. Go to previous or next window.
- Count only real published fixtures in the selected range, never fill the 30 unassigned NBA Cup games. Separate source-quality warnings remain.
- Date selection, filtering and sorting do **not** affect fantasy team, saved cash, transfer history, draft plans, personal Firestore or backend.

## Test evidence

- Pure Node module tests check ET vs MSK Monday boundary, both US daylight saving changes, Sunday-to-Monday transitions, real vs duplicate fixtures, tour limits and user-selected day windows.
- Full-calendar test intended for GitHub Actions uses `data/schedule.json` (1200 validated published games, 30 teams) and ensures counts sum to 2400 player-team fixture appearances without invented games.
- Isolated Chromium (source HTML, CSS, JS; no access to real accounts), viewport 1440x1000 and mobile 390x844: 30 rows in both modes, no separately vertical scrolling calendar, sticky first two columns when horizontal scrolling, real 26 Oct 01:00 Moscow Sunday ET placement, flexible 5/10-day windows and both sorting directions, zero JavaScript page errors and no mutations to the guest roster/transfer journal.
- Existing expensive-target-transfer functionality is not changed. The new build uses only public static data and no paid APIs.

## Publish — user's explicit action only

Download **one** `NBA_Season_Lab_v6_6_Calendar_Fixes.zip`, upload it into the Cloud Shell of the existing Firebase project `nba-season-lab` (Spark) and run:

```bash
unzip -qo ~/NBA_Season_Lab_v6_6_Calendar_Fixes.zip -d ~ && cd ~/nba-season-lab-deploy && firebase deploy --only hosting --project nba-season-lab
```

After `Deploy complete!` open https://nba-season-lab.web.app, confirm **v6.6** on the header, open **Календарь**: check Sunday ET / Monday Moscow, 30 clubs, totals immediately after team name, sorting and **Любой диапазон дат**.

## Research

`research_only_not_deployed` / `adopt_on_site=false` remains in effect for medical/prospective experimental models; this UI-only update does not touch them. No changes to Sports.ru prices, real transfers, KHL/NHL or accounts.
