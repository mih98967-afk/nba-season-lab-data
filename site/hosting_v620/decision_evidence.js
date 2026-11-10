/* NBA Season Lab v6.11: read-only evidence guard for hypothetical Optimizer routes.
 * Does not change models, prices, S, Firestore, or actual Sports.ru transfers.
 * A browser receipt and an official report are timestamped observations,
 * not guarantees of future prices, participation, locks, or weekly quota.
 */
(function(root,factory){
 'use strict';
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 root.NBADecisionEvidence=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const HOUR=3600000;
 const finite=x=>typeof x==='number'&&Number.isFinite(x);
 const nonnegative=x=>finite(x)&&x>=0;
 const riskStatuses=new Set(['out','doubtful','questionable']);
 const shortStatus={out:'OUT',doubtful:'DOUBTFUL',questionable:'QUESTIONABLE'};
 function audit(input){
  const x=input||{},moves=x.route?.moves||[],now=x.nowEpoch;
  if(!Array.isArray(moves)||!finite(now))return {ready:false,reason:'Некорректный момент проверки или сценарий'};
  const archive=x.priceArchive;
  const receipts=archive?.schema_version===1&&archive?.private_local_only===true&&
   archive?.never_autosync===true&&Array.isArray(archive.receipts)?archive.receipts:[];
  const imported=archive?.restored_from_file_unverified===true;
  const reports=Array.isArray(x.officialReports)?x.officialReports:[];
  const entries=[];
  let missingQuote=0,priceConflict=0,staleQuote=0,futureSteps=0,officialOut=0,officialRisk=0;
  for(const m of moves){
   if(!m||!m.out||!m.in_||!finite(m.epoch))return {ready:false,reason:'Нет точных параметров шага'};
   const future=m.epoch>now+30*60000;
   if(future)futureSteps++;
   // Receipts are independent local, owner-attested PAIR snapshots. Do not
   // splice a sell price from one receipt with a buy price from another.
   const pair=receipts.filter(r=>{
    const t=Date.parse(r?.observed_at_utc||'');
    return Number.isFinite(t)&&t<=now&&r?.quotes?.length===2&&
     r.quotes[0]?.side==='sell'&&r.quotes[0]?.player_id===m.out&&
     r.quotes[1]?.side==='buy'&&r.quotes[1]?.player_id===m.in_;
   }).sort((a,b)=>Date.parse(a.observed_at_utc)-Date.parse(b.observed_at_utc));
   const last=pair.at(-1)||null;
   const ageHours=last?(now-Date.parse(last.observed_at_utc))/HOUR:null;
   const quoteMatches=last?nonnegative(m.sell)&&nonnegative(m.buy)&&
    m.sell===last.quotes[0].price&&m.buy===last.quotes[1].price:null;
   let quoteStatus='no_pair_snapshot';
   if(last){
    if(imported)quoteStatus='restored_snapshot_unverified';
    else if(quoteMatches===false)quoteStatus='snapshot_disagrees_with_scenario';
    else if(ageHours>1)quoteStatus='old_matching_snapshot';
    else quoteStatus='recent_matching_snapshot_not_live_verified';
   }
   if(!last)missingQuote++;
   if(quoteMatches===false)priceConflict++;
   if(ageHours!==null&&ageHours>1)staleQuote++;
   // OfficialStatus.select already checks exact game, club, prelock issue,
   // report URL and first-observed time. Revalidate the minimum clock/range
   // here to make an impossible future report or old game fail closed.
   const relevant=reports.filter(r=>r?.playerId===m.in_&&
     riskStatuses.has(r.status)&&finite(r.tipoffEpoch)&&
     finite(r.firstSeenEpoch)&&r.firstSeenEpoch<=now&&
     r.tipoffEpoch>now&&r.tipoffEpoch>=m.epoch-30*60000&&
     r.tipoffEpoch<=m.epoch+72*HOUR);
   const strongest=relevant.sort((a,b)=>{
     const rank={out:3,doubtful:2,questionable:1};
     return rank[b.status]-rank[a.status]||a.tipoffEpoch-b.tipoffEpoch;
   })[0]||null;
   if(strongest){officialRisk++;if(strongest.status==='out')officialOut++;}
   entries.push({out:m.out,in_:m.in_,executionEpoch:m.epoch,plannedFuture:future,
    quoteStatus,quoteObservedAtUtc:last?.observed_at_utc||null,
    manualSell:last?.quotes[0].price??null,manualBuy:last?.quotes[1].price??null,
    scenarioSell:m.sell??null,scenarioBuy:m.buy??null,
    ageHours:ageHours===null?null:Math.round(ageHours*10)/10,
    quoteMatches,officialStatus:strongest?.status||null,
    officialTipEpoch:strongest?.tipoffEpoch||null,
    officialReportStale:strongest?.stale===true,
    officialSourceUrl:strongest?.sourceUrl||null});
  }
  const warnings=[];
  if(officialOut)warnings.push('Официальный NBA OUT для покупаемого игрока в ближайшем матче: перепроверьте статус перед заменой');
  else if(officialRisk)warnings.push('NBA сообщает о риске участия покупаемого игрока: перепроверьте официальный отчёт');
  if(priceConflict)warnings.push('Ручная отметка Sports.ru отличается от расчётной цены: обновите расчёт');
  if(missingQuote)warnings.push('Для части замен нет ручной отметки пары цен Sports.ru');
  if(staleQuote)warnings.push('Часть отметок цен сделана более часа назад; котировки могли измениться');
  if(imported&&entries.some(e=>e.quoteObservedAtUtc))warnings.push('Восстановленные отметки цен не имеют независимо подтверждённого времени');
  if(futureSteps)warnings.push('Будущие цены и разблокировка неизвестны');
  if(!x.officialFeedValid)warnings.push('Нет проверенной полноты свежих официальных статусов NBA: отсутствие OUT не доказывает участие');
  return {ready:true,entries,warnings,
    counts:{moves:moves.length,missingQuote,priceConflict,staleQuote,futureSteps,officialOut,officialRisk},
    requiresManualReview:moves.length>0,verifiedMarketOrMedicalDecision:false,
    allowAutoTransfer:false,sourceType:'read_only_local_receipt_and_prelock_official_evidence',
    disclaimer:'Ни ручная отметка цены, ни NBA Injury Report не гарантируют цену, участие или право на замену на Sports.ru.'};
 }

 // An owner-attested current quote is useful evidence, not independent market verification.
 // Never treat a modelled price or an inferred weekly reset as a Sports.ru counter.
 function marketReadiness(x={}){
  const moves=x.route?.moves;
  if(!Array.isArray(moves))return {status:'needs_check',ready:false,reasons:['Сценарий не сформирован.']};
  if(!moves.length)return {status:'keep',ready:false,reasons:[]};
  const now=x.nowEpoch;
  if(!finite(now))return {status:'needs_check',ready:false,reasons:['Время проверки неизвестно.']};
  if(moves.some(m=>!finite(m?.epoch)||m.epoch<now-60000||m.epoch>now+30*60000))
   return {status:'future_scenario',ready:false,reasons:['Будущие цены и остаток замен нельзя подтверждать заранее.']};
  if(x.draftCount!==0)
   return {status:'needs_check',ready:false,reasons:['Уже есть черновик: сначала сверьте его с фактическими заменами Sports.ru.']};
  const wk=x.weekKey;
  if(typeof wk!=='function'||[0,15].some(hour=>new Set([wk(now,hour),...moves.map(m=>wk(m.epoch,hour))]).size!==1))
   return {status:'needs_check',ready:false,reasons:['Время операции близко к возможной границе недели: проверьте новый счётчик Sports.ru.']};
  const archive=x.priceArchive;
  if(!archive||archive.schema_version!==1||archive.private_local_only!==true||archive.never_autosync!==true||!Array.isArray(archive.receipts))
   return {status:'needs_check',ready:false,reasons:['Нет локального журнала ручной проверки цен Sports.ru.']};
  if(archive.restored_from_file_unverified===true)
   return {status:'needs_check',ready:false,reasons:['Журнал цен восстановлен из файла: отметьте реальные значения заново.']};
  const recent=archive.receipts.filter(r=>{
   const t=Date.parse(r?.observed_at_utc||'');
   return r?.user_confirmed_now===true&&r?.private_local_only===true&&
    r?.provenance==='owner_manually_rechecked_sportsru_screen'&&r?.transfer_executed===false&&
    finite(t)&&t<=now&&now-t<=HOUR;
  });
  const reasons=[];
  for(const m of moves){
   if(!nonnegative(m?.sell)||!nonnegative(m?.buy)){
    reasons.push('В сценарии нет двух корректных цен.');continue;
   }
   const found=recent.some(r=>r.quotes?.length===2&&
    r.quotes[0]?.side==='sell'&&r.quotes[0].player_id===m.out&&r.quotes[0].price===m.sell&&
    r.quotes[1]?.side==='buy'&&r.quotes[1].player_id===m.in_&&r.quotes[1].price===m.buy);
   if(!found)reasons.push('Не для каждой пары OUT/IN есть совпадающая ручная отметка цен за последний час.');
  }
  const current=recent.filter(r=>Number.isSafeInteger(r.cash_from_sportsru_screen)&&
   Number.isInteger(r.quota_remaining_from_sportsru_screen)).at(-1);
  if(!current)reasons.push('Нет свежей ручной отметки кассы и остатка замен Sports.ru.');
  else{
   if(!nonnegative(x.cash)||x.cash!==current.cash_from_sportsru_screen)
    reasons.push('Касса в сервисе не совпадает с последней отметкой Sports.ru.');
   if(moves.length>current.quota_remaining_from_sportsru_screen)
    reasons.push('На Sports.ru отмечено меньше свободных замен, чем в сценарии.');
  }
  const ready=reasons.length===0;
  return {status:ready?'owner_checked_now':'needs_check',ready,
   remainingOwner:current?.quota_remaining_from_sportsru_screen??null,
   cashOwner:current?.cash_from_sportsru_screen??null,
   reasons:[...new Set(reasons)],independentlyVerified:false,allowAutoTransfer:false};
 }
 return {audit,marketReadiness};
});
