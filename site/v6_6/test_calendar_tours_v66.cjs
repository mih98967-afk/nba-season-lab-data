'use strict';
const assert=require('node:assert/strict');
const T=require('./calendar_tours.js');
const teamCodes=['BKN','IND','DEN','GSW','LAL','UTA'];
let passes=0;
function test(title, fn){fn();passes++;process.stdout.write('PASS '+title+'\n');}
function game(id,utc,home='BKN',away='IND',more={}){return {id,utc,epoch:Date.parse(utc),home,away,status:'scheduled',...more};}
const oldSunday=game('sunday','2026-10-25T22:00:00Z'); // Mon 01:00 Moscow, Sun 18:00 EDT
const monday=game('monday','2026-10-26T23:00:00Z','DEN','GSW'); // Tue 02:00 Moscow, Mon 19:00 EDT
const t1=T.tourRange(1,1),t2=T.tourRange(2,1);
test('Monday 01:00 Moscow still previous US/ET Sunday',()=>{
 assert.equal(T.dayKeyMsk(oldSunday.epoch),'2026-10-26');
 assert.equal(T.dayKeyET(oldSunday.epoch),'2026-10-25');
 assert.equal(T.tourNumber(oldSunday.epoch),1);
 const x=T.buildMatrix([oldSunday],teamCodes,t1);
 assert.equal(x.rows.find(r=>r.team==='BKN').total,1);
 assert.equal(x.rows.find(r=>r.team==='BKN').parts[0].days.at(-1).games.length,1);
 assert.equal(x.rows.find(r=>r.team==='BKN').parts[0].days.at(-1).games[0].time,'01:00');
 assert.equal(x.rows.find(r=>r.team==='BKN').parts[0].days.at(-1).games[0].moscowNextDay,true);
 assert.equal(T.buildMatrix([oldSunday],teamCodes,t2).actualUniqueGames,0);
});
test('Late Monday ET correctly belongs to next tour',()=>{
 assert.equal(T.tourNumber(monday.utc),2);
 assert.equal(T.dayKeyMsk(monday.epoch),'2026-10-27');
 assert.equal(T.buildMatrix([monday],teamCodes,t1).actualUniqueGames,0);
 assert.equal(T.buildMatrix([monday],teamCodes,t2).rows.find(r=>r.team==='DEN').total,1);
});
test('Eastern DST fall back resolves correct NBA day',()=>{
 assert.equal(T.dayKeyET('2026-11-01T05:30:00Z'),'2026-11-01');
 assert.equal(T.dayKeyET('2026-11-01T06:30:00Z'),'2026-11-01');
 assert.equal(T.dayKeyET('2026-11-02T03:30:00Z'),'2026-11-01');
 assert.equal(T.dayKeyET('2026-11-02T05:30:00Z'),'2026-11-02');
});
test('Eastern spring DST starts properly',()=>{
 assert.equal(T.dayKeyET('2027-03-14T06:30:00Z'),'2027-03-14');
 assert.equal(T.dayKeyET('2027-03-14T07:30:00Z'),'2027-03-14');
 assert.equal(T.dayKeyET('2027-03-15T03:30:00Z'),'2027-03-14');
});
test('Season 25 fixed US weekly tours and New Year boundaries',()=>{
 assert.equal(T.seasonTourCount(),25);
 assert.equal(T.tourStartDate(1),'2026-10-19');
 assert.equal(T.tourRange(25,1)[0].labelEnd,'2027-04-11');
 assert.equal(T.tourNumber('2027-01-01T02:00:00Z'),11);
 assert.equal(T.tourRange(12,1)[0].labelStart,'2027-01-04');
});
test('Select arbitrary dates 1 through 185 days inclusive',()=>{
 assert.equal(T.dateRange('2026-10-25','2026-10-26')[0].days.length,2);
 assert.equal(T.dateRange('2026-10-25','2026-10-25')[0].days.length,1);
 assert.equal(T.dateRange('2026-12-28','2027-01-09')[0].days.length,13);
 assert.equal(T.dateRange('2026-10-19','2027-04-11')[0].days.length,175);
 assert.throws(()=>T.dateRange('2027-01-05','2027-01-04'));
 assert.throws(()=>T.dateRange('2026-10-01','2027-05-30'));
});
test('Games identical across source IDs count only once in period',()=>{
 const gs=[oldSunday,{...oldSunday,id:'alternate_feed_id'}];
 const r=T.buildMatrix(gs,teamCodes,T.dateRange('2026-10-25','2026-10-27'));
 assert.equal(r.actualUniqueGames,1);
 assert.equal(r.totalTeamAppearances,2);
});
test('Canceled fixtures and outside dates excluded',()=>{
 const gs=[oldSunday,game('canceled','2026-10-25T23:00:00Z','DEN','GSW',{status:'canceled'}),monday];
 assert.equal(T.buildMatrix(gs,teamCodes,t1).actualUniqueGames,1);
});
test('One filtered team gets its own accurate total',()=>{
 const x=T.buildMatrix([oldSunday,monday],['BKN'],T.tourRange(1,2));
 assert.equal(x.rows.length,1);assert.equal(x.rows[0].total,1);
 assert.equal(x.totalTeamAppearances,1);assert.equal(x.actualUniqueGames,1);
});
test('6 and 12 tours supported with stable day counts',()=>{
 assert.equal(T.tourRange(1,6).flatMap(g=>g.days).length,42);
 assert.equal(T.tourRange(14,12).flatMap(g=>g.days).length,84);
 assert.throws(()=>T.tourRange(22,6));
});
test('All 30 teams present, sorting total descending stable by team name',()=>{
 const teams=Array.from({length:30},(_,i)=>'T'+String(i).padStart(2,'0'));
 const x=T.buildMatrix([game('x','2026-10-25T22:00:00Z','T29','T05')],teams,t1);
 const sorted=[...x.rows].sort((a,b)=>b.total-a.total||a.team.localeCompare(b.team));
 assert.equal(x.rows.length,30);assert.equal(sorted[0].team,'T05');assert.equal(sorted[1].team,'T29');
});
test('Moscow time and ET assignment are separate',()=>{
 const r=T.buildMatrix([oldSunday],teamCodes,T.dateRange('2026-10-25','2026-10-25'));
 const match=r.rows[0].parts[0].days[0].games[0];
 assert.equal(match.moscowDate,'2026-10-26');assert.equal(match.etDate,'2026-10-25');
 assert.equal(match.time,'01:00');
});
test('True UTC vs invalid boundaries fail closed',()=>{
 assert.equal(T.dayKeyET('invalid'),null);assert.equal(T.daysBetween('2026-02-30','2026-03-01'),NaN);
 assert.throws(()=>T.buildMatrix([],teamCodes,[{days:[{key:'2030-15-88'}]}]));
});
console.log('NBA_V66_CALENDAR_REGRESSION_PASS',passes);
