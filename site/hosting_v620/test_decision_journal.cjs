const test=require('node:test'), assert=require('node:assert/strict');
const j=require('./decision_journal.js');
const NOW=Date.parse('2026-11-01T09:00:00Z'),DAY=86400000;
const roster=Array.from({length:10},(_,i)=>'n'+String(i+101));
const local=()=>{const m=new Map();return {getItem:k=>m.has(k)?m.get(k):null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k),store:m};};
const fixture=()=>({userConfirmedNow:true,roster,cash:850,liveUpdatedAtUtc:'2026-11-01T06:09:10Z',chosenIndex:1,
 plan:{ready:true,horizonDays:14,start:NOW+60000,end:NOW+14*DAY+60000,baseline:650,routes:[
  {kind:'keep',gain:0,net:0,moves:[]},
  {kind:'now',gain:25.5,net:21.5,moves:[{out:'n101',in_:'n222',epoch:NOW+60000,sell:1345,buy:1200}]},
  {kind:'later',gain:14.2,net:10.2,moves:[{out:'n101',in_:'n222',epoch:NOW+2*DAY,sell:1345,buy:1200}]}
 ]}});
const engine=(ms=NOW)=>j._makeForTests(()=>ms);
test('nothing is stored until the owner explicitly clicks',()=>{
 const s=local(),a=engine();assert.equal(a.read(s).entries.length,0);
 const x=fixture();delete x.userConfirmedNow;
 assert.throws(()=>a.take(s,x),/CLICK_REQUIRED/);
 assert.equal(s.store.size,0);
});
test('freeze all alternatives and preserve immutable as-of times locally only',()=>{
 const s=local(),a=engine(),x=fixture();
 const frozen=a.take(s,x);assert.equal(frozen.scenario.routes.length,3);
 assert.equal(frozen.scenario.chosen_index,1);
 assert.equal(frozen.scenario.routes[1].gain_fp,25.5);
 assert.equal(frozen.outcome.actual_gain_fp,null);
 assert.equal(frozen.public_feed_freshness_proven,true);
 assert.equal(frozen.no_sportsru_transfer_executed,true);
 assert.equal(frozen.frozen_original_model_issue_proven,false);
 x.plan.routes[1].gain=999;x.roster[0]='n999';
 assert.equal(a.read(s).entries[0].scenario.routes[1].gain_fp,25.5);
 assert.equal(a.read(s).entries[0].owner_state.roster_ids[0],'n101');
 assert.equal(s.store.size,1);
});
test('a missing LIVE source is marked unknown rather than manufactured freshness',()=>{
 const s=local(),a=engine(),x=fixture();x.liveUpdatedAtUtc=null;
 const frozen=a.take(s,x);assert.equal(frozen.public_feed_freshness_proven,false);
 assert.equal(frozen.observed_public_feed_updated_at_utc,null);
});
test('source from the future cannot be frozen as known',()=>{
 const s=local(),a=engine(),x=fixture();x.liveUpdatedAtUtc='2026-11-01T09:00:01.000Z';
 assert.throws(()=>a.take(s,x),/FUTURE_OR_INVALID_LIVE_SOURCE/);
});
test('decisions in the past are rejected rather than reissued',()=>{
 const s=local(),a=engine(),x=fixture();x.plan.start=NOW-2*60000;
 assert.throws(()=>a.take(s,x),/NO_CURRENT_PROSPECTIVE_PLAN/);
});
test('unknown FP is refused, never changed into zero',()=>{
 const s=local(),a=engine(),x=fixture();x.plan.routes[1].gain=null;
 assert.throws(()=>a.take(s,x),/INVALID_ROUTE/);
});
test('missing KEEP is refused',()=>{
 const s=local(),a=engine(),x=fixture();x.plan.routes.shift();x.chosenIndex=0;
 assert.throws(()=>a.take(s,x),/MISSING_KEEP/);
});
test('future planned prices are explicitly NOT independently verified',()=>{
 const s=local(),a=engine();const e=a.take(s,fixture());
 assert.equal(e.scenario.routes[1].moves[0].prices_independently_verified,false);
 assert.equal(e.scenario.routes[2].moves[0].assumed_sell,1345);
});
test('repeating a capture at identical UTC millisecond is blocked',()=>{
 const s=local(),a=engine();a.take(s,fixture());
 assert.throws(()=>a.take(s,fixture()),/CLOCK_NOT_MONOTONE/);
});
test('sequential captures preserve history without overwriting prior decision',()=>{
 const s=local(),a=engine(),x=fixture();a.take(s,x);
 const later=engine(NOW+2*60000),y=fixture();y.plan.start=NOW+3*60000;
 y.plan.end=y.plan.start+14*DAY;
 y.plan.routes[1].moves[0].epoch=y.plan.start;
 later.take(s,y);
 assert.equal(later.read(s).entries.length,2);
 assert.equal(later.read(s).entries[0].scenario.routes[1].gain_fp,25.5);
});
test('corrupted archive is not silently accepted',()=>{
 const s=local(),a=engine();a.take(s,fixture());
 const raw=JSON.parse(s.store.get(j.KEY));raw.entries[0].outcome.real_transfer_benefit_proven=true;
 s.store.set(j.KEY,JSON.stringify(raw));
 assert.throws(()=>a.read(s),/MODIFIED_OR_UNTRUSTED_ENTRY/);
});
test('clear requires explicit owner action and touches only its own key',()=>{
 const s=local(),a=engine();a.take(s,fixture());s.store.set('sportsru_local_state','private data');
 assert.throws(()=>a.clear(s,false),/EXPLICIT_ERASE_REQUIRED/);
 a.clear(s,true);
 assert.equal(s.store.get('sportsru_local_state'),'private data');
 assert.equal(a.read(s).entries.length,0);
});
