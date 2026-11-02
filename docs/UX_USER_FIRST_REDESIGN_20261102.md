# NBA Season Lab — user-first UX audit and redesign brief (2026-11-02)

Status: DESIGN PROPOSAL, not deployed. Existing Hosting v6.17 retained, no model/scoring/Firestore mutations.

## Method and limitations
- Inspected actual v6.17 ZIP HTML/CSS/JS, 8 tab routes.
- Rendered all eight screens at 1440×900 and 390×844 in headless Chromium, with empty local account and a synthetic 10-player roster.
- Offline source seed lacks verified updated live calendar/history. Missing FP shown in screenshots is not proof that production lacks forecasts.
- No horizontal viewport overflow observed, but narrow-screen top nav hides later routes.
- No end-to-end tests on real owner account, cloud data, actual Sports.ru quota or authenticated production UI.

## Product goal
An NBA newcomer should answer three questions without basketball knowledge:
1. What should I do today: KEEP, TRANSFER NOW, WAIT or CHECK A RISK?
2. Why? How does this decision change expected points over the same window?
3. How reliable is the evidence and what real-world check must I make?

## Findings by route
1. Team: four top-level metrics precede decisions; quota numbers are hypothetical. Court is useful but two big graphical courts consume vertical space. Keep court, surface risk and next action; move audit and technical status to details.
2. Players: dozens of rows and jargon-heavy options before concrete recommendations; show shortlist with position, team, upcoming games, recent verified minutes, risk, price provenance, reason and meaningful uncertainty. Preserve comprehensive search in expandable mode.
3. Calendar: games ≠ fantasy difficulty. Add context: verified opponent strength, rest days, consecutive days (back-to-back), home/away and opponent fantasy FP allowed if independently verified. Provide relative descriptive groups only when verified/sufficient sample; otherwise 'difficulty unknown'. Never declare more games = automatically better.
4. History: standalone raw multi-season FP tables have low everyday value. Integrate per-player form/stability into player detail; advanced table stays accessible.
5. Statuses: official vs Telegram separation is sound. Push actionable roster risk to Today/Team, preserve source timestamp and injury semantics. UNKNOWN is not available or DNP.
6. Transfers: task segmentation is a good start. Start with recommendation ranked KEEP/NOW/LATER with same horizon and pair, source quality, quota/cash eligibility and expected FP difference (not empirically proven profit). Hide multi-target/budget tools in advanced.
7. Data/prices: model estimate vs owner verified must remain visibly distinct; use contextual editing and one central diagnostics area.
8. Profile: move into Settings with backup and safe reset.

## Proposed 5-route navigation
Today (daily briefing, risk, one decision) | Team (roster/court and constraints) | Transfers (KEEP/NOW/LATER recommendation) | Calendar (quantity + independently grounded difficulty) | Players (decision-oriented discovery).
Secondary route: Settings (account, prices, sources, score reconciliation, detailed research/debugging). Historical match tables and official status archive remain available via player/team detail and settings, not deleted.

## Trust and decision contract
- Separate OBSERVED: completed NBA boxscore, verified Sports.ru owner testimony, and independently timestamped official injury.
- ESTIMATED: forecast FP, approximate prices, P(play) proxy, conditional minutes, synthetic scenario intervals.
- NOT VERIFIED: actual Sports.ru credited gain, full-population P(play) calibration, reliable future injury status, true quota reset without owner evidence.
- Every recommendation must display horizon, as-of timestamp, ranked alternatives, source recency, reason + risk + decision action; refuse pseudo-precise confidence/green 'safe' badge.
- Don't show a 'match difficulty' scalar before tested methodology and minimum schedule/strength coverage. If built, validate opponent pace / FP conceded, position sensitivity, injury/team context and sample bias against independent outcome.
- Preserve all pure calculations, no automatic transfers. Protect private roster, personal cash and transaction history from the public GitHub repo.

## Visual design direction (inspired by Claude, not an official copy)
Warm ivory background, restrained warm brown/terracotta action color, subtle border/surface contrast, generous whitespace and clear typographic rhythm. Prefer a Cyrillic-capable modern sans for text, balanced display serif only for select headings when verified licensed and available; progressive font fallback and no external font dependency required for functionality.
Color has semantic use only (injury / real blockers / valid provenance), no decorative gradients, badge overload or excessive cards.
Simplify navigation, line length, labels, and controls; keep content left aligned and accessible; provide dark/contrast/responsive QA.

## Acceptance tests
- At 390 and 320px all 5 primary destinations visible without sideways nav scrolling.
- In under 15 seconds user identifies next actionable step, one prominent primary CTA per task, no unanswered technical acronym before glossary.
- 10 player fantasy slots retained, correct club/position validation, no bench implication.
- Cross-page navigation preserves intent from player -> planner -> calendar.
- Missing source never becomes zero games, zero FP or 'healthy'.
- All forecast display distinguishes model projections from Sports.ru credited points.
- Comparative recommendations have consistent baseline, horizon and transaction assumptions, real user must approve actual move on Sports.ru.
- CI and mobile/desktop authenticated smoke tests pass, no paid services.

## Ordered implementation
P0: navigation + Today + decision hierarchy and flags; verify production data freshness before any unqualified recommendation.
P1: novice-friendly Transfers + why/reliability and warning explanations; simplify Team/Players.
P2: verified Calendar difficulty, schedule density/rest and player-specific interpretation; validate before ranking.
P3: Settings consolidation, typography polish, contextual guides, production usability checks.

## Owner input desired
Primary opening task, default evaluation window, risk style, preferred decision explanation depth, phone vs desktop use. Do not infer agreement to deploy from this brief.
