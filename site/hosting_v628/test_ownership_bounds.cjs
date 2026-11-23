const assert=require('node:assert/strict');
const {estimate}=require('./ownership_bounds.js');
const at=x=>Date.parse(x);
const newGames=[['g1','2026-11-03T00:00:00Z'],['g2','2026-11-03T12:00:00Z'],['g3','2026-11-04T00:00:00Z']].map(([id,utc])=>({id,utc,epoch:at(utc),status:'final'}));
const live={mode:'live_sync',updated_at_utc:'2026-11-04T08:00:00Z',games:newGames,rows:[
{id:'a',game_id:'g1',played:true,fp:10},{id:'b',game_id:'g1',played:true,fp:-2},
{id:'a',game_id:'g2',played:true,fp:30},{id:'b',game_id:'g2',played:true,fp:20},
{id:'b',game_id:'g3',played:true,fp:8}]};
const roster=['a',...Array.from({length:9},(_,i)=>'x'+i)];
const state={initialEpoch:at('2026-10-20T00:00:00Z'),initialRoster:roster,
 roster:['b',...roster.slice(1)],cash:0,executed:[{out:'a',in_:'b',sell:100,buy:100,
 sportsRuDateMoscow:'2026-11-03',timePrecision:'date_only',epochIsPlaceholder:true,epoch:at('2026-11-03T04:00:00Z')}]};
const opts={sourceVerified:true,nowEpoch:at('2026-11-04T09:00:00Z')};
let x=estimate(live,state,opts);assert.equal(x.available,true,JSON.stringify(x));
assert.equal(x.minimum,26,'Negative played FP must remain negative');
assert.equal(x.maximum,48,'Later ownership may be worth more');
assert.equal(x.windows.length,1);
assert.equal(x.fixedDateFP,8);
assert.equal(x.windows[0].gamesWithLockOnDate,2);
assert.equal(estimate(live,state,{...opts,sourceVerified:false}).available,false);
assert.equal(estimate({...live,updated_at_utc:'2026-10-30T00:00:00Z'},state,opts).available,false);
const bad=structuredClone(live);bad.rows.push({...bad.rows[0]});
assert.equal(estimate(bad,state,opts).available,false,'Duplicate row cannot be silently counted twice');
const changed=structuredClone(state);changed.cash=-2;
assert.equal(estimate(live,changed,opts).available,false,'Wrong balance invalidates owner reconstruction');
const mixed=structuredClone(state);mixed.executed[0].timePrecision='exact';
assert.equal(estimate(live,mixed,opts).available,false,'Do not infer mixed precise and date-only timestamps');
console.log('PASS ownership bounds: scenarios, negatives, stale/forged sources, identity and cash');
