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
assert.equal(mod.checkpointSummary(rows).latestCapital.asOfDateMoscow,'2026-11-11');
assert.equal(mod.checkpointSummary(rows).latestCapital.officialMinusImplied,1);
assert.equal(mod.checkpointSummary(rows).latestCapital.sameAsLatest,false);
assert.equal(mod.checkpointSummary([rows[0]]).latestCapital.sameAsLatest,true);
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

// An opt-in private diagnostic export must preserve provenance and cut off
// player-game rows after the latest explicitly entered Moscow checkpoint.
const evidenceStore=new Map();
const evidenceStorage={getItem:k=>evidenceStore.has(k)?evidenceStore.get(k):null,
 setItem:(k,v)=>evidenceStore.set(k,v)};
mod.checkpointSave(evidenceStorage,state,{confirmed:true,asOfDateMoscow:'2026-11-11',fp:2362,rosterValue:22330,cash:31},now);
mod.checkpointSave(evidenceStorage,state,{confirmed:true,asOfDateMoscow:'2026-11-12',fp:2504},now);
const owner={...state,roster:[...state.initialRoster.slice(0,9),'n121'],cash:31,
 executed:[{out:state.initialRoster[9],in_:'n121',sportsRuDateMoscow:'2026-11-09',
  timePrecision:'date_only',epochIsPlaceholder:true,epoch:Date.parse('2026-11-09T12:00:00Z'),sell:1200,buy:1300}]};
const gameA={id:'g1',epoch:Date.parse('2026-11-11T01:00:00Z'),status:'final',home:'NYK',away:'BOS',et_date:'2026-11-10'};
const gameB={id:'g2',epoch:Date.parse('2026-11-13T12:00:00Z'),status:'final',home:'NYK',away:'BOS',et_date:'2026-11-13'};
const source={mode:'live_sync',updated_at_utc:'2026-11-13T07:00:00Z',
 games:[gameA,gameB],rows:[
  {id:'n121',game_id:'g1',fp:35,played:true,minutes:31},
  {id:state.initialRoster[0],game_id:'g1',fp:-2,played:true,minutes:10},
  {id:'n999',game_id:'g1',fp:100,played:true},
  {id:'n121',game_id:'g2',fp:50,played:true}]};
const beforeJson=JSON.stringify(owner);
const evidence=mod.exportReconciliation(evidenceStorage,owner,source,true,now);
assert.equal(evidence.kind,'NBA_SEASON_LAB_PRIVATE_RECONCILIATION_EXPORT');
assert.equal(evidence.sportsru_owner_checkpoints.length,2);
assert.equal(evidence.team_history.transfers[0].timePrecision,'date_only');
assert.equal(evidence.nba_source.rows.length,2);
assert.equal(evidence.nba_source.games.length,1);
assert.equal(evidence.nba_source.rows[1].fp,-2);
assert.equal(evidence.nba_source.rows.some(x=>x.id==='n999'),false);
assert.equal(evidence.nba_source.rows.some(x=>x.game_id==='g2'),false);
assert.equal(evidence.sportsru_owner_checkpoints.some(x=>x.ownerKey),false);
assert.equal(JSON.stringify(owner),beforeJson);
assert.throws(()=>mod.exportReconciliation(evidenceStorage,owner,source,false,now),/синхронизации/);
assert.throws(()=>mod.exportReconciliation(evidenceStorage,owner,{...source,mode:'seed'},true,now),/синхронизации/);
assert.throws(()=>mod.exportReconciliation(storage,owner,source,true,now),/повреждены/);

console.log('PASS owner-only dated Sports.ru FP checkpoint snapshots and fail-closed corruption');
