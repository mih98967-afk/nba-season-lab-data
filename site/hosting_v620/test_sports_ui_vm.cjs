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
