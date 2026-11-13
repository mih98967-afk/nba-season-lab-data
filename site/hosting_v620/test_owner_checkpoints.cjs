const assert=require('node:assert/strict');
const mod=require('./sports_reconciliation.js');
const state={initialRoster:Array.from({length:10},(_,i)=>'n'+String(i).padStart(3,'0')),initialEpoch:Date.parse('2026-10-20T19:00:00Z')};
const store=new Map();
const storage={getItem:k=>store.has(k)?store.get(k):null,setItem:(k,v)=>store.set(k,v)};
const now=Date.parse('2026-11-13T08:00:00Z');
const capture=(date,fp,rosterValue,cash)=>mod.checkpointSave(storage,state,{confirmed:true,asOfDateMoscow:date,fp,rosterValue,cash},now);
assert.deepEqual(mod.checkpointRead(storage,state),[]);
capture('2026-11-11',2362,22330,31);
capture('2026-11-12',2504,null,null);
let rows=mod.checkpointRead(storage,state);
assert.equal(rows.length,2);
assert.equal(mod.checkpointSummary(rows).delta,142);
assert.equal(mod.checkpointSummary([rows[0]]).capital.impliedFP,2361);
assert.equal(mod.checkpointSummary([rows[0]]).capital.officialMinusImplied,1);
assert.equal(mod.checkpointSummary(rows).capital,null);
assert.equal(rows[0].independent_verification,false);
assert.equal(rows[0].source,'owner_entered_sportsru_score_not_independently_verified');
for(const bad of [
 {confirmed:false,asOfDateMoscow:'2026-11-10',fp:2},
 {confirmed:true,asOfDateMoscow:'2026-11-14',fp:2},
 {confirmed:true,asOfDateMoscow:'2026-11-10',fp:'',rosterValue:2,cash:2},
 {confirmed:true,asOfDateMoscow:'2026-11-10',fp:'not a number'},
 {confirmed:true,asOfDateMoscow:'2026-11-10',fp:0,rosterValue:22330},
 {confirmed:true,asOfDateMoscow:'2026-11-10',fp:0,rosterValue:20000,cash:-1},
 {confirmed:true,asOfDateMoscow:'2026-11-11',fp:2362}
 ])assert.throws(()=>mod.checkpointSave(storage,state,bad,now));
assert.equal(mod.checkpointRead(storage,{...state,initialRoster:[...state.initialRoster.slice(0,9),'other']}).length,0);
assert.equal(mod.checkpointDelete(storage,state,'2026-11-12',true),true);
assert.equal(mod.checkpointRead(storage,state).length,1);
assert.equal(mod.checkpointDelete(storage,state,'2026-11-12',true),false);
assert.throws(()=>mod.checkpointDelete(storage,state,'2026-11-11',false));
store.set(mod.CHECKPOINT_KEY,'{broken');
assert.throws(()=>mod.checkpointRead(storage,state));
assert.throws(()=>capture('2026-11-10',100,null,null)); // no overwrite if corrupt
assert.equal(store.get(mod.CHECKPOINT_KEY),'{broken');
console.log('PASS owner-only dated Sports.ru FP checkpoint snapshots and fail-closed corruption');
