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

// An unverified Monday clock must not make a multi-step transfer actionable.
{
 const x={rosterCount:10,rosterValid:true,cashReady:true,feedVerified:true,feedAgeHours:2,feedMode:'live_sync',calendar7:true,calendar21:true,officialFeedReady:true,
  resultFresh:true,bestExplanationVerified:true,bestRoute:{kind:'multi_slot',moves:[{out:'p1',in_:'p2'}]},resultDays:7,marketReady:false,historicalQuotaTimesUnverified:true,marketReason:'Сверь квоту Sports.ru',fp7:15,fp21:30,games7:4,games21:12};
 const out=build(x);
 assert.equal(out.state,'market');
 assert.match(out.reasons.join(' '),/Сверь квоту/);
}

// PR166 — pure regressions for full-calendar lock, placeholder quota, and stale reuse.
(()=>{
 const G=require('./today_brief.js');
 const t=Date.parse('2026-11-15T17:00:00Z');
 const w15=x=>x<Date.parse('2026-11-16T12:00:00Z')?'old':'new';
 const w00=x=>x<Date.parse('2026-11-15T21:00:00Z')?'old':'new';
 const u=G.quotaSnapshot([{epoch:t-60000,timePrecision:'date_only',epochIsPlaceholder:true}],t,w15,w00);
 assert.equal(u.known,false);assert.equal(u.used15,null);
 assert.equal(G.quotaSnapshot([{epoch:t-60000}],t,w15,w00).used15,1);
 const roster={a:{team:'A'},b:{team:'B'}};
 const games=[...Array.from({length:4},(_,i)=>({id:String(i),epoch:t+(i+2)*60000,home:'A',away:'Z',status:'scheduled'})),
 {id:'later',epoch:t+3600000,home:'B',away:'Z',status:'scheduled'}];
 const next=G.nextRosterLock(games,['a','b'],roster,t);
 assert.equal(next.gameId,'later');assert.deepEqual(next.playerIds,['b']);
 const result={ready:true,signature:'team-v1',start:t+20*60000,horizonDays:7,routes:[{kind:'now',moves:[{epoch:t+20*60000}]}]};
 const opts={result,calculatedAt:t,nowMs:t,signature:'team-v1',horizonDays:7,preflightReady:true};
 assert(G.freshScenario(opts));
 assert.equal(G.freshScenario({...opts,signature:'modified'}),null);
 assert.equal(G.freshScenario({...opts,nowMs:t+31*60000}),null);
 assert.equal(G.freshScenario({...opts,preflightReady:false}),null);
 assert.equal(G.freshScenario({...opts,result:{...result,start:t-3600000}}),null);
 console.log('PASS PR166: precise quota, full-calendar next lock, frozen-asof guard');
})();



// PR170: Date-only owner history is an INTERVAL in Moscow local time,
// never a real clock pulled from the backfilled placeholder epoch.
(()=>{
 const {quotaSnapshot}=require('./today_brief.js');
 const week=require('./transfer_guard.js').weekKey;
 const w15=t=>week(t,15),w00=t=>week(t,0);
 const at=d=>Date.parse(d);
 const dated=(day,placeholder=0)=>({timePrecision:'date_only',epochIsPlaceholder:true,
   sportsRuDateMoscow:day,epoch:placeholder});
 const nov9=dated('2026-11-09',at('2026-11-09T00:01:00Z'));
 let q=quotaSnapshot([nov9],at('2026-11-15T15:00:00Z'),w15,w00);
 assert.equal(q.known,false,'Monday owner transfer straddled a reset while still in the current Monday-15 week');
 assert.match(q.reason,/границ/);
 q=quotaSnapshot([nov9],at('2026-11-16T11:00:00Z'),w15,w00);
 assert.equal(q.known,false,'Until Monday 15 MSK, Nov 9 still overlaps the current week');
 q=quotaSnapshot([nov9],at('2026-11-16T13:00:00Z'),w15,w00);
 assert.equal(q.known,true,'After Monday 15 MSK the whole old date is clearly outside both current weeks');
 assert.equal(q.used15,0);assert.equal(q.used00,0);
 const exactSun=dated('2026-11-15',at('2026-09-02T01:00:00Z'));
 q=quotaSnapshot([exactSun],at('2026-11-15T18:00:00Z'),w15,w00);
 assert.equal(q.known,true);
 assert.equal(q.used15,1);assert.equal(q.used00,1);
 assert.equal(q.date_only_assigned_without_hour,1);
 const recentTue=dated('2026-11-17',at('2026-11-01T01:01:00Z'));
 q=quotaSnapshot([nov9,recentTue],at('2026-11-17T10:00:00Z'),w15,w00);
 assert.equal(q.known,true);assert.equal(q.used15,1);assert.equal(q.used00,1);
 q=quotaSnapshot([dated('2026-11-16')],at('2026-11-16T14:00:00Z'),w15,w00);
 assert.equal(q.known,false,'Monday date spans the 15:00 reset by the current clock');
 q=quotaSnapshot([dated('2026-11-16')],at('2026-11-16T10:00:00Z'),w15,w00);
 assert.equal(q.known,true,'Before Monday 15:00, same-day history is bounded by now');
 assert.equal(q.used15,1);assert.equal(q.used00,1);
 q=quotaSnapshot([dated('2026-11-09')],at('2026-11-17T12:00:00Z'),w15,w00);
 assert.equal(q.known,true);
 q=quotaSnapshot([{epoch:at('2026-11-09T10:00:00Z'),timePrecision:'date_only',epochIsPlaceholder:true}],at('2026-11-17T12:00:00Z'),w15,w00);
 assert.equal(q.known,false,'Without a known date the backfilled epoch is NEVER enough to infer quota');
 q=quotaSnapshot([dated('2026-02-30')],at('2026-11-17T12:00:00Z'),w15,w00);
 assert.equal(q.known,false,'Impossible calendar date rejected');
 q=quotaSnapshot([dated('2026-11-19')],at('2026-11-17T12:00:00Z'),w15,w00);
 assert.equal(q.known,false,'Owner history in future rejected');
 // Full synthetic copy of the historical day-only owner dates: by November 17
 // all entries must be outside the new week, regardless of placeholder epoch.
 const ownerDates=['2026-10-26','2026-10-26','2026-10-27','2026-10-28','2026-10-29',
                   '2026-11-03','2026-11-03','2026-11-09','2026-11-09','2026-11-09'];
 q=quotaSnapshot(ownerDates.map(d=>dated(d)),at('2026-11-17T14:00:00Z'),w15,w00);
 assert.equal(q.known,true);assert.equal(q.used15,0);assert.equal(q.used00,0);
 assert.equal(q.independentSportsruVerification,false);
 console.log('PASS PR170: date-only week intervals, two reset clocks, never trusted placeholder timestamps');
})();
