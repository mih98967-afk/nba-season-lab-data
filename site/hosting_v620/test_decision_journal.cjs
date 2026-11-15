const test=require('node:test'), assert=require('node:assert/strict');
const j=require('./decision_journal.js');
const NOW=Date.parse('2026-11-01T09:00:00Z'),DAY=86400000;
const roster=Array.from({length:10},(_,i)=>'n'+String(i+101));
const local=()=>{const m=new Map();return {getItem:k=>m.has(k)?m.get(k):null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k),store:m};};
const fixture=()=>({userConfirmedNow:true,roster:[...roster],cash:850,liveUpdatedAtUtc:'2026-11-01T06:09:10Z',chosenIndex:1,
 plan:{ready:true,horizonDays:14,start:NOW+60000,end:NOW+14*DAY+60000,baseline:650,routes:[
  {kind:'keep',gain:0,net:0,moves:[]},
  {kind:'now',gain:25.5,net:21.5,moves:[{out:'n101',in_:'n222',epoch:NOW+60000,sell:1345,buy:1200}]},
  {kind:'later',gain:14.2,net:10.2,moves:[{out:'n101',in_:'n222',epoch:NOW+2*DAY,sell:1345,buy:1200}]}
 ]}});
const engine=(ms=NOW)=>j._makeForTests(()=>ms);
test('seven-day KEEP/NOW/LATER comparison can be frozen before games',()=>{
 const store=local(),a=engine(),x=fixture();
 x.plan.horizonDays=7;x.plan.end=x.plan.start+7*DAY;
 const frozen=a.take(store,x);
 assert.equal(frozen.scenario.horizon_days,7);
 assert.equal(frozen.scenario.routes.length,3);
 assert.equal(frozen.outcome.actual_gain_fp,null);
 assert.equal(a.read(store).entries[0].scenario.horizon_days,7);
 assert.equal(store.store.size,1);
});
test('wrong seven-day end must fail, never freeze a mismatched horizon',()=>{
 const store=local(),a=engine(),x=fixture();
 x.plan.horizonDays=7;
 assert.throws(()=>a.take(store,x),/NO_CURRENT_PROSPECTIVE_PLAN/);
 assert.equal(store.store.size,0);
});
test('retrospectively edited horizon is rejected as untrusted',()=>{
 const store=local(),a=engine(),x=fixture();a.take(store,x);
 const raw=JSON.parse(store.store.get(j.KEY));
 raw.entries[0].scenario.horizon_days=7;
 store.store.set(j.KEY,JSON.stringify(raw));
 assert.throws(()=>a.read(store),/MODIFIED_DECISION_CLOCK/);
});
test('nothing is stored until the owner explicitly clicks',()=>{
 const s=local(),a=engine();assert.equal(a.read(s).entries.length,0);
 const x=fixture();delete x.userConfirmedNow;
 assert.throws(()=>a.take(s,x),/CLICK_REQUIRED/);
 assert.equal(s.store.size,0);
});
test('freeze all alternatives and preserve immutable as-of times locally only',()=>{
 const s=local(),a=engine(),x=fixture();
 const frozen=a.take(s,x);assert.equal(frozen.scenario.routes.length,3);
 assert.equal(frozen.scenario.chosen_index,1);
 assert.equal(frozen.scenario.routes[1].gain_fp,25.5);
 assert.equal(frozen.outcome.actual_gain_fp,null);
 assert.equal(frozen.public_feed_freshness_proven,true);
 assert.equal(frozen.no_sportsru_transfer_executed,true);
 assert.equal(frozen.frozen_original_model_issue_proven,false);
 x.plan.routes[1].gain=999;x.roster[0]='n999';
 assert.equal(a.read(s).entries[0].scenario.routes[1].gain_fp,25.5);
 assert.equal(a.read(s).entries[0].owner_state.roster_ids[0],'n101');
 assert.equal(s.store.size,1);
});
test('a missing LIVE source is marked unknown rather than manufactured freshness',()=>{
 const s=local(),a=engine(),x=fixture();x.liveUpdatedAtUtc=null;
 const frozen=a.take(s,x);assert.equal(frozen.public_feed_freshness_proven,false);
 assert.equal(frozen.observed_public_feed_updated_at_utc,null);
});
test('source from the future cannot be frozen as known',()=>{
 const s=local(),a=engine(),x=fixture();x.liveUpdatedAtUtc='2026-11-01T09:00:01.000Z';
 assert.throws(()=>a.take(s,x),/FUTURE_OR_INVALID_LIVE_SOURCE/);
});
test('decisions in the past are rejected rather than reissued',()=>{
 const s=local(),a=engine(),x=fixture();x.plan.start=NOW-2*60000;
 assert.throws(()=>a.take(s,x),/NO_CURRENT_PROSPECTIVE_PLAN/);
});
test('unknown FP is refused, never changed into zero',()=>{
 const s=local(),a=engine(),x=fixture();x.plan.routes[1].gain=null;
 assert.throws(()=>a.take(s,x),/INVALID_ROUTE/);
});
test('missing KEEP is refused',()=>{
 const s=local(),a=engine(),x=fixture();x.plan.routes.shift();x.chosenIndex=0;
 assert.throws(()=>a.take(s,x),/MISSING_KEEP/);
});
test('future planned prices are explicitly NOT independently verified',()=>{
 const s=local(),a=engine();const e=a.take(s,fixture());
 assert.equal(e.scenario.routes[1].moves[0].prices_independently_verified,false);
 assert.equal(e.scenario.routes[2].moves[0].assumed_sell,1345);
});
test('repeating a capture at identical UTC millisecond is blocked',()=>{
 const s=local(),a=engine();a.take(s,fixture());
 assert.throws(()=>a.take(s,fixture()),/CLOCK_NOT_MONOTONE/);
});
test('sequential captures preserve history without overwriting prior decision',()=>{
 const s=local(),a=engine(),x=fixture();a.take(s,x);
 const later=engine(NOW+2*60000),y=fixture();y.plan.start=NOW+3*60000;
 y.plan.end=y.plan.start+14*DAY;
 y.plan.routes[1].moves[0].epoch=y.plan.start;
 later.take(s,y);
 assert.equal(later.read(s).entries.length,2);
 assert.equal(later.read(s).entries[0].scenario.routes[1].gain_fp,25.5);
});
test('corrupted archive is not silently accepted',()=>{
 const s=local(),a=engine();a.take(s,fixture());
 const raw=JSON.parse(s.store.get(j.KEY));raw.entries[0].outcome.real_transfer_benefit_proven=true;
 s.store.set(j.KEY,JSON.stringify(raw));
 assert.throws(()=>a.read(s),/MODIFIED_OR_UNTRUSTED_ENTRY/);
});
test('clear requires explicit owner action and touches only its own key',()=>{
 const s=local(),a=engine();a.take(s,fixture());s.store.set('sportsru_local_state','private data');
 assert.throws(()=>a.clear(s,false),/EXPLICIT_ERASE_REQUIRED/);
 a.clear(s,true);
 assert.equal(s.store.get('sportsru_local_state'),'private data');
 assert.equal(a.read(s).entries.length,0);
});

