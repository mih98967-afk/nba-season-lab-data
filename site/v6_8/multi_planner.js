/* NBA Season Lab v6.2 - multi-slot, multi-week transfer decision assistant.
 * Pure, bounded beam-search; never accesses Firestore/Sports.ru or mutates inputs.
 * Prices at future dates and availability are scenarios, not facts.
 */
(function(root,factory){
 'use strict';
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 root.NBAMultiPlanner=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const DAY=86400000,HOUR=3600000;
 const fail=reason=>({ready:false,reason,routes:[],tested:0,eligible:0});
 const finite=x=>typeof x==='number'&&Number.isFinite(x);
 function mondayStart(epoch){
   if(!finite(epoch))return NaN;
   const d=new Date(epoch+3*HOUR);
   if(!finite(d.getTime()))return NaN;
   const day=(d.getUTCDay()+6)%7;
   d.setUTCHours(0,0,0,0);
   d.setUTCDate(d.getUTCDate()-day);
   return d.getTime()-3*HOUR;
 }
 function weekKey(epoch){
   const m=mondayStart(epoch-15*HOUR);
   return finite(m)?new Date(m+3*HOUR).toISOString().slice(0,10):null;
 }
 function decisionMoments(start,end){
   const moments=new Set([start]);
   // Coarse decision points intentionally bound computation; not an exhaustive schedule search.
   for(const days of [2,4,7,10,14,17,21]){
     const d=new Date(start+days*DAY+3*HOUR);
     d.setUTCHours(15,0,0,0);
     const at=d.getTime()-3*HOUR;
     if(at>start+DAY&&at<end-DAY)moments.add(at);
   }
   for(let week=1;week<=4;week++){
     const at=mondayStart(start)+week*7*DAY+15*HOUR;
     if(at>start+DAY&&at<end-DAY)moments.add(at);
   }
   return [...moments].sort((a,b)=>a-b).slice(0,10);
 }
 function plan(options){
   const o=options||{};
   const {players,roster,candidates,existingDraft=[],nowEpoch,whenEpoch,
     horizonDays=21,opportunityPenalty=4,maxMoves=3,
     priceOf,validateDraft,coverage,scorePlayer,project,
     isCandidateAvailable=()=>true,focusIds=[],maxRoutes=5}=o;
   if(![14,21,28].includes(horizonDays)||![0,4,8].includes(opportunityPenalty)||
      ![1,2,3,4].includes(maxMoves))
     return fail('Горизонт: 14/21/28 дней; резерв: 0/4/8 FP; максимум новых ходов: 1–4');
   if(!finite(nowEpoch)||!finite(whenEpoch)||whenEpoch<nowEpoch-60000)
     return fail('Укажите актуальный момент начала анализа');
   if(!Array.isArray(roster)||roster.length!==10||new Set(roster).size!==10||!players||
      roster.some(id=>!players[id]))return fail('Для сравнения нужен корректный состав из 10 игроков');
   if(!Array.isArray(candidates)||!Array.isArray(existingDraft)||
      [priceOf,validateDraft,coverage,scorePlayer,project].some(x=>typeof x!=='function'))
     return fail('Не хватает данных о календаре, ценах или проверке состава');
   if(existingDraft.some(x=>!finite(x?.epoch)||x.epoch>whenEpoch))
     return fail('Сначала завершите хронологию существующего черновика; новые шаги должны быть позже');
   const end=whenEpoch+horizonDays*DAY;
   const covered=coverage(whenEpoch,horizonDays);
   if(!covered?.ok)return fail('Неполный календарь: '+(covered?.reason||'нет подтверждения'));
   const current=validateDraft(existingDraft);
   if(!current?.valid||!Array.isArray(current.roster)||current.roster.length!==10||
      !finite(current.cash)||current.cash<0)return fail('Текущий черновик некорректен');
   const starting=current.roster;
   const attention=new Set(focusIds.length?focusIds:starting);
   if(![...attention].some(id=>starting.includes(id)))return fail('Нет выбранных слотов для сравнения');
   const base=project(existingDraft,whenEpoch,end);
   if(!finite(base))return fail('Нет прогноза KEEP для всего выбранного периода');
   const moments=decisionMoments(whenEpoch,end);
   const scoreCache=new Map(),priceCache=new Map();
   function val(id,a,b=end){
     if(b<=a)return 0;
     const key=id+'|'+a+'|'+b;
     if(!scoreCache.has(key))scoreCache.set(key,Number(scorePlayer(id,a,b)));
     const number=scoreCache.get(key);
     return finite(number)?number:NaN;
   }
   function price(id){
     if(!priceCache.has(id)){
       const raw=priceOf(id);
       priceCache.set(id,raw==null||raw===''?NaN:Number(raw));
     }
     const p=priceCache.get(id);
     return finite(p)&&p>=0?p:NaN;
   }
   const catalog=[];
   for(const p of candidates){
     if(!p?.id||!players[p.id]||!players[p.id].forecast||!isCandidateAvailable(p.id))continue;
     if(!finite(price(p.id)))continue;
     catalog.push(p.id);
   }
   const positionLists=new Map();
   for(let k=0;k<moments.length;k++){
     for(const pos of ['PG','SG','SF','PF','C']){
       const matches=catalog.filter(id=>players[id].pos===pos);
       const scored=matches.map(id=>({id,score:val(id,moments[k]),price:price(id)}))
         .filter(x=>finite(x.score));
       const top=[...scored].sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id)).slice(0,7);
       const cheap=[...scored].sort((a,b)=>a.price-b.price||a.id.localeCompare(b.id)).slice(0,3);
       positionLists.set(k+'|'+pos,[...new Set([...top,...cheap].map(x=>x.id))]);
     }
   }
   const quota={...(current.used||{})};
   const origin=new Map(starting.map(id=>[id,id]));
   const starter={moves:[],roster:[...starting],origins:origin,cash:current.cash,
     weekCounts:quota,lastTimeIndex:0,approx:0,net:0,touched:[]};
   const allStates=[];
   let tested=0,eligible=0;
   function expanded(parent){
     const children=[];
     for(let k=parent.lastTimeIndex;k<moments.length;k++){
       const stamp=moments[k],week=weekKey(stamp);
       if((parent.weekCounts[week]||0)>=3)continue;
       for(const out of parent.roster){
         const root=parent.origins.get(out);
         if(!attention.has(root))continue;
         const old=players[out],sell=price(out);
         if(!old||!finite(sell))continue;
         const oldScore=val(out,stamp);
         if(!finite(oldScore))continue;
         for(const into of positionLists.get(k+'|'+old.pos)||[]){
           if(parent.roster.includes(into))continue;
           const buy=price(into);
           if(!finite(buy)||parent.cash+sell-buy < -0.00001)continue;
           if(parent.roster.filter(id=>id!==out&&players[id].team===players[into].team).length>=2)continue;
           const lastSame=parent.moves.findLast(m=>m.root===root);
           if(lastSame&&lastSame.epoch===stamp)continue; // no same-slot ping-pong at one instant
           const delta=val(into,stamp)-oldScore;
           if(!finite(delta))continue;
           tested++;
           const roster2=[...parent.roster];roster2[roster2.indexOf(out)]=into;
           const origins2=new Map(parent.origins);origins2.delete(out);origins2.set(into,root);
           const weekly={...parent.weekCounts,[week]:(parent.weekCounts[week]||0)+1};
           const t={out,in_:into,epoch:stamp,sell,buy,root};
           const moves=[...parent.moves,t];
           const approx=parent.approx+delta;
           children.push({moves,roster:roster2,origins:origins2,
             cash:parent.cash+sell-buy,weekCounts:weekly,lastTimeIndex:k,
             approx,net:approx-opportunityPenalty*moves.length,
             touched:[...new Set([...parent.touched,root])]});
         }
       }
     }
     return children;
   }
   let beam=[starter];
   for(let depth=1;depth<=maxMoves;depth++){
     const next=beam.flatMap(expanded);
     if(!next.length)break;
     // Deterministic diversity: limit near-duplicates with the same origin+first time.
     next.sort((a,b)=>b.net-a.net||b.approx-a.approx||a.moves.length-b.moves.length||
       a.moves.map(m=>m.in_).join(',').localeCompare(b.moves.map(m=>m.in_).join(',')));
     const chosen=[],counts=new Map();
     for(const node of next){
       const key=node.moves[0].root+'|'+node.moves[0].epoch+'|'+node.moves.length;
       const seen=counts.get(key)||0;
       if(seen>=7)continue;
       counts.set(key,seen+1);
       chosen.push(node);
       if(chosen.length>=34)break;
     }
     allStates.push(...chosen);
     beam=chosen;
   }
   const valid=[];
   // Rerun authoritative guard before claiming eligibility. This catches
   // 30-minute locks, real confirmed transfers and all quota/roster conditions.
   const sorted=[...allStates].sort((a,b)=>b.net-a.net).slice(0,125);
   for(const state of sorted){
     const moves=state.moves.map(({root,...m})=>m);
     const checked=validateDraft([...existingDraft,...moves]);
     if(!checked?.valid)continue;
     const projected=project([...existingDraft,...moves],whenEpoch,end);
     if(!finite(projected))continue;
     eligible++;
     const gain=projected-base;
     const net=gain-opportunityPenalty*moves.length;
     const categories=state.touched.length>1?'multi_slot':
       moves.length>1?'same_slot_chain':
       moves[0].epoch===whenEpoch?'now':'later';
     valid.push({kind:categories,moves,gain,net,
       usedByWeek:checked.used||{},cash:checked.cash,
       touched:state.touched.length,warnings:checked.warnings||[]});
   }
   valid.sort((a,b)=>b.net-a.net||b.gain-a.gain||a.moves.length-b.moves.length);
   const keep={kind:'keep',moves:[],gain:0,net:0,cash:current.cash,
     touched:0,usedByWeek:current.used||{},warnings:current.warnings||[]};
   const chosen=[];
   const seenSignature=new Set();
   function push(route){
     if(!route||chosen.length>=maxRoutes-1)return;
     const signature=route.moves.map(m=>m.out+'>'+m.in_+'@'+m.epoch).join('|');
     if(seenSignature.has(signature))return;
     seenSignature.add(signature);chosen.push(route);
   }
   // Show the trade-off between 1, 2 and 3+ moves, not four nearly
   // identical permutations of a greedy three-move recommendation.
   push(valid[0]);
   for(const count of [1,2,3,4])push(valid.find(r=>r.moves.length===count));
   for(const kind of ['later','now','multi_slot','same_slot_chain'])push(valid.find(r=>r.kind===kind));
   for(const r of valid)push(r);
   const routes=[keep,...chosen].sort((a,b)=>b.net-a.net||a.moves.length-b.moves.length);
   const withWeeks=routes.map(route=>{
     const weeks=[];
     for(let t=whenEpoch;t<end;){
       const b=Math.min(end,mondayStart(t)+7*DAY);
       if(b<=t)throw Error('Немонотонная московская неделя');
       const prev=project(existingDraft,t,b);
       const current=project([...existingDraft,...route.moves],t,b);
       weeks.push({week:weekKey(t),gain:finite(prev)&&finite(current)?current-prev:null,
         used:route.usedByWeek[weekKey(t)]||0});
       t=b;
     }
     return {...route,weeks};
   });
   return {ready:true,start:whenEpoch,end,horizonDays,maxMoves,
     opportunityPenalty,baseline:base,moments:moments.length,
     tested,eligible,routes:withWeeks,
     coverage:covered.reason,kind:'bounded_scenario_not_validated',
     disclaimer:'Планы ограничены несколькими датами и отобранными кандидатами. Будущие цены, участие и разблокировка не гарантированы. Резерв хода — эвристика, а не штраф Sports.ru.'};
 }
 return {plan,decisionMoments,mondayStart,weekKey};
});
