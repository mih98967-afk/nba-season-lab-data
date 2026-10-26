/* NBA Season Lab v6.7: read-only reconstruction of recorded Sports.ru transfers.
 * No network, browser storage, Firestore, team mutations, or automatic trades.
 * Replays recorded and newly backfilled moves in chronological order.
 */
(function(root,factory){
  'use strict';
  const api=factory();
  if(typeof module==='object' && module.exports)module.exports=api;
  root.NBATransferHistory=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const MAX_NEW=12, WEEK_CAP=3, MAX_CASH=100000;
  const msHour=3600000;
  function safeNumber(v){
    if(v===null||v===undefined||String(v).trim()==='')return NaN;
    const x=Number(v);
    return Number.isFinite(x)&&x>=0&&x<=MAX_CASH?x:NaN;
  }
  function weekKey(ms,hour=15){
    if(!Number.isFinite(ms))return null;
    const d=new Date(ms+3*msHour-hour*msHour);
    if(!Number.isFinite(d.getTime()))return null;
    d.setUTCDate(d.getUTCDate()-(d.getUTCDay()+6)%7);
    return d.toISOString().slice(0,10);
  }
  function matchSet(a,b){
    return a.length===b.length && new Set(a).size===a.length &&
      new Set(b).size===b.length && a.every(id=>b.includes(id));
  }
  function positionErrors(roster,players){
    const errors=[];
    if(!Array.isArray(roster)||roster.length!==10||new Set(roster).size!==10)
      return ['Историческая десятка отсутствует, неполная или содержит дубликаты'];
    const counts={PG:0,SG:0,SF:0,PF:0,C:0};
    for(const id of roster){
      const p=players?.[id];
      if(!p||!(p.pos in counts))errors.push('Неизвестный игрок или позиция в исходной десятке');
      else counts[p.pos]++;
    }
    for(const [pos,n] of Object.entries(counts))if(n!==2)errors.push('В историческом составе должно быть два игрока '+pos);
    return [...new Set(errors)];
  }
  function prepare(items,source){
    return items.map((t,index)=>({
      epoch:Number(t?.epoch),out:t?.out,in_:t?.in_,sell:safeNumber(t?.sell),buy:safeNumber(t?.buy),
      index,source,original:t
    }));
  }
  function sortMoves(items){
    return items.slice().sort((a,b)=>a.epoch-b.epoch||
      (a.source==='existing'?0:1)-(b.source==='existing'?0:1)||a.index-b.index);
  }
  function validateMove(move,now,initialEpoch){
    const errors=[];
    if(!Number.isFinite(move.epoch)||move.epoch<initialEpoch||move.epoch>now)
      errors.push('Не указана прошедшая дата после начала исходного состава');
    if(!Number.isFinite(move.sell)||!Number.isFinite(move.buy))
      errors.push('Нужны реальные неотрицательные цены покупки и продажи');
    if(typeof move.out!=='string'||!move.out||typeof move.in_!=='string'||!move.in_)
      errors.push('Выберите обоих игроков');
    return errors;
  }
  function replay(initial,items,players,openingCash,now,initialEpoch){
    const errors=[],warnings=[],timeline=[],used={},altUsed={},seen=new Set();
    let roster=[...initial],cash=openingCash;
    const sorted=sortMoves(items);
    for(const move of sorted){
      const localErrors=validateMove(move,now,initialEpoch);
      const signature=move.epoch+'|'+move.out+'|'+move.in_;
      if(seen.has(signature))localErrors.push('Повтор одной и той же операции в журнале');
      seen.add(signature);
      const out=players[move.out],incoming=players[move.in_];
      if(!out||!incoming)localErrors.push('Игрок отсутствует в базе');
      if(!roster.includes(move.out))localErrors.push('OUT не находился в составе в этот момент');
      if(roster.includes(move.in_))localErrors.push('IN уже находился в составе в этот момент');
      if(out&&incoming&&out.pos!==incoming.pos)localErrors.push('Нужно сохранять fantasy-позицию');
      const week=weekKey(move.epoch),alt=weekKey(move.epoch,0);
      if(week){used[week]=(used[week]||0)+1;if(used[week]>WEEK_CAP)localErrors.push('Больше трёх замен за неделю '+week);}
      if(alt){altUsed[alt]=(altUsed[alt]||0)+1;}
      const nextCash=cash+move.sell-move.buy;
      if(!Number.isFinite(nextCash)||nextCash<-.000001)localErrors.push('Отрицательная касса на историческом шаге');
      let nextRoster=roster.slice();
      const at=nextRoster.indexOf(move.out);
      if(at!==-1)nextRoster[at]=move.in_;
      if(localErrors.length){errors.push(...localErrors);break;}
      if(positionErrors(nextRoster,players).length){errors.push('Нарушены позиции десятки на историческом шаге');break;}
      roster=nextRoster;cash=nextCash;
      timeline.push({epoch:move.epoch,source:move.source,index:move.index,
        out:move.out,in_:move.in_,sell:move.sell,buy:move.buy,
        cashBefore:cash-move.sell+move.buy,cashAfter:cash,week,
        rosterAfter:[...roster]});
    }
    if(Object.values(altUsed).some(v=>v>WEEK_CAP))
      warnings.push('Проверьте сброс недельного лимита Sports.ru около понедельника 15:00 МСК');
    return {valid:errors.length===0,errors:[...new Set(errors)],warnings,roster,cash,
      timeline,used,altUsed};
  }
  function preview(input){
    const errors=[],warnings=[];
    const players=input?.players||{};
    const initial=input?.initialRoster, current=input?.currentRoster;
    const existing=input?.existing,proposed=input?.proposed;
    const now=input?.nowEpoch,initialEpoch=input?.initialEpoch;
    if(!Number.isFinite(now)||!Number.isFinite(initialEpoch))errors.push('Неизвестно время исходного состава');
    if(!Array.isArray(initial)||!Array.isArray(current)||!Array.isArray(existing)||!Array.isArray(proposed))
      errors.push('История состава отсутствует или повреждена');
    if(errors.length)return {valid:false,errors,warnings};
    errors.push(...positionErrors(initial,players),...positionErrors(current,players));
    if(!proposed.length||proposed.length>MAX_NEW)errors.push('Введите от одной до 12 прошлых замен');
    if((input.draftCount||0)>0)errors.push('Сначала сохраните или очистите черновик: он будет зависеть от новой истории');
    const cash=safeNumber(input.currentCash);
    if(!Number.isFinite(cash))errors.push('Текущая касса не подтверждена');
    const old=prepare(existing,'existing');
    const added=prepare(proposed,'new');
    const oldDelta=old.reduce((v,m)=>v+m.sell-m.buy,0);
    const newDelta=added.reduce((v,m)=>v+m.sell-m.buy,0);
    const opening=cash-oldDelta;
    if(!Number.isFinite(opening)||opening<-.000001||opening>MAX_CASH)
      errors.push('Невозможно восстановить кассу по уже записанным операциям');
    if(errors.length)return {valid:false,errors:[...new Set(errors)],warnings};
    const oldResult=replay(initial,old,players,opening,now,initialEpoch);
    if(!oldResult.valid)errors.push('Уже записанная история противоречива: '+oldResult.errors.join(' · '));
    if(!matchSet(oldResult.roster,current))errors.push('Текущий состав не совпадает с восстановленной историей; изменения заблокированы');
    if(Math.abs(oldResult.cash-cash)>0.00001)errors.push('Текущая касса не согласуется с журналом');
    if(errors.length)return {valid:false,errors,warnings};
    const merged=replay(initial,[...old,...added],players,opening,now,initialEpoch);
    errors.push(...merged.errors);
    warnings.push(...merged.warnings);
    if(!Number.isFinite(cash+newDelta)||cash+newDelta<-.000001||cash+newDelta>MAX_CASH)
      errors.push('Итоговая касса вышла за допустимые границы');
    const teamCounters={};
    for(const id of merged.roster){const t=players[id]?.team;if(t)teamCounters[t]=(teamCounters[t]||0)+1;}
    if(Object.values(teamCounters).some(v=>v>2))errors.push('Итоговый состав нарушает лимит двух игроков из клуба');
    // Historical club membership can differ from TODAY's catalog, do not fabricate historical eligibility.
    warnings.push('Касса в прошлом восстановлена из сегодняшнего остатка; ручные корректировки прошлого не известны');
    warnings.push('Историческая принадлежность игроков клубам и разблокировки должны быть сверены на Sports.ru');
    const newExecuted=added.map(m=>({...m.original,epoch:m.epoch,out:m.out,in_:m.in_,sell:m.sell,buy:m.buy,
      origin:'manual_history_backfill',recordedAt:new Date(now).toISOString()}));
    const mergedItems=[...existing.map(x=>({...x})),...newExecuted].map((x,i)=>({x,i,source:i<existing.length?'existing':'new'}));
    mergedItems.sort((a,b)=>a.x.epoch-b.x.epoch||
      (a.source==='existing'?0:1)-(b.source==='existing'?0:1)||a.i-b.i);
    return {valid:errors.length===0,errors:[...new Set(errors)],warnings:[...new Set(warnings)],
      currentCash:cash,cash:cash+newDelta,deltaCash:newDelta,impliedOpeningCash:opening,
      roster:merged.roster,mergedExecuted:mergedItems.map(q=>q.x),newExecuted,
      timeline:merged.timeline,used:merged.used,stepsAdded:added.length};
  }
  /** What players should be offered as OUT at a historical moment? Read-only. */
  function rosterBefore(input,at,index){
    if(!Array.isArray(input?.initialRoster)||!Number.isFinite(at))return [];
    const items=sortMoves([
      ...prepare(Array.isArray(input.existing)?input.existing:[],'existing'),
      ...prepare(Array.isArray(input.proposed)?input.proposed:[],'new').filter(m=>m.index!==index)
    ]);
    const roster=[...input.initialRoster];
    for(const m of items){
      if(!Number.isFinite(m.epoch)||m.epoch>at)continue;
      if(m.epoch===at&&m.source==='new'&&m.index>index)continue;
      const i=roster.indexOf(m.out);
      if(i!==-1&&!roster.includes(m.in_))roster[i]=m.in_;
    }
    return roster;
  }
  return {preview,rosterBefore,weekKey};
});
