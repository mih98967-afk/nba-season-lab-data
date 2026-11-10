const assert = require('node:assert/strict');
const { build } = require('./today_brief.js');
const known = {rosterCount:10,rosterValid:true,feedVerified:true,feedAgeHours:4,feedMode:'live_sync',officialFeedReady:true,calendar7:true,calendar21:true,
 officialRiskNames:[],manualOutCount:0,telegramCount:0,fp7:179.3,fp21:515.9,games7:21,games21:69};
let a=build(known);assert.equal(a.state,'review');assert.equal(a.hasResults,false);assert.equal(a.shortFP,179.3);assert.equal(a.longFP,515.9);assert.equal(a.reasons.length,2);
a=build({...known,rosterCount:0});assert.equal(a.state,'onboarding');assert.equal(a.showForecast,false);
a=build({...known,feedMode:'seed'});assert.equal(a.state,'blocked');assert.equal(a.shortFP,null);
a=build({...known,feedAgeHours:28});assert.equal(a.state,'blocked');assert.equal(a.longFP,null);
a=build({...known,calendar21:false});assert.equal(a.state,'review');assert.equal(a.longFP,null);assert.equal(a.games21,null);assert.equal(a.shortFP,179.3);
a=build({...known,fp7:NaN,fp21:Infinity});assert.equal(a.shortFP,null);assert.equal(a.longFP,null);
a=build({...known,officialRiskNames:['Игрок А']});assert.equal(a.state,'risk');assert.match(a.reasons[0],/Игрок А/);
a=build({...known,manualOutCount:1});assert.equal(a.state,'risk');
a=build({...known,telegramCount:2});assert.equal(a.state,'review');assert.match(a.reasons[0],/неофициальных/);
a=build({...known,cashReady:false});assert.equal(a.state,'fix_roster');
a=build({...known,rosterValid:false});assert.equal(a.state,'fix_roster');assert.equal(a.hasResults,false);
a=build({...known,feedVerified:false,resultFresh:true,bestExplanationVerified:true,bestRoute:{kind:'now'}});assert.equal(a.state,'blocked');
a=build({...known,feedMode:'live',resultFresh:true,bestExplanationVerified:true,bestRoute:{kind:'now'}});assert.equal(a.state,'blocked');
a=build({...known,officialFeedReady:false});assert.match(a.reasons.join(' '),/Injury Reports/);
a=build({...known, resultFresh:true,bestExplanationVerified:true,bestRoute:{kind:'keep'}});assert.equal(a.state,'scenario');assert.equal(a.hasResults,true);assert.match(a.title,/сохранить/);
a=build({...known, resultFresh:true,bestExplanationVerified:false,bestRoute:{kind:'now'}});assert.equal(a.state,'review');
a=build({...known, resultFresh:true,bestExplanationVerified:true,bestRoute:{kind:'now'},officialRiskNames:['Игрок А']});assert.equal(a.state,'risk');
a=build({...known,feedAgeHours:-1,resultFresh:true,bestExplanationVerified:true,bestRoute:{kind:'now'}});assert.equal(a.state,'blocked');
console.log('PASS: user-first daily decision brief, risk and source gates');

