const test=require('node:test'),assert=require('node:assert/strict');
const j=require('./site/v6_12/decision_journal.js');
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
test('no entry without owner confirmation',()=>{const s=local(),a=engine(),x=fixture();delete x.userConfirmedNow;assert.throws(()=>a.take(s,x),/CLICK_REQUIRED/);assert.equal(s.store.size,0);});
test('snapshot freezes 3 routes, selected plan and no postgame proof',()=>{const s=local(),a=engine(),x=fixture();const e=a.take(s,x);x.plan.routes[1].gain=999;assert.equal(a.read(s).entries[0].scenario.routes[1].gain_fp,25.5);assert.equal(e.scenario.chosen_index,1);assert.equal(e.outcome.actual_gain_fp,null);assert.equal(e.no_sportsru_transfer_executed,true);});
test('no source does not fabricate freshness',()=>{const x=fixture(),s=local();x.liveUpdatedAtUtc=null;assert.equal(engine().take(s,x).public_feed_freshness_proven,false);});
test('future source fails closed',()=>{const x=fixture();x.liveUpdatedAtUtc='2026-11-01T09:00:01Z';assert.throws(()=>engine().take(local(),x),/FUTURE_OR_INVALID_LIVE_SOURCE/);});
test('cannot create retrospectively timed decision',()=>{const x=fixture();x.plan.start=NOW-120000;assert.throws(()=>engine().take(local(),x),/NO_CURRENT_PROSPECTIVE_PLAN/);});
test('missing projected FP is not zero',()=>{const x=fixture();x.plan.routes[1].gain=null;assert.throws(()=>engine().take(local(),x),/INVALID_ROUTE/);});
test('must include KEEP',()=>{const x=fixture();x.plan.routes.shift();x.chosenIndex=0;assert.throws(()=>engine().take(local(),x),/MISSING_KEEP/);});
test('future price assumptions remain explicitly not verified',()=>{const e=engine().take(local(),fixture());assert.equal(e.scenario.routes[1].moves[0].prices_independently_verified,false);});
test('same-clock duplicate rejected',()=>{const s=local(),a=engine();a.take(s,fixture());assert.throws(()=>a.take(s,fixture()),/CLOCK_NOT_MONOTONE/);});
test('next real click appends without rewriting old decision',()=>{const s=local();engine().take(s,fixture());const x=fixture();x.plan.start=NOW+180000;x.plan.end=x.plan.start+14*DAY;x.plan.routes[1].moves[0].epoch=x.plan.start;engine(NOW+120000).take(s,x);assert.equal(engine().read(s).entries.length,2);});
test('corrupted outcome cannot claim benefits',()=>{const s=local(),a=engine();a.take(s,fixture());const raw=JSON.parse(s.store.get(j.KEY));raw.entries[0].outcome.real_transfer_benefit_proven=true;s.store.set(j.KEY,JSON.stringify(raw));assert.throws(()=>a.read(s),/MODIFIED_OR_UNTRUSTED_ENTRY/);});
test('explicit clear affects journal key only',()=>{const s=local(),a=engine();a.take(s,fixture());s.store.set('sportsru_state','secret');assert.throws(()=>a.clear(s,false),/EXPLICIT_ERASE_REQUIRED/);a.clear(s,true);assert.equal(s.store.get('sportsru_state'),'secret');});
