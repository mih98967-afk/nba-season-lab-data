const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync(__dirname+'/index.html','utf8');
function embedded(id){const m=html.match(new RegExp(`<script[^>]*id="${id}"[^>]*>([\\s\\S]*?)<\\/script>`));return m?m[1]:'';}
const keys=new Map(),listeners={};const view={innerHTML:''};let plannerCalls=0,chainCalls=0,budgetCalls=0;
let testRoster=[];
const futureMoscowInput=()=>new Date(Date.now()+4*3600000).toISOString().slice(0,16);
const document={
 getElementById(id){if(id.startsWith('bootstrap-'))return {textContent:embedded(id)};
  if(id==='when'||id==='budget-when')return {value:futureMoscowInput()};
  if(id==='out')return {value:testRoster[0]||''};
  if(id==='budget-target')return {value:'invalid'};
  if(id==='budget-buy')return {value:'100'};
  if(id==='root')return view;
  if(id==='navigation')return {addEventListener(type,fn){listeners['nav:'+type]=fn;}};
  if(id==='source-status')return {textContent:''};
  return null;},
 querySelectorAll(){return []},querySelector(){return {remove(){}}},
 addEventListener(name,fn){(listeners[name]||(listeners[name]=[])).push(fn)}
};
const window={
 NBATransferGuard:require('./transfer_guard.js'),NBAScoreAudit:require('./score_audit.js'),
 NBATodayBrief:require('./today_brief.js'),NBAAdviceReadiness:require('./advice_readiness.js'),
 NBATeamCourtLayout:require('./team_court.js'),
 NBAMultiPlanner:{plan(){plannerCalls++;return {ready:false,reason:'unreachable mocked planner'};}},
 NBAChainPlanner:{rank(){chainCalls++;return {ready:false,reason:'unexpected chain run'};}},
 NBABudgetPackage:{solve(){budgetCalls++;return {ready:false,reason:'unexpected budget run'};}},
 scrollTo(){}
};
// A synthetic, independently controlled 1100-game calendar fixture lets
// the positive journal test freeze its *as-of* slate; no real site data used.
const baseFixture=JSON.parse(embedded('bootstrap-data'));
const clubsFixture=baseFixture.teams.map(x=>x.team);
const epochFixture=Date.parse('2026-10-20T19:00:00Z');
const gamesFixture=Array.from({length:1100},(_,i)=>{
 const epoch=epochFixture+i*4*3600000;
 return {id:'espn_'+(410000000+i),utc:new Date(epoch).toISOString().slice(0,19)+'Z',
  epoch,home:clubsFixture[i%clubsFixture.length],
  away:clubsFixture[(i+1)%clubsFixture.length],status:'scheduled'};
});
keys.set('nba-season-lab-verified-calendar-v1',JSON.stringify({schema_version:1,
 status:'verified_public_calendar_with_known_gaps',fantasy_timezone:'Europe/Moscow',
 updated_at_utc:new Date().toISOString(),games:gamesFixture,
 completeness:{teams:30,team_games_min:70,unassigned_or_unavailable_games:0}}));
const localStorage={getItem:k=>keys.get(k)||null,setItem:(k,v)=>keys.set(k,v),removeItem:k=>keys.delete(k)};
const ctx={window,document,localStorage,location:{protocol:'file:'},Date,Intl,Math,Number,String,Array,Map,Set,JSON,console,
 setTimeout:()=>{},setInterval:()=>{},clearTimeout:()=>{},fetch:()=>Promise.reject(Error('unexpected network'))};
vm.runInNewContext(fs.readFileSync(__dirname+'/app.js','utf8'),ctx,{timeout:10000,filename:'app.js'});
let roster=[],byClub={};
for(const pos of ['PG','SG','SF','PF','C']){
 let n=0;for(const p of window.PythosNBA.base.players.filter(p=>p.pos===pos)){
  if((byClub[p.team]||0)>=2)continue;
  roster.push(p.id);byClub[p.team]=(byClub[p.team]||0)+1;
  if(++n===2)break;
 }
}
assert.equal(roster.length,10);
testRoster=roster.slice();
let state=window.PythosNBA.getState();state.roster=roster;state.initialRoster=roster.slice();state.cash=100;
window.PythosNBA.setState(state);
assert.match(view.innerHTML,/Сначала обнови статистику NBA/);
assert.match(view.innerHTML,/Не подтверждена/);
assert.match(view.innerHTML,/Проверить полезность советов/);
assert.match(view.innerHTML,/Пока нет сохранённых прогнозов/);
assert.doesNotMatch(view.innerHTML,/data-action="today-freeze-best"/);
assert.doesNotMatch(view.innerHTML,/data-action="today-freeze-keep"/);

