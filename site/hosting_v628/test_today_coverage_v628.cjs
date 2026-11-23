'use strict';
// v6.28: deterministic oracle exercises the exact pure function copied in app.js.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/app.js','utf8');
const begin=source.indexOf('function todayForecastCoverageV628(');
const end=source.indexOf('function todayPage(){',begin);
assert(begin>=0&&end>begin,'Read-only coverage helper missing');
const ctx={};
vm.runInNewContext(source.slice(begin,end)+'\nthis.cover= todayForecastCoverageV628;',ctx);
const cover=ctx.cover;
const start=Date.parse('2026-11-23T12:00:00Z');
const roster=Array.from({length:10},(_,i)=>'n'+(i+1));
const players=Object.fromEntries([...roster,'n11'].map(id=>[id,{id,team:'BOS'}]));
const games=[
 {id:'g1',epoch:start+50*60000,home:'BOS',away:'NYK',status:'scheduled'},
 {id:'g2',epoch:start+100*60000,home:'BOS',away:'MIA',status:'scheduled'}];
const has=(p,g)=>(p.id==='n1'&&g.id==='g1')||(p.id==='n11'&&g.id==='g2');
let x=cover(roster,players,games,start,7,has);
assert.equal(x.available,true);assert.equal(x.total,20);assert.equal(x.modelled,1);
assert.equal(x.fallback,19);assert.match(x.note,/not accuracy/);
const move=epoch=>[{out:'n1',in_:'n11',epoch}];
// Exact lock ownership, never a guessed transfer-day owner.
x=cover(roster,players,games,start,7,has,move(start+30*60000));
assert.equal(x.total,20);assert.equal(x.modelled,2);assert.equal(x.fallback,18);
x=cover(roster,players,games,start,7,has,move(start+10*60000));
assert.equal(x.modelled,1);
x=cover(roster,players,games,start,7,has,move(start+85*60000));
assert.equal(x.modelled,1);
for(const invalid of [
 [roster,players,[games[0],{...games[0]}],start,7,has],
 [roster,{...players,n11:undefined},games,start,7,has,move(start)],
 [roster,players,[{...games[0],id:''}],start,7,has],
 [roster.slice(1),players,games,start,7,has],
 [roster,players,games,start,7,has,[{out:'ghost',in_:'n11',epoch:start}]],
 [roster,players,games,start,7,has,[{out:'n1',in_:'n11',epoch:NaN}]]
 ])assert.equal(cover(...invalid).available,false,JSON.stringify(invalid));
x=cover(roster,players,[],start,7,has);
assert.equal(x.available,true);assert.equal(x.total,0);assert.equal(x.modelled,0);
x=cover(roster,players,games,start,7,()=>{throw Error('Model');});
assert.equal(x.available,false,'Thrown model error must not silently become fallback');
console.log('PASS v6.28 exact-model coverage: route T-30, unknown and duplicate fail-closed');