// PR168: prospective player/game schedule and actual NBA boxscore coverage.
const frozenFixture=()=>{
 const input=fixture();
 const teams=Object.fromEntries(roster.map(id=>[id,'AAA']));
 teams.n222='BBB';
 input.slate={ownerClickedVerifiedCalendar:true,
  calendarUpdatedAtUtc:'2026-11-01T08:00:00Z',playerTeams:teams,existingDraft:[],
  games:[{id:'espn_444',epoch:NOW+3*3600000,home:'AAA',away:'BBB'}]};
 return input;
};
test('freezes exact as-of player/team/fixture slate without certifying source',()=>{
 const s=local(),api=engine(),x=frozenFixture();
 const entry=api.take(s,x);
 assert.equal(entry.frozen_slate.status,'owner_clicked_model_schedule_unverified');
 assert.deepEqual(entry.frozen_slate.player_teams_at_capture,Object.fromEntries(roster.map(id=>[id,'AAA']).concat([['n222','BBB']])));
 assert.equal(entry.frozen_slate.games[0].id,'espn_444');
 assert.equal(entry.frozen_slate.source_independently_verified,false);
 assert.equal(entry.frozen_slate.sportsru_credited_fp_verified,false);
 x.slate.games[0].home='DUP';x.slate.playerTeams.n101='CCC';
 assert.equal(api.read(s).entries[0].frozen_slate.games[0].home,'AAA');
});
test('future games wait rather than becoming phantom outcomes',()=>{
 const api=engine(),s=local(),entry=api.take(s,frozenFixture());
 const data={mode:'live_sync',games:[],rows:[]};
 const result=api.inspectCoverage(entry,data,{nowMs:NOW+24*3600000,sourceVerified:true});
 assert.equal(result.status,'PENDING_HORIZON');
 assert.equal(result.actual_gain_fp,null);
});
test('NBA matched played rows are coverage only; an absent bought player is UNKNOWN not zero',()=>{
 const api=engine(),s=local(),entry=api.take(s,frozenFixture());
 const live={mode:'live_sync',games:[{id:'espn_444',home:'AAA',away:'BBB',epoch:NOW+3*3600000,status:'final'}],
  rows:[{id:'n101',game_id:'espn_444',played:true,fp:21,team:'AAA'}]};
 const status=api.inspectCoverage(entry,live,{nowMs:NOW+15*DAY,sourceVerified:true});
 assert.equal(status.status,'INCOMPLETE_PUBLIC_OUTCOMES');
 assert.equal(status.routes[0].expected_player_games_on_final_games,10);
 assert.equal(status.routes[0].observed_played_rows,1);
 assert.equal(status.routes[0].unknown_or_dnp_rows,9);
 assert.equal(status.routes[1].unknown_or_dnp_rows,10);
 assert.equal(status.actual_gain_fp,null);
 assert.equal(status.real_sportsru_gain_proven,false);
 assert.equal(status.official_credited_fp_available,false);
 live.rows.push({id:'n222',game_id:'espn_444',played:true,fp:55,team:'BBB'});
 const rerun=api.inspectCoverage(entry,live,{nowMs:NOW+15*DAY,sourceVerified:true});
 assert.equal(rerun.routes[1].unknown_or_dnp_rows,9);
 assert.equal(rerun.routes[1].nba_played_fp_partial_not_official,55);
 assert.equal(rerun.actual_gain_fp,null);
});
test('a fully played NBA slate is still NOT Sports.ru credited gain',()=>{
 const api=engine(),s=local(),entry=api.take(s,frozenFixture());
 const feed={mode:'live_sync',games:[{id:'espn_444',home:'AAA',away:'BBB',epoch:NOW+3*3600000,status:'final'}],
  rows:roster.map((id,i)=>({id,game_id:'espn_444',played:true,fp:i+1,team:'AAA'})).concat([{id:'n222',game_id:'espn_444',played:true,fp:50,team:'BBB'}])};
 const done=api.inspectCoverage(entry,feed,{nowMs:NOW+15*DAY,sourceVerified:true});
 assert.equal(done.status,'NBA_PLAYED_ROWS_ONLY_NOT_OFFICIAL');
 assert.equal(done.routes[0].unknown_or_dnp_rows,0);
 assert.equal(done.routes[1].unknown_or_dnp_rows,0);
 assert.equal(done.actual_gain_fp,null);
 assert.equal(done.comparable_actual_net_fp_proven,false);
});
test('moved schedule and unverified public feed fail closed',()=>{
 const api=engine(),s=local(),entry=api.take(s,frozenFixture());
 const live={mode:'live_sync',games:[{id:'espn_444',home:'AAA',away:'BBB',epoch:NOW+5*3600000,status:'final'}],rows:[]};
 assert.equal(api.inspectCoverage(entry,live,{nowMs:NOW+15*DAY,sourceVerified:false}).status,'SOURCE_UNVERIFIED');
 assert.equal(api.inspectCoverage(entry,live,{nowMs:NOW+15*DAY,sourceVerified:true}).status,'SCHEDULE_CHANGED_AFTER_CAPTURE');
});
test('frozen slate rejects a substituted fixture and unrelated club',()=>{
 const api=engine(),s=local(),x=frozenFixture();
 x.slate.games[0].id='not_espn';
 assert.throws(()=>api.take(s,x),/BAD_FROZEN_SLATE_GAME/);
 assert.equal(s.store.size,0);
 const y=frozenFixture();y.slate.games[0].id='espn_444';y.slate.games[0].home='CCC';y.slate.games[0].away='DDD';
 assert.throws(()=>api.take(s,y),/BAD_FROZEN_SLATE_GAME/);
});
test('preexisting private journals remain readable, but cannot claim a frozen slate',()=>{
 const api=engine(),s=local(),e=api.take(s,fixture());
 assert.equal(e.frozen_slate,undefined);
 assert.equal(api.inspectCoverage(e,{mode:'live_sync',games:[],rows:[]},{nowMs:NOW+15*DAY,sourceVerified:true}).status,'LEGACY_NO_FROZEN_SLATE');
 assert.equal(api.read(s).entries.length,1);
});
test('tampering with the frozen slate is caught on read, not repaired',()=>{
 const api=engine(),s=local();api.take(s,frozenFixture());
 const raw=JSON.parse(s.store.get(j.KEY));raw.entries[0].frozen_slate.games[0].tipoff_utc='2026-10-01T12:00:00Z';
 s.store.set(j.KEY,JSON.stringify(raw));
 assert.throws(()=>api.read(s),/BAD_FROZEN_SLATE_GAME/);
});

