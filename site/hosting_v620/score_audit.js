/* NBA Season Lab v6.8 — pure read-only NBA boxscore/ownership audit.
 * This is NOT an official Sports.ru total or proof that an ET day has been credited.
 * No storage, network, personal identifiers, or account mutations.
 */
(function(root,factory){
 'use strict';
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 root.NBAScoreAudit=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const DAY='America/New_York';
 const ET=new Intl.DateTimeFormat('en-GB',{timeZone:DAY,year:'numeric',month:'2-digit',day:'2-digit'});
 const validDay=s=>typeof s==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(s);
 function dayET(epoch){
  const parts=ET.formatToParts(new Date(epoch));
  const get=k=>parts.find(x=>x.type===k)?.value;
  return `${get('year')}-${get('month')}-${get('day')}`;
 }
 function ownedAt(state,epoch){
  const initial=state?.initialRoster||[];
  if(!Array.isArray(initial)||!initial.length||!Number.isFinite(state?.initialEpoch)||epoch<state.initialEpoch)return [];
  const owned=initial.slice();
  // Equal timestamps preserve recorded insertion order, just like v6.7.
  for(const move of [...(state.executed||[])].sort((a,b)=>a.epoch-b.epoch)){
   if(Number.isFinite(move?.epoch)&&move.epoch<=epoch){
    const i=owned.indexOf(move.out);
    if(i>=0)owned[i]=move.in_;
   }
  }
  return owned;
 }
 // A season total is meaningful only if ownership can be replayed unambiguously.
 // User-provided timestamps remain self-reported, not official Sports.ru clocks.
 function ownershipLineage(state){
  const initial=state?.initialRoster;
  if(!Array.isArray(initial)||initial.length!==10||new Set(initial).size!==10||
     initial.some(id=>typeof id!=='string'||!id))
   return {ok:false,reason:'Нет подтверждённой исходной десятки для истории FP.'};
  if(!Number.isFinite(state?.initialEpoch))
   return {ok:false,reason:'Неизвестно начало владения исходным составом.'};
  if(!Array.isArray(state?.executed))
   return {ok:false,reason:'История выполненных замен недоступна.'};
  const current=initial.slice();
  const moves=state.executed.slice().sort((a,b)=>(a?.epoch||0)-(b?.epoch||0));
  for(const t of moves){
   if(!Number.isFinite(t?.epoch)||t.epoch<state.initialEpoch||
      typeof t.out!=='string'||typeof t.in_!=='string'||!t.in_||t.out===t.in_)
    return {ok:false,reason:'В истории есть замена без точного момента или игроков.'};
   const slot=current.indexOf(t.out);
   if(slot<0||current.includes(t.in_))
    return {ok:false,reason:'История замен не совпадает с последовательностью владения игроками.'};
   current[slot]=t.in_;
  }
  if(Array.isArray(state.roster)&&state.roster.length===10&&
     (new Set(state.roster).size!==10||current.some(id=>!state.roster.includes(id))))
   return {ok:false,reason:'История замен не воспроизводит текущую десятку.'};
  return {ok:true,reason:null};
 }
 function audit(live,state,options={}){
  const owner=ownershipLineage(state),warnings=[];
  const sourceReady=options.sourceVerified===true&&live?.mode==='live_sync'&&
   Array.isArray(live.games)&&Array.isArray(live.rows);
  if(!sourceReady)warnings.push('Публичный NBA live-срез не подтверждён; итог FP недоступен.');
  if(!owner.ok)warnings.push(owner.reason);
  const games=new Map((sourceReady?live.games:[]).filter(g=>g&&g.status==='final'&&Number.isFinite(g.epoch)).map(g=>[g.id,g]));
  const grouped=new Map();let fp=0,matches=0,incomplete=!owner.ok||!sourceReady;
  const unique=new Set();
  for(const r of sourceReady&&owner.ok?live.rows:[]){
   const g=games.get(r?.game_id);
   if(!g||!r?.id||r.played!==true)continue;
   if(!ownedAt(state,g.epoch-30*60000).includes(r.id))continue;
   const key=g.id+'|'+r.id;
   if(unique.has(key)){warnings.push('Повтор player-game в NBA feed; проверка очков неполная');incomplete=true;continue;}
   const raw=r.fp;
   // Number(null), Number('') and Number(' ') are zero in JS, but missing FP are UNKNOWN.
   const value=raw==null||(typeof raw==='string'&&!raw.trim())?NaN:Number(raw);
   if(!Number.isFinite(value)){warnings.push('Некорректные или отсутствующие FP в NBA feed');incomplete=true;continue;}
   unique.add(key);
   const day=validDay(g.et_date)?g.et_date:dayET(g.epoch);
   const group=grouped.get(day)||{day,fp:0,matches:0};
   group.fp+=value;group.matches++;
   grouped.set(day,group);
   fp+=value;matches++;
  }
  const days=[...grouped.values()].sort((a,b)=>a.day.localeCompare(b.day));
  const last=days.at(-1)||null;
  return {fp:incomplete?NaN:fp,matches,days,complete:!incomplete,
   ownershipReady:owner.ok,sourceReady,
   latestETDay:last?.day||null,latestETFP:incomplete?NaN:(last?.fp||0),
   earlierETFP:incomplete?NaN:fp-(last?.fp||0),warnings:[...new Set(warnings)],
   officialSportsFPTotal:null,officialSportsWeekCreditKnown:false,
   sourceUpdatedAt:live?.updated_at_utc||null,
   disclaimer:'ESPN/NBA boxscores, not Sports.ru credited FP. The newest ET date may be pending. Historical source stat corrections are possible.'};
 }
 return {audit,ownedAt,dayET,ownershipLineage};
});
