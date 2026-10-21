# NBA Season Lab — общие данные

Этот открытый репозиторий **не содержит личных составов, логинов или паролей**. Они остаются в Firebase Auth/Firestore.

## Текущий этап

- `src/sync.py`: собирает официальный календарь и законченные box score NBA, рассчитывает FP по правилам Sports.ru.
- `.github/workflows/nba-sync.yml`: обновление раз в 4 часа + ручной запуск из Actions.
- `data/live.json`: появится после **успешного** первого запуска.
- Публичный сайт https://nba-season-lab.web.app **пока не читает этот репозиторий автоматически**. Для этого нужен следующий шаг интеграции с Firebase Hosting. Не путайте успех workflow с обновлением сайта.
- Трёхсезонный подробный импорт и Telegram будут подключены отдельными проверяемыми задачами; их ещё нельзя считать запущенными.

## Первый запуск

Откройте вкладку **Actions** → **NBA public data sync** → **Run workflow** → зелёная кнопка **Run workflow**. Дождитесь завершения. Если красный крест — откройте failed step и передайте его текст в чат. Не включайте платные тарифы и не добавляйте секреты.

## Источники

- Official NBA: https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json
- Official NBA box scores: https://cdn.nba.com/static/json/liveData/boxscore/boxscore_0022600002.json
- ESPN scores fallback for identifying final games: https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard
- Starter catalog: https://nba-season-lab.web.app/data/base.json

**Принцип качества:** только финальные матчи, полный набор полей; если источники недоступны, не подставлять фиктивные нули. Игровые цены и позиции Sports.ru не берутся из API NBA. Полноту live feed следует проверить после первого запуска.
