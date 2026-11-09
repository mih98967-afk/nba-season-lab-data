(()=>{'use strict';
const BASE=JSON.parse(document.getElementById('bootstrap-data').textContent);
const SEED=JSON.parse(document.getElementById('bootstrap-live').textContent);
const P=Object.fromEntries(BASE.players.map(p=>[p.id,p]));
const CLUBS=Object.fromEntries(BASE.teams.map(t=>[t.team,t.name_ru||t.name||t.team]));
const ORIGINAL_TEAMS=Object.fromEntries(BASE.players.map(p=>[p.id,p.team]));
const POS=['PG','SG','SF','PF','C'];
const POSRU={PG:'Разыгрывающие',SG:'Атакующие защитники',SF:'Лёгкие форварды',PF:'Тяжёлые форварды',C:'Центровые'};
const KEY='pythos-nba-season-v5-guest-2026';
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const round=(x,n=0)=>Number.isFinite(Number(x))?Number(x).toLocaleString('ru-RU',{maximumFractionDigits:n,minimumFractionDigits:n}):'—';
const approx=x=>Number.isFinite(x)?round(x,1):'—';
const num=x=>x==null||x===''?NaN:Number(x);
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const TZ='Europe/Moscow';
const dateText=x=>new Date(x).toLocaleString('ru-RU',{timeZone:TZ,day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
const justDay=x=>new Date(x).toLocaleDateString('ru-RU',{timeZone:TZ,day:'2-digit',month:'2-digit',weekday:'short'});
const clock=x=>new Date(x).toLocaleTimeString('ru-RU',{timeZone:TZ,hour:'2-digit',minute:'2-digit'});
const now=()=>Date.now();
const defaults=()=>({v:5,initialRoster:[],initialEpoch:Date.parse(BASE.season_start||'2026-10-20T19:00:00Z'),roster:[],cash:20000,executed:[],prices:{},teamOverrides:{},medical:{},draft:[],riskMode:'baseline',modelMode:'current',lastUpdate:null});
function load(){try{const s=JSON.parse(localStorage.getItem(KEY));if(s&&s.v===5&&Array.isArray(s.roster))return {...defaults(),...s};}catch{}return defaults();}
const embeddedJSON=id=>{try{return JSON.parse(document.getElementById(id)?.textContent||'null');}catch{return null;}};
let S=load(),LIVE=SEED,tab='today',MODAL=null,cache=null,onlineError='',liveSource='starter snapshot',publicFeedValidated=false,notice='',NBA_HISTORY=embeddedJSON('bootstrap-history'),TG_NEWS=embeddedJSON('bootstrap-telegram'),MODEL_REPORT=embeddedJSON('bootstrap-model');
let CALENDAR=null,CALENDAR_STATUS='Полный календарь загружается';
let OFFICIAL_FEED=null,OFFICIAL_STATUS='Официальные NBA Injury Reports загружаются';
let HISTORY_INDEX=null,HISTORY_STATUS='Загружается индекс…',HISTORY_INFLIGHT=new Set();
let MODEL_V2=null,HISTORY_LOADED_SHARDS=new Set(),HISTORY_FETCHING_SHARDS=new Set(),HISTORY_SHARD_ERRORS=new Map();

let UI={search:'',position:'all',club:'all',sort:'week',compare:[],window:7,calendarStart:'',calendarEnd:'',calendarDays:14,calendarOwn:false,calendarMode:'tours',calendarTour:0,calendarTourCount:3,calendarTourSort:'games',playerId:null,histSeason:'all',histOpponent:'all',histLimit:25,plannerOut:null,plannerIn:null,plannerWhen:null,plannerSell:null,plannerBuy:null,quickPreview:null,chainDays:21,chainPenalty:4,chainResult:null,multiDays:21,multiPenalty:4,multiMoves:3,multiFocus:'all',multiResult:null,budgetPosition:'all',budgetTarget:null,budgetOut:'auto',budgetBuy:null,budgetDays:14,budgetPenalty:4,budgetMoves:3,budgetResult:null,retroOpen:false,retroRows:[],retroPreview:null,plannerTask:'advice',plannerTaskListOpen:false,plannerAdvanced:false,plannerSequenceTool:'none',plannerManualOpen:false,plannerDetail:false,multiOptions:false,multiCalculatedAt:null,teamView:'court',marketView:'candidates',marketAdvanced:false,marketLimit:50,marketFocusPlayer:null,calendarQuick:'team',calendarTeamDays:7,calendarFocusPlayer:null,statusScope:'mine',sportsOpen:false,sportsResult:null,sportsInputs:{fp:'',cash:'',remaining:''}};
const root=document.getElementById('root');
function save(){UI.sportsResult=null;UI.sportsInputs={fp:'',cash:'',remaining:''};UI.chainResult=null;UI.multiResult=null;UI.budgetResult=null;S.v=5;S.lastUpdate=new Date().toISOString();try{localStorage.setItem(KEY,JSON.stringify(S));}catch{notice='Браузер не разрешил локальное сохранение. Используйте экспорт резервной копии.';}window.nbaCloudSave?.(JSON.parse(JSON.stringify(S)));}
function applyState(remote){if(!remote||!Array.isArray(remote.roster))return;UI.sportsResult=null;UI.sportsInputs={fp:'',cash:'',remaining:''};UI.chainResult=null;UI.multiResult=null;UI.budgetResult=null;S={...defaults(),...remote,v:5};saveLocalOnly();tab='today';view();}
function saveLocalOnly(){try{localStorage.setItem(KEY,JSON.stringify(S));}catch{}}
window.NBA={getState:()=>JSON.parse(JSON.stringify(S)),applyState,guestReset:()=>{S=defaults();UI.sportsResult=null;UI.sportsInputs={fp:'',cash:'',remaining:''};saveLocalOnly();view();},getAuthStatus:()=>window.NBA_CLOUD_STATUS||{state:'local',label:'На этом устройстве'},setHistory:(x)=>{NBA_HISTORY=x;view();},setTelegram:(x)=>{TG_NEWS=x;view();},setModel:(x)=>{MODEL_REPORT=x;view();},setOfficial:(x)=>{setOfficialStatus(x,'тестовая инъекция');},view:()=>view()};

function updatePlayerTeams(){
 // Most recent actual NBA club; a manual Sports.ru override takes precedence.
 const recent={};for(const row of LIVE.rows||[]){
  if(!row.id||!CLUBS[row.team])continue;
  if(!recent[row.id]||String(row.utc)>recent[row.id].utc)recent[row.id]={utc:String(row.utc),team:row.team};
 }
 for(const p of BASE.players)p.team=(S.teamOverrides||{})[p.id]||recent[p.id]?.team||ORIGINAL_TEAMS[p.id];
}
function hardCheck(ids,prices=null,cash=null){
 const errors=[],cnt=Object.fromEntries(POS.map(k=>[k,0])),teams={};let sum=0;
 if(!Array.isArray(ids)||ids.length!==10)errors.push('В составе должно быть ровно десять игроков');
 if(new Set(ids).size!==ids.length)errors.push('Игрок не может занимать два слота');
 for(const id of ids||[]){const p=P[id];if(!p){errors.push('Неизвестный игрок');continue;}cnt[p.pos]++;teams[p.team]=(teams[p.team]||0)+1;sum+=(prices&&prices[id]!=null?Number(prices[id]):p.start_price);}
 for(const [k,v] of Object.entries(cnt))if(v!==2)errors.push(`${k}: необходимо два игрока, сейчас ${v}`);
 for(const [k,v] of Object.entries(teams))if(v>2)errors.push(`${k}: максимум два баскетболиста`);
 if(cash!=null&&cash<-0.001)errors.push('Недостаточно свободных средств');
 return {valid:!errors.length,errors,sum,cnt,teams};
}
function moscowWeek(ms){return window.NBATransferGuard.weekKey(ms,15);}
function calendarMoscowWeek(ms){return window.NBATransferGuard.weekKey(ms,0);}
function moscowEpoch(value){if(!value)return NaN;const v=String(value).slice(0,16);const a=Date.parse(v+':00+03:00');return Number.isFinite(a)?a:NaN;}
function moscowInput(epoch){const d=new Date(epoch+3*3600000);return d.toISOString().slice(0,16);}
function prices(id){const override=S.prices[id];if(override!=null&&Number.isFinite(Number(override)))return Number(override);const p=P[id];if(!p)return 0;const total=(LIVE.rows||[]).filter(r=>r.id===id).reduce((s,r)=>s+(Number(r.fp)||0),0);return Math.max(0,p.start_price+total);}
// No synthetic games: the verified ESPN calendar supersedes the 197-game seed.
// Live final scores take precedence over the daily calendar snapshot.
function normalizedGames(){
 if(cache?.games)return cache.games;
 const map=new Map();
 const signature=g=>`${g.home}|${g.away}|${new Date(g.epoch||Date.parse(g.utc)).toISOString().slice(0,10)}`;
 const all=CALENDAR?.games?.length>=1100 ? CALENDAR.games : BASE.static_schedule;
 for(const g of all){if(!g.home||!g.away||!g.utc)continue;map.set(signature(g),{...g,kind:CALENDAR?'espn-calendar':'static'});}
 for(const g of LIVE.schedule||[]){if(!g.home||!g.away||!g.utc)continue;map.set(signature(g),{...g,kind:'online'});}
 for(const g of LIVE.games||[]){if(!g.home||!g.away||!g.utc)continue;map.set(signature(g),{...g,kind:'online'});}
 return [...map.values()].sort((a,b)=>a.epoch-b.epoch);
}
function calendarCoverage(start=now(),days=7){
 const end=start+days*86400000;
 if(!CALENDAR||CALENDAR.status!=='verified_public_calendar_with_known_gaps')return {ok:false,reason:'Полный UTC-календарь пока не загружен'};
 const age=now()-Date.parse(CALENDAR.updated_at_utc||'');
 if(!Number.isFinite(age)||age>72*3600000)return {ok:false,reason:'Календарь устарел более чем на 72 часа'};
 const cupStart=Date.parse('2026-12-04T00:00:00Z'),cupEnd=Date.parse('2026-12-11T12:00:00Z');
 if((CALENDAR.completeness?.unassigned_or_unavailable_games||0)>0&&start<cupEnd&&end>cupStart)return {ok:false,reason:'В выбранном окне ещё не назначены отдельные матчи NBA Cup'};
 const knownEnd=Date.parse('2027-04-12T12:00:00Z');
 if(end>knownEnd)return {ok:false,reason:'Выбранное окно выходит за пределы календаря регулярного сезона'};
 if(start<Date.parse('2026-10-20T00:00:00Z'))return {ok:false,reason:'Начало окна находится до регулярного сезона'};
 return {ok:true,reason:'Проверенный календарь ESPN; незакреплённые матчи Кубка исключены'};
}
function advicePreflight(days=21,startEpoch=now()){
 const readiness=window.NBAAdviceReadiness;
 if(!readiness)return {ready:false,rosterReady:false,feedReady:false,reasons:['Модуль проверки данных не загрузился.']};
 return readiness.inspect({nowEpoch:now(),feed:LIVE,sourceVerified:publicFeedValidated,
  roster:S.roster,players:P,cash:S.cash,startEpoch,calendarReady:calendarCoverage(startEpoch,days).ok});
}
function coverageMessage(start,days){const x=calendarCoverage(start,days);return `<div class="info ${x.ok?'':'warning'}" role="status"><b>Календарь ${days} дней:</b> ${esc(x.reason)}. Источник: <a href="https://github.com/mih98967-afk/nba-season-lab-data/blob/main/data/schedule.json" rel="noopener noreferrer" target="_blank">GitHub / ESPN</a>.</div>`;}
function actualByPlayer(){
 if(cache?.actuals)return cache.actuals;
 const by={};for(const r of LIVE.rows||[]){(by[r.id]||(by[r.id]=[])).push(r);}
 Object.values(by).forEach(a=>a.sort((a,b)=>Date.parse(a.utc)-Date.parse(b.utc)));
 return by;
}
function ownedAt(ms){if(!S.initialRoster?.length||ms<(S.initialEpoch||0))return [];let ids=[...S.initialRoster];for(const t of [...S.executed].sort((a,b)=>a.epoch-b.epoch)){if(t.epoch<=ms){const k=ids.indexOf(t.out);if(k>=0)ids[k]=t.in_;}}return ids;}
function actualTotal(){return window.NBAScoreAudit.audit(LIVE,S);}
function playerActual(id){return (actualByPlayer()[id]||[]).filter(x=>x.played).slice(-12);}
function oldGameProjection(p,g){let old=(p.games||[]).find(x=>x.id===g.id||Math.abs(x.epoch-g.epoch)<3.1*3600e3&&x.opponent===(p.team===g.home?g.away:g.home));return old;}
function probability(p,g){let pp=oldGameProjection(p,g)?.p_play;
 if(!Number.isFinite(pp))pp=Number.isFinite(p.availability_p1)?clamp(p.availability_p1,0.5,.98):.86;
 const status=S.medical[p.id]||'default';
 if(status==='out')return 0;
 if(S.riskMode==='allplay')return 1;
 if(status==='questionable')pp=Math.min(pp,.52);
 if(status==='available')pp=Math.max(pp,.96);
 if(S.riskMode==='cautious'&&status!=='available')pp-=.15;
 return clamp(pp,0,1);
}
function validatedModelSignal(p){
 // Independently backtested only for NEXT PLAYED game. The availability model is separate.
 if(MODEL_V2?.schema_version!==2||MODEL_V2?.status!=='validated_for_conditional_game')return null;
 const hist=(NBA_HISTORY?.players?.[p.id]||[]).flatMap(z=>z.game_log||[]).filter(r=>Number.isFinite(Number(r.fp))&&Number.isFinite(Number(r.min))&&Number(r.min)>0);
 const current=(actualByPlayer()[p.id]||[]).filter(r=>Number.isFinite(Number(r.fp))&&Number.isFinite(Number(r.minutes))&&Number(r.minutes)>0).map(r=>({d:String(r.utc),g:r.game_id,fp:Number(r.fp),min:Number(r.minutes)}));
 const all=[...hist,...current].sort((a,b)=>String(a.d).localeCompare(String(b.d))||String(a.g||'').localeCompare(String(b.g||'')));
 if(all.length<25)return null;
 const last10=all.slice(-10),last25=all.slice(-25),last5=all.slice(-5);
 const mean=(rows,key)=>rows.reduce((z,x)=>z+Number(x[key]),0)/rows.length;
 const params=MODEL_V2.chosen_params||{};
 const recency=Number(params.recency),oldWeight=Number(params.old_weight),minuteWeight=Number(params.minutes_weight);
 if(![recency,oldWeight,minuteWeight].every(Number.isFinite))return null;
 const base=mean(last10,'fp'),recent=mean(last5,'fp'),long=mean(last25,'fp');
 const momentum=mean(last5,'min')-mean(last10,'min');
 const rate=last10.reduce((z,x)=>z+Number(x.fp),0)/Math.max(75,last10.reduce((z,x)=>z+Number(x.min),0));
 const minutesEffect=clamp(minuteWeight*momentum*clamp(rate,0,1.5),-8,8);
 const value=clamp((1-recency)*((1-oldWeight)*base+oldWeight*long)+recency*recent+minutesEffect,-5,80);
 return {value,n:all.length,baseline:base,minutesEffect};
}
function learnedMean(p,g){if(!p||!p.forecast)return NaN;
 if(S.modelMode==='validated'){const x=validatedModelSignal(p);if(x)return x.value;}
 const historic=oldGameProjection(p,g)?.mu;
 const prior=Number.isFinite(historic)?historic:p.mean_if_play;
 const a=playerActual(p.id);if(!a.length)return prior;
 const last=a.slice(-8);let nume=0,den=0;
 last.forEach((x,i)=>{const w=Math.pow(.87,last.length-i-1);nume+=(Number(x.fp)||0)*w;den+=w;});
 const w=clamp(den/(12+den),0,.42);
 return (1-w)*prior+w*nume/den;
}
function futureGames(id,after=now(),days=7){const p=P[id];if(!p)return [];
 return normalizedGames().filter(g=>g.epoch>=after&&g.epoch<=after+days*86400000&&(g.home===p.team||g.away===p.team)&&g.status!=='final');}
function prediction(id,start=now(),days=7){const p=P[id];if(!p||!p.forecast)return {available:false};
 const coverage=calendarCoverage(start,days);
 if(!coverage.ok)return {available:false,reason:coverage.reason,fp:NaN,games:null,expGames:NaN};
 const gs=futureGames(id,start,days);let fp=0,all=0,expGames=0;
 for(const g of gs){const mu=learnedMean(p,g),q=probability(p,g);fp+=mu*q;all+=mu;expGames+=q;}
 return {available:true,fp,all,games:gs.length,expGames};}
function displayRisk(p){if((S.medical[p.id]||'')==='out')return '<span class="pill bad">Указан OUT</span>';
 if((S.medical[p.id]||'')==='questionable')return '<span class="pill warn">Под вопросом</span>';
 if(p.risk>=3)return '<span class="pill warn">Проверить статус</span>';
 if(p.risk>=2)return '<span class="pill warn">Повышенный риск</span>';
 return '<span class="pill good">Базовый сценарий</span>';}
function summaryRange(ids,start=now(),days=7,n=1400){
 const groups=[];for(const id of ids){const p=P[id];if(!p||!p.forecast)continue;const games=futureGames(id,start,days),a=playerActual(id);const ref=p.noise?.length?p.noise:(p.history||[]).flatMap(x=>x.log_valid?x.log:[]).filter(Number.isFinite).map(x=>x-p.mean_if_play);const noise=(ref||[]).filter(Number.isFinite);
  groups.push({p,games,q:games.map(g=>probability(p,g)),mu:games.map(g=>learnedMean(p,g)),noise,sd:Math.max(5,(p.mean_if_play||15)*.45)});}
 let seed=123456789;function rand(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return (seed>>>0)/4294967296;}
 const values=[];for(let z=0;z<n;z++){let fp=0;for(const o of groups){let active=rand()<.91;let latent=(rand()-.5)*o.sd*.55;for(let i=0;i<o.games.length;i++){
  const q=o.q[i];const yes=rand()< (active?Math.min(.99,q+.04):Math.max(0,q-.10));active=yes;
  if(yes){let epsilon=o.noise.length?o.noise[Math.floor(rand()*o.noise.length)]:((rand()+rand()+rand()+rand()-2)*o.sd);fp+=o.mu[i]+epsilon+latent;}}}values.push(fp);}
 values.sort((a,b)=>a-b);return {p10:values[Math.floor(n*.1)],p90:values[Math.floor(n*.9)],p50:values[Math.floor(n*.5)],scenarios:n,kind:'сценарный, не калиброванный интервал'};
}
function currentStatus(){if(LIVE.mode==='seed_partial_verified')return 'Частичный начальный срез · проверить загрузку';if(LIVE.mode==='sync_failed_using_cache')return 'Синхронизация не удалась · сохранены прошлые данные';if(LIVE.mode==='schedule_sync_only')return 'Обновлён календарь · FP могут отставать';const updated=Date.parse(LIVE.updated_at_utc||'');if(!Number.isFinite(updated))return 'Без обновления';const age=(now()-updated)/3600000;if(age>48)return 'Данные старше 48 часов';if(age>6)return 'Обновлено '+Math.floor(age)+' ч назад';return 'Обновлено '+dateText(updated);}
function projectionPeriod(ids,dayCount){const xs=ids.map(id=>prediction(id,now(),dayCount));return xs.some(x=>!x.available)?NaN:xs.reduce((total,x)=>total+x.fp,0);}
function showNotice(){return notice?`<div class="info warning" role="status">${esc(notice)} <button class="ghost" data-action="dismiss">Закрыть</button></div>`:'';}
function activeScenarioNotice(){
 if((S.modelMode||'current')==='current'&&(S.riskMode||'baseline')==='baseline')return '';
 const method=S.modelMode==='validated'?'исследовательская модель FP v2':'текущий прогноз';
 const missed=S.riskMode==='allplay'?'все сыграют':S.riskMode==='cautious'?'осторожный риск пропуска':'базовый риск пропуска';
 return `<div class="info warning" style="margin-bottom:13px"><b>Активен ваш сценарий:</b> ${method}; ${missed}. Это не подтверждение травм или точности FP. <button class="ghost" data-tabto="planner">Изменить в разделе «Замены»</button></div>`;
}
function view(){updatePlayerTeams();cache={games:null,actuals:null};const games=normalizedGames(),actuals=actualByPlayer();cache={games,actuals};
 document.getElementById('source-status').textContent=currentStatus();document.querySelectorAll('[data-tab]').forEach(b=>{const active=b.dataset.tab===tab;b.classList.toggle('active',active);if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});document.getElementById('more-menu')?.classList.toggle('active', ['history','news','data','account'].includes(tab));
 let html=showNotice();if((tab==='overview'||tab==='players')&&S.roster.length)html+=activeScenarioNotice();if(!S.roster?.length&&(tab==='overview'||tab==='planner'))html+=onboarding();else if(tab==='today')html+=todayPage();else if(tab==='overview')html+=overview();else if(tab==='players')html+=playersPage();else if(tab==='calendar')html+=calendarPage();else if(tab==='planner')html+=plannerPage();else if(tab==='data')html+=dataPage();else if(tab==='history')html+=historyPage();else if(tab==='news')html+=newsPage();else if(tab==='account')html+=accountPage();
 root.innerHTML=html;renderModal();if(tab==='planner'&&S.modelMode==='validated')setTimeout(prefetchPlannerHistory,0);}
function header(k,title,desc){return `<div class="sectiontitle"><div><div class="eyebrow">${esc(k)}</div><h1>${esc(title)}</h1><p class="sub">${esc(desc)}</p></div></div>`;}
function cardMetric(k,n,sub){return `<div class="metric"><span class="k">${k}</span><strong class="num">${n}</strong><span class="more">${sub}</span></div>`;}
function rosterRow(p){const alert=rosterNews(p.id).length;const official=officialForRoster().find(e=>e.playerId===p.id);const a=playerActual(p.id);const last=a.length?a.at(-1):null;const pred=prediction(p.id,now(),7);const next=futureGames(p.id,now(),7).slice(0,2);
 return `<div class="roster-row"><div><button class="ghost person" data-player="${p.id}">${esc(p.name)}</button>${official?`<span class="pill ${window.NBAOfficialStatus.isHighRisk(official.status)?'warn':''}" title="Официальный отчёт NBA; не изменяет FP автоматически">NBA: ${esc(official.status.toUpperCase())}</span>`:''}${alert?'<span class="pill warn" title="Неофициальный пост Telegram — требуется проверка">Новость</span>':''}<small>${p.team} · ${esc(p.pos)}</small></div><div class="v"><strong>${round(prices(p.id))}</strong><small>цена*</small></div><div class="v"><strong>${last?round(last.fp):'—'}</strong><small>посл. FP</small></div><div class="v"><strong>${pred.available?round(pred.fp):'—'}</strong><small>7 дней</small></div><div class="v last"><strong>${next.map(g=>g.home===p.team?'· '+g.away:'@'+g.home).join(' ')||'—'}</strong><small>соперники</small></div></div>`;}
function scoreAuditPanel(a){
 if(!a.days.length)return '<div class="info warning">Пока нет подтверждённых сыгранных строк NBA в вашем периоде владения.</div>';
 const fmtDay=d=>d.slice(8,10)+'.'+d.slice(5,7);
 const dayRows=a.days.map(d=>`<div class="horizontal" style="margin:3px 0"><span>${fmtDay(d.day)} ET</span><span class="spacer"></span><b>${round(d.fp)} FP</b><span class="small">(${d.matches} игроко-матчей)</span></div>`).join('');
 return `<div class="info"><b>Почему NBA FP могут отличаться от Sports.ru</b><p>Из NBA boxscores до последней загруженной даты: <b>${round(a.earlierETFP)} FP</b>. За последнюю дату <b>${fmtDay(a.latestETDay)} ET</b>: ещё <b>${round(a.latestETFP)} FP</b>. Это разделение по дате данных, <b>не подтверждение официального зачёта Sports.ru</b>: последняя дата может быть предварительной.</p><p class="small">Приложение не видит персональный верхний счётчик Sports.ru. ESPN и Sports.ru могут расходиться в отдельных игроко-матчах или времени исправлений статистики. В сумме здесь показаны именно NBA boxscore FP, а не гарантированно зачтённые очки турнира.</p><details><summary>Показать все игровые дни и FP</summary><div style="margin-top:8px">${dayRows}</div></details>${a.warnings.length?`<p class="small">${esc(a.warnings.join(' · '))}</p>`:''}</div>`;
}
// A private, ephemeral comparison only. No Firebase or browser storage writes.
const SRU={
 title:"\u0421\u0432\u0435\u0440\u0438\u0442\u044c \u0441\u043e Sports.ru",
 open:"\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u043f\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u0438",
 close:"\u0421\u043a\u0440\u044b\u0442\u044c",
 lead:"\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0447\u0438\u0441\u043b\u0430, \u043a\u043e\u0442\u043e\u0440\u044b\u0435 \u0441\u0435\u0439\u0447\u0430\u0441 \u0432\u0438\u0434\u043d\u044b \u043d\u0430 Sports.ru. \u0421\u0435\u0440\u0432\u0438\u0441 \u043d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u0438\u0441\u043f\u0440\u0430\u0432\u0438\u0442 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438.",
 fp:"\u041e\u0447\u043a\u0438 \u0437\u0430 \u0441\u0435\u0437\u043e\u043d",
 cash:"\u0421\u0432\u043e\u0431\u043e\u0434\u043d\u044b\u0435 \u0441\u0440\u0435\u0434\u0441\u0442\u0432\u0430",
 quota:"\u041e\u0441\u0442\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u043c\u0435\u043d",
 attest:"\u042f \u0442\u043e\u043b\u044c\u043a\u043e \u0447\u0442\u043e \u043f\u0440\u043e\u0432\u0435\u0440\u0438\u043b \u044d\u0442\u0438 \u0437\u043d\u0430\u0447\u0435\u043d\u0438\u044f \u043d\u0430 Sports.ru",
 run:"\u0421\u0440\u0430\u0432\u043d\u0438\u0442\u044c \u0431\u0435\u0437 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0438\u044f",
 privacy:"\u0427\u0438\u0441\u043b\u0430 \u043d\u0435 \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u044e\u0442\u0441\u044f, \u043d\u0435 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u044e\u0442\u0441\u044f \u0432 Firebase \u0438 \u0438\u0441\u0447\u0435\u0437\u043d\u0443\u0442 \u043f\u043e\u0441\u043b\u0435 \u043f\u0435\u0440\u0435\u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u044b.",
 report:"\u0420\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442 \u0441\u0432\u0435\u0440\u043a\u0438",
 captured:"\u0412\u0440\u0435\u043c\u044f \u043d\u0430 \u0432\u0430\u0448\u0435\u043c \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u0435",
 noInput:"\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0445\u043e\u0442\u044f \u0431\u044b \u043e\u0434\u0438\u043d \u043f\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u044c.",
 needAttest:"\u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0434\u0438\u0442\u0435, \u0447\u0442\u043e \u0441\u043c\u043e\u0442\u0440\u0438\u0442\u0435 \u043d\u0430 Sports.ru \u0441\u0435\u0439\u0447\u0430\u0441.",
 invalid:"\u041d\u0435\u043f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u043e\u0435 \u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0435. FP \u2014 \u0447\u0438\u0441\u043b\u043e, \u043a\u0430\u0441\u0441\u0430 \u2014 \u043e\u0442 0 \u0434\u043e 20 000, \u0437\u0430\u043c\u0435\u043d\u044b \u2014 \u0446\u0435\u043b\u043e\u0435 \u043e\u0442 0 \u0434\u043e 3.",
 fpOwner:"Sports.ru",fpLocal:"NBA: \u043f\u0435\u0440\u0435\u0441\u0447\u0451\u0442",cashLocal:"\u0421\u0435\u0440\u0432\u0438\u0441",
 delta:"\u0420\u0430\u0437\u043d\u0438\u0446\u0430 (\u0441\u0435\u0440\u0432\u0438\u0441 \u2212 Sports.ru)",
 match:"\u0421\u043e\u0432\u043f\u0430\u0434\u0430\u0435\u0442 \u043f\u043e \u0432\u0432\u0435\u0434\u0451\u043d\u043d\u044b\u043c \u0447\u0438\u0441\u043b\u0430\u043c, \u043d\u043e \u044d\u0442\u043e \u043d\u0435 \u043d\u0435\u0437\u0430\u0432\u0438\u0441\u0438\u043c\u0430\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430.",
 fpMismatch:"FP \u0440\u0430\u0441\u0445\u043e\u0434\u044f\u0442\u0441\u044f. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 \u043c\u0430\u0442\u0447\u0438 \u043f\u043e ET, \u0437\u0430\u0447\u0451\u0442 Sports.ru \u0438 \u0434\u0430\u0442\u044b \u0432\u043b\u0430\u0434\u0435\u043d\u0438\u044f \u0438\u0433\u0440\u043e\u043a\u0430\u043c\u0438.",
 fpCaveat:"NBA boxscore \u043c\u043e\u0436\u0435\u0442 \u043e\u0442\u043b\u0438\u0447\u0430\u0442\u044c\u0441\u044f \u043e\u0442 \u043d\u0430\u0447\u0438\u0441\u043b\u0435\u043d\u0438\u0439 Sports.ru \u0438 \u0432\u043a\u043b\u044e\u0447\u0430\u0442\u044c \u0435\u0449\u0451 \u043d\u0435 \u0437\u0430\u0447\u0442\u0451\u043d\u043d\u044b\u0435 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u044b.",
 fpStale:"\u041f\u0443\u0431\u043b\u0438\u0447\u043d\u044b\u0435 \u0434\u0430\u043d\u043d\u044b\u0435 NBA \u0443\u0441\u0442\u0430\u0440\u0435\u043b\u0438 \u0438\u043b\u0438 \u0432\u0440\u0435\u043c\u044f \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u043d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u043e.",
 cashMismatch:"\u041a\u0430\u0441\u0441\u0430 \u0440\u0430\u0441\u0445\u043e\u0434\u0438\u0442\u0441\u044f. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u043d\u0435\u0437\u0430\u043f\u0438\u0441\u0430\u043d\u043d\u044b\u0435 \u0437\u0430\u043c\u0435\u043d\u044b \u0438 \u0444\u0430\u043a\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u0446\u0435\u043d\u044b.",
 cashMatch:"\u041a\u0430\u0441\u0441\u0430 \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u0435\u0442. \u0426\u0435\u043d\u044b \u0438\u0433\u0440\u043e\u043a\u043e\u0432 \u044d\u0442\u0438\u043c \u043d\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u044e\u0442\u0441\u044f.",
 quotaLabel:"\u0421\u0447\u0451\u0442\u0447\u0438\u043a \u043f\u043e \u0436\u0443\u0440\u043d\u0430\u043b\u0443: \u041f\u043d 15:00 / \u041f\u043d 00:00",
 quotaMatched:"\u041e\u0434\u043d\u0430 \u0438\u0437 \u0433\u0438\u043f\u043e\u0442\u0435\u0437 \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u0435\u0442, \u043d\u043e \u0433\u0440\u0430\u043d\u0438\u0446\u0430 \u0441\u0431\u0440\u043e\u0441\u0430 \u043d\u0435 \u0434\u043e\u043a\u0430\u0437\u0430\u043d\u0430.",
 quotaBoth:"\u041e\u0431\u0435 \u0433\u0438\u043f\u043e\u0442\u0435\u0437\u044b \u0434\u0430\u044e\u0442 \u0442\u043e\u0442 \u0436\u0435 \u043e\u0441\u0442\u0430\u0442\u043e\u043a. \u041f\u0440\u0430\u0432\u0438\u043b\u043e \u0441\u0431\u0440\u043e\u0441\u0430 \u043d\u0435 \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0438\u0442\u044c.",
 quotaNeither:"\u041d\u0438 \u043e\u0434\u043d\u0430 \u0433\u0438\u043f\u043e\u0442\u0435\u0437\u0430 \u043d\u0435 \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u0435\u0442. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u043f\u0440\u043e\u043f\u0443\u0449\u0435\u043d\u043d\u044b\u0435 \u0437\u0430\u043c\u0435\u043d\u044b \u043d\u0430 Sports.ru.",
 quotaUnknown:"\u041d\u0435\u043b\u044c\u0437\u044f \u043f\u043e\u0434\u0441\u0447\u0438\u0442\u0430\u0442\u044c \u043e\u0441\u0442\u0430\u0442\u043e\u043a \u043f\u043e \u0436\u0443\u0440\u043d\u0430\u043b\u0443. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0434\u0430\u0442\u044b \u043e\u043f\u0435\u0440\u0430\u0446\u0438\u0439.",
 unavailable:"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u0441\u0447\u0438\u0442\u0430\u0442\u044c \u043f\u043e \u0438\u043c\u0435\u044e\u0449\u0438\u043c\u0441\u044f \u0434\u0430\u043d\u043d\u044b\u043c.",
 staleResult:"\u0414\u0430\u043d\u043d\u044b\u0435 NBA \u0438\u0437\u043c\u0435\u043d\u0438\u043b\u0438\u0441\u044c \u043f\u043e\u0441\u043b\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438. \u041f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u0435 \u0441\u0432\u0435\u0440\u043a\u0443.",
 teamHeader:"\u041d\u0435 \u0437\u0430\u0431\u0443\u0434\u044c\u0442\u0435 \u043e\u0442\u0434\u0435\u043b\u044c\u043d\u043e \u0441\u0432\u0435\u0440\u0438\u0442\u044c \u0434\u0435\u0441\u044f\u0442\u044c \u0438\u0433\u0440\u043e\u043a\u043e\u0432 \u0438 \u0434\u0430\u0442\u044b \u0437\u0430\u043c\u0435\u043d.",
 quotaTile:"\u0417\u0430\u043c\u0435\u043d\u044b \u00b7 \u0434\u0432\u0435 \u0433\u0438\u043f\u043e\u0442\u0435\u0437\u044b",
 quotaTileNote:"\u041d\u0435 \u0444\u0430\u043a\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u0441\u0447\u0451\u0442\u0447\u0438\u043a Sports.ru",
 cashTile:"\u041a\u0430\u0441\u0441\u0430 \u00b7 \u043f\u043e \u0436\u0443\u0440\u043d\u0430\u043b\u0443",
 cashTileNote:"\u041d\u0435 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0430 \u0432 Sports.ru"
};
const sportsAmt=x=>typeof x==='number'&&Number.isFinite(x)?x.toLocaleString('ru-RU',{maximumFractionDigits:2}):'\u2014';
function sportsResultMarkup(){
 const r=UI.sportsResult;
 if(!r)return '';
 if(!r.valid){const message=r.errors.includes('OWNER_ATTESTATION_REQUIRED')?SRU.needAttest:r.errors.includes('NO_OWNER_FIELDS')?SRU.noInput:SRU.invalid;
  return `<div class="info warning" role="status">${esc(message)}</div>`;}
 const rows=[];
 if(r.checks.fp){const f=r.checks.fp;
  rows.push(`<div class="sports-check-row"><b>${SRU.fp}:</b> ${SRU.fpOwner} <strong>${sportsAmt(f.owner)}</strong> / ${SRU.fpLocal} <strong>${sportsAmt(f.calculatedNBA)}</strong>${f.difference===null?'':`<span>${SRU.delta}: <b>${sportsAmt(f.difference)} FP</b></span>`}<p class="small">${f.difference===null?SRU.unavailable:f.difference===0?SRU.match:SRU.fpMismatch} ${f.kind==='STALE_OR_UNDATED_NBA_FEED'?SRU.fpStale:''} ${SRU.fpCaveat}</p></div>`);
 }
 if(r.checks.cash){const c=r.checks.cash;
  rows.push(`<div class="sports-check-row"><b>${SRU.cash}:</b> ${SRU.fpOwner} <strong>${sportsAmt(c.owner)}</strong> / ${SRU.cashLocal} <strong>${sportsAmt(c.local)}</strong><p class="small">${c.difference===null?SRU.unavailable:c.kind==='AGREES'?SRU.cashMatch:SRU.cashMismatch}</p></div>`);
 }
 if(r.checks.quota){const q=r.checks.quota;
  const text=q.kind==='AGREES_BOTH_UNVERIFIED'?SRU.quotaBoth:q.kind==='AGREES_NEITHER'?SRU.quotaNeither:['AGREES_15_ONLY_UNVERIFIED','AGREES_00_ONLY_UNVERIFIED'].includes(q.kind)?SRU.quotaMatched:SRU.quotaUnknown;
  rows.push(`<div class="sports-check-row"><b>${SRU.quota}:</b> ${SRU.fpOwner} <strong>${sportsAmt(q.owner)}</strong> / ${SRU.quotaLabel} <strong>${sportsAmt(q.localRemaining15)} / ${sportsAmt(q.localRemaining00)}</strong><p class="small">${text}</p></div>`);
 }
 const stale=!!r.checks.fp&&Date.parse(r.checks.fp.sourceUpdatedAtUtc||'')!==Date.parse(LIVE.updated_at_utc||'');
 return `<div class="sports-check-result" role="status" aria-live="polite"><h3>${SRU.report}</h3><p class="small">${SRU.captured}: ${esc(dateText(Date.parse(r.capturedAtUtc)))}</p>${stale?`<p class="warntext">${SRU.staleResult}</p>`:''}${rows.join('')}<p class="small">${SRU.teamHeader}</p></div>`;
}
function sportsCheckPanel(){
 const vals=UI.sportsInputs||{fp:'',cash:'',remaining:''};
 return `<section class="card sports-check-card" id="sports-check"><div class="titledetail"><div><h2>${SRU.title}</h2><p class="small">${SRU.lead}</p></div><button class="button" type="button" data-action="sports-check-toggle" aria-expanded="${UI.sportsOpen}">${UI.sportsOpen?SRU.close:SRU.open}</button></div>
 ${UI.sportsOpen?`<div class="sports-check-form"><div class="formgrid">
 <label for="sports-fp">${SRU.fp}<input id="sports-fp" type="text" inputmode="decimal" autocomplete="off" placeholder="FP" value="${esc(vals.fp)}"></label>
 <label for="sports-cash">${SRU.cash}<input id="sports-cash" type="text" inputmode="decimal" autocomplete="off" placeholder="0-20000" value="${esc(vals.cash)}"></label>
 <label for="sports-remaining">${SRU.quota}<input id="sports-remaining" type="number" inputmode="numeric" min="0" max="3" step="1" autocomplete="off" placeholder="0-3" value="${esc(vals.remaining)}"></label>
 </div><label class="sports-attest"><input id="sports-confirm" type="checkbox"> ${SRU.attest}</label>
 <div class="toolbar"><button class="primary" data-action="sports-check-run" type="button">${SRU.run}</button></div>
 <p class="small">${SRU.privacy}</p>${sportsResultMarkup()}</div>`:''}</section>`;
}
function sportsCheckRun(){
 const mod=window.NBASportsReconciliation;
 if(!mod)return showMsg(SRU.unavailable);
 const owner={fp:document.getElementById('sports-fp')?.value||'',
  cash:document.getElementById('sports-cash')?.value||'',
  remaining:document.getElementById('sports-remaining')?.value||'',
  confirmedNow:document.getElementById('sports-confirm')?.checked===true};
 UI.sportsInputs={fp:owner.fp,cash:owner.cash,remaining:owner.remaining};
 UI.sportsResult=mod.compare({owner,nowEpoch:now(),weekKey:window.NBATransferGuard.weekKey,
  service:{calculatedNBAFP:actualTotal().fp,initialRosterCount:S.initialRoster?.length,
   cash:S.cash,executed:S.executed,feedUpdatedAtUtc:LIVE?.updated_at_utc}});
 UI.sportsOpen=true;view();document.getElementById('sports-check')?.scrollIntoView({block:'start',behavior:'instant'});
}

function quotaNote(nowMs){
 const a=moscowWeek(nowMs),b=calendarMoscowWeek(nowMs);
 return a!==b?'Ориентир Sports.ru до Пн 15:00 МСК; две границы недель различаются':'По границе Пн 15:00 МСК; точный сброс проверьте на Sports.ru';
}
function halfCourtSvg(){return `<svg class="court-lines" viewBox="0 0 520 420" preserveAspectRatio="none" aria-hidden="true" focusable="false">
 <rect x="7" y="7" width="506" height="406" rx="13" stroke="currentColor" fill="none"/>
 <path d="M201 7 V142 H319 V7 M228 7 V97 H292 V7" stroke="currentColor" fill="none"/>
 <circle cx="260" cy="53" r="13" stroke="currentColor" fill="none"/>
 <path d="M236 28 H284" stroke="currentColor" fill="none"/>
 <path d="M201 142 A59 59 0 0 0 319 142" stroke="currentColor" fill="none" stroke-dasharray="5 8"/>
 <path d="M65 7 V80 A202 202 0 0 0 455 80 V7" stroke="currentColor" fill="none"/>
 <path d="M201 411 A59 59 0 0 1 319 411" stroke="currentColor" fill="none"/>
 </svg>`;}
function courtPlayer(pid,pos){
 const p=P[pid];if(!p)return `<div class="court-player court-player--${pos.toLowerCase()} court-placeholder"><span class="court-role">${esc(pos)}</span><span>Нет игрока</span></div>`;
 const a=prediction(pid,now(),7);
 const official=officialForRoster().find(e=>e.playerId===pid);
 const high=!!official&&window.NBAOfficialStatus?.isHighRisk(official.status);
 const manuallyOut=S.medical?.[pid]==='out';
 const risk=manuallyOut?'Указан OUT':official?(high?'NBA: '+official.status.toUpperCase():'NBA: '+official.status.toUpperCase()):null;
 return `<button type="button" class="court-player court-player--${pos.toLowerCase()} ${high||manuallyOut?'court-player-risk':''}" data-player="${esc(pid)}" aria-label="${esc(p.name)}, ${pos}, ${esc(p.team)}. Открыть профиль игрока">
  <span class="court-card-top"><span class="court-role">${pos}</span><span class="court-club">${esc(p.team)}</span></span>
  <strong class="court-player-name">${esc(p.name)}</strong>
  <span class="court-player-price">≈ ${round(prices(pid))} · цена*</span>
  <span class="court-player-pred">${a.available?`${a.games} игр · ${round(a.fp)} FP / 7 дн.`:'Прогноз: н/д'}</span>
  ${risk?`<span class="court-risk-label">${esc(risk)}</span>`:''}
 </button>`;
}
function teamCourt(){
 const grouped=window.NBATeamCourtLayout?.group(S.roster,P);
 const byPosition=grouped?.byPosition||Object.fromEntries(POS.map(pos=>[pos,S.roster.filter(id=>P[id]?.pos===pos)]));
 return `<div class="court-pair" aria-label="Моя команда на баскетбольной площадке">${[0,1].map(i=>`<section class="half-court" aria-label="Пятёрка ${i+1}">
  <div class="court-head"><strong>Пятёрка ${i+1}</strong><span>1 × PG · SG · SF · PF · C</span></div>
  <div class="court-surface">${halfCourtSvg()}
  ${['PG','SG','SF','PF','C'].map(pos=>courtPlayer(byPosition[pos][i],pos)).join('')}
  </div></section>`).join('')}</div>`;
}
function teamRosterPanel(){
 const court=UI.teamView!=='list';
 return `<section class="card team-roster-panel"><div class="titledetail team-roster-header"><div><h2>Мои 10 игроков</h2><p class="small">Две условные пятёрки, обе участвуют в fantasy. Нажмите на игрока для статистики.</p></div>
 <div class="view-switch" role="group" aria-label="Представление состава"><button type="button" data-team-view="court" class="${court?'selected':''}" aria-pressed="${court}">Площадка</button><button type="button" data-team-view="list" class="${!court?'selected':''}" aria-pressed="${!court}">Список</button></div></div>
 ${court?teamCourt():POS.map(pos=>`<div class="poshead">${esc(POSRU[pos])} · ${pos}</div>`+S.roster.filter(id=>P[id]?.pos===pos).map(id=>rosterRow(P[id])).join('')).join('')}
 <p class="court-source-note">* Цены ориентировочные, если не подтверждены вручную. FP — модельный прогноз по календарю, не зачёт Sports.ru.</p></section>`;
}

function todayPage(){
 const tick=now(), valid=advicePreflight(21,tick),complete=valid.rosterReady;
 const updated=Date.parse(LIVE?.updated_at_utc||'');
 const liveAge=Number.isFinite(updated)?(tick-updated)/3600000:NaN;
 const feedMode=publicFeedValidated?LIVE?.mode:'unverified';
 const short=calendarCoverage(tick,7),long=calendarCoverage(tick,21);
 const official=complete?officialForRoster().filter(e=>!e.stale&&window.NBAOfficialStatus?.isHighRisk(e.status)):[];
 const officialRiskNames=[...new Set(official.map(e=>P[e.playerId]?.name||e.playerName))];
 const manualOutCount=complete?S.roster.filter(id=>S.medical?.[id]==='out').length:0;
 const telegramCount=complete?S.roster.filter(id=>rosterNews(id).length).length:0;
 const result=valid.ready&&UI.multiResult?.signature===chainSignature()&&UI.multiCalculatedAt&&tick-UI.multiCalculatedAt<30*60000?UI.multiResult:null;
 const best=result?.ready&&result.horizonDays===21?result.routes?.[0]:null;
 const verifiedExplanation=best?explainMulti(best,result)?.ready===true:false;
 const forecast7=complete&&valid.feedReady&&short.ok?projectionPeriod(S.roster,7):NaN;
 const forecast21=complete&&valid.feedReady&&long.ok?projectionPeriod(S.roster,21):NaN;
 const games7=complete&&short.ok?S.roster.reduce((n,id)=>n+futureGames(id,tick,7).length,0):null;
 const games21=complete&&long.ok?S.roster.reduce((n,id)=>n+futureGames(id,tick,21).length,0):null;
 const reportQuality=window.NBAOfficialStatus?.validate(OFFICIAL_FEED);
 const officialFeedReady=!!reportQuality?.ok&&Number.isFinite(reportQuality.updatedAt)
   &&tick>=reportQuality.updatedAt&&tick-reportQuality.updatedAt<=12*3600000;
 const brief=window.NBATodayBrief?.build({rosterCount:S.roster?.length||0,rosterValid:valid.rosterReady,cashReady:valid.cashReady,feedVerified:publicFeedValidated,feedAgeHours:liveAge,feedMode,officialFeedReady,
  calendar7:short.ok,calendar21:long.ok,officialRiskNames,manualOutCount,telegramCount,
  fp7:forecast7,fp21:forecast21,games7,games21,
  resultFresh:!!best,bestRoute:best,bestExplanationVerified:verifiedExplanation})||{state:'blocked',title:'Не удалось загрузить модуль решений',description:'Проверь источники и повтори после обновления.',reasons:['Расчётные показатели временно недоступны.'],shortFP:null,longFP:null,games7:null,games21:null};
 const primary=brief.state==='onboarding'||brief.state==='fix_roster'
   ?'<button type="button" class="primary today-primary" data-tabto="overview">Добавить состав</button>'
   :brief.state==='blocked'
     ?'<button type="button" class="primary today-primary" data-tabto="data">Проверить источники</button>'
     :brief.state==='risk'
       ?'<button type="button" class="primary today-primary" data-tabto="news">Проверить статусы игроков</button>'
       :'<button type="button" class="primary today-primary" data-action="today-review">Сравнить варианты замен</button>';
 const secondary=brief.state==='onboarding'?''
   :brief.state==='risk'?'<button type="button" class="button" data-action="today-review">Сравнить после проверки риска</button>'
   :brief.state==='blocked'?'<button type="button" class="button" data-tabto="planner">Открыть планировщик</button>'
   :'<button type="button" class="button" data-tabto="overview">Моя команда</button>';
 const fact=(fp,games,days)=>`<section class="today-window"><div class="today-window-head"><b>${days} ${days===21?'день':'дней'}</b><span>${games===null?'Матчи: н/д':games+' игроко-матчей'}</span></div><strong>${fp===null?'н/д':round(fp,1)+' FP'}</strong><p>${fp===null?'Нет проверенного прогноза':'Ожидаемые очки текущей десятки без новых замен'}</p></section>`;
 const reasons=brief.reasons.map((r,i)=>`<li><span aria-hidden="true">${i+1}</span><p>${esc(r)}</p></li>`).join('');
 const topGames=complete&&short.ok?normalizedGames().filter(g=>g.epoch>tick&&g.epoch<=tick+7*86400000&&g.status!=='final'&&S.roster.some(id=>P[id]?.team===g.home||P[id]?.team===g.away)).slice(0,4):[];
 const nextLock=topGames.map(g=>g.epoch-30*60000).filter(x=>x>tick).sort((a,b)=>a-b)[0];
 const quota15=complete&&S.executed.every(x=>Number.isFinite(x.epoch))?S.executed.filter(x=>moscowWeek(x.epoch)===moscowWeek(tick)).length:null;
 const quota00=complete&&S.executed.every(x=>Number.isFinite(x.epoch))?S.executed.filter(x=>calendarMoscowWeek(x.epoch)===calendarMoscowWeek(tick)).length:null;
 const quotaText=quota15===null||quota00===null?'н/д':quota15===quota00?quota15+'/3 · обе гипотезы':quota15+'/3 или '+quota00+'/3';
 const rows=topGames.map(g=>`<div class="today-game"><span><b>${esc(g.away)} @ ${esc(g.home)}</b><small>${esc(S.roster.filter(id=>P[id]?.team===g.home||P[id]?.team===g.away).map(id=>P[id]?.name).filter(Boolean).join(', '))}</small></span><time>${dateText(g.epoch)} МСК</time></div>`).join('');
 if(brief.state==='onboarding'||brief.state==='fix_roster')return `<header class="today-heading"><div><div class="eyebrow">Твой ежедневный обзор</div><h1>Нужна ли замена сегодня?</h1><p class="sub">Для начала внеси десятку с Sports.ru.</p></div></header><section class="card today-decision today-onboarding"><div class="today-kicker">ПЕРВЫЙ ШАГ</div><h2>${esc(brief.title)}</h2><p class="today-lead">${esc(brief.description)}</p><div class="today-actions">${primary}</div><p class="today-disclaimer">После этого будут доступны календарь, риски и сравнение вариантов. Сервис не делает трансферы сам.</p></section>`;
 return `<header class="today-heading"><div><div class="eyebrow">Твой ежедневный обзор</div><h1>Нужна ли замена сегодня?</h1><p class="sub">Сначала решение. Подробные расчёты — только если понадобятся.</p></div></header>
 <div class="today-main"><section class="card today-decision today-decision--${esc(brief.state)}"><div class="today-kicker">ЧТО ДЕЛАТЬ</div>
 <h2>${esc(brief.title)}</h2><p class="today-lead">${esc(brief.description)}</p>
 <ol class="today-reasons">${reasons}</ol>
 <div class="today-actions">${primary}${secondary}</div>
 <p class="today-disclaimer">Сценарный совет не доказывает реальную выгоду. Трансферы выполняются только на Sports.ru.</p></section>
 <aside class="today-aside"><section class="card today-why"><h3>Надёжность данных</h3><div class="today-proof"><span>Статистика NBA</span><b>${valid.feedReady?'Проверена · '+Math.floor(valid.feedAgeHours)+' ч назад':'Не подтверждена'}</b></div><div class="today-proof"><span>Календарь · 7 дней</span><b>${short.ok?'Доступен':'Не подтверждён'}</b></div><div class="today-proof"><span>Календарь · 21 день</span><b>${long.ok?'Доступен':'Не подтверждён'}</b></div><div class="today-proof"><span>Модель FP</span><b>Точность решений не доказана</b></div><div class="today-proof"><span>Замены по журналу</span><b>${quotaText}</b></div><p>Счётчики по двум гипотезам сброса. Фактический остаток — на Sports.ru.</p></section></aside></div>
 <section class="today-section" aria-label="Короткий и длинный горизонт"><div class="today-section-title"><h2>Ближайшая неделя и три недели</h2><span>FP — очки в Fantasy NBA</span></div><div class="today-windows">${fact(brief.shortFP,brief.games7,7)}${fact(brief.longFP,brief.games21,21)}</div><p class="today-footnote">Это модельные ожидания по текущему составу, а не очки, начисленные Sports.ru. Сложность соперников пока не оценена достоверно: число матчей не равно их качеству.</p></section>
 ${short.ok?`<section class="card today-schedule"><div class="titledetail"><div><h2>Что дальше по расписанию</h2><p>Матчи твоих игроков, ближайшие 7 дней.</p></div><button type="button" class="ghost" data-tabto="calendar">Весь календарь</button></div>
 ${rows||'<p class="muted">Нет подтверждённых ближайших матчей. Не считай это доказательством, что команда не играет.</p>'}
 ${Number.isFinite(nextLock)?`<p class="today-lock">Ближайшая потенциальная блокировка: ${dateText(nextLock)} МСК (за 30 минут до матча).</p>`:''}</section>`:''}`;
}

function overview(){
 const at=actualTotal();
 const historyValid=Array.isArray(S.executed)&&S.executed.every(t=>Number.isFinite(t?.epoch)&&t.epoch<=now());
 const q15=historyValid?S.executed.filter(t=>moscowWeek(t.epoch)===moscowWeek(now())).length:null;
 const q00=historyValid?S.executed.filter(t=>calendarMoscowWeek(t.epoch)===calendarMoscowWeek(now())).length:null;
 const remaining15=q15!=null&&q15<=3?3-q15:null;
 const remaining00=q00!=null&&q00<=3?3-q00:null;
 const quotaText=(remaining15==null?'\u043d/\u0434':remaining15)+' / '+(remaining00==null?'\u043d/\u0434':remaining00);
 const thisWeekEnd=weekEnd(now()),enddays=Math.max(0,(thisWeekEnd-now())/86400000);
 const remainingMean=projectionPeriod(S.roster,enddays),free=S.cash;
 const ng=normalizedGames().filter(g=>g.epoch>now()&&(S.roster||[]).some(id=>P[id]?.team===g.home||P[id]?.team===g.away)).slice(0,5);
 const stale=(now()-Date.parse(LIVE.updated_at_utc||0))>24*3600e3||LIVE.mode==='schedule_sync_only';
 return header('Команда','Мой состав','Десять игроков, календарь и ближайшее решение. Состав на Sports.ru изменяется только вручную.')+rosterWarnings()+
 `<div class="grid metrics">${cardMetric('NBA boxscore · не Sports.ru',round(at.fp)+' FP',at.matches+' сыгранных игроко-матчей')}
 ${cardMetric('До конца недели · модель',Number.isFinite(remainingMean)?approx(remainingMean)+' FP':'н/д',Number.isFinite(remainingMean)?'Ожидаемые FP, не зачёт':'Календарь недостаточно полон')}
 ${cardMetric(SRU.cashTile,round(free),SRU.cashTileNote)}
 ${cardMetric(SRU.quotaTile,quotaText,SRU.quotaTileNote)}</div>
 <div class="team-layout"><div>${teamRosterPanel()}</div><aside class="team-aside">
 <section class="card team-next-action"><div class="eyebrow">Следующее решение</div><h2>Стоит ли менять состав?</h2><p>Сравним оставить десятку, заменить сейчас или позже, учитывая календарь и кассу.</p><button class="primary" data-tabto="planner">Сравнить варианты</button></section>
 <section class="card"><div class="titledetail"><h2>Ближайшие матчи состава</h2><button class="ghost" data-tabto="calendar">Весь календарь</button></div>${ng.length?ng.map(g=>{const own=S.roster.filter(id=>P[id]?.team===g.home||P[id]?.team===g.away).map(id=>P[id].name).join(', ');return `<div class="lined"><div class="horizontal"><b>${esc(g.away)} @ ${esc(g.home)}</b><span class="spacer"></span><span class="small">${dateText(g.epoch)}</span></div><div class="small">${esc(own)}</div></div>`;}).join(''):'<div class="empty">Нет подтверждённых ближайших игр в имеющемся календаре.</div>'}</section>
 </aside></div>
 ${sportsCheckPanel()}
 <details class="card deep-details"><summary>Как посчитаны очки и насколько свежие данные?</summary>${scoreAuditPanel(at)}
 <div class="horizontal" style="margin-top:12px"><span class="pill ${stale?'warn':'good'}">${esc(currentStatus())}</span><button class="button" data-tabto="data">Источники и цены</button></div>
 <p class="small">NBA boxscore и зачёт Sports.ru могут расходиться. Для точного сравнения используйте официальные очки Sports.ru.</p></details>`;
}
function weekEnd(ms){return window.NBATransferGuard.calendarWeekEnd(ms);} // 00:00 MSK next Monday, not 15:00 deadline
function canReplaceWith(p){
 if(S.roster.length!==10||S.roster.includes(p.id)||!Number.isFinite(prices(p.id)))return false;
 return S.roster.some(out=>{
  const old=P[out];if(!old||old.pos!==p.pos||prices(p.id)>S.cash+prices(out))return false;
  const alt=S.roster.map(id=>id===out?p.id:id);
  return hardCheck(alt).valid;
 });
}
function playerList(){
 let rows=BASE.players.filter(p=>(UI.position==='all'||p.pos===UI.position)&&(UI.club==='all'||p.team===UI.club));
 const q=UI.search.trim().toLocaleLowerCase('ru-RU');
 if(q)rows=rows.filter(p=>(p.name+' '+p.english+' '+p.team).toLocaleLowerCase('ru-RU').includes(q));
 if(S.roster.length===10){
  if(UI.marketView==='mine')rows=rows.filter(p=>S.roster.includes(p.id));
  if(UI.marketView==='candidates')rows=rows.filter(canReplaceWith);
  if(UI.marketView==='candidates'&&UI.marketFocusPlayer&&S.roster.includes(UI.marketFocusPlayer)){
   const focus=P[UI.marketFocusPlayer];
   rows=rows.filter(p=>p.pos===focus.pos&&p.id!==focus.id&&
    prices(p.id)<=S.cash+prices(focus.id)&&
    hardCheck(S.roster.map(id=>id===focus.id?p.id:id)).valid);
  }
 }
 const days=UI.window;
 function key(p){
  if(UI.sort==='price')return prices(p.id);
  if(UI.sort==='expert')return p.expert_pop??-1;
  if(UI.sort==='historic')return p.history.at(-1)?.fp_avg??-1;
  if(UI.sort==='minutes')return p.minutes_projection??-1;
  if(UI.sort==='games')return futureGames(p.id,now(),days).length;
  const f=prediction(p.id,now(),days);
  return f.available&&Number.isFinite(f.fp)?f.fp:-1e12;
 }
 const keys=new Map(rows.map(p=>[p.id,key(p)]));
 rows.sort((a,b)=>keys.get(b.id)-keys.get(a.id)||a.name.localeCompare(b.name,'ru'));
 return rows;
}
function playersPage(){
 const options=POS.map(p=>`<option value="${p}" ${UI.position===p?'selected':''}>${p} — ${esc(POSRU[p])}</option>`).join('');
 const clubs=[...new Set(BASE.players.map(x=>x.team))].sort().map(x=>`<option value="${esc(x)}" ${UI.club===x?'selected':''}>${esc(x)}</option>`).join('');
 const full=S.roster.length===10;
 const rows=playerList(),visible=rows.slice(0,UI.marketLimit);
 const cards=visible.map(p=>{
  const forecast=prediction(p.id,now(),UI.window);
  const count=forecast.available?forecast.games:null;
  const mine=S.roster.includes(p.id);
  return `<article class="market-item ${mine?'market-owned':''}"><div class="market-identity"><button class="ghost personname" data-player="${esc(p.id)}">${esc(p.name)}</button><span class="market-club">${esc(p.team)} · ${esc(p.pos)}</span></div>
   <div class="market-stat"><b>${round(prices(p.id))}</b><small>цена*</small></div>
   <div class="market-stat"><b>${count===null?'н/д':count}</b><small>игры / ${UI.window} дн.</small></div>
   <div class="market-stat market-projected"><b>${forecast.available?round(forecast.fp,1):'н/д'}</b><small>прогноз FP</small></div>
   <button class="market-compare" aria-label="${UI.compare.includes(p.id)?'Убрать из сравнения':'Добавить в сравнение'} ${esc(p.name)}" data-compare="${esc(p.id)}">${UI.compare.includes(p.id)?'✓':'+'}</button></article>`;
 }).join('');
 return header('Игроки','Найти кандидата','Сначала выберите, кого смотреть. Подробная статистика открывается нажатием на имя.')+
 `<div class="card"><div class="market-quick-filters" role="group" aria-label="Кого показывать">
 <button data-market-view="candidates" ${!full?'disabled':''} class="${UI.marketView==='candidates'&&full?'selected':''}" aria-pressed="${UI.marketView==='candidates'&&full}">Возможные замены</button>
 <button data-market-view="mine" ${!full?'disabled':''} class="${UI.marketView==='mine'&&full?'selected':''}" aria-pressed="${UI.marketView==='mine'&&full}">Моя десятка</button>
 <button data-market-view="all" class="${UI.marketView==='all'||!full?'selected':''}" aria-pressed="${UI.marketView==='all'||!full}">Все игроки</button></div>
 ${UI.marketFocusPlayer&&S.roster.includes(UI.marketFocusPlayer)?`<div class="intent-context"><span>Подбор для <b>${esc(P[UI.marketFocusPlayer]?.name||UI.marketFocusPlayer)}</b> · ${esc(P[UI.marketFocusPlayer]?.pos||'')}</span><button type="button" class="button" data-player-intent="replace" data-intent-player="${esc(UI.marketFocusPlayer)}">К расчёту замены</button><button type="button" class="ghost" data-clear-intent="players">Сбросить</button></div>`:''}
 <div class="toolbar market-main-controls"><label class="market-search">Поиск<input id="search" type="search" placeholder="Имя игрока или клуб" value="${esc(UI.search)}"></label>
 <label>Период<select id="window">${[7,14,28].map(d=>`<option value="${d}" ${UI.window===d?'selected':''}>${d} дней</option>`).join('')}</select></label>
 <label>Ранжировать<select id="sort"><option value="week" ${UI.sort==='week'?'selected':''}>По прогнозу FP</option><option value="games" ${UI.sort==='games'?'selected':''}>По числу игр</option><option value="price" ${UI.sort==='price'?'selected':''}>По цене</option><option value="historic" ${UI.sort==='historic'?'selected':''}>По FP/матч 25/26</option></select></label></div>
 <button type="button" class="ghost market-advanced-toggle" data-action="market-advanced" aria-expanded="${UI.marketAdvanced}">${UI.marketAdvanced?'Скрыть фильтры':'Фильтры по позиции и клубу'}</button>
 ${UI.marketAdvanced?`<div class="toolbar market-advanced"><label>Позиция<select id="pos"><option value="all">Любая позиция</option>${options}</select></label><label>Клуб<select id="club"><option value="all">Все клубы</option>${clubs}</select></label></div>`:''}
 ${full&&UI.marketView==='candidates'?'<p class="small">Показаны игроки, которых можно условно приобрести, продав одного игрока той же позиции при текущей кассе и расчётных ценах. Блокировки, статус и реальную стоимость нужно проверить на Sports.ru.</p>':''}
 ${UI.compare.length?`<div class="market-compare-bar">${UI.compare.map(id=>`<button data-uncompare="${esc(id)}">× ${esc(P[id]?.name||id)}</button>`).join('')}<button class="primary" data-action="compare">Сравнить (${UI.compare.length})</button></div>`:'<p class="small">Сравнение: отметьте 2–4 игроков кнопкой «+» справа.</p>'}
 <div class="market-items" aria-label="Игроки">${cards||'<p class="empty">Для заданных условий игроков не найдено. Попробуйте другой фильтр.</p>'}</div>
 <div class="market-footer"><span class="small">Показано ${visible.length} из ${rows.length}. «н/д» — нет подтверждённого прогноза, не 0 FP.</span>${rows.length>visible.length?`<button class="button" data-action="market-more">Показать ещё ${Math.min(50,rows.length-visible.length)}</button>`:''}</div>
 </div>`;
}
function playerModal(id){const p=P[id];if(!p)return '';const recent=playerActual(id);const hist=p.history||[];const nbaHist=NBA_HISTORY?.players?.[id]||[];const pred7=prediction(id,now(),7),pred14=prediction(id,now(),14);const futures=futureGames(id,now(),14);
 return `<div class="titledetail"><div><div class="eyebrow">${p.team} · ${p.pos}</div><h2 style="margin:4px 0">${esc(p.name)}</h2><div class="small">${esc(p.english)}</div></div><button class="close" data-action="close-modal" aria-label="Закрыть">×</button></div><div class="tagline"><span class="tag">Цена*: ${round(prices(id))}</span><span class="tag">КЭ: ${p.expert_pop!=null?round(p.expert_pop,1)+'%':'—'}</span>${displayRisk(p)}</div><div class="grid stats-mini" style="margin:16px 0"><div><span class="stat-label">FP при выходе (модель)</span><strong>${p.forecast?approx(learnedMean(p,futures[0]||{epoch:now(),id:'',home:p.team,away:''})):'н/д'}</strong></div><div><span class="stat-label">FP / 7 дней</span><strong>${pred7.available?round(pred7.fp):'—'}</strong></div><div><span class="stat-label">FP / 14 дней</span><strong>${pred14.available?round(pred14.fp):'—'}</strong></div></div>
 <div class="player-decision-actions" role="group" aria-label="Действия с игроком">${S.roster.includes(id)?`<button type="button" class="primary" data-player-intent="replace" data-intent-player="${esc(id)}">Подобрать замену</button>`:`<button type="button" class="primary" data-player-intent="players" data-intent-player="${esc(id)}">Похожие кандидаты</button>`}<button type="button" class="button" data-player-intent="calendar" data-intent-player="${esc(id)}">Ближайшие игры</button></div>
 <h3>История fantasy за три сезона</h3><div class="tablewrap"><table><thead><tr><th>Сезон</th><th>Клуб</th><th class="num">Игры</th><th class="num">Всего FP</th><th class="num">FP/матч</th><th>Поматчевые</th></tr></thead><tbody>${hist.map(h=>`<tr><td>${h.season}</td><td>${esc(h.team)}</td><td class="num">${h.games}</td><td class="num">${round(h.total)}</td><td class="num">${h.fp_avg??'—'}</td><td>${h.log_valid?'<span class="pill good">полный ряд</span>':'<span class="pill warn">частично</span>'}</td></tr>`).join('')||'<tr><td colspan="6">История отсутствует</td></tr>'}</tbody></table></div>
 <h3 class="subheading">Текущий сезон · реальные матчи</h3>${recent.length?`<div class="tablewrap"><table><thead><tr><th>Дата МСК</th><th>Мин.</th><th class="num">PTS</th><th class="num">REB</th><th class="num">AST</th><th class="num">FP</th></tr></thead><tbody>${recent.slice(-10).reverse().map(r=>`<tr><td>${dateText(r.utc)}</td><td>${round(r.minutes,0)}</td><td class="num">${r.box?.pts??'—'}</td><td class="num">${r.box?.reb??'—'}</td><td class="num">${r.box?.ast??'—'}</td><td class="num"><b>${round(r.fp)}</b></td></tr>`).join('')}</tbody></table></div>`:'<div class="info">В загруженной NBA-статистике ещё нет сыгранных матчей. Это не подтверждение отсутствия игр.</div>'}
 <h3 class="subheading">Ближайший календарь</h3>${futures.length?futures.map(g=>`<div class="lined">${dateText(g.epoch)} · <b>${g.home===p.team?g.away+' дома':'@'+g.home+' в гостях'}</b> · ${approx(learnedMean(p,g))} FP при выходе · вероятность участия (модель) ${round(probability(p,g)*100)}%</div>`).join(''):'<p>Пока нет загруженного расписания на следующие 14 дней.</p>'}
 <h3 class="subheading">Медицинский сценарий</h3><div class="toolbar"><label>Ручной статус<select id="medical" data-id="${p.id}"><option value="default" ${(S.medical[id]||'default')==='default'?'selected':''}>Без подтверждённой поправки</option><option value="available" ${S.medical[id]==='available'?'selected':''}>Могу подтвердить готовность</option><option value="questionable" ${S.medical[id]==='questionable'?'selected':''}>Сомнительный / сниженный шанс</option><option value="out" ${S.medical[id]==='out'?'selected':''}>Подтверждён OUT</option></select></label></div><div class="info warning">Этот переключатель меняет только ваш сценарный расчёт. Статус не устанавливается автоматически из Telegram.</div>${p.news?`<details><summary>Ранний контекст (${esc(p.news_date||'дата неизвестна')})</summary><p>${esc(p.news)}</p></details>`:''}`;
}
function compareModal(){const ids=UI.compare;return `<div class="titledetail"><h2>Сравнение ${ids.length} игроков</h2><button class="close" data-action="close-modal">×</button></div><div class="tablewrap"><table><thead><tr><th>Метрика</th>${ids.map(id=>`<th>${esc(P[id].name)}</th>`).join('')}</tr></thead><tbody>${[['Клуб',p=>p.team],['Позиция',p=>p.pos],['Цена*',p=>round(prices(p.id))],['FP/игра 25/26',p=>p.history.at(-1)?.fp_avg??'—'],['FP/7 дней',p=>prediction(p.id,now(),7).available?round(prediction(p.id,now(),7).fp):'—'],['FP/14 дней',p=>prediction(p.id,now(),14).available?round(prediction(p.id,now(),14).fp):'—'],['Игр/14 дней',p=>prediction(p.id,now(),14).available?prediction(p.id,now(),14).games:'—'],['КЭ',p=>p.expert_pop==null?'—':round(p.expert_pop,1)+'%']].map(([label,get])=>`<tr><td>${label}</td>${ids.map(id=>`<td>${esc(get(P[id]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div><div class="info warning" style="margin-top:14px">Сравнивайте не только FP. При покупке проверьте остаток денег, позицию и максимум двух из клуба. Прогнозы — не фактические результаты.</div>`;}
function teamCalendarQuick(){
 const days=UI.calendarTeamDays;
 const complete=calendarCoverage(now(),days);
 const members=S.roster.map(id=>P[id]).filter(Boolean);
 if(!members.length)return '<div class="card"><p>Чтобы увидеть расписание своей десятки, сначала сохраните состав на странице «Команда».</p><button class="button" data-tabto="overview">Перейти к команде</button></div>';
 const cards=members.map(p=>({p,games:futureGames(p.id,now(),days)}));
 const focused=UI.calendarFocusPlayer&&S.roster.includes(UI.calendarFocusPlayer)?UI.calendarFocusPlayer:null;
 if(focused)cards.sort((a,b)=>(a.p.id===focused?-1:0)-(b.p.id===focused?-1:0));
 cards.sort((a,b)=>(focused?(a.p.id===focused?-1:b.p.id===focused?1:0):0)||b.games.length-a.games.length||a.p.name.localeCompare(b.p.name,'ru'));
 const playerGames=cards.reduce((sum,x)=>sum+x.games.length,0);
 const distinct=new Set(cards.flatMap(x=>x.games.map(g=>g.id||g.home+'-'+g.away+'-'+g.epoch))).size;
 return `<div class="card calendar-quick-card"><div class="titledetail"><div><h2>Игры моей десятки</h2><p class="small">Матчи за ${days} дней · время МСК, игровой тур определяется датой NBA (ET).</p></div></div>
 ${focused?`<div class="intent-context"><span>Ближайшие матчи: <b>${esc(P[focused]?.name||focused)}</b> — первый в списке</span><button type="button" class="button" data-player-intent="replace" data-intent-player="${esc(focused)}">Подобрать замену</button><button type="button" class="ghost" data-clear-intent="calendar">Все десять</button></div>`:''}
 <div class="calendar-quick-switch" role="group" aria-label="Длина периода">${[7,14,28].map(d=>`<button type="button" data-team-days="${d}" class="${days===d?'selected':''}" aria-pressed="${days===d}">${d} дней</button>`).join('')}</div>
 ${complete.ok?`<div class="calendar-quick-summary"><div><strong>${playerGames}</strong><span>игроко-матчей у десятки</span></div><div><strong>${distinct}</strong><span>разных матчей NBA</span></div></div>`:
 `<div class="info warning" role="status"><b>Количество игр не подтверждено.</b> ${esc(complete.reason)}. Не воспринимайте неполный календарь как 0 игр.</div>`}
 <div class="calendar-team-list">${cards.map(({p,games})=>{
  const forecast=prediction(p.id,now(),days);
  const scheduleContext=window.NBACalendarContext?.describe(normalizedGames(),p.team,now(),now()+days*86400000,complete.ok);
  const restLabel=scheduleContext?.ready?`${scheduleContext.b2b} B2B · ${scheduleContext.shortRest} с 1 днём отдыха${scheduleContext.unknownRest?' · отдых не везде известен':''}`:'Ритм игр н/д';
  const preview=games.slice(0,3).map(g=>`${dateText(g.epoch)} · ${g.home===p.team?'против '+g.away:'@ '+g.home}`).join(' | ');
  return `<div class="calendar-team-row"><button type="button" class="ghost personname" data-player="${esc(p.id)}">${esc(p.name)}</button><span class="calendar-team-meta">${esc(p.pos)} · ${esc(p.team)}</span>
   <strong class="calendar-team-games">${complete.ok?games.length:'н/д'} <small>игр</small></strong>
   <span class="calendar-team-next">${preview?esc(preview):complete.ok?'Нет матчей в этом периоде':'Проверьте расписание после обновления'}</span>
   <span class="calendar-team-forecast">${forecast.available?round(forecast.fp,1)+' FP · модель':'прогноз н/д'}<small class="calendar-rest-hint">${esc(restLabel)}</small></span></div>`;
 }).join('')}</div>
 <div class="horizontal" style="margin-top:16px"><button class="primary" data-tabto="planner">Сравнить замены на период</button><span class="small">Игр больше не значит автоматически больше FP: учитываются минуты и участие.</span></div></div>`;
}
function calendarPage(){
 const full=UI.calendarQuick==='full';
 const mode=UI.calendarMode==='window'?'window':'tours';
 return header('Календарь','Игры и игровые окна','Ближайшие матчи своих игроков — сначала. Подробный календарь всех клубов доступен отдельно.')+
 '<p class="calendar-novice-hint"><b>Как читать:</b> больше игр означает больше потенциальных выходов, но не гарантирует больше FP. <b>B2B</b> — два матча подряд по календарным дням NBA: это фактор нагрузки, а не доказанная потеря FP. Рейтинг сложности соперников пока не подтверждён.</p>'+
 `<div class="view-switch calendar-page-switch" role="group" aria-label="Представление календаря"><button type="button" data-calendar-quick="team" class="${!full?'selected':''}" aria-pressed="${!full}">Мои игроки</button><button type="button" data-calendar-quick="full" class="${full?'selected':''}" aria-pressed="${full}">Все клубы и туры</button></div>`+
 (full?`<div class="card calendar-mode-picker"><div class="horizontal" style="align-items:center"><label class="compact" for="cal-view">Подробный календарь<select id="cal-view"><option value="tours" ${mode==='tours'?'selected':''}>По турам NBA (ET)</option><option value="window" ${mode==='window'?'selected':''}>Произвольный диапазон</option></select></label><span class="small">Ночные игры понедельника МСК могут принадлежать воскресному туру NBA (ET). Время матчей — МСК.</span></div></div>`+(mode==='tours'?calendarToursPage():calendarWindowPage()):teamCalendarQuick());
}
function calendarPeriodTable(groups,mode){
 const T=window.NBACalendarTours;
 const gs=normalizedGames(),owned=new Set(S.roster.map(id=>P[id]?.team));
 const teams=BASE.teams.filter(t=>!UI.calendarOwn||owned.has(t.team)).map(t=>t.team).sort();
 const matrix=T.buildMatrix(gs,teams,groups);
 const sort=UI.calendarTourSort;
 const rows=matrix.rows.sort((a,b)=>sort==='games'?b.total-a.total||a.team.localeCompare(b.team):
   sort==='fewest'?a.total-b.total||a.team.localeCompare(b.team):a.team.localeCompare(b.team));
 const todayET=T.dayKeyET(now()),totalDays=groups.reduce((sum,x)=>sum+x.days.length,0);
 const from=groups[0].labelStart,to=groups.at(-1).labelEnd;
 const dm=key=>key.slice(8,10)+'.'+key.slice(5,7);
 const dated=(from,to)=>dm(from)+'–'+dm(to);
 const sumCls=n=>n===0?'zero':n<3?'low':n===3?'medium':'high';
 const nCell=n=>`<td class="tour-sum ${sumCls(n)}" title="${n} игр в туре"><b>${n}</b></td>`;
 const dateLabel=key=>{
  const week=new Date(key+'T12:00:00Z').toLocaleDateString('ru-RU',{timeZone:'UTC',weekday:'short'});
  return esc(week)+' '+dm(key);
 };
 const rowCells=row=>row.parts.map(part=>{
   const cells=part.days.map(day=>{
     const current=day.key===todayET;
     const matches=day.games.map(g=>{
       const title=(g.away?'В гостях':'Дома')+' с '+g.opponent+' · '+dm(g.etDate)+' (дата NBA) · '+
                   dm(g.moscowDate)+' '+g.time+' МСК'+(g.b2b?' · B2B':'');
       return `<span class="tour-fixture ${g.b2b?'tour-b2b':''}" title="${esc(title)}">`+
        `<span class="tour-opponent">${g.away?'@':''}${esc(g.opponent)}</span>`+
        `<span class="tour-fixture-clock">${esc(g.time)}${g.moscowNextDay?'<sup title="Следующий день по Москве">+1</sup>':''}</span></span>`;
     }).join('');
     return `<td class="tour-day ${current?'tour-today':''}" data-day-et="${day.key}" title="Дата NBA ${day.key}">${matches||'<span class="tour-empty">·</span>'}</td>`;
   }).join('');
   return cells+(mode==='tours'?nCell(part.count):'');
 }).join('');
 const renderedRows=rows.map((r,i)=>`<tr class="${owned.has(r.team)?'mine':''}" data-team="${esc(r.team)}" data-period-total="${r.total}">`+
  `<th scope="row" class="stickycol tour-team" title="${esc(CLUBS[r.team]||r.team)}"><strong>${esc(r.team)}</strong><small>${esc(CLUBS[r.team]||r.team)}</small></th>`+
  `<td class="tour-total tour-sticky-total" title="${r.total} игр за весь выбранный период"><b>${r.total}</b></td>`+
  rowCells(r)+'</tr>').join('');
 const groupHeaders=groups.map(g=>`<th colspan="${g.days.length+(mode==='tours'?1:0)}" scope="colgroup" class="tour-group ${g.days.some(d=>d.key===todayET)?'tour-current':''}">`+
   `${mode==='tours'?'Тур '+g.number:'Выбранное окно'} <small>${dated(g.labelStart,g.labelEnd)}</small></th>`).join('');
 const dates=groups.map(g=>g.days.map(d=>`<th class="tour-date ${d.key===todayET?'tour-today':''}" scope="col" title="Игровая дата NBA, США (ET)">${dateLabel(d.key)}</th>`).join('')+
  (mode==='tours'?'<th class="tour-sum-head" scope="col" title="Число игр команды в туре">Игр</th>':'')).join('');
 const firstTime=Date.parse(from+'T12:00:00Z');
 const endTime=Date.parse(T.addDays(to,1)+'T12:00:00Z');
 const qualityFrom=Math.max(firstTime,Date.parse('2026-10-20T00:00:00Z'));
 const quality=calendarCoverage(qualityFrom,(endTime-qualityFrom)/T.DAY);
 const draftInWindow=[...S.draft].sort((a,b)=>a.epoch-b.epoch)
   .filter(x=>{const d=T.dayKeyET(x.epoch);return d&&d>=from&&d<=to;});
 return `<div class="tour-range-stats" role="status"><span><b>${totalDays}</b> ${totalDays===1?'день':'дней'} · ${dated(from,to)} (даты NBA)</span>`+
 `<span><b>${matrix.actualUniqueGames}</b> матчей в расписании · <b>${matrix.rows.length}</b> команд</span>`+
 `<span>Сортировка: <b>${sort==='games'?'по количеству игр ↓':sort==='fewest'?'по количеству игр ↑':'по названию'}</b></span></div>`+
 `<div class="small tour-swipe-hint">Вся сумма игр — сразу после команды. По вертикали таблица не прокручивается отдельно, по горизонтали можно листать даты →</div>`+
 `<div class="tablewrap tour-scroller" role="region" tabindex="0" aria-label="Календарь NBA, 30 команд. Горизонтальная прокрутка дат, без отдельной вертикальной прокрутки.">`+
 `<table class="calendar tour-table tour-table-compact"><thead><tr><th rowspan="2" scope="col" class="stickycol tour-head-team">Команда</th>`+
 `<th rowspan="2" scope="col" class="tour-grand-head tour-sticky-total">Всего<br>игр</th>${groupHeaders}</tr><tr>${dates}</tr></thead>`+
 `<tbody>${renderedRows||'<tr><td colspan="4">Укажи клубы в составе либо отключи фильтр</td></tr>'}</tbody></table></div>`+
 `<div class="tour-legend"><span class="tour-legend-cell high">4+ игр в туре</span>`+
 `<span class="tour-legend-cell medium">3 игры</span><span class="tour-legend-cell low">1–2 игры</span>`+
 `<span class="tour-legend-cell zero">0 игр</span><span class="small">@ — выезд · +1 рядом со временем = следующий календарный день в Москве · B2B — матчи подряд.</span></div>`+
 `<div class="info ${quality.ok?'':'warning'}"><b>Источник:</b> ${esc(quality.reason)}. <a href="https://github.com/mih98967-afk/nba-season-lab-data/blob/main/data/schedule.json" rel="noopener noreferrer" target="_blank">Проверенный календарь NBA/ESPN</a>. Неопределённые матчи NBA Cup не выдумываются.</div>`+
 `<div class="small" style="margin-top:12px">Номер тура — отображение недели Пн–Вс по дате NBA (ET), начиная с 19.10.2026; официальный зачёт Sports.ru этим не подтверждается. Таблица не изменяет дедлайны, блокировки, трансферы или FP.</div>`+
 `${S.draft.length?`<div class="schedule-plan"><b>Черновик в выбранном периоде</b>${draftInWindow.map(x=>`<span class="tag">${dateText(x.epoch)} · ${esc(P[x.out]?.name)} → ${esc(P[x.in_]?.name)}</span>`).join('')||'<span class="small">Запланированных замен в периоде нет</span>'}</div>`:''}`;
}
function calendarSortControl(){
 return `<label>Сортировать команды<select id="cal-tour-sort"><option value="games" ${UI.calendarTourSort==='games'?'selected':''}>Больше игр за период — выше</option><option value="fewest" ${UI.calendarTourSort==='fewest'?'selected':''}>Меньше игр за период — выше</option><option value="name" ${UI.calendarTourSort==='name'?'selected':''}>По алфавиту</option></select></label>`;
}
function calendarOwnedControl(){
 return `<label class="horizontal tour-own"><input type="checkbox" id="cal-own" ${UI.calendarOwn?'checked':''} style="width:auto;margin:0"> Только клубы моего состава</label>`;
}
function calendarToursPage(){
 const T=window.NBACalendarTours;
 if(!T)return '<div class="info warning">Не удалось загрузить модуль календаря. Обнови страницу.</div>';
 const current=clamp(T.tourNumber(now())||1,1,T.seasonTourCount());
 const count=clamp(Number(UI.calendarTourCount)||3,1,12);
 const max=T.seasonTourCount(),maxStart=Math.max(1,max-count+1);
 const start=clamp(Number(UI.calendarTour)||current,1,maxStart);
 const groups=T.tourRange(start,count);
 const dated=g=>g.labelStart.slice(8,10)+'.'+g.labelStart.slice(5,7)+'–'+g.labelEnd.slice(8,10)+'.'+g.labelEnd.slice(5,7);
 const tourOptions=Array.from({length:maxStart},(_,i)=>i+1).map(n=>{
   const t=T.tourRange(n,1)[0];return `<option value="${n}" ${n===start?'selected':''}>Тур ${n} · ${dated(t)}</option>`;
 }).join('');
 return `<div class="card tour-card"><div class="toolbar tour-controls">`+
 `<label>Начальный тур<select id="cal-tour-first">${tourOptions}</select></label>`+
 `<label>Сколько туров<select id="cal-tour-count">${Array.from({length:12},(_,i)=>i+1).map(n=>`<option value="${n}" ${n===count?'selected':''}>${n}</option>`).join('')}</select></label>`+
 calendarSortControl()+calendarOwnedControl()+`</div>`+
 `<div class="horizontal tour-nav"><button type="button" class="button" data-action="cal-prev-tours" ${start===1?'disabled':''}>← Назад</button>`+
 `<button type="button" class="button" data-action="cal-current-tours">Текущий</button>`+
 `<button type="button" class="button" data-action="cal-next-tours" ${start>=maxStart?'disabled':''}>Вперёд →</button>`+
 `<span class="small">Туры ${start}–${start+count-1} из ${max}</span></div>`+
 calendarPeriodTable(groups,'tours')+`</div>`;
}
function calendarWindowPage(){
 const T=window.NBACalendarTours;
 if(!T)return '<div class="info warning">Не удалось загрузить модуль календаря. Обнови страницу.</div>';
 if(!UI.calendarStart||!Number.isFinite(T.daysBetween(UI.calendarStart,UI.calendarStart)))
   UI.calendarStart=T.dayKeyET(now());
 const start=UI.calendarStart<T.FIRST_DATE?T.FIRST_DATE:UI.calendarStart>T.LAST_DATE?T.LAST_DATE:UI.calendarStart;
 UI.calendarStart=start;
 const maxDays=Math.min(T.MAX_WINDOW_DAYS,T.daysBetween(start,T.LAST_DATE)+1);
 const requested=clamp(Math.round(Number(UI.calendarDays)||14),1,maxDays);
 const endCandidate=UI.calendarEnd&&Number.isFinite(T.daysBetween(start,UI.calendarEnd))?UI.calendarEnd:T.addDays(start,requested-1);
 const end=endCandidate<start?start:endCandidate>T.LAST_DATE?T.LAST_DATE:endCandidate;
 const days=Math.min(maxDays,T.daysBetween(start,end)+1);
 UI.calendarEnd=end;UI.calendarDays=days;
 const groups=T.dateRange(start,end);
 return `<div class="card tour-card"><div class="toolbar tour-controls">`+
 `<label>Дата с (NBA, США)<input type="date" id="cal-start" min="${T.FIRST_DATE}" max="${T.LAST_DATE}" value="${start}"></label>`+
 `<label>Дата по (NBA, США)<input type="date" id="cal-end" min="${start}" max="${T.LAST_DATE}" value="${end}"></label>`+
 `<label>Длина окна, дней<input type="number" id="cal-days" min="1" max="${maxDays}" step="1" value="${days}" title="От 1 до ${maxDays} дней"></label>`+
 calendarSortControl()+calendarOwnedControl()+`</div>`+
 `<div class="horizontal tour-nav"><button type="button" class="button" data-action="cal-prev-window" ${start<=T.FIRST_DATE?'disabled':''}>← Предыдущее окно</button>`+
 `<button type="button" class="button" data-action="cal-next-window" ${end>=T.LAST_DATE?'disabled':''}>Следующее окно →</button>`+
 `<span class="small">Можно указать любые даты или количество дней — до конца регулярного сезона.</span></div>`+
 calendarPeriodTable(groups,'window')+`</div>`;
}
function allowedIds(out,owned=S.roster){
 if(!out||!P[out])return [];
 const available=planResult(S.draft).cash;
 const fits=p=>p.start_price>=0&&prices(p.id)<=available+prices(out)&&owned.filter(id=>id!==out&&P[id]?.team===p.team).length<2;
 return BASE.players.filter(p=>p.id!==out&&p.pos===P[out].pos&&!owned.includes(p.id)).sort((a,b)=>{
  const fa=fits(a),fb=fits(b);if(fa!==fb)return fa?-1:1;
  const from=Math.max(now(),Number.isFinite(UI.plannerWhen)?UI.plannerWhen:now());
  const av=prediction(a.id,from,14).fp||0,bv=prediction(b.id,from,14).fp||0;
  return bv-av;
 });
}
function planResult(draft){
 // Pure read-only validator. Personal Firebase state is not written by this function.
 const fresh=!!CALENDAR&&CALENDAR.status==='verified_public_calendar_with_known_gaps'
   &&Number.isFinite(Date.parse(CALENDAR.updated_at_utc))
   &&now()-Date.parse(CALENDAR.updated_at_utc)<=72*3600000;
 const coverageOk=fresh&&draft.every(t=>Number.isFinite(t.epoch)&&calendarCoverage(t.epoch,1).ok);
 return window.NBATransferGuard.validate({
  players:P,roster:S.roster,cash:S.cash,executed:S.executed,draft,
  games:normalizedGames(),scheduleVerified:coverageOk,nowEpoch:now()
 });
}
function plannedMean(ids,draft,days){const next=now(),horizon=next+days*86400000;if(!calendarCoverage(next,days).ok)return NaN;let sum=0;const allGames=normalizedGames().filter(g=>g.epoch>=next&&g.epoch<horizon&&g.status!=='final');
 for(const g of allGames){let own=[...ids];for(const t of [...draft].sort((a,b)=>a.epoch-b.epoch)){if(t.epoch<=g.epoch-30*60000){const idx=own.indexOf(t.out);if(idx>=0)own[idx]=t.in_;}}for(const id of own){const p=P[id];if(!p||!p.forecast||!(p.team===g.home||p.team===g.away))continue;sum+=learnedMean(p,g)*probability(p,g);}}
 return sum;}
function rangeMean(ids,draft,start,end){
 if(end<=start)return 0;
 if(!calendarCoverage(start,(end-start)/86400000).ok)return NaN;
 let sum=0, moves=[...draft].sort((a,b)=>a.epoch-b.epoch);
 for(const g of normalizedGames()){
  if(g.epoch<start||g.epoch>=end||g.status==='final')continue;
  const owning=[...ids];
  for(const t of moves){if(t.epoch>g.epoch-30*60000)break;let slot=owning.indexOf(t.out);if(slot>=0)owning[slot]=t.in_;}
  for(const id of owning){const p=P[id];if(p?.forecast&&(p.team===g.home||p.team===g.away))sum+=learnedMean(p,g)*probability(p,g);}
 }
 return sum;
}
function prefetchPlannerHistory(){
 if(S.modelMode!=='validated'||!HISTORY_INDEX)return;
 const ids=[...new Set([...S.roster,...S.draft.map(x=>x.in_),UI.plannerIn].filter(Boolean))].slice(0,18);
 for(const pid of ids)scheduleHistory(pid);
}
function plannerModelCoverage(){return S.roster.filter(id=>validatedModelSignal(P[id])).length;}
function planWorlds(draft,days,samples=850){
 // Paired simulations use identical player-game events in baseline and plan.
 // Thus unchanged players cancel in the gain distribution, eliminating bogus noise.
 const start=now(),end=start+days*86400000;
 const games=normalizedGames().filter(g=>g.epoch>=start&&g.epoch<end&&g.status!=='final');
 const moves=[...draft].sort((a,b)=>a.epoch-b.epoch);
 const owningAt=(g,withMoves)=>{let ids=[...S.roster];if(withMoves)for(const t of moves){if(t.epoch>g.epoch-30*60000)break;const i=ids.indexOf(t.out);if(i>=0)ids[i]=t.in_;}return ids.filter(id=>P[id]?.forecast&&(P[id].team===g.home||P[id].team===g.away));};
 const noiseCache=new Map(),events=[];
 for(const g of games){const baseline=new Set(owningAt(g,false)),planned=new Set(owningAt(g,true));
  for(const pid of new Set([...baseline,...planned])){
   const p=P[pid],mu=learnedMean(p,g),q=probability(p,g);
   if(!Number.isFinite(mu))continue;
   if(!noiseCache.has(pid)){
    const empirical=(p.noise||[]).filter(Number.isFinite);
    const average=empirical.length?empirical.reduce((a,b)=>a+b,0)/empirical.length:0;
    noiseCache.set(pid,{values:empirical.map(v=>v-average),sd:Math.max(5,(p.mean_if_play||15)*.45)});
   }
   events.push({pid,mu,q,base:baseline.has(pid),plan:planned.has(pid),noise:noiseCache.get(pid)});
  }
 }
 let seed=(227333+Math.floor(start/86400000)+days*17+events.length*13)>>>0;
 const rand=()=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return (seed>>>0)/4294967296;};
 const a=[],b=[],gains=[];
 for(let i=0;i<samples;i++){
  let baseline=0,planned=0;const individual=new Map();
  for(const e of events){
   if(!individual.has(e.pid))individual.set(e.pid,(rand()-.5)*.20);
   if(rand()>=clamp(e.q+individual.get(e.pid),0,1))continue;
   const z=e.noise.values;
   const residual=z.length?z[Math.floor(rand()*z.length)]:(rand()+rand()+rand()+rand()-2)*e.noise.sd;
   const value=e.mu+residual;
   if(e.base)baseline+=value;
   if(e.plan)planned+=value;
  }
  a.push(baseline);b.push(planned);gains.push(planned-baseline);
 }
 const stats=v=>{v.sort((x,y)=>x-y);return {lo:v[Math.floor((v.length-1)*.10)],mid:v[Math.floor((v.length-1)*.50)],hi:v[Math.floor((v.length-1)*.90)]};};
 const wins=gains.filter(v=>v>0).length;const ties=gains.filter(v=>Math.abs(v)<.000001).length;
 return {base:stats(a),plan:stats(b),gain:stats(gains),probBetter:wins/samples,
  games:games.length,playerGameEvents:events.length,n:samples,coverageEnd:Math.max(...normalizedGames().map(g=>g.epoch),0),
  caution:'Сценарные P10–P90: не откалиброванная вероятность результата недели'};
}
function planningControls(){
 const experimental=MODEL_V2?.schema_version===2&&MODEL_V2.status==='validated_for_conditional_game';
 const coverage=plannerModelCoverage();
 return `<div class="card plan-settings"><div class="titledetail"><h2>Как считать ожидаемые FP</h2><span class="pill">Сценарии, не медицинский прогноз</span></div>
 <div class="formgrid"><label>Результативность при выходе<select id="model-mode"><option value="current" ${S.modelMode!=='validated'?'selected':''}>Текущий прогноз (по умолчанию)</option><option value="validated" ${S.modelMode==='validated'?'selected':''} ${!experimental?'disabled':''}>Историческая модель v2 — исследование</option></select></label>
 <label>Риск пропуска<select id="risk-mode"><option value="baseline" ${S.riskMode==='baseline'?'selected':''}>Базовое допущение</option><option value="cautious" ${S.riskMode==='cautious'?'selected':''}>Осторожнее: −15 п.п.</option><option value="allplay" ${S.riskMode==='allplay'?'selected':''}>Все сыграют (кроме ручного OUT)</option></select></label></div>
 <p class="small">В проверке на сезоне 2025/26 средняя ошибка прогноза следующего <b>сыгранного</b> матча снизилась с 6,93 до 6,82 FP. Она не предсказывает DNP. ${S.modelMode==='validated'?'Загружено проверенной истории для '+coverage+' из '+S.roster.length+' игроков текущего состава; остальные остаются на исходном прогнозе.':'Прогнозы команды не изменялись автоматически.'} Риск участия и сценарные интервалы <b>не калиброваны по неделям</b>. Отметки Telegram не меняют вероятности.</p></div>`;
}
function scenarioPanel(draft,checked){
 if(!checked.valid||S.roster.length!==10)return '';
 const scenarios=[7,14,28].map(days=>{
  const coverage=calendarCoverage(now(),days);
  return {days,coverage,base:coverage.ok?plannedMean(S.roster,[],days):null,
          plan:coverage.ok?plannedMean(S.roster,draft,days):null,
          distribution:coverage.ok?planWorlds(draft,days):null};
 });
 return `<div class="card"><h2>Прирост и неопределённость</h2><div class="tablewrap"><table><thead><tr><th>Окно</th><th>Без замен</th><th>С планом</th><th>Разница</th><th>Сценарный P10–P90 разницы</th></tr></thead><tbody>${scenarios.map(x=>{
  if(!x.coverage.ok)return `<tr><td>${x.days} дней</td><td colspan="4" class="small">Недостаточно расписания: ${esc(x.coverage.reason)}</td></tr>`;
  const gain=x.plan-x.base;
  return `<tr><td>${x.days} дней</td><td>${round(x.base,1)}</td><td>${round(x.plan,1)}</td><td class="${gain>=0?'delta-plus':'delta-minus'}"><b>${gain>=0?'+':''}${round(gain,1)} FP</b></td><td>${round(x.distribution.gain.lo)}…${round(x.distribution.gain.hi)} FP</td></tr>`;
 }).join('')}</tbody></table></div><p class="small">Одинаковые случайные исходы используются для сравнения KEEP и TRANSFER. Диапазоны — модельные сценарии, не откалиброванные 80%-е вероятностные интервалы. Неучтённая стоимость третьей замены остаётся ограничением.</p>${scenarios.filter(x=>!x.coverage.ok).map(x=>`<div class="info warning">${x.days} дней: ${esc(x.coverage.reason)}. Прирост FP не рассчитывается.</div>`).join('')}</div>`;
}
function shortlistPanel(out,when,available){
 if(!window.NBAShortlist || S.roster.length!==10)return '';
 const current=planResult(S.draft);
 const base={
  out,available,players:P,candidates:BASE.players,
  draft:S.draft,cash:current.cash,whenEpoch:when,nowEpoch:now(),max:5,
  priceOf:id=>id===out&&UI.plannerSell!=null?UI.plannerSell:prices(id),
  validateDraft:planResult,
  coverage:calendarCoverage,
  project:(moves,start,end)=>rangeMean(S.roster,moves,start,end),
  countGames:(id,start,days)=>futureGames(id,start,days).filter(g=>g.epoch>=start+30*60000).length
 };
 const ranked=window.NBAShortlist.rank(base);
 if(!ranked.ready)return `<div class="info warning" style="margin-top:12px"><b>Альтернативы пока не рассчитаны.</b> ${esc(ranked.reason)}</div>`;
 const remaining=Math.max(0,3-(current.used[moscowWeek(when)]||0));
 const rows=ranked.rows.map(x=>{
  const p=P[x.id];const gain=v=>`<span class="${v>=0?'delta-plus':'delta-minus'}">${v>=0?'+':''}${round(v,1)} FP</span>`;
  const risk=S.medical[x.id]==='out'?'Ручной OUT':S.medical[x.id]==='questionable'?'Ручной статус: под вопросом':p.risk>=3?'Проверить статус':'Статус не подтверждён';
  return `<tr><td><b>${esc(p.name)}</b><div class="small">${esc(p.team)} · ${esc(risk)}</div></td><td>${round(x.price)}<div class="small">оценка, не цена Sports.ru</div></td><td>${x.games7} / ${x.games14}</td><td>${gain(x.gain7)}</td><td>${gain(x.gain14)}</td><td><button class="ghost" data-shortlist="${esc(x.id)}">Подставить</button></td></tr>`;
 }).join('');
 return `<div class="shortlist-panel" style="margin-top:18px"><div class="titledetail"><h3>Проверить альтернативы</h3><span class="small">Оценка замен (Пн 15:00): ${remaining}/3 · проверьте Sports.ru</span></div>
 <p class="small">Тот же слот, бюджет и лимит команд. Разница FP рассчитана с выбранного момента замены относительно KEEP, с учётом уже существующего черновика. Цены приблизительные; покупка всегда проверяется на Sports.ru.</p>
 ${rows?`<div class="tablewrap"><table><thead><tr><th>Кандидат</th><th>Цена</th><th>Игр 7/14 дней</th><th>Δ 7 дней</th><th>Δ 14 дней</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`:'<div class="info warning">Нет условно допустимых кандидатов. Сохранение игрока (KEEP) — допустимое решение.</div>'}
 <div class="small" style="margin-top:8px">${ranked.eligible} условно допустимых из ${ranked.checked} рассмотренных. Это сценарные оценки, не доказанные вероятности и не гарантия выгодного трансфера. Если нет положительной разницы — KEEP.</div></div>`;
}
function chainSignature(){return JSON.stringify({r:S.roster,d:S.draft,c:S.cash,e:S.executed,
 p:S.prices,t:S.teamOverrides,m:S.medical,live:LIVE.updated_at_utc,cal:CALENDAR?.updated_at_utc,
 official:OFFICIAL_FEED?.updated_at_utc,
 model:S.modelMode,risk:S.riskMode});}
function chainPanel(out,when){
 if(!window.NBAChainPlanner||S.roster.length!==10)return '';
 const readiness=advicePreflight(UI.chainDays,when);
 const result=readiness.ready&&UI.chainResult?.signature===chainSignature()?UI.chainResult:null;
 const gain=n=>`<strong class="${n>=0?'delta-plus':'delta-minus'}">${n>=0?'+':''}${round(n,1)} FP</strong>`;
 const kind={keep:'KEEP · сохранить игрока',now:'Одна замена в выбранный момент',later:'Одна замена позже',chain:'Цепочка из двух замен'};
 const resultHtml=!result?'':!result.ready?
  `<div class="info warning" role="status">${esc(result.reason)}</div>`:
  `<div class="chain-results" role="status"><p class="small">Прогноз от ${dateText(result.start)} на ${result.horizonDays} дней. Базовый сценарий KEEP: ${round(result.baseline,1)} FP всей команды. Вариантов проверено: ${result.tested} (в финале подробно сравнено: ${result.eligible}).</p>
   ${result.routes.map((route,i)=>`<div class="chain-route"><div class="horizontal" style="justify-content:space-between"><span class="pill">${esc(kind[route.kind]||route.kind)}</span>${gain(route.gain)}</div>
    ${route.moves.length?`<div class="small">После условного резерва ${result.opportunityPenalty} FP на замену: ${gain(route.net)}. Ходов: ${route.moves.length}. Касса по неизменным ценам: ${round(route.cash)}.</div>`:'<div class="small">Ноль дополнительных ходов. Сохранение состава — полноценный вариант.</div>'}
    ${route.moves.map((m,j)=>`<div class="chain-step"><b>${j+1}.</b> ${esc(P[m.out]?.name||m.out)} → <b>${esc(P[m.in_]?.name||m.in_)}</b> <span class="small">${dateText(m.epoch)} МСК · ${round(m.sell)} → ${round(m.buy)}</span></div>`).join('')}
    <div class="chain-weeks">${route.weekly.map(w=>`<span class="chain-week">С ${esc(w.week)}: ${w.gain==null?'н/д':(w.gain>=0?'+':'')+round(w.gain,1)} FP</span>`).join('')}</div>
    ${route.warnings.length?`<div class="small warntext">Нужна проверка: ${esc(route.warnings.slice(0,3).join(' · '))}</div>`:''}
    ${route.moves.length?`<button class="button chain-copy" data-chain-apply="${i}">Добавить ${route.moves.length===1?'шаг':'оба шага'} в черновик</button>`:''}</div>`).join('')}
   <p class="small">Сравниваем только сценарии для выбранного слота; это не глобальная оптимизация десятки. Существующие трансферы в черновике учтены. Будущие цены и время разблокировки неизвестны, FP и резервы замены — сценарные оценки, а не гарантии.</p></div>`;
 return `<div class="card chain-panel" id="chain-panel"><div class="titledetail"><h2>Когда выгоднее менять: сейчас или позже?</h2><span class="pill">Без автоматических трансферов</span></div>
  <p>Сравните KEEP, покупку сейчас, ожидание и двухшаговую цепочку. Доступные ходы и лимит команд проверяются на каждой стадии. Условная цена сохранённого хода помогает не менять игрока ради небольшого преимущества.</p>
  <div class="formgrid"><label>Горизонт оценки<select id="chain-days">${[14,21,28].map(n=>`<option value="${n}" ${UI.chainDays===n?'selected':''}>${n} дней</option>`).join('')}</select></label>
  <label>Резерв одного трансфера<select id="chain-penalty">${[0,4,8].map(n=>`<option value="${n}" ${UI.chainPenalty===n?'selected':''}>${n===0?'0 FP · максимальный риск':n===4?'4 FP · баланс':'8 FP · беречь ходы'}</option>`).join('')}</select></label></div>
  ${!readiness.ready?`<div class="info warning" role="status">Рекомендации заблокированы: ${esc(readiness.reasons.slice(0,2).join(' '))}</div>`:''}
  <div class="toolbar"><button class="primary" data-action="calculate-chains" ${readiness.ready?'':'disabled'}>Сравнить цепочки для ${esc(P[out]?.name||'игрока')}</button><span class="small">Старт: ${dateText(when)} МСК</span></div>
  ${resultHtml}<div class="small">* Резерв хода — не реальный штраф Sports.ru и не доказанная оптимальная стоимость замены. Он влияет только на сортировку стратегий. Цены будущих игроков моделируются по текущей оценке.</div></div>`;
}
function scenarioScorePlayer(id,start,end){
 const p=P[id];if(!p?.forecast)return NaN;
 let total=0;
 for(const g of normalizedGames()){
  if(g.status==='final'||g.epoch<start||g.epoch>=end)continue;
  if(g.home!==p.team&&g.away!==p.team)continue;
  const mu=learnedMean(p,g),chance=probability(p,g);
  if(!Number.isFinite(mu)||!Number.isFinite(chance))return NaN;
  total+=mu*chance;
 }
 return total;
}
function budgetSignature(){
 return chainSignature()+JSON.stringify({pos:UI.budgetPosition,target:UI.budgetTarget,
  out:UI.budgetOut,buy:UI.budgetBuy,days:UI.budgetDays,
  penalty:UI.budgetPenalty,moves:UI.budgetMoves,when:UI.plannerWhen});
}
function budgetPanel(){
 if(!window.NBABudgetPackage||S.roster.length!==10)return '';
 const checked=planResult(S.draft),owned=checked.valid?checked.roster:S.roster;
 const t=Number.isFinite(UI.plannerWhen)?UI.plannerWhen:now()+20*60000;
 const week=moscowWeek(t),remaining=Math.max(0,3-(checked.used?.[week]||0));
 const options=BASE.players.filter(p=>p?.forecast&&!owned.includes(p.id)&&
  (UI.budgetPosition==='all'||p.pos===UI.budgetPosition))
  .sort((a,b)=>prices(b.id)-prices(a.id)||a.name.localeCompare(b.name));
 const selected=options.some(p=>p.id===UI.budgetTarget)?UI.budgetTarget:null;
 const target=selected?P[selected]:null;
 const outs=target?owned.filter(id=>P[id]?.pos===target.pos):[];
 const out=outs.includes(UI.budgetOut)?UI.budgetOut:'auto';
 const buy=UI.budgetBuy!=null?UI.budgetBuy:(target?prices(target.id):null);
 const deficits=target&&checked.valid?outs.filter(id=>out==='auto'||out===id)
  .map(id=>({id,short:Math.max(0,buy-checked.cash-prices(id))})):[];
 const readiness=advicePreflight(UI.budgetDays,t);
 const result=readiness.ready&&UI.budgetResult?.signature===budgetSignature()?UI.budgetResult:null;
 const routes=result?.ready?result.routes:[];
 const signed=n=>`<strong class="${n>=0?'delta-plus':'delta-minus'}">${n>=0?'+':''}${round(n,1)} FP</strong>`;
 const detail=!result?'':!result.ready?
  `<div class="info warning" role="status">${esc(result.reason)}${result.requiredByOut?.length?`<div class="small">Нужно дополнительно: ${result.requiredByOut.map(v=>esc(P[v.out]?.name||v.out)+': '+round(v.deficit)).join(' · ')}</div>`:''}</div>`:
  `<div class="budget-results" role="status">${routes.length&&routes[0].net<=0?'<div class="info warning"><b>KEEP выглядит выгоднее.</b> Цель можно профинансировать, но найденные пакеты теряют ожидаемые FP или не оправдывают расход ходов.</div>':''}<p class="small">KEEP: ${round(result.baseline,1)} FP за ${result.horizonDays} дней. Свободных ходов на этой неделе: ${result.remaining}. Найдено допустимых пакетов при полной проверке: ${result.eligible}. Ограниченный поиск — не гарантия глобального оптимума.</p>
    ${routes.map((r,i)=>`<div class="budget-route"><div class="horizontal" style="justify-content:space-between;gap:10px"><b>${r.moves.length===1?'Прямая покупка':r.moves.length===2?'Покупка + 1 замена для бюджета':'Покупка + 2 замены для бюджета'}</b>${signed(r.gain)}</div>
      <div class="small">С резервом ${UI.budgetPenalty} FP за ход: ${signed(r.net)} · ходов ${r.moves.length} · касса после ${round(r.cash)}</div>
      ${r.moves.map((m,j)=>`<div class="budget-step"><span class="budget-step-index">${j+1}</span><div><b>${j===r.moves.length-1?'Целевая покупка':'Сначала освободить бюджет'}</b><div>${esc(P[m.out]?.name||m.out)} → <b>${esc(P[m.in_]?.name||m.in_)}</b></div><div class="small">${round(m.sell)} → ${round(m.buy)} · касса после ${round(r.stepCash?.[j])} · ${dateText(m.epoch)} МСК</div></div></div>`).join('')}
      <div class="small">Разница FP сравнивается с KEEP всей десятки, включая уже существующий черновик. Суммарные FP всей команды, а не только дорогого игрока.</div>
      ${r.warnings?.length?`<div class="small warntext">Проверьте: ${esc(r.warnings.slice(0,3).join(' · '))}</div>`:''}
      <button class="button" data-budget-apply="${i}">Добавить все ${r.moves.length} шага в черновик</button></div>`).join('')}
    <p class="small">${esc(result.disclaimer)}</p></div>`;
 return `<div class="card budget-panel" id="budget-panel"><div class="titledetail"><h2>Хочу дорогого игрока — как освободить бюджет?</h2><span class="pill">Новый режим · v6.4</span></div>
  <p class="small">Укажите обязательную покупку, и сервис подберёт, кого ещё заменить сейчас, чтобы хватило денег. Можно предложить обе продажи автоматически или самому выбрать, с кем расстаться ради цели. <b>Все ходы идут в указанное ниже время — сначала освобождение бюджета, затем покупка.</b></p>
  <div class="formgrid">
    <label>Позиция цели<select id="budget-position">${['all',...POS].map(pos=>`<option value="${pos}" ${pos===UI.budgetPosition?'selected':''}>${pos==='all'?'Любая позиция':pos+' · '+POSRU[pos]}</option>`).join('')}</select></label>
    <label>Кого хочу купить<select id="budget-target"><option value="">Выбери игрока IN</option>${options.map(p=>`<option value="${p.id}" ${selected===p.id?'selected':''}>${esc(p.name)} · ${p.pos} · ${p.team} · ${round(prices(p.id))}</option>`).join('')}</select></label>
    <label>Кого продать в этом слоте<select id="budget-out" ${target?'':'disabled'}><option value="auto" ${out==='auto'?'selected':''}>Подбери автоматически</option>${outs.map(id=>`<option value="${id}" ${out===id?'selected':''}>${esc(P[id].name)} · оценка ${round(prices(id))}</option>`).join('')}</select></label>
    <label>Цена целевой покупки (Sports.ru)<input id="budget-buy" type="number" min="0" step="1" ${target?'':'disabled'} value="${buy==null?'':Number.isFinite(buy)?buy:''}"></label>
    <label>Момент выполнения пакета (МСК)<input id="budget-when" type="datetime-local" value="${moscowInput(t)}"></label>
    <label>Максимум новых ходов (включая цель)<select id="budget-moves">${[1,2,3].map(n=>`<option value="${n}" ${UI.budgetMoves===n?'selected':''}>${n} ${n===1?'ход':'хода'}</option>`).join('')}</select></label>
    <label>Оценивать за<select id="budget-days">${[7,14,21,28].map(n=>`<option value="${n}" ${UI.budgetDays===n?'selected':''}>${n} дней</option>`).join('')}</select></label>
    <label>Резерв за потраченный ход<select id="budget-penalty">${[0,4,8].map(n=>`<option value="${n}" ${UI.budgetPenalty===n?'selected':''}>${n} FP ${n===0?'· не беречь':n===4?'· баланс':'· беречь ходы'}</option>`).join('')}</select></label>
  </div>
  ${target?`<div class="info budget-need"><b>Касса по текущему черновику: ${round(checked.cash)}.</b> Цель стоит ${round(buy)}.${deficits.length?`<div>Не хватает при продаже выбранного игрока: ${deficits.map(d=>`${esc(P[d.id]?.name||d.id)} — ${round(d.short)}`).join(' · ')}.</div>`:''}<div class="small">Цены остальных игроков берутся из раздела «Данные» (или расчётно). Проверьте их на Sports.ru.</div></div>`:''}
  ${!readiness.ready?`<div class="info warning" role="status">Рекомендации заблокированы: ${esc(readiness.reasons.slice(0,2).join(' '))}</div>`:''}
  <div class="toolbar"><button class="primary" data-action="calculate-budget" ${!readiness.ready||!target||!remaining?'disabled':''}>Найти пакеты под покупку</button><span class="small">Свободно: ${remaining} из 3 ходов · момент ${dateText(t)} МСК</span></div>
  ${detail}<p class="small">Черновик не совершает трансферы. Если цены на Sports.ru отличаются, обновите их и пересчитайте. Цена цели в этом поле используется только для сценария, не меняя профиль.</p></div>`;
}
function calculateBudget(){
 if(!window.NBABudgetPackage)return showMsg('Модуль финансирования покупки недоступен.');
 const t=moscowEpoch(document.getElementById('budget-when')?.value);
 if(!Number.isFinite(t))return showMsg('Укажите момент замены по Москве.');
 const readiness=advicePreflight(UI.budgetDays,t);
 if(!readiness.ready){UI.budgetResult=null;return showMsg('Рекомендации заблокированы: '+readiness.reasons.slice(0,2).join(' '));}
 const target=document.getElementById('budget-target')?.value;
 if(!P[target])return showMsg('Выбери игрока, которого хочешь купить.');
 const buy=num(document.getElementById('budget-buy')?.value);
 if(!Number.isFinite(buy)||buy<0)return showMsg('Впишите фактическую цену целевой покупки.');
 UI.plannerWhen=t;UI.budgetTarget=target;UI.budgetBuy=buy;
 const forced=UI.budgetOut!=='auto'?UI.budgetOut:null;
 const games=normalizedGames();
 const atLock=(id,when)=>games.some(g=>g.status!=='final'&&
  (g.home===P[id]?.team||g.away===P[id]?.team)&&
  when>=g.epoch-30*60000&&when<g.epoch);
 const r=window.NBABudgetPackage.solve({players:P,roster:S.roster,candidates:BASE.players,
  existingDraft:S.draft,nowEpoch:now(),whenEpoch:t,targetId:target,
  forcedOutId:forced,maxMoves:UI.budgetMoves,horizonDays:UI.budgetDays,
  opportunityPenalty:UI.budgetPenalty,
  priceOf:id=>id===target?buy:prices(id),validateDraft:planResult,
  coverage:calendarCoverage,scorePlayer:scenarioScorePlayer,
  project:(moves,start,end)=>rangeMean(S.roster,moves,start,end),
  isCandidateAvailable:id=>S.medical[id]!=='out',isBlocked:atLock});
 r.signature=budgetSignature();UI.budgetResult=r;
 view();document.getElementById('budget-panel')?.scrollIntoView?.({behavior:'smooth',block:'start'});
}
function applyBudget(index){
 const readiness=advicePreflight(UI.budgetDays,UI.budgetResult?.start??now());
 if(!readiness.ready)return showMsg('Рекомендации заблокированы: '+readiness.reasons.slice(0,2).join(' '));
 const r=UI.budgetResult;
 if(!r?.ready||r.signature!==budgetSignature())return showMsg('Данные изменились — пересчитайте пакет.');
 const route=r.routes?.[index];
 if(!route?.moves?.length)return showMsg('Нет выбранных замен для добавления.');
 if(route.moves.some(m=>m.epoch<now()-60000))return showMsg('Время уже прошло — пересчитайте план.');
 if(!calendarCoverage(r.start,r.horizonDays).ok)return showMsg('Календарь изменился — пересчитайте пакет.');
 const checked=planResult([...S.draft,...route.moves]);
 if(!checked.valid)return showMsg('Пакет более не допустим: '+checked.errors.join(' · '));
 const summary=route.moves.map((m,i)=>`${i+1}. ${P[m.out]?.name||m.out} → ${P[m.in_]?.name||m.in_} · ${round(m.sell)} → ${round(m.buy)}`).join('\n');
 if(!confirm('Добавить '+route.moves.length+' шаг(а) ТОЛЬКО В ЧЕРНОВИК?\n\n'+summary+'\n\nВыполните реальные замены на Sports.ru вручную, по порядку, проверяя цены и блокировки.'))return;
 S.draft.push(...route.moves);save();view();showMsg('Все шаги добавлены только в черновик. Реальных трансферов не совершено.');
}
function multiEvidence(route){
 // Read-only: a private price receipt is never copied to S or Firebase.
 if(!route?.moves?.length||!window.NBADecisionEvidence)return null;
 let archive=null,localError='';
 try{archive=window.NBAPriceEvidence?.read(localStorage)||null;}
 catch{localError='Локальный журнал цен недоступен';}
 const officialQuality=window.NBAOfficialStatus?.validate(OFFICIAL_FEED);
 const isFresh=!!officialQuality?.ok&&Number.isFinite(officialQuality.updatedAt)
   &&now()-officialQuality.updatedAt>=0&&now()-officialQuality.updatedAt<=12*3600000;
 const report=window.NBADecisionEvidence.audit({
  route,nowEpoch:now(),priceArchive:archive,
  officialReports:officialForPlayers([...new Set(route.moves.map(m=>m.in_))]),
  officialFeedValid:isFresh
 });
 if(report.ready&&localError)report.warnings.unshift(localError);
 return report;
}
function multiEvidenceHtml(route){
 const audit=multiEvidence(route);
 if(!audit?.ready)return '';
 const urgent=audit.entries.filter(x=>x.officialStatus==='out');
 const head=urgent.length
   ? 'Внимание: NBA OUT у покупаемого игрока — проверьте матч'
   : audit.counts.priceConflict
     ? 'Цена в плане отличается от последней ручной отметки Sports.ru'
     : 'Проверка цен и участия перед решением';
 const details=audit.entries.map(e=>{
  const name=esc(P[e.in_]?.name||e.in_);
  const quote=e.quoteStatus==='no_pair_snapshot'?'нет ручной отметки обеих цен':
   e.quoteStatus==='snapshot_disagrees_with_scenario'?
     `ручная цена ${round(e.manualSell)} → ${round(e.manualBuy)} отличается от плана ${round(e.scenarioSell)} → ${round(e.scenarioBuy)}`:
   e.quoteStatus==='old_matching_snapshot'?'ручная отметка старше часа':
   e.quoteStatus==='restored_snapshot_unverified'?'отметка восстановлена из файла, время не доказано':
     'ручная отметка совпадает с планом, но это не живая котировка';
  return `<div class="small">${name}: ${esc(quote)}${e.officialStatus?` · NBA ${esc(e.officialStatus.toUpperCase())} (${esc(dateText(e.officialTipEpoch))} МСК)` : ''}</div>`;
 }).join('');
 return `<details class="info warning" style="margin-top:8px"><summary><b>${head}</b></summary>
  ${details}${audit.warnings.map(w=>`<p class="small">${esc(w)}</p>`).join('')}
  <p class="small">Отметки цен локальные, будущие котировки и участие не гарантированы. Ни одна проверка не совершает замен.</p>
 </details>`;
}
function decisionJournalCount(){
 try{return window.NBADecisionJournal?.read(localStorage)?.entries.length??0;}
 catch{return null;}
}
function freezeMultiDecision(index){
 const readiness=advicePreflight(UI.multiDays,UI.multiResult?.start??now());
 if(!readiness.ready)return showMsg('Недостаточно подтверждённых данных для записи сравнения: '+readiness.reasons.slice(0,2).join(' '));
 const result=UI.multiResult;
 if(UI.multiCalculatedAt&&now()-UI.multiCalculatedAt>30*60000)return showMsg('Варианты устарели: пересчитайте перед записью в журнал.');
 if(!window.NBADecisionJournal)return showMsg('Локальный журнал решений не загрузился.');
 if(!result?.ready||result.signature!==chainSignature())
   return showMsg('Данные изменились: сначала пересчитайте сравнение.');
 if(!Number.isInteger(index)||!result.routes?.[index])
   return showMsg('Выберите действительный вариант KEEP / NOW / LATER.');
 if(!explainMulti(result.routes[index],result).ready)
   return showMsg('Подробные FP не прошли сверку с планом. Запись заблокирована; пересчитайте.');
 if(!confirm('Сохранить наблюдение о вариантах KEEP / NOW / LATER ТОЛЬКО В ЭТОМ БРАУЗЕРЕ?\n\n'
   +'Запишутся текущий состав, предполагаемые цены, прогноз FP и реальное время нажатия. '
   +'Это не отправляет данные в GitHub/Firebase и не означает фактическую замену.'))return;
 try{
   const receipt=window.NBADecisionJournal.take(localStorage,{
     userConfirmedNow:true,plan:result,chosenIndex:index,
     roster:S.roster,cash:S.cash,liveUpdatedAtUtc:LIVE?.updated_at_utc||null
   });
   showMsg('Сравнение зафиксировано локально: '+dateText(Date.parse(receipt.captured_at_utc))+
    ' МСК. Для проверки после матчей экспортируйте журнал.');
   view();
 }catch(error){showMsg('Журнал: '+String(error.message||error));}
}
function decisionJournalExport(){
 try{
   if(!window.NBADecisionJournal)return showMsg('Журнал не загрузился.');
   download('nba-season-lab-private-decision-journal.json',
    window.NBADecisionJournal.exportData(localStorage));
   showMsg('Скачана локальная копия решений; файл содержит ваш состав и прогнозы.');
 }catch(error){showMsg('Экспорт журнала: '+String(error.message||error));}
}
function decisionJournalClear(){
 if(!window.NBADecisionJournal)return showMsg('Журнал не загрузился.');
 if(!confirm('Удалить локальный журнал решений в этом браузере?\n'
     +'Это не затронет состав, кассу, трансферы и Firebase.'))return;
 try{window.NBADecisionJournal.clear(localStorage,true);view();
     showMsg('Локальный журнал решений очищен.');}
 catch(error){showMsg('Очистка журнала: '+String(error.message||error));}
}
function explainMulti(route,result){
 if(!window.NBADecisionBreakdown)return {ready:false,code:'MODULE_NOT_LOADED'};
 return window.NBADecisionBreakdown.build({
  baseRoster:S.roster,existingDraft:S.draft,route,
  start:result.start,end:result.end,baselineFP:result.baseline,
  opportunityPenalty:result.opportunityPenalty,
  games:normalizedGames(),players:P,scorePlayer:scenarioScorePlayer,
  project:(moves,start,end)=>rangeMean(S.roster,moves,start,end)
 });
}
function explainMultiHtml(ex){
 if(!ex?.ready)return '<div class="info warning" role="status">'+
  '\u0420\u0430\u0437\u0431\u0438\u0432\u043a\u0430 FP \u043d\u0435 \u0441\u043e\u0448\u043b\u0430\u0441\u044c \u0441 \u0440\u0430\u0441\u0447\u0451\u0442\u043e\u043c. '+
  '\u0427\u0438\u0441\u043b\u0430 \u0438 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f \u043f\u043e \u044d\u0442\u043e\u043c\u0443 \u0432\u0430\u0440\u0438\u0430\u043d\u0442\u0443 \u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d\u044b. '+esc(ex?.code||'UNKNOWN')+'</div>';
 const signed=v=>(v>=0?'+':'')+round(v,1);
 const fmtPlayer=(x,incoming)=>`<div class="decision-fp-row"><span>${esc(P[x.id]?.name||x.id)} <small>${incoming?x.intoGames:x.outGames} \u0438\u0433\u0440</small></span><b>${incoming?'+':'\u2212'}${round(incoming?x.intoFP:x.outFP,1)} FP</b></div>`;
 const inRows=ex.playersIn.map(x=>fmtPlayer(x,true)).join('');
 const outRows=ex.playersOut.map(x=>fmtPlayer(x,false)).join('');
 const games=ex.changedGames.slice(0,8).map(g=>`<div class="decision-fp-row"><span>${dateText(g.epoch)} \u041c\u0421\u041a \u00b7 ${esc(g.away)} @ ${esc(g.home)}</span><b>${signed(g.deltaFP)} FP</b></div>`).join('');
 return `<details class="decision-breakdown"><summary>\u041e\u0442\u043a\u0443\u0434\u0430 \u0431\u0435\u0440\u0443\u0442\u0441\u044f FP: ${signed(ex.gainFP)} \u043f\u043e \u043c\u0430\u0442\u0447\u0430\u043c</summary>
  <div class="decision-fp-total"><span>\u041f\u043b\u044e\u0441 \u043e\u0442 \u043d\u043e\u0432\u044b\u0445 \u0438\u0433\u0440\u043e\u043a\u043e\u0432 <b>+${round(ex.expectedIncomingFP,1)} FP</b></span><span>\u041c\u0438\u043d\u0443\u0441 \u043e\u0442 \u043f\u0440\u043e\u0434\u0430\u043d\u043d\u044b\u0445 <b>\u2212${round(ex.foregoneOutgoingFP,1)} FP</b></span><strong>\u0418\u0442\u043e\u0433 ${signed(ex.gainFP)} FP</strong></div>
  <div class="decision-fp-columns"><div><b>\u041f\u0440\u0438\u043e\u0431\u0440\u0435\u0442\u0451\u043d\u043d\u044b\u0435</b>${inRows||'<p class="small">\u041d\u0435\u0442</p>'}</div><div><b>\u0412\u044b\u0431\u044b\u0432\u0448\u0438\u0435</b>${outRows||'<p class="small">\u041d\u0435\u0442</p>'}</div></div>
  <div class="decision-fp-games"><b>\u0411\u043b\u0438\u0436\u0430\u0439\u0448\u0438\u0435 \u043c\u0430\u0442\u0447\u0438, \u0433\u0434\u0435 \u0435\u0441\u0442\u044c \u0440\u0430\u0437\u043d\u0438\u0446\u0430 (${ex.gamesChanged})</b>${games||'<p class="small">\u041d\u0435\u0442 \u0440\u0430\u0437\u043d\u0438\u0446\u044b</p>'}${ex.gamesChanged>8?`<p class="small">\u041f\u0435\u0440\u0432\u044b\u0435 8 \u0438\u0437 ${ex.gamesChanged}. \u0412\u0441\u0435 \u043c\u0430\u0442\u0447\u0438 \u0443\u0447\u0442\u0435\u043d\u044b \u0432 \u0438\u0442\u043e\u0433\u0435.</p>`:''}</div>
  <p class="small">\u042d\u0442\u043e \u043e\u0431\u044a\u044f\u0441\u043d\u0435\u043d\u0438\u0435 \u043c\u043e\u0434\u0435\u043b\u044c\u043d\u043e\u0439 \u0440\u0430\u0437\u043d\u0438\u0446\u044b, \u043d\u0435 \u0437\u0430\u0447\u0438\u0441\u043b\u0435\u043d\u043d\u044b\u0435 Sports.ru \u043e\u0447\u043a\u0438. \u0420\u0435\u0437\u0435\u0440\u0432 FP \u0437\u0430 \u0445\u043e\u0434 \u0432 \u0440\u0430\u0437\u0431\u0438\u0432\u043a\u0443 \u043d\u0435 \u0432\u0445\u043e\u0434\u0438\u0442.</p></details>`;
}
function multiPanel(){
 if(!window.NBAMultiPlanner||S.roster.length!==10)return '';
 const when=Number.isFinite(UI.plannerWhen)?UI.plannerWhen:now()+20*60000;
 const readiness=advicePreflight(UI.multiDays,when);
 const result=readiness.ready&&UI.multiResult?.signature===chainSignature()&&UI.multiCalculatedAt!=null&&now()-UI.multiCalculatedAt<=30*60000?UI.multiResult:null;
 const explanations=result?.ready?result.routes.map(route=>explainMulti(route,result)):[];
 const choices=['all',...POS].map(p=>`<option value="${p}" ${UI.multiFocus===p?'selected':''}>${p==='all'?'Вся десятка':p+' · '+POSRU[p]}</option>`).join('');
 const gain=n=>`<strong class="${n>=0?'delta-plus':'delta-minus'}">${n>=0?'+':''}${round(n,1)} FP</strong>`;
 const types={keep:'KEEP · не менять',multi_slot:'Несколько слотов',same_slot_chain:'Цепочка в одном слоте',later:'Отложить замену',now:'Заменить сейчас'};
 let detail='';
 if(result&&!result.ready)detail=`<div class="info warning" role="status">${esc(result.reason)}</div>`;
 else if(result?.ready){
  detail=`<div class="multi-results" role="status"><p class="small">Прогноз KEEP всей команды: ${round(result.baseline,1)} FP за ${result.horizonDays} дней. Проверено ${result.tested} промежуточных вариантов, полную проверку прошли ${result.eligible}. Это ограниченный поиск, не доказанный оптимум.</p>
   ${result.routes.map((route,i)=>`<div class="multi-route"><div class="horizontal" style="justify-content:space-between"><b>${esc(types[route.kind]||route.kind)}</b>${explanations[i]?.ready?gain(route.gain):'<strong>н/д</strong>'}</div>
    <div class="small">С резервом ${result.opportunityPenalty} FP за ход: ${explanations[i]?.ready?gain(route.net):'н/д'} · новых ходов ${route.moves.length} · касса ${round(route.cash)}</div>
    ${route.moves.length?route.moves.map((m,j)=>`<div class="multi-step"><span>${j+1}.</span> ${esc(P[m.out]?.name||m.out)} → <b>${esc(P[m.in_]?.name||m.in_)}</b><span class="small">${dateText(m.epoch)} МСК · ${round(m.sell)} → ${round(m.buy)}</span></div>`).join(''):'<p class="small">Состав сохраняется, новые ходы не расходуются.</p>'}
    ${route.samePairNow?.status==='comparable_scenario'
       ? `<p class="small">Та же пара при замене сейчас: ${gain(route.samePairNow.gainNowFP)}. Разница ожидания против немедленной замены: ${gain(route.samePairNow.waitMinusNowFP)}. Одинаковые предположительные цены; реальная выгода не подтверждена.</p>`
       : route.samePairNow?.status==='not_comparable'
         ? `<p class="small warntext">Не сравниваем с NOW: ${esc(route.samePairNow.reason)}.</p>`
         : ''}
    <div class="chain-weeks">${route.weeks.map(w=>`<span class="chain-week">${dateText(w.startEpoch)}–${dateText(w.endEpoch)} МСК · ${w.gain==null?'н/д':(w.gain>=0?'+':'')+round(w.gain,1)} FP · использовано (Пн 15 / Пн 00): ${w.used==null?'н/д':w.used}/3 · ${w.usedIf00==null?'н/д':w.usedIf00}/3${w.quotaResetVerified?'':' (гипотезы)'}</span>`).join('')}</div>
    ${route.warnings?.length?`<p class="small warntext">Проверить перед покупкой: ${esc(route.warnings.slice(0,2).join(' · '))}</p>`:''}
    ${multiEvidenceHtml(route)}
    ${route.moves.length?explainMultiHtml(explanations[i]):''}
    <button class="button" data-journal-freeze="${i}" ${explanations[i]?.ready?'':'disabled'}>Запомнить сравнение на момент решения (локально)</button>
    ${route.moves.length?`<button class="button" data-multi-apply="${i}" ${explanations[i]?.ready?'':'disabled'}>Добавить ${route.moves.length} шаг(а) только в черновик</button>`:''}</div>`).join('')}
   <p class="small">Результаты планов — сценарные FP, а не фактически измеренная выгода. Будущие цены и разблокировки неизвестны; при необходимости проверьте официальный статус NBA. Сигналы Telegram не повышают вероятность участия автоматически.</p></div>`;
 }
 const best=result?.ready?result.routes?.[0]:null;
 const fresh=UI.multiCalculatedAt!=null&&now()-UI.multiCalculatedAt<=30*60000;
 const bestExplanation=best?explanations[result.routes.indexOf(best)]:null;
 const bestAllowed=fresh&&bestExplanation?.ready;
 const bestReasons=best?[
  best.kind==='keep'
    ?'В ограниченном поиске не найден сценарий с более высоким модельным результатом после условного резерва за ход.'
    :'Для выбранного горизонта рассчитан прирост относительно сохранения состава; это не фактически полученные очки.',
  best.kind==='later'?'Ожидание сравнивается с немедленной покупкой при предположении неизменных цен.'
    :'Учитываются количество матчей и модельные ожидания участия, но сложность соперников не подтверждена.',
  'Реальные цены, остаток замен и разблокировки обязательно проверь на Sports.ru.'
 ]:[];
 const decisionSummary=best?`<div class="planner-outcome" role="status">
   <div class="planner-outcome-main"><div><span class="small">Лучший из найденных сценариев · ${result.horizonDays} дней</span>
   <h3>${best.kind==='keep'?'Пока оставить состав':best.kind==='later'?'Предпочтительнее рассмотреть замену позже':best.kind==='now'?'Есть вариант замены сейчас':'Есть вариант плана в несколько шагов'}</h3></div>
   <div class="planner-outcome-value">${bestExplanation?.ready?gain(best.net):'н/д'}<span>с учётом условного резерва за ходы</span></div></div>
   ${best.moves.length?best.moves.map((m,i)=>`<div class="planner-best-step"><b>${i+1}.</b> ${esc(P[m.out]?.name||m.out)} → <b>${esc(P[m.in_]?.name||m.in_)}</b> · ${dateText(m.epoch)} МСК</div>`).join(''):'<p>Не тратить трансфер — тоже полноценное решение.</p>'}
   <ol class="planner-best-reasons">${bestReasons.map((s,i)=>`<li><span>${i+1}</span>${esc(s)}</li>`).join('')}</ol>
   <p class="small">Это ограниченный сценарный поиск, не доказанная выгода или гарантия оптимума.</p>
   ${best.moves.length?explainMultiHtml(bestExplanation):''}
   ${!fresh?'<div class="info warning">Расчёт старше 30 минут; обновите варианты перед реальной заменой.</div>':''}
   <div class="toolbar"><button class="button" data-journal-freeze="${result.routes.indexOf(best)}" ${bestAllowed?'':'disabled'}>Сохранить сравнение локально</button>
   ${best.moves.length?`<button class="primary" data-multi-apply="${result.routes.indexOf(best)}" ${bestAllowed?'':'disabled'}>Добавить шаги в черновик</button>`:''}</div>
   </div>`:'';
 return `<div class="card multi-panel" id="multi-panel"><div class="titledetail"><h2>Совет по составу</h2><span class="pill">Не совершает трансферы</span></div>
  <p>Сравним сохранение состава, замену сейчас, ожидание и цепочки. Сначала посмотрите результат; настройка модели и прочие расчёты доступны по запросу.</p>
  ${!readiness.ready?`<div class="info warning" role="status"><b>Рекомендации пока недоступны.</b> ${esc(readiness.reasons.slice(0,2).join(' '))} Состав и календарь можно изучать без расчёта замен.</div>`:''}
  <div class="formgrid"><label>На какой срок смотрим<select id="multi-days">${[14,21,28].map(v=>`<option value="${v}" ${UI.multiDays===v?'selected':''}>${v} дней</option>`).join('')}</select></label>
  <div class="toolbar"><button class="primary" data-action="calculate-multi" ${readiness.ready?'':'disabled'}>Сравнить варианты</button></div></div>
  <div class="planner-reveal"><button type="button" class="ghost" data-action="multi-options-toggle" aria-expanded="${UI.multiOptions}">${UI.multiOptions?'Скрыть параметры поиска':'Уточнить поиск'}</button></div>
  ${UI.multiOptions?`<div class="formgrid"><label>Какие слоты учитывать<select id="multi-focus">${choices}</select></label>
   <label>Максимум новых замен<select id="multi-moves">${[1,2,3,4].map(v=>`<option value="${v}" ${UI.multiMoves===v?'selected':''}>${v}</option>`).join('')}</select></label>
   <label>Условный резерв за каждый ход<select id="multi-penalty">${[0,4,8].map(v=>`<option value="${v}" ${UI.multiPenalty===v?'selected':''}>${v} FP</option>`).join('')}</select></label>
   <label>Начать анализ (МСК)<input id="multi-when" type="datetime-local" value="${moscowInput(Number.isFinite(UI.plannerWhen)?UI.plannerWhen:now()+20*60000)}"></label></div>`:''}
  ${decisionSummary}${detail?`<details class="planner-explain"><summary>Все варианты и подробные проверки (${result?.routes?.length||0})</summary>${detail}</details>`:''}<details class="planner-journal"><summary>Мой журнал решений · ${decisionJournalCount()==null?'н/д':decisionJournalCount()}</summary><div class="toolbar"><button class="button" data-action="journal-export">Скачать журнал</button><button class="button" data-action="journal-clear">Очистить журнал</button></div><p class="small">Локальные наблюдения не синхронизируются с облаком. Для проверки пользы нужны результаты на Sports.ru. Условный резерв FP не является штрафом площадки.</p></details></div>`;
}
function calculateMulti(){
 if(!window.NBAMultiPlanner)return showMsg('Модуль общего планировщика не загрузился.');
 const raw=document.getElementById('multi-when')?.value;
 const t=raw?moscowEpoch(raw):Number.isFinite(UI.plannerWhen)?UI.plannerWhen:now()+20*60000;
 if(!Number.isFinite(t)||t<now()-60000)return showMsg('Выберите актуальное время начала анализа.');
 const readiness=advicePreflight(UI.multiDays,t);
 if(!readiness.ready){UI.multiResult=null;UI.multiCalculatedAt=null;view();return showMsg('Рекомендации заблокированы: '+readiness.reasons.slice(0,2).join(' '));}
 UI.plannerWhen=t;UI.multiCalculatedAt=now();
 const focus=UI.multiFocus==='all'?[]:planResult(S.draft).roster.filter(id=>P[id]?.pos===UI.multiFocus);
 const games=normalizedGames();
 const result=window.NBAMultiPlanner.plan({roster:S.roster,players:P,candidates:BASE.players,
  existingDraft:S.draft,nowEpoch:now(),whenEpoch:t,horizonDays:UI.multiDays,
  opportunityPenalty:UI.multiPenalty,maxMoves:UI.multiMoves,
  priceOf:prices,validateDraft:planResult,coverage:calendarCoverage,
  scorePlayer:scenarioScorePlayer,project:(moves,start,end)=>rangeMean(S.roster,moves,start,end),
  isCandidateAvailable:id=>S.medical[id]!=='out',focusIds:focus});
 result.signature=chainSignature();UI.multiResult=result;
 view();document.getElementById('multi-panel')?.scrollIntoView?.({behavior:'smooth',block:'start'});
}
function applyMulti(index){
 const readiness=advicePreflight(UI.multiDays,UI.multiResult?.start??now());
 if(!readiness.ready)return showMsg('Недостаточно подтверждённых данных для черновика: '+readiness.reasons.slice(0,2).join(' '));
 const result=UI.multiResult;
 if(!result?.ready||result.signature!==chainSignature()||!UI.multiCalculatedAt||now()-UI.multiCalculatedAt>30*60000)return showMsg('Данные или время изменились: пересчитайте варианты.');
 const route=result.routes?.[index];
 if(!route?.moves?.length)return showMsg('Это KEEP — добавлять в черновик нечего.');
 if(!explainMulti(route,result).ready)return showMsg('Разбивка FP не совпадает с прогнозом. Этот вариант заблокирован; пересчитайте.');
 if(route.moves.some(m=>m.epoch<now()-60000))return showMsg('Запланированное время уже прошло: пересчитайте план.');
 if(!calendarCoverage(result.start,result.horizonDays).ok)return showMsg('Календарь изменился: пересчитайте план.');
 const checked=planResult([...S.draft,...route.moves]);
 if(!checked.valid)return showMsg('План больше не допустим: '+checked.errors.join(' · '));
 const audit=multiEvidence(route);
 if(audit?.ready&&(audit.counts.officialOut||audit.counts.priceConflict)){
  const alert=audit.warnings.slice(0,3).join('\n');
  if(!confirm('Перед добавлением сценария обнаружены риски:\n'+alert+
      '\n\nДобавить ТОЛЬКО В ЧЕРНОВИК несмотря на них?'))return;
 }
 const summary=route.moves.map(m=>`${P[m.out]?.name||m.out} → ${P[m.in_]?.name||m.in_} (${dateText(m.epoch)} МСК)`).join('\n');
 if(!confirm('Добавить только в ЧЕРНОВИК '+route.moves.length+' шаг(а)?\n\n'+summary+'\n\nСверьте фактические цены и разблокировки на Sports.ru. Реальных трансферов не будет.'))return;
 S.draft.push(...route.moves);save();view();showMsg('План добавлен только в черновик. Реальные операции необходимо отдельно выполнить на Sports.ru.');
}
function calculateChains(){
 if(!window.NBAChainPlanner)return showMsg('Модуль цепочек ещё не загрузился.');
 const t=moscowEpoch(document.getElementById('when')?.value);
 const out=document.getElementById('out')?.value;
 if(!Number.isFinite(t)||!out)return showMsg('Укажите игрока OUT и время начала.');
 const readiness=advicePreflight(UI.chainDays,t);
 if(!readiness.ready){UI.chainResult=null;return showMsg('Рекомендации заблокированы: '+readiness.reasons.slice(0,2).join(' '));}
 UI.plannerOut=out;UI.plannerWhen=t;
 const checked=planResult(S.draft);
 const roster=checked.valid?checked.roster:S.roster;
 const scorePlayer=scenarioScorePlayer;
 const sellInput=num(document.getElementById('sell')?.value);
 const reply=window.NBAChainPlanner.rank({out,roster,players:P,candidates:BASE.players,
  existingDraft:S.draft,nowEpoch:now(),whenEpoch:t,horizonDays:UI.chainDays,
  opportunityPenalty:UI.chainPenalty,priceOf:id=>id===out&&Number.isFinite(sellInput)?sellInput:prices(id),
  validateDraft:planResult,coverage:calendarCoverage,scorePlayer,
  project:(moves,start,end)=>rangeMean(S.roster,moves,start,end)});
 reply.signature=chainSignature();UI.chainResult=reply;
 view();
 const panel=document.getElementById('chain-panel');panel?.scrollIntoView?.({behavior:'smooth',block:'start'});
}
function applyChain(index){
 const readiness=advicePreflight(UI.chainDays,UI.chainResult?.start??now());
 if(!readiness.ready)return showMsg('Рекомендации заблокированы: '+readiness.reasons.slice(0,2).join(' '));
 const result=UI.chainResult;
 if(!result?.ready||result.signature!==chainSignature())return showMsg('Данные изменились — сначала пересчитайте цепочку.');
 const route=result.routes?.[index];if(!route?.moves?.length)return showMsg('Нет замен для добавления.');
 if(route.moves.some(m=>m.epoch<now()-60000))return showMsg('Указанное время уже прошло. Пересчитайте цепочку.');
 const checked=planResult([...S.draft,...route.moves]);
 if(!checked.valid)return showMsg('План больше не соответствует ограничениям: '+checked.errors.join(' · '));
 if(!confirm('Добавить '+route.moves.length+' условных шаг(а) только в ЧЕРНОВИК? Будущие цены и разблокировки нужно отдельно проверить в Sports.ru. Реальный трансфер не выполняется.'))return;
 S.draft.push(...route.moves);save();view();showMsg('Цепочка добавлена в черновик. Проверьте будущие цены, доступность игроков и лимит замен перед реальными операциями.');
}
function planByWeeks(draft){
 const start=Date.parse(calendarMoscowWeek(now())+'T00:00:00+03:00');
 if(!calendarCoverage(now(),28).ok)return `<div class="card"><h2>Помесячный план по неделям</h2><div class="info warning">${esc(calendarCoverage(now(),28).reason)}. Не показываем ложные нулевые FP по неделям.</div></div>`;
 const result=planResult(draft);
 const spans=Array.from({length:4},(_,i)=>{
  const a=start+i*7*86400000,b=a+7*86400000;
  const base=rangeMean(S.roster,[],Math.max(now(),a),b);
  const withPlan=rangeMean(S.roster,draft,Math.max(now(),a),b);
  return {a,base,withPlan,diff:withPlan-base,used:result.used[moscowWeek(a+15*3600000)]||0};
 });
 const max=Math.max(1,...spans.map(z=>Math.max(z.base,z.withPlan)));
 return `<div class="card"><div class="titledetail"><h2>Что изменится по неделям</h2><span class="small">Прогноз, не начисленные FP</span></div><div class="weekrows">${spans.map((r,i)=>`<div class="weekrow"><div class="horizontal"><b>Неделя ${i+1}</b><span class="small">с ${justDay(r.a)} · оценка Пн 15: ${r.used}/3</span></div><div class="weekbar" aria-hidden="true"><span style="width:${Math.round(r.base/max*100)}%"></span></div><div class="weekbar planned" aria-hidden="true"><span style="width:${Math.round(r.withPlan/max*100)}%"></span></div><div class="horizontal"><span class="small">Без плана ${round(r.base)} → с планом <b>${round(r.withPlan)}</b></span><b class="${r.diff>=0?'delta-plus':'delta-minus'}">${r.diff>=0?'+':''}${round(r.diff,1)} FP</b></div></div>`).join('')}</div><p class="small">Рассчитаны только игры, уже присутствующие в календаре. Штраф за использованный трансфер не переводится в FP: решение оценивается отдельно.</p></div>`;
}
function retroBlank(){return {when:'',out:'',in_:'',sell:'',buy:''};}
function retroInput(){return {
 players:P,initialRoster:S.initialRoster,currentRoster:S.roster,currentCash:S.cash,
 existing:S.executed,proposed:UI.retroRows.map(r=>({
  epoch:moscowEpoch(r.when),out:r.out,in_:r.in_,sell:r.sell,buy:r.buy
 })),initialEpoch:S.initialEpoch,nowEpoch:now(),draftCount:S.draft.length
};}
function retroSignature(){return JSON.stringify({rows:UI.retroRows,initial:S.initialRoster,
 current:S.roster,cash:S.cash,executed:S.executed,draft:S.draft,epoch:S.initialEpoch,teams:S.teamOverrides});}
function retroPanel(){
 if(!UI.retroRows.length)UI.retroRows=[retroBlank()];
 const open=UI.retroOpen;
 const rows=UI.retroRows.map((row,i)=>{
  const at=moscowEpoch(row.when);
  const roster=Number.isFinite(at)?window.NBATransferHistory.rosterBefore({
   initialRoster:S.initialRoster,existing:S.executed,
   proposed:UI.retroRows.map(r=>({...r,epoch:moscowEpoch(r.when)}))
  },at,i):[...S.initialRoster];
  const pos=P[row.out]?.pos;
  const outOptions=roster.filter(id=>P[id]).map(id=>
    `<option value="${esc(id)}" ${row.out===id?'selected':''}>${esc(P[id].name)} · ${P[id].pos}</option>`).join('');
  const extraOut=row.out&&!roster.includes(row.out)?
    `<option value="${esc(row.out)}" selected>⚠ ${esc(P[row.out]?.name||row.out)} — нет в составе на дату</option>`:'';
  const buys=pos?BASE.players.filter(p=>p.pos===pos&&!roster.includes(p.id)):[ ];
  const inOptions=buys.slice().sort((a,b)=>a.name.localeCompare(b.name,'ru')).map(p=>
    `<option value="${esc(p.id)}" ${row.in_===p.id?'selected':''}>${esc(p.name)} · ${p.team}</option>`).join('');
  const extraIn=row.in_&&!buys.some(p=>p.id===row.in_)?
    `<option value="${esc(row.in_)}" selected>⚠ ${esc(P[row.in_]?.name||row.in_)} — перепроверь</option>`:'';
  const field=(name,html)=>`<label>${name}${html}</label>`;
  return `<div class="retro-row" role="group" aria-label="Старая замена ${i+1}">
    <div class="titledetail"><b>Замена ${i+1}</b><button type="button" class="ghost" data-action="retro-remove" data-idx="${i}" ${UI.retroRows.length===1?'disabled':''}>Убрать строку</button></div>
    <div class="retro-grid">
     ${field('Фактическое время, МСК',`<input type="datetime-local" data-history-index="${i}" data-history-field="when" value="${esc(row.when)}">`)}
     ${field('Кого продал (OUT)',`<select data-history-index="${i}" data-history-field="out"><option value="">Выбери OUT</option>${extraOut}${outOptions}</select>`)}
     ${field('Кого купил (IN)',`<select data-history-index="${i}" data-history-field="in_" ${pos?'':'disabled'}><option value="">Выбери IN после OUT</option>${extraIn}${inOptions}</select>`)}
     ${field('Цена продажи тогда',`<input type="number" min="0" step="any" placeholder="Цена Sports.ru" data-history-index="${i}" data-history-field="sell" value="${esc(row.sell)}">`)}
     ${field('Цена покупки тогда',`<input type="number" min="0" step="any" placeholder="Цена Sports.ru" data-history-index="${i}" data-history-field="buy" value="${esc(row.buy)}">`)}
    </div>
   </div>`;
 }).join('');
 const p=UI.retroPreview;
 const fresh=p&&p.signature===retroSignature();
 const result=fresh?p.result:null;
 const preview=result?`<div class="retro-preview" role="status">
   <div class="info ${result.valid?'':'error'}"><b>${result.valid?'История согласована. Это только предварительный расчёт.':'Нельзя записать историю'}</b>
   ${result.errors.length?`<div>${result.errors.map(esc).join(' · ')}</div>`:''}</div>
   ${result.valid?`<div class="retro-results"><span>Новых операций: <b>${result.stepsAdded}</b></span>
    <span>Всего в журнале: <b>${result.mergedExecuted.length}</b></span>
    <span>Касса сейчас: <b>${round(result.currentCash,2)}</b></span>
    <span>После внесения: <b>${round(result.cash,2)}</b></span></div>
    <div class="retro-result-roster">Итоговая десятка: ${result.roster.map(id=>esc(P[id]?.name||id)).join(' · ')}</div>
    <div class="retro-timeline"><b>Порядок операций</b>${result.timeline.map(t=>
      `<div class="donut"><span>${t.source==='new'?'<strong>Добавляем</strong>':'Уже было'} · ${esc(dateText(t.epoch))} · ${esc(P[t.out]?.name)} → ${esc(P[t.in_]?.name)}</span><b>${round(t.cashAfter,2)}</b></div>`
     ).join('')}</div>
    <div class="info warning">${result.warnings.map(esc).join(' · ')}. Обязательно сверяй итоговую кассу и состав на Sports.ru.</div>`:''}
  </div>`:'';
 return `<div class="card retro-card" id="retro-card">
  <div class="titledetail"><div><h2 style="margin:0">Уже сделал замены на Sports.ru?</h2>
   <span class="small">Записать прошлые операции с их реальными датами и ценами</span></div>
   <button type="button" class="button" data-action="retro-toggle" aria-expanded="${open}">${open?'Свернуть':'Записать прошлые замены'}</button></div>
  ${open?`<div class="info">Это только учёт <b>уже совершённых</b> операций, не новые трансферы. Сначала убедись, что их ещё нет в журнале. Программа восстановит состав на каждую дату, включая ранее записанные замены. Состав на Sports.ru она не меняет.</div>
   ${S.draft.length?`<div class="info warning">В черновике ${S.draft.length} операций. Для безопасного внесения истории сначала сохрани резервную копию и очисти черновик, если он больше не нужен.</div>`:''}
   ${rows}<div class="toolbar"><button class="button" data-action="retro-add" ${UI.retroRows.length>=12?'disabled':''}>+ Ещё замена</button>
    <button class="primary" data-action="retro-preview">Проверить всю историю</button></div>
   ${preview}
   <div class="toolbar"><button class="primary" data-action="retro-save" ${!result?.valid?'disabled':''}>Сохранить уже выполненные замены</button>
    <button class="button" data-action="export-state">Скачать резервную копию</button></div>
   <p class="small">Перед изменением автоматически скачается резервная копия профиля. Если исходный состав, даты или цены неправильные, ничего не сохраняй. Уже записанные операции программа не дублирует.</p>`:''}</div>`;
}
function retroPreviewHistory(){
 const result=window.NBATransferHistory.preview(retroInput());
 UI.retroPreview={signature:retroSignature(),result};
 view();
}
function retroCommitHistory(){
 if(!UI.retroPreview||UI.retroPreview.signature!==retroSignature())return showMsg('Сначала заново проверь историю');
 const result=window.NBATransferHistory.preview(retroInput());
 if(!result.valid)return showMsg('Запись отменена: '+result.errors.join(' · '));
 if(!confirm('Подтверди: ты УЖЕ выполнил на Sports.ru '+result.stepsAdded+' замен(ы), и их ещё нет в журнале?\n\nПосле записи состав и касса в приложении изменятся; Sports.ru не затронется.\n\nБудет скачана резервная копия.'))return;
 // Local export is deliberately done BEFORE any change to the personal state.
 download('NBA_Season_Lab_before_backfill_'+new Date().toISOString().slice(0,19).replace(/[:T]/g,'-')+'.json',S);
 S.executed=result.mergedExecuted;
 S.roster=[...result.roster];
 S.cash=result.cash;
 UI.retroRows=[retroBlank()];UI.retroPreview=null;UI.retroOpen=false;
 save();showMsg('История подтверждённых операций сохранена только в NBA Season Lab. Проверь состав и кассу по Sports.ru.');
}
function privatePriceEvidenceCard(out,incoming){
 const mod=window.NBAPriceEvidence;
 if(!mod)return `<div class="card"><h2>Журнал цен Sports.ru</h2><p class="small">Локальный модуль недоступен: цены не фиксируются.</p></div>`;
 let count=0,last=null,restored=false,problem='';
 try{const data=mod.read(localStorage);count=data.receipts.length;last=data.receipts.at(-1)||null;restored=data.restored_from_file_unverified;}
 catch(e){problem='Локальный журнал не удалось прочитать: '+String(e.message||e).slice(0,120);}
 const ready=!!(P[out]&&P[incoming]&&out!==incoming);
 const who=ready?`${esc(P[out].name)} → ${esc(P[incoming].name)}`:'Выбери двух разных игроков в форме замены';
 const recent=last?`Последняя ручная отметка: ${dateText(Date.parse(last.observed_at_utc))} МСК · ${esc(P[last.quotes[0].player_id]?.name||last.quotes[0].player_id)} → ${esc(P[last.quotes[1].player_id]?.name||last.quotes[1].player_id)}.`:'Ещё нет записей.';
 return `<div class="card" id="price-evidence-card">
  <div class="titledetail"><h2>Подтверждение цен Sports.ru</h2><span class="pill">Локально · без облака</span></div>
  <p class="small">${who}. Две цены вводятся только вручную после проверки Sports.ru; расчётные значения не копируются. Запись не меняет состав, кассу, прогноз или черновик.</p>
  <div class="formgrid">
   <label>Продать за (точная цена Sports.ru)<input id="price-proof-sell" type="number" min="0" max="20000" step="1" placeholder="Введите вручную" autocomplete="off"></label>
   <label>Купить за (точная цена Sports.ru)<input id="price-proof-buy" type="number" min="0" max="20000" step="1" placeholder="Введите вручную" autocomplete="off"></label>
   <label>Касса на Sports.ru (необязательно)<input id="price-proof-cash" type="number" min="0" max="20000" step="1" placeholder="Необязательно" autocomplete="off"></label>
   <label>Осталось замен (необязательно)<input id="price-proof-quota" type="number" min="0" max="3" step="1" placeholder="Необязательно" autocomplete="off"></label>
  </div>
  <div class="toolbar"><label class="small"><input type="checkbox" id="price-proof-reviewed"> Я прямо сейчас проверил обе цены на Sports.ru</label></div>
  <div class="toolbar">
    <button class="button" data-action="price-proof-save" ${ready&&!problem?'':'disabled'}>Зафиксировать цены и время</button>
    <button class="ghost" data-action="price-proof-export">Экспорт журнала JSON</button>
    <label class="button" style="position:relative;cursor:pointer">Импорт журнала<input id="price-proof-file" type="file" accept=".json,application/json" style="display:none"></label>
    <button class="ghost" data-action="price-proof-delete">Очистить журнал</button>
  </div>
  <p class="small">Записей: ${count}. ${recent} ${restored?'Журнал восстановлен из файла: исходные времена не подтверждены независимо.':''}</p>
  ${problem?`<div class="info error">${esc(problem)}</div>`:''}
  <div class="info warning">Время — часы этого браузера, не время публикации Sports.ru. Цены не проверены автоматически, блокировка и квота тоже не подтверждаются этой формой. Журнал не попадёт в обычную облачную копию состава: экспортируйте его отдельно. Хранилище этого браузера может быть очищено. На общем устройстве журнал доступен другим пользователям этого браузера; при необходимости экспортируйте и удалите его.</div>
 </div>`;
}
function privatePriceCapture(){
 try{
  const mod=window.NBAPriceEvidence;
  if(!mod)throw Error('Локальный модуль недоступен');
  const outId=document.getElementById('out')?.value;
  const inId=document.getElementById('in')?.value;
  const input={outId,inId,
   confirmedSellPrice:document.getElementById('price-proof-sell')?.value,
   confirmedBuyPrice:document.getElementById('price-proof-buy')?.value,
   confirmedCash:document.getElementById('price-proof-cash')?.value,
   confirmedQuota:document.getElementById('price-proof-quota')?.value,
   userConfirmedNow:document.getElementById('price-proof-reviewed')?.checked===true};
  const receipt=mod.capture(localStorage,input);
  showMsg('Цены отмечены по часам браузера: '+dateText(Date.parse(receipt.observed_at_utc))+' МСК. Локальный журнал сохранён отдельно. Состав и Sports.ru не изменены.');
 }catch(e){showMsg('Не удалось сохранить цену: '+String(e.message||e).slice(0,160));}
}
function privatePriceExport(){
 try{const data=window.NBAPriceEvidence.exportData(localStorage);
  download('nba-season-lab-private-price-evidence.json',data);
  showMsg('Экспортирован отдельный приватный журнал цен. В облачную копию он не входит.');
 }catch(e){showMsg('Не удалось экспортировать журнал: '+String(e.message||e).slice(0,160));}
}
async function privatePriceImport(file){
 try{
  if(file.size>1000000)throw Error('Файл слишком велик');
  const raw=JSON.parse(await file.text());
  if(!confirm('Заменить локальный журнал цен записями из выбранного файла? Существующий журнал будет перезаписан. Временные метки старой копии независимо не подтверждены.'))return;
  const n=window.NBAPriceEvidence.importData(localStorage,raw,true);
  showMsg('Восстановлено '+n+' старых локальных отметок. Они не считаются независимо подтверждёнными наблюдениями.');
 }catch(e){showMsg('Импорт журнала отклонён: '+String(e.message||e).slice(0,180));}
 finally{const input=document.getElementById('price-proof-file');if(input)input.value='';}
}
function privatePriceDelete(){
 if(!confirm('Удалить ВСЕ локальные отметки цен из этого браузера? Это нельзя отменить без отдельно экспортированной копии.'))return;
 try{window.NBAPriceEvidence.erase(localStorage,true);showMsg('Локальный журнал цен очищен. Состав, касса и черновики не изменены.');}
 catch(e){showMsg('Не удалось очистить журнал: '+String(e.message||e).slice(0,160));}
}
function plannerTaskNav(){
 const tasks=[
  ['advice','Нужна ли замена?','Сравнить оставить / сейчас / позже'],
  ['specific','Подобрать игрока','Найти замену для конкретного слота'],
  ['sequence','План на недели','Составить несколько ходов заранее'],
  ['record','Записать сделанную замену','Внести реальный ход со Sports.ru']
 ];
 const current=tasks.find(x=>x[0]===UI.plannerTask)||tasks[0];
 return `<div id="planner-task" class="card planner-entry planner-entry--compact">
  <div class="planner-task-current"><div><span class="small">Текущая задача</span><h2>${esc(current[1])}</h2><p>${esc(current[2])}</p></div>
  <button type="button" class="button" data-action="planner-task-toggle" aria-expanded="${UI.plannerTaskListOpen}">${UI.plannerTaskListOpen?'Скрыть':'Другая задача'}</button></div>
  ${UI.plannerTaskListOpen?`<div class="planner-task-grid" role="group" aria-label="Выбор задачи">
    ${tasks.map(([id,label,hint])=>`<button type="button" class="planner-task ${UI.plannerTask===id?'active':''}" data-planner-task="${id}" aria-pressed="${UI.plannerTask===id}"><b>${label}</b><span>${hint}</span></button>`).join('')}
  </div>`:''}</div>`;
}
function plannerStateBar(){
 const checked=planResult(S.draft);
 const p15=moscowWeek(now()),p00=calendarMoscowWeek(now());
 const c15=S.executed.filter(t=>moscowWeek(t.epoch)===p15).length;
 const c00=S.executed.filter(t=>calendarMoscowWeek(t.epoch)===p00).length;
 return `<div class="planner-statebar" role="status">
  <span>Касса по журналу: <b>${round(S.cash)}</b></span>
  ${S.draft.length?`<span>Черновик: <b>${S.draft.length}</b></span>`:''}
  <span class="planner-quota" title="Время сброса Sports.ru не подтверждено. Это не количество доступных ходов, а подсчёт по двум временным гипотезам.">Замены по истории: <b>${c15}/3</b> или <b>${c00}/3</b> <small>— границу проверьте на Sports.ru</small></span>
  ${checked.errors.length?`<span class="planner-state-error">В черновике ошибка: ${esc(checked.errors[0])}</span>`:''}
 </div>`;
}
function plannerDraftCard(checked,steps,seven,fourteen,base7,base14){
 return `<div class="card" id="planner-draft"><div class="titledetail"><h2>Мой черновик · ${S.draft.length}</h2><span class="pill">Не выполнен на Sports.ru</span></div>
  ${steps}
  ${S.draft.length?`<div class="review"><div class="donut"><span>Условный эффект за 7 / 14 дней</span><b>${approx(seven-base7)} / ${approx(fourteen-base14)} FP</b></div><div class="donut"><span>Касса после шагов</span><b>${round(checked.cash)}</b></div></div>`:''}
  ${checked.errors.length?`<div class="info error">${checked.errors.map(esc).join(' · ')}</div>`:''}
  ${checked.warnings.length?`<div class="info warning">${checked.warnings.slice(0,3).map(esc).join(' · ')}</div>`:''}
  <div class="toolbar"><button class="button" data-action="clear-draft" ${S.draft.length?'':'disabled'}>Очистить черновик</button>
  <button class="primary" data-action="confirm-draft" ${(!S.draft.length||!checked.valid||S.draft.some(t=>t.epoch>now()+2*60000))?'disabled':''}>Отметить выполненным в сервисе</button></div>
  <p class="small">Последняя кнопка — только после того, как вы уже выполнили все эти замены на Sports.ru. Она обновляет историю, состав и кассу в NBA Season Lab; Sports.ru не затрагивается.</p>
 </div>`;
}
function plannerPage(){
 if(S.roster.length!==10)return header('Решения','Замены','Сначала сохраните десятку на странице «Команда».')+
   `<div class="card"><h2>Сначала нужен состав</h2><p>Сервис не может сравнить варианты без реальных десяти игроков и кассы.</p><button class="primary" data-tabto="overview">Перейти к составу</button></div>`;
 const prior=planResult(S.draft),available=prior.valid?prior.roster:S.roster;
 const out=available.includes(UI.plannerOut)?UI.plannerOut:available[0];
 const choices=allowedIds(out,available);
 const dst=choices.some(p=>p.id===UI.plannerIn)?UI.plannerIn:choices[0]?.id;
 const when=Number.isFinite(UI.plannerWhen)?UI.plannerWhen:now()+20*60000;
 const checked=planResult(S.draft);
 const signed=n=>Number.isFinite(n)?(n>=0?'+':'')+approx(n):'н/д';
 const seven=plannedMean(S.roster,S.draft,7),fourteen=plannedMean(S.roster,S.draft,14);
 const base7=plannedMean(S.roster,[],7),base14=plannedMean(S.roster,[],14);
 const ordered=[...S.draft].sort((a,b)=>a.epoch-b.epoch);
 const steps=ordered.length?ordered.map((t,i)=>{
  const st=checked.steps.find(x=>x.t===t);
  return `<div class="step"><span class="step-index">${i+1}</span><div style="flex:1"><b>${esc(P[t.out]?.name||t.out)} → ${esc(P[t.in_]?.name||t.in_)}</b><div class="small">${dateText(t.epoch)} МСК · ${round(t.sell)} → ${round(t.buy)} · касса ${round(st?.cash)}</div>${st?.errors.length?`<div class="warntext">${esc(st.errors.join(' · '))}</div>`:''}</div><button class="ghost" data-remove-draft="${S.draft.indexOf(t)}">Удалить</button></div>`;
 }).join(''):'<p class="muted">Пока пусто. Это нормально: не всегда нужно делать замену.</p>';
 const form=`<div class="formgrid">
  <label>Кого заменить<select id="out">${available.map(id=>`<option value="${id}" ${out===id?'selected':''}>${esc(P[id].name)} · ${P[id].pos}</option>`).join('')}</select></label>
  <label>На кого<select id="in">${choices.map(p=>`<option value="${p.id}" ${dst===p.id?'selected':''}>${esc(p.name)} · ${p.team} · ≈${round(prices(p.id))}</option>`).join('')}</select></label>
  <label>Когда (МСК)<input id="when" type="datetime-local" value="${moscowInput(when)}"></label>
  <label>Цена продажи на Sports.ru<input id="sell" type="number" min="0" value="${UI.plannerSell!=null?UI.plannerSell:prices(out)}"></label>
  <label>Цена покупки на Sports.ru<input id="buy" type="number" min="0" value="${UI.plannerBuy!=null?UI.plannerBuy:prices(dst)}"></label>
  <div class="toolbar" style="align-self:end"><button class="button" data-action="preview-transfer">Проверить</button><button class="primary" data-action="add-draft">В черновик</button></div></div>`;
 const officialCandidates=officialForPlayers([out,dst]);
 const officialHint=officialCandidates.length?`<div class="info warning"><b>Статусы игроков по NBA:</b>${officialCandidates.map(officialCard).join('')}<span class="small">Проверьте актуальный отчёт перед реальной покупкой.</span></div>`:'';
 let content='';
 if(UI.plannerTask==='advice'){
  content=multiPanel();
 }else if(UI.plannerTask==='specific'){
  content=`<div class="card planner-manual" id="planner-manual"><div class="titledetail"><h2>Проверить одного игрока</h2><span class="pill">Цены уточняются вручную</span></div>
    <p>Выберите, кого хотите продать. Ниже — возможные замены с учётом вашей кассы.</p>
    ${form}
    ${UI.quickPreview?`<div class="info ${UI.quickPreview.valid?'':'error'}" role="status"><b>${UI.quickPreview.valid?'Проверка пройдена с оговорками':'Такой вариант сейчас не проходит проверку'}</b><div>${UI.quickPreview.valid?'Прогноз относительно KEEP: '+signed(UI.quickPreview.gain7)+' FP за 7 дней и '+signed(UI.quickPreview.gain14)+' FP за 14 дней.':esc(UI.quickPreview.errors.join(' · '))}</div>${UI.quickPreview.warnings.length?`<div>${esc(UI.quickPreview.warnings.slice(0,3).join(' · '))}</div>`:''}</div>`:''}
    ${officialHint}${shortlistPanel(out,when,available)}
    <div class="info">Цены в списке ориентировочные. Перед переносом в реальные трансферы проверьте две цены, остаток замен и блокировки на Sports.ru.</div>
   </div>
   <div class="planner-reveal"><button type="button" class="button" data-action="planner-manual-toggle" aria-expanded="${UI.plannerManualOpen}">${UI.plannerManualOpen?'Скрыть подтверждение цен':'Дополнительно: зафиксировать цены Sports.ru'}</button></div>
   ${UI.plannerManualOpen?privatePriceEvidenceCard(out,dst):''}
   ${plannerDraftCard(checked,steps,seven,fourteen,base7,base14)}`;
 }else if(UI.plannerTask==='sequence'){
  const tool=UI.plannerSequenceTool;
  content=`<p class="planner-task-instruction">Сначала сравните варианты всей команды на выбранном периоде. Отдельные инструменты нужны, только если у вас есть специальная цель.</p>`+multiPanel()+
  `<div class="card"><h2>Особая задача?</h2><div class="planner-tool-row">
   <button type="button" class="button ${tool==='chain'?'selected':''}" data-planner-tool="chain" aria-pressed="${tool==='chain'}">Поменять одного сейчас или позже</button>
   <button type="button" class="button ${tool==='budget'?'selected':''}" data-planner-tool="budget" aria-pressed="${tool==='budget'}">Нужен дорогой игрок — собрать бюджет</button>
   ${tool!=='none'?'<button type="button" class="ghost" data-planner-tool="none">Скрыть инструменты</button>':''}</div></div>`+
   (tool==='chain'?`<div class="card"><h2>Выберите исходного игрока и время</h2>${form}</div>${chainPanel(out,when)}`:tool==='budget'?budgetPanel():'')+
   `<div class="planner-reveal"><button type="button" class="button" data-action="planner-detail-toggle" aria-expanded="${UI.plannerDetail}">${UI.plannerDetail?'Скрыть недельную разбивку':'Показать расчёты по неделям'}</button></div>`+
   (UI.plannerDetail?scenarioPanel(S.draft,checked)+planByWeeks(S.draft):'')+
   (S.draft.length?plannerDraftCard(checked,steps,seven,fourteen,base7,base14):'');
 }else if(UI.plannerTask==='record'){
  content=`<p class="planner-task-instruction">Вносите только операции, которые уже совершили на Sports.ru. Понадобятся дата и время, проданный и купленный игрок и две цены.</p>`+
   (S.draft.length?plannerDraftCard(checked,steps,seven,fourteen,base7,base14):'')+
   retroPanel()+`<div class="card"><h2>Последние записанные замены</h2>${S.executed.length?S.executed.slice(-5).reverse().map(t=>`<div class="donut"><span>${dateText(t.epoch)} · ${esc(P[t.out]?.name||t.out)} → ${esc(P[t.in_]?.name||t.in_)}</span><b>${round(t.sell)} → ${round(t.buy)}</b></div>`).join(''):'<p>Пока нет выполненных операций в журнале.</p>'}</div>`;
 }else{UI.plannerTask='advice';content=multiPanel();}
 return header('Моя команда','Замены','Выберите задачу — сервис покажет только нужные действия. Ни один сценарий сам не совершает трансферы.')+
  plannerStateBar()+plannerTaskNav()+content+
  `<div class="planner-reveal"><button type="button" class="ghost" data-action="planner-advanced-toggle" aria-expanded="${UI.plannerAdvanced}">${UI.plannerAdvanced?'Скрыть настройки расчётов':'Настройки модели и ограничения'}</button></div>`+
  (UI.plannerAdvanced?planningControls()+`<div class="card"><h2>Что важно знать</h2><p>Прогнозы и вероятности участия пока не доказаны для всей совокупности игроков. Цены кроме ручных подтверждений — оценки. Две границы сброса квоты (Пн 00:00 и Пн 15:00 МСК) — гипотезы, а не две отдельные квоты.</p><button class="button" data-tabto="data">Проверить данные и цены</button></div>`:'');
}
function sourceHealth(){
 const h=NBA_HISTORY,news=TG_NEWS,m=MODEL_REPORT;
 const n=h?.qa?.matched_player_game_rows??null;
 const officialQuality=window.NBAOfficialStatus?.validate(OFFICIAL_FEED);
 const officialAge=officialQuality?.ok?(now()-officialQuality.updatedAt)/3600000:Infinity;
 const officialLabel=officialQuality?.ok?`${officialQuality.matched} / ${officialQuality.raw} строк`:'Недоступен';
 const officialSub=officialQuality?.ok?`Первичный PDF NBA · ${Math.floor(officialAge)} ч от последнего отчёта`:OFFICIAL_STATUS;
 return `<div class="card"><h2>Источники · прозрачность</h2><div class="grid metrics source-grid"><div class="metric"><span class="k">История NBA, 3 сезона</span><strong>${n==null?'Не загружена':round(n)+' строк'}</strong><span class="more">${esc(h?.status||'Нужен исторический импорт')}</span></div><div class="metric"><span class="k">Telegram</span><strong>${news?.events?.length??'—'} сообщений</strong><span class="more">${esc(news?.updated_at_utc||'Загрузка пока не выполнена')} · только публичные посты</span></div><div class="metric"><span class="k">Валидация новой модели</span><strong>${m?.status==='validated_for_single_game_mean'?'Кандидат прошёл тест':m?.status==='baseline_retained'?'Базовая оставлена':'Не проверена'}</strong><span class="more">${m?.holdout?.n?'Отложенные наблюдения: '+round(m.holdout.n):'Без новых исторических рядов выводов нет'}</span></div><div class="metric"><span class="k">Текущий сезон NBA</span><strong>${round(LIVE.rows?.length||0)} записей</strong><span class="more">${esc(currentStatus())}</span></div><div class="metric"><span class="k">Официальные NBA Injury Reports</span><strong>${esc(officialLabel)}</strong><span class="more">${esc(officialSub)}</span></div></div><p class="small">Публичный пост Telegram не подтверждает статус игрока. Историческая метрика MAE не означает точности прогноза недельных FP в 2026/27.</p></div>`;
}
function dataPage(){
 const age=(now()-Date.parse(LIVE.updated_at_utc||0))/3600000;
 const partial=['seed_partial_verified','sync_failed_using_cache','schedule_sync_only'].includes(LIVE.mode);
 const report=LIVE.source_status;
 const providers=typeof report==='object'?Object.entries(report).map(([k,v])=>`<div class="donut"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join(''):esc(report||'статический файл');
 const pricesHtml=S.roster.map(id=>`<div class="donut"><span>${esc(P[id]?.name||id)} · ${esc(P[id]?.team||'')}</span><div class="horizontal"><input class="priceedit" data-price-id="${esc(id)}" type="number" min="0" aria-label="Цена ${esc(P[id]?.name||id)}" value="${round(prices(id)).replace(/\s/g,'')}" style="width:100px;max-width:100px;padding:5px 6px;border:1px solid var(--line);border-radius:6px"><button class="ghost" data-price-reset="${esc(id)}" title="Вернуть расчётную">↻</button></div></div>`).join('');
 const teamsHtml=S.roster.map(id=>`<div class="donut"><span>${esc(P[id]?.name||id)}</span><select class="teamedit" data-team-id="${esc(id)}" aria-label="Клуб ${esc(P[id]?.name||id)}" style="max-width:155px"><option value="auto" ${!(S.teamOverrides||{})[id]?'selected':''}>Авто · ${esc(P[id]?.team||'')}</option>${Object.keys(CLUBS).sort().map(t=>`<option value="${esc(t)}" ${S.teamOverrides?.[id]===t?'selected':''}>${esc(t)}</option>`).join('')}</select></div>`).join('');
 return header('Данные','Данные и цены','Сначала актуальность и ваша касса. Сложную техническую диагностику можно раскрыть отдельно.')+
 `<div class="grid columns"><div><section class="card"><div class="titledetail"><h2>Обновление статистики</h2><span class="pill ${age>24||partial?'warn':'good'}">${esc(currentStatus())}</span></div>
 <p>Статистика NBA обновляется через публичный GitHub. Источник: <b>${esc(liveSource)}</b>.</p>
 ${onlineError?`<p class="warntext">${esc(onlineError)}</p>`:''}<button class="primary" data-action="refresh">Проверить свежие данные</button>
 <p class="small">Это не обновление цен Sports.ru и не прямой эфир.</p></section>
 <section class="card"><h2>Цены моей команды</h2><p>Укажите фактические значения Sports.ru. Без ручной проверки модельные цены могут быть неточными.</p>
 ${pricesHtml||'<div class="empty">Состав ещё не заполнен.</div>'}<div class="separator"></div><label for="cash"><b>Свободная касса</b></label>
 <div class="horizontal" style="margin-top:8px"><input type="number" min="0" id="cash" value="${round(S.cash).replace(/\s/g,'')}" style="width:130px;padding:9px;border:1px solid var(--line);border-radius:7px"><button class="button" data-action="set-cash">Сохранить кассу</button></div>
 <p class="small">Реальная замена обновляет кассу в сервисе только после её записи в журнале.</p></section></div>
 <div><section class="card"><h2>Что ещё проверить?</h2><p>Травмы и доступность игроков находятся на отдельной странице.</p>
 <button class="button" data-tabto="news">Открыть статусы</button><div class="separator"></div>
 <p>Состав и замены можно сохранить через «Профиль».</p><button class="button" data-tabto="account">Резервная копия</button></section>
 <details class="card deep-details"><summary>Изменился клуб игрока?</summary><p class="small">Если Sports.ru уже перевёл игрока в новый клуб, а данные NBA отстают, скорректируйте клуб вручную. Это пересчитает календарь и лимит двух игроков.</p>${teamsHtml}</details></div></div>
 <details class="card deep-details"><summary>Дополнительно · источники, импорт и методика</summary>${sourceHealth()}
 <div class="toolbar"><label class="button" style="flex:0 1 auto;position:relative;cursor:pointer">Импорт NBA JSON<input id="feedfile" type="file" accept="application/json,.json" style="display:none"></label>
 <label class="button" style="flex:0 1 auto;position:relative;cursor:pointer">Импорт копии профиля<input id="backupfile" type="file" accept="application/json,.json" style="display:none"></label></div>
 <p class="small">Статус источников:</p>${providers}<div class="donut"><span>UTC-календарь</span><b>${esc(CALENDAR_STATUS)} · ${CALENDAR?.games?.length||0} игр</b></div>
 ${LIVE.warnings?.length?`<details><summary>Предупреждения набора данных (${LIVE.warnings.length})</summary><ul class="warninglist">${LIVE.warnings.slice(0,12).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>`:''}
 <h3>Что означает прогноз</h3><p>История 2023/24–2025/26 и новые игры текущего сезона. FP при выходе — только при условии участия; FP за период дополнительно учитывает расписание и модельный риск пропуска.</p>
 <p>Сценарные диапазоны не являются калиброванными доверительными интервалами. <a href="https://github.com/mih98967-afk/nba-season-lab-data" target="_blank" rel="noopener noreferrer">Исходники и журналы обновлений GitHub</a>.</p></details>`;
}
function renderModal(){let target=document.getElementById('modal-root');if(!MODAL){target?.remove();return;}if(!target){target=document.createElement('div');target.id='modal-root';document.body.appendChild(target);}target.className='modal';target.innerHTML=`<div class="modalpanel" role="dialog" aria-modal="true">${MODAL==='compare'?compareModal():playerModal(MODAL)}</div>`;target.onclick=e=>{if(e.target===target){MODAL=null;renderModal();}};}
function openPlayerDecision(id,task){
 if(!P[id])return showMsg('Игрок не найден в текущем каталоге');
 if(task==='replace'&&!S.roster.includes(id))return showMsg('Этот игрок не в вашем составе. Откройте его карточку для сравнения.');
 if(task==='replace'){
  UI.plannerTask='specific';UI.plannerOut=id;UI.plannerIn=null;
  UI.plannerSell=null;UI.plannerBuy=null;UI.plannerWhen=null;
  UI.quickPreview=null;UI.multiResult=null;UI.chainResult=null;
  tab='planner';
 }else if(task==='calendar'){
  UI.calendarQuick='team';UI.calendarTeamDays=14;
  UI.calendarFocusPlayer=id;tab='calendar';
 }else if(task==='players'){
  UI.marketView='candidates';UI.position=P[id].pos;
  UI.marketFocusPlayer=id;UI.marketAdvanced=false;UI.marketLimit=50;
  tab='players';
 }else return;
 MODAL=null;view();window.scrollTo({top:0,behavior:'instant'});
}
function setTab(t){const more=document.getElementById('more-menu');if(more)more.open=false;tab=t;MODAL=null;if(t==='players'){UI.marketFocusPlayer=null;UI.position='all';}if(t==='calendar')UI.calendarFocusPlayer=null;view();window.scrollTo({top:0,behavior:'instant'});}
function showMsg(msg){notice=msg;view();}
function formTransfer(){return {out:document.getElementById('out')?.value,in_:document.getElementById('in')?.value,epoch:moscowEpoch(document.getElementById('when')?.value),sell:num(document.getElementById('sell')?.value),buy:num(document.getElementById('buy')?.value)};}
function plausibleTransfer(t){return t.out&&t.in_&&Number.isFinite(t.epoch)&&Number.isFinite(t.sell)&&Number.isFinite(t.buy);}
function addDraft(){if(S.roster.length!==10)return showMsg('Сначала сохраните вашу десятку.');const t=formTransfer();
 if(!plausibleTransfer(t))return showMsg('Для черновика укажите OUT, IN, дату и две цены.');
 const result=planResult([...S.draft,t]);if(!result.valid)return showMsg('Этот переход недопустим: '+result.errors.join(' · '));
 S.draft.push(t);UI.quickPreview=null;UI.plannerSell=null;UI.plannerBuy=null;save();view();}
function previewTransfer(){const t=formTransfer();if(!plausibleTransfer(t))return showMsg('Заполните игроков, дату и обе цены.');
 UI.plannerOut=t.out;UI.plannerIn=t.in_;UI.plannerWhen=t.epoch;UI.plannerSell=t.sell;UI.plannerBuy=t.buy;
 const test=planResult([...S.draft,t]);
 UI.quickPreview={t,valid:test.valid,errors:test.errors,warnings:test.warnings,
  gain7:test.valid&&calendarCoverage(now(),7).ok?plannedMean(S.roster,[...S.draft,t],7)-plannedMean(S.roster,S.draft,7):null,
  gain14:test.valid&&calendarCoverage(now(),14).ok?plannedMean(S.roster,[...S.draft,t],14)-plannedMean(S.roster,S.draft,14):null};
 view();}
function confirmDraft(){const v=planResult(S.draft);if(!v.valid)return showMsg('План имеет нарушения, его нельзя отметить выполненным.');
 if(S.draft.some(t=>t.epoch>now()+2*60000))return showMsg('Будущие замены нельзя отметить выполненными. Оставьте их в черновике и подтвердите после реальной операции на Sports.ru.');
 if(v.warnings.length&&!confirm('У плана есть непроверенные условия доступности карточек. Вы действительно выполнили все указанные операции на Sports.ru?'))return;
 if(!confirm('Только если вы УЖЕ провели эти замены на Sports.ru: перенести их в историю и изменить ваш реальный состав в приложении?'))return;
 S.executed.push(...S.draft);S.executed.sort((a,b)=>a.epoch-b.epoch);S.roster=[...v.roster];S.cash=v.cash;S.draft=[];S.lastUpdate=new Date().toISOString();save();showMsg('Записи о подтверждённых вами трансферах сохранены. Sports.ru не изменялся.');}
function download(name,obj){const blob=new Blob([JSON.stringify(obj,null,2)],{type:'application/json;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function reconstructInitialRoster(backup){
 if(Array.isArray(backup.initialRoster)&&hardCheck(backup.initialRoster).valid)return [...backup.initialRoster];
 if(!Array.isArray(backup.roster)||!hardCheck(backup.roster).valid)return [];
 const reversed=[...backup.roster];
 for(const t of [...(backup.executed||[])].sort((a,b)=>(b.epoch||0)-(a.epoch||0))){
  const idx=reversed.indexOf(t.in_);
  if(idx<0||reversed.includes(t.out))return [];
  reversed[idx]=t.out;
 }
 return hardCheck(reversed).valid?reversed:[];
}
async function upload(file,kind){try{const text=await file.text(),o=JSON.parse(text);if(kind==='feed'){
 applyPublicFeed(o,'ручной импорт NBA JSON');showMsg('Проверенный файл NBA загружен.');}
 else{if(![4,5].includes(o.v)||!Array.isArray(o.roster)||!hardCheck(o.roster,null,0).valid)throw Error('Копия не содержит допустимую десятку');if(!confirm('Заменить локальную историю, кассу и состав сохранённой копией?'))return;const initial=reconstructInitialRoster(o);S={...defaults(),...o,v:5,initialRoster:initial};save();showMsg(initial.length===10?'Резервная копия восстановлена.':'Состав и касса восстановлены; начальная десятка не подтверждена, поэтому исторические FP могут быть неполными.');}}
 catch(err){showMsg('Импорт не выполнен: '+err.message);}}
// Free public feed: GitHub Actions commits it to main every four hours.
// It contains common NBA stats only. Personal squads stay in Firebase Firestore.
const GITHUB_FEED='https://raw.githubusercontent.com/mih98967-afk/nba-season-lab-data/main/data/live.json';
const FEED_CACHE_KEY='nba-season-lab-validated-public-feed-v1';
function checkPublicFeed(v){
 if(!v||v.schema_version!==4||!Array.isArray(v.rows)||!Array.isArray(v.games)||
    !Array.isArray(v.schedule))throw Error('Несовместимый формат общего NBA-файла');
 if(!['live_sync','schedule_sync_only','sync_failed_using_cache'].includes(v.mode))
    throw Error('Источник не завершил обработку');
 const timestamp=Date.parse(v.updated_at_utc||'');
 if(!Number.isFinite(timestamp)||timestamp>Date.now()+3600000)throw Error('Некорректная дата обновления');
 if(!v.rows.length)throw Error('В источнике пока нет рассчитанных FP');
 const names=new Set(BASE.players.map(p=>p.id));
 const games=new Map(v.games.map(g=>[String(g.id),g]));
 const seen=new Set();
 for(const r of v.rows){
  if(!names.has(r.id)||!games.has(String(r.game_id))||games.get(String(r.game_id))?.status!=='final'||
     typeof r.fp!=='number'||!Number.isFinite(r.fp)||r.fp<-200||r.fp>250||
     !r.utc||!r.source||!r.name)
   throw Error('Непроверенная строка NBA: '+String(r?.name||r?.id||''));
  const key=String(r.game_id)+'|'+String(r.id);
  if(seen.has(key))throw Error('Дублирование игроко-матча');
  seen.add(key);
 }
 return v;
}
function applyPublicFeed(feed,origin){
 const v=checkPublicFeed(feed);
 const oldAt=Date.parse(LIVE.updated_at_utc||'')||0;
 const newAt=Date.parse(v.updated_at_utc)||0;
 if(newAt<oldAt && LIVE.rows?.length>=v.rows.length)return false;
 // Never replace a verified set of game rows with an empty or smaller partial response.
 if((LIVE.rows?.length||0)>v.rows.length&&newAt<=oldAt)return false;
 LIVE=v;publicFeedValidated=true;UI.chainResult=null;UI.multiResult=null;UI.multiCalculatedAt=null;UI.budgetResult=null;liveSource=origin;onlineError='';
 try{const str=JSON.stringify(v);if(str.length<3_300_000)localStorage.setItem(FEED_CACHE_KEY,str);}catch{}
 view();return true;
}
function restorePublicCache(){
 try{const raw=localStorage.getItem(FEED_CACHE_KEY);if(!raw)return false;
  return applyPublicFeed(JSON.parse(raw),'сохранённый проверенный срез');
 }catch{return false;}
}
async function loadFeed(){
 if(location.protocol==='file:')return;
 const src=GITHUB_FEED+'?v='+Math.floor(Date.now()/300000);
 try{
  const response=await fetch(src,{cache:'no-store',mode:'cors'});
  if(!response.ok)throw Error('GitHub HTTP '+response.status);
  const data=await response.json();
  if(!applyPublicFeed(data,'GitHub Actions · NBA / ESPN')){
   onlineError='Новый срез старее сохранённого; данные не заменены';view();
  }
 }catch(e){
  onlineError='Не удалось получить новые данные из GitHub: '+String(e.message||e).slice(0,125);
  if(!restorePublicCache())liveSource='начальный срез сайта';
  onlineError='Не удалось получить новые данные из GitHub: '+String(e.message||e).slice(0,125);
  view();
 }
}
async function remoteRefresh(){
 await Promise.all([loadFeed(),loadCalendar(),loadOfficialStatus()]);
 if(onlineError)showMsg(onlineError+'. Попробуйте позже; состав и трансферы сохранены.');
 else showMsg('Проверка GitHub завершена. '+currentStatus()+'.');
}
// Event delegation for navigation, comparisons and roster ledger.
document.addEventListener('click',e=>{const el=e.target.closest('[data-action],[data-tabto],[data-player],[data-compare],[data-uncompare],[data-remove-draft],[data-price-reset],[data-shortlist],[data-chain-apply],[data-multi-apply],[data-budget-apply],[data-journal-freeze],[data-planner-task],[data-planner-tool],[data-team-view],[data-market-view],[data-calendar-quick],[data-team-days],[data-status-scope],[data-player-intent],[data-clear-intent]');if(!el)return;
 if(el.dataset.playerIntent){openPlayerDecision(el.dataset.intentPlayer,el.dataset.playerIntent);return;}
 if(el.dataset.clearIntent){if(el.dataset.clearIntent==='players'){UI.marketFocusPlayer=null;UI.position='all';}if(el.dataset.clearIntent==='calendar')UI.calendarFocusPlayer=null;view();return;}
 if(el.dataset.tabto){setTab(el.dataset.tabto);return;}
 if(el.dataset.teamView){UI.teamView=el.dataset.teamView==='list'?'list':'court';view();return;}
 if(el.dataset.marketView){UI.marketView=el.dataset.marketView;UI.marketLimit=50;view();return;}
 if(el.dataset.calendarQuick){UI.calendarQuick=el.dataset.calendarQuick==='full'?'full':'team';view();return;}
 if(el.dataset.teamDays){UI.calendarTeamDays=Number(el.dataset.teamDays);view();return;}
 if(el.dataset.statusScope){UI.statusScope=el.dataset.statusScope==='all'?'all':'mine';view();return;}
 if(el.dataset.plannerTask){UI.plannerTask=el.dataset.plannerTask;UI.plannerTaskListOpen=false;UI.plannerSequenceTool='none';UI.quickPreview=null;UI.retroOpen=UI.plannerTask==='record';view();document.getElementById('planner-task')?.scrollIntoView({block:'start',behavior:'instant'});return;}
 if(el.dataset.plannerTool){UI.plannerSequenceTool=el.dataset.plannerTool;view();return;}

 if(el.dataset.player){MODAL=el.dataset.player;renderModal();return;}
 if(el.dataset.compare){const id=el.dataset.compare;if(UI.compare.includes(id))UI.compare=UI.compare.filter(x=>x!==id);else if(UI.compare.length<4)UI.compare.push(id);else return showMsg('Можно сравнивать максимум четырёх игроков.');view();return;}
 if(el.dataset.uncompare){UI.compare=UI.compare.filter(id=>id!==el.dataset.uncompare);view();return;}
 if(el.dataset.chainApply!==undefined){applyChain(Number(el.dataset.chainApply));return;}
 if(el.dataset.journalFreeze!==undefined){freezeMultiDecision(Number(el.dataset.journalFreeze));return;}
 if(el.dataset.multiApply!==undefined){applyMulti(Number(el.dataset.multiApply));return;}
 if(el.dataset.budgetApply!==undefined){applyBudget(Number(el.dataset.budgetApply));return;}
 if(el.dataset.shortlist){UI.plannerTask='specific';UI.plannerIn=el.dataset.shortlist;UI.plannerBuy=null;UI.quickPreview=null;view();document.getElementById('planner-manual')?.scrollIntoView({block:'start',behavior:'smooth'});return;}
 if(el.dataset.removeDraft!==undefined){S.draft.splice(Number(el.dataset.removeDraft),1);save();view();return;}
 if(el.dataset.priceReset){delete S.prices[el.dataset.priceReset];save();view();return;}
 switch(el.dataset.action){case 'planner-task-toggle':UI.plannerTaskListOpen=!UI.plannerTaskListOpen;view();break;case 'today-review':{UI.plannerTask='advice';UI.multiDays=21;UI.multiFocus='all';UI.plannerWhen=null;tab='planner';view();calculateMulti();break;}case 'sports-check-toggle':UI.sportsOpen=!UI.sportsOpen;view();break;case 'sports-check-run':sportsCheckRun();break;case 'dismiss':notice='';view();break;case 'create-roster':createRoster();break;case 'reset-roster':resetRoster();break;case 'close-modal':MODAL=null;renderModal();break;case 'compare':if(UI.compare.length>=2){MODAL='compare';renderModal();}else showMsg('Выберите хотя бы двух игроков.');break;case 'cal-prev-tours':UI.calendarTour=Math.max(1,(UI.calendarTour||window.NBACalendarTours.tourNumber(now()))-UI.calendarTourCount);view();break;case 'cal-next-tours':UI.calendarTour=Math.min(Math.max(1,window.NBACalendarTours.seasonTourCount()-UI.calendarTourCount+1),(UI.calendarTour||window.NBACalendarTours.tourNumber(now()))+UI.calendarTourCount);view();break;case 'cal-current-tours':UI.calendarTour=window.NBACalendarTours.tourNumber(now());view();break;case 'cal-prev-window':{const T=window.NBACalendarTours,n=Math.min(UI.calendarDays,T.daysBetween(T.FIRST_DATE,UI.calendarStart));UI.calendarStart=T.addDays(UI.calendarStart,-n);UI.calendarEnd=T.addDays(UI.calendarStart,UI.calendarDays-1);view();break;}case 'cal-next-window':{const T=window.NBACalendarTours,n=Math.min(UI.calendarDays,T.daysBetween(UI.calendarEnd,T.LAST_DATE));UI.calendarStart=T.addDays(UI.calendarStart,n);UI.calendarEnd=T.addDays(UI.calendarStart,UI.calendarDays-1);view();break;}case 'market-advanced':UI.marketAdvanced=!UI.marketAdvanced;view();break;case 'market-more':UI.marketLimit=Math.min(BASE.players.length,UI.marketLimit+50);view();break;case 'planner-advanced-toggle':UI.plannerAdvanced=!UI.plannerAdvanced;view();break;case 'planner-detail-toggle':UI.plannerDetail=!UI.plannerDetail;view();break;case 'planner-manual-toggle':UI.plannerManualOpen=!UI.plannerManualOpen;view();break;case 'multi-options-toggle':UI.multiOptions=!UI.multiOptions;view();break;case 'calculate-chains':calculateChains();break;case 'calculate-multi':calculateMulti();break;case 'calculate-budget':calculateBudget();break;case 'retro-toggle':UI.retroOpen=!UI.retroOpen;UI.retroPreview=null;view();break;case 'retro-add':UI.retroRows.push(retroBlank());UI.retroPreview=null;view();break;case 'retro-remove':if(UI.retroRows.length>1){UI.retroRows.splice(Number(el.dataset.idx),1);UI.retroPreview=null;view();}break;case 'retro-preview':retroPreviewHistory();break;case 'retro-save':retroCommitHistory();break;case 'add-draft':addDraft();break;case 'preview-transfer':previewTransfer();break;case 'clear-draft':S.draft=[];save();view();break;case 'confirm-draft':confirmDraft();break;case 'refresh':remoteRefresh();break;case 'history-more':UI.histLimit=Math.min(10000,UI.histLimit+100);view();break;case 'retry-history':{const pid=UI.playerId||S.roster[0];if(HISTORY_INDEX){const file=HISTORY_INDEX.player_shards?.[pid];if(file)HISTORY_SHARD_ERRORS.delete(file);scheduleHistory(pid);}else loadAux();break;}case 'journal-export':decisionJournalExport();break;case 'journal-clear':decisionJournalClear();break;case 'price-proof-save':privatePriceCapture();break;case 'price-proof-export':privatePriceExport();break;case 'price-proof-delete':privatePriceDelete();break;case 'export-state':download('nba-season-lab-backup.json',S);break;case 'set-cash':{const val=num(document.getElementById('cash')?.value);if(!Number.isFinite(val)||val<0)return showMsg('Некорректная касса');S.cash=val;save();view();break;}}});
document.getElementById('navigation').addEventListener('click',e=>{const b=e.target.closest('button[data-tab]');if(b)setTab(b.dataset.tab);});
document.addEventListener('change',e=>{const el=e.target;if(!el)return;
 if(el.dataset.historyField!==undefined){const i=Number(el.dataset.historyIndex),field=el.dataset.historyField;
  if(Number.isInteger(i)&&UI.retroRows[i]&&['when','out','in_','sell','buy'].includes(field)){
   UI.retroRows[i][field]=el.value;
   if(field==='out')UI.retroRows[i].in_='';
   UI.retroPreview=null;view();
  }return;
 }
 if(el.id==='price-proof-file'&&el.files?.[0])return privatePriceImport(el.files[0]);if(el.id==='feedfile'&&el.files?.[0])return upload(el.files[0],'feed');if(el.id==='backupfile'&&el.files?.[0])return upload(el.files[0],'backup');
 if(el.id==='medical'){S.medical[el.dataset.id]=el.value;save();view();return;}
 if(el.classList.contains('teamedit')){if(!S.teamOverrides)S.teamOverrides={};if(el.value==='auto')delete S.teamOverrides[el.dataset.teamId];else if(CLUBS[el.value])S.teamOverrides[el.dataset.teamId]=el.value;save();view();return;}
 if(el.classList.contains('priceedit')){const v=num(el.value);if(Number.isFinite(v)&&v>=0)S.prices[el.dataset.priceId]=v;save();view();return;}
 if(el.id==='hist-player'){UI.playerId=el.value;UI.histSeason='all';UI.histOpponent='all';UI.histLimit=25;view();return;}if(el.id==='hist-season'){UI.histSeason=el.value;UI.histLimit=25;view();return;}if(el.id==='hist-opponent'){UI.histOpponent=el.value;UI.histLimit=25;view();return;}if(el.id==='hist-limit'){UI.histLimit=Number(el.value);view();return;}if(el.id==='pos'){UI.position=el.value;UI.marketLimit=50;view();return;}if(el.id==='club'){UI.club=el.value;UI.marketLimit=50;view();return;}if(el.id==='sort'){UI.sort=el.value;UI.marketLimit=50;view();return;}if(el.id==='window'){UI.window=Number(el.value);UI.marketLimit=50;view();return;}
 if(el.id==='cal-view'){UI.calendarMode=el.value==='window'?'window':'tours';view();return;}if(el.id==='cal-tour-first'){UI.calendarTour=Number(el.value);view();return;}if(el.id==='cal-tour-count'){UI.calendarTourCount=Number(el.value);view();return;}if(el.id==='cal-tour-sort'){UI.calendarTourSort=el.value;view();return;}
 if(el.id==='cal-start'){const T=window.NBACalendarTours;const key=el.value;if(key<T.FIRST_DATE||key>T.LAST_DATE)return showMsg('Дата вне регулярного сезона');UI.calendarStart=key;UI.calendarDays=clamp(UI.calendarDays,1,T.daysBetween(key,T.LAST_DATE)+1);UI.calendarEnd=T.addDays(key,UI.calendarDays-1);view();return;}
 if(el.id==='cal-end'){const T=window.NBACalendarTours;const days=T.daysBetween(UI.calendarStart,el.value)+1;if(days<1||days>T.MAX_WINDOW_DAYS||el.value>T.LAST_DATE)return showMsg('Неверный диапазон дат');UI.calendarEnd=el.value;UI.calendarDays=days;view();return;}
 if(el.id==='cal-days'){const T=window.NBACalendarTours;const d=Number(el.value);if(!Number.isInteger(d)||d<1||d>T.MAX_WINDOW_DAYS)return showMsg('Укажи целое число дней от 1 до '+T.MAX_WINDOW_DAYS);UI.calendarDays=Math.min(d,T.daysBetween(UI.calendarStart,T.LAST_DATE)+1);UI.calendarEnd=T.addDays(UI.calendarStart,UI.calendarDays-1);view();return;}if(el.id==='cal-own'){UI.calendarOwn=el.checked;view();return;}
 if(el.id==='budget-when'){UI.plannerWhen=moscowEpoch(el.value);UI.budgetResult=null;UI.quickPreview=null;view();return;}
 if(el.id==='budget-position'){UI.budgetPosition=el.value;UI.budgetTarget=null;UI.budgetOut='auto';UI.budgetBuy=null;UI.budgetResult=null;view();return;}
 if(el.id==='budget-target'){UI.budgetTarget=el.value||null;UI.budgetOut='auto';UI.budgetBuy=null;UI.budgetResult=null;view();return;}
 if(el.id==='budget-out'){UI.budgetOut=el.value;UI.budgetResult=null;view();return;}
 if(el.id==='budget-buy'){UI.budgetBuy=num(el.value);UI.budgetResult=null;view();return;}
 if(el.id==='budget-days'){UI.budgetDays=Number(el.value);UI.budgetResult=null;view();return;}
 if(el.id==='budget-moves'){UI.budgetMoves=Number(el.value);UI.budgetResult=null;view();return;}
 if(el.id==='budget-penalty'){UI.budgetPenalty=Number(el.value);UI.budgetResult=null;view();return;}
 if(el.id==='multi-when'){UI.plannerWhen=moscowEpoch(el.value);UI.multiResult=null;view();return;}
 if(el.id==='multi-days'){UI.multiDays=Number(el.value);UI.multiResult=null;view();return;}
 if(el.id==='multi-penalty'){UI.multiPenalty=Number(el.value);UI.multiResult=null;view();return;}
 if(el.id==='multi-moves'){UI.multiMoves=Number(el.value);UI.multiResult=null;view();return;}
 if(el.id==='multi-focus'){UI.multiFocus=el.value;UI.multiResult=null;view();return;}
 if(el.id==='chain-days'){UI.chainDays=Number(el.value);UI.chainResult=null;view();return;}
 if(el.id==='chain-penalty'){UI.chainPenalty=Number(el.value);UI.chainResult=null;view();return;}
 if(el.id==='out'){UI.multiResult=null;UI.chainResult=null;UI.plannerOut=el.value;UI.plannerIn=null;UI.plannerSell=null;UI.plannerBuy=null;UI.quickPreview=null;view();return;}
 if(el.id==='in'){UI.plannerIn=el.value;UI.plannerBuy=null;UI.quickPreview=null;root.querySelector('#buy').value=prices(el.value);return;}
 if(el.id==='when'){UI.multiResult=null;UI.chainResult=null;UI.plannerWhen=moscowEpoch(el.value);UI.quickPreview=null;view();return;}
 if(el.id==='sell'){UI.multiResult=null;UI.chainResult=null;UI.plannerSell=num(el.value);UI.quickPreview=null;return;}
 if(el.id==='buy'){UI.multiResult=null;UI.chainResult=null;UI.plannerBuy=num(el.value);UI.quickPreview=null;return;}
 if(el.id==='risk-mode'){S.riskMode=el.value;save();view();return;}
 if(el.id==='model-mode'){S.modelMode=el.value;save();view();if(S.modelMode==='validated')prefetchPlannerHistory();return;}
 });
let searchTimer;document.addEventListener('input',e=>{
 const fieldKey={'sports-fp':'fp','sports-cash':'cash','sports-remaining':'remaining'}[e.target.id];
 if(fieldKey){UI.sportsInputs[fieldKey]=e.target.value;UI.sportsResult=null;
  document.querySelector('.sports-check-result')?.remove();return;}
 if(e.target.id==='search'){UI.search=e.target.value;UI.marketLimit=50;clearTimeout(searchTimer);searchTimer=setTimeout(()=>{const field=document.activeElement===e.target;const cursor=e.target.selectionStart;view();const n=document.getElementById('search');if(field&&n){n.focus();n.setSelectionRange(cursor,cursor);}},180);}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&MODAL){MODAL=null;renderModal();}});
window.PythosNBA={base:BASE,getState:()=>JSON.parse(JSON.stringify(S)),getFeed:()=>LIVE,getFeedSource:()=>liveSource,getFeedError:()=>onlineError,validateFeed:checkPublicFeed,refreshFeed:loadFeed,score:(s,home,win)=>{const minutes=Number(s.min)||0;if(!minutes)return 0;return s.pts+s.reb+s.ast+s.stl+s.blk+s.fgm+s.ftm-s.fga-s.fta-s.pf-2*s.tov+(minutes>=10?2:1)+(win?(home?2:3):(home?-3:-2));},check:hardCheck,planCheck:planResult,setState:x=>{S=x;save();view();},updateFeed:x=>{LIVE=x;publicFeedValidated=false;UI.multiResult=null;UI.multiCalculatedAt=null;view();},preview:plannedMean,planWorlds,modelSignal:id=>validatedModelSignal(P[id]),estimate:(id,g)=>learnedMean(P[id],g),modelReport:()=>MODEL_V2};


function nbaSeasons(pid){return NBA_HISTORY?.players?.[pid]||[];}
function historyAvailable(pid){return !!HISTORY_INDEX?.player_shards?.[pid];}
function scheduleHistory(pid){if(!pid||!historyAvailable(pid)||nbaSeasons(pid).length)return;
 const file=HISTORY_INDEX.player_shards[pid];
 if(HISTORY_LOADED_SHARDS.has(file)||HISTORY_FETCHING_SHARDS.has(file))return;
 const priorError=HISTORY_SHARD_ERRORS.get(file);if(priorError&&Date.now()-priorError.at<600000)return;
 HISTORY_FETCHING_SHARDS.add(file);
 fetch(GITHUB_PUBLIC_DATA+'history/'+file+'?v='+encodeURIComponent(HISTORY_INDEX.version),{mode:'cors',cache:'force-cache'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(d=>{if(d.schema_version!==1||d.status!=='complete'||d.version!==HISTORY_INDEX.version||!d.players?.[pid])throw Error('Некорректный файл истории');
 NBA_HISTORY.players={...NBA_HISTORY.players,...d.players};HISTORY_LOADED_SHARDS.add(file);HISTORY_SHARD_ERRORS.delete(file);HISTORY_STATUS='Готово';view();}).catch(e=>{HISTORY_STATUS='Не удалось загрузить историю: '+String(e.message||e).slice(0,90);HISTORY_SHARD_ERRORS.set(file,{message:String(e.message||e),at:Date.now()});view();}).finally(()=>HISTORY_FETCHING_SHARDS.delete(file));}
function rosterNews(pid){return (TG_NEWS?.events||[]).filter(n=>(n.player_ids||[]).includes(pid)&&(!n.published_at||Date.now()-Date.parse(n.published_at)<12*86400000));}
function officialForPlayers(ids){
 const lib=window.NBAOfficialStatus;
 return lib?.select(OFFICIAL_FEED,ids,P,now(),72)||[];
}
function officialForRoster(){return officialForPlayers(S.roster);}
function officialCard(e){
 const dangerous=window.NBAOfficialStatus.isHighRisk(e.status);
 return `<div class="lined"><div class="horizontal"><b>${esc(e.playerName)}</b><span class="pill ${dangerous?'warn':''}">${esc(window.NBAOfficialStatus.translate(e.status))}</span></div>
  <div class="small">${esc(e.away)} @ ${esc(e.home)} · матч ${esc(dateText(e.tipoffEpoch))} МСК · отчёт ${esc(dateText(e.reportEpoch))} · получено ${esc(dateText(e.firstSeenEpoch))}${e.stale?' · снимок старше 12 ч':''}</div>
  <a href="${esc(e.sourceUrl)}" rel="noopener noreferrer" target="_blank">Официальный PDF NBA</a></div>`;
}
function rosterWarnings(){
 const official=officialForRoster(),alerts=S.roster.flatMap(id=>rosterNews(id).slice(0,1).map(e=>({id,...e})));
 if(!official.length&&!alerts.length)return '';
 const officialHtml=official.length?`<div class="titledetail"><h2>Официальные статусы NBA · ${official.length}</h2><span class="pill">По конкретным ближайшим матчам</span></div>${official.slice(0,8).map(officialCard).join('')}`:'';
 const telegramHtml=alerts.length?`<div class="titledetail" style="margin-top:${official.length?'15':'0'}px"><h2>Telegram · ${alerts.length} сигналов</h2><span class="pill warn">Не подтверждено</span></div>${alerts.slice(0,5).map(x=>`<div class="lined"><div class="horizontal"><b>${esc(P[x.id]?.name)}</b><span class="small">${esc(x.published_at?dateText(x.published_at):'Дата не определена')}</span></div><p class="small">${esc(x.text)}</p><a target="_blank" rel="noopener noreferrer" href="${esc(x.url)}">Исходный пост</a></div>`).join('')}`:'';
 return `<div class="card official-evidence" style="margin-bottom:16px"><div class="small">ИСТОЧНИКИ ДОСТУПНОСТИ · ТОЛЬКО ИНФОРМАЦИЯ, НЕ ПРОГНОЗ</div>${officialHtml}${telegramHtml}<p class="small">Отсутствие статуса не означает здоровье или участие. Даже статус Available не гарантирует выход. FP и вероятности автоматически не меняются.</p></div>`;
}
function onboarding(){const selectFor=(pos,n)=>`<label>${pos} · ${n+1}<select data-roster-slot="${pos}"><option value="">Выберите игрока</option>${BASE.players.filter(p=>p.pos===pos).sort((a,b)=>b.start_price-a.start_price).map(p=>`<option value="${p.id}">${esc(p.name)} · ${esc(p.team)} · ${round(p.start_price)}</option>`).join('')}</select></label>`;
 return header('Начало','Моя команда','Составы пользователей независимы. Сначала укажите десять игроков Sports.ru.')+
 `<div class="grid columns"><div class="card"><h2>Собрать десятку</h2><p class="small">По два каждой позиции, максимум два из клуба, бюджет 20 000. Зафиксируйте дату, с которой считать ваши исторические очки.</p><div class="formgrid">${POS.map(pos=>selectFor(pos,0)+selectFor(pos,1)).join('')}<label>Дата исходного состава, МСК<input id="roster-start" type="datetime-local" value="2026-10-20T19:00"></label></div><div class="toolbar" style="margin-top:18px"><button class="primary" data-action="create-roster">Сохранить мой состав</button></div><div class="small">У каждого пользователя свой состав. Примеры чужих реальных составов не публикуются.</div></div><div class="card"><h2>Как это работает</h2><p>После сохранения появятся ваш текущий состав, прогнозы, календарь, планировщик и журнал выполненных замен.</p><p>Если включить бесплатный облачный аккаунт Firebase, состав будет доступен с разных устройств. Без подключения всё сохраняется только в этом браузере.</p><button class="button" data-tabto="account">Моя учётная запись</button></div></div>`;
}
function createRoster(){let ids=[...document.querySelectorAll('[data-roster-slot]')].map(x=>x.value).filter(Boolean);const valid=hardCheck(ids);if(!valid.valid||valid.sum>BASE.budget)return showMsg(valid.errors.join('; ')||(valid.sum>BASE.budget?'Превышен бюджет: '+round(valid.sum):'Недопустимый состав'));const when=moscowEpoch(document.getElementById('roster-start').value);if(!Number.isFinite(when))return showMsg('Неверная дата исходного состава');if(!confirm('Сохранить эту десятку как начальный состав сезона? Историю операций можно будет изменять отдельно.'))return;
 S={...defaults(),roster:ids,initialRoster:[...ids],initialEpoch:when,cash:BASE.budget-valid.sum};save();showMsg('Состав сохранён, бюджет и лимиты проверены.');}
function histMin(m){if(!Number.isFinite(Number(m)))return '—';let seconds=Math.round(Number(m)*60);return String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');}
function histQuantile(values,p){const a=values.filter(Number.isFinite).sort((x,y)=>x-y);if(!a.length)return NaN;const i=(a.length-1)*p;return a[Math.floor(i)]+(a[Math.ceil(i)]-a[Math.floor(i)])*(i-Math.floor(i));}
function histTint(value,base,invert=false){if(!Number.isFinite(value)||!Number.isFinite(base)||base===0)return '';const d=(value-base)/Math.max(Math.abs(base),5)*(invert?-1:1);return d>.2?'hist-positive':d<-.2?'hist-negative':'';}
function histLabels(){return `<details class="hist-help"><summary>Что означают показатели?</summary><div class="hist-dictionary"><span><b>PTS</b> — очки NBA</span><span><b>REB</b> — подборы</span><span><b>AST</b> — передачи</span><span><b>STL</b> — перехваты</span><span><b>BLK</b> — блок-шоты</span><span><b>FGM/FGA</b> — попадания / попытки с игры</span><span><b>FTM/FTA</b> — попадания / попытки штрафных</span><span><b>TOV</b> — потери</span><span><b>FP</b> — очки Sports.ru по пересчитанному протоколу</span><span><b>P10–P90</b> — между 10-м и 90-м процентилями сыгранных матчей (не прогноз)</span><span><b>SD</b> — стандартное отклонение результатов</span></div></details>`;}
function historyPage(){
 const pid=UI.playerId||S.roster[0]||BASE.players[0].id;
 if(historyAvailable(pid)&&!nbaSeasons(pid).length)scheduleHistory(pid);
 const opts=BASE.players.filter(p=>historyAvailable(p.id)||nbaSeasons(p.id).length||(actualByPlayer()[p.id]||[]).length).sort((a,b)=>a.name.localeCompare(b.name,'ru'));
 const seasons=nbaSeasons(pid),selected=P[pid];
 const liveRows=(actualByPlayer()[pid]||[]).filter(x=>x.played).map(x=>{
  const g=(LIVE.games||[]).find(g=>g.id===x.game_id);
  return {d:String(x.utc||'').slice(0,10),g:x.game_id,team:x.team,opp:g?(g.home===x.team?g.away:g.home):null,home:g?g.home===x.team:null,season:'2026/27',min:x.minutes,
    pts:x.box?.pts,reb:x.box?.reb,ast:x.box?.ast,stl:x.box?.stl,blk:x.box?.blk,
    fgm:x.box?.fgm,fga:x.box?.fga,ftm:x.box?.ftm,fta:x.box?.fta,
    tov:x.box?.tov,pf:x.box?.pf,fp:x.fp,source:x.source||'NBA / ESPN'};
 });
 const historical=seasons.flatMap(s=>(s.game_log||s.last35||[]).map(x=>({...x,season:s.season,source:'История NBA'})));
 const raw=[...historical,...liveRows].sort((a,b)=>String(b.d).localeCompare(String(a.d)));
 const availableSeasons=[...new Set(raw.map(x=>x.season))].sort().reverse();
 const opponents=[...new Set(raw.map(x=>x.opp).filter(Boolean))].sort();
 let filtered=raw.filter(x=>(UI.histSeason==='all'||x.season===UI.histSeason)&&(UI.histOpponent==='all'||x.opp===UI.histOpponent));
 const values=filtered.map(x=>Number(x.fp)).filter(Number.isFinite);
 const mean=values.length?values.reduce((a,b)=>a+b,0)/values.length:NaN;
 const med=histQuantile(values,.5),p10=histQuantile(values,.1),p90=histQuantile(values,.9);
 const variance=values.length>1?values.reduce((a,v)=>a+(v-mean)**2,0)/(values.length-1):NaN;
 const sd=Math.sqrt(variance);
 const shown=filtered.slice(0,UI.histLimit);
 const options=(items,current)=>items.map(v=>`<option value="${esc(v)}" ${String(current)===String(v)?'selected':''}>${esc(v)}</option>`).join('');
 const table=seasons.length?`<div class="tablewrap"><table><thead><tr><th>Сезон</th><th class="num">Игры</th><th class="num">Мин</th><th class="num">PTS</th><th class="num">REB</th><th class="num">AST</th><th class="num">STL</th><th class="num">BLK</th><th class="num">FGM/FGA</th><th class="num">FTM/FTA</th><th class="num">TOV</th><th class="num">FP</th><th class="num">P10–P90</th></tr></thead><tbody>${seasons.map(s=>`<tr><td>${esc(s.season)}</td><td class="num">${s.games}</td>${['min','pts','reb','ast','stl','blk'].map(k=>`<td class="num">${k==='min'?histMin(s.averages[k]):round(s.averages[k],1)}</td>`).join('')}<td class="num">${round(s.averages.fgm,1)}/${round(s.averages.fga,1)}</td><td class="num">${round(s.averages.ftm,1)}/${round(s.averages.fta,1)}</td><td class="num">${round(s.averages.tov,1)}</td><td class="num"><b>${round(s.fp_avg,1)}</b></td><td class="num">${round(s.fp_q10??s.fp_q20,0)}–${round(s.fp_q90??s.fp_q80,0)}</td></tr>`).join('')}</tbody></table></div>`:'';
 return header('NBA · история','Матчи и стабильность','Три прошлых сезона и сыгранные матчи 2026/27. Данные NBA и прогнозы разделены.')+
 `<div class="card"><div class="toolbar"><label style="min-width:260px;flex:2">Баскетболист<select id="hist-player">${opts.map(p=>`<option value="${p.id}" ${p.id===pid?'selected':''}>${esc(p.name)} · ${p.team}</option>`).join('')}</select></label></div>${histLabels()}
 ${table||'<p class="info">История прошлых сезонов для этого игрока отсутствует. Матчи текущего сезона могут быть доступны ниже.</p>'}
 <h3 class="subheading">Распределение FP за выбранный период</h3>
 <div class="toolbar"><label>Сезон<select id="hist-season"><option value="all">Все сезоны</option>${options(availableSeasons,UI.histSeason)}</select></label><label>Соперник<select id="hist-opponent"><option value="all">Все соперники</option>${options(opponents,UI.histOpponent)}</select></label><label>Строк на странице<select id="hist-limit">${[25,50,100,200,500,10000].map(v=>`<option value="${v}" ${UI.histLimit===v?'selected':''}>${v===10000?'Все':v}</option>`).join('')}</select></label></div>
 ${values.length?`<div class="hist-metrics"><div><span>Сыграно</span><strong>${values.length}</strong></div><div><span>Среднее FP</span><strong>${round(mean,1)}</strong></div><div><span>Медиана</span><strong>${round(med,1)}</strong></div><div><span>P10–P90</span><strong>${round(p10)}–${round(p90)}</strong></div><div><span>Разброс SD</span><strong>${round(sd,1)}</strong></div></div><div class="hist-scale"><div class="hist-track"><span style="left:${100*Math.max(0,Math.min(1,(p10-Math.min(...values))/(Math.max(...values)-Math.min(...values)||1)))}%;width:${100*Math.max(0,(p90-p10)/(Math.max(...values)-Math.min(...values)||1))}%"></span></div><small>Полоса показывает центральные 80% фактических FP; не является прогнозным интервалом.</small></div>`:'<div class="info">Для этого фильтра нет подтверждённых сыгранных матчей.</div>'}
 <div class="horizontal" style="justify-content:space-between"><h3 class="subheading">Матчи · ${shown.length} из ${filtered.length}</h3><span class="small">Время — ММ:СС · цвет отражает отклонение FP от среднего отфильтрованных матчей</span></div>
 <div class="tablewrap"><table class="hist-table"><thead><tr><th>Дата</th><th>Сезон</th><th>Матч</th><th class="num">Мин</th><th class="num">PTS</th><th class="num">REB</th><th class="num">AST</th><th class="num">STL</th><th class="num">BLK</th><th class="num">FGM/FGA</th><th class="num">FTM/FTA</th><th class="num">TOV</th><th class="num">FP</th></tr></thead><tbody>${shown.map(x=>`<tr><td>${esc(x.d)}</td><td>${esc(x.season)}</td><td>${x.opp?esc((x.home?'':'@')+x.opp):'—'}</td><td class="num">${histMin(x.min)}</td>${['pts','reb','ast','stl','blk'].map(k=>`<td class="num">${Number.isFinite(Number(x[k]))?round(x[k],0):'—'}</td>`).join('')}<td class="num">${Number.isFinite(Number(x.fgm))?round(x.fgm)+'/'+round(x.fga):'—'}</td><td class="num">${Number.isFinite(Number(x.ftm))?round(x.ftm)+'/'+round(x.fta):'—'}</td><td class="num">${Number.isFinite(Number(x.tov))?round(x.tov):'—'}</td><td class="num ${histTint(Number(x.fp),mean)}"><b>${round(x.fp)}</b></td></tr>`).join('')||'<tr><td colspan="13" class="empty">Нет матчей для этого фильтра.</td></tr>'}</tbody></table></div>
 ${shown.length<filtered.length?`<button class="button" data-action="history-more" style="margin-top:12px">Показать ещё ${Math.min(100,filtered.length-shown.length)} матчей</button>`:''}
 <div class="info" style="margin-top:18px"><b>Источники:</b> NBA Stats / SportsDataverse — прошлые сезоны, NBA / ESPN — 2026/27. Составы и цены Sports.ru хранятся отдельно. Данные текущего сезона появляются после следующей синхронизации GitHub, а не сразу после финальной сирены. Исторический архив: ${round(NBA_HISTORY?.qa?.matched_players||0)} игроков · ${round(NBA_HISTORY?.qa?.matched_player_game_rows||0)} записей. ${historyAvailable(pid)&&!seasons.length?esc(HISTORY_STATUS):''}</div></div>`;
}

function newsPage(){
 const arr=(TG_NEWS?.events||[]).slice().sort((a,b)=>Date.parse(b.published_at||0)-Date.parse(a.published_at||0));
 const mine=arr.filter(a=>(a.player_ids||[]).some(id=>S.roster.includes(id)));
 const age=TG_NEWS?.updated_at_utc?(now()-Date.parse(TG_NEWS.updated_at_utc))/3600000:Infinity;
 const status=TG_NEWS?.status==='public_preview_unverified'?(age>12?'Последняя проверка более 12 часов назад':'Последняя проверка выполнена'):'Автоматическая загрузка не подтверждена';
 const stat={out:'Сообщают: не сыграет',doubtful:'Под большим вопросом',questionable:'Участие под вопросом',probable:'Вероятно сыграет',available:'Сообщают: доступен',injury_update:'Сообщение о состоянии'};
 const card=n=>`<div class="lined"><div class="horizontal"><b>${(n.player_ids||[]).map(id=>esc(P[id]?.name||id)).join(', ')}</b><span class="pill ${['out','doubtful'].includes(n.status)?'bad':n.status==='available'?'good':'warn'}">${esc(stat[n.status]||'Сообщение')}</span></div><div class="small">${esc(n.published_at?dateText(Date.parse(n.published_at)):'Дата неизвестна')} · Telegram · не подтверждено</div><p>${esc(n.text)}</p><a href="${esc(n.url||'https://t.me/s/nba_injurynews')}" target="_blank" rel="noopener noreferrer">Открыть исходный пост</a></div>`;
 const showAll=UI.statusScope==='all';
 const official=officialForPlayers(showAll?BASE.players.map(p=>p.id):S.roster);
 return header('Статусы','Травмы и участие','Сначала — сведения о моей десятке. Официальные NBA Injury Reports отдельно от сообщений Telegram.')+
 `<div class="view-switch status-view-switch" role="group" aria-label="Кого показывать"><button data-status-scope="mine" class="${!showAll?'selected':''}" aria-pressed="${!showAll}">Мои игроки</button><button data-status-scope="all" class="${showAll?'selected':''}" aria-pressed="${showAll}">Остальные новости</button></div>
 <div class="card"><div class="titledetail"><h2>Официальный NBA Injury Report</h2><span class="pill">${official.length} ${showAll?'сопоставлено по лиге':'статусов моей команды'}</span></div>
 <p class="small">${esc(OFFICIAL_STATUS)}. Каждая отметка относится к конкретному матчу; отсутствие игрока в отчёте не означает гарантированное участие.</p>
 ${official.length?official.slice(0,50).map(officialCard).join(''):'<div class="empty">Не найдено сопоставленных официальных отметок на ближайшие 72 часа. Это не подтверждение готовности.</div>'}</div>
 <div class="card"><div class="titledetail"><h2>${showAll?'Telegram · другие игроки':'Telegram · моя команда'}</h2><span class="pill">${showAll?arr.length-mine.length:mine.length} сообщений</span></div>
 <p class="small">${esc(status)} · ${TG_NEWS?.updated_at_utc?esc(dateText(Date.parse(TG_NEWS.updated_at_utc))):'Нет свежей загрузки'}. Новости не обновляют модель вероятности участия автоматически.</p>
 ${(showAll?arr.filter(x=>!mine.includes(x)):mine).slice(0,25).map(card).join('')||'<div class="empty">Нет сопоставленных сообщений в этой группе; медицинский статус неизвестен.</div>'}
 <div class="horizontal" style="margin-top:14px"><a href="https://t.me/s/nba_injurynews" target="_blank" rel="noopener noreferrer">Источник Telegram</a><button class="button" data-tabto="planner">Проверить риск перед заменой</button></div></div>`;
}

function accountPage(){
 const st=window.NBA_CLOUD_STATUS||{state:'local',label:'Работа на этом устройстве'};
 return header('Мой профиль','Профиль и сохранение','Где хранится ваш состав и как не потерять историю замен.')+
 `<div class="grid columns"><section class="card"><h2>Мой доступ</h2><p><b>${esc(st.label||st.state)}</b></p>
 ${st.user?`<p class="small">Аккаунт: ${esc(st.user)}</p><button class="button" data-cloud="logout">Выйти</button>`:st.state==='unconfigured'?`<p>Облачная синхронизация не подключена. Данные хранятся локально на этом устройстве.</p>`:
 `<div class="formgrid"><label>Email<input id="cloud-email" type="email" placeholder="email@example.com" autocomplete="email"></label><label>Пароль<input id="cloud-password" type="password" autocomplete="current-password" minlength="8"></label></div><div class="toolbar" style="margin-top:14px"><button class="primary" data-cloud="login">Войти</button><button class="button" data-cloud="signup">Создать профиль</button></div>`}
 <p class="small">Вход в сервис не связан с аккаунтом Sports.ru и не выполняет трансферы.</p></section>
 <section class="card"><h2>Сохранить мои данные</h2><div class="donut"><span>Игроки в составе</span><b>${S.roster.length} / 10</b></div><div class="donut"><span>Учтённые замены</span><b>${S.executed.length}</b></div>
 <button class="primary" data-action="export-state">Скачать состав, кассу и журнал замен</button>
 <p class="small">Это резервная копия профиля. Локальные журналы наблюдений (цены и решения Optimizer) экспортируются отдельно и могут не переноситься между устройствами.</p>
 <details class="deep-details"><summary>Экспортировать локальные журналы отдельно</summary><div class="toolbar" style="margin-top:12px"><button class="button" data-action="journal-export">Журнал решений</button><button class="button" data-action="price-proof-export">Ручные подтверждения цен</button></div></details>
 <details class="deep-details"><summary>Опасные действия · сбросить команду</summary><p class="small">Сброс удаляет состав и историю замен из выбранного профиля сервиса. Сначала сделайте копию.</p><button class="button" data-action="reset-roster">Сбросить состав и журнал</button></details></section></div>`;
}
function resetRoster(){if(!confirm('Сбросить состав и весь журнал замен НА ЭТОМ профиле? Сначала экспортируйте копию!'))return;S=defaults();save();view();}
const GITHUB_CALENDAR='https://raw.githubusercontent.com/mih98967-afk/nba-season-lab-data/main/data/schedule.json';
const CALENDAR_CACHE_KEY='nba-season-lab-verified-calendar-v1';
function checkCalendar(v){
 if(v?.schema_version!==1||v.status!=='verified_public_calendar_with_known_gaps'||
    v.fantasy_timezone!=='Europe/Moscow'||!Array.isArray(v.games)||
    v.games.length<1100||v.games.length>1230||v.completeness?.teams!==30||
    v.completeness?.team_games_min<70)throw Error('Полный календарь не прошёл проверку охвата');
 const seen=new Set();
 for(const g of v.games){
  if(!String(g.id||'').startsWith('espn_')||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(g.utc)||
     !Number.isFinite(g.epoch)||!g.home||!g.away||seen.has(g.id))throw Error('Некорректный матч календаря');
  seen.add(g.id);
 }
 return v;
}
function setCalendar(v,source){
 const incoming=checkCalendar(v);
 if(CALENDAR&&Date.parse(incoming.updated_at_utc)<Date.parse(CALENDAR.updated_at_utc))return;
 CALENDAR=incoming;UI.chainResult=null;UI.multiResult=null;UI.budgetResult=null;CALENDAR_STATUS=source;
 try{localStorage.setItem(CALENDAR_CACHE_KEY,JSON.stringify(v));}catch{}
 view();
}
async function loadCalendar(){
 if(location.protocol==='file:')return;
 try{
  const response=await fetch(GITHUB_CALENDAR+'?t='+Math.floor(Date.now()/3600000),{cache:'no-store',mode:'cors'});
  if(!response.ok)throw Error('GitHub HTTP '+response.status);
  setCalendar(await response.json(),'GitHub · ESPN UTC');
 }catch(e){CALENDAR_STATUS='Ошибка расписания: '+String(e.message||e).slice(0,90);view();}
}
try{const cached=localStorage.getItem(CALENDAR_CACHE_KEY);if(cached)setCalendar(JSON.parse(cached),'кеш полного календаря');}catch{}
const GITHUB_PUBLIC_DATA='https://raw.githubusercontent.com/mih98967-afk/nba-season-lab-data/main/data/';
function setOfficialStatus(payload,source){
 const qa=window.NBAOfficialStatus?.validate(payload);
 if(!qa?.ok){OFFICIAL_STATUS='Некорректные официальные данные: '+String(qa?.reason||'неизвестно');return false;}
 if(OFFICIAL_FEED && qa.updatedAt<Date.parse(OFFICIAL_FEED.updated_at_utc))return false;
 OFFICIAL_FEED=payload;UI.chainResult=null;UI.multiResult=null;UI.multiCalculatedAt=null;UI.budgetResult=null;
 const age=(now()-qa.updatedAt)/3600000;
 OFFICIAL_STATUS=(age>12?'Последний снимок старше 12 часов · ':'Получено из GitHub · ')+source+' · '+dateText(qa.updatedAt);
 view();return true;
}
async function loadOfficialStatus(){
 if(location.protocol==='file:')return;
 try{
  const u=GITHUB_PUBLIC_DATA+'official_injury_status_research.json?t='+Math.floor(now()/900000);
  const r=await fetch(u,{cache:'no-store',mode:'cors'});
  if(!r.ok)throw Error('GitHub HTTP '+r.status);
  const value=await r.json();
  if(!setOfficialStatus(value,'NBA PDF'))throw Error('файл не прошёл проверку');
 }catch(e){OFFICIAL_STATUS='Не удалось обновить официальный отчёт: '+String(e.message||e).slice(0,95);view();}
}

async function loadAux(){
 try{
  const response=await fetch(GITHUB_PUBLIC_DATA+'history/index.json?t='+Math.floor(Date.now()/900000),{mode:'cors',cache:'no-store'});
  if(!response.ok)throw Error('HTTP '+response.status);
  const v=await response.json();
  if(v.schema_version!==1||v.status!=='complete'||v.format!=='by_shard'||!v.player_shards||v.qa?.matched_players<200)throw Error('Некорректный индекс истории');
  if(HISTORY_INDEX?.version!==v.version){HISTORY_INDEX=v;NBA_HISTORY={schema_version:1,status:'complete',qa:v.qa,players:{}};HISTORY_LOADED_SHARDS.clear();HISTORY_FETCHING_SHARDS.clear();HISTORY_SHARD_ERRORS.clear();}
  HISTORY_STATUS='Готово';view();
  if(tab==='history'||MODAL) scheduleHistory(UI.playerId||S.roster[0]);if(tab==='planner'&&S.modelMode==='validated')prefetchPlannerHistory();
 }catch(e){HISTORY_STATUS='Индекс истории недоступен: '+String(e.message||e).slice(0,90);view();}
 for(const [file,fn] of [['model_report.json',v=>window.NBA.setModel(v)],['model_experiment_v2.json',v=>{if(v.schema_version===2&&v.holdout?.observations>=5000){MODEL_V2=v;view();if(tab==='planner'&&S.modelMode==='validated')prefetchPlannerHistory();}}],['telegram.json',v=>window.NBA.setTelegram(v)]]){
  try{
   const response=await fetch(GITHUB_PUBLIC_DATA+file+'?t='+Math.floor(Date.now()/900000),{mode:'cors',cache:'no-store'});
   if(response.ok){const v=await response.json();if(v.schema_version===1||v.schema_version===2)fn(v);}
  }catch(e){/* Other public sources are optional and cannot change rosters. */}
 }
}

view();if(location.protocol==='http:'||location.protocol==='https:'){restorePublicCache();loadFeed();loadAux();loadCalendar();loadOfficialStatus();}
setInterval(()=>{if(location.protocol!=='file:'){loadFeed();loadAux();loadCalendar();loadOfficialStatus();}},15*60000);

})();
