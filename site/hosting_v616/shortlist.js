/* NBA Season Lab — read-only shortlist at the scheduled transfer time.
 * Pure comparison; does not write Firestore or execute any Sports.ru action.
 * The underlying FP model is scenario-based and must not be presented as calibrated.
 */
(function(root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.NBAShortlist = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';
  const DAY = 86400000;
  function rank(options) {
    const {out, available, players, candidates, draft, whenEpoch, nowEpoch,
      cash, priceOf, validateDraft, coverage, project, countGames} = options || {};
    const failure = reason => ({ready:false, reason, rows:[], checked:0, eligible:0, excluded:{}});
    if (!Number.isFinite(whenEpoch) || !Number.isFinite(nowEpoch)) return failure('Укажите точную дату и время замены');
    if (whenEpoch < nowEpoch - 60000) return failure('Дата замены уже в прошлом');
    if (!Array.isArray(available) || !available.includes(out) || !players?.[out]) return failure('Сначала выберите игрока своего состава');
    if (!Number.isFinite(cash) || cash < 0) return failure('Неизвестна доступная касса');
    if (typeof priceOf !== 'function' || typeof validateDraft !== 'function' || typeof project !== 'function'
        || typeof coverage !== 'function' || typeof countGames !== 'function') return failure('Нет данных для расчёта');
    const start = Math.max(nowEpoch, whenEpoch);
    const end7 = start + 7 * DAY, end14 = start + 14 * DAY;
    const check7 = coverage(start, 7), check14 = coverage(start, 14);
    if (!check7?.ok || !check14?.ok) return failure('Неполный календарь: ' + (check7?.reason || check14?.reason || 'требуется проверка'));
    const keep7 = project(draft, start, end7), keep14 = project(draft, start, end14);
    if (!Number.isFinite(keep7) || !Number.isFinite(keep14)) return failure('Базовый прогноз состава недоступен');
    const sell = Number(priceOf(out));
    if (!Number.isFinite(sell) || sell < 0) return failure('Неизвестна цена продажи');
    const excluded = {}, rows = [];
    const seen = new Set();
    for (const p of candidates || []) {
      if (!p?.id || seen.has(p.id)) continue;
      seen.add(p.id);
      if (!players[p.id] || players[p.id].pos !== players[out].pos || available.includes(p.id)) {
        excluded.position_or_roster = (excluded.position_or_roster || 0) + 1;
        continue;
      }
      const buy = Number(priceOf(p.id));
      if (!Number.isFinite(buy) || buy < 0) {
        excluded.unknown_price = (excluded.unknown_price || 0) + 1;
        continue;
      }
      const proposed = {out, in_:p.id, epoch:whenEpoch, sell, buy};
      const plan = [...(draft || []), proposed];
      const checked = validateDraft(plan);
      if (!checked?.valid) {
        excluded.rule_violation = (excluded.rule_violation || 0) + 1;
        continue;
      }
      const plan7 = project(plan, start, end7), plan14 = project(plan, start, end14);
      if (!Number.isFinite(plan7) || !Number.isFinite(plan14)) {
        excluded.missing_forecast = (excluded.missing_forecast || 0) + 1;
        continue;
      }
      const n7 = countGames(p.id, start, 7), n14 = countGames(p.id, start, 14);
      rows.push({id:p.id, team:p.team, pos:p.pos, price:buy,
        gain7:plan7-keep7, gain14:plan14-keep14,
        games7:Number.isFinite(n7)?n7:null, games14:Number.isFinite(n14)?n14:null,
        warnings:checked.warnings || [], newCash:checked.cash});
    }
    rows.sort((a,b) => b.gain14-a.gain14 || b.gain7-a.gain7 || a.id.localeCompare(b.id));
    const max = Number.isInteger(options.max) ? Math.min(20,Math.max(1,options.max)) : 5;
    return {ready:true, start, keep7, keep14, checked:seen.size, eligible:rows.length,
      excluded, rows:rows.slice(0,max)};
  }
  return {rank};
});
