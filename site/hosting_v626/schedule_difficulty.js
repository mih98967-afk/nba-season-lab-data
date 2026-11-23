/* Opponent context. Effect uncertainty is distinct from a game-outcome interval. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.NBAScheduleDifficulty=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const POS=['ALL','PG','SG','SF','PF','C'],DAY=86400000;
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const fmt=(v,d=1)=>Number.isFinite(v)?v.toLocaleString('ru-RU',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
 const signed=v=>Number.isFinite(v)?(v>0?'+':'')+fmt(v):'—';
 const dayText=x=>new Date(x).toLocaleDateString('ru-RU',{timeZone:'Europe/Moscow',day:'2-digit',month:'2-digit'});
 const timeText=x=>new Date(x).toLocaleTimeString('ru-RU',{timeZone:'Europe/Moscow',hour:'2-digit',minute:'2-digit'});
 function prepare(feed){
  if(!feed||!['nba_matchup_difficulty_v1','nba_matchup_difficulty'].includes(feed.schema||feed.kind)||!feed.opponents||typeof feed.opponents!=='object')return {ok:false,reason:'Сложность соперников загружается',feed:null};
  const asof=Date.parse(feed.as_of_utc||'');if(!Number.isFinite(asof))return {ok:false,reason:'Время оценки соперников не подтверждено',feed:null};
  for(const [team,positions] of Object.entries(feed.opponents)){
   if(!/^[A-Z]{2,3}$/.test(team)||!positions||typeof positions!=='object')return {ok:false,reason:'Неверная команда в оценках',feed:null};
   for(const position of POS){const r=positions[position];if(!r)continue;
    for(const key of ['general_delta_fp','position_extra_fp','total_delta_fp'])if(r[key]!==null&&r[key]!==undefined&&!Number.isFinite(r[key]))return {ok:false,reason:'Некорректная оценка сложности',feed:null};
    const ci=r.effect_interval95;if(ci!==null&&ci!==undefined&&(!Array.isArray(ci)||ci.length!==2||!ci.every(Number.isFinite)||ci[0]>ci[1]))return {ok:false,reason:'Неверный диапазон оценки эффекта',feed:null};
   }
  }
  return {ok:true,feed,asof};
 }
 function effect(store,opponent,position='ALL',tick=Date.now()){
  if(!store?.ok||!POS.includes(position)||store.asof>tick+300000||tick-store.asof>72*3600000)return null;
  const r=store.feed.opponents[opponent]?.[position];
  if(!r||!Number.isFinite(r.total_delta_fp)||r.status==='unavailable'||r.status==='insufficient_data')return null;
  const ci=r.effect_interval95,uncertain=Array.isArray(ci)&&ci[0]<=0&&ci[1]>=0;
  const tone=uncertain||Math.abs(r.total_delta_fp)<.1?'neutral':r.total_delta_fp>0?'easier':'harder';
  return {...r,opponent,position,uncertain,tone};
 }
 function describe(store,games,team,position,start,days){
  const end=start+days*DAY,seen=new Set(),list=[];
  for(const g of games||[]){const epoch=Number.isFinite(g.epoch)?g.epoch:Date.parse(g.utc||'');
   if(!Number.isFinite(epoch)||epoch<start||epoch>=end||!([g.home,g.away].includes(team))||['final','postponed','cancelled','canceled'].includes(String(g.status||'').toLowerCase()))continue;
   const opponent=g.home===team?g.away:g.home,key=[team,opponent,epoch].join('|');if(seen.has(key))continue;seen.add(key);
   list.push({game:g,epoch,opponent,away:g.away===team,effect:effect(store,opponent,position,start)});
  }
  list.sort((a,b)=>a.epoch-b.epoch);
  const available=list.filter(g=>g.effect),total=available.reduce((s,g)=>s+g.effect.total_delta_fp,0);
  return {team,games:list,count:list.length,covered:available.length,average:list.length&&available.length===list.length?total/list.length:null,known_average:available.length?total/available.length:null,effect_interval95:null};
 }
 function tooltip(r){if(!r)return 'Недостаточно данных для оценки соперника';
  const n=r.effective_games??r.weighted_player_games;
  return 'Отклонение от среднего соперника: '+signed(r.total_delta_fp)+' FP за выход. Общий контекст: '+signed(r.general_delta_fp)+'; позиционная добавка: '+signed(r.position_extra_fp)+'. '+
   (Array.isArray(r.effect_interval95)?'Приблизительный 95% диапазон оценки эффекта: '+signed(r.effect_interval95[0])+' … '+signed(r.effect_interval95[1])+'. ':'')+
   (Number.isFinite(n)?'Эффективных наблюдений: '+fmt(n,0)+'. ':'')+
   (Number.isFinite(r.current_season_n_games)?'Матчей в текущем сезоне: '+fmt(r.current_season_n_games,0)+'. ':'')+
   (r.predictive_validated?'Прогностическая проверка пройдена.':'Описательная оценка: прибавка к точности FP пока не доказана.');
 }
 function chip(store,opponent,position,tick){const r=effect(store,opponent,position,tick);return `<span class="difficulty-chip difficulty-${r?.tone||'missing'}" title="${esc(tooltip(r))}">${r?signed(r.total_delta_fp):'н/д'}${r&&!r.predictive_validated?' *':''}</span>`;}
 function panel(store,{games=[],teams=[],clubs={},position='ALL',days=14,sort='easiest',onlyOwned=false,ownedTeams=[],tick=Date.now(),calendarComplete=false,calendarReason='',showAll=false}={}){
  const selected=POS.includes(position)?position:'ALL',length=[7,14,21,28].includes(days)?days:14;
  const eligible=teams.map(t=>typeof t==='string'?t:t.team).filter(t=>!onlyOwned||ownedTeams.includes(t));
  const rows=eligible.map(team=>describe(store,games,team,selected,tick,length));
  rows.sort((a,b)=>sort==='games'?b.count-a.count||a.team.localeCompare(b.team):sort==='name'?a.team.localeCompare(b.team):(a.average===null&&b.average===null?0:a.average===null?1:b.average===null?-1:sort==='hardest'?a.average-b.average:b.average-a.average)||a.team.localeCompare(b.team));
  const ready=store?.ok&&store.asof<=tick+300000&&tick-store.asof<=72*3600000;
  const validated=ready&&rows.some(r=>r.games.some(g=>g.effect?.predictive_validated===true));
  const available=rows.filter(r=>r.average!==null);
  const best=available.length?[...available].sort((a,b)=>b.average-a.average)[0]:null;
  const head=best?`По выбранной оценке легче окно у ${esc(clubs[best.team]||best.team)}: <b>${signed(best.average)} FP за выход</b>, ${best.count} ${calendarComplete?'матчей':'известных матчей'}.`:'Для выбранных условий пока нет полной оценки сложности.';
  const displayed=showAll?rows:rows.slice(0,10),hiddenCount=rows.length-displayed.length;
  const fixtureCard=g=>`<div class="difficulty-fixture difficulty-${g.effect?.tone||'missing'}" title="${esc(tooltip(g.effect))}"><span class="difficulty-fixture-date">${dayText(g.epoch)} · ${timeText(g.epoch)}</span><b>${g.away?'@ ':''}${esc(g.opponent)}</b><span>${g.effect?signed(g.effect.total_delta_fp)+' FP':'н/д'}${g.effect&&!g.effect.predictive_validated?' *':''}</span></div>`;
  const fixtureList=r=>r.games.length
   ?`<div class="difficulty-fixtures">${r.games.slice(0,4).map(fixtureCard).join('')}${r.games.length>4?`<details class="difficulty-fixtures-more"><summary>Ещё ${r.games.length-4} матчей</summary><div class="difficulty-fixtures">${r.games.slice(4).map(fixtureCard).join('')}</div></details>`:''}</div>`
   :'<span class="small">Нет известных матчей в окне</span>';
  return `<section class="card difficulty-card" aria-label="Сложность календаря"><div class="titledetail"><div><h2>Сложность ближайших соперников</h2><p class="small">Выбери позицию своего игрока. Плюс означает больше FP против этого соперника относительно среднего, минус — меньше.</p></div></div><div class="difficulty-controls"><label>Позиция игрока<select id="difficulty-position">${POS.map(p=>`<option value="${p}" ${p===selected?'selected':''}>${p==='ALL'?'Все позиции':p}</option>`).join('')}</select></label><div class="difficulty-period" role="group" aria-label="Горизонт календаря">${[7,14,21,28].map(d=>`<button type="button" data-difficulty-days="${d}" class="${d===length?'selected':''}" aria-pressed="${d===length}">${d} дней</button>`).join('')}</div><label>Порядок команд<select id="difficulty-sort"><option value="easiest" ${sort==='easiest'?'selected':''}>Сначала легче</option><option value="hardest" ${sort==='hardest'?'selected':''}>Сначала сложнее</option><option value="games" ${sort==='games'?'selected':''}>Больше матчей</option><option value="name" ${sort==='name'?'selected':''}>По названию</option></select></label><label class="horizontal"><input type="checkbox" id="difficulty-owned" ${onlyOwned?'checked':''}>Мои клубы</label></div><div class="difficulty-verdict"><p>${head}</p><span>${validated?'Общий контекст из прошедшей проверку модели; порядок отдельных клубов отдельно не валидирован.':'Скорректированная история и модельный контекст. Дополнительная прогностическая польза не подтверждена.'} Количество матчей учитывается отдельно от сложности.</span></div>${!ready?`<div class="info warning">${esc(store?.reason||'Оценки сложности устарели или недоступны')}. Расписание остаётся доступным.</div>`:''}${!calendarComplete?`<div class="info warning">${esc(calendarReason||'Полнота календаря не подтверждена')}. Показаны только известные матчи; это не полный итог окна.</div>`:''}<div class="difficulty-legend"><span class="difficulty-chip difficulty-easier">+ FP · легче</span><span class="difficulty-chip difficulty-harder">− FP · сложнее</span><span class="difficulty-chip difficulty-neutral">Эффект неясен</span><span class="small">* позиционная оценка ещё не улучшает прогноз автоматически</span></div><div class="tablewrap difficulty-table-wrap"><table class="difficulty-table"><thead><tr><th>Клуб игрока</th><th class="num">Игр</th><th class="num">Среднее<br>FP / выход</th><th>Ближайшие матчи · время МСК</th></tr></thead><tbody>${displayed.map(r=>`<tr class="${ownedTeams.includes(r.team)?'difficulty-owned-row':''}"><th scope="row"><b>${esc(r.team)}</b><small>${esc(clubs[r.team]||r.team)}</small></th><td class="num">${r.count}</td><td class="num"><strong>${signed(r.average)}</strong>${r.covered<r.count?`<small>${r.covered}/${r.count} оценено</small>`:''}</td><td>${fixtureList(r)}</td></tr>`).join('')||'<tr><td colspan="4">В составе пока нет клубов для этого фильтра.</td></tr>'}</tbody></table></div>${hiddenCount?`<div class="difficulty-footer"><span class="small">Показаны первые ${displayed.length} команд</span><button type="button" class="button" data-action="difficulty-toggle-more">Показать все ${rows.length} команд</button></div>`:showAll&&rows.length>10?'<div class="difficulty-footer"><span class="small">Показаны все команды</span><button type="button" class="button" data-action="difficulty-toggle-more">Свернуть до 10</button></div>':''}<details class="difficulty-method"><summary>Как рассчитано и насколько уверенно</summary><p>Общая оценка соперника учитывает качество игроков, ожидаемые минуты и темп. Позиционная добавка описывает отклонение для выбранной позиции после этих поправок; малые выборки сглаживаются к среднему.</p><p>Среднее за период — среднее матчевых оценок, а не сумма будущих FP. Приблизительный 95% диапазон в подсказке относится к оценке эффекта соперника, а не к результату игрока в матче. Его фактическое покрытие отдельно не подтверждено. Если он пересекает ноль, направление эффекта неясно.</p><p>Исторические fantasy-позиции взяты из ростеров соответствующих сезонов. Дата их выгрузки известна, но их наличие перед каждым старым матчем не доказано. Неподтверждённая позиционная поправка не меняет модель FP и советы по заменам. Общий контекст соперника уже учтён внутри новой модели; число из этой таблицы не нужно ещё раз прибавлять к прогнозу игрока.</p>${ready?`<p class="small">Срез: ${esc(dayText(store.asof))} ${esc(timeText(store.asof))} МСК. Последние результаты: ${esc(store.feed.latest_outcome_date||'неизвестно')}.</p>`:''}</details></section>`;
 }
 return {prepare,effect,describe,chip,panel,tooltip,POSITIONS:POS};
});
