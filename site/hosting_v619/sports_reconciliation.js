/* NBA Season Lab v6.17 - read-only owner-attested Sports.ru comparison.
 * No persistence, account access, network calls, forecast adoption or transfers.
 * An equality of numbers is NOT independent verification of Sports.ru scoring.
 */
(function(root,factory){
 'use strict';
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 root.NBASportsReconciliation=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const DAY=86400000;
 function parseNumber(value,min,max,integer=false){
  if(typeof value!=='string'&&typeof value!=='number')return null;
  const s=String(value).replace(/[\s\u00a0\u202f]/g,'').replace(',','.');
  if(!/^-?\d+(?:\.\d{1,2})?$/.test(s))return null;
  const x=Number(s);
  return Number.isFinite(x)&&x>=min&&x<=max&&(!integer||Number.isInteger(x))?x:null;
 }
 function isBlank(v){return v==null||(typeof v==='string'&&v.trim()==='');}
 function readValue(value,min,max,integer){
  if(isBlank(value))return {present:false,value:null,valid:true};
  const x=parseNumber(value,min,max,integer);
  return {present:true,value:x,valid:x!==null};
 }
 function usage(executed,clock,weekKey,resetHour){
  if(!Array.isArray(executed)||typeof weekKey!=='function')return null;
  let target;
  try{target=weekKey(clock,resetHour);}catch{return null;}
  if(typeof target!=='string'||!target)return null;
  let n=0;
  for(const m of executed){
   if(!m||typeof m.epoch!=='number'||!Number.isFinite(m.epoch)||m.epoch>clock)return null;
   let key;
   try{key=weekKey(m.epoch,resetHour);}catch{return null;}
   if(typeof key!=='string'||!key)return null;
   if(key===target)n++;
  }
  return n;
 }
 function compare(input){
  const owner=input?.owner||{},service=input?.service||{};
  const now=input?.nowEpoch;
  const errors=[];
  if(!Number.isFinite(now)||now<=0)errors.push('INVALID_CAPTURE_CLOCK');
  if(owner.confirmedNow!==true)errors.push('OWNER_ATTESTATION_REQUIRED');
  const pts=readValue(owner.fp,-100000,1000000,false);
  const cash=readValue(owner.cash,0,20000,false);
  const quota=readValue(owner.remaining,0,3,true);
  if(!pts.valid)errors.push('INVALID_OWNER_FP');
  if(!cash.valid)errors.push('INVALID_OWNER_CASH');
  if(!quota.valid)errors.push('INVALID_OWNER_QUOTA');
  if(!pts.present&&!cash.present&&!quota.present)errors.push('NO_OWNER_FIELDS');
  if(errors.length)return {valid:false,errors,readOnly:true};
  const checks={};
  const updated=Date.parse(service.feedUpdatedAtUtc||'');
  const age=Number.isFinite(updated)?now-updated:null;
  const feedFresh=age!=null&&age>=-5*60000&&age<=DAY;
  if(pts.present){
   const score=service.calculatedNBAFP;
   const rosterReady=service.initialRosterCount===10;
   const comparable=rosterReady&&typeof score==='number'&&Number.isFinite(score);
   checks.fp={owner:pts.value,calculatedNBA:comparable?score:null,
    difference:comparable?score-pts.value:null,
    kind:!comparable?'LOCAL_SCORE_UNAVAILABLE':feedFresh?'PROVISIONAL_COMPARISON':'STALE_OR_UNDATED_NBA_FEED',
    feedFresh,sourceUpdatedAtUtc:Number.isFinite(updated)?new Date(updated).toISOString():null};
  }
  if(cash.present){
   const local=service.cash;
   const comparable=typeof local==='number'&&Number.isFinite(local)&&local>=0&&local<=20000;
   checks.cash={owner:cash.value,local:comparable?local:null,
    difference:comparable?local-cash.value:null,
    kind:!comparable?'LOCAL_BALANCE_UNAVAILABLE':Math.abs(local-cash.value)<=0.001?'AGREES':'DIFFERS'};
  }
  if(quota.present){
   const fifteen=usage(service.executed,now,input?.weekKey,15);
   const midnight=usage(service.executed,now,input?.weekKey,0);
   const known=fifteen!==null&&midnight!==null;
   const valid15=known&&fifteen<=3,valid00=known&&midnight<=3;
   const remaining15=valid15?3-fifteen:null,remaining00=valid00?3-midnight:null;
   const matched15=valid15&&remaining15===quota.value;
   const matched00=valid00&&remaining00===quota.value;
   const kind=!known?'LOCAL_LEDGER_UNVERIFIED':!valid15&&!valid00?'BOTH_HYPOTHESES_OVER_CAP':matched15&&matched00?'AGREES_BOTH_UNVERIFIED':matched15?'AGREES_15_ONLY_UNVERIFIED':matched00?'AGREES_00_ONLY_UNVERIFIED':'AGREES_NEITHER';
   checks.quota={owner:quota.value,used15:fifteen,used00:midnight,
    localRemaining15:remaining15,localRemaining00:remaining00,
    kind,resetRuleIndependentlyVerified:false};
  }
  return {valid:true,readOnly:true,verifiedSportsData:false,
   capturedAtUtc:new Date(now).toISOString(),checks,
   disclaimer:'Owner-attested browser snapshot only. Nothing was submitted or saved. Live NBA FP and Sports.ru credited FP may have different clocks or scoring revisions.'};
 }
 return {compare,parseNumber};
});
