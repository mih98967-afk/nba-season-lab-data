/* NBA Season Lab: pure Sports.ru draft-transfer eligibility guard.
 * No Firestore writes, no Sports.ru API calls, no automatic transfers.
 * Position and club caps are deterministic; prices/unlock state require owner verification.
 */
(function(root,factory){
  'use strict';
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  root.NBATransferGuard=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const POSITIONS=['PG','SG','SF','PF','C'];
  const HALF_HOUR=30*60000;
  const HOUR=3600000;
  function weekKey(epoch,resetHour=15){
    if(!Number.isFinite(epoch))return null;
    const d=new Date(epoch+3*HOUR-resetHour*HOUR);
    if(!Number.isFinite(d.getTime()))return null;
    const day=(d.getUTCDay()+6)%7;
    d.setUTCDate(d.getUTCDate()-day);
    return d.toISOString().slice(0,10);
  }
  function calendarWeekEnd(epoch){
    const key=weekKey(epoch,0);
    return key?Date.parse(key+'T00:00:00+03:00')+7*86400000:NaN;
  }
  function checkRoster(ids,players){
    const errors=[];
    if(!Array.isArray(ids)||ids.length!==10)errors.push('Нужны ровно 10 игроков');
    if(new Set(ids||[]).size!==(ids||[]).length)errors.push('Один игрок указан в нескольких слотах');
    const positions=Object.fromEntries(POSITIONS.map(p=>[p,0]));
    const teams={};
    for(const id of ids||[]){
      const p=players?.[id];
      if(!p){errors.push('Игрок отсутствует в каталоге: '+id);continue;}
      if(!POSITIONS.includes(p.pos)){errors.push('Неизвестная позиция: '+id);continue;}
      positions[p.pos]++;
      teams[p.team]=(teams[p.team]||0)+1;
    }
    for(const [pos,n] of Object.entries(positions))if(n!==2)errors.push(pos+': необходимо два игрока');
    for(const [team,n] of Object.entries(teams))if(n>2)errors.push(team+': не более двух игроков');
    return errors;
  }
  function price(value){
    if(value===null||value===undefined||String(value).trim()==='')return NaN;
    const n=Number(value);
    return Number.isFinite(n)&&n>=0?n:NaN;
  }
  function validGames(games){
    return (Array.isArray(games)?games:[]).map(g=>({
      ...g,stamp:Number.isFinite(g?.epoch)?g.epoch:Date.parse(g?.utc||'')
    })).filter(g=>Number.isFinite(g.stamp)&&g.home&&g.away&&!['canceled','cancelled'].includes(g.status));
  }
  // A completed historical transfer may have only a Sports.ru MOSCOW DATE.
  // Never use its synthetic epoch to assign a weekly quota. Track lower/upper
  // count bounds independently for Monday 15:00 and Monday 00:00 resets.
  function historicalWeekBounds(executed,observedAt){
    const min15={},max15={},min00={},max00={};
    let dateOnly=0,ambiguous=0,invalid=0;
    const DAY=86400000;
    const add=(low,high,start,end,hour)=>{
      const a=weekKey(start,hour),b=weekKey(end,hour);
      if(!a||!b)return false;
      high[a]=(high[a]||0)+1;
      if(b!==a){high[b]=(high[b]||0)+1;ambiguous++;}
      else low[a]=(low[a]||0)+1;
      return true;
    };
    for(const t of executed){
      let start,end;
      if(t?.timePrecision==='date_only'||t?.epochIsPlaceholder===true){
        dateOnly++;
        const day=t?.sportsRuDateMoscow;
        if(typeof day!=='string'||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(day)){
          invalid++;continue;
        }
        start=Date.parse(day+'T00:00:00+03:00');
        if(!Number.isFinite(start)||new Date(start+3*HOUR).toISOString().slice(0,10)!==day||
           !Number.isFinite(observedAt)||start>observedAt){invalid++;continue;}
        end=Math.min(start+DAY-1,observedAt);
      }else{
        start=t?.epoch;end=start;
        if(!Number.isFinite(start)||!Number.isFinite(observedAt)||start>observedAt+60000){
          invalid++;continue;
        }
      }
      if(!add(min15,max15,start,end,15)||!add(min00,max00,start,end,0))invalid++;
    }
    return {min15,max15,min00,max00,dateOnly,ambiguous,invalid};
  }
  function validate(input){
    const players=input?.players||{},draft=Array.isArray(input?.draft)?input.draft:[];
    const executed=Array.isArray(input?.executed)?input.executed:[];
    const schedule=validGames(input?.games);
    const errors=[],warnings=[],steps=[];
    let roster=[...(Array.isArray(input?.roster)?input.roster:[])],cash=price(input?.cash);
    if(!Number.isFinite(cash)){errors.push('Неизвестная или отрицательная касса');cash=0;}
    const now=Number.isFinite(input?.nowEpoch)?input.nowEpoch:Date.now();
    const bounds=historicalWeekBounds(executed,now);
    const used={...bounds.min15},alternate={...bounds.min00};
    const upper15={...bounds.max15},upper00={...bounds.max00};
    // Lower counts are certain. Upper counts mark possible membership.
    // One ambiguous Monday can never be resolved using a placeholder hour.
    if(bounds.invalid)warnings.push('В истории есть замена без достоверной даты или с датой в будущем: квота по журналу не подтверждена.');
    if(bounds.ambiguous)warnings.push('Дата прошлой замены пересекает возможный сброс недели: её часы неизвестны.');
    const historicalQuotaConflict=Object.values(used).some(n=>n>3)&&
      Object.values(alternate).some(n=>n>3);
    if(historicalQuotaConflict)
      warnings.push('В сохранённой истории есть недели с более чем тремя операциями при обеих гипотезах сброса; новые недели проверяются отдельно.');
    if(draft.length&&!schedule.length)warnings.push('Нет расписания матчей: блокировки не проверены');
    const sorted=[...draft].sort((a,b)=>(a.epoch||0)-(b.epoch||0));
    for(const t of sorted){
      const ee=[],ww=[];
      const out=players[t?.out],inp=players[t?.in_];
      if(!out||!inp)ee.push('Неизвестный игрок OUT/IN');
      if(!roster.includes(t?.out))ee.push('Продаваемого игрока нет в составе');
      if(roster.includes(t?.in_))ee.push('Покупаемый игрок уже в составе');
      if(out&&inp&&out.pos!==inp.pos)ee.push('Замена должна сохранять позицию');
      const stamp=t?.epoch;
      if(!Number.isFinite(stamp))ee.push('Нужно точное время операции');
      const key=weekKey(stamp),alt=weekKey(stamp,0);
      if(key){used[key]=(used[key]||0)+1;upper15[key]=(upper15[key]||0)+1;}
      if(alt){alternate[alt]=(alternate[alt]||0)+1;upper00[alt]=(upper00[alt]||0)+1;}
      const definitely15=key!==null&&(used[key]||0)>3;
      const definitely00=alt!==null&&(alternate[alt]||0)>3;
      const possibly15=key!==null&&(upper15[key]||0)>3;
      const possibly00=alt!==null&&(upper00[alt]||0)>3;
      if(definitely15&&definitely00)
        ee.push('Превышены три замены при обеих гипотезах сброса недельной квоты');
      else if(possibly15||possibly00)
        ww.push('Недостаточно данных о недельной квоте: возможен лимит при одном из сбросов или неизвестном часе прошлой замены. Проверьте Sports.ru');
      const sell=price(t?.sell),buy=price(t?.buy);
      if(!Number.isFinite(sell)||!Number.isFinite(buy))ee.push('Необходимы фактические цены продажи и покупки');
      const nextCash=cash+sell-buy;
      if(Number.isFinite(nextCash)&&nextCash<-.00001)ee.push('Недостаточно денег для покупки');
      if(Number.isFinite(stamp)){
        if(stamp<now-3*HOUR)ww.push('Прошлая операция: проверьте реальное время на Sports.ru');
        if(stamp>now+30*60000)ww.push('Будущая операция: цены и доступность могут измениться');
        for(const p of [out,inp]){
          if(!p)continue;
          const clubGames=schedule.filter(g=>g.home===p.team||g.away===p.team);
          for(const g of clubGames){
            if(stamp>=g.stamp-HALF_HOUR&&stamp<g.stamp){
              ee.push((p.name||p.id||p.team)+': предматчевая блокировка (−30 минут)');
            }else if(stamp>=g.stamp&&stamp<g.stamp+12*HOUR){
              ww.push((p.name||p.id||p.team)+': после начала матча нужна проверка разблокировки Sports.ru');
            }
          }
        }
        if(schedule.length&&stamp>Math.max(...schedule.map(g=>g.stamp)))
          ww.push('Дата операции позднее последнего доступного матча календаря');
      }
      const nextRoster=[...roster];
      const at=nextRoster.indexOf(t?.out);
      if(at!==-1)nextRoster[at]=t?.in_;
      if(out&&inp)ee.push(...checkRoster(nextRoster,players));
      const step={t,errors:[...new Set(ee)],warnings:[...new Set(ww)],cash:nextCash};
      steps.push(step);errors.push(...ee);warnings.push(...ww);
      if(!ee.length){roster=nextRoster;cash=nextCash;}
    }
    if(draft.length){
      if(bounds.dateOnly)warnings.push('Исторические часы замен условные: модельный остаток ходов НЕ подтверждён. Сверьте реальную квоту Sports.ru.');
      warnings.push('Сверьте фактические цены и доступность карточек на Sports.ru перед реальным ходом');
      warnings.push('Точный момент сброса недельной квоты не подтверждён; используйте реальный счётчик Sports.ru');
      if(input?.scheduleVerified!==true)warnings.push('Не подтверждена полнота и свежесть UTC-календаря');
    }
    const uniqErrors=[...new Set(errors)],uniqWarnings=[...new Set(warnings)];
    return {valid:!uniqErrors.length,verified:!uniqErrors.length&&!uniqWarnings.length,
      requiresCheck:uniqWarnings.length>0,errors:uniqErrors,warnings:uniqWarnings,
      steps,roster,cash,used,alternateQuotaWeeks:alternate,
      quotaUpperBounds:{monday15:upper15,monday00:upper00},
      quotaHistoryDateOnly:bounds.dateOnly,quotaHistoryInvalid:bounds.invalid,
      historicalQuotaConflict,
      quotaResetVerified:false,quotaAssumptions:['monday_15_MSK','monday_00_MSK']};
  }
  return {weekKey,calendarWeekEnd,checkRoster,validate,historicalWeekBounds};
});
