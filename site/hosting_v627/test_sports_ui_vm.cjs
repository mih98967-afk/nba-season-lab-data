const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=__dirname;
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
function embedded(id){const rx=new RegExp(`<script[^>]*id="${id}"[^>]*>([\\s\\S]*?)<\\/script>`);const x=html.match(rx);return x?x[1]:'';}
const nodes={};
const view={innerHTML:''};
const handlers={};
const saved=new Map();
const document={
 getElementById(id){if(['bootstrap-data','bootstrap-live','bootstrap-history','bootstrap-telegram','bootstrap-model'].includes(id))return {textContent:embedded(id)};
  if(id==='root')return view;
  if(id==='navigation')return {addEventListener(name,fn){handlers['nav:'+name]=fn}};
  if(id==='source-status')return {textContent:''};
  if(id==='sports-check')return {scrollIntoView(){}};
  return nodes[id]||null;},
 addEventListener(name,fn){(handlers[name]||(handlers[name]=[])).push(fn)},
 querySelector(){return {remove(){}}},querySelectorAll(){return []}
};
const localStorage={getItem:k=>saved.get(k)||null,setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)};
const window={NBATransferGuard:require('./transfer_guard.js'),NBAScoreAudit:require('./score_audit.js'),
 NBASportsReconciliation:require('./sports_reconciliation.js'),NBATeamCourtLayout:require('./team_court.js'),NBAOfficialStatus:require('./official_status.js'),NBATodayBrief:require('./today_brief.js'),NBAAdviceReadiness:require('./advice_readiness.js'),scrollTo(){}};
const ctx={window,document,localStorage,location:{protocol:'file:'},Date,Intl,Math,Number,String,Array,Map,Set,JSON,
 console,setTimeout:()=>{},setInterval:()=>{},clearTimeout:()=>{},fetch:()=>Promise.reject(Error('Unexpected external fetch'))};
vm.runInNewContext(fs.readFileSync(path.join(root,'app.js'),'utf8'),ctx,{timeout:10000,filename:'app.js'});
assert.match(view.innerHTML,/Нужна ли замена сегодня/);
let roster=[],teams={};const positions={};
for(const pos of ['PG','SG','SF','PF','C']){
 for(const p of window.PythosNBA.base.players.filter(x=>x.pos===pos)){
  if((positions[pos]||0)>=2)break;
  if((teams[p.team]||0)>=2)continue;
  roster.push(p.id);positions[pos]=(positions[pos]||0)+1;teams[p.team]=(teams[p.team]||0)+1;
 }
}
assert.equal(roster.length,10);
let s=window.PythosNBA.getState();s.roster=roster;s.initialRoster=roster.slice();s.initialEpoch=Date.parse('2026-10-20T00:00:00Z');s.cash=100;s.executed=[];s.draft=[];
window.PythosNBA.setState(s);
assert.match(view.innerHTML,/Нужна ли замена сегодня/);
handlers['nav:click']({target:{closest:()=>({dataset:{tab:'overview'}})}});
assert.match(view.innerHTML,/Сверить со Sports.ru/);
assert.match(view.innerHTML,/Замены/);
const before=window.PythosNBA.getState();
const click=action=>handlers.click[0]({target:{closest:()=>({dataset:{action}})}});
click('sports-check-toggle');
assert.match(view.innerHTML,/id="sports-fp"/);
for(const [id,value] of [['sports-fp','686'],['sports-cash','99'],['sports-remaining','3']])nodes[id]={value};
nodes['sports-confirm']={checked:true};
click('sports-check-run');
assert.match(view.innerHTML,/Результат сверки/);
assert.match(view.innerHTML,/686/);
assert.match(view.innerHTML,/Сверить со Sports.ru/);
assert.deepEqual(window.PythosNBA.getState(),before);
assert.equal(saved.size,1);
assert(!JSON.stringify(window.PythosNBA.getState()).includes('sportsResult'));
// Owner-attested historical scores are browser-local and explicitly date-labelled.
assert.match(view.innerHTML,/Официальные FP · контрольные даты/);
for(const [id,value] of [['checkpoint-day','2026-11-11'],['checkpoint-fp','2362'],
 ['checkpoint-roster','22330'],['checkpoint-cash','31']])nodes[id]={value};
