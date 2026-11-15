/* NBA Season Lab v6.12 -- opt-in, local-only prospective decision journal.
 * Freezes observed KEEP / NOW / LATER scenario inputs at a real user click.
 * Does not claim authentic Sports.ru quotes, PIT model issuance, actual
 * execution, or economic gain. Never writes to Firebase or remote APIs.
 */
(function(root, factory){
 'use strict';
 const api=factory(()=>Date.now());
 if(typeof module==='object'&&module.exports)module.exports={...api,_makeForTests:factory};
 root.NBADecisionJournal=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(nowMs){
 'use strict';
 const KEY='nba-season-lab-local-decision-journal-v1';
 const MAX=100,MAX_ROUTES=8,MAX_MOVES=4,DAY=86400000;
 const ID=/^n[0-9]{3,5}$/;
 const STATUS='owner_clicked_predecision_snapshot_unverified';

 // Optional as-of schedule envelope. Existing v1 journals remain readable.
 // This is owner-clicked, not independently witnessed or Sports.ru-attested.
 const SLATE_STATUS='owner_clicked_model_schedule_unverified';
 const TEAM=/^[A-Z]{3}$/;
 const MAX_GAMES=330,MAX_DRAFT=12,LOCK=30*60000;
 function involvedIds(e){
  const ids=new Set(e.owner_state.roster_ids);
  for(const r of e.scenario.routes)for(const m of r.moves){ids.add(m.out);ids.add(m.in_);}
  for(const m of e.frozen_slate?.existing_draft_unexecuted||[]){ids.add(m.out);ids.add(m.in_);}
  return ids;
 }
 function validateSlate(e){
  const s=e.frozen_slate;
  if(s===undefined)return;
  ensure(s&&s.schema_version===1&&s.status===SLATE_STATUS&&
    s.source_independently_verified===false&&s.sportsru_credited_fp_verified===false&&
    Array.isArray(s.games)&&s.games.length>=1&&s.games.length<=MAX_GAMES&&
    Array.isArray(s.existing_draft_unexecuted)&&s.existing_draft_unexecuted.length<=MAX_DRAFT&&
    s.player_teams_at_capture&&typeof s.player_teams_at_capture==='object'&&
    !Array.isArray(s.player_teams_at_capture),'BAD_FROZEN_SLATE');
  const observed=instant(s.observed_calendar_updated_at_utc);
  const captured=instant(e.captured_at_utc);
  ensure(Number.isFinite(observed)&&observed<=captured&&captured-observed<=72*3600000,
    'BAD_FROZEN_SLATE_CALENDAR_AGE');
  const ids=involvedIds(e),teamMap=s.player_teams_at_capture;
  ensure(Object.keys(teamMap).length===ids.size&&
    [...ids].every(id=>ID.test(id)&&TEAM.test(teamMap[id])),'BAD_FROZEN_SLATE_PLAYERS');
  const start=instant(e.decision_start_utc),end=instant(e.decision_end_utc);
  for(const m of s.existing_draft_unexecuted){
   const at=instant(m.execution_utc);
   ensure(ID.test(m.out)&&ID.test(m.in_)&&m.out!==m.in_&&
      Number.isFinite(at)&&at>=Date.parse('2026-10-19T00:00:00Z')&&at<end&&
      isNum(m.assumed_sell)&&m.assumed_sell>=0&&
      isNum(m.assumed_buy)&&m.assumed_buy>=0,'BAD_FROZEN_SLATE_DRAFT');
  }
  let previous=-Infinity;const seen=new Set(),clubs=new Set(Object.values(teamMap));
  for(const g of s.games){
   const at=instant(g.tipoff_utc);
   ensure(/^espn_[0-9]+$/.test(g.id||'')&&TEAM.test(g.home)&&TEAM.test(g.away)&&
      g.home!==g.away&&Number.isFinite(at)&&at>=start&&at<end&&
      at>=previous&&!seen.has(g.id)&&
      (clubs.has(g.home)||clubs.has(g.away)), 'BAD_FROZEN_SLATE_GAME');
   seen.add(g.id);previous=at;
  }
 }
 function buildSlate(src,e){
  if(src===null||src===undefined)return undefined; // Backward-compatible pure API.
  ensure(src&&src.ownerClickedVerifiedCalendar===true&&
     Array.isArray(src.games)&&Array.isArray(src.existingDraft)&&
     src.playerTeams&&typeof src.playerTeams==='object','BAD_SLATE_INPUT');
  const draft=src.existingDraft.map(m=>({out:m.out,in_:m.in_,
    execution_utc:stamp(m.epoch),assumed_sell:m.sell,assumed_buy:m.buy}));
  const games=src.games.map(g=>({id:g.id,tipoff_utc:stamp(g.epoch),home:g.home,away:g.away}))
    .sort((a,b)=>instant(a.tipoff_utc)-instant(b.tipoff_utc)||a.id.localeCompare(b.id));
  const slate={schema_version:1,status:SLATE_STATUS,
   observed_calendar_updated_at_utc:src.calendarUpdatedAtUtc,
   player_teams_at_capture:clone(src.playerTeams),
   existing_draft_unexecuted:draft,games,
   source_independently_verified:false,sportsru_credited_fp_verified:false};
  e.frozen_slate=slate;
  validateSlate(e);
  return slate;
 }
 // Coverage, not a realized gain. Missing rows remain UNKNOWN, never DNP/zero.
 // Any future Sports.ru credited player-game evaluation is independent work.
 function inspectCoverage(entry,live,options={}){
  const no=(status,extra={})=>({status,real_sportsru_gain_proven:false,
    official_credited_fp_available:false,actual_gain_fp:null,...extra});
  if(!entry||!Number.isFinite(instant(entry.decision_end_utc)))return no('INVALID_ENTRY');
  const t=options.nowMs;
  if(!isNum(t))return no('INVALID_CLOCK');
  if(t<instant(entry.decision_end_utc))return no('PENDING_HORIZON',
    {end_utc:entry.decision_end_utc});
  if(!entry.frozen_slate)return no('LEGACY_NO_FROZEN_SLATE');
  validateSlate(entry);
  if(options.sourceVerified!==true||live?.mode!=='live_sync'||
      !Array.isArray(live.games)||!Array.isArray(live.rows))return no('SOURCE_UNVERIFIED');
  const byGame=new Map(),byRow=new Map();
  for(const g of live.games){
   if(!g?.id)continue;
   if(byGame.has(g.id))return no('DUPLICATE_PUBLIC_GAME');
   byGame.set(g.id,g);
  }
  for(const r of live.rows){
   if(!r?.game_id||!r?.id)continue;
   const key=r.game_id+'|'+r.id;
   if(byRow.has(key))return no('DUPLICATE_PUBLIC_PLAYER_GAME');
   byRow.set(key,r);
  }
  let finals=0,missingGames=0,changedGames=0;
  const relevant=new Set(entry.frozen_slate.games.map(g=>g.id));
  for(const g of entry.frozen_slate.games){
   const actual=byGame.get(g.id);
   if(!actual){missingGames++;continue;}
   if(actual.home!==g.home||actual.away!==g.away||
     !isNum(actual.epoch)||Math.abs(actual.epoch-instant(g.tipoff_utc))>60000){
     changedGames++;continue;
   }
   if(actual.status==='final')finals++;
  }
  if(changedGames)return no('SCHEDULE_CHANGED_AFTER_CAPTURE',
    {changed_games:changedGames,scheduled_games:relevant.size});
  // A player may have changed clubs after this prediction. A played row on
  // another team (or without a verifiable team label) must NOT be credited
  // to the frozen roster in a hypothetical ex-post comparison.
  const frozenTeams=entry.frozen_slate.player_teams_at_capture;
  for(const r of live.rows){
   if(!relevant.has(r?.game_id)||!Object.prototype.hasOwnProperty.call(frozenTeams,r?.id)||
      r.played!==true||byGame.get(r.game_id)?.status!=='final')continue;
   const match=byGame.get(r.game_id),expectedTeam=frozenTeams[r.id];
   if(r.team!==expectedTeam || (r.team!==match.home&&r.team!==match.away)){
    return no('PLAYER_CLUB_TENURE_CONFLICT',{
     unmatched_player_game_club:true,
     caution:'Observed NBA team disagrees with the at-click club mapping; do not score this hypothetical roster.'});
   }
  }
  const allRoutes=[];
  for(const route of entry.scenario.routes){
   const moves=[...entry.frozen_slate.existing_draft_unexecuted,...route.moves]
     .sort((a,b)=>instant(a.execution_utc)-instant(b.execution_utc));
   let expected=0,played=0,unknown=0,observed=0;
   for(const g of entry.frozen_slate.games){
    if(byGame.get(g.id)?.status!=='final')continue;
    let owned=entry.owner_state.roster_ids.slice();
    for(const m of moves){
     // At T-30m the player is already locked. Do not invent an
     // execution exactly on the lock boundary as valid ownership.
     if(instant(m.execution_utc)>=instant(g.tipoff_utc)-LOCK)break;
     const i=owned.indexOf(m.out);
     if(i<0||owned.includes(m.in_))return no('UNVERIFIED_OWNERSHIP_PATH',{
      caution:'A scenario move cannot be applied to the frozen roster in its modelled order.'});
     owned[i]=m.in_;
    }
    if(new Set(owned).size!==owned.length)return no('UNVERIFIED_OWNERSHIP_PATH');
    for(const id of owned){
     const team=entry.frozen_slate.player_teams_at_capture[id];
     if(team!==g.home&&team!==g.away)continue;
     expected++;
     const r=byRow.get(g.id+'|'+id);
     if(r?.played===true&&isNum(r.fp)){played++;observed+=r.fp;}
     else unknown++; // No row != zero and != verified DNP.
    }
   }
   allRoutes.push({kind:route.kind,expected_player_games_on_final_games:expected,
      observed_played_rows:played,unknown_or_dnp_rows:unknown,
      nba_played_fp_partial_not_official:observed,
      comparable_full_fantasy_outcome_proven:false});
  }
  const incomplete=missingGames>0||finals!==relevant.size||allRoutes.some(r=>r.unknown_or_dnp_rows>0);
  return no(incomplete?'INCOMPLETE_PUBLIC_OUTCOMES':'NBA_PLAYED_ROWS_ONLY_NOT_OFFICIAL',{
   frozen_games:relevant.size,final_games_matched:finals,missing_games:missingGames,
   routes:allRoutes,selected_index:entry.scenario.chosen_index,
   comparable_actual_net_fp_proven:false,
   caution:'NBA played rows cannot substitute for full Sports.ru credited FP or independently verified executed transfers.'});
 }
 // Sparse prospective evidence request: roster exposures identical to KEEP
 // cancel. This is NOT an outcome, price verification, or official FP replay.
 // The frozen model schedule and hypothetical transfer times still require
 // source verification before any credited Sports.ru comparison is accepted.
 function differentialEvidence(entry){
  const no=(status,extra={})=>({schema_version:1,status,
   credit_evidence_verified:false,actual_gain_fp:null,
   economic_benefit_proven:false,verified_transfer_execution:false,...extra});
  if(!entry||!entry.frozen_slate)return no('LEGACY_NO_FROZEN_SLATE');
  validateSlate(entry);
  const routes=entry?.scenario?.routes;
  if(!Array.isArray(routes)||!Array.isArray(entry.owner_state?.roster_ids))
   return no('INVALID_ENTRY');
  const ki=routes.findIndex(r=>r.kind==='keep'&&r.moves.length===0);
  if(ki<0)return no('KEEP_NOT_FOUND');
  const draft=entry.frozen_slate.existing_draft_unexecuted;
  const teamMap=entry.frozen_slate.player_teams_at_capture;
  const games=entry.frozen_slate.games;
  const ownAt=(moves,g)=>{
   const cutoff=instant(g.tipoff_utc)-LOCK;
   const owned=entry.owner_state.roster_ids.slice();
   for(const m of moves){
    if(instant(m.execution_utc)>=cutoff)break;
    const index=owned.indexOf(m.out);
    if(index<0||owned.includes(m.in_))return null;
    owned[index]=m.in_;
   }
   return new Set(owned).size===owned.length?owned:null;
  };
  const sortedMoves=route=>[...draft,...route.moves].sort((a,b)=>
   instant(a.execution_utc)-instant(b.execution_utc));
  const keepMoves=sortedMoves(routes[ki]);
  const out=[],unique=new Map();
  for(let i=0;i<routes.length;i++){
   const route=routes[i];
   const needed=[];
   if(i!==ki){
    const moves=sortedMoves(route);
    for(const g of games){
     const k=ownAt(keepMoves,g),v=ownAt(moves,g);
     if(!k||!v)return no('UNVERIFIED_OWNERSHIP_PATH',
      {blocked_route_index:i,blocked_game_id:g.id});
     const ks=new Set(k),vs=new Set(v);
     // Only player-game rows that differ in hypothetical ownership survive.
     for(const id of new Set([...k,...v])){
      if(ks.has(id)===vs.has(id))continue;
      const frozenTeam=teamMap[id];
      if(!frozenTeam)return no('UNKNOWN_FROZEN_PLAYER_CLUB');
      if(frozenTeam!==g.home&&frozenTeam!==g.away)continue;
      const record={game_id:g.id,tipoff_utc:g.tipoff_utc,
       home:g.home,away:g.away,player_id:id,frozen_team:frozenTeam,
       in_keep:ks.has(id),in_variant:vs.has(id),
       sportsru_credited_fp:null,verified_played_or_dnp:false,
       official_source_receipt:null};
      needed.push(record);
      const key=g.id+'|'+id;
      if(!unique.has(key))unique.set(key,{game_id:g.id,tipoff_utc:g.tipoff_utc,
       home:g.home,away:g.away,player_id:id,frozen_team:frozenTeam,
       sportsru_credited_fp:null,verified_played_or_dnp:false,
       official_source_receipt:null});
     }
    }
   }
   out.push({route_index:i,kind:route.kind,
    selected:i===entry.scenario.chosen_index,
    vs_keep_differential_player_games:needed.length,
    requirements:needed});
  }
  const selected=out[entry.scenario.chosen_index];
  return no('FROZEN_MODEL_REQUEST_NOT_OFFICIAL',{
   captured_at_utc:entry.captured_at_utc,
   decision_start_utc:entry.decision_start_utc,
   decision_end_utc:entry.decision_end_utc,
   horizon_days:entry.scenario.horizon_days,keep_route_index:ki,
   selected_route_index:entry.scenario.chosen_index,
   selected_vs_keep_rows:selected?.vs_keep_differential_player_games??null,
   all_routes_unique_player_games:unique.size,
   all_routes_requests:out,
   unique_sportsru_credit_requests:[...unique.values()],
   frozen_calendar_verified:false,frozen_club_tenure_verified:false,
   prices_and_actual_execution_verified:false,
   caution:'These are minimal model-schedule player-game credit requests relative to KEEP, not actual Sports.ru scores, DNP proof, transactions, or verified gains. Confirm match schedules, club tenure, T-30 locks, transfers, quotes, and weekly quota independently.'});
 }
 // Read-only, decision-level coverage audit; no economic score or inferred DNP.
 // Time-overlapping horizons are clustered, never sold as independent wins.
 function auditCoverage(journal,live,options={}){
  ensure(isNum(options.nowMs),'AUDIT_CLOCK_REQUIRED');
  validate(journal); // Do not repair or drop invalid personal records.
  const classes=['pending','nba_rows_only','partial_nba','source_unverified','legacy','blocked'];
  const counts=Object.fromEntries(classes.map(k=>[k,0]));
  const entries=journal.entries.map((e,index)=>{
   const coverage=inspectCoverage(e,live,options);
   const status=coverage.status;
   const category=status==='PENDING_HORIZON'?'pending':
      status==='NBA_PLAYED_ROWS_ONLY_NOT_OFFICIAL'?'nba_rows_only':
      status==='INCOMPLETE_PUBLIC_OUTCOMES'?'partial_nba':
      status==='SOURCE_UNVERIFIED'?'source_unverified':
      status==='LEGACY_NO_FROZEN_SLATE'?'legacy':'blocked';
   counts[category]++;
   const chosen=e.scenario.routes[e.scenario.chosen_index];
   const route=coverage.routes?.[e.scenario.chosen_index];
   return {index,captured_at_utc:e.captured_at_utc,
    decision_start_utc:e.decision_start_utc,decision_end_utc:e.decision_end_utc,
    horizon_days:e.scenario.horizon_days,chosen_kind:chosen.kind,
    predicted_gain_model_fp:chosen.gain_fp,category,status,
    final_games_matched:coverage.final_games_matched??null,
    frozen_games:coverage.frozen_games??e.frozen_slate?.games.length??null,
    selected_expected_on_final_games:route?.expected_player_games_on_final_games??null,
    selected_nba_played_rows:route?.observed_played_rows??null,
    unknown_or_dnp_rows:route?.unknown_or_dnp_rows??null,
    real_sportsru_gain_proven:false,actual_gain_fp:null};
  });
  let nonoverlapGroups=0,overlappingEntries=0,lastEnd=-Infinity;
  for(const e of [...entries].sort((a,b)=>instant(a.decision_start_utc)-instant(b.decision_start_utc))){
   const start=instant(e.decision_start_utc),end=instant(e.decision_end_utc);
   if(start>=lastEnd)nonoverlapGroups++;
   else overlappingEntries++;
   lastEnd=Math.max(lastEnd,end);
  }
  return {schema_version:1,status:'private_observational_coverage_only',
   total:entries.length,counts,nonoverlap_time_groups:nonoverlapGroups,
   overlapping_decisions:overlappingEntries,
   groups_not_statistical_independence:true,
   sportsru_credited_player_game_results_available:false,
   proven_economic_wins:0,proven_economic_losses:0,
   winning_strategy_proven:false,entries};
 }
 const isNum=n=>typeof n==='number'&&Number.isFinite(n);
 const fail=code=>{throw new Error('DECISION_JOURNAL_'+code);};
 const ensure=(okay,code)=>{if(!okay)fail(code);};
 const clone=x=>JSON.parse(JSON.stringify(x));
 function instant(value){
   if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value))return NaN;
   const t=Date.parse(value);
   return Number.isFinite(t)?t:NaN;
 }
 function stamp(ms){
   ensure(Number.isSafeInteger(ms)&&ms>=Date.parse('2026-10-19T00:00:00Z')&&
     ms<Date.parse('2027-07-01T00:00:00Z'),'BROWSER_CLOCK_OUT_OF_SEASON');
   return new Date(ms).toISOString();
 }
 function empty(){
   return {schema_version:1,private_local_only:true,never_autosync:true,
     not_sportsru_attested:true,not_cryptographic_proof:true,entries:[]};
 }
 function validate(journal){
   ensure(journal&&journal.schema_version===1&&journal.private_local_only===true&&
     journal.never_autosync===true&&journal.not_sportsru_attested===true&&
     journal.not_cryptographic_proof===true&&Array.isArray(journal.entries)&&
     journal.entries.length<=MAX,'BAD_LOCAL_ARCHIVE');
   let last=-1;
   for(const e of journal.entries){
     ensure(e?.schema_version===1&&e?.status===STATUS&&
       e?.user_clicked_to_record===true&&e?.private_local_only===true&&
       e?.never_autosync===true&&e?.no_sportsru_transfer_executed===true&&
       e?.model_was_not_retrained===true&&e?.outcome?.status==='not_yet_independently_scored'&&
       e?.outcome?.actual_gain_fp===null&&e?.outcome?.real_transfer_benefit_proven===false,
       'MODIFIED_OR_UNTRUSTED_ENTRY');
     const t=instant(e.captured_at_utc);
     ensure(Number.isFinite(t)&&t>last,'CAPTURE_CLOCKS_NOT_STRICT');
     last=t;
     const s=e?.scenario;
     ensure(s&&[7,14,21,28].includes(s.horizon_days)&&
       isNum(s.baseline_fp)&&Array.isArray(s.routes)&&
       s.routes.length>=1&&s.routes.length<=MAX_ROUTES&&
       Number.isInteger(s.chosen_index)&&s.chosen_index>=0&&
       s.chosen_index<s.routes.length,'MODIFIED_SCENARIO');
     ensure(Array.isArray(e.owner_state?.roster_ids)&&e.owner_state.roster_ids.length===10&&
       e.owner_state.roster_ids.every(id=>typeof id==='string'&&ID.test(id))&&
       new Set(e.owner_state.roster_ids).size===10&&
       isNum(e.owner_state.cash_scenario)&&e.owner_state.cash_scenario>=0,
       'MODIFIED_PRIVATE_BASELINE');
     ensure(Number.isFinite(instant(e.decision_start_utc))&&
       Number.isFinite(instant(e.decision_end_utc))&&
       instant(e.decision_start_utc)>=t-60000&&
       instant(e.decision_end_utc)>instant(e.decision_start_utc)&&
       instant(e.decision_end_utc)-instant(e.decision_start_utc)===s.horizon_days*DAY,
       'MODIFIED_DECISION_CLOCK');
     for(const route of s.routes){
       ensure(['keep','now','later','multi_slot','same_slot_chain'].includes(route.kind)&&
         isNum(route.gain_fp)&&isNum(route.net_fp)&&
         Array.isArray(route.moves)&&route.moves.length<=MAX_MOVES,
         'MODIFIED_ROUTE');
       ensure((route.kind==='keep')===(route.moves.length===0),'ROUTE_NOT_KEEP_CONSISTENT');
       for(const m of route.moves){
         ensure(ID.test(m.out)&&ID.test(m.in_)&&m.out!==m.in_&&
           Number.isFinite(instant(m.execution_utc))&&
           instant(m.execution_utc)>=instant(e.decision_start_utc)&&
           instant(m.execution_utc)<instant(e.decision_end_utc)&&
           isNum(m.assumed_sell)&&m.assumed_sell>=0&&
           isNum(m.assumed_buy)&&m.assumed_buy>=0,
           'MODIFIED_MOVE');
       }
     }
     ensure(s.routes.some(r=>r.kind==='keep'),'NO_KEEP_COMPARISON');
     validateSlate(e);
   }
   return journal;
 }
 function read(storage){
   ensure(storage&&typeof storage.getItem==='function','NO_STORAGE');
   const raw=storage.getItem(KEY);
   if(raw===null)return empty();
   let parsed;
   try{parsed=JSON.parse(raw);}catch{fail('INVALID_JSON');}
   return clone(validate(parsed));
 }
 function take(storage,input){
   ensure(input?.userConfirmedNow===true,'CLICK_REQUIRED');
   const ms=nowMs(),capturedAt=stamp(ms);
   const p=input.plan;
   ensure(p?.ready===true&&[7,14,21,28].includes(p.horizonDays)&&
     isNum(p.start)&&isNum(p.end)&&p.end>p.start&&
     p.start>=ms-60000&&p.end-p.start===p.horizonDays*DAY&&isNum(p.baseline),
     'NO_CURRENT_PROSPECTIVE_PLAN');
   const roster=input.roster;
   ensure(Array.isArray(roster)&&roster.length===10&&
     roster.every(id=>typeof id==='string'&&ID.test(id))&&
     new Set(roster).size===10,'INVALID_ROSTER');
   ensure(isNum(input.cash)&&input.cash>=0,'INVALID_CASH');
   ensure(Array.isArray(p.routes)&&p.routes.length>=1&&p.routes.length<=MAX_ROUTES&&
     Number.isInteger(input.chosenIndex)&&input.chosenIndex>=0&&
     input.chosenIndex<p.routes.length,'INVALID_ROUTE_CHOICE');
   const src=typeof input.liveUpdatedAtUtc==='string'?input.liveUpdatedAtUtc:null;
   const srcMs=src===null?NaN:instant(src);
   ensure(src===null||Number.isFinite(srcMs)&&srcMs<=ms,
     'FUTURE_OR_INVALID_LIVE_SOURCE');
   const normalized=[];
   for(const r of p.routes){
     ensure(r&&['keep','now','later','multi_slot','same_slot_chain'].includes(r.kind)&&
       isNum(r.gain)&&isNum(r.net)&&Array.isArray(r.moves)&&
       r.moves.length<=MAX_MOVES,'INVALID_ROUTE');
     ensure((r.kind==='keep')===(r.moves.length===0),'INVALID_KEEP_ROUTE');
     const normalizedMoves=[];
     for(const m of r.moves){
       ensure(m&&ID.test(m.out)&&ID.test(m.in_)&&m.out!==m.in_&&
         isNum(m.epoch)&&m.epoch>=p.start&&m.epoch<p.end&&
         isNum(m.sell)&&m.sell>=0&&isNum(m.buy)&&m.buy>=0,
         'INVALID_MOVE_OR_PRICE');
       normalizedMoves.push({out:m.out,in_:m.in_,execution_utc:stamp(m.epoch),
         assumed_sell:m.sell,assumed_buy:m.buy,
         prices_independently_verified:false});
     }
     normalized.push({kind:r.kind,gain_fp:r.gain,net_fp:r.net,
       hypothetical_not_observed_gain:true,moves:normalizedMoves});
   }
   ensure(normalized.some(r=>r.kind==='keep'),'MISSING_KEEP');
   const journal=read(storage);
   const prev=journal.entries.at(-1);
   ensure(!prev||instant(prev.captured_at_utc)<ms,'CLOCK_NOT_MONOTONE');
   ensure(journal.entries.length<MAX,'JOURNAL_FULL_EXPORT_FIRST');
   const entry={schema_version:1,status:STATUS,user_clicked_to_record:true,
     private_local_only:true,never_autosync:true,
     captured_at_utc:capturedAt,decision_start_utc:stamp(p.start),
     decision_end_utc:stamp(p.end),
     observed_public_feed_updated_at_utc:src,
     public_feed_freshness_proven:src!==null&&ms-srcMs<=4*3600000,
     frozen_original_model_issue_proven:false,
     owner_state:{roster_ids:[...roster],cash_scenario:input.cash,
       real_sportsru_account_independently_verified:false},
     scenario:{horizon_days:p.horizonDays,baseline_fp:p.baseline,
       chosen_index:input.chosenIndex,routes:normalized},
     outcome:{status:'not_yet_independently_scored',actual_gain_fp:null,
       real_transfer_benefit_proven:false,needs_sportsru_credited_player_games:true},
     no_sportsru_transfer_executed:true,model_was_not_retrained:true,
     caution:'Owner-clicked local observation, not independent source publication time or proof of real transfer advantage.'};
   buildSlate(input.slate,entry);
   const next={...journal,entries:[...journal.entries,entry]};
   validate(next);
   ensure(typeof storage.setItem==='function','NO_STORAGE_WRITE');
   try{storage.setItem(KEY,JSON.stringify(next));}
   catch{fail('STORAGE_WRITE_FAILED');}
   return clone(entry);
 }
 function exportData(storage){return read(storage);}
 function clear(storage,explicit){
   ensure(explicit===true,'EXPLICIT_ERASE_REQUIRED');
   ensure(storage&&typeof storage.removeItem==='function','NO_STORAGE');
   storage.removeItem(KEY);
 }
 return {KEY,read,take,exportData,clear,inspectCoverage,auditCoverage,differentialEvidence,_status:STATUS};
});
