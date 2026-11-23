/* Read-only schedule interpretation; days off and back-to-back are schedule facts, not opponent strength. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.NBACalendarContext=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const day=86400000;
 const fmt=new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'});
 function etDate(t){const x=typeof t==='number'?t:Date.parse(t);if(!Number.isFinite(x))return null;const parts=Object.fromEntries(fmt.formatToParts(new Date(x)).map(y=>[y.type,y.value]));return parts.year+'-'+parts.month+'-'+parts.day;}
 function describe(games,team,start,end,verified){
  if(!verified)return {ready:false,reason:'Календарь NBA не подтверждён',games:null,b2b:null,shortRest:null,unknownRest:null};
  if(!team||!Number.isFinite(start)||!Number.isFinite(end)||end<=start||!Array.isArray(games))return {ready:false,reason:'Недостаточно данных',games:null};
  const seen=new Set();const selected=[];
  for(const g of games){if(!g||![g.home,g.away].includes(team))continue;const ms=Number.isFinite(g.epoch)?g.epoch:Date.parse(g.utc||'');const d=etDate(ms);if(!Number.isFinite(ms)||!d)return {ready:false,reason:'Матч без даты',games:null};if(['cancelled','canceled','postponed'].includes(String(g.status||'').toLowerCase()))continue;const key=team+'|'+d+'|'+g.home+'|'+g.away;if(seen.has(key))continue;seen.add(key);selected.push({ms,d,opponent:g.home===team?g.away:g.home,away:g.away===team,raw:g});}
  selected.sort((a,b)=>a.ms-b.ms);
  const upcoming=selected.filter(g=>g.ms>=start&&g.ms<end);
  if(!upcoming.length)return {ready:true,games:0,b2b:0,shortRest:0,unknownRest:0,next:[],difficulty:'unknown'};
  let b2b=0,shortRest=0,unknownRest=0;
  const next=[];
  for(const x of upcoming){const prior=selected.filter(g=>g.ms<x.ms&&g.d!==x.d).at(-1);let off=null;
   if(prior){const delta=Math.round((Date.parse(x.d+'T00:00:00Z')-Date.parse(prior.d+'T00:00:00Z'))/day);off=Math.max(0,delta-1);if(off===0)b2b++;if(off===1)shortRest++;}else unknownRest++;
   next.push({epoch:x.ms,etDate:x.d,opponent:x.opponent,away:x.away,restDays:off,b2b:off===0});
  }
  return {ready:true,games:upcoming.length,b2b,shortRest,unknownRest,next,difficulty:'unknown'};
 }
 return {describe,etDate};
});
