/* Research-grade, read-only ownership uncertainty for date-only Sports.ru transfers.
 * The range concerns observed positive-minute NBA boxscore FP ONLY. It cannot
 * establish Sports.ru credited FP, complete DNP denominators, or exact transfer clocks.
 */
(function(root,factory){
 'use strict';
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 root.NBAOwnershipBounds=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const DAY=86400000,MSK=3*3600000,LOCK=30*60000;
 const localDay=ms=>new Date(ms+MSK).toISOString().slice(0,10);
 const validDate=d=>typeof d==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(d)&&
  Number.isFinite(Date.parse(d+'T00:00:00+03:00'))&&
  localDay(Date.parse(d+'T00:00:00+03:00'))===d;
 const failure=reason=>({available:false,reason});
 function estimate(live,state,opts={}){
  const now=opts.nowEpoch;
  if(opts.sourceVerified!==true||!Number.isFinite(now)||live?.mode!=='live_sync'||
     !Array.isArray(live.games)||!Array.isArray(live.rows))return failure('Публичные NBA-результаты не подтверждены.');
  const updated=Date.parse(live.updated_at_utc||'');
  if(!Number.isFinite(updated)||updated>now+5*60000||now-updated>DAY)return failure('Срез NBA старше 24 часов или время публикации неизвестно.');
  const moves=state?.executed;
  const roster=state?.initialRoster;
  if(!Array.isArray(moves)||!moves.length||!Array.isArray(roster)||roster.length!==10||
     new Set(roster).size!==10||!Number.isFinite(state.initialEpoch)||
     !Number.isFinite(state.cash)||state.cash<0)return failure('Недостаточно подтверждений исходной десятки и истории.');
  if(moves.some(m=>!m||m.timePrecision!=='date_only'||m.epochIsPlaceholder!==true||
       !validDate(m.sportsRuDateMoscow)||typeof m.out!=='string'||typeof m.in_!=='string'||
       m.out===m.in_||!Number.isFinite(m.buy)||!Number.isFinite(m.sell)||m.buy<0||m.sell<0))
    return failure('Смешанные или неподтверждённые типы времени пока не допускают расчёт диапазона.');
  const sorted=moves.map((m,i)=>({...m,sourceIndex:i})).sort((a,b)=>a.sportsRuDateMoscow.localeCompare(b.sportsRuDateMoscow)||a.sourceIndex-b.sourceIndex);
  if(sorted.some(m=>Date.parse(m.sportsRuDateMoscow+'T00:00:00+03:00')<state.initialEpoch-DAY||
    Date.parse(m.sportsRuDateMoscow+'T00:00:00+03:00')>now))return failure('Дата замены вне подтверждённого периода.');
  const initialCash=state.cash-sorted.reduce((sum,m)=>sum+(m.sell-m.buy),0);
  if(!Number.isFinite(initialCash)||initialCash<0)return failure('Движение кассы не согласовано с историей Sports.ru.');
  const games=new Map();
  for(const game of live.games){
   if(game?.status!=='final')continue;
   if(!game.id||!Number.isFinite(game.epoch)||games.has(game.id))return failure('Повторы или неверные времена матчей NBA.');
   if(game.epoch>now||game.epoch<state.initialEpoch)continue;
   games.set(game.id,game);
  }
  if(!games.size)return failure('Нет подтверждённых завершённых матчей для периода владения.');
  const scored=new Map();
  for(const r of live.rows){
   if(!games.has(r.game_id)||r.played!==true)continue;
   if(typeof r.id!=='string'||typeof r.fp!=='number'||!Number.isFinite(r.fp))
    return failure('Некорректные или отсутствующие очки сыгравшего игрока.');
   const key=r.game_id+'|'+r.id;
   if(scored.has(key))return failure('Повтор игроко-матча в NBA-срезе.');
   scored.set(key,r.fp);
  }
  const gamesByDay=new Map();
  for(const game of games.values()){
   const lock=game.epoch-LOCK;
   if(lock<state.initialEpoch)continue;
   const day=localDay(lock);
   if(!gamesByDay.has(day))gamesByDay.set(day,[]);
   gamesByDay.get(day).push({game,lock});
  }
  const movesByDay=new Map();
  for(const m of sorted){const day=m.sportsRuDateMoscow;
   if(!movesByDay.has(day))movesByDay.set(day,[]);
   movesByDay.get(day).push(m);
  }
  const days=[...new Set([...gamesByDay.keys(),...movesByDay.keys()])].sort();
  let owned=roster.slice(),cash=initialCash,certain=0,min=0,max=0,playedKnown=0;
  const windows=[];
  const gameFP=(ids,g)=>{let total=0,n=0;for(const id of ids){const p=scored.get(g.game.id+'|'+id);
   if(typeof p==='number'){total+=p;n++;}}
   return {total,n};};
  const tryMove=(ids,bank,m)=>{
   const ix=ids.indexOf(m.out);
   if(ix<0||ids.includes(m.in_)||bank+m.sell<m.buy)return null;
   const next=ids.slice();next[ix]=m.in_;
   return {owned:next,cash:bank+m.sell-m.buy};
  };
  for(const date of days){
   const dayGames=(gamesByDay.get(date)||[]).sort((a,b)=>a.lock-b.lock||String(a.game.id).localeCompare(String(b.game.id)));
   const dayMoves=movesByDay.get(date)||[];
   if(!dayMoves.length){
    for(const g of dayGames){const p=gameFP(owned,g);certain+=p.total;playedKnown+=p.n;}
    continue;
   }
   if(dayMoves.length>4)return failure('Больше четырёх замен в один день: точный перебор не поддерживается.');
   let low=Infinity,high=-Infinity,valid=0,final=null;
   function walk(ids,bank,remaining,at,total){
    if(valid>75000)return;
    if(!remaining.length){let score=total;for(let i=at;i<dayGames.length;i++)score+=gameFP(ids,dayGames[i]).total;
     valid++;low=Math.min(low,score);high=Math.max(high,score);
     if(!final)final={owned:ids,cash:bank};
     else if(final.cash!==bank||final.owned.some((id,i)=>id!==ids[i]))valid=75001;
     return;
    }
    let accrued=0;
    for(let i=at;i<=dayGames.length;i++){
     if(i>at)accrued+=gameFP(ids,dayGames[i-1]).total;
     for(let j=0;j<remaining.length;j++){
      const m=remaining[j],next=tryMove(ids,bank,m);
      if(next)walk(next.owned,next.cash,remaining.filter((_,idx)=>idx!==j),i,total+accrued);
     }
    }
   }
   walk(owned,cash,dayMoves,0,0);
   if(!valid||valid>75000||!final)return failure('Не удалось однозначно подтвердить последовательность состава и денег.');
   min+=low;max+=high;
   windows.push({date,minimum:low,maximum:high,uncertainty:high-low,
    gamesWithLockOnDate:dayGames.length,validTimingScenarios:valid});
   owned=final.owned;cash=final.cash;
  }
  if(cash!==state.cash||!Array.isArray(state.roster)||
    state.roster.length!==10||owned.slice().sort().join('|')!==state.roster.slice().sort().join('|'))
   return failure('Восстановленные состав или касса не совпадают с текущим профилем.');
  return {available:true,minimum:certain+min,maximum:certain+max,
   fixedDateFP:certain,windows,sourceUpdatedAtUtc:live.updated_at_utc,
   observedPlayedPlayerGamesOnUnambiguousDates:playedKnown,
   disclaimer:'Диапазон только известных FP сыгравших игроков по NBA boxscore при всех допустимых внутридневных моментах замены. Не является пределами официальных FP Sports.ru: DNP/UNKNOWN, срок зачёта, исправления источника и точное время покупки не подтверждены.'};
 }
 return {estimate};
});
