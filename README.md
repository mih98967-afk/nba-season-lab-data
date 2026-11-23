# NBA Season Lab — публичные данные и существующий сервис

**Действующая публикация, подтверждённая владельцем 23.11.2026: v6.28.** Сайт: https://nba-season-lab.web.app. Репозиторий: \`mih98967-afk/nba-season-lab-data\`, ветка \`main\`. Firebase проект \`nba-season-lab\`, бесплатный Spark.

Здесь хранятся публичные NBA/Sports.ru-совместимые вычислительные данные, исследовательский код, проверки, отчёты и исходники последовательных Hosting-версий. **Репозиторий не содержит личный состав пользователя, баланс, персональные Sports.ru начисления и частные резервные копии.** Не путайте общедоступные NBA boxscore FP с фактически зачисленными Sports.ru очками.

## Актуальное продолжение работы

[Полный технический handoff после опубликованной v6.28](docs/handoffs/20261123_AFTER_PR194/00_README_FIRST.md) — точка входа для новых чатов и следующей разработки; включает [готовое и незавершённое](docs/handoffs/20261123_AFTER_PR194/01_DELIVERED_VS_OPEN.md), [приоритеты и критерии](docs/handoffs/20261123_AFTER_PR194/02_PRIORITIES_AND_GATES.md), [границы релизов и приватности](docs/handoffs/20261123_AFTER_PR194/03_RELEASE_BOUNDARIES.md). Релизные изменения: \`docs/NBA_SEASON_LAB_V623_RELEASE.md\` … \`docs/NBA_SEASON_LAB_V628_RELEASE.md\`.

- Исходники опубликованной v6.28: \`site/hosting_v628/\`; тесты и процедура выпуска: \`.github/workflows/hosting-v628.yml\` и \`scripts/build_hosting_v628.py\`.
- \`src/sync.py\` и \`.github/workflows/nba-sync.yml\` поддерживают публичный NBA feed на best-effort расписании; \`data/live.json\`, \`data/model_forecasts_v1.json\` и \`data/matchup_difficulty_v1.json\` — существующие, регулярно проверяемые/обновляемые источники. Расписание/данные/модель могут иметь разные времена обновления.
- Сайт использует интегрированные снимки публичной статистики и прогнозов, но это **не** прямое автоматическое чтение пользовательских начислений Sports.ru.
- Реальные данные могут быть неполны: отсутствие игрока в boxscore не доказывает DNP; неопределённость обозначается \`UNKNOWN\` / «н/д»; модельный прирост FP не является доказанной выгодой реальной замены.
- Исследовательские минуты, альтернативные вероятности участия и новые веса остаются \`adopt_on_site=false\` до независимой проверки.
- Успешный workflow или merged PR **не публикует** новую версию сайта: только владелец вручную загружает проверенный полный Hosting ZIP в уже существующий Firebase-проект.

## Источники

- Официальное расписание NBA: https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json
- Официальные NBA boxscores: https://cdn.nba.com/static/json/liveData/boxscore/boxscore_0022600002.json
- ESPN NBA scoreboard как проверяемый резервный источник: https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard

**Старинные документы:** \`docs/NBA_SEASON_LAB_ACTIVE_ROADMAP.md\` и \`docs/NBA_SEASON_LAB_CONTINUATION_20261105.md\` сохраняются как история; они не определяют текущую опубликованную версию.