// Unchecked injection with a forged new timestamp must never qualify as a live source.
window.PythosNBA.updateFeed({mode:'live_sync',updated_at_utc:new Date().toISOString(),rows:[],games:[],schedule:[]});
assert.match(view.innerHTML,/Сначала обнови статистику NBA/);
assert.match(view.innerHTML,/Матчевая модель · 7 дней/);
assert.match(view.innerHTML,/н\/д — сначала подтвердить источники/);
const click=action=>listeners.click[0]({target:{closest:()=>({dataset:{action}})}});
// A forged click cannot cause a capture while public source is unverified.
click('today-freeze-best');
assert.equal(keys.has('nba-season-lab-local-decision-journal-v1'),false);
click('today-freeze-keep');
assert.equal(keys.has('nba-season-lab-local-decision-journal-v1'),false);
click('today-review');
assert.equal(plannerCalls,0,'No optimizer run using unvalidated or embedded source');
assert.match(view.innerHTML,/Рекомендации пока недоступны/);
assert.match(view.innerHTML,/data-action="calculate-multi" disabled/);
click('calculate-multi');
assert.equal(plannerCalls,0,'Disabled UI must also be guarded at the action handler');
// Secondary automated planners must share the same verified public-source gate.
click('calculate-chains');
assert.equal(chainCalls,0,'Chain planner must not use stale or unverified feed');
click('calculate-budget');
assert.equal(budgetCalls,0,'Budget planner must not use stale or unverified feed');
assert.match(view.innerHTML,/Рекомендации заблокированы/);
// The advanced chain control is not mounted in the default Advice view;
// its delegated action above is still required to reject unverified data.
assert.match(view.innerHTML,/Рекомендации заблокированы/);
assert.equal(window.PythosNBA.getState().roster.length,10);
// Ten entries without valid position structure cannot be silently treated as ready.
state=window.PythosNBA.getState();state.roster=[...roster.slice(0,9),roster[0]];
window.PythosNBA.setState(state);
listeners['nav:click']({target:{closest:()=>({dataset:{tab:'today'}})}});
assert.match(view.innerHTML,/Сначала проверь свой состав/);
assert.equal(plannerCalls,0);
// The planner must not display a fabricated exact weekly quota when the owner
// only knows the day of a historical move (not its real timestamp).
state=window.PythosNBA.getState();
state.roster=roster.slice();
state.executed=[{out:roster[0],in_:'n999',epoch:Date.now()-3600000,
 timePrecision:'date_only',epochIsPlaceholder:true,sell:1200,buy:1300}];
window.PythosNBA.setState(state);
listeners['nav:click']({target:{closest:()=>({dataset:{tab:'planner'}})}});
assert.match(view.innerHTML,/Замены по истории: <b>н\/д<\/b>/);
assert.match(view.innerHTML,/Недавние замены записаны только по датам/);
assert.doesNotMatch(view.innerHTML,/Замены по истории: <b>1\/3<\/b>/);
click('market-review-best');
assert.match(view.innerHTML,/Сценарий устарел или его данные изменились/);
console.log('PASS Today / Transfers VM: unvalidated feed, invalid roster, unknown quota and no stale market shortcut');

// PR167: positive owner-click flow, explicitly synthetic verified inputs.
// No live NBA feed is forged in production; the test stubs readiness only.
window.NBADecisionJournal=require('./decision_journal.js');
window.NBADecisionBreakdown={build:()=>({ready:true})};
window.NBAAdviceReadiness.inspect=()=>({ready:true,rosterReady:true,cashReady:true,
 feedReady:true,calendarReady:true,feedAgeHours:0,reasons:[]});
window.NBATodayBrief.build=()=>({state:'scenario',title:'Тест сравнения',
 description:'Локальный сценарий',hasResults:true,reasons:[],
 shortFP:null,longFP:null,games7:null,games21:null});
