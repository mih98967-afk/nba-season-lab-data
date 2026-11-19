/* v6.20 — shared fail-closed preflight for Today and automatic transfer advice.
 * Pure and read-only: neither a forecast model nor a Sports.ru quota validator.
 * Validated source age never proves price, club affiliation or injury status.
 */
(function(root,factory){
 'use strict';
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 root.NBAAdviceReadiness=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const POS=['PG','SG','SF','PF','C'];
 function inspect(x={}){
  const reasons=[];
  const roster=x.roster;
  const players=x.players;
  let rosterReady=Array.isArray(roster)&&roster.length===10&&new Set(roster).size===10&&players&&typeof players==='object';
  if(rosterReady){
   const pos=Object.fromEntries(POS.map(k=>[k,0])),clubs={};
   for(const id of roster){
    const p=players[id];
    if(!p||!POS.includes(p.pos)||typeof p.team!=='string'||!p.team){rosterReady=false;break;}
    pos[p.pos]++;
    clubs[p.team]=(clubs[p.team]||0)+1;
   }
   if(rosterReady&&(POS.some(k=>pos[k]!==2)||Object.values(clubs).some(n=>n>2)))rosterReady=false;
  }
  if(!rosterReady)reasons.push('Состав не подтверждён: нужны 10 разных игроков, по два на позицию и максимум два из клуба.');
  const cashReady=typeof x.cash==='number'&&Number.isFinite(x.cash)&&x.cash>=0;
  if(!cashReady)reasons.push('Касса неизвестна или некорректна.');
  const updated=typeof x.feed?.updated_at_utc==='string'?Date.parse(x.feed.updated_at_utc):NaN;
  const age=Number.isFinite(x.nowEpoch)&&Number.isFinite(updated)?(x.nowEpoch-updated)/3600000:null;
  const feedReady=x.sourceVerified===true&&x.feed?.mode==='live_sync'&&age!==null&&age>=0&&age<=24;
  if(!feedReady)reasons.push('Нет подтверждённого NBA live-среза за последние 24 часа. Обновите данные.');
  const calendarReady=x.calendarReady===true;
  if(!calendarReady)reasons.push('Полный календарь на выбранный период не подтверждён.');
  const startReady=Number.isFinite(x.startEpoch)&&Number.isFinite(x.nowEpoch)&&x.startEpoch>=x.nowEpoch-60000;
  if(!startReady)reasons.push('Время начала расчёта уже прошло.');
  return {ready:!!(rosterReady&&cashReady&&feedReady&&calendarReady&&startReady),
   rosterReady:!!rosterReady,cashReady,feedReady,calendarReady,startReady,feedAgeHours:age,reasons};
 }
 return {inspect};
});
