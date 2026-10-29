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

const guard=require('./site/transfer_guard.js');
// Independent fixture-by-fixture oracle: a bought player never earns FP
// from fixtures that occurred before that transfer's execution time.
function chainScenario(){
 const start=Date.parse('2026-10-26T12:00:00Z'); // Monday 15 MSK
 const DAY=86400000, dates=[1,5,9,16].map(d=>start+d*DAY);
 const positions=['PG','PG','SG','SG','SF','SF','PF','PF','C','C'];
 const clubs=['BOS','NYK','ATL','MIA','DEN','CLE','PHI','SAS','GSW','LAL'];
 const roster=positions.map((_,i)=>'p'+i),players={};
 roster.forEach((id,i)=>{players[id]={id,pos:positions[i],team:clubs[i],forecast:{}};});
 players.mid={id:'mid',pos:'PG',team:'WAS',forecast:{}};
 players.target={id:'target',pos:'PG',team:'DET',forecast:{}};
 const table={p0:[10,10,10,10],mid:[30,30,0,0],target:[0,0,40,40]};
 const fp=(id,i)=>(table[id]||[0,0,0,0])[i];
 const scorePlayer=(id,a,b)=>dates.reduce((s,g,i)=>s+(g>=a&&g<b?fp(id,i):0),0);
 const project=(moves,a,b)=>{
  let total=0;
  for(let i=0;i<dates.length;i++){
   const game=dates[i];
   if(game<a||game>=b)continue;
   const owned=[...roster];
   for(const t of [...moves].sort((x,y)=>x.epoch-y.epoch)){
    if(t.epoch>game-30*60000)break;
    const index=owned.indexOf(t.out);
    if(index>=0)owned[index]=t.in_;
   }
   total+=owned.reduce((s,id)=>s+fp(id,i),0);
  }
  return total;
 };
 const games=dates.map(epoch=>({epoch,home:'BOS',away:'NYK',status:'scheduled'}));
 const validator=executed=>draft=>guard.validate({
  players,roster,cash:100,executed,draft,games,
  scheduleVerified:true,nowEpoch:start
 });
 return {start,dates,players,roster,candidates:[{id:'mid'},{id:'target'}],
  existingDraft:[],nowEpoch:start,whenEpoch:start,horizonDays:21,
  maxMoves:2,opportunityPenalty:0,focusIds:['p0'],
  priceOf:()=>100,isCandidateAvailable:()=>true,
  coverage:()=>({ok:true,reason:'synthetic complete fixture list'}),
  scorePlayer,project,validateDraft:validator([]),validator};
}
test('cross-week two-step chain adds only fixtures owned AFTER each purchase',()=>{
 const s=chainScenario(), result=p.plan(s);
 assert.equal(result.ready,true);
 const c=result.routes.find(r=>r.kind==='same_slot_chain'&&
  r.moves.length===2&&r.moves[0].out==='p0'&&r.moves[0].in_==='mid'&&
  r.moves[1].out==='mid'&&r.moves[1].in_==='target');
 assert.ok(c,'valid cross-week chain should be present in top routes');
 assert.equal(c.moves[0].epoch,s.start);
 assert.ok(c.moves[1].epoch>s.dates[1]&&c.moves[1].epoch<s.dates[2]-30*60000);
 assert.equal(result.baseline,40);
 assert.equal(s.project(c.moves,s.start,result.end),140);
 assert.equal(c.gain,100);
 assert.equal(c.net,100);
 assert.equal(c.weeks.reduce((sum,w)=>sum+w.gain,0),c.gain);
 assert.equal(c.usedByWeek['2026-10-26'],1);
 assert.equal(c.usedByWeek['2026-11-02'],1);
 assert.equal(c.alternateQuotaWeeks['2026-10-26'],1);
 assert.equal(c.alternateQuotaWeeks['2026-11-02'],1);
 assert.equal(c.weeks[0].usedIf15,1);
 assert.equal(c.weeks[1].usedIf15,1);
 assert.equal(c.quotaResetVerified,false);
});
test('Monday 15 reset hypothesis is shown alongside midnight quota, not hidden',()=>{
 const s=chainScenario();
 const executed=[
  '2026-10-26T07:00:00Z','2026-10-26T08:00:00Z','2026-10-26T09:00:00Z'
 ].map(t=>({epoch:Date.parse(t)}));
 s.validateDraft=s.validator(executed);
 s.candidates=[{id:'mid'}];s.maxMoves=1;
 const result=p.plan(s);
 assert.equal(result.ready,true);
 const now=result.routes.find(r=>r.kind==='now');
 assert.ok(now,'Monday 15:00 move should remain a marked scenario');
 assert.equal(now.weeks[0].used,4);
 assert.equal(now.weeks[0].usedIf15,1);
 assert.equal(now.weeks[0].quotaResetVerified,false);
 assert.ok(now.warnings.some(w=>w.includes('Разные варианты сброса')));
});
test('missing alternate quota evidence stays UNKNOWN, never displayed as zero',()=>{
 const s=chainScenario();
 const original=s.validateDraft;
 s.validateDraft=draft=>{
  const result=original(draft);
  delete result.alternateQuotaWeeks;
  return result;
 };
 const result=p.plan(s);
 assert.equal(result.ready,true);
 assert.equal(result.routes[0].weeks[0].usedIf15,null);
 assert.ok(result.disclaimer.includes('две доступные квоты'));
});