window.NBAMultiPlanner.plan=()=>{
 const start=Date.now()+20*60000;
 return {ready:true,start,end:start+7*86400000,horizonDays:7,baseline:200,
 routes:[
  {kind:'now',gain:15,net:11,moves:[{out:roster[0],in_:'n222',epoch:start,sell:1200,buy:1000}]},
  {kind:'keep',gain:0,net:0,moves:[]}
 ]};
};
ctx.confirm=()=>true;
// Controlled synthetic freshness, distinct from production's full signature guard.
window.NBATodayBrief.freshScenario=x=>x.result?.ready?x.result:null;
const scheduled=[];ctx.setTimeout=fn=>{scheduled.push(fn);return scheduled.length;};
state=window.PythosNBA.getState();state.roster=roster.slice();state.executed=[];
window.PythosNBA.setState(state);
listeners['nav:click']({target:{closest:()=>({dataset:{tab:'today'}})}});
assert(scheduled.length>0, 'today forecast was scheduled');
scheduled.shift()();
assert.match(view.innerHTML,/data-action="today-freeze-best"/);
assert.match(view.innerHTML,/data-action="today-freeze-keep"/);
assert.match(view.innerHTML,/Пока нет сохранённых прогнозов/);
const beforeCapture=window.PythosNBA.getState();
click('today-freeze-keep');
const savedJournal=window.NBADecisionJournal.read(localStorage);
assert.equal(savedJournal.entries.length,1);
assert.equal(savedJournal.entries[0].scenario.chosen_index,1);
assert.equal(savedJournal.entries[0].scenario.routes[1].kind,'keep');
assert.equal(savedJournal.entries[0].scenario.routes.length,2);
assert.equal(savedJournal.entries[0].no_sportsru_transfer_executed,true);
assert.equal(savedJournal.entries[0].outcome.real_transfer_benefit_proven,false);
assert.equal(savedJournal.entries[0].frozen_slate.status,'owner_clicked_model_schedule_unverified');
assert(savedJournal.entries[0].frozen_slate.games.length>0);
assert.equal(savedJournal.entries[0].frozen_slate.source_independently_verified,false);
assert.deepEqual(window.PythosNBA.getState(),beforeCapture);
assert.match(view.innerHTML,/Локально сохранено снимков: 1/);
assert.match(view.innerHTML,/Последний снимок: результаты ожидаются/);
assert.match(view.innerHTML,/Все решения · 1/);
assert.match(view.innerHTML,/Проверить начисления Sports.ru вручную/);
assert.match(view.innerHTML,/data-action="journal-credit-save"/);
assert.match(view.innerHTML,/data-action="journal-credit-export"/);
assert.match(view.innerHTML,/Период ещё не завершился/);

// PR175: previously saved game credits stay accessible after later captures;
// the selected frozen decision (not always the latest) owns the action.
const apiCredit=window.NBADecisionJournal;
const firstFrozen=savedJournal.entries[0];
const unknownCredits=e=>apiCredit.differentialEvidence(e).unique_sportsru_credit_requests
 .map(r=>({game_id:r.game_id,player_id:r.player_id,participation_status:'unknown',
  sportsru_credited_fp:null,source_ref:''}));
apiCredit.creditSave(localStorage,firstFrozen,unknownCredits(firstFrozen),true);
const secondMs=Date.parse(firstFrozen.captured_at_utc)+2*60000;
const secondStart=secondMs+2*60000,secondEnd=secondStart+7*86400000;
const firstStart=Date.parse(firstFrozen.decision_start_utc);
const secondInput={userConfirmedNow:true,roster:firstFrozen.owner_state.roster_ids,
 cash:firstFrozen.owner_state.cash_scenario,chosenIndex:0,
 liveUpdatedAtUtc:firstFrozen.observed_public_feed_updated_at_utc,
 plan:{ready:true,horizonDays:7,start:secondStart,end:secondEnd,
  baseline:firstFrozen.scenario.baseline_fp,
  routes:firstFrozen.scenario.routes.map(r=>({kind:r.kind,gain:r.gain_fp,net:r.net_fp,
   moves:r.moves.map(m=>({out:m.out,in_:m.in_,epoch:secondStart+
     (Date.parse(m.execution_utc)-firstStart),sell:m.assumed_sell,buy:m.assumed_buy}))}))},
 slate:{ownerClickedVerifiedCalendar:true,
  calendarUpdatedAtUtc:firstFrozen.frozen_slate.observed_calendar_updated_at_utc,
  playerTeams:firstFrozen.frozen_slate.player_teams_at_capture,existingDraft:[],
  games:firstFrozen.frozen_slate.games.map(g=>({id:g.id,epoch:Date.parse(g.tipoff_utc),
   home:g.home,away:g.away})).filter(g=>g.epoch>=secondStart&&g.epoch<secondEnd)}};
