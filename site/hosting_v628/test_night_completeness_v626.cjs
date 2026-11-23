'use strict';
// Regression for the difference between partial NBA final boxscores and a whole ET day.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'app.js'),'utf8');
const start=script.indexOf('// Player-market windows are separate'),end=script.indexOf('function playerList(){',start);
assert(start>0&&end>start);
const tick=Date.parse('2026-11-23T09:00:00Z');
const roster=Array.from({length:10},(_,i)=>'n'+i);
const schedule=[
 {id:'g1',home:'BOS',away:'NYK',et_date:'2026-11-22',status:'final'},
 {id:'g2',home:'PHI',away:'MIL',et_date:'2026-11-22',status:'scheduled'},
];
const final=(id,home,away)=>({id,home,away,et_date:'2026-11-22',status:'final',epoch:tick-3600000});
const rowsFor=(id,home,away)=>[
 ...Array.from({length:7},(_,i)=>({id:i===0?'n0':id+'h'+i,game_id:id,team:home,played:true,fp:i===0?13:1})),
 ...Array.from({length:6},(_,i)=>({id:i===0?'n1':id+'a'+i,game_id:id,team:away,played:true,fp:i===0?-2:1}))
];
const LIVE={mode:'live_sync',updated_at_utc:'2026-11-23T08:55:00Z',
 schedule,games:[final('g1','BOS','NYK')],rows:rowsFor('g1','BOS','NYK')};
const context={UI:{marketPeriod:'preset',window:7},S:{roster},LIVE,publicFeedValidated:true,
 Date,Math,Number,String,Set,Map,now:()=>tick,calendarCoverage:()=>({ok:true}),
 normalizedGames:()=>[],console};
vm.createContext(context);vm.runInContext(script.slice(start,end),context);
const run=()=>vm.runInContext('marketNightStatus()',context);
let result=run();
assert.equal(result.complete,false,'One final among two games is not a complete ET date');
assert.equal(result.confirmed,1);assert.equal(result.expected,2);
assert.equal(result.fp,null,'Partial night must never be rendered as final FP');
LIVE.games.push(final('g2','PHI','MIL'));
LIVE.rows.push(...rowsFor('g2','PHI','MIL'));
result=run();
assert.equal(result.complete,true);
assert.equal(result.fp,22,'Negative fantasy points must remain signed');
assert.equal(result.creditedBySportsRu,false);
LIVE.rows.push({...LIVE.rows[0]});
result=run();assert.equal(result.complete,false);assert.equal(result.fp,null);
LIVE.rows.pop();LIVE.schedule[1].home='WRONG';
result=run();assert.equal(result.complete,false);assert.equal(result.confirmed,1);
LIVE.schedule[1].home='PHI';context.publicFeedValidated=false;
assert.equal(run(),null);
context.publicFeedValidated=true;LIVE.schedule=[];assert.equal(run(),null);
assert(!script.includes('S.roster=BASE.players'),'No unexpected roster replacement');
console.log('PASS v6.26: partial/full ET night, negative FP, conflict, duplicate, unverified and Sports.ru distinction');
