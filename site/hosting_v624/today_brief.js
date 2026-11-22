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
  // Read-only interpretation of a *verified* bounded scenario, not an
  // independent outcome estimate or an independently proven market price.
  function modelReasons(route, days) {
    if (!route || !['keep','now','later','multi_slot','same_slot_chain'].includes(route.kind) ||
        !Array.isArray(route.moves) || !Number.isInteger(days) || ![7,14,21,28].includes(days)) return [];
    const signed = value => (value > 0 ? '+' : '') + (Math.round(value * 10) / 10).toFixed(1);
    const count = route.moves.length;
    if (route.kind === 'keep') {
      if (count !== 0 || !finite(route.gain) || !finite(route.net) ||
          Math.abs(route.gain) > 1e-6 || Math.abs(route.net) > 1e-6) return [];
      return ['KEEP: в ограниченном поиске не найден сценарий выше сохранения состава после условного резерва за ходы.'];
    }
    if (count < 1 || count > 4 || !finite(route.gain) || !finite(route.net) ||
        route.net > route.gain + 1e-6 || !route.moves.every(m => m && finite(m.epoch))) return [];
    const reserve = route.gain - route.net;
    return [
      'Разница с KEEP за ' + days + ' дней: ' + signed(route.gain) +
        ' модельных FP до условного резерва, не реальные начисления Sports.ru.',
      count + (count === 1 ? ' замена' : count >= 2 && count <= 4 ? ' замены' : ' замен') +
        '; условный резерв ' + signed(reserve) + ' FP; оценка после резерва ' +
        signed(route.net) + ' FP. Это эвристика, не доказанная цена хода.'
    ];
  }
  function build(x = {}) {
    const complete = x.rosterCount === 10 && x.rosterValid !== false;
    const fresh = x.feedVerified === true && finite(x.feedAgeHours) && x.feedAgeHours >= 0 && x.feedAgeHours <= 24 && x.feedMode === 'live_sync';
    const shortOK = x.calendar7 === true;
    const longOK = x.calendar21 === true;
    const riskNames = Array.isArray(x.officialRiskNames) ? x.officialRiskNames.filter(s => typeof s === 'string' && s) : [];
    const manualOutCount = Number.isInteger(x.manualOutCount) && x.manualOutCount >= 0 ? x.manualOutCount : 0;
    const telegramCount = Number.isInteger(x.telegramCount) && x.telegramCount >= 0 ? x.telegramCount : 0;
    const hasResults = complete && fresh && shortOK && x.resultFresh === true &&
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
    if (!shortOK) {
      if (state !== 'blocked') { state = 'blocked'; title = 'Сначала проверь полноту календаря';
        description = 'Нет подтверждённого расписания на ближайшую неделю.'; }
      reasons.push('Не подтверждён полный календарь на 7 дней.');
    }
    if (shortOK && !longOK) reasons.push('На 21 день календарь неполный: дальний прогноз скрыт, ближайшая неделя доступна.');
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
      // A same-day multi-slot or chain route needs the same owner market
      // checks as a single NOW move. Deferred LATER remains hypothetical.
      const hasMove = Array.isArray(x.bestRoute.moves) && x.bestRoute.moves.length > 0;
      const needsImmediateMarket = x.bestRoute.kind === 'now' ||
        (hasMove && (x.firstMoveSoon === true || x.historicalQuotaTimesUnverified === true));
      if (needsImmediateMarket && x.marketReady !== true) {
        state = 'market'; title = 'По модели есть замена сейчас — проверь Sports.ru';
        description = 'Потенциальный прирост FP рассчитан, но реальная цена, касса и доступность хода требуют сверки.';
        reasons.unshift(x.marketReason || 'Не подтверждены обе цены и реальный остаток замен.');
      } else {
        state = 'scenario'; title = decisionTitles[x.bestRoute.kind];
        description = 'Сценарное сравнение за ' + (x.resultDays === 7 ? 7 : 21) + ' дней, не гарантия результата. Перед ходом проверь цены.';
        reasons.unshift('Сравнивались KEEP / NOW / LATER на одном горизонте.');
      }
    }
    // Only emit numeric explanations after the original reconciliation gate.
    // Keep warnings first; the final brief remains at most three reasons.
    if (hasResults && (state === 'scenario' || state === 'market')) {
      const numeric = modelReasons(x.bestRoute, x.resultDays);
      if (numeric.length) reasons.push(...numeric);
    }
    if (hasResults && typeof x.modelCaution === 'string' && x.modelCaution)
      reasons.push(x.modelCaution);
    if (fresh && shortOK && longOK && !reasons.some(s => s.includes('календар')) &&
        !hasResults) {
      reasons.push('Расписание на 7 и 21 день доступно; число игр само по себе не означает лёгких соперников.');
    }
    reasons.push('Свободные замены, реальные цены и разблокировки подтверждаются на Sports.ru.');
    // In numeric cases show the specific FP/transfer trade-off and one safety
    // caveat; avoid replacing the actionable explanation with boilerplate.
    const selected = hasResults && (state === 'scenario' || state === 'market') ?
      [...(state === 'market' ? reasons.slice(0,1) : []),
       ...reasons.filter(r => r.includes('Injury Reports') ||
         r.includes('неофициальных сигналов') || r === x.modelCaution),
       ...reasons.filter(r => r.startsWith('Разница с KEEP') || r.startsWith('KEEP:') ||
         r.includes('условный резерв')),
       ...reasons.filter(r => !r.startsWith('Разница с KEEP') && !r.startsWith('KEEP:') &&
         !r.includes('условный резерв'))] : reasons;
    return {
      state, title, description, reasons: [...new Set(selected)].slice(0,3),
      action: 'Сравнить KEEP / NOW / LATER',
      hasResults: Boolean(hasResults),
      showForecast: fresh,
      shortFP: fresh && shortOK && finite(x.fp7) ? x.fp7 : null,
      longFP: fresh && longOK && finite(x.fp21) ? x.fp21 : null,
      games7: shortOK && Number.isInteger(x.games7) && x.games7 >= 0 ? x.games7 : null,
      games21: longOK && Number.isInteger(x.games21) && x.games21 >= 0 ? x.games21 : null
    };
  }
  const minute = 60000;
  const day = 86400000;

  // A route is an as-of scenario. A model route must never silently survive its
  // calculation age, planned start, changed roster or failed public preflight.
  function freshScenario({result, calculatedAt, nowMs, signature, horizonDays, preflightReady} = {}) {
    if (preflightReady !== true || !finite(nowMs) || !finite(calculatedAt) ||
        calculatedAt > nowMs || nowMs-calculatedAt > 30*minute ||
        !result || result.ready !== true || result.signature !== signature ||
        result.horizonDays !== horizonDays || !finite(result.start) ||
        result.start < nowMs-minute || !Array.isArray(result.routes) || !result.routes.length)
      return null;
    const best = result.routes[0];
    if (!best || !Array.isArray(best.moves) || best.moves.some(m =>
      !m || !finite(m.epoch) || m.epoch < nowMs-minute)) return null;
    return result;
  }

  // The date alone can sometimes prove which fantasy week a transfer belongs
  // to. Its numeric placeholder epoch NEVER does. A Moscow calendar date
  // represents the closed-open interval [00:00 MSK, next 00:00 MSK).
  // If the interval straddles EITHER reset hypothesis, fail closed.
  function moscowDateInterval(value) {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
    const start = Date.parse(value+'T00:00:00+03:00');
    if (!finite(start) || new Date(start+3*3600000).toISOString().slice(0,10)!==value) return null;
    return {start,end:start+day};
  }
  function quotaSnapshot(executed, nowMs, weekAt15, weekAt00) {
    const unknown = {known:false,used15:null,used00:null,
      independentSportsruVerification:false,source:'private_history_only'};
    if (!Array.isArray(executed)||!finite(nowMs)||
        typeof weekAt15!=='function'||typeof weekAt00!=='function')
      return {...unknown,reason:'История и границы недели не подтверждены.'};
    const current15=weekAt15(nowMs),current00=weekAt00(nowMs);
    if (!current15||!current00) return {...unknown,reason:'Граница недели неизвестна.'};
    let used15=0,used00=0,dated=0;
    for (const t of executed) {
      if (!t || typeof t!=='object') return {...unknown,reason:'Некорректная операция в истории.'};
      let earliest,latest;
      if (t.timePrecision==='date_only'||t.epochIsPlaceholder===true) {
        // Trust only the explicitly owner-entered Sports.ru Moscow DATE,
        // never a reconstructed timestamp. No date => no safe inference.
        const interval=moscowDateInterval(t.sportsRuDateMoscow);
        if (!interval||interval.start>nowMs)
          return {...unknown,reason:'Неизвестна подтверждённая дата прежней замены.'};
        earliest=interval.start;
        latest=Math.min(interval.end-1,nowMs);
        dated++;
      } else {
        if (!finite(t.epoch)||t.epoch>nowMs+minute)
          return {...unknown,reason:'Есть операция без допустимого фактического времени.'};
        earliest=latest=t.epoch;
      }
      const a15=weekAt15(earliest),b15=weekAt15(latest);
      const a00=weekAt00(earliest),b00=weekAt00(latest);
      if (!a15||!b15||!a00||!b00)
        return {...unknown,reason:'Граница недели для операции не определена.'};
      // A historical date may straddle a *past* reset without changing the
      // answer for the CURRENT week. Unknown only when membership in the
      // current week differs between the two possible execution times.
      const in15a=a15===current15,in15b=b15===current15;
      const in00a=a00===current00,in00b=b00===current00;
      if (in15a!==in15b||in00a!==in00b)
        return {...unknown,reason:'Дата замены пересекает одну из границ текущей недели: часы неизвестны.'};
      if (in15a) used15++;
      if (in00a) used00++;
    }
    return {known:true,used15,used00,date_only_assigned_without_hour:dated,
      independentSportsruVerification:false,source:'private_history_only',
      reason:'Только распределение записей по неделям; реальный остаток сверяй на Sports.ru.'};
  }

  // Show at most four games elsewhere, but compute the lock from the entire
  // eligible seven-day schedule, skipping games already locked or finished.
  function nextRosterLock(games, roster, players, nowMs, horizonDays=7) {
    if (!Array.isArray(games) || !Array.isArray(roster) || !players ||
        !finite(nowMs) || !finite(horizonDays) || horizonDays <= 0) return null;
    let earliest = null;
    for (const game of games) {
      if (!game || !finite(game.epoch) || game.status === 'final' ||
          game.epoch > nowMs + horizonDays*day) continue;
      const lockAt = game.epoch - 30*minute;
      if (lockAt <= nowMs) continue;
      const playerIds = roster.filter(id => {
        const team = players[id]?.team;
        return team && (team === game.home || team === game.away);
      });
      if (!playerIds.length) continue;
      if (!earliest || lockAt < earliest.lockAt) {
        earliest = {lockAt, tipoffAt:game.epoch, gameId:game.id||null,
          home:game.home,away:game.away,playerIds};
      }
    }
    return earliest;
  }
  return {build,freshScenario,quotaSnapshot,nextRosterLock};
});