const secondFrozen=apiCredit._makeForTests(()=>secondMs).take(localStorage,secondInput);
apiCredit.creditSave(localStorage,secondFrozen,unknownCredits(secondFrozen),true);
window.NBA.view();
assert.match(view.innerHTML,/Выбрать сохранённое решение/);
assert.match(view.innerHTML,/Доступно 2 решений/);
assert.match(view.innerHTML,/Ручные FP относятся только к выбранному снимку/);
listeners.change[0]({target:{id:'credit-review-snapshot',dataset:{},
 value:firstFrozen.captured_at_utc}});
assert.match(view.innerHTML,/class="journal-credit-review" open/,
 'selected old decision remains expanded');
const preClear=JSON.stringify(apiCredit.read(localStorage));
click('journal-credit-clear');
assert.equal(apiCredit.creditFind(localStorage,firstFrozen),null,
 'clear applies to selected old decision');
assert(apiCredit.creditFind(localStorage,secondFrozen),
 'newer record must survive clearing older review');
assert.equal(JSON.stringify(apiCredit.read(localStorage)),preClear,
 'frozen journal is never rewritten by credit actions');
// The existing one-click economic export must now include the credit sidecar.
let privateExport=null;
ctx.Blob=class {constructor(parts){this.parts=parts;}};
ctx.URL={createObjectURL(blob){privateExport=JSON.parse(blob.parts[0]);return 'blob:test';},
 revokeObjectURL(){}};
document.body={appendChild(){}};
document.createElement=()=>({click(){},remove(){}});
window.NBASportsReconciliation={exportReconciliation:()=>({kind:'synthetic-owner-only'})};
window.NBAPriceEvidence={exportData:()=>({receipts:[]})};
click('today-evidence-export');
assert.equal(privateExport?.manual_sportsru_credit_reviews_unverified?.reviews.length,1);
assert.equal(privateExport.manual_sportsru_credit_reviews_unverified.reviews[0].captured_at_utc,
 secondFrozen.captured_at_utc);
assert.equal(privateExport.frozen_decision_journal.entries.length,2);
assert.equal(privateExport.no_sportsru_transfer_executed,true);
console.log('PASS PR175: older snapshot selectable, targeted delete, full private export includes manual FP');

assert.match(view.innerHTML,/Доказанных побед и поражений по очкам Sports.ru/);
assert.match(view.innerHTML,/нет данных/);
window.NBATodayBrief.freshScenario=()=>null;
click('today-freeze-best');
assert.equal(window.NBADecisionJournal.read(localStorage).entries.length,2);
console.log('PASS PR167: Today KEEP choice, all frozen alternatives, no Firestore/profile write, stale advice blocked');


// PR170: historical entries MUST NOT leak their placeholder epoch as an actual
// transfer hour in the user-facing executed-history view.
state=window.PythosNBA.getState();
state.executed=[{out:roster[0],in_:'n222',
 timePrecision:'date_only',epochIsPlaceholder:true,
 sportsRuDateMoscow:'2026-11-09',epoch:Date.parse('2026-11-09T12:34:00Z'),
 sell:1234,buy:1000}];
window.PythosNBA.setState(state);
listeners['nav:click']({target:{closest:()=>({dataset:{tab:'planner'}})}});
listeners.click[0]({target:{closest:()=>({dataset:{plannerTask:'record'}})}});
assert.match(view.innerHTML,/09\.11\.2026 · часы неизвестны/);
assert.doesNotMatch(view.innerHTML,/09\.11, 15:34/);
console.log('PASS PR170: date-only historical transfer never exposed as an actual clock');