nodes['checkpoint-confirm']={checked:true};
click('owner-checkpoint-save');
assert.match(view.innerHTML,/Sports.ru · ваша запись/);
assert.match(view.innerHTML,/2.{0,2}362 FP/);
assert.match(view.innerHTML,/На 2026-11-11 МСК/);
assert.match(view.innerHTML,/Sports.ru минус расчёт на эту дату: 1 FP/);
assert.equal(saved.has(window.NBASportsReconciliation.CHECKPOINT_KEY),true);
assert.deepEqual(window.PythosNBA.getState(),before);
assert.match(view.innerHTML,/Почему личные FP пока нельзя проверить автоматически/);
assert.match(view.innerHTML,/Нет независимого поматчевого источника/);
// Paired owner-entered dates: delta arithmetic never becomes official NBA/Sports.ru evidence.
for(const [id,value] of [['checkpoint-day','2026-11-12'],['checkpoint-fp','2504'],
 ['checkpoint-roster','22472'],['checkpoint-cash','31']])nodes[id]={value};
click('owner-checkpoint-save');
assert.match(view.innerHTML,/2026-11-11 → 2026-11-12/);
assert.match(view.innerHTML,/Sports.ru: \+142 FP/);
assert.match(view.innerHTML,/разница изменений: 0 ед/);
assert.deepEqual(window.PythosNBA.getState(),before);
// A browser-injected unverified NBA source cannot appear as a verified historical total.
window.PythosNBA.updateFeed({updated_at_utc:'2026-11-09T18:00:00Z',mode:'live_sync',
 games:[{id:'g1',status:'final',epoch:Date.parse('2026-11-01T23:00:00Z'),et_date:'2026-11-01',home:'BOS',away:'NYK'}],
 rows:[{id:roster[0],game_id:'g1',played:true,fp:10}],schedule:[]});
assert.match(view.innerHTML,/Сумма NBA FP не подтверждена/);
// Read-only official OUT overrides even the all-play scenario for its exact game only.
const pp=window.PythosNBA;
const active=roster[0],player=pp.base.players.find(p=>p.id===active);
const tip=Date.now()+3*3600000,fixture={id:'espn_401909960',epoch:tip,home:player.team,away:player.team==='MIL'?'BOS':'MIL'};
assert(pp.pPlay(active,fixture)>0);
const feed={schema_version:1,status:'research_only_not_deployed',updated_at_utc:new Date().toISOString(),events:[{
 player_id:active,team:player.team,home:fixture.home,away:fixture.away,game_id:fixture.id,
 tipoff_utc:new Date(tip).toISOString(),report_at_utc:new Date(Date.now()-30*60000).toISOString(),
 first_seen_at_utc:new Date(Date.now()-20*60000).toISOString(),status:'out',
 source_url:'https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-11-10_07_45AM.pdf'
}]};
window.NBA.setOfficial(feed);
assert.equal(pp.pPlay(active,fixture),0);
assert(pp.pPlay(active,{...fixture,id:'espn_other'})>0,'A report cannot zero a different game');
let alt=pp.getState();alt.riskMode='allplay';pp.setState(alt);
assert.equal(pp.pPlay(active,fixture),0,'Even all-play may not override an official exact-game OUT');
console.log('VM PASS: user-facing render, event wiring, private input, no state changes');

// Regression: do not use browser-global alert as a player-news flag.
ctx.alert=()=>{};
window.NBA.setTelegram({events:[]});
handlers['nav:click']({target:{closest:()=>({dataset:{tab:'overview'}})}});
handlers.click[0]({target:{closest:()=>({dataset:{teamView:'list'}})}});
const newsPill=/>Новость</g;
const pillCount=()=> (view.innerHTML.match(newsPill)||[]).length;
assert.equal(pillCount(),0,'No player-specific Telegram item means no News badges');
window.NBA.setTelegram({events:[{player_ids:[roster[0]],published_at:new Date().toISOString()}]});
assert.equal(pillCount(),1,'News about one player gives only one badge');
window.NBA.setTelegram({events:[]});
assert.equal(pillCount(),0,'News badge disappears when events are removed');
assert(!view.innerHTML.includes('не изменяет FP автоматически'), 'Old official OUT tooltip is misleading');
console.log('VM PASS: roster badges are player-specific');

