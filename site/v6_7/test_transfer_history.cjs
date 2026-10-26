'use strict';
const assert=require('node:assert/strict');
const H=require('./transfer_history');
const G=require('./transfer_guard');
const date=s=>Date.parse(s);
const t1=date('2026-10-22T10:00:00Z');
const t2=date('2026-10-23T12:00:00Z');
const t3=date('2026-10-24T11:00:00Z');
const now=date('2026-10-26T08:00:00Z');
const players={};
const initial=[];
for(const pos of ['PG','SG','SF','PF','C'])for(let i=0;i<2;i++){
 const id=pos+i;initial.push(id);players[id]={id,pos,team:'T'+pos+i};
 for(const v of ['x','y','z'])players[id+v]={id:id+v,pos,team:'K'+pos+i+v};
}
const move=(out,in_,epoch=t1,sell=1000,buy=900)=>({out,in_,epoch,sell,buy});
const base=()=>({initialRoster:initial,currentRoster:[...initial],currentCash:1300,
 existing:[],proposed:[],players,initialEpoch:date('2026-10-20T19:00:00Z'),nowEpoch:now,draftCount:0});
let passes=0;
const test=(name,fn)=>{try{fn();passes++;console.log('PASS',name)}catch(e){console.error('FAIL',name);throw e}};

test('Two historical moves replays through exact times and calculates cash delta',()=>{
 const s=base();s.proposed=[move('PG0','PG0x',t1,1000,1300),move('SG0','SG0x',t2,900,800)];
 const before=JSON.stringify(s);const r=H.preview(s);
 assert.equal(r.valid,true,JSON.stringify(r.errors));assert.equal(r.cash,1100);
 assert.equal(r.deltaCash,-200);assert.equal(r.roster.includes('PG0x'),true);
 assert.equal(r.roster.includes('SG0x'),true);assert.deepEqual(r.timeline.map(t=>t.source),['new','new']);
 assert.equal(JSON.stringify(s),before,'Pure preview may not mutate user state');
});
test('History insertion before recorded move replays chronologically',()=>{
 const s=base();s.existing=[move('PG0','PG0y',t3,900,1000)];s.currentRoster[0]='PG0y';
 // New move replaces an independent slot before the previously recorded move.
 s.proposed=[move('SG0','SG0x',t1,1000,900)];
 const r=H.preview(s);assert.equal(r.valid,true,JSON.stringify(r.errors));
 assert.equal(r.roster[0],'PG0y');assert.equal(r.roster[2],'SG0x');assert.equal(r.cash,1400);assert.deepEqual(r.timeline.map(t=>t.source),['new','existing']);
 assert.equal(r.mergedExecuted.length,2);
});
test('Backfill which invalidates later already recorded OUT fails closed',()=>{
 const s=base();s.existing=[move('PG0','PG0x',t3,1000,1100)];s.currentRoster[0]='PG0x';
 s.proposed=[move('PG0','PG0y',t1,1000,900)];
 const r=H.preview(s);assert.equal(r.valid,false);assert(r.errors.some(x=>x.includes('OUT')));
});
test('Duplicate historical operation cannot be added again',()=>{
 const s=base();s.existing=[move('PG0','PG0x',t1,1000,1100)];s.currentRoster[0]='PG0x';
 s.proposed=[move('PG0','PG0x',t1,1000,1100)];
 const r=H.preview(s);assert.equal(r.valid,false);assert(r.errors.some(x=>x.includes('Повтор')));
});
test('Wrong previously recorded current roster stops backfill',()=>{
 const s=base();s.existing=[move('PG0','PG0x',t3,1000,1100)];s.proposed=[move('SG0','SG0x',t2)];
 const r=H.preview(s);assert.equal(r.valid,false);assert(r.errors.some(x=>x.includes('Текущий состав')));
});
test('Cannot exceed three moves in same Moscow week',()=>{
 const s=base();s.existing=[move('PG0','PG0x',t1),move('SG0','SG0x',t2),move('SF0','SF0x',t3)];
 s.currentRoster[0]='PG0x';s.currentRoster[2]='SG0x';s.currentRoster[4]='SF0x';
 s.proposed=[move('C0','C0x',t3+60000)];
 const r=H.preview(s);assert.equal(r.valid,false);assert(r.errors.some(x=>x.includes('Больше трёх')));
});
test('Draft pending blocks retroactive mutation',()=>{const s=base();s.draftCount=1;s.proposed=[move('PG0','PG0x')];assert.equal(H.preview(s).valid,false)});
test('Cannot fake a future transfer as already done',()=>{const s=base();s.proposed=[move('PG0','PG0x',now+120000)];assert.equal(H.preview(s).valid,false)});
test('No blank or negative prices',()=>{for(const price of ['',null,-2]){const s=base();s.proposed=[move('PG0','PG0x',t1,1000,price)];assert.equal(H.preview(s).valid,false)}});
test('No incomplete historical roster',()=>{const s=base();s.initialRoster=[];s.proposed=[move('PG0','PG0x')];assert.equal(H.preview(s).valid,false)});
test('Cannot own same player twice, including historical path',()=>{const s=base();s.proposed=[move('PG0','PG1',t1)];assert.equal(H.preview(s).valid,false)});
test('Same fantasy position required',()=>{const s=base();s.proposed=[move('PG0','SF0x',t1)];assert.equal(H.preview(s).valid,false)});
test('Historical cash never allowed to go negative',()=>{const s=base();s.proposed=[move('PG0','PG0x',t1,1000,3500)];assert.equal(H.preview(s).valid,false)});
test('Newly backfilled moves do not overwrite executed records',()=>{
 const s=base();s.existing=[move('PG0','PG0x',t3,1000,950)];s.currentRoster[0]='PG0x';s.proposed=[move('SG0','SG0x',t2)];
 const r=H.preview(s);assert.equal(r.valid,true);assert.deepEqual(r.mergedExecuted.find(x=>x.out==='PG0'),s.existing[0]);
 assert.equal(r.newExecuted[0].origin,'manual_history_backfill');
});
test('Historical rosterBefore includes earlier new moves, not future',()=>{
 const s=base();s.proposed=[move('PG0','PG0x',t1),move('PG0x','PG0y',t3)];
 assert(H.rosterBefore(s,t2,1).includes('PG0x'));
 assert(!H.rosterBefore(s,t2,1).includes('PG0y'));
});
test('Moscow week matches original guard including overnight Monday',()=>{
 for(const stamp of ['2026-10-26T00:00:00Z','2026-10-25T21:30:00Z','2026-11-01T23:00:00Z'])
 assert.equal(H.weekKey(date(stamp)),G.weekKey(date(stamp)));
});
test('Current team cap violation is blocked even when past clubs are unverified',()=>{
 const s=base();players.PG0x.team=players.SG0.team;players.SF0x.team=players.SG0.team;
 s.proposed=[move('PG0','PG0x',t1),move('SF0','SF0x',t2)];
 const r=H.preview(s);assert.equal(r.valid,false);assert(r.errors.some(x=>x.includes('лимит двух')));
});
test('Stage same-minute operations explicitly follow entered order',()=>{
 const s=base();s.proposed=[move('PG0','PG0x',t1),move('PG0x','PG0y',t1)];
 const r=H.preview(s);assert.equal(r.valid,true);assert.equal(r.roster[0],'PG0y');
});
console.log('TRANSFER_HISTORY_TEST_PASS',passes);
