const test=require('node:test'),assert=require('node:assert/strict');
const p=require('./site/v6_2/multi_planner.js');
test('Moscow week Sunday crossing',()=>{assert.equal(p.weekKey(Date.parse('2026-10-25T20:59:59Z')),'2026-10-19');assert.equal(p.weekKey(Date.parse('2026-10-25T21:00:00Z')),'2026-10-26');});
test('No complete calendar means no transfer recommendation',()=>{const x=p.plan({roster:Array(10).fill('x'),whenEpoch:1,nowEpoch:1,coverage:()=>({ok:false})});assert.equal(x.ready,false);});
test('Invalid horizon rejected',()=>{assert.equal(p.plan({horizonDays:15}).ready,false);});
