/* NBA Season Lab v6.4: expensive-target funded transfer packages.
 * Read-only, deterministic and bounded. Never makes real Sports.ru transfers.
 * Earlier financing moves must pass at EVERY step before the target purchase.
 * Exact prices, per-player unlock and current quota require Sports.ru review.
 */
(function(root,factory){
 'use strict';
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 root.NBABudgetPackage=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const DAY=86400000;
 const finite=x=>typeof x==='number'&&Number.isFinite(x);
 const fail=(reason,extras={})=>({ready:false,reason,routes:[],...extras});
 const idcmp=(a,b)=>String(a).localeCompare(String(b));
 const KEY=p=>p.out+'>'+p.in_;
 const weekKey=epoch=>{
  const d=new Date(epoch+3*3600000),n=(d.getUTCDay()+6)%7;
  d.setUTCHours(0,0,0,0);d.setUTCDate(d.getUTCDate()-n);
  return d.toISOString().slice(0,10);
 };
 function solve(options){
  const o=options||{};
  const {players,roster,candidates,existingDraft=[],nowEpoch,whenEpoch,
   horizonDays=14,maxMoves=3,opportunityPenalty=4,targetId,forcedOutId=null,
   priceOf,validateDraft,coverage,scorePlayer,project,
   isCandidateAvailable=()=>true,isBlocked=()=>false,maxRoutes=7}=o;
  if(![7,14,21,28].includes(horizonDays)||![0,4,8].includes(opportunityPenalty)||
    ![1,2,3].includes(maxMoves)||!finite(nowEpoch)||!finite(whenEpoch)||
    whenEpoch<nowEpoch-60000||!Array.isArray(roster)||roster.length!==10||
    new Set(roster).size!==10||!players||
    [priceOf,validateDraft,coverage,scorePlayer,project,isCandidateAvailable,isBlocked].some(f=>typeof f!=='function'))
   return fail('Проверьте время, состав, горизонт и настройки поиска.');
  if(!Array.isArray(existingDraft)||existingDraft.some(m=>!finite(m?.epoch)||m.epoch>whenEpoch))
   return fail('Новые ходы должны идти после уже существующих шагов черновика.');
  const source=coverage(whenEpoch,horizonDays);
  if(!source?.ok)return fail('Календарь неполон: '+(source?.reason||'нет данных'));
  const current=validateDraft(existingDraft);
  if(!current?.valid||!Array.isArray(current.roster)||current.roster.length!==10||
     !finite(current.cash)||current.cash<0)
   return fail('Сначала исправьте текущую десятку, кассу или черновик.');
  const target=players[targetId],starting=current.roster;
  if(!target||!target.forecast||starting.includes(targetId)||!isCandidateAvailable(targetId))
   return fail('Выберите доступного игрока IN, которого ещё нет в составе.');
  if(isBlocked(targetId,whenEpoch))return fail('Игрок для покупки заблокирован в выбранный момент.');
  const scores=new Map(),prices=new Map(),end=whenEpoch+horizonDays*DAY;
  function score(id){
   if(!scores.has(id))scores.set(id,Number(scorePlayer(id,whenEpoch,end)));
   return scores.get(id);
  }
  function price(id){
   if(!prices.has(id)){
    const raw=priceOf(id);
    prices.set(id,raw===null||raw===undefined||raw===''?NaN:Number(raw));
   }
   const n=prices.get(id);
   return finite(n)&&n>=0?n:NaN;
  }
  if(!finite(price(targetId))||!finite(score(targetId)))
   return fail('Неизвестна цена или прогноз выбранного игрока.');
  const used=Number(current.used?.[weekKey(whenEpoch)]||0);
  const remaining=Math.max(0,3-used);
  const capacity=Math.min(maxMoves,remaining);
  if(!capacity)return fail('На выбранной неделе нет свободных замен.',{remaining});
  const possibleOut=starting.filter(id=>players[id]?.pos===target.pos&&!isBlocked(id,whenEpoch));
  if(forcedOutId&&(!possibleOut.includes(forcedOutId)))
   return fail('Продаваемый игрок должен находиться в этом позиционном слоте и быть доступным.');
  const targetOuts=forcedOutId?[forcedOutId]:possibleOut;
  if(!targetOuts.length)return fail('Нет доступного игрока для освобождения нужной позиции.');
  const base=Number(project(existingDraft,whenEpoch,end));
  if(!finite(base))return fail('Недоступен прогноз KEEP на выбранный горизонт.');
  const originCash=current.cash;
  const marketByPos=new Map();
  for(const p of candidates||[]){
   if(!p?.id||!players[p.id]||!players[p.id].forecast||p.id===targetId||
      starting.includes(p.id)||!isCandidateAvailable(p.id)||isBlocked(p.id,whenEpoch)||
      !finite(price(p.id))||!finite(score(p.id)))continue;
   const pos=players[p.id].pos;
   if(!marketByPos.has(pos))marketByPos.set(pos,[]);
   marketByPos.get(pos).push(p.id);
  }
  const combinations=[];
  let tested=0,prelim=0;
  function swap(state,out,into){
   if(!state.roster.includes(out)||state.roster.includes(into)||
      players[out]?.pos!==players[into]?.pos||
      isBlocked(out,whenEpoch)||isBlocked(into,whenEpoch))return null;
   const sell=price(out),buy=price(into),diff=state.cash+sell-buy;
   if(!finite(sell)||!finite(buy)||diff<-.00001)return null;
   const next=[...state.roster];next[next.indexOf(out)]=into;
   const teams=new Map();
   for(const id of next){
    if(!players[id])return null;
    const club=players[id].team;
    teams.set(club,(teams.get(club)||0)+1);
    if(teams.get(club)>2)return null;
   }
   const s1=score(into),s0=score(out);
   if(!finite(s1)||!finite(s0))return null;
   return {roster:next,cash:diff,
     moves:[...state.moves,{out,in_:into,epoch:whenEpoch,sell,buy}],
     approx:state.approx+s1-s0};
  }
  // Shortlist is deliberately diverse in savings and expected FP, not simply
  // the cheapest or most popular player. Full search is NOT guaranteed.
  function optionsFor(out,deficit){
   const sale=price(out),oldScore=score(out),pos=players[out].pos;
   if(!finite(sale)||!finite(oldScore))return [];
   const all=(marketByPos.get(pos)||[]).map(id=>({id,buy:price(id),
      save:sale-price(id),delta:score(id)-oldScore}));
   const dedup=new Map();
   function take(list,n){for(const item of list.slice(0,n))dedup.set(item.id,item.id);}
   take([...all].sort((a,b)=>b.delta-a.delta||b.save-a.save||idcmp(a.id,b.id)),7);
   take([...all].sort((a,b)=>b.save-a.save||b.delta-a.delta||idcmp(a.id,b.id)),8);
   take([...all].sort((a,b)=>
      (b.delta+.006*b.save)-(a.delta+.006*a.save)||idcmp(a.id,b.id)),7);
   take([...all].sort((a,b)=>Math.abs(a.save-deficit)-Math.abs(b.save-deficit)||
       b.delta-a.delta||idcmp(a.id,b.id)),5);
   return [...dedup.values()].slice(0,25);
  }
  const initial={roster:starting,cash:originCash,moves:[],approx:0};
  function emit(state,targetOut){
   const last=swap(state,targetOut,targetId);
   if(!last)return;
   tested++;
   combinations.push({moves:last.moves,approx:last.approx,
     netApprox:last.approx-opportunityPenalty*last.moves.length,
     cash:last.cash,targetOut});
  }
  // For 3-move funding, retain paths with strong gain OR with the highest
  // savings. This prevents a cheap but useful bridge from being pruned.
  function chooseStage(states,targetOut){
   const needed=Math.max(0,price(targetId)-price(targetOut)-originCash);
   const byScore=[...states].sort((a,b)=>
     (b.approx-.005*Math.max(0,needed-(b.cash-originCash)))-
     (a.approx-.005*Math.max(0,needed-(a.cash-originCash)))||
     a.moves.map(KEY).join('|').localeCompare(b.moves.map(KEY).join('|'))).slice(0,80);
   const byCash=[...states].sort((a,b)=>b.cash-a.cash||b.approx-a.approx).slice(0,45);
   const byOut=new Map();
   for(const st of states){
    const id=st.moves[0].out;
    const a=byOut.get(id)||[];a.push(st);byOut.set(id,a);
   }
   const diverse=[...byOut.values()].flatMap(group=>group.sort((a,b)=>b.cash-a.cash||b.approx-a.approx).slice(0,6));
   const chosen=new Map();for(const s of [...byScore,...byCash,...diverse]){
    const key=s.moves.map(KEY).join('|');chosen.set(key,s);
   }
   return [...chosen.values()].slice(0,180);
  }
  for(const targetOut of targetOuts){
   const initialDeficit=Math.max(0,price(targetId)-price(targetOut)-originCash);
   emit(initial,targetOut);
   if(capacity<2)continue;
   const stage=[];
   for(const out of starting){
    if(out===targetOut||isBlocked(out,whenEpoch))continue;
    for(const into of optionsFor(out,initialDeficit)){
     const st=swap(initial,out,into);
     if(!st)continue;
     prelim++;
     // Financing step must either release cash or a slot from the incoming
     // player's club; non-contributing 'extra' transfers are out of scope.
     const freesClub=players[out].team===target.team&&players[into].team!==target.team;
     if(st.cash<originCash-0.00001&&!freesClub)continue;
     stage.push(st);
     emit(st,targetOut);
    }
   }
   if(capacity<3)continue;
   for(const first of chooseStage(stage,targetOut)){
    const usedOut=first.moves[0].out;
    const deficit=Math.max(0,price(targetId)-price(targetOut)-first.cash);
    for(const out of starting){
     if(out===targetOut||out===usedOut||isBlocked(out,whenEpoch))continue;
     for(const into of optionsFor(out,deficit)){
      const next=swap(first,out,into);
      if(!next)continue;
      // Every financing move must have some budget or club-cap benefit.
      const freesClub=players[out].team===target.team&&players[into].team!==target.team;
      if(next.cash<first.cash-0.00001&&!freesClub)continue;
      prelim++;
      emit(next,targetOut);
     }
    }
   }
  }
  const sorted=combinations.sort((a,b)=>b.netApprox-a.netApprox||
    b.approx-a.approx||a.moves.length-b.moves.length||
    a.moves.map(KEY).join('|').localeCompare(b.moves.map(KEY).join('|')));
  const shortlist=[];
  const perType=new Map();
  // First retain high-utility routes by total move count / fixed OUT, then
  // add best overall. A bounded number is passed to the authoritative guard.
  for(const route of sorted){
   const group=route.moves.length+'|'+route.targetOut;
   const count=perType.get(group)||0;
   if(count>=65)continue;
   perType.set(group,count+1);
   shortlist.push(route);
   if(shortlist.length>=380)break;
  }
  const final=[];
  let eligible=0;
  for(const candidate of shortlist){
   const checked=validateDraft([...existingDraft,...candidate.moves]);
   if(!checked?.valid||!finite(checked.cash)||checked.cash<-.00001)continue;
   const projected=Number(project([...existingDraft,...candidate.moves],whenEpoch,end));
   if(!finite(projected))continue;
   eligible++;
   const gain=projected-base;
   final.push({...candidate,gain,net:gain-opportunityPenalty*candidate.moves.length,
     cash:checked.cash,stepCash:(checked.steps||[]).slice(existingDraft.length).map(s=>s.cash),
     warnings:checked.warnings||[],usedByWeek:checked.used||{}});
  }
  final.sort((a,b)=>b.net-a.net||b.gain-a.gain||a.moves.length-b.moves.length||
    a.moves.map(KEY).join('|').localeCompare(b.moves.map(KEY).join('|')));
  const selected=[],seen=new Set(),groupCounts=new Map();
  function signature(route){return route.moves.map(KEY).join('|');}
  function group(route){return route.moves.length+'|'+route.targetOut+'|'+
    route.moves.slice(0,-1).map(m=>m.out).sort().join(',');}
  function push(route,limit=2){
   if(!route||selected.length>=maxRoutes)return;
   const sig=signature(route),key=group(route);
   if(seen.has(sig)||(groupCounts.get(key)||0)>=limit)return;
   seen.add(sig);groupCounts.set(key,(groupCounts.get(key)||0)+1);
   selected.push(route);
  }
  push(final[0]);
  for(const n of [1,2,3])push(final.find(r=>r.moves.length===n));
  for(const out of targetOuts)push(final.find(r=>r.targetOut===out));
  for(const route of final)push(route,1); // different sacrificed slots first
  for(const route of final)push(route,2); // then different replacement choices
  selected.sort((a,b)=>b.net-a.net||a.moves.length-b.moves.length);
  const requiredByOut=targetOuts.map(out=>({out,
    deficit:Math.max(0,price(targetId)-originCash-price(out)),
    targetSell:price(out)}));
  if(!selected.length)return fail('Не найден пакет, который одновременно проходит бюджет, блокировки и лимит ходов. Проверьте реальные цены или измените цель.',{
    remaining,requiredByOut,tested,eligible});
  return {ready:true,targetId,targetPrice:price(targetId),remaining,capacity,
    start:whenEpoch,end,horizonDays,baseline:base,
    requiredByOut,routes:selected,eligible,tested,prelim,
    kind:'bounded_immediate_funding_not_proven_optimal',
    disclaimer:'Финансирование и покупка рассчитаны на одно выбранное время, порядок действий важен. '+
     'Цены и разблокировку сверяйте на Sports.ru перед КАЖДЫМ ходом. '+
     'Резерв FP за ход — эвристика, не реальный штраф. Черновик не делает трансферы.'};
 }
 return {solve,weekKey};
});