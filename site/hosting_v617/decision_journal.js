/* NBA Season Lab v6.12 -- opt-in, local-only prospective decision journal.
 * Freezes observed KEEP / NOW / LATER scenario inputs at a real user click.
 * Does not claim authentic Sports.ru quotes, PIT model issuance, actual
 * execution, or economic gain. Never writes to Firebase or remote APIs.
 */
(function(root, factory){
 'use strict';
 const api=factory(()=>Date.now());
 if(typeof module==='object'&&module.exports)module.exports={...api,_makeForTests:factory};
 root.NBADecisionJournal=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(nowMs){
 'use strict';
 const KEY='nba-season-lab-local-decision-journal-v1';
 const MAX=100,MAX_ROUTES=8,MAX_MOVES=4;
 const ID=/^n[0-9]{3,5}$/;
 const STATUS='owner_clicked_predecision_snapshot_unverified';
 const isNum=n=>typeof n==='number'&&Number.isFinite(n);
 const fail=code=>{throw new Error('DECISION_JOURNAL_'+code);};
 const ensure=(okay,code)=>{if(!okay)fail(code);};
 const clone=x=>JSON.parse(JSON.stringify(x));
 function instant(value){
   if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value))return NaN;
   const t=Date.parse(value);
   return Number.isFinite(t)?t:NaN;
 }
 function stamp(ms){
   ensure(Number.isSafeInteger(ms)&&ms>=Date.parse('2026-10-19T00:00:00Z')&&
     ms<Date.parse('2027-07-01T00:00:00Z'),'BROWSER_CLOCK_OUT_OF_SEASON');
   return new Date(ms).toISOString();
 }
 function empty(){
   return {schema_version:1,private_local_only:true,never_autosync:true,
     not_sportsru_attested:true,not_cryptographic_proof:true,entries:[]};
 }
 function validate(journal){
   ensure(journal&&journal.schema_version===1&&journal.private_local_only===true&&
     journal.never_autosync===true&&journal.not_sportsru_attested===true&&
     journal.not_cryptographic_proof===true&&Array.isArray(journal.entries)&&
     journal.entries.length<=MAX,'BAD_LOCAL_ARCHIVE');
   let last=-1;
   for(const e of journal.entries){
     ensure(e?.schema_version===1&&e?.status===STATUS&&
       e?.user_clicked_to_record===true&&e?.private_local_only===true&&
       e?.never_autosync===true&&e?.no_sportsru_transfer_executed===true&&
       e?.model_was_not_retrained===true&&e?.outcome?.status==='not_yet_independently_scored'&&
       e?.outcome?.actual_gain_fp===null&&e?.outcome?.real_transfer_benefit_proven===false,
       'MODIFIED_OR_UNTRUSTED_ENTRY');
     const t=instant(e.captured_at_utc);
     ensure(Number.isFinite(t)&&t>last,'CAPTURE_CLOCKS_NOT_STRICT');
     last=t;
     const s=e?.scenario;
     ensure(s&&[14,21,28].includes(s.horizon_days)&&
       isNum(s.baseline_fp)&&Array.isArray(s.routes)&&
       s.routes.length>=1&&s.routes.length<=MAX_ROUTES&&
       Number.isInteger(s.chosen_index)&&s.chosen_index>=0&&
       s.chosen_index<s.routes.length,'MODIFIED_SCENARIO');
     ensure(Array.isArray(e.owner_state?.roster_ids)&&e.owner_state.roster_ids.length===10&&
       e.owner_state.roster_ids.every(id=>typeof id==='string'&&ID.test(id))&&
       new Set(e.owner_state.roster_ids).size===10&&
       isNum(e.owner_state.cash_scenario)&&e.owner_state.cash_scenario>=0,
       'MODIFIED_PRIVATE_BASELINE');
     ensure(Number.isFinite(instant(e.decision_start_utc))&&
       Number.isFinite(instant(e.decision_end_utc))&&
       instant(e.decision_start_utc)>=t-60000&&
       instant(e.decision_end_utc)>instant(e.decision_start_utc),
       'MODIFIED_DECISION_CLOCK');
     for(const route of s.routes){
       ensure(['keep','now','later','multi_slot','same_slot_chain'].includes(route.kind)&&
         isNum(route.gain_fp)&&isNum(route.net_fp)&&
         Array.isArray(route.moves)&&route.moves.length<=MAX_MOVES,
         'MODIFIED_ROUTE');
       ensure((route.kind==='keep')===(route.moves.length===0),'ROUTE_NOT_KEEP_CONSISTENT');
       for(const m of route.moves){
         ensure(ID.test(m.out)&&ID.test(m.in_)&&m.out!==m.in_&&
           Number.isFinite(instant(m.execution_utc))&&
           instant(m.execution_utc)>=instant(e.decision_start_utc)&&
           instant(m.execution_utc)<instant(e.decision_end_utc)&&
           isNum(m.assumed_sell)&&m.assumed_sell>=0&&
           isNum(m.assumed_buy)&&m.assumed_buy>=0,
           'MODIFIED_MOVE');
       }
     }
     ensure(s.routes.some(r=>r.kind==='keep'),'NO_KEEP_COMPARISON');
   }
   return journal;
 }
 function read(storage){
   ensure(storage&&typeof storage.getItem==='function','NO_STORAGE');
   const raw=storage.getItem(KEY);
   if(raw===null)return empty();
   let parsed;
   try{parsed=JSON.parse(raw);}catch{fail('INVALID_JSON');}
   return clone(validate(parsed));
 }
 function take(storage,input){
   ensure(input?.userConfirmedNow===true,'CLICK_REQUIRED');
   const ms=nowMs(),capturedAt=stamp(ms);
   const p=input.plan;
   ensure(p?.ready===true&&[14,21,28].includes(p.horizonDays)&&
     isNum(p.start)&&isNum(p.end)&&p.end>p.start&&
     p.start>=ms-60000&&isNum(p.baseline),
     'NO_CURRENT_PROSPECTIVE_PLAN');
   const roster=input.roster;
   ensure(Array.isArray(roster)&&roster.length===10&&
     roster.every(id=>typeof id==='string'&&ID.test(id))&&
     new Set(roster).size===10,'INVALID_ROSTER');
   ensure(isNum(input.cash)&&input.cash>=0,'INVALID_CASH');
   ensure(Array.isArray(p.routes)&&p.routes.length>=1&&p.routes.length<=MAX_ROUTES&&
     Number.isInteger(input.chosenIndex)&&input.chosenIndex>=0&&
     input.chosenIndex<p.routes.length,'INVALID_ROUTE_CHOICE');
   const src=typeof input.liveUpdatedAtUtc==='string'?input.liveUpdatedAtUtc:null;
   const srcMs=src===null?NaN:instant(src);
   ensure(src===null||Number.isFinite(srcMs)&&srcMs<=ms,
     'FUTURE_OR_INVALID_LIVE_SOURCE');
   const normalized=[];
   for(const r of p.routes){
     ensure(r&&['keep','now','later','multi_slot','same_slot_chain'].includes(r.kind)&&
       isNum(r.gain)&&isNum(r.net)&&Array.isArray(r.moves)&&
       r.moves.length<=MAX_MOVES,'INVALID_ROUTE');
     ensure((r.kind==='keep')===(r.moves.length===0),'INVALID_KEEP_ROUTE');
     const normalizedMoves=[];
     for(const m of r.moves){
       ensure(m&&ID.test(m.out)&&ID.test(m.in_)&&m.out!==m.in_&&
         isNum(m.epoch)&&m.epoch>=p.start&&m.epoch<p.end&&
         isNum(m.sell)&&m.sell>=0&&isNum(m.buy)&&m.buy>=0,
         'INVALID_MOVE_OR_PRICE');
       normalizedMoves.push({out:m.out,in_:m.in_,execution_utc:stamp(m.epoch),
         assumed_sell:m.sell,assumed_buy:m.buy,
         prices_independently_verified:false});
     }
     normalized.push({kind:r.kind,gain_fp:r.gain,net_fp:r.net,
       hypothetical_not_observed_gain:true,moves:normalizedMoves});
   }
   ensure(normalized.some(r=>r.kind==='keep'),'MISSING_KEEP');
   const journal=read(storage);
   const prev=journal.entries.at(-1);
   ensure(!prev||instant(prev.captured_at_utc)<ms,'CLOCK_NOT_MONOTONE');
   ensure(journal.entries.length<MAX,'JOURNAL_FULL_EXPORT_FIRST');
   const entry={schema_version:1,status:STATUS,user_clicked_to_record:true,
     private_local_only:true,never_autosync:true,
     captured_at_utc:capturedAt,decision_start_utc:stamp(p.start),
     decision_end_utc:stamp(p.end),
     observed_public_feed_updated_at_utc:src,
     public_feed_freshness_proven:src!==null&&ms-srcMs<=4*3600000,
     frozen_original_model_issue_proven:false,
     owner_state:{roster_ids:[...roster],cash_scenario:input.cash,
       real_sportsru_account_independently_verified:false},
     scenario:{horizon_days:p.horizonDays,baseline_fp:p.baseline,
       chosen_index:input.chosenIndex,routes:normalized},
     outcome:{status:'not_yet_independently_scored',actual_gain_fp:null,
       real_transfer_benefit_proven:false,needs_sportsru_credited_player_games:true},
     no_sportsru_transfer_executed:true,model_was_not_retrained:true,
     caution:'Owner-clicked local observation, not independent source publication time or proof of real transfer advantage.'};
   const next={...journal,entries:[...journal.entries,entry]};
   validate(next);
   ensure(typeof storage.setItem==='function','NO_STORAGE_WRITE');
   try{storage.setItem(KEY,JSON.stringify(next));}
   catch{fail('STORAGE_WRITE_FAILED');}
   return clone(entry);
 }
 function exportData(storage){return read(storage);}
 function clear(storage,explicit){
   ensure(explicit===true,'EXPLICIT_ERASE_REQUIRED');
   ensure(storage&&typeof storage.removeItem==='function','NO_STORAGE');
   storage.removeItem(KEY);
 }
 return {KEY,read,take,exportData,clear,_status:STATUS};
});