a=build({...known,resultFresh:true,bestExplanationVerified:true,bestRoute:{kind:'now'},marketReady:false,marketReason:'Ручные цены отсутствуют.'});
assert.equal(a.state,'market');assert.match(a.title,/проверь Sports.ru/);assert.match(a.reasons[0],/цены/);
a=build({...known,resultFresh:true,bestExplanationVerified:true,bestRoute:{kind:'now'},marketReady:true});
assert.equal(a.state,'scenario');
a=build({...known,resultFresh:true,bestExplanationVerified:true,bestRoute:{kind:'later'},marketReady:false});
assert.equal(a.state,'scenario','LATER remains hypothetical and is not mislabeled an executable NOW move');
a=build({...known,calendar21:false,resultFresh:true,bestExplanationVerified:true,bestRoute:{kind:'keep'},resultDays:7});
assert.equal(a.state,'scenario','A valid 7-day KEEP stays actionable while NBA Cup 21-day is unknown');
assert.equal(a.longFP,null);assert.equal(a.shortFP,179.3);
a=build({...known,calendar7:false,calendar21:true,resultFresh:true,bestExplanationVerified:true,bestRoute:{kind:'now'}});
assert.equal(a.state,'blocked','Unknown 7-day data must never inherit a 21-day route');
// Price/real-quota evidence is independent from model scenario ranking.
(()=>{
const evidence=require('./decision_evidence.js');
const receipts=require('./price_evidence.js');
const {weekKey}=require('./transfer_guard.js');
const NOW=Date.parse('2026-11-10T12:00:00Z');
const storage=()=>{const map=new Map();return {getItem:k=>map.has(k)?map.get(k):null,setItem:(k,v)=>map.set(k,v),removeItem:k=>map.delete(k)};};
const move=(out='n101',in_='n222',when=NOW+10*60000)=>({out,in_,epoch:when,sell:1300,buy:1400});
const run=(route,archive=null,opts={})=>evidence.marketReadiness({route,priceArchive:archive,nowEpoch:NOW,cash:500,draftCount:0,weekKey,...opts});
const pair=(at,loc,which,opts={})=>receipts._makeForTests(()=>at).capture(loc,{
 outId:which.out,inId:which.in_,confirmedSellPrice:which.sell,confirmedBuyPrice:which.buy,
 confirmedCash:opts.cash===undefined?500:opts.cash,confirmedQuota:opts.quota===undefined?2:opts.quota,
 userConfirmedNow:true
});
assert.equal(run({moves:[]}).status,'keep');
assert.equal(run({moves:[move()]}).ready,false);
assert.match(run({moves:[move()]}).reasons.join(' '),/журнала/);
const loc=storage();pair(NOW-12*60000,loc,move());
let archive=receipts.read(loc),route={moves:[move()]},r=run(route,archive);
assert.equal(r.ready,true,JSON.stringify(r));
assert.equal(r.status,'owner_checked_now');
assert.equal(r.remainingOwner,2);
assert.equal(r.independentlyVerified,false);
assert.equal(r.allowAutoTransfer,false);
assert.equal(run({moves:[{...move(),buy:1401}]},archive).ready,false);
assert.equal(run({moves:[move('n101','n223')]},archive).ready,false);
assert.equal(run(route,archive,{cash:499}).ready,false);
assert.equal(run(route,archive,{draftCount:1}).ready,false);
assert.equal(run({moves:[move('n101','n222',NOW+2*3600000)]},archive).status,'future_scenario');
assert.equal(run({moves:[move('n101','n222',NOW-2*60000)]},archive).status,'future_scenario');
const noCash=storage();pair(NOW-5*60000,noCash,move(),{cash:''});
assert.equal(run(route,receipts.read(noCash)).ready,false);
const noQuota=storage();pair(NOW-5*60000,noQuota,move(),{quota:''});
assert.equal(run(route,receipts.read(noQuota)).ready,false);
const zeroQuota=storage();pair(NOW-5*60000,zeroQuota,move(),{quota:0});
assert.equal(run(route,receipts.read(zeroQuota)).ready,false);
const stale=storage();pair(NOW-61*60000,stale,move());
assert.equal(run(route,receipts.read(stale)).ready,false);
const restored={...archive,restored_from_file_unverified:true};
assert.equal(run(route,restored).ready,false);
const loc2=storage();pair(NOW-8*60000,loc2,move());
pair(NOW-5*60000,loc2,move('n102','n223'));
assert.equal(run({moves:[move(),move('n102','n223',NOW+15*60000)]},receipts.read(loc2)).ready,true);
assert.equal(run({moves:[move(),move('n102','n223',NOW+15*60000),move('n103','n224',NOW+18*60000)]},receipts.read(loc2)).ready,false);
const MON=Date.parse('2026-11-09T11:50:00Z');
const monday=storage();pair(MON-60000,monday,move('n101','n222',MON+20*60000));
assert.equal(evidence.marketReadiness({route:{moves:[move('n101','n222',MON+20*60000)]},priceArchive:receipts.read(monday),nowEpoch:MON,cash:500,draftCount:0,weekKey}).ready,false);
const frozen=JSON.stringify(archive);run(route,archive);assert.equal(JSON.stringify(archive),frozen);
console.log('PASS market readiness: real vs modelled prices, local cash/quota, clock, week boundary, no mutation');
})();

