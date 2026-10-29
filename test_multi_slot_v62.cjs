const test=require('node:test'),assert=require('node:assert/strict');
const p=require('./site/v6_2/multi_planner.js');
test('Moscow week Sunday crossing',()=>{assert.equal(p.weekKey(Date.parse('2026-10-25T20:59:59Z')),'2026-10-19');assert.equal(p.weekKey(Date.parse('2026-10-25T21:00:00Z')),'2026-10-26');});
test('No complete calendar means no transfer recommendation',()=>{const x=p.plan({roster:Array(10).fill('x'),whenEpoch:1,nowEpoch:1,coverage:()=>({ok:false})});assert.equal(x.ready,false);});
test('Invalid horizon rejected',()=>{assert.equal(p.plan({horizonDays:15}).ready,false);});

test('search does not falsely prune viable Monday-15 candidate',()=>{
 const start=Date.parse('2026-10-26T13:00:00Z');
 const pos=['PG','PG','SG','SG','SF','SF','PF','PF','C','C'];
 const roster=pos.map((_,i)=>'p'+i);
 const players={};
 roster.forEach((id,i)=>{players[id]={id,pos:pos[i],team:['BOS','NYK','ATL','MIA','DEN','CLE','PHI','SAS','GSW','LAL'][i],forecast:{}};});
 players.newPG={id:'newPG',pos:'PG',team:'WAS',forecast:{}};
 const scenario={
  players,roster,candidates:[{id:'newPG'}],
  nowEpoch:start,whenEpoch:start,horizonDays:14,
  maxMoves:1,opportunityPenalty:0,focusIds:['p0'],
  priceOf:()=>100,isCandidateAvailable:()=>true,
  coverage:()=>({ok:true,reason:'synthetic complete horizon'}),
  scorePlayer:id=>id==='newPG'?30:10,
  validateDraft:moves=>({valid:true,roster:[...roster],cash:100,
    used:{[p.weekKey(start)]:3},warnings:['Квота только условная']}),
  project:moves=>100+10*moves.length
 };
 const result=p.plan(scenario);
 assert.equal(result.ready,true);
 assert.equal(result.quotaResetVerified,false);
 assert.ok(result.routes.some(r=>r.moves.some(m=>m.in_==='newPG')));
 assert.ok(result.disclaimer.includes('квоты'));
});
