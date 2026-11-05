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
 function audit(live,state){
  const games=new Map((live?.games||[]).filter(g=>g&&g.status==='final'&&Number.isFinite(g.epoch)).map(g=>[g.id,g]));
  const grouped=new Map();let fp=0,matches=0;
  const unique=new Set(),warnings=[];
  for(const r of live?.rows||[]){
   const g=games.get(r?.game_id);
   if(!g||!r?.id||r.played!==true)continue;
   if(!ownedAt(state,g.epoch-30*60000).includes(r.id))continue;
   const key=g.id+'|'+r.id;
   if(unique.has(key)){warnings.push('Повтор player-game в NBA feed; проверка очков неполная');continue;}
   unique.add(key);
   const value=Number(r.fp);
   if(!Number.isFinite(value)){warnings.push('Некорректные FP в NBA feed');continue;}
   const day=validDay(g.et_date)?g.et_date:dayET(g.epoch);
   const group=grouped.get(day)||{day,fp:0,matches:0};
   group.fp+=value;group.matches++;
   grouped.set(day,group);
   fp+=value;matches++;
  }
  const days=[...grouped.values()].sort((a,b)=>a.day.localeCompare(b.day));
  const last=days.at(-1)||null;
  return {fp,matches,days,latestETDay:last?.day||null,latestETFP:last?.fp||0,
   earlierETFP:fp-(last?.fp||0),warnings:[...new Set(warnings)],
   officialSportsFPTotal:null,officialSportsWeekCreditKnown:false,
   sourceUpdatedAt:live?.updated_at_utc||null,
   disclaimer:'ESPN/NBA boxscores, not Sports.ru credited FP. The newest ET date may be pending. Historical source stat corrections are possible.'};
 }
 return {audit,ownedAt,dayET};
});
