# NBA Season Lab v6.20 — Today / Transfers advice data-integrity gate

- No transfer advice until a structurally validated public NBA file is actually loaded from GitHub, a validated cache or a verified manual import. An embedded HTML seed is never automatically trusted just because its timestamp is recent.
- Only `live_sync` is eligible for transfer advice; partial/schedule-only/failed-sync sources are ineligible even when recently timestamped. The feed must be at most 24h old and not future-dated.
- Ten unique fantasy roster IDs, exact two per PG/SG/SF/PF/C, at most two per club and finite nonnegative cash are prerequisites for automatic advice, as is a complete calendar in the proposed decision window.
- Today clearly explains invalid roster/feed/calendar and hides unverified model FP. The Transfers page fails closed for Calculate, Apply to draft and Freeze journal when those prerequisites are not met. Manual history reconciliation and research tools remain accessible.
- Missing official injury update is shown as uncertainty, not a claim that players are healthy. No change to forecast weights, Sports.ru rules, Firebase, transfers or price provenance.
- Full Hosting candidate only. Publication to the existing site remains a separate owner action. Smoke and pure tests are offline/synthetic and are not proof of real Sports.ru transfer benefit.
