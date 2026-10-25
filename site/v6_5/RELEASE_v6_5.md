# NBA Season Lab v6.5 — calendar by tour (Moscow week grouping)

A direct continuation of v6.4. Full Hosting package includes the existing funded-target-transfer planner and all existing account isolation functionality.

## Calendar UX

- **По турам** is the new default. A display "tour" is Monday 00:00 through next Monday 00:00 **Europe/Moscow**, anchored at 19 Oct 2026. This is NOT a claim that the official Sports.ru site uses these exact tour numbers or reset instants.
- Each tour has a labeled weekly header, seven Moscow date columns, and a colored **Игр** count column. **Всего** sums the selected tours. Matchups show **@** for away, clock time in Moscow and the source B2B marker.
- Show 1, 2, 3, 4, or 6 tours; jump to a week, move back/forward, reset to the current tour; sort by team or total fixture count; filter to user's clubs. Table scrolls horizontally on mobile and keeps team names sticky.
- **Окно дат** is still available unchanged. The two viewing modes are UI-only and do not affect actual rosters, draft, executed transfers, cash or cloud state.
- Verified public schedule is authoritative. Unassigned NBA Cup fixtures are not invented. If the data are incomplete or old, the calendar explicitly warns. Zero means "no match in the currently loaded fixture list", not a guaranteed off-day.

## Verification

- Node deterministic tour tests: 17 PASS; Moscow midnight/week boundary, crossing months/year, game deduplication, only-my-club filter, B2B per team, postponed fixtures.
- Node syntax check app/calendar/budget modules; existing funded transfer package tests also pass.
- Isolated Playwright Chromium at 1360 and 390 px: tour table rows and grouped headers, sorting, 6-tour range, selected start, next/current navigation, own-clubs filter, original 21-day date window, no JavaScript errors, no page-wide overflow.
- Verified that roster, cash, executed transfers and draft do not change when switching calendar views. No real Firebase, Sports.ru or external account accessed during QA.

## Publish (user action only)

Upload **one ZIP** `NBA_Season_Lab_v6_5_Tour_Calendar.zip` to existing Firebase project's Cloud Shell and execute:

```bash
unzip -qo ~/NBA_Season_Lab_v6_5_Tour_Calendar.zip -d ~ && cd ~/nba-season-lab-deploy && firebase deploy --only hosting --project nba-season-lab
```

After `Deploy complete!` open https://nba-season-lab.web.app, verify **v6.5** in header, open **Календарь → По турам**, select 2–6 tours and switch to **Окно дат**. Do not do any real Sports.ru transfers during this test.

No paid API, Lovable credits, Firebase Blaze, new project or Firestore writes.
