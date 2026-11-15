const assert=require('node:assert/strict');
const G=require('./today_brief.js');
const now=Date.parse('2026-11-15T17:00:00Z');
const week15=t=>t<Date.parse('2026-11-16T12:00:00Z')?'old':'new';
const week00=t=>t<Date.parse('2026-11-15T21:00:00Z')?'old':'new';
let q=G.quotaSnapshot([],now,week15,week00);
assert.equal(q.known,true);assert.equal(q.used15,0);
assert.equal(q.independentSportsruVerification,false);
q=G.quotaSnapshot([{epoch:now-60000}],now,week15,week00);
assert.equal(q.known,true);assert.equal(q.used15,1);assert.equal(q.used00,1);
q=G.quotaSnapshot([{epoch:now-60000,timePrecision:'date_only',epochIsPlaceholder:true}],now,week15,week00);
assert.equal(q.known,false);assert.equal(q.used15,null);
q=G.quotaSnapshot([{epoch:now+60000*5}],now,week15,week00);
assert.equal(q.known,false);
q=G.quotaSnapshot([{epoch:NaN}],now,week15,week00);
assert.equal(q.known,false);
q=G.quotaSnapshot([{epoch:now-25*86400000,timePrecision:'date_only'}],now,week15,week00);
assert.equal(q.known,true,'Ancient date-only cannot affect current week');
const players={a:{team:'A'},b:{team:'B'},c:{team:'C'}};
const games=[
 {id:'1',epoch:now+5*60000,home:'A',away:'Z',status:'scheduled'},
 {id:'2',epoch:now+8*60000,home:'A',away:'Z',status:'scheduled'},
 {id:'3',epoch:now+10*60000,home:'A',away:'Z',status:'scheduled'},
 {id:'4',epoch:now+15*60000,home:'A',away:'Z',status:'scheduled'},
 {id:'5',epoch:now+2*3600000,home:'B',away:'Z',status:'scheduled'},
 {id:'6',epoch:now+1*3600000,home:'C',away:'Z',status:'scheduled'}
];
// The first four listed games are already locked. The correct next lock is #6,
// NOT null, even when the UI only shows four fixtures.
let lock=G.nextRosterLock(games,['a','b','c'],players,now);
assert.equal(lock.gameId,'6');assert.deepEqual(lock.playerIds,['c']);
assert.equal(lock.lockAt,now+30*60000);
assert.equal(G.nextRosterLock(games,['a'],players,now),null);
assert.equal(G.nextRosterLock([{...games[5],status:'final'}],['c'],players,now),null);
const planned={ready:true,signature:'roster-v1',horizonDays:7,start:now+20*60000,
 routes:[{kind:'now',moves:[{epoch:now+20*60000}]}]};
const args={result:planned,calculatedAt:now,nowMs:now,signature:'roster-v1',horizonDays:7,preflightReady:true};
assert(G.freshScenario(args));
assert.equal(G.freshScenario({...args,preflightReady:false}),null);
assert.equal(G.freshScenario({...args,signature:'changed-roster'}),null);
assert.equal(G.freshScenario({...args,horizonDays:14}),null);
assert.equal(G.freshScenario({...args,nowMs:now+25*60000}),null,'Start already passed');
assert.equal(G.freshScenario({...args,nowMs:now+31*60000}),null,'Stale calculation');
assert.equal(G.freshScenario({...args,result:{...planned,routes:[{moves:[{epoch:now-60000*3}]}]}}),null);
assert.equal(G.freshScenario({...args,result:{...planned,start:NaN}}),null);
console.log('PASS: daily as-of, quota precision and full-calendar next lock');
