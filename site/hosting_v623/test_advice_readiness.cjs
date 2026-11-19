const assert=require('node:assert/strict');
const {inspect}=require('./advice_readiness.js');
const now=Date.parse('2026-11-07T13:30:00Z');
const players={};const roster=[];
for(const pos of ['PG','SG','SF','PF','C'])for(let i=0;i<2;i++){
 const id=pos+i;roster.push(id);players[id]={id,pos,team:id};
}
const base={nowEpoch:now,sourceVerified:true,feed:{mode:'live_sync',updated_at_utc:'2026-11-07T00:30:00Z'},
 roster,players,cash:100,calendarReady:true,startEpoch:now};
let a=inspect(base);assert.equal(a.ready,true);assert.equal(a.feedAgeHours,13);
for(const x of [
 {sourceVerified:false},
 {feed:{mode:'seed_partial_verified',updated_at_utc:'2026-11-07T00:30:00Z'}},
 {feed:{mode:'schedule_sync_only',updated_at_utc:'2026-11-07T00:30:00Z'}},
 {feed:{mode:'sync_failed_using_cache',updated_at_utc:'2026-11-07T00:30:00Z'}},
 {feed:{mode:'live_sync',updated_at_utc:'2026-11-05T00:00:00Z'}},
 {feed:{mode:'live_sync',updated_at_utc:'2026-11-08T00:00:00Z'}},
 {feed:{mode:'live_sync'}},
 {calendarReady:false},
 {cash:NaN},
 {cash:'100'},
 {startEpoch:now-60001},
 {startEpoch:null},
 {roster:[...roster.slice(1),roster[1]]},
 {roster:roster.slice(0,9)},
 {roster:roster.slice().reverse().fill('PG0',0,1)}
 ]){
 a=inspect({...base,...x});assert.equal(a.ready,false,JSON.stringify(x));assert(a.reasons.length);
}
const badClubs=Object.fromEntries(Object.entries(players).map(([k,p])=>[k,{...p}]));
badClubs.SG0.team=badClubs.PG0.team;badClubs.SF0.team=badClubs.PG0.team;
a=inspect({...base,players:badClubs});assert.equal(a.rosterReady,false);
const badPos=Object.fromEntries(Object.entries(players).map(([k,p])=>[k,{...p}]));
badPos.C0.pos='PG';a=inspect({...base,players:badPos});assert.equal(a.rosterReady,false);
assert.equal(inspect({...base,feed:{mode:'live_sync',updated_at_utc:'2026-11-06T13:30:00Z'}}).ready,true);
assert.equal(inspect({...base,feed:{mode:'live_sync',updated_at_utc:'2026-11-06T13:29:59Z'}}).ready,false);
assert.deepEqual(roster,['PG0','PG1','SG0','SG1','SF0','SF1','PF0','PF1','C0','C1']);
console.log('PASS advice readiness: feed provenance, 24h, 10 slots, cash and calendar');
