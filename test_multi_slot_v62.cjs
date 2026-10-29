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

function pairFixture(){
 const start=Date.parse('2026-10-29T00:00:00Z'),DAY=86400000;
 const pos=['PG','PG','SG','SG','SF','SF','PF','PF','C','C'];
 const roster=pos.map((_,i)=>'p'+i);
 const teams=['BOS','NYK','ATL','MIA','DEN','CLE','PHI','SAS','GSW','LAL'];
 const players={};
 roster.forEach((id,i)=>{players[id]={id,pos:pos[i],team:teams[i],forecast:{}};});
 players.newPG={id:'newPG',pos:'PG',team:'WAS',forecast:{}};
 const games=[start+DAY,start+5*DAY];
 const project=(moves,from,to)=>{
  let points=0;
  for(const game of games){
   if(game<from||game>=to)continue;
   let owned='p0';
   for(const move of [...moves].sort((a,b)=>a.epoch-b.epoch)){
    if(move.epoch<=game-30*60000&&move.out===owned)owned=move.in_;
   }
   points+=owned==='newPG'?25:10;
  }
  return points;
 };
 const validateDraft=moves=>{
  const ids=[...roster];
  for(const m of moves){
   const slot=ids.indexOf(m.out);
   if(slot<0||ids.includes(m.in_))return {valid:false,roster:ids,cash:100,used:{}};
   ids[slot]=m.in_;
  }
  return {valid:true,roster:ids,cash:100,used:{},warnings:[]};
 };
 return {players,roster,candidates:[{id:'newPG'}],existingDraft:[],
  nowEpoch:start,whenEpoch:start,horizonDays:14,maxMoves:1,
  opportunityPenalty:0,focusIds:['p0'],priceOf:()=>100,
  coverage:()=>({ok:true,reason:'synthetic confirmed calendar'}),
  isCandidateAvailable:()=>true,
  scorePlayer:(id,a,b)=>games.filter(g=>g>=a&&g<b).length*(id==='newPG'?25:10),
  project,validateDraft};
}
test('KEEP / NOW / LATER all appear and compare exactly the same pair',()=>{
 const result=p.plan(pairFixture());
 assert.equal(result.ready,true);
 const keep=result.routes.find(r=>r.kind==='keep');
 const now=result.routes.find(r=>r.kind==='now');
 const later=result.routes.find(r=>r.kind==='later');
 assert.ok(keep&&now&&later);
 assert.equal(keep.gain,0);
 assert.equal(now.moves.length,1);
 assert.equal(later.moves.length,1);
 assert.equal(now.moves[0].out,later.moves[0].out);
 assert.equal(now.moves[0].in_,later.moves[0].in_);
 assert.equal(now.gain,30);
 assert.equal(later.gain,15);
 assert.equal(later.samePairNow.status,'comparable_scenario');
 assert.equal(later.samePairNow.gainNowFP,30);
 assert.equal(later.samePairNow.waitMinusNowFP,-15);
 assert.equal(later.samePairNow.identicalPair,true);
 assert.equal(later.samePairNow.futurePricesAssumedUnchanged,true);
 assert.equal(result.kind,'bounded_scenario_not_validated');
 assert.ok(result.routes.length<=5);
});
test('unavailable NOW never fabricates gain from waiting',()=>{
 const s=pairFixture(),original=s.validateDraft;
 s.validateDraft=moves=>moves.some(m=>m.epoch===s.whenEpoch)
  ?{valid:false,roster:s.roster,cash:100,used:{},errors:['synthetic lock']}
  :original(moves);
 const result=p.plan(s);
 const later=result.routes.find(r=>r.kind==='later');
 assert.ok(later);
 assert.equal(later.samePairNow.status,'not_comparable');
 assert.equal(result.routes.some(r=>r.kind==='now'),false);
});
test('null FP is missing, not zero, so the candidate is excluded',()=>{
 const s=pairFixture();
 s.scorePlayer=(id,a,b)=>id==='newPG'?null:10;
 const result=p.plan(s);
 assert.equal(result.ready,true);
 assert.equal(result.routes.length,1);
 assert.equal(result.routes[0].kind,'keep');
});
