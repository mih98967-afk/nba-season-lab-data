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
  if(id==='navigation')return {addEventListener(){}};
  if(id==='source-status')return {textContent:''};
  if(id==='sports-check')return {scrollIntoView(){}};
  return nodes[id]||null;},
 addEventListener(name,fn){(handlers[name]||(handlers[name]=[])).push(fn)},
 querySelector(){return {remove(){}}},querySelectorAll(){return []}
};
const localStorage={getItem:k=>saved.get(k)||null,setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)};
const window={NBATransferGuard:require('./transfer_guard.js'),NBAScoreAudit:require('./score_audit.js'),
 NBASportsReconciliation:require('./sports_reconciliation.js'),NBATeamCourtLayout:require('./team_court.js')};
const ctx={window,document,localStorage,location:{protocol:'file:'},Date,Intl,Math,Number,String,Array,Map,Set,JSON,
 console,setTimeout:()=>{},setInterval:()=>{},clearTimeout:()=>{},fetch:()=>Promise.reject(Error('Unexpected external fetch'))};
vm.runInNewContext(fs.readFileSync(path.join(root,'app.js'),'utf8'),ctx,{timeout:10000,filename:'app.js'});
assert.match(view.innerHTML,/Моя команда/);
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
console.log('VM PASS: user-facing render, event wiring, private input, no state changes');
