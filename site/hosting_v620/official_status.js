/* NBA Season Lab v6.3 — read-only official injury report observations.
 * No p_play/FP manipulation, no medical inference, no Firebase writes.
 * Uses only player/game IDs already resolved in the public GitHub research feed.
 */
(function(root, factory){
  'use strict';
  const api=factory();
  if(typeof module==='object' && module.exports) module.exports=api;
  root.NBAOfficialStatus=api;
})(typeof globalThis==='undefined'?this:globalThis, function(){
  'use strict';
  const STATUSES=new Set(['out','doubtful','questionable','probable','available']);
  const halfHour=30*60000;
  const hour=3600000;
  const SOURCE=/^https:\/\/ak-static\.cms\.nba\.com\/referee\/injury\/Injury-Report_20\d\d-\d\d-\d\d_\d\d_\d\d(?:AM|PM)\.pdf$/i;
  const isoTime=s=>typeof s==='string'&&/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(s)&&Number.isFinite(Date.parse(s))?Date.parse(s):NaN;
  function validate(feed){
    if(!feed || feed.schema_version!==1 || feed.status!=='research_only_not_deployed' || !Array.isArray(feed.events) || feed.events.length>2500){
      return {ok:false,reason:'Неподдерживаемый или отсутствующий файл официальных статусов'};
    }
    const updated=isoTime(feed.updated_at_utc);
    if(!Number.isFinite(updated))return {ok:false,reason:'Отсутствует время обновления статусов'};
    return {ok:true,updatedAt:updated,raw:Math.max(0,Number(feed.raw_status_rows)||0),matched:Math.max(0,Number(feed.matched_count)||0)};
  }
  function select(feed,roster,players,at=Date.now(),windowHours=72){
    const quality=validate(feed);
    if(!quality.ok || !Array.isArray(roster) || !players || !Number.isFinite(at) || !(windowHours>0&&windowHours<=168))return [];
    const owned=new Set(roster),byGame=new Map();
    for(const e of feed.events){
      if(!e || !owned.has(e.player_id) || !players[e.player_id] || !STATUSES.has(e.status))continue;
      const p=players[e.player_id];
      // When Sports.ru has a more recent manual team override, do not attach a
      // report for an unrelated team to their current fantasy card.
      if(e.team!==p.team || typeof e.game_id!=='string' || !e.game_id.startsWith('espn_'))continue;
      if(!SOURCE.test(String(e.source_url||'')))continue;
      const first=isoTime(e.first_seen_at_utc),report=isoTime(e.report_at_utc),tip=isoTime(e.tipoff_utc);
      if(![first,report,tip].every(Number.isFinite))continue;
      // Point-in-time: a future report cannot be displayed before its arrival.
      // Anything seen after player lock is not actionable evidence.
      if(first>at || report>at || first>tip-halfHour || report>tip-halfHour || tip<=at || tip>at+windowHours*hour)continue;
      if(!/^[A-Z]{3}$/.test(String(e.home||''))||!/^[A-Z]{3}$/.test(String(e.away||'')))continue;
      if(e.team!==e.home&&e.team!==e.away)continue;
      const key=e.player_id+'|'+e.game_id;
      const previous=byGame.get(key);
      if(!previous || report>previous.reportEpoch || (report===previous.reportEpoch&&first>previous.firstSeenEpoch)){
        byGame.set(key,{
          playerId:e.player_id,playerName:p.name||e.player_id,team:e.team,
          status:e.status,gameId:e.game_id,home:e.home,away:e.away,
          tipoffEpoch:tip,firstSeenEpoch:first,reportEpoch:report,
          sourceUrl:e.source_url,ageHours:Math.max(0,(at-first)/hour),
          stale:at-first>12*hour
        });
      }
    }
    return [...byGame.values()].sort((a,b)=>a.tipoffEpoch-b.tipoffEpoch||a.playerName.localeCompare(b.playerName,'ru'));
  }
  function forGame(feed,player,game,players,at=Date.now()){
    if(!player?.id||!game?.id||!Number.isFinite(game.epoch)||!players)return null;
    const report=select(feed,[player.id],players,at,72).find(e=>
      e.gameId===game.id && !e.stale && e.team===player.team &&
      e.home===game.home && e.away===game.away &&
      Math.abs(e.tipoffEpoch-game.epoch)<=60000);
    return report||null;
  }
  function translate(status){
    return ({out:'OUT · не сыграет по отчёту',doubtful:'Doubtful · маловероятен',
      questionable:'Questionable · под вопросом',probable:'Probable · вероятен',
      available:'Available · доступен по отчёту'})[status]||'Статус неизвестен';
  }
  function isHighRisk(status){return ['out','doubtful','questionable'].includes(status);}
  return {validate,select,forGame,translate,isHighRisk};
});
