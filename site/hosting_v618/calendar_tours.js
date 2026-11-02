/* NBA Season Lab v6.6: NBA league-date (Eastern Time) groupings, Moscow clocks.
 * NBA week is Monday-Sunday in America/New_York. Monday early Moscow
 * games played on Sunday in New York are included in the previous tour.
 * Display-only grouping, not a verified Sports.ru scoring-week policy.
 * Pure read-only API. No roster, cash, trades or Firestore access.
 */
(function(root,factory){
 'use strict';
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 if(root)root.NBACalendarTours=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const DAY=86400000,WEEK=7*DAY,MSK=3*3600000;
 const FIRST_DATE='2026-10-19',LAST_DATE='2027-04-11';
 const FIRST_MONDAY=Date.parse('2026-10-19T04:00:00.000Z');
 const MAX_WINDOW_DAYS=185;
 const etFormatter=new Intl.DateTimeFormat('en-US', {timeZone:'America/New_York', year:'numeric',month:'2-digit',day:'2-digit'});
 const epoch=v=>Number.isFinite(v)?v:typeof v==='string'?Date.parse(v):NaN;
 const ordinal=key=>{
   if(typeof key!=='string'||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(key))return NaN;
   const t=Date.parse(key+'T00:00:00Z');
   return Number.isFinite(t)&&new Date(t).toISOString().slice(0,10)===key?t:NaN;
 };
 const addDays=(key,count)=>{
   const ms=ordinal(key);
   return Number.isFinite(ms)&&Number.isInteger(count)?new Date(ms+count*DAY).toISOString().slice(0,10):null;
 };
 const daysBetween=(start,end)=>{
   const a=ordinal(start),b=ordinal(end);
   return Number.isFinite(a)&&Number.isFinite(b)?Math.round((b-a)/DAY):NaN;
 };
 const dayKeyMsk=t=>{
   const ms=epoch(t);return Number.isFinite(ms)?new Date(ms+MSK).toISOString().slice(0,10):null;
 };
 const dayKeyET=t=>{
   const ms=epoch(t);
   if(!Number.isFinite(ms))return null;
   const p=Object.fromEntries(etFormatter.formatToParts(new Date(ms)).filter(x=>x.type!=='literal').map(x=>[x.type,x.value]));
   return p.year+'-'+p.month+'-'+p.day;
 };
 const mskTime=t=>{
   const ms=epoch(t);
   return Number.isFinite(ms)?new Date(ms+MSK).toISOString().slice(11,16):null;
 };
 // All tour numbers/column dates follow the NBA league's American date.
 const tourNumber=t=>{
   const key=dayKeyET(t);const delta=daysBetween(FIRST_DATE,key);
   return Number.isFinite(delta)?Math.floor(delta/7)+1:null;
 };
 const tourStartDate=n=>Number.isInteger(n)&&n>=1?addDays(FIRST_DATE,(n-1)*7):null;
 const tourStart=n=>{const key=tourStartDate(n);return key?ordinal(key):NaN;};
 const seasonTourCount=()=>Math.floor(daysBetween(FIRST_DATE,LAST_DATE)/7)+1;
 const periodDays=(start,count)=>Array.from({length:count},(_,i)=>({
   key:addDays(start,i),epoch:ordinal(addDays(start,i))
 }));
 const tourRange=(start,count)=>{
   if(!Number.isInteger(start)||start<1||start>seasonTourCount()||
      !Number.isInteger(count)||count<1||count>12||start+count-1>seasonTourCount())
     throw new Error('Invalid tour range');
   return Array.from({length:count},(_,i)=>{
     const n=start+i,from=tourStartDate(n),to=addDays(from,6);
     return {number:n,kind:'tour',labelStart:from,labelEnd:to,
       days:periodDays(from,7)};
   });
 };
 const dateRange=(start,end)=>{
   const total=daysBetween(start,end)+1;
   if(!Number.isInteger(total)||total<1||total>MAX_WINDOW_DAYS)
     throw new Error('Date range must be between 1 and '+MAX_WINDOW_DAYS+' days');
   return [{kind:'range',number:null,labelStart:start,labelEnd:end,
     days:periodDays(start,total)}];
 };
 function buildMatrix(games,teamCodes,periods){
   if(!Array.isArray(games)||!Array.isArray(periods)||!periods.length||!Array.isArray(teamCodes))
     throw new Error('Invalid NBA calendar input');
   const keys=periods.flatMap(t=>t.days.map(d=>d.key));
   if(!keys.length||keys.some(k=>!Number.isFinite(ordinal(k)))||new Set(keys).size!==keys.length)
     throw new Error('Invalid or repeated displayed day');
   const days=new Set(keys),teams=new Set(teamCodes),slots=new Map(),seen=new Set();
   for(const g of games){
     if(!g||!g.home||!g.away||g.home===g.away||(!teams.has(g.home)&&!teams.has(g.away)))continue;
     if(['postponed','canceled','cancelled'].includes(String(g.status||'').toLowerCase()))continue;
     const ms=Number.isFinite(g.epoch)?g.epoch:epoch(g.utc);
     if(!Number.isFinite(ms))continue;
     const key=dayKeyET(ms);
     if(!days.has(key))continue;
     // Different feeds may use different IDs for the SAME game.
     // Home, away and NBA calendar date are its stable display identity.
     const sig=g.home+'|'+g.away+'|'+key;
     if(seen.has(sig))continue;
     seen.add(sig);
     const utcDate=new Date(ms).toISOString(),local=dayKeyMsk(ms),time=mskTime(ms);
     for(const team of [g.home,g.away]){
       if(!teams.has(team))continue;
       const idx=team+'|'+key;
       if(!slots.has(idx))slots.set(idx,[]);
       slots.get(idx).push({id:String(g.id||sig),ms,utc:utcDate,
         etDate:key,moscowDate:local,time,
         moscowNextDay:daysBetween(key,local)>0,
         opponent:team===g.home?g.away:g.home,
         away:team===g.away,
         b2b:!!(team===g.home?g.home_b2b:g.away_b2b),
         status:g.status||'scheduled'});
     }
   }
   for(const a of slots.values())a.sort((a,b)=>a.ms-b.ms||a.opponent.localeCompare(b.opponent));
   const rows=teamCodes.map(team=>{
     const parts=periods.map(t=>{
       const list=t.days.map(d=>({key:d.key,games:slots.get(team+'|'+d.key)||[]}));
       return {number:t.number,kind:t.kind,days:list,
         count:list.reduce((n,d)=>n+d.games.length,0)};
     });
     return {team,parts,total:parts.reduce((n,p)=>n+p.count,0)};
   });
   return {periods,tours:periods,rows,actualUniqueGames:seen.size,
     totalTeamAppearances:rows.reduce((n,r)=>n+r.total,0)};
 }
 return {FIRST_DATE,LAST_DATE,FIRST_MONDAY,DAY,WEEK,MSK,MAX_WINDOW_DAYS,
   dayKeyMsk,dayKeyET,mskTime,addDays,daysBetween,tourNumber,tourStart,
   tourStartDate,seasonTourCount,tourRange,dateRange,buildMatrix};
});
