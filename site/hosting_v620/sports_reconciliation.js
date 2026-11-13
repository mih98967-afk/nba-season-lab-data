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
   // Owner's historical date-only imports carry hypothetical epoch anchors.
   // A recent Monday can straddle both reset hypotheses. Never present those
   // anchors as an independently reconstructed Sports.ru remaining quota.
   const uncertainRecent=Array.isArray(service.executed)&&service.executed.some(m=>m&&
    (m.timePrecision==='date_only'||m.epochIsPlaceholder===true)&&
    Number.isFinite(m.epoch)&&m.epoch>=now-14*DAY&&m.epoch<=now);
   if(uncertainRecent){
    checks.quota={owner:quota.value,used15:null,used00:null,localRemaining15:null,localRemaining00:null,
     kind:'HISTORICAL_DATE_ONLY_CLOCK_UNVERIFIED',resetRuleIndependentlyVerified:false};
   }else{
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
  }
  return {valid:true,readOnly:true,verifiedSportsData:false,
   capturedAtUtc:new Date(now).toISOString(),checks,
   disclaimer:'Owner-attested browser snapshot only. Nothing was submitted or saved. Live NBA FP and Sports.ru credited FP may have different clocks or scoring revisions.'};
 }
 // Private, dated Sports.ru totals. A past as-of date is owner testimony,
 // not an independently audited site snapshot or a reconstructed trade clock.
 const CHECKPOINT_KEY='nba-season-lab-private-fp-checkpoints-v1';
 const CHECKPOINT_SOURCE='owner_entered_sportsru_score_not_independently_verified';
 const DAY_MSK=3*3600000;
 const moscowDate=ms=>new Date(ms+DAY_MSK).toISOString().slice(0,10);
 function ownerKey(state){
  const ids=state?.initialRoster;
  if(!Array.isArray(ids)||ids.length!==10||new Set(ids).size!==10||
     !Number.isFinite(state.initialEpoch)||ids.some(id=>typeof id!=='string'||!id))return null;
  return String(state.initialEpoch)+'|'+ids.slice().sort().join('|');
 }
 function validDate(s){
  return typeof s==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(s)&&
   Number.isFinite(Date.parse(s+'T00:00:00+03:00'))&&
   moscowDate(Date.parse(s+'T00:00:00+03:00'))===s&&
   s>='2026-10-20'&&s<='2027-06-30';
 }
 function checkpointNumber(v,min,max,optional=false){
  if(optional&&(v===undefined||v===null||String(v).trim()===''))return null;
  const n=parseNumber(v,min,max,true);
  if(n===null)throw Error('Неверные числовые данные контрольной даты.');
  return n;
 }
 function validateCheckpoints(payload){
  if(!payload||payload.schema_version!==1||payload.private_local_only!==true||
     !Array.isArray(payload.rows)||payload.rows.length>40)throw Error('Локальные контрольные даты повреждены.');
  const keys=new Set();
  for(const row of payload.rows){
   if(!row||typeof row.ownerKey!=='string'||!row.ownerKey||!validDate(row.asOfDateMoscow)||
      !Number.isSafeInteger(row.fp)||row.fp < -100000||row.fp > 1000000||
      row.source!==CHECKPOINT_SOURCE||row.independent_verification!==false||
      typeof row.capturedAtUtc!=='string'||!Number.isFinite(Date.parse(row.capturedAtUtc))||
      !((row.rosterValue===null&&row.cash===null)||
       (Number.isSafeInteger(row.rosterValue)&&row.rosterValue>=0&&row.rosterValue<=1000000&&
        Number.isSafeInteger(row.cash)&&row.cash>=0&&row.cash<=20000)))throw Error('Некорректная запись контрольной даты.');
   const key=row.ownerKey+'|'+row.asOfDateMoscow;
   if(keys.has(key))throw Error('Повтор контрольной даты.');
   keys.add(key);
  }
  return payload;
 }
 function checkpointRead(storage,state){
  if(!storage||typeof storage.getItem!=='function')throw Error('Локальное хранилище недоступно.');
  const key=ownerKey(state);
  if(!key)return [];
  const raw=storage.getItem(CHECKPOINT_KEY);
  if(raw==null)return [];
  let parsed;try{parsed=JSON.parse(raw);}catch{throw Error('Локальные контрольные даты повреждены.');}
  return validateCheckpoints(parsed).rows.filter(row=>row.ownerKey===key)
   .sort((a,b)=>a.asOfDateMoscow.localeCompare(b.asOfDateMoscow));
 }
 function checkpointSave(storage,state,input,nowEpoch){
  const key=ownerKey(state);
  if(!key)throw Error('Сначала нужна подтверждённая исходная десятка.');
  if(!Number.isFinite(nowEpoch)||nowEpoch<=0||input?.confirmed!==true)
   throw Error('Подтвердите значение со Sports.ru.');
  const day=input.asOfDateMoscow;
  if(!validDate(day)||day>moscowDate(nowEpoch))throw Error('Некорректная или будущая дата по МСК.');
  const fp=checkpointNumber(input.fp,-100000,1000000);
  const rosterValue=checkpointNumber(input.rosterValue,0,1000000,true);
  const cash=checkpointNumber(input.cash,0,20000,true);
  if((rosterValue===null)!==(cash===null))throw Error('Стоимость десятки и кассу укажите вместе либо не указывайте.');
  // The existing records are checked before any write. Never overwrite history silently.
  const raw=storage.getItem(CHECKPOINT_KEY);
  let archive;
  if(raw===null)archive={schema_version:1,private_local_only:true,rows:[]};
  else {try{archive=validateCheckpoints(JSON.parse(raw));}catch(e){throw Error('Локальная история повреждена — сохранение остановлено: '+e.message);}}
  if(archive.rows.some(r=>r.ownerKey===key&&r.asOfDateMoscow===day))
   throw Error('Контрольная дата уже сохранена. Для исправления удалите её вручную.');
  if(archive.rows.length>=40)throw Error('Достигнут лимит локальных контрольных дат.');
  const row={ownerKey:key,asOfDateMoscow:day,fp,rosterValue,cash,
   capturedAtUtc:new Date(nowEpoch).toISOString(),source:CHECKPOINT_SOURCE,independent_verification:false};
  const next=validateCheckpoints({...archive,rows:[...archive.rows,row]});
  storage.setItem(CHECKPOINT_KEY,JSON.stringify(next));
  return row;
 }
 function checkpointDelete(storage,state,day,confirmed){
  if(confirmed!==true)throw Error('Подтвердите удаление контрольной даты.');
  const key=ownerKey(state);
  if(!key||!validDate(day))throw Error('Некорректная контрольная дата.');
  const raw=storage.getItem(CHECKPOINT_KEY);
  if(raw===null)return false;
  const parsed=validateCheckpoints(JSON.parse(raw));
  const remaining=parsed.rows.filter(r=>!(r.ownerKey===key&&r.asOfDateMoscow===day));
  if(remaining.length===parsed.rows.length)return false;
  storage.setItem(CHECKPOINT_KEY,JSON.stringify({...parsed,rows:remaining}));
  return true;
 }
 function checkpointSummary(rows,initialBudget=20000){
  if(!Array.isArray(rows)||!Number.isSafeInteger(initialBudget)||initialBudget<0)return null;
  const list=rows.slice().sort((a,b)=>a.asOfDateMoscow.localeCompare(b.asOfDateMoscow));
  if(!list.length)return {latest:null,previous:null,delta:null,capital:null};
  const latest=list.at(-1),previous=list.at(-2)||null;
  const capital=latest.rosterValue===null||latest.cash===null?null:
   {impliedFP:latest.rosterValue+latest.cash-initialBudget,
    officialMinusImplied:latest.fp-(latest.rosterValue+latest.cash-initialBudget)};
  return {latest,previous,delta:previous?latest.fp-previous.fp:null,capital};
 }
 return {compare,parseNumber,ownerKey,checkpointRead,checkpointSave,checkpointDelete,checkpointSummary,CHECKPOINT_KEY};
});
