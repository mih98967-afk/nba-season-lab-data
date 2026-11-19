/* Exact public/default PR175 app function replay on preserved pre-issue data. */
const fs=require('fs'),path=require('path'),vm=require('vm'),crypto=require('crypto');
const HERE=__dirname,ROOT=path.resolve(HERE,'../..'),IN=path.join(HERE,'baseline_inputs');
const BASE=process.env.NBA_RESEARCH_BASE||path.join(ROOT,'research_base');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const shaText=s=>crypto.createHash('sha256').update(s).digest('hex');
function exactFunction(source,name){
 const start=source.indexOf('function '+name+'(');if(start<0)throw Error('Missing actual app function '+name);
 const brace=source.indexOf('{',start);let depth=0,state='',escape=false;
 for(let i=brace;i<source.length;i++){
  const c=source[i],next=source[i+1];
  if(state==='line'){if(c==='\n')state='';continue;}
  if(state==='block'){if(c==='*'&&next==='/'){state='';i++;}continue;}
  if(state){if(escape){escape=false;continue;}if(c==='\\'){escape=true;continue;}if(c===state)state='';continue;}
  if(c==='/'&&next==='/'){state='line';i++;continue;}if(c==='/'&&next==='*'){state='block';i++;continue;}
  if(c==='"'||c==="'"||c==='`'){state=c;continue;}
  if(c==='{')depth++;else if(c==='}'&&--depth===0)return source.slice(start,i+1);
 }
 throw Error('Unterminated actual app function '+name);
}
const app=fs.readFileSync(path.join(IN,'app_pr175.js'),'utf8'),app176=fs.readFileSync(path.join(IN,'app_pr176.js'),'utf8');
const names=['updatePlayerTeams','actualByPlayer','playerActual','verifiedOfficialForGame','oldGameProjection','probability','learnedMean'];
const functions=Object.fromEntries(names.map(n=>[n,exactFunction(app,n)]));
for(const n of names)if(functions[n]!==exactFunction(app176,n))throw Error('PR175/176 prediction-function difference '+n);
const clamp=app.match(/^const clamp=.*;$/m)?.[0];if(!clamp)throw Error('Missing app clamp');
const base=read(path.join(IN,'base_pr175.json')),identity=read(path.join(IN,'identity_pregame.json'));
const mapped={};for(const [id,r] of Object.entries(identity.players||{}))if(r.confidence==='high'&&/^\d+$/.test(String(r.nba_id)))(mapped[String(r.nba_id)]??=[]).push(id);
const idmap=Object.fromEntries(Object.entries(mapped).filter(([k,v])=>v.length===1).map(([k,v])=>[k,v[0]]));
const configurations=[
 {cohort:'original_20261116',freeze:path.join(BASE,'prospective_20261116/forecasts.json'),live:path.join(BASE,'source/data/live.json'),official:path.join(IN,'official_20261116.json')},
 {cohort:'paired_20261117',freeze:path.join(ROOT,'research_extension/prospective_20261117/forecasts.json'),live:path.join(ROOT,'research_extension/fresh_20261117/source/data/live.json'),official:path.join(IN,'official_20261117.json')}
];
const results={},meta={schema:'nba-exact-app-public-default-replay-v1',generated_at_utc:new Date().toISOString(),baseline_predictions_were_not_prospectively_frozen:true,private_owner_settings_replayed:false,source_PR175_confirmed_hosting:true,pregame_team_update_applied:true,PR176_same_prediction_functions_verified:true,app_sha256:sha(path.join(IN,'app_pr175.js')),base_sha256:sha(path.join(IN,'base_pr175.json')),official_status_module_sha256:sha(path.join(IN,'official_status_pr175.js')),function_sha256:Object.fromEntries(names.map(n=>[n,shaText(functions[n])])),cohorts:{}};
for(const conf of configurations){
 const freeze=read(conf.freeze),live=read(conf.live),official=read(conf.official),issued=Date.parse(freeze.issued_at_utc);
 if(Date.parse(live.updated_at_utc)>issued||Date.parse(official.updated_at_utc)>issued)throw Error('Post-issue public input');
 if(live.rows.some(r=>Date.parse(r.utc)>=issued))throw Error('Post-issue historical player outcome');
 if(official.events.some(e=>Date.parse(e.first_seen_at_utc)>issued||Date.parse(e.report_at_utc)>issued))throw Error('Post-issue official status');
 const localBase=JSON.parse(JSON.stringify(base));
 const context={BASE:localBase,CLUBS:Object.fromEntries(localBase.teams.map(t=>[t.team,t.name_ru||t.name||t.team])),ORIGINAL_TEAMS:Object.fromEntries(localBase.players.map(p=>[p.id,p.team])),LIVE:live,P:Object.fromEntries(localBase.players.map(p=>[p.id,p])),S:{medical:{},teamOverrides:{},riskMode:'baseline',modelMode:'current'},OFFICIAL_FEED:official,cache:{},now:()=>issued,Math,Date,Map,Number,NaN};
 context.window=context;vm.createContext(context);
 vm.runInContext(fs.readFileSync(path.join(IN,'official_status_pr175.js'),'utf8'),context,{timeout:1000});
 vm.runInContext(clamp+'\nconst officialGameCache=new Map();let officialGameBucket=-1;\n'+names.map(n=>functions[n]).join('\n'),context,{timeout:1000});
 context.updatePlayerTeams();
 const fixtures=new Map((live.schedule||[]).map(g=>[g.id,g]));let officialOut=0,nonforecast=0;
 const rows=freeze.records.map(f=>{
  const id=idmap[f.nba_player_id],p=context.P[id],g=fixtures.get(f.calendar_game_id);
  const row={model_role:f.model_role,nba_player_id:f.nba_player_id,nba_game_id:f.nba_game_id,lead_days:f.lead_days,date_ET:f.date_ET,catalog_id:id||null,baseline_status:'UNAVAILABLE'};
  if(!id||!p)return {...row,reason:'no_unique_pregame_identity_or_seed_player'};
  if(!p.forecast){nonforecast++;return {...row,reason:'seed_forecast_unavailable'};}
  if(p.team!==f.team)return {...row,reason:'seed_team_differs_from_exact_frozen_team'};
  if(!g||g.utc!==f.tipoff_utc||!new Set([g.home,g.away]).has(p.team))return {...row,reason:'pregame_fixture_mismatch'};
  if(g.status==='final'||Date.parse(g.utc)<=issued+30*60000)return {...row,reason:'pregame_fixture_not_actionable'};
  const mu=context.learnedMean(p,g),prob=context.probability(p,g),status=context.verifiedOfficialForGame(p,g);
  if(!Number.isFinite(mu)||!Number.isFinite(prob))throw Error('Nonfinite actual runtime output');
  if(status?.status==='out')officialOut++;
  return {...row,baseline_status:'AVAILABLE',mean_if_play:mu,p_play:prob,expected_fp:mu*prob,official_exact_game_status:status?.status||null,old_game_projection_available:!!context.oldGameProjection(p,g),recent_played_rows:context.playerActual(p.id).length};
 });
 results[conf.cohort]=rows;
 const count={};for(const r of rows){const k=r.baseline_status==='AVAILABLE'?'AVAILABLE':r.reason;count[k]=(count[k]||0)+1;}
 meta.cohorts[conf.cohort]={issued_at_utc:freeze.issued_at_utc,live_updated_at_utc:live.updated_at_utc,official_updated_at_utc:official.updated_at_utc,live_sha256:sha(conf.live),official_sha256:sha(conf.official),forecast_sha256:sha(conf.freeze),counts:count,official_OUT_rows:officialOut,all_live_outcomes_predate_issue:true,all_status_observations_predate_issue:true};
}
const out=path.join(HERE,'baseline_results_v2');fs.mkdirSync(out,{recursive:true});
for(const [cohort,rows]of Object.entries(results))fs.writeFileSync(path.join(out,cohort+'_runtime_predictions.json'),JSON.stringify(rows)+'\n');
fs.writeFileSync(path.join(out,'REPLAY_METADATA.json'),JSON.stringify(meta,null,2)+'\n');console.log(JSON.stringify(meta,null,2));
