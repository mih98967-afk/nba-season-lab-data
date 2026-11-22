// Pure calendar and data freshness regression, no network or private state.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const app=fs.readFileSync(path.join(__dirname,'app.js'),'utf8');
const begin=app.indexOf('// Player-market windows are separate');
const end=app.indexOf('function playerList(){',begin);
assert(begin>0&&end>begin,'Expected production implementation markers');
const frozen=Date.parse('2026-11-22T18:00:00Z'); // Sun 21:00 MSK
const monday=Date.parse('2026-11-22T21:00:00Z'); // Mon 00:00 MSK
const UI={marketPeriod:'preset',window:7,marketDays:10,marketFrom:'',marketTo:'',
 marketWeekFilters:['any','any','any']};
const games=[
 {epoch:frozen+3600000,status:'scheduled',home:'BOS',away:'NYK'},
 {epoch:monday,status:'scheduled',home:'BOS',away:'LAL'},
 {epoch:monday+2*86400000,status:'scheduled',home:'BOS',away:'PHI'},
 {epoch:monday+8*86400000,status:'scheduled',home:'BOS',away:'MIL'},
 {epoch:monday+15*86400000,status:'scheduled',home:'BOS',away:'CHI'},
 {epoch:monday+1000,status:'final',home:'BOS',away:'ATL'},
];
const S={roster:Array.from({length:10},(_,i)=>'n'+i)};
const LIVE={mode:'live_sync',updated_at_utc:'2026-11-22T17:00:00Z',
 games:[{id:'z',et_date:'2026-11-21',status:'final',epoch:frozen-5000}],
 rows:[{id:'n0',game_id:'z',played:true,fp:22.5},{id:'n1',game_id:'z',played:true,fp:-2}]};
const ctx={UI,S,LIVE,publicFeedValidated:true,Date,Math,Number,String,Set,Map,
 MARKET_DAY:undefined,
 now:()=>frozen,calendarCoverage:(start,days)=>({ok:true,reason:'complete'}),
 normalizedGames:()=>games,
 console};
vm.createContext(ctx);
vm.runInContext(app.slice(begin,end),ctx);
const get=(src)=>vm.runInContext(src,ctx);
assert.equal(get('marketISO('+frozen+')'),'2026-11-22');
assert.equal(get('marketMidnight("2026-11-23")'),monday);
assert(Number.isNaN(get('marketMidnight("2026-02-30")')),'reject impossible dates');
const w=get('marketWeeks()');
assert.equal(w.length,3);
assert.equal(w[0].end,monday);
assert.equal(w[1].start,monday);
assert.equal(w[2].start,monday+7*86400000);
assert.equal(get('marketKnownGames({team:"BOS"},marketWeeks()[0].start,marketWeeks()[0].end)'),1);
assert.equal(get('marketKnownGames({team:"BOS"},marketWeeks()[1].start,marketWeeks()[1].end)'),2);
assert.equal(get('marketKnownGames({team:"BOS"},marketWeeks()[2].start,marketWeeks()[2].end)'),1);
assert.equal(get('marketWeekMatch(0,"eq:0")'),true);
assert.equal(get('marketWeekMatch(null,"eq:0")'),false,'unknown is never zero');
assert.equal(get('marketWeekMatch(2,"min:2")'),true);
assert.equal(get('marketWeekMatch(1,"min:2")'),false);
assert.equal(get('marketWindowSpec().ok'),true);
UI.marketPeriod='days';UI.marketDays=21;
assert(Math.abs(get('marketWindowSpec().days')-21)<0.0001);
UI.marketDays=29;assert.equal(get('marketWindowSpec().ok'),false);
UI.marketPeriod='dates';UI.marketFrom='2026-11-23';UI.marketTo='2026-11-29';
assert.equal(get('marketWindowSpec().ok'),true);
assert.equal(get('marketWindowSpec().start'),monday);
assert.equal(get('marketWindowSpec().end'),monday+7*86400000);
UI.marketTo='2027-04-20';assert.equal(get('marketWindowSpec().ok'),false);
ctx.calendarCoverage=()=>({ok:false,reason:'NBA Cup unassigned'});
assert.equal(get('marketKnownGames({team:"BOS"},marketWeeks()[1].start,marketWeeks()[1].end)'),null);
assert.equal(get('marketWeekMatch(null,"min:3")'),false);
ctx.calendarCoverage=()=>({ok:true});
const recent=get('marketRecentRosterFP()');
assert.equal(recent.date,'2026-11-21');assert.equal(recent.fp,20.5);assert.equal(recent.played,2);
ctx.publicFeedValidated=false;assert.equal(get('marketRecentRosterFP()'),null);
assert(!app.includes('S.roster=BASE.players'),'market cannot touch owner roster');
console.log('PASS v6.25: 3 Moscow weeks, future custom dates, unknown Cup exclusions and read-only NBA team day');
