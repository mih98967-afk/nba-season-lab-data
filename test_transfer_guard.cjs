const test=require('node:test'),assert=require('node:assert/strict'),g=require('./site/transfer_guard.js');
const ms=s=>Date.parse(s);
test('calendar week ends Monday 00 MSK',()=>{
 assert.equal(g.weekKey(ms('2026-10-25T20:59:59Z')),'2026-10-19');
 assert.equal(g.weekKey(ms('2026-10-25T21:00:00Z')),'2026-10-26');
 assert.equal(g.calendarWeekEnd(ms('2026-10-24T12:00:00Z')),ms('2026-10-25T21:00:00Z'));
});
const pos=['PG','PG','SG','SG','SF','SF','PF','PF','C','C'];const clubs=['BOS','NYK','BOS','NYK','MIA','ATL','MIA','ATL','WAS','SAS'];
const players={};for(let i=0;i<10;i++)players['p'+i]={id:'p'+i,name:'p'+i,pos:pos[i],team:clubs[i]};
players.p10={id:'p10',name:'p10',pos:'PG',team:'CLE'};
players.p11={id:'p11',name:'p11',pos:'PG',team:'BOS'};
const roster=pos.map((_,i)=>'p'+i),tip=ms('2026-10-25T20:00:00Z');
const base=(draft=[])=>({players,roster,cash:150,executed:[],draft,games:[{home:'MIA',away:'BOS',epoch:tip,status:'scheduled'}],scheduleVerified:true,nowEpoch:ms('2026-10-24T09:00:00Z')});
const move=(time=tip-31*60000)=>({out:'p0',in_:'p10',epoch:time,sell:100,buy:130});
test('cash and positions stay valid, state immutable',()=>{
 const input=base([move()]),result=g.validate(input);
 assert.equal(result.valid,true);assert.equal(result.cash,120);assert.equal(result.roster[0],'p10');assert.equal(input.roster[0],'p0');
 assert.equal(result.verified,false);
});
test('reject negative funds and empty prices',()=>{
 assert.equal(g.validate(base([{...move(),buy:600}])).valid,false);
 assert.equal(g.validate(base([{...move(),sell:null}])).valid,false);
});
test('lock at exact minus 30 minutes',()=>{
 assert.equal(g.validate(base([move(tip-30*60000)])).valid,false);
 assert.equal(g.validate(base([move(tip-31*60000)])).valid,true);
});
test('after match unlock remains uncertain',()=>{
 const r=g.validate(base([move(tip+60000)]));
 assert.equal(r.valid,true);assert.equal(r.verified,false);
 assert.ok(r.warnings.some(v=>v.includes('разблокировки')));
});
test('three weekly operations max',()=>{
 const x=base([move()]);
 x.executed=[ms('2026-10-22T10:00:00Z'),ms('2026-10-23T10:00:00Z'),ms('2026-10-24T10:00:00Z')].map(epoch=>({epoch}));
 assert.equal(g.validate(x).valid,false);
});
test('team cap',()=>{
 const m={...move(),out:'p1',in_:'p11'};assert.equal(g.validate(base([m])).valid,false);
});
test('missing schedule must be flagged',()=>{
 const x=base([move()]);x.games=[];x.scheduleVerified=false;
 const r=g.validate(x);assert.equal(r.verified,false);assert.ok(r.warnings.some(v=>v.includes('календаря')));
});