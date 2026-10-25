'use strict';
// Run from repository checkout via GitHub Actions, after schedule.json exists.
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const T=require('./calendar_tours');
const target=path.join(__dirname,'..','..','data','schedule.json');
if(!fs.existsSync(target)){
 console.log('FULL_VERIFIED_CALENDAR_LOCAL_SKIP: run from GitHub checkout to test all published fixtures');
 process.exit(0);
}
const j=JSON.parse(fs.readFileSync(target,'utf8'));
assert(j.status==='verified_public_calendar_with_known_gaps','Expected validated full-calendar file');
assert(j.games.length>=1100 && j.games.length<=1230);
const teams=[...new Set(j.games.flatMap(g=>[g.home,g.away]))].sort();
assert.equal(teams.length,30);
const all=T.buildMatrix(j.games,teams,T.dateRange(T.FIRST_DATE,T.LAST_DATE));
assert.equal(all.rows.length,30);
assert.equal(all.actualUniqueGames,j.games.length);
assert.equal(all.totalTeamAppearances,2*j.games.length);
let crossing=0;
for(const g of j.games){
 const keyET=T.dayKeyET(g.utc),keyMSK=T.dayKeyMsk(g.utc);
 if(keyMSK!==keyET && new Date(keyMSK+'T00:00:00Z').getUTCDay()===1 &&
    new Date(keyET+'T00:00:00Z').getUTCDay()===0){
  crossing++;
  const n=T.tourNumber(g.utc),group=T.tourRange(n,1);
  assert(group[0].days.some(d=>d.key===keyET),'Monday early Moscow should map to US Sunday');
  assert.equal(group[0].labelEnd,keyET);
 }
}
assert(crossing>=50,'Expected many Sunday US to Monday Moscow crossover fixtures in full season');
console.log('FULL_PUBLISHED_NBA_CALENDAR_V66_PASS',JSON.stringify({games:j.games.length,teams:teams.length,monday_msk_sunday_et:crossing}));
