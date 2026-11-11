const assert=require('node:assert/strict');
const {preview,weekKey}=require('./transfer_history.js');
const guard=require('./transfer_guard.js');
const POS=['PG','SG','SF','PF','C'];
const initial=Array.from({length:10},(_,i)=>'p'+i);
const players={};
for(let i=0;i<10;i++)players['p'+i]={pos:POS[Math.floor(i/2)],team:'T'+i};
for(let i=0;i<4;i++)players['q'+i]={pos:players['p'+i].pos,team:'Z'+i};
const make=(times)=>times.map((date,i)=>({out:'p'+i,in_:'q'+i,sell:100,buy:100,epoch:Date.parse(date)}));
const input={initialRoster:initial,currentRoster:initial,existing:[],proposed:[],players,
 currentCash:200,nowEpoch:Date.parse('2026-11-02T09:00:00Z'),initialEpoch:Date.parse('2026-10-20T00:00:00Z'),draftCount:0};
const split=make(['2026-10-30T09:00:00Z','2026-10-31T09:00:00Z','2026-11-01T09:00:00Z','2026-11-02T07:00:00Z']);
let result=preview({...input,proposed:split});
assert.equal(result.valid,true,JSON.stringify(result.errors));
assert.equal(result.stepsAdded,4);
assert.equal(result.warnings.some(x=>/Sports\.ru/.test(x)),true);
assert.equal(result.used['2026-10-26'],4);
assert.equal(result.roster.length,10);
assert.equal(result.cash,200);
const both=make(['2026-10-27T09:00:00Z','2026-10-28T09:00:00Z','2026-10-29T09:00:00Z','2026-10-30T09:00:00Z']);
result=preview({...input,proposed:both});
assert.equal(result.valid,true,'Owner-attested completed moves must not be discarded solely because both guessed quota windows disagree');
assert.equal(result.historicalQuotaConflict,true);
assert.equal(result.stepsAdded,4);
assert.equal(result.warnings.some(x=>/Sports\.ru/.test(x)),true);
assert.equal(result.roster.length,10);
// A bad move still fails: only the historical quota assumption is downgraded.
const invalid=[...both.map(m=>({...m}))];
invalid[3].out=invalid[2].out;
result=preview({...input,proposed:invalid});
assert.equal(result.valid,false);
assert.equal(result.errors.some(x=>/OUT/.test(x)),true);
const duplicate=make(['2026-10-30T09:00:00Z','2026-10-30T09:00:00Z']);
result=preview({...input,proposed:duplicate});
assert.equal(result.valid,true);
assert.equal(result.stepsAdded,2);
const badCash=make(['2026-10-30T09:00:00Z']);badCash[0].buy=500;
result=preview({...input,proposed:badCash});
assert.equal(result.valid,false);
assert.equal(weekKey(Date.parse('2026-11-02T07:00:00Z'),15),'2026-10-26');
assert.equal(weekKey(Date.parse('2026-11-02T07:00:00Z'),0),'2026-11-02');
// A historical week in disagreement must not permanently block a fresh week.
// New moves in their OWN week still face the 3-transfer safety hypotheses.
const oldFive=[
 '2026-10-26T17:00:00Z','2026-10-27T17:00:00Z',
 '2026-10-28T17:00:00Z','2026-10-29T17:00:00Z',
 '2026-10-30T17:00:00Z'
].map(epoch=>({epoch:Date.parse(epoch)}));
const freshMove={out:'p0',in_:'q0',sell:100,buy:100,
 epoch:Date.parse('2026-11-10T17:00:00Z')};
const futureInput={players,roster:initial,cash:200,executed:oldFive,
 nowEpoch:Date.parse('2026-11-09T20:00:00Z'),
 draft:[freshMove],games:[]};
let future=guard.validate(futureInput);
assert.equal(future.historicalQuotaConflict,true);
assert.equal(future.valid,true,JSON.stringify(future.errors));
assert.equal(future.used['2026-11-09'],1);
const extraFresh=[
 {out:'p1',in_:'q1',sell:100,buy:100,epoch:Date.parse('2026-11-10T18:00:00Z')},
 {out:'p2',in_:'q2',sell:100,buy:100,epoch:Date.parse('2026-11-11T18:00:00Z')},
 {out:'p3',in_:'q3',sell:100,buy:100,epoch:Date.parse('2026-11-12T18:00:00Z')}
];
future=guard.validate({...futureInput,draft:[freshMove,...extraFresh]});
assert.equal(future.valid,false,'Four proposed transfers within the new week must remain blocked');
assert.equal(future.errors.some(x=>/Превышены три замены/.test(x)),true);
console.log('transfer history two-hypothesis quota: regression passed');

// A future planner must not silently treat date-only historical epochs as factual.
{
 const players={a:{id:'a',pos:'PG',team:'A'},b:{id:'b',pos:'PG',team:'B'},c:{id:'c',pos:'PG',team:'C'}};
 const roster=['a','q1','q2','q3','q4','q5','q6','q7','q8','q9'];
 for(let i=1;i<=9;i++)players['q'+i]={id:'q'+i,pos:['PG','SG','SG','SF','SF','PF','PF','C','C'][i-1],team:'T'+i};
 const stamp=Date.parse('2026-11-11T10:00:00Z');
 const res=guard.validate({players,roster,cash:200,executed:[{epoch:stamp-86400000,timePrecision:'date_only',epochIsPlaceholder:true}],draft:[{out:'a',in_:'c',sell:100,buy:100,epoch:stamp+60000}],games:[],nowEpoch:stamp});
 assert(res.warnings.some(w=>w.includes('Исторические часы замен условные')));
 assert.equal(res.verified,false);
}
