const assert=require('node:assert/strict');
const {build}=require('./site/v6_16/decision_breakdown.js');
const a='a',b='b';
const players={};for(let i=0;i<10;i++)players['p'+i]={team:'a',forecast:true};
players.p9={team:'b',forecast:true};players.q={team:'b',forecast:true};
const roster=Array.from({length:10},(_,i)=>'p'+i);
const games=[{epoch:200,home:'a',away:'b',id:'g1'},{epoch:300,home:'a',away:'b',id:'g2'}];
const scores={p9:10,q:30};let gain=40;
const base={baseRoster:roster,start:0,end:500,lockOffsetMs:10,games,players,
  scorePlayer:(id)=>scores[id]||0,project:(moves)=>moves.length?60:20,
  route:{moves:[{out:'p9',in_:'q',epoch:100}],gain}};
const result=build(base);
assert.equal(result.ready,true,JSON.stringify(result));
assert.equal(result.gainFP,40);
assert.equal(result.gamesChanged,2);
assert.equal(result.expectedIncomingFP,60);
assert.equal(result.foregoneOutgoingFP,20);
assert.equal(build({...base,route:{...base.route,gain:41}}).code,'ROUTE_TOTAL_MISMATCH');
assert.equal(build({...base,players:{...players,q:{team:'b',forecast:false}}}).code,'MISSING_FORECAST');
assert.equal(build({...base,games:[...games,games[0]]}).code,'DUPLICATE_GAME');
assert.equal(build({...base,scorePlayer:()=>null}).code,'MISSING_GAME_FP');
assert.equal(build({...base,baseRoster:[...roster.slice(1),'p1']}).code,'INVALID_INPUT');
assert.equal(build({...base,project:()=>NaN}).code,'MISSING_PROJECTED_FP');
assert.equal(build({...base,route:{moves:[{out:'p9',in_:'q',epoch:400}],gain:0},
 project:()=>20}).ready,true);
console.log('v6.16 decision breakdown tests PASS');
