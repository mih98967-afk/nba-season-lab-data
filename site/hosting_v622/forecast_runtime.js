/* Validated, read-only adapter for immutable per-game model output. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.NBAForecastRuntime=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const MODEL_IDS=new Set(['near_latest','long_latest']);
 const LEVELS=['50','80','95'];
 const WARNINGS={ACTUAL_DAY_USES_FROZEN_NEXT_LEAD_CALIBRATION:'Для этого дня использована проверка ближайшего более длинного горизонта.',UNVALIDATED_LEGACY_FALLBACK:'Резервная прежняя формула: точность новой модели на неё не переносится.',LONG_LEAD_HISTORICAL_CONFIRMATION_LIMITED:'Для дальнего горизонта исторических проверок пока мало.',INTERVAL_COVERAGE_AT_THIS_DAY_NOT_VALIDATED:'Покрытие диапазона именно на этом горизонте ещё не подтверждено.',QUESTIONABLE_INTERVAL_COVERAGE_LIMITED:'Для статуса Questionable точность прогнозных диапазонов подтверждена слабее.'};
 const OFFICIAL_SOURCE=/^https:\/\/ak-static\.cms\.nba\.com\/referee\/injury\/Injury-Report_20\d\d-\d\d-\d\d_\d\d_\d\d(?:AM|PM)\.pdf$/i;
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const number=(x,d=1)=>Number.isFinite(x)?x.toLocaleString('ru-RU',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
 const stamp=x=>new Date(x).toLocaleString('ru-RU',{timeZone:'Europe/Moscow',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
 const fail=reason=>({ok:false,reason,index:new Map(),identityIndex:new Map(),feed:null});
 const identityKey=(id,team,opponent,epoch)=>[id,team,opponent,epoch].join('|');
 const reasonText=text=>/^Матч сегодня:/.test(text)?'Текущий игровой день НБА: прогноз учитывает последние игры и минуты.':text.replace(/^Горизонт (\d+) дн\.; калибровка сохранённого lead (\d+) дн\.$/,'До матча $1 дн.: роль и статус игрока ещё могут измениться.');
 function validIntervals(value){
  if(value===null||value===undefined)return true;
  if(typeof value!=='object')return false;
  let prior=null;
  for(const level of LEVELS){const pair=value[level];if(!Array.isArray(pair)||pair.length!==2||!pair.every(Number.isFinite)||pair[0]>pair[1])return false;
   if(prior&&(pair[0]>prior[0]+1e-7||pair[1]<prior[1]-1e-7))return false;prior=pair;}
  return true;
 }
 function prepare(feed){
  if(!feed||feed.schema_version!==1||feed.kind!=='nba_per_game_model_forecasts'||!Array.isArray(feed.rows))return fail('Неверный формат прогнозов');
  const issued=Date.parse(feed.issued_at_utc||''),captured=Date.parse(feed.source_capture_completed_at_utc||''),until=Date.parse(feed.valid_until_utc||'');
  if(![issued,captured,until].every(Number.isFinite)||captured>issued+1000||until<=issued)return fail('Не подтверждено время прогноза');
  if(!['ready','stale_inputs'].includes(feed.status))return fail('Состояние источников не подтверждено');
  const index=new Map(),identityIndex=new Map();
  for(const row of feed.rows){
   if(!row||typeof row!=='object')return fail('Некорректная строка прогноза');
   if(!row.player_id)continue;
   const epoch=Date.parse(row.game_utc||''),lock=Date.parse(row.lock_utc||'');
   if(typeof row.player_id!=='string'||typeof row.game_id!=='string'||!row.team||!row.opponent||!Number.isFinite(epoch)||!Number.isFinite(lock)||Math.abs(epoch-lock-1800000)>1000)return fail('Не подтверждена идентичность матча');
   const key=row.player_id+'|'+row.game_id;
   if(index.has(key))return fail('Повтор игрока и матча в прогнозе');
   const finite=[row.p_play,row.mean_if_play,row.expected_fp].every(Number.isFinite);
   if(finite){
    if(row.p_play<0||row.p_play>1||Math.abs(row.expected_fp-row.p_play*row.mean_if_play)>2e-5)return fail('Нарушено согласование FP и вероятности');
   }else if(MODEL_IDS.has(row.model_id)||row.eligible_for_decision===true)return fail('Пропущено число в доступном прогнозе');
   if(!validIntervals(row.conditional_intervals)||!validIntervals(row.unconditional_intervals))return fail('Неверные прогнозные диапазоны');
   const normalized={...row,epoch,lock,finite};
   index.set(key,normalized);
   const ik=identityKey(row.player_id,row.team,row.opponent,epoch);
   if(identityIndex.has(ik))return fail('Неоднозначная пара игрока и времени матча');
   identityIndex.set(ik,normalized);
  }
  return {ok:true,reason:'',feed,index,identityIndex,issued,captured,until};
 }
 function freshness(store,tick=Date.now()){
  if(!store?.ok)return {ok:false,reason:store?.reason||'Прогнозы загружаются'};
  if(!Number.isFinite(tick)||store.issued>tick+300000)return {ok:false,reason:'Время прогноза находится в будущем'};
  if(tick>store.until)return {ok:false,reason:'Срок актуальности прогноза истёк'};
  if(store.feed.status!=='ready')return {ok:false,reason:'Результаты последних матчей ещё не полностью обновлены'};
  return {ok:true,reason:''};
 }
 function find(store,player,game){
  if(!store?.ok||!player||!game)return null;
  const epoch=Number.isFinite(game.epoch)?game.epoch:Date.parse(game.utc||'');
  const opponent=game.home===player.team?game.away:game.away===player.team?game.home:null;
  if(!opponent||!Number.isFinite(epoch))return null;
  const r=store.index.get(player.id+'|'+game.id)||store.identityIndex.get(identityKey(player.id,player.team,opponent,epoch));
  if(!r||r.team!==player.team||r.opponent!==opponent||Math.abs(r.epoch-epoch)>1000)return null;
  return r;
 }
 function usable(store,player,game,tick=Date.now(),forDecision=false){
  if(!freshness(store,tick).ok)return null;
  const row=find(store,player,game);
  if(!row?.finite||!MODEL_IDS.has(row.model_id)||store.issued>=row.lock||row.epoch<=tick)return null;
  if(forDecision&&(row.eligible_for_decision!==true||tick>=row.lock))return null;
  return row;
 }
 function officialStatus(store,player,game,tick=Date.now()){
  if(!freshness(store,tick).ok)return null;
  const row=find(store,player,game),s=row?.official_status;
  if(!s||s.exact_player_team_game_time!==true||!['out','doubtful','questionable','probable','available'].includes(s.status))return null;
  if(![s.nba_player_id,row.nba_id].every(x=>/^[1-9]\d*$/.test(String(x??'')))||![s.nba_game_id,row.nba_game_id].every(x=>/^002\d{7}$/.test(String(x??''))))return null;
  if(String(s.nba_player_id)!==String(row.nba_id)||String(s.nba_game_id)!==String(row.nba_game_id)||s.calendar_game_id!==row.game_id||s.team!==row.team||s.home!==game.home||s.away!==game.away||Math.abs(Date.parse(s.tipoff_utc)-row.epoch)>1000)return null;
  const report=Date.parse(s.report_at_utc),available=Date.parse(s.available_at_utc),tip=Date.parse(s.tipoff_utc);
  if(![report,available,tip].every(Number.isFinite)||report>available||available>store.issued||available>tick||available>=row.lock||report>=row.lock||tip<=tick||tick-report>36*3600000)return null;
  if(!OFFICIAL_SOURCE.test(String(s.source_url||''))||!/^[a-f0-9]{64}$/i.test(String(s.source_sha256||'')))return null;
  return {status:s.status,reportEpoch:report,firstSeenEpoch:available,tipoffEpoch:tip,sourceUrl:s.source_url,sourceSha256:s.source_sha256,exact:true};
 }
 function effective(store,player,game,tick=Date.now(),resolvedOfficial=undefined){
  const row=find(store,player,game);if(!row?.finite)return null;
  const official=resolvedOfficial===undefined?officialStatus(store,player,game,tick):resolvedOfficial,out=official?.status==='out';
  return {p_play:out?0:row.p_play,mean_if_play:row.mean_if_play,expected_fp:out?0:row.expected_fp,
   unconditional_intervals:out?{'50':[0,0],'80':[0,0],'95':[0,0]}:row.unconditional_intervals,official_out:out,official};
 }
 function aggregate(rows){
  let expected=0,conditional=0,appearances=0,covered=0;
  for(const r of rows){if(!r||![r.p_play,r.mean_if_play,r.expected_fp].every(Number.isFinite))continue;
   covered++;expected+=r.expected_fp;conditional+=r.mean_if_play;appearances+=r.p_play;}
  return {expected_fp:covered===rows.length?expected:null,known_games_expected_fp:expected,conditional_sum_if_all_play:covered===rows.length?conditional:null,expected_games:covered===rows.length?appearances:null,scheduled_games:rows.length,covered_games:covered,predictive_intervals:null};
 }
 function statusText(row){
  if(!row)return 'Нет новой оценки для этого матча';
  if(row.support==='cold_start_fallback')return 'Мало подтверждённой истории';
  if(row.model_id==='legacy_seed_fallback')return 'Сохранённая оценка прежней формулы · для сравнения';
  if(row.model_id==='unavailable')return 'Недостаточно данных для оценки этого матча';
  if(['provisional_bucket_no_coverage_claim','exact_saved_lead_limited_confirmation'].includes(row.interval_status))return 'Дальний прогноз · диапазоны предварительные';
  if(row.support==='audited_lead_bucket')return 'Дальний прогноз · исторически проверенная группа горизонтов';
  if(row.actual_horizon_days>1)return 'Дальний прогноз · статус игрока ещё может измениться';
  return 'Прогноз ближайшего матча';
 }
 function gameCard(store,player,game,{tick=Date.now(),active=false,probability=null,mean=null,officialStatus:resolvedOfficial=undefined}={}){
  const row=find(store,player,game),state=freshness(store,tick);
  if(!row||!row.finite)return `<div class="model-game model-game-empty"><b>${esc(stamp(game.epoch||game.utc))} · ${esc(game.home===player.team?game.away:game.home)}</b><p>${esc(statusText(row))}. Пропуск данных не означает 0 FP.</p></div>`;
  const current=effective(store,player,game,tick,resolvedOfficial),canUse=!!usable(store,player,game,tick,true),q=Number.isFinite(probability)&&active?probability:current.p_play,mu=Number.isFinite(mean)&&active?mean:row.mean_if_play;
  const overridden=Math.abs(q-current.p_play)>1e-7||Math.abs(mu-row.mean_if_play)>1e-7;
  const conditional=row.conditional_intervals,unconditional=overridden?null:current.unconditional_intervals;
  const provisional=['provisional_bucket_no_coverage_claim','exact_saved_lead_limited_confirmation'].includes(row.interval_status);
  const title=game.home===player.team?row.opponent+' дома':'@ '+row.opponent;
  const reasons=(row.reasons||[]).filter(x=>typeof x==='string'&&!/^Свежий официальный отчёт:/.test(x)).map(reasonText).slice(0,3);
  const warnings=(row.warnings||[]).filter(x=>typeof x==='string').map(x=>WARNINGS[x]||x);
  if(!state.ok)warnings.unshift(state.reason);
  if(current.official_out)warnings.unshift('Свежий официальный OUT для этого матча: 0 FP с учётом пропуска. Это правило статуса, а не новая калибровка модели.');
  else if(current.official)warnings.unshift('Свежий официальный статус: '+current.official.status.toUpperCase()+'. Показана исходная модельная вероятность; этот статус не гарантирует выход.');
  if(overridden)warnings.unshift('Применён ваш сценарий или свежий официальный OUT. Диапазон с пропуском для него не калибровался.');
  if(tick>=row.lock)warnings.unshift('Матч закрыт для новых замен: показана ранее рассчитанная оценка.');
  const rangeTable=conditional?`<details class="model-ranges"><summary>Прогнозные диапазоны 50 / 80 / 95%</summary><p class="small">Диапазон возможных FP за один матч. ${provisional?'Для этого горизонта фактическое покрытие ещё не подтверждено.':'Калибровка проверена на истории; это не гарантия для отдельного игрока.'}</p><div class="tablewrap"><table><thead><tr><th>Уровень</th><th class="num">При выходе</th><th class="num">С учётом пропуска</th></tr></thead><tbody>${LEVELS.map(level=>`<tr><td>${level}%${provisional?' *':''}</td><td class="num">${number(conditional[level][0])} … ${number(conditional[level][1])}</td><td class="num">${unconditional?number(unconditional[level][0])+' … '+number(unconditional[level][1]):'не рассчитан'}</td></tr>`).join('')}</tbody></table></div></details>`:'<p class="small">Для этой оценки прогнозный диапазон пока не подтверждён.</p>';
  return `<article class="model-game ${!canUse?'model-game-stale':''}"><div class="model-game-heading"><div><strong>${esc(title)}</strong><span>${esc(stamp(row.epoch))} МСК</span></div><span class="model-method">${active&&canUse?'Используется в расчёте':'Для сравнения'}</span></div><div class="model-game-values"><div class="model-primary"><span>Ожидаемые FP</span><b>${number(mu*q)}</b></div><div><span>FP при выходе</span><b>${number(mu)}</b></div><div><span>Шанс выхода</span><b>${number(q*100,0)}%</b></div></div><p class="model-game-status">${esc(statusText(row))}</p>${Number.isFinite(row.recent_minutes)&&row.recent_minutes>=0&&row.recent_minutes<=48?`<p class="model-game-context">Последние игры: ${number(row.recent_minutes)} мин в среднем · фактический ориентир, не прогноз</p>`:''}${reasons.length?'<details class="model-reasons-details"><summary>Почему такой прогноз</summary><ul class="model-reasons">'+reasons.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul></details>':''}${rangeTable}${warnings.length?'<p class="model-warning">'+warnings.map(esc).join(' · ')+'</p>':''}</article>`;
 }
 function overview(store,tick=Date.now()){
  const f=freshness(store,tick);
  if(!store?.ok)return `<div class="model-feed-status"><strong>Новая модель FP и участия</strong><span>${esc(f.reason)}. Пока используется прежний расчёт.</span></div>`;
  const n=[...store.index.values()].filter(r=>MODEL_IDS.has(r.model_id)&&r.finite&&r.epoch>tick).length;
  return `<div class="model-feed-status ${f.ok?'':'model-feed-warning'}"><strong>FP и вероятность участия</strong><span>${f.ok?n+' матчевых оценок · обновлено '+esc(stamp(store.issued))+' МСК':esc(f.reason)+'. Прежний расчёт доступен отдельно.'}</span></div>`;
 }
 return {prepare,freshness,find,usable,officialStatus,effective,aggregate,gameCard,overview,statusText,validIntervals};
});
