/* NBA Season Lab 6.1. Read-only 14-28-day slot-path comparison.
 * Uses the existing Sports.ru guard and scenario FP engine supplied by caller.
 * Not a global optimal or historically calibrated strategy. No account writes.
 */
(function(root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.NBAChainPlanner = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';
  const DAY=86400000, HOUR=3600000;
  const allowedLengths = [14,21,28];
  const allowedPenalty=[0,4,8];
  const fail=reason=>({ready:false,reason,routes:[],tested:0,eligible:0});
  function mondayStartMoscow(epoch){
    const d=new Date(epoch+3*HOUR);
    const day=(d.getUTCDay()+6)%7;
    d.setUTCHours(0,0,0,0);
    d.setUTCDate(d.getUTCDate()-day);
    return d.getTime()-3*HOUR;
  }
  function laterMoments(start,end){
    const date=new Date(start+3*HOUR);
    date.setUTCHours(15,0,0,0);
    const moments=new Set();
    for(const day of [2,4,6,7,9,11,14,16,18,21,23]){
      const at=date.getTime()-3*HOUR+day*DAY;
      if(at>start+DAY&&at<end-DAY) moments.add(at);
    }
    // Explicitly test next fantasy Monday: 15:00 is a decision reference,
    // never an assumed quota reset.
    const nextMonday=mondayStartMoscow(start)+7*DAY+15*HOUR;
    if(nextMonday>start+DAY&&nextMonday<end-DAY)moments.add(nextMonday);
    return [...moments].sort((a,b)=>a-b);
  }
  function rank(options){
    const {
      out, roster, players, candidates, existingDraft=[], nowEpoch, whenEpoch,
      horizonDays=14, opportunityPenalty=4, priceOf, validateDraft, project,
      scorePlayer, coverage, maxRoutes=4
    }=options||{};
    if(!allowedLengths.includes(horizonDays)||!allowedPenalty.includes(opportunityPenalty))
      return fail('Допустимые горизонты: 14, 21 или 28 дней; резерв одного хода: 0/4/8 FP');
    if(!Number.isFinite(whenEpoch)||!Number.isFinite(nowEpoch)||whenEpoch<nowEpoch-60000)
      return fail('Укажите дату и время первого решения не раньше текущего момента');
    if(!Array.isArray(roster)||roster.length!==10||!players?.[out]||!roster.includes(out))
      return fail('Укажите одного игрока из действующей десятки');
    if(!Array.isArray(existingDraft)||typeof priceOf!=='function'||typeof validateDraft!=='function'||
       typeof project!=='function'||typeof scorePlayer!=='function'||typeof coverage!=='function')
      return fail('Для расчёта не хватает данных о составе, ценах или календаре');
    if(existingDraft.some(t=>!Number.isFinite(t?.epoch)||t.epoch>whenEpoch))
      return fail('Первая дата цепочки должна быть ПОСЛЕ уже запланированных замен в черновике');
    const end=whenEpoch+horizonDays*DAY;
    const c=coverage(whenEpoch,horizonDays);
    if(!c?.ok) return fail('Неполный календарь: '+(c?.reason||'требуется уточнение'));
    const existing=validateDraft(existingDraft);
    if(!existing?.valid||!Array.isArray(existing.roster)||!existing.roster.includes(out))
      return fail('Текущий черновик недопустим либо игрок уже продан');
    const base=project(existingDraft,whenEpoch,end);
    if(!Number.isFinite(base))return fail('Нет базового прогноза KEEP для выбранного периода');
    const sell=Number(priceOf(out));
    if(!Number.isFinite(sell)||sell<0)return fail('Неизвестна цена продаваемого игрока');
    const cache=new Map();
    function val(id,a,b){
      if(b<=a)return 0;
      const key=id+'|'+a+'|'+b;
      if(!cache.has(key))cache.set(key,scorePlayer(id,a,b));
      const x=cache.get(key);
      return Number.isFinite(x)?x:NaN;
    }
    const universe=[];
    for(const p of candidates||[]){
      if(!p||!p.id||p.id===out||existing.roster.includes(p.id)||p.pos!==players[out].pos)continue;
      if(!players[p.id]||!players[p.id].forecast)continue;
      const buy=Number(priceOf(p.id));
      if(!Number.isFinite(buy)||buy<0)continue;
      const total=val(p.id,whenEpoch,end);
      if(!Number.isFinite(total))continue;
      universe.push({id:p.id,buy,score:total});
    }
    const baselinePlayer=val(out,whenEpoch,end);
    if(!Number.isFinite(baselinePlayer))return fail('Нет прогнозов для удержания выбранного игрока');
    const byId=new Map(universe.map(p=>[p.id,p]));
    const validMoves=moves=>{
      const check=validateDraft(existingDraft.concat(moves));
      return check?.valid?check:null;
    };
    let tested=0;
    const proposals=[];
    const seen=new Set();
    function add(moves,kind,scoreHint){
      if(!moves.length)return;
      const signature=moves.map(m=>m.out+'>'+m.in_+'@'+m.epoch).join('|');
      if(seen.has(signature))return;
      seen.add(signature);
      tested++;
      if(!Number.isFinite(scoreHint))return;
      const checked=validMoves(moves);
      if(!checked)return;
      proposals.push({moves,kind,hint:scoreHint,checked});
    }
    const first=m=>({out,in_:m.id,epoch:whenEpoch,sell,buy:m.buy});
    const maxFirst=14;
    const sevenEnd=Math.min(end,whenEpoch+7*DAY);
    const bestShort=[...universe].sort((a,b)=>
      (val(b.id,whenEpoch,sevenEnd)-val(out,whenEpoch,sevenEnd))-
      (val(a.id,whenEpoch,sevenEnd)-val(out,whenEpoch,sevenEnd)) || a.id.localeCompare(b.id)).slice(0,maxFirst);
    const bestLong=[...universe].sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id)).slice(0,maxFirst);
    const cheapest=[...universe].sort((a,b)=>a.buy-b.buy||a.id.localeCompare(b.id)).slice(0,5);
    const firstSet=[...new Map([...bestShort,...bestLong,...cheapest].map(p=>[p.id,p])).values()];
    for(const p of firstSet){
      const moves=[first(p)];
      add(moves,'now',p.score-baselinePlayer);
    }
    const times=laterMoments(whenEpoch,end);
    // Compare waiting for an advantageous calendar window, not just immediate buy.
    for(const t2 of times){
      const tail=universe.map(p=>({...p,tail:val(p.id,t2,end)})).filter(x=>Number.isFinite(x.tail));
      tail.sort((a,b)=>b.tail-a.tail||a.id.localeCompare(b.id));
      const pool=[...new Map([...tail.slice(0,14),...cheapest].map(p=>[p.id,p])).values()];
      const keepTail=val(out,t2,end);
      for(const p of pool){
        add([{out,in_:p.id,epoch:t2,sell,buy:p.buy}],'later',p.tail-keepTail);
      }
    }
    // Two-step paths use only the best short/long/cost candidates, never an
    // exhaustive, unbounded search that would freeze a mobile browser.
    for(const a of firstSet){
      const move1=first(a);
      if(!validMoves([move1]))continue;
      for(const t2 of times){
        const aTail=val(a.id,t2,end);
        const firstWindow=val(a.id,whenEpoch,t2);
        if(!Number.isFinite(aTail)||!Number.isFinite(firstWindow))continue;
        const tail=universe.filter(p=>p.id!==a.id).map(p=>({...p,tail:val(p.id,t2,end)}));
        const reentry={id:out,buy:sell,tail:val(out,t2,end)};
        const cheapest2=[...tail].sort((a,b)=>a.buy-b.buy||a.id.localeCompare(b.id)).slice(0,5);
        const preferred=[...new Map([...tail.sort((a,b)=>b.tail-a.tail||a.id.localeCompare(b.id)).slice(0,12),...cheapest2,reentry].map(p=>[p.id,p])).values()];
        for(const b of preferred){
          if(!Number.isFinite(b.tail))continue;
          const two=[move1,{out:a.id,in_:b.id,epoch:t2,sell:a.buy,buy:b.buy}];
          const hint=firstWindow+b.tail-baselinePlayer;
          add(two,'chain',hint);
        }
      }
    }
    // First stage is a fast prefilter. Final ranking always uses the exact
    // same full-team project function for KEEP and every candidate route.
    proposals.sort((a,b)=>b.hint-a.hint||a.moves.length-b.moves.length);
    // Reserve final-evaluation slots by strategy type; otherwise numerous
    // near-identical chains can crowd out a useful delayed one-transfer plan.
    const shortlist=['now','later','chain'].flatMap(kind=>
      proposals.filter(r=>r.kind===kind).slice(0,25));
    const ranked=[];
    for(const proposal of shortlist){
      const predicted=project(existingDraft.concat(proposal.moves),whenEpoch,end);
      if(!Number.isFinite(predicted))continue;
      const gain=predicted-base;
      ranked.push({...proposal,gain,net:gain-opportunityPenalty*proposal.moves.length,
        cash:proposal.checked.cash,warnings:proposal.checked.warnings||[]});
    }
    ranked.sort((a,b)=>b.net-a.net || b.gain-a.gain || a.moves.length-b.moves.length);
    const keep={kind:'keep',moves:[],gain:0,net:0,cash:existing.cash,warnings:[]};
    // Different strategies must remain visible. A wall of nearly identical
    // chains is less useful than the best direct, delayed and two-leg routes.
    const selected=[];
    for(const kind of ['now','later','chain']){
      const best=ranked.find(r=>r.kind===kind);
      if(best)selected.push(best);
    }
    selected.push(keep);
    selected.sort((a,b)=>b.net-a.net||a.moves.length-b.moves.length);
    selected.splice(Math.max(1,Math.min(4,maxRoutes)));
    const weekly=selected.map(route=>{
      const segments=[];
      let a=whenEpoch;
      while(a<end){
        const weekEnd=mondayStartMoscow(a)+7*DAY;
        const b=Math.min(end,weekEnd);
        if(b<=a)throw new Error('Non-monotonic Moscow week');
        const keepScore=project(existingDraft,a,b);
        const actual=project(existingDraft.concat(route.moves),a,b);
        segments.push({week:new Date(mondayStartMoscow(a)+3*HOUR).toISOString().slice(0,10),
          gain:Number.isFinite(actual)&&Number.isFinite(keepScore)?actual-keepScore:null});
        a=b;
      }
      return {...route,weekly:segments};
    });
    return {ready:true,start:whenEpoch,end,horizonDays,opportunityPenalty,
      kind:'scenario_not_calibrated',baseline:base,possible:universe.length,
      tested,eligible:ranked.length,routeCount:weekly.length,routes:weekly,
      limitation:'Сценарий: текущие цены считаются неизменными, будущая разблокировка неизвестна; сравнение не является доказанным оптимумом или прогнозом реальных трансферов.'};
  }
  return {rank,laterMoments,mondayStartMoscow};
});