// PR169 — the stored scenario is a conditional what-if, not an official ledger.
test('a traded player club mismatch blocks NBA replay instead of silently crediting FP',()=>{
 const api=engine(),s=local(),entry=api.take(s,frozenFixture());
 const live={mode:'live_sync',games:[{id:'espn_444',home:'AAA',away:'BBB',epoch:NOW+3*3600000,status:'final'}],
  rows:[{id:'n101',game_id:'espn_444',played:true,fp:72,team:'CCC'}]};
 const result=api.inspectCoverage(entry,live,{nowMs:NOW+15*DAY,sourceVerified:true});
 assert.equal(result.status,'PLAYER_CLUB_TENURE_CONFLICT');
 assert.equal(result.actual_gain_fp,null);
 assert.equal(result.real_sportsru_gain_proven,false);
 live.rows[0].team=undefined;
 assert.equal(api.inspectCoverage(entry,live,{nowMs:NOW+15*DAY,sourceVerified:true}).status,'PLAYER_CLUB_TENURE_CONFLICT');
});
test('modelled move that sells an already sold player fails ownership replay closed',()=>{
 const api=engine(),s=local(),x=frozenFixture();
 x.slate.playerTeams.n223='BBB';
 x.plan.routes[1].moves.push({out:'n101',in_:'n223',epoch:NOW+2*60000,sell:1200,buy:900});
 const entry=api.take(s,x);
 const live={mode:'live_sync',games:[{id:'espn_444',home:'AAA',away:'BBB',epoch:NOW+3*3600000,status:'final'}],rows:[]};
 const status=api.inspectCoverage(entry,live,{nowMs:NOW+15*DAY,sourceVerified:true});
 assert.equal(status.status,'UNVERIFIED_OWNERSHIP_PATH');
 assert.equal(status.actual_gain_fp,null);
});
test('buying an already owned player is not silently applied as a second roster slot',()=>{
 const api=engine(),s=local(),x=frozenFixture();
 x.plan.routes[1].moves[0].in_='n102';
 // The LATER alternative still references n222, so its club stays in the snapshot.
 const entry=api.take(s,x);
 const live={mode:'live_sync',games:[{id:'espn_444',home:'AAA',away:'BBB',epoch:NOW+3*3600000,status:'final'}],rows:[]};
 assert.equal(api.inspectCoverage(entry,live,{nowMs:NOW+15*DAY,sourceVerified:true}).status,'UNVERIFIED_OWNERSHIP_PATH');
});
test('T-30 exactly is locked, not an executable buy timestamp',()=>{
 const api=engine(),s=local(),x=frozenFixture();
 x.slate.games[0].epoch=NOW+31*60000;
 const entry=api.take(s,x);
 const rows=roster.map((id,i)=>({id,game_id:'espn_444',played:true,fp:i+1,team:'AAA'}));
 rows.push({id:'n222',game_id:'espn_444',played:true,fp:88,team:'BBB'});
 const live={mode:'live_sync',games:[{id:'espn_444',home:'AAA',away:'BBB',epoch:NOW+31*60000,status:'final'}],rows};
 const status=api.inspectCoverage(entry,live,{nowMs:NOW+15*DAY,sourceVerified:true});
 assert.equal(status.status,'NBA_PLAYED_ROWS_ONLY_NOT_OFFICIAL');
 assert.equal(status.routes[0].nba_played_fp_partial_not_official,55);
 assert.equal(status.routes[1].nba_played_fp_partial_not_official,55);
 assert.equal(status.routes[1].observed_played_rows,10);
 assert.equal(status.actual_gain_fp,null);
});