// NBA official OUT is attached to the EXACT known fixture and verified point-in-time report.
(()=>{
const official=require('./official_status.js');
const at=Date.parse('2026-11-10T15:00:00Z');
const tip=Date.parse('2026-11-11T00:30:00Z');
const p={id:'n1',name:'Игрок теста',team:'NYK',pos:'PG'};
const game={id:'espn_401909960',home:'NYK',away:'MIL',epoch:tip};
const event={player_id:p.id,team:p.team,home:'NYK',away:'MIL',game_id:game.id,
 tipoff_utc:new Date(tip).toISOString(),report_at_utc:'2026-11-10T12:45:00Z',
 first_seen_at_utc:'2026-11-10T12:58:59Z',status:'out',
 source_url:'https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-11-10_07_45AM.pdf'};
const feed={schema_version:1,status:'research_only_not_deployed',updated_at_utc:'2026-11-10T13:04:20Z',events:[event]};
assert.equal(official.forGame(feed,p,game,{n1:p},at)?.status,'out');
assert.equal(official.forGame(feed,p,{...game,id:'espn_401909961'},{n1:p},at),null);
assert.equal(official.forGame(feed,p,{...game,away:'BOS'},{n1:p},at),null);
assert.equal(official.forGame(feed,{...p,team:'MIL'},game,{n1:{...p,team:'MIL'}},at),null);
assert.equal(official.forGame(feed,p,game,{n1:p},at-3*3600000),null,'Future information must not leak backwards');
assert.equal(official.forGame(feed,p,game,{n1:p},at+13*3600000),null,'Expired/in-play report is not an actionable fresh OUT');
const q={...feed,events:[{...event,status:'questionable'}]};
assert.equal(official.forGame(q,p,game,{n1:p},at)?.status,'questionable');
const bad={...feed,events:[{...event,first_seen_at_utc:'2026-11-11T00:01:00Z'}]};
assert.equal(official.forGame(bad,p,game,{n1:p},Date.parse('2026-11-11T00:05:00Z')),null,'After-lock evidence must not reassign prelock risk');
})();
// Seven-day bounded search must have an explicit calendar horizon contract.
(()=>{
const planner=require('./multi_planner.js');
const names=['PG','SG','SF','PF','C'];const roster=[],players={};
for(const pos of names)for(let i=0;i<2;i++){
 const id=pos+i;roster.push(id);players[id]={id,pos,team:pos+i,forecast:true,mean_if_play:15};
}
const t=Date.parse('2026-11-10T18:00:00Z');
const draftCheck=()=>({valid:true,roster:roster.slice(),cash:500,used:{},alternateQuotaWeeks:{},warnings:[]});
const project=(_moves,a,b)=>(b-a)/86400000*100;
const res=planner.plan({roster,players,candidates:Object.values(players),nowEpoch:t-1200000,
 whenEpoch:t,horizonDays:7,maxMoves:2,priceOf:()=>100,validateDraft:draftCheck,
 coverage:()=>({ok:true,reason:'seven days complete'}),scorePlayer:(_id,a,b)=>(b-a)/86400000*10,project});
assert.equal(res.ready,true,JSON.stringify(res));
assert.equal(res.horizonDays,7);assert.equal(res.routes[0].kind,'keep');
})();
