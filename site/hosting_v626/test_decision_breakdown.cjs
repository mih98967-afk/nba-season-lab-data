const {test}=require('node:test');
const assert=require('node:assert/strict');
const {build}=require('./decision_breakdown.js');
const H=3600000, D=24*H;
const start=Date.parse('2026-11-03T00:00:00Z');
const g=(day,home='AAA',away='BBB')=>({id:'g'+day,epoch:start+day*D,home,away,status:'scheduled'});
const roster=['p0',...Array.from({length:9},(_,i)=>'f'+i)];
const players={p0:{team:'AAA',forecast:true},p1:{team:'AAA',forecast:true},p2:{team:'AAA',forecast:true}};
for(let i=0;i<9;i++)players['f'+i]={team:'CCC',forecast:true};
const games=[g(1),g(5),g(8),g(11)];
const value=(id,epoch)=>id==='p0'?10:id==='p1'?epoch<start+8*D?30:0:id==='p2'?epoch<start+8*D?0:40:0;
const score=(id,a,b)=>games.filter(x=>x.epoch>=a&&x.epoch<b&&(x.home===players[id]?.team||x.away===players[id]?.team)).reduce((s,x)=>s+value(id,x.epoch),0);
function project(moves,a,b){let total=0;for(const game of games){if(game.epoch<a||game.epoch>=b)continue;
 const own=roster.slice();for(const move of [...moves].sort((x,y)=>x.epoch-y.epoch)){if(move.epoch<=game.epoch-1800000){const idx=own.indexOf(move.out);if(idx<0)throw Error('bad move');own[idx]=move.in_;}}
 for(const id of own)total+=score(id,game.epoch,game.epoch+1);}
 return total;}
const M1={out:'p0',in_:'p1',epoch:start+H},M2={out:'p1',in_:'p2',epoch:start+7*D+H};
const fixture=(route={moves:[M1,M2],gain:100,net:92})=>({baseRoster:roster,existingDraft:[],route,start,end:start+14*D,games,players,scorePlayer:score,project,opportunityPenalty:4,baselineFP:40});
test('chain reconciles source players and every actual scheduled game; no early target gain',()=>{
 const r=build(fixture());assert.equal(r.ready,true);assert.equal(r.gainFP,100);assert.equal(r.baselineFP,40);assert.equal(r.plannedFP,140);assert.equal(r.expectedIncomingFP,140);assert.equal(r.foregoneOutgoingFP,40);
 assert.deepEqual(r.changedGames.map(x=>x.deltaFP),[20,20,30,30]);
 assert.deepEqual(r.playersIn.map(x=>x.id),['p2','p1']);assert.equal(r.playersIn.find(x=>x.id==='p2').intoGames,2);
 assert.equal(r.playersOut.find(x=>x.id==='p0').outGames,4);
});
test('KEEP returns zero with no manufactured explanation',()=>{const r=build(fixture({moves:[],gain:0,net:0}));assert.equal(r.ready,true);assert.equal(r.gainFP,0);assert.equal(r.gamesChanged,0);});
test('Monday lock uses 30 minute cutoff and excludes a late buy',()=>{const m={out:'p0',in_:'p1',epoch:games[0].epoch-10*60000};const x=fixture({moves:[m],gain:0,net:-4});
 assert.equal(build(x).ready,true);assert.deepEqual(build(x).changedGames.map(y=>y.epoch),[games[1].epoch,games[2].epoch,games[3].epoch]);
});
test('route different from project is blocked',()=>{const x=fixture();x.route={...x.route,gain:200};assert.equal(build(x).code,'ROUTE_TOTAL_MISMATCH');});
test('different event-level prediction is blocked even when route total agrees',()=>{const x=fixture();x.scorePlayer=()=>0;assert.equal(build(x).code,'GAME_SUM_MISMATCH');});
test('missing forecast cannot silently become zero',()=>{const x=fixture();x.players={...players,p1:{...players.p1,forecast:false}};assert.equal(build(x).code,'MISSING_FORECAST');});
test('missing scorer value cannot become zero',()=>{const x=fixture();x.scorePlayer=(id,a,b)=>id==='p1'?NaN:score(id,a,b);assert.equal(build(x).code,'MISSING_GAME_FP');});
test('missing baseline blocks explanation',()=>{const x=fixture();x.project=()=>NaN;assert.equal(build(x).code,'MISSING_PROJECTED_FP');});
test('tampered net (implicit penalty) blocks output',()=>{const x=fixture();x.route.net=100;assert.equal(build(x).code,'NET_MISMATCH');});
test('duplicate schedule game blocked; never count twice',()=>{const x=fixture();x.games=[...games,{...games[0],id:'other'}];assert.equal(build(x).code,'DUPLICATE_GAME');});
test('cannot explain unowned or duplicate transfer',()=>{const x=fixture({moves:[{out:'ghost',in_:'p2',epoch:start+H}],gain:100,net:96});assert.equal(build(x).code,'INVALID_ROSTER_TRANSITION');});
test('existing draft in KEEP path is not double counted',()=>{const x=fixture({moves:[],gain:0,net:0});x.existingDraft=[M1];x.baselineFP=60;assert.equal(build(x).ready,true);});
test('zero-game horizon permits genuine zero explanation',()=>{const x=fixture({moves:[],gain:0,net:0});x.games=[];x.project=()=>0;x.baselineFP=0;const r=build(x);assert.equal(r.ready,true);assert.equal(r.gamesConsidered,0);});
test('reject null gain, missing team and nonsense inputs',()=>{let x=fixture();x.route.gain=null;assert.equal(build(x).code,'INVALID_ROUTE');x=fixture();x.players={...players,p1:{forecast:true}};assert.equal(build(x).code,'MISSING_PLAYER');x=fixture();x.baseRoster=['p0','p0',...roster.slice(2)];assert.equal(build(x).code,'INVALID_INPUT');});
