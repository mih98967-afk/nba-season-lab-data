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
// Unchecked injection with a forged new timestamp must never qualify as a live source.
window.PythosNBA.updateFeed({mode:'live_sync',updated_at_utc:new Date().toISOString(),rows:[],games:[],schedule:[]});
assert.match(view.innerHTML,/Сначала обнови статистику NBA/);
const click=action=>listeners.click[0]({target:{closest:()=>({dataset:{action}})}});
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
assert.match(view.innerHTML,/data-action="calculate-chains" disabled/);
assert.match(view.innerHTML,/Рекомендации заблокированы/);
assert.equal(window.PythosNBA.getState().roster.length,10);
// Ten entries without valid position structure cannot be silently treated as ready.
state=window.PythosNBA.getState();state.roster=[...roster.slice(0,9),roster[0]];
window.PythosNBA.setState(state);
listeners['nav:click']({target:{closest:()=>({dataset:{tab:'today'}})}});
assert.match(view.innerHTML,/Сначала проверь свой состав/);
assert.equal(plannerCalls,0);
console.log('PASS Today / Transfers VM: unvalidated feed and malformed roster fail closed without mutations');