// PR172: one read-only readiness ledger for all frozen horizons.
test('coverage ledger distinguishes pending, incomplete NBA rows and never produces Sports.ru gain',()=>{
 const api=engine(),s=local();api.take(s,frozenFixture());
 const snapshot=api.read(s),before=JSON.stringify(snapshot);
 const pending=api.auditCoverage(snapshot,{mode:'live_sync',games:[],rows:[]},
  {nowMs:NOW+DAY,sourceVerified:true});
 assert.equal(pending.total,1);
 assert.equal(pending.counts.pending,1);
 assert.equal(pending.proven_economic_wins,0);
 assert.equal(pending.winning_strategy_proven,false);
 assert.equal(pending.entries[0].predicted_gain_model_fp,25.5);
 const live={mode:'live_sync',games:[{id:'espn_444',home:'AAA',away:'BBB',
   epoch:NOW+3*3600000,status:'final'}],rows:[{id:'n101',game_id:'espn_444',played:true,fp:15,team:'AAA'}]};
 const incomplete=api.auditCoverage(snapshot,live,{nowMs:NOW+15*DAY,sourceVerified:true});
 assert.equal(incomplete.counts.partial_nba,1);
 assert.equal(incomplete.entries[0].selected_nba_played_rows,0);
 assert.equal(incomplete.entries[0].unknown_or_dnp_rows,10);
 assert.equal(incomplete.entries[0].actual_gain_fp,null);
 assert.equal(incomplete.sportsru_credited_player_game_results_available,false);
 const full={...live,rows:roster.map((id,i)=>({id,game_id:'espn_444',played:true,
   fp:i+1,team:'AAA'})).concat([{id:'n222',game_id:'espn_444',played:true,fp:23,team:'BBB'}])};
 const complete=api.auditCoverage(snapshot,full,{nowMs:NOW+15*DAY,sourceVerified:true});
 assert.equal(complete.counts.nba_rows_only,1);
 assert.equal(complete.entries[0].real_sportsru_gain_proven,false);
 assert.equal(complete.proven_economic_losses,0);
 assert.equal(complete.winning_strategy_proven,false);
 assert.equal(JSON.stringify(snapshot),before,'audit must not edit the private journal');
});
test('overlapping retrospective horizons are counted as dependent observations, not independent winners',()=>{
 const api=engine(),s=local();api.take(s,fixture());
 const shifted=engine(NOW+2*60000),x=frozenFixture();x.plan.start=NOW+3*60000;
 x.plan.end=x.plan.start+14*DAY;x.plan.routes[1].moves[0].epoch=x.plan.start;
 x.slate.games[0].epoch=NOW+3*3600000;
 shifted.take(s,x);
 const audit=shifted.auditCoverage(shifted.read(s),{mode:'live_sync',games:[],rows:[]},
  {nowMs:NOW+DAY,sourceVerified:false});
 assert.equal(audit.total,2);
 assert.equal(audit.counts.pending,2);
 assert.equal(audit.nonoverlap_time_groups,1);
 assert.equal(audit.overlapping_decisions,1);
 assert.equal(audit.groups_not_statistical_independence,true);
 const later=shifted.auditCoverage(shifted.read(s),{mode:'live_sync',games:[],rows:[]},
  {nowMs:NOW+15*DAY,sourceVerified:true});
 assert.equal(later.counts.legacy,1);
 assert.equal(later.counts.partial_nba,1);
});
test('ledger refuses a corrupt local archive and an unvalidated observation clock',()=>{
 const api=engine(),s=local();api.take(s,fixture());
 assert.throws(()=>api.auditCoverage(api.read(s),{},{}),/AUDIT_CLOCK_REQUIRED/);
 const bad=api.read(s);bad.entries[0].outcome.real_transfer_benefit_proven=true;
 assert.throws(()=>api.auditCoverage(bad,{},
  {nowMs:NOW+16*DAY,sourceVerified:false}),/MODIFIED_OR_UNTRUSTED_ENTRY/);
});
