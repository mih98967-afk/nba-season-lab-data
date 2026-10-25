/* NBA Season Lab v6.5 - read-only Moscow-week calendar tour grid.
 * "Tour" is a DISPLAY grouping of Mon-Sun Moscow weeks, NOT verified
 * official fantasy tour IDs or a claim about exact Sports.ru reset times.
 * No invented games, no personal state mutations, no transfer execution.
 */
(function(root,factory){
 'use strict';
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 if(root)root.NBACalendarTours=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const DAY=86400000,WEEK=7*DAY,MSK=3*3600000;
 const FIRST_MONDAY=Date.parse('2026-10-18T21:00:00.000Z'); // 19 Oct 00:00 MSK
 const SEASON_END=Date.parse('2027-04-12T21:00:00.000Z');
 const epoch=v=>Number.isFinite(v)?v:typeof v==='string'?Date.parse(v):NaN;
 const dayKeyMsk=t=>{const ms=epoch(t);return Number.isFinite(ms)?new Date(ms+MSK).toISOString().slice(0,10):null;};
 const tourNumber=t=>{const ms=epoch(t);return Number.isFinite(ms)?Math.floor((ms-FIRST_MONDAY)/WEEK)+1:null;};
 const tourStart=n=>Number.isInteger(n)&&n>=1?FIRST_MONDAY+(n-1)*WEEK:NaN;
 const seasonTourCount=()=>tourNumber(SEASON_END-1);
 const tourRange=(start,count)=>{
   if(!Number.isInteger(start)||start<1||!Number.isInteger(count)||count<1||count>6)throw new Error('Invalid calendar tour range');
   const result=[];
   for(let i=0;i<count;i++){
     const n=start+i,from=tourStart(n);
     result.push({number:n,startUtc:from,endUtc:from+WEEK,
       labelStart:dayKeyMsk(from),labelEnd:dayKeyMsk(from+6*DAY),
       days:Array.from({length:7},(_,d)=>({epoch:from+d*DAY,key:dayKeyMsk(from+d*DAY)}))});
   }
   return result;
 };
 function buildMatrix(games,teamCodes,tours){
   if(!Array.isArray(games)||!Array.isArray(tours)||!tours.length||!Array.isArray(teamCodes))throw new Error('Invalid input');
   const slots=new Map(),seen=new Set(),teams=new Set(teamCodes);
   const from=tours[0].startUtc,to=tours[tours.length-1].endUtc;
   for(const g of games){
     if(!g||!g.home||!g.away||g.home===g.away||(!teams.has(g.home)&&!teams.has(g.away)))continue;
     if(['postponed','canceled','cancelled'].includes(g.status))continue;
     const ms=Number.isFinite(g.epoch)?g.epoch:epoch(g.utc);
     if(!Number.isFinite(ms)||ms<from||ms>=to)continue;
     const id=String(g.id||`${g.home}|${g.away}|${ms}`);
     const sig=id+'|'+g.home+'|'+g.away+'|'+ms;
     if(seen.has(sig))continue;
     seen.add(sig);
     const key=dayKeyMsk(ms),time=new Date(ms+MSK).toISOString().slice(11,16);
     for(const team of [g.home,g.away]){
       if(!teams.has(team))continue;
       const idx=team+'|'+key;
       if(!slots.has(idx))slots.set(idx,[]);
       slots.get(idx).push({id,ms,time,opponent:team===g.home?g.away:g.home,
         away:team===g.away,b2b:!!(team===g.home?g.home_b2b:g.away_b2b),
         status:g.status||'scheduled'});
     }
   }
   for(const list of slots.values())list.sort((a,b)=>a.ms-b.ms||a.opponent.localeCompare(b.opponent));
   const rows=teamCodes.map(team=>{
     const parts=tours.map(t=>{
       const days=t.days.map(d=>({key:d.key,games:slots.get(team+'|'+d.key)||[]}));
       return {number:t.number,days,count:days.reduce((sum,d)=>sum+d.games.length,0)};
     });
     return {team,parts,total:parts.reduce((sum,p)=>sum+p.count,0)};
   });
   return {tours,rows,actualUniqueGames:seen.size};
 }
 return {FIRST_MONDAY,DAY,WEEK,MSK,dayKeyMsk,tourNumber,tourStart,seasonTourCount,tourRange,buildMatrix};
});