// PR176: >80 independent player-games must be editable page by page without
// silently erasing already saved evidence on earlier or later pages.
const bigMs=Date.parse(secondFrozen.captured_at_utc)+120000;
const bigStart=bigMs+120000;
const bigTeams=Object.fromEntries(firstFrozen.owner_state.roster_ids.map(id=>[id,'AAA']));
bigTeams.n222='BBB';
const bigFrozen=apiCredit._makeForTests(()=>bigMs).take(localStorage,{
 userConfirmedNow:true,roster:firstFrozen.owner_state.roster_ids,
 cash:firstFrozen.owner_state.cash_scenario,chosenIndex:0,
 liveUpdatedAtUtc:new Date(bigMs-360000).toISOString(),
 plan:{ready:true,horizonDays:28,start:bigStart,end:bigStart+28*86400000,
  baseline:300,routes:[
   {kind:'now',gain:35,net:26,moves:[{out:roster[0],in_:'n222',epoch:bigStart,
    sell:1200,buy:1000}]},
   {kind:'keep',gain:0,net:0,moves:[]}
  ]},
 slate:{ownerClickedVerifiedCalendar:true,
  calendarUpdatedAtUtc:new Date(bigMs-360000).toISOString(),
  playerTeams:bigTeams,existingDraft:[],games:Array.from({length:120},(_,i)=>({
   id:'espn_'+(920000+i),epoch:bigStart+(i+1)*4*3600000,
   home:'AAA',away:'BBB'
  }))}
});
const bigNeeded=apiCredit.differentialEvidence(bigFrozen).unique_sportsru_credit_requests;
assert(bigNeeded.length>80);
listeners['nav:click']({target:{closest:()=>({dataset:{tab:'today'}})}});
listeners.change[0]({target:{id:'credit-review-snapshot',dataset:{},
 value:bigFrozen.captured_at_utc}});
assert.match(view.innerHTML,/journal-credit-page-next/);
assert.match(view.innerHTML,/32.*\u0438\u0437/);
assert.doesNotMatch(view.innerHTML,/data-action="journal-credit-save" disabled/);
const originalQuery=document.querySelector;
const mockCreditFields=new Map();
const setRow=(i,status,fp,source)=>{
 mockCreditFields.set(i,{status,fp,source});
};
setRow(0,'played','-2.5','Sports.ru source A');
document.querySelector=selector=>{
 const match=/^\[data-credit-(status|fp|source)="(\d+)"\]$/.exec(selector);
 if(match){const row=mockCreditFields.get(Number(match[2]));
  return {value:row?.[match[1]]??(match[1]==='status'?'unknown':'')};}
 return originalQuery(selector);
};
click('journal-credit-save');
let bigRecord=apiCredit.creditFind(localStorage,bigFrozen);
assert.equal(bigRecord.rows.length,bigNeeded.length);
assert.equal(bigRecord.rows[0].sportsru_credited_fp,-2.5);
assert.equal(bigRecord.rows[32].sportsru_credited_fp,null);
click('journal-credit-page-next');
assert.match(view.innerHTML,/\u0421\u0442\u0440\u0430\u043d\u0438\u0446\u0430 2/);
setRow(32,'official_dnp','0','Sports.ru source DNP');
click('journal-credit-save');
bigRecord=apiCredit.creditFind(localStorage,bigFrozen);
assert.equal(bigRecord.rows[0].sportsru_credited_fp,-2.5);
assert.equal(bigRecord.rows[32].sportsru_credited_fp,0);
assert.equal(bigRecord.rows[32].participation_status,'official_dnp');
// Reject a page change with unsaved values; do not erase or save them.
listeners.input[0]({target:{dataset:{creditFp:'32'}}});
ctx.confirm=()=>false;
click('journal-credit-page-next');
assert.match(view.innerHTML,/\u0421\u0442\u0440\u0430\u043d\u0438\u0446\u0430 2/);
ctx.confirm=()=>true;
click('journal-credit-page-prev');
assert.match(view.innerHTML,/\u0421\u0442\u0440\u0430\u043d\u0438\u0446\u0430 1/);
assert.match(view.innerHTML,/value="-2.5"/);
assert.equal(apiCredit.creditFind(localStorage,bigFrozen).rows[32].sportsru_credited_fp,0);
assert.equal(apiCredit.creditReview(bigFrozen,bigRecord,
 {nowMs:bigStart+29*86400000}).status,'CREDITS_INCOMPLETE');
click('today-evidence-export');
assert.equal(privateExport.manual_sportsru_credit_reviews_unverified.reviews.length,2);
assert.equal(privateExport.manual_sportsru_credit_reviews_unverified.reviews
 .find(x=>x.captured_at_utc===bigFrozen.captured_at_utc).rows.length,bigNeeded.length);
assert.equal(privateExport.frozen_decision_journal.entries.length,3);
assert.equal(privateExport.no_sportsru_transfer_executed,true);
console.log('PASS PR176: >80 credits paged safely, source+negative+DNP, unsaved guard, private export');
