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
  function weekKey(epoch,resetHour=0){
    if(!Number.isFinite(epoch))return null;
    const d=new Date(epoch+3*HOUR-resetHour*HOUR);
    if(!Number.isFinite(d.getTime()))return null;
    const day=(d.getUTCDay()+6)%7;
    d.setUTCDate(d.getUTCDate()-day);
    return d.toISOString().slice(0,10);
  }
  function calendarWeekEnd(epoch){
    const key=weekKey(epoch);
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
  function validate(input){
    const players=input?.players||{},draft=Array.isArray(input?.draft)?input.draft:[];
    const executed=Array.isArray(input?.executed)?input.executed:[];
    const schedule=validGames(input?.games);
    const errors=[],warnings=[],steps=[];
    let roster=[...(Array.isArray(input?.roster)?input.roster:[])],cash=price(input?.cash);
    if(!Number.isFinite(cash)){errors.push('Неизвестная или отрицательная касса');cash=0;}
    const used={},alternate={};
    // These are competing hypotheses, NOT verified Sports.ru reset clocks.
    // A draft is definitively over quota only when BOTH hypotheses fail.
    let midnightEverExceeded=false, fifteenEverExceeded=false;
    for(const move of executed){
      const key=weekKey(move?.epoch),alt=weekKey(move?.epoch,15);
      if(!key||!alt){warnings.push('В истории есть операция без подтверждённой даты');continue;}
      used[key]=(used[key]||0)+1;
      alternate[alt]=(alternate[alt]||0)+1;
    }
    midnightEverExceeded=Object.values(used).some(n=>n>3);
    fifteenEverExceeded=Object.values(alternate).some(n=>n>3);
    if(draft.length&&!schedule.length)warnings.push('Нет расписания матчей: блокировки не проверены');
    const now=Number.isFinite(input?.nowEpoch)?input.nowEpoch:Date.now();
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
      const key=weekKey(stamp),alt=weekKey(stamp,15);
      if(key){used[key]=(used[key]||0)+1;
        if(used[key]>3)midnightEverExceeded=true;
      }
      if(alt){alternate[alt]=(alternate[alt]||0)+1;
        if(alternate[alt]>3)fifteenEverExceeded=true;
      }
      if(midnightEverExceeded&&fifteenEverExceeded)
        ee.push('Превышены три замены при обеих гипотезах сброса недельной квоты');
      else if(midnightEverExceeded||fifteenEverExceeded)
        ww.push('Разные варианты сброса квоты дают разные лимиты: проверьте фактический счётчик Sports.ru');
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
      warnings.push('Сверьте фактические цены и доступность карточек на Sports.ru перед реальным ходом');
      warnings.push('Время сброса лимита замен не подтверждено; используйте реальный счётчик Sports.ru');
      if(input?.scheduleVerified!==true)warnings.push('Не подтверждена полнота и свежесть UTC-календаря');
    }
    const uniqErrors=[...new Set(errors)],uniqWarnings=[...new Set(warnings)];
    return {valid:!uniqErrors.length,verified:!uniqErrors.length&&!uniqWarnings.length,
      requiresCheck:uniqWarnings.length>0,errors:uniqErrors,warnings:uniqWarnings,
      steps,roster,cash,used,alternateQuotaWeeks:alternate,
      quotaResetVerified:false,quotaAssumptions:['monday_00_MSK','monday_15_MSK']};
  }
  return {weekKey,calendarWeekEnd,checkRoster,validate};
});