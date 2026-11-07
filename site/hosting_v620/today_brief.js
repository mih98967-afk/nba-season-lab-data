/* v6.18 — user-first read-only daily decision brief.
 * No forecast model, score or Sports.ru transaction is changed here.
 * The module never claims calibrated probability, difficulty, or real transfer gain.
 */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.NBATodayBrief = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const finite = x => typeof x === 'number' && Number.isFinite(x);
  const decisionTitles = {
    keep: 'По модели выгоднее пока сохранить состав',
    later: 'По модели есть смысл рассмотреть замену позже',
    now: 'По модели найден вариант замены сейчас',
    multi_slot: 'По модели найден план из нескольких замен',
    same_slot_chain: 'По модели найдена цепочка замен'
  };
  function build(x = {}) {
    const complete = x.rosterCount === 10 && x.rosterValid !== false;
    const fresh = x.feedVerified === true && finite(x.feedAgeHours) && x.feedAgeHours >= 0 && x.feedAgeHours <= 24 && x.feedMode === 'live_sync';
    const shortOK = x.calendar7 === true;
    const longOK = x.calendar21 === true;
    const riskNames = Array.isArray(x.officialRiskNames) ? x.officialRiskNames.filter(s => typeof s === 'string' && s) : [];
    const manualOutCount = Number.isInteger(x.manualOutCount) && x.manualOutCount >= 0 ? x.manualOutCount : 0;
    const telegramCount = Number.isInteger(x.telegramCount) && x.telegramCount >= 0 ? x.telegramCount : 0;
    const hasResults = complete && fresh && shortOK && longOK && x.resultFresh === true &&
      x.bestExplanationVerified === true && x.bestRoute && decisionTitles[x.bestRoute.kind];
    if (x.rosterCount === 10 && x.rosterValid === false) return {
      state: 'fix_roster', title: 'Сначала проверь свой состав',
      description: 'В составе нарушено одно из правил: по два игрока каждой позиции, без дублей и максимум два из клуба.',
      reasons: ['Исправь состав перед сравнением замен.', 'Сервис не изменяет состав на Sports.ru.'],
      action: 'Перейти к команде', showForecast: false, hasResults: false,shortFP:null,longFP:null,games7:null,games21:null
    };
    if (x.rosterCount === 10 && x.rosterValid !== false && x.cashReady === false) return {
      state: 'fix_roster', title: 'Сначала проверь кассу',
      description: 'Остаток средств должен быть подтверждён и неотрицателен, прежде чем сравнивать стоимость замен.',
      reasons: ['Уточни кассу со Sports.ru перед планированием.', 'Сервис не выполняет трансферы автоматически.'],
      action: 'Перейти к команде', showForecast: false, hasResults: false,shortFP:null,longFP:null,games7:null,games21:null
    };
    if (!complete) return {
      state: 'onboarding', title: 'Сначала добавь свою десятку',
      description: 'Без состава нельзя оценить твой календарь и сравнить варианты замен.',
      reasons: ['Нужны по два игрока каждой fantasy-позиции.', 'Сервис не меняет состав на Sports.ru.'],
      action: 'Перейти к команде', showForecast: false, hasResults: false,shortFP:null,longFP:null,games7:null,games21:null
    };
    let state = 'review', title = 'Стоит ли делать замену сегодня?',
      description = 'Сравни оставить состав, заменить сейчас или подождать. Пока это сценарии модели, а не доказанная выгода.';
    const reasons = [];
    if (!fresh) {
      state = 'blocked'; title = 'Сначала обнови статистику NBA';
      description = 'Без свежих данных решение о замене не стоит принимать по расчёту.';
      reasons.push('Последняя версия статистики недоступна или старше 24 часов.');
    }
    if (!shortOK || !longOK) {
      if (state !== 'blocked') { state = 'blocked'; title = 'Сначала проверь полноту календаря';
        description = 'Недостаточно данных, чтобы честно сопоставить 7 и 21 день.'; }
      reasons.push(!shortOK ? 'Не подтверждён полный календарь на 7 дней.' : 'Не подтверждён полный календарь на 21 день.');
    }
    if (riskNames.length || manualOutCount) {
      if (state !== 'blocked') {
        state = 'risk'; title = 'Сначала проверь риски своего состава';
        description = 'Статус игрока нужно уточнить до покупки или продажи, даже если модель показывает прирост FP.';
      }
      if (riskNames.length) reasons.unshift('Официальный NBA-отчёт: требует внимания ' + riskNames.slice(0,2).join(', ') + (riskNames.length > 2 ? ' и другие' : '') + '.');
      else reasons.unshift('Вручную отмечены как OUT: ' + manualOutCount + '. Это не независимое подтверждение NBA.');
    } else if (telegramCount) {
      reasons.push('Есть ' + telegramCount + ' неофициальных сигналов о твоих игроках: проверь источник.');
    }
    if (x.officialFeedReady === false) {
      reasons.push('Актуальность официальных NBA Injury Reports не подтверждена: проверь статусы перед покупкой.');
    }
    if (hasResults && state === 'review') {
      state = 'scenario'; title = decisionTitles[x.bestRoute.kind];
      description = 'Сценарное сравнение за 21 день, а не гарантия результата. Проверь цены и ограничения перед действием.';
      reasons.unshift('Сравнивались KEEP / NOW / LATER на одном горизонте.');
    }
    if (fresh && shortOK && longOK && !reasons.some(s => s.includes('календар'))) {
      reasons.push('Расписание на 7 и 21 день доступно; число игр само по себе не означает лёгких соперников.');
    }
    reasons.push('Свободные замены, реальные цены и разблокировки подтверждаются на Sports.ru.');
    return {
      state, title, description, reasons: reasons.slice(0,3),
      action: 'Сравнить KEEP / NOW / LATER',
      hasResults: Boolean(hasResults),
      showForecast: fresh,
      shortFP: fresh && shortOK && finite(x.fp7) ? x.fp7 : null,
      longFP: fresh && longOK && finite(x.fp21) ? x.fp21 : null,
      games7: shortOK && Number.isInteger(x.games7) && x.games7 >= 0 ? x.games7 : null,
      games21: longOK && Number.isInteger(x.games21) && x.games21 >= 0 ? x.games21 : null
    };
  }
  return { build };
});