// PR165: one-click economic packet joins independent PRIVATE local journals.
// The ordinary FP export stays unchanged, no cloud write, and no hypothetical
// quote may be presented as a verified executable transfer.
const capturedPackets=[];
ctx.Blob=class { constructor(parts){this.text=parts.join('');} };
ctx.URL={createObjectURL(blob){capturedPackets.push({data:JSON.parse(blob.text)});return 'blob:local-test';},revokeObjectURL(){}};
document.createElement=()=>({href:'',download:'',click(){capturedPackets.at(-1).name=this.download;},remove(){}});
document.body={appendChild(){}};
ctx.confirm=()=>true;
const priceApi=require('./price_evidence.js')._makeForTests(()=>Date.parse('2026-11-14T10:00:00Z'));
const journalApi=require('./decision_journal.js')._makeForTests(()=>Date.parse('2026-11-14T10:05:00Z'));
window.NBAPriceEvidence=priceApi;
window.NBADecisionJournal=journalApi;
const mockRecon=window.NBASportsReconciliation;
window.NBASportsReconciliation={...mockRecon,exportReconciliation(){return {kind:'PRIVATE_FP_TEST',notAnOfficialScore:true};}};
const priorState=window.PythosNBA.getState();
const beforeStore=Array.from(saved.entries());
priceApi.capture(localStorage,{outId:roster[0],inId:'n222',confirmedSellPrice:'1345',confirmedBuyPrice:'1200',confirmedCash:'100',confirmedQuota:'2',userConfirmedNow:true});
const decTs=Date.parse('2026-11-14T10:05:00Z');
journalApi.take(localStorage,{userConfirmedNow:true,roster,cash:100,liveUpdatedAtUtc:'2026-11-14T09:30:00Z',chosenIndex:1,
 plan:{ready:true,horizonDays:7,start:decTs+60000,end:decTs+7*86400000+60000,baseline:520,routes:[
  {kind:'keep',gain:0,net:0,moves:[]},
  {kind:'now',gain:12,net:8,moves:[{out:roster[0],in_:'n222',epoch:decTs+60000,sell:1345,buy:1200}]}
 ]}});
click('owner-economics-export');
assert.equal(capturedPackets.length,1);
assert.equal(capturedPackets[0].name,'nba-season-lab-private-economic-evidence.json');
const pack=capturedPackets[0].data;
assert.equal(pack.kind,'NBA_SEASON_LAB_PRIVATE_ECONOMIC_EVALUATION_PACKET');
assert.equal(pack.personal_fp_reconciliation.kind,'PRIVATE_FP_TEST');
assert.equal(pack.frozen_decision_journal.entries.length,1);
assert.equal(pack.manual_price_evidence.receipts.length,1);
assert.equal(pack.prospective_price_coverage_descriptive_only[0].owner_price_match_count,1);
assert.equal(pack.prospective_price_coverage_descriptive_only[0].price_pairs[0].quote_is_independently_verified,false);
assert.equal(pack.prospective_price_coverage_descriptive_only[0].executable_transfer_plan_proven,false);
assert.equal(pack.no_cloud_upload,true);
assert.equal(pack.postdecision_public_nba_observations_only.status,'public_NBA_only_unverified_Sportsru_credits');
assert.equal(pack.postdecision_public_nba_observations_only.actual_sportsru_credited_fp_available,false);
assert.equal(pack.frozen_outcome_coverage_descriptive_only.length,1);
assert.equal(pack.frozen_outcome_coverage_descriptive_only[0].actual_gain_fp,null);
assert.deepEqual(window.PythosNBA.getState(),priorState,'Export must not mutate team or Firestore-backed state');
assert.equal(saved.size,beforeStore.length+2,'Only explicit journal and price writes occurred');
// Corrupt local evidence must fail closed instead of silently exporting an incomplete packet.
saved.set(journalApi.KEY,'{invalid json');
click('owner-economics-export');
assert.equal(capturedPackets.length,1);
console.log('VM PASS: private economic packet, pricing-as-of, no execution, fail-closed corrupt input');


// v6.25: market navigation and custom filters must never change owner state.
// Public model/calendar are intentionally not injected: absent data stays n/d.
const ownerBeforeMarket=JSON.stringify(window.PythosNBA.getState());
handlers['nav:click']({target:{closest:()=>({dataset:{tab:'players'}})}});
assert.match(view.innerHTML,/market-period/);
assert.match(view.innerHTML,/market-week-0/);
assert.match(view.innerHTML,/market-week-1/);
assert.match(view.innerHTML,/market-week-2/);
handlers.change[0]({target:{dataset:{},classList:{contains:()=>false},id:'market-period',value:'days'}});
assert.match(view.innerHTML,/market-days/);
handlers.change[0]({target:{dataset:{},classList:{contains:()=>false},id:'market-days',value:'21'}});
assert.match(view.innerHTML,/Н1/);
handlers.change[0]({target:{dataset:{},classList:{contains:()=>false},id:'market-week-0',value:'min:3'}});
assert.match(view.innerHTML,/Показано 0 из 0/,'unknown schedule cannot be treated as three confirmed fixtures');
handlers.change[0]({target:{dataset:{},classList:{contains:()=>false},id:'market-week-0',value:'any'}});
handlers.change[0]({target:{dataset:{},classList:{contains:()=>false},id:'market-period',value:'dates'}});
assert.match(view.innerHTML,/market-from/);
assert.match(view.innerHTML,/market-to/);
assert.equal(JSON.stringify(window.PythosNBA.getState()),ownerBeforeMarket,'Market browsing must not write roster or money');
console.log('VM PASS v6.25: market filters, safe unknowns, read-only owner state');
