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
let S=load(),LIVE=SEED,tab='overview',MODAL=null,cache=null,onlineError='',liveSource='starter snapshot',notice='',NBA_HISTORY=embeddedJSON('bootstrap-history'),TG_NEWS=embeddedJSON('bootstrap-telegram'),MODEL_REPORT=embeddedJSON('bootstrap-model');
let CALENDAR=null,CALENDAR_STATUS='Полный календарь загружается';
let OFFICIAL_FEED=null,OFFICIAL_STATUS='Официальные NBA Injury Reports загружаются';
let HISTORY_INDEX=null,HISTORY_STATUS='Загружается индекс…',HISTORY_INFLIGHT=new Set();
let MODEL_V2=null,HISTORY_LOADED_SHARDS=new Set(),HISTORY_FETCHING_SHARDS=new Set(),HISTORY_SHARD_ERRORS=new Map();

let UI={search:'',position:'all',club:'all',sort:'week',compare:[],window:7,calendarStart:'',calendarEnd:'',calendarDays:14,calendarOwn:false,calendarMode:'tours',calendarTour:0,calendarTourCount:3,calendarTourSort:'games',playerId:null,histSeason:'all',histOpponent:'all',histLimit:25,plannerOut:null,plannerIn:null,plannerWhen:null,plannerSell:null,plannerBuy:null,quickPreview:null,chainDays:21,chainPenalty:4,chainResult:null,multiDays:21,multiPenalty:4,multiMoves:3,multiFocus:'all',multiResult:null,budgetPosition:'all',budgetTarget:null,budgetOut:'auto',budgetBuy:null,budgetDays:14,budgetPenalty:4,budgetMoves:3,budgetResult:null};
const root=document.getElementById('root');
function save(){UI.chainResult=null;UI.multiResult=null;UI.budgetResult=null;S.v=5;S.lastUpdate=new Date().toISOString();try{localStorage.setItem(KEY,JSON.stringify(S));}catch{notice='Браузер не разрешил локальное сохранение. Используйте экспорт резервной копии.';}window.nbaCloudSave?.(JSON.parse(JSON.stringify(S)));}
function applyState(remote){if(!remote||!Array.isArray(remote.roster))return;UI.chainResult=null;UI.multiResult=null;UI.budgetResult=null;S={...defaults(),...remote,v:5};saveLocalOnly();tab='overview';view();}
function saveLocalOnly(){try{localStorage.setItem(KEY,JSON.stringify(S));}catch{}}
window.NBA={getState:()=>JSON.parse(JSON.stringify(S)),applyState,guestReset:()=>{S=defaults();saveLocalOnly();view();},getAuthStatus:()=>window.NBA_CLOUD_STATUS||{state:'local',label:'На этом устройстве'},setHistory:(x)=>{NBA_HISTORY=x;view();},setTelegram:(x)=>{TG_NEWS=x;view();},setModel:(x)=>{MODEL_REPORT=x;view();},setOfficial:(x)=>{setOfficialStatus(x,'тестовая инъекция');},view:()=>view()};

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
function moscowWeek(ms){return window.NBATransferGuard.weekKey(ms);}
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
function coverageMessage(start,days){const x=calendarCoverage(start,days);return `<div class="info ${x.ok?'':'warning'}" role="status"><b>Календарь ${days} дней:</b> ${esc(x.reason)}. Источник: <a href="https://github.com/mih98967-afk/nba-season-lab-data/blob/main/data/schedule.json" rel="noopener noreferrer" target="_blank">GitHub / ESPN</a>.</div>`;}
function actualByPlayer(){
 if(cache?.actuals)return cache.actuals;
 const by={};for(const r of LIVE.rows||[]){(by[r.id]||(by[r.id]=[])).push(r);}
 Object.values(by).forEach(a=>a.sort((a,b)=>Date.parse(a.utc)-Date.parse(b.utc)));
 return by;
}
function ownedAt(ms){if(!S.initialRoster?.length||ms<(S.initialEpoch||0))return [];let ids=[...S.initialRoster];for(const t of [...S.executed].sort((a,b)=>a.epoch-b.epoch)){if(t.epoch<=ms){const k=ids.indexOf(t.out);if(k>=0)ids[k]=t.in_;}}return ids;}
function actualTotal(){let sum=0,matches=0;const all=new Map((LIVE.games||[]).map(g=>[g.id,g]));for(const r of LIVE.rows||[]){const g=all.get(r.game_id);if(!g||!Number.isFinite(g.epoch))continue;if(ownedAt(g.epoch-30*60e3).includes(r.id)){sum+=Number(r.fp)||0;matches++;}}
 return {fp:sum,matches};}
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
 return `<div class="info warning" style="margin-bottom:13px"><b>Активен ваш сценарий:</b> ${method}; ${missed}. Это не подтверждение травм или точности FP. <button class="ghost" data-tabto="planner">Изменить в заменах</button></div>`;
}
function view(){updatePlayerTeams();cache={games:null,actuals:null};const games=normalizedGames(),actuals=actualByPlayer();cache={games,actuals};
 document.getElementById('source-status').textContent=currentStatus();document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));
 let html=showNotice();if((tab==='overview'||tab==='players')&&S.roster.length)html+=activeScenarioNotice();if(!S.roster?.length&&(tab==='overview'||tab==='planner'))html+=onboarding();else if(tab==='overview')html+=overview();else if(tab==='players')html+=playersPage();else if(tab==='calendar')html+=calendarPage();else if(tab==='planner')html+=plannerPage();else if(tab==='data')html+=dataPage();else if(tab==='history')html+=historyPage();else if(tab==='news')html+=newsPage();else if(tab==='account')html+=accountPage();
 root.innerHTML=html;renderModal();if(tab==='planner'&&S.modelMode==='validated')setTimeout(prefetchPlannerHistory,0);}
function header(k,title,desc){return `<div class="sectiontitle"><div><div class="eyebrow">${esc(k)}</div><h1>${esc(title)}</h1><p class="sub">${esc(desc)}</p></div></div>`;}
function cardMetric(k,n,sub){return `<div class="metric"><span class="k">${k}</span><strong class="num">${n}</strong><span class="more">${sub}</span></div>`;}
function rosterRow(p){const alert=rosterNews(p.id).length;const official=officialForRoster().find(e=>e.playerId===p.id);const a=playerActual(p.id);const last=a.length?a.at(-1):null;const pred=prediction(p.id,now(),7);const next=futureGames(p.id,now(),7).slice(0,2);
 return `<div class="roster-row"><div><button class="ghost person" data-player="${p.id}">${esc(p.name)}</button>${official?`<span class="pill ${window.NBAOfficialStatus.isHighRisk(official.status)?'warn':''}" title="Официальный отчёт NBA; не изменяет FP автоматически">NBA: ${esc(official.status.toUpperCase())}</span>`:''}${alert?'<span class="pill warn" title="Неофициальный пост Telegram — требуется проверка">Новость</span>':''}<small>${p.team} · ${esc(p.pos)}</small></div><div class="v"><strong>${round(prices(p.id))}</strong><small>цена*</small></div><div class="v"><strong>${last?round(last.fp):'—'}</strong><small>посл. FP</small></div><div class="v"><strong>${pred.available?round(pred.fp):'—'}</strong><small>7 дней</small></div><div class="v last"><strong>${next.map(g=>g.home===p.team?'· '+g.away:'@'+g.home).join(' ')||'—'}</strong><small>соперники</small></div></div>`;}
function overview(){const at=actualTotal(),remain=3-(S.executed||[]).filter(t=>moscowWeek(t.epoch)===moscowWeek(now())).length;
 const thisWeekEnd=weekEnd(now());const enddays=Math.max(0,(thisWeekEnd-now())/86400000),remainingMean=projectionPeriod(S.roster,enddays);const weekRange=calendarCoverage(now(),enddays).ok?summaryRange(S.roster,now(),enddays):null;const free=S.cash;
 let rows=POS.map(pos=>`<div class="poshead">${esc(POSRU[pos])} · ${pos}</div>`+S.roster.filter(id=>P[id]?.pos===pos).map(id=>rosterRow(P[id])).join('')).join('');
 const ng=normalizedGames().filter(g=>g.epoch>now()&&(S.roster||[]).some(id=>P[id]?.team===g.home||P[id]?.team===g.away)).slice(0,7);
 const stale=(now()-Date.parse(LIVE.updated_at_utc||0))>24*3600e3||LIVE.mode==='schedule_sync_only';
 return header('Моя команда','Сезон в одном месте','Ваш подтверждённый состав, календарь и решение. Трансфер на Sports.ru выполняете только вы.')+rosterWarnings()+
 `<div class="grid metrics">${cardMetric('Фактически учтено',round(at.fp)+' FP',at.matches+' загруженных игроко-матчей')}${cardMetric('До конца игровой недели',Number.isFinite(remainingMean)?approx(remainingMean)+' FP':'—',weekRange?'сценарный P10–P90: '+round(weekRange.p10)+'–'+round(weekRange.p90):'Нет полного календаря; не трактуйте как 0 FP')}${cardMetric('Свободные средства',round(free),'из вашего подтверждённого журнала')}${cardMetric('Осталось замен',round(remain)+' / 3','в текущей игровой неделе')}</div>`+
 `<div class="grid columns"><div><div class="card"><div class="titledetail"><h2>Мой состав <span class="pill big">10 игроков</span></h2><span class="small">Цены расчётные до ручного подтверждения</span></div>${rows}<div class="info">* Цены оценены как стартовая цена + загруженные FP. Если результаты пропущены или были корректировки Sports.ru, настройте цены вручную в разделе «Данные».</div></div><div class="card"><h2>Что дальше</h2><p>Сервис не предлагает продавать игроков только потому, что они провели один слабый матч. Для каждой замены он сравнивает календарь, ожидаемые FP, деньги и ценность трансфера.</p><button class="primary" data-tabto="planner">Проверить замену</button></div></div><div><div class="card"><h2>Ближайшие игры состава</h2>${ng.length?ng.map(g=>{const own=S.roster.filter(id=>P[id]?.team===g.home||P[id]?.team===g.away).map(id=>P[id].name).join(', ');return `<div class="lined"><div class="horizontal"><b>${esc(g.away)} @ ${esc(g.home)}</b><span class="spacer"></span><span class="small">${dateText(g.epoch)}</span></div><div class="small">${esc(own)}</div></div>`;}).join(''):'<div class="empty">Дальнейший календарь не загружен</div>'}</div><div class="card"><h2>Качество данных</h2>${LIVE.mode==='seed_partial_verified'?'<span class="pill warn">Неполный срез: 2 записи</span>':stale||LIVE.mode==='sync_failed_using_cache'?'<span class="pill warn">Проверить актуальность</span>':'<span class="pill good">Обновление доступно</span>'}<p><b>${esc(currentStatus())}</b></p><p>NBA box score: ${round(LIVE.rows?.length||0)} записей. UTC-календарь ESPN: ${round(CALENDAR?.games?.length||0)} / 1230 известных игр; ${CALENDAR?.completeness?.unassigned_or_unavailable_games??'—'} пока не назначено.</p><p>Статусы NBA: <a href="https://official.nba.com/nba-injury-report-2026-27-season" rel="noopener noreferrer" target="_blank">официальные PDF</a>. Telegram — дополнительный неподтверждённый источник.</p><button class="button" data-tabto="data">Проверить источники</button></div></div></div>`;
}
function weekEnd(ms){return window.NBATransferGuard.calendarWeekEnd(ms);} // 00:00 MSK next Monday, not 15:00 deadline
function playerList(){let rows=BASE.players.filter(p=>(UI.position==='all'||p.pos===UI.position)&&(UI.club==='all'||p.team===UI.club));const q=UI.search.trim().toLowerCase();if(q)rows=rows.filter(p=>(p.name+' '+p.english+' '+p.team).toLowerCase().includes(q));
 const nextdays=UI.window;
 rows.sort((a,b)=>{if(UI.sort==='price')return b.start_price-a.start_price;if(UI.sort==='expert')return (b.expert_pop||0)-(a.expert_pop||0);if(UI.sort==='historic')return (b.history.at(-1)?.fp_avg||0)-(a.history.at(-1)?.fp_avg||0);if(UI.sort==='minutes')return (b.minutes_projection||0)-(a.minutes_projection||0);return (prediction(b.id,now(),nextdays).fp||0)-(prediction(a.id,now(),nextdays).fp||0);});
 return rows;
}
function playersPage(){const options=POS.map(p=>`<option value="${p}" ${UI.position===p?'selected':''}>${p} — ${esc(POSRU[p])}</option>`).join('');const clubs=[...new Set(BASE.players.map(x=>x.team))].sort().map(x=>`<option ${UI.club===x?'selected':''}>${x}</option>`).join('');const rows=playerList();
 return header('Рынок игроков','Игроки и альтернативы','История: три предыдущих сезона Sports.ru. Текущие игровые данные: NBA/ESPN после успешной синхронизации.')+
 `<div class="card"><div class="toolbar"><label style="flex:2">Найти игрока<input id="search" placeholder="Имя или команда" value="${esc(UI.search)}"></label><label>Позиция<select id="pos"><option value="all">Все</option>${options}</select></label><label>Клуб<select id="club"><option value="all">Все клубы</option>${clubs}</select></label><label>Окно<select id="window"><option value="7" ${UI.window===7?'selected':''}>7 дней</option><option value="14" ${UI.window===14?'selected':''}>14 дней</option><option value="28" ${UI.window===28?'selected':''}>28 дней</option></select></label><label>Сортировка<select id="sort"><option value="week" ${UI.sort==='week'?'selected':''}>Прогноз периода</option><option value="expert" ${UI.sort==='expert'?'selected':''}>Популярность КЭ</option><option value="historic" ${UI.sort==='historic'?'selected':''}>FP/матч 2025/26</option><option value="price" ${UI.sort==='price'?'selected':''}>Цена</option><option value="minutes" ${UI.sort==='minutes'?'selected':''}>Минуты прогноза</option></select></label></div><div class="basket">${UI.compare.length?UI.compare.map(id=>`<button data-uncompare="${id}">× ${esc(P[id]?.name)}</button>`).join('')+` <button class="primary" data-action="compare">Сравнить (${UI.compare.length})</button>`:'<span class="small">Выберите 2–4 игроков через кнопку «+» для сравнения.</span>'}</div><div class="tablewrap"><table><thead><tr><th>Игрок</th><th>Команда</th><th class="num">Цена*</th><th class="num">FP/игра 25/26</th><th class="num">2026/27 сыграно</th><th class="num">Игры вперёд</th><th class="num">Прогноз FP</th><th class="num">КЭ</th><th>+</th></tr></thead><tbody>${rows.slice(0,120).map(p=>{const a=playerActual(p.id);const x=prediction(p.id,now(),UI.window);return `<tr class="interactive ${S.roster.includes(p.id)?'mine':''}"><td><button class="ghost personname" data-player="${p.id}">${esc(p.name)}</button>${S.roster.includes(p.id)?'<span class="pill good">Мой</span>':''}</td><td>${p.team}</td><td class="num">${round(prices(p.id))}</td><td class="num">${p.history.at(-1)?.fp_avg!=null?round(p.history.at(-1).fp_avg,1):'—'}</td><td class="num">${a.length?a.length+' / '+round(a.reduce((s,v)=>s+v.fp,0)/a.length,1):'—'}</td><td class="num">${x.games??'—'}</td><td class="num"><b>${x.available?round(x.fp):'н/д'}</b></td><td class="num">${p.expert_pop==null?'—':round(p.expert_pop,1)+'%'}</td><td><button class="ghost" data-compare="${p.id}">${UI.compare.includes(p.id)?'✓':'+'}</button></td></tr>`;}).join('')}</tbody></table></div><div class="small" style="margin-top:10px">Показано ${Math.min(rows.length,120)} из ${rows.length}. Знак «н/д» означает отсутствие прогнозной оценки, не нулевые очки. КЭ — популярность среди успешных менеджеров на момент выгрузки, не вероятность успеха.</div></div>`;
}
function playerModal(id){const p=P[id];if(!p)return '';const recent=playerActual(id);const hist=p.history||[];const nbaHist=NBA_HISTORY?.players?.[id]||[];const pred7=prediction(id,now(),7),pred14=prediction(id,now(),14);const futures=futureGames(id,now(),14);
 return `<div class="titledetail"><div><div class="eyebrow">${p.team} · ${p.pos}</div><h2 style="margin:4px 0">${esc(p.name)}</h2><div class="small">${esc(p.english)}</div></div><button class="close" data-action="close-modal" aria-label="Закрыть">×</button></div><div class="tagline"><span class="tag">Цена*: ${round(prices(id))}</span><span class="tag">КЭ: ${p.expert_pop!=null?round(p.expert_pop,1)+'%':'—'}</span>${displayRisk(p)}</div><div class="grid stats-mini" style="margin:16px 0"><div><span class="stat-label">FP при выходе (модель)</span><strong>${p.forecast?approx(learnedMean(p,futures[0]||{epoch:now(),id:'',home:p.team,away:''})):'н/д'}</strong></div><div><span class="stat-label">FP / 7 дней</span><strong>${pred7.available?round(pred7.fp):'—'}</strong></div><div><span class="stat-label">FP / 14 дней</span><strong>${pred14.available?round(pred14.fp):'—'}</strong></div></div>
 <h3>История fantasy за три сезона</h3><div class="tablewrap"><table><thead><tr><th>Сезон</th><th>Клуб</th><th class="num">Игры</th><th class="num">Всего FP</th><th class="num">FP/матч</th><th>Поматчевые</th></tr></thead><tbody>${hist.map(h=>`<tr><td>${h.season}</td><td>${esc(h.team)}</td><td class="num">${h.games}</td><td class="num">${round(h.total)}</td><td class="num">${h.fp_avg??'—'}</td><td>${h.log_valid?'<span class="pill good">полный ряд</span>':'<span class="pill warn">частично</span>'}</td></tr>`).join('')||'<tr><td colspan="6">История отсутствует</td></tr>'}</tbody></table></div>
 <h3 class="subheading">Текущий сезон · реальные матчи</h3>${recent.length?`<div class="tablewrap"><table><thead><tr><th>Дата МСК</th><th>Мин.</th><th class="num">PTS</th><th class="num">REB</th><th class="num">AST</th><th class="num">FP</th></tr></thead><tbody>${recent.slice(-10).reverse().map(r=>`<tr><td>${dateText(r.utc)}</td><td>${round(r.minutes,0)}</td><td class="num">${r.box?.pts??'—'}</td><td class="num">${r.box?.reb??'—'}</td><td class="num">${r.box?.ast??'—'}</td><td class="num"><b>${round(r.fp)}</b></td></tr>`).join('')}</tbody></table></div>`:'<div class="info">В загруженной NBA-статистике ещё нет сыгранных матчей. Это не подтверждение отсутствия игр.</div>'}
 <h3 class="subheading">Ближайший календарь</h3>${futures.length?futures.map(g=>`<div class="lined">${dateText(g.epoch)} · <b>${g.home===p.team?g.away+' дома':'@'+g.home+' в гостях'}</b> · ${approx(learnedMean(p,g))} FP при выходе · вероятность участия (модель) ${round(probability(p,g)*100)}%</div>`).join(''):'<p>Пока нет загруженного расписания на следующие 14 дней.</p>'}
 <h3 class="subheading">Медицинский сценарий</h3><div class="toolbar"><label>Ручной статус<select id="medical" data-id="${p.id}"><option value="default" ${(S.medical[id]||'default')==='default'?'selected':''}>Без подтверждённой поправки</option><option value="available" ${S.medical[id]==='available'?'selected':''}>Могу подтвердить готовность</option><option value="questionable" ${S.medical[id]==='questionable'?'selected':''}>Сомнительный / сниженный шанс</option><option value="out" ${S.medical[id]==='out'?'selected':''}>Подтверждён OUT</option></select></label></div><div class="info warning">Этот переключатель меняет только ваш сценарный расчёт. Статус не устанавливается автоматически из Telegram.</div>${p.news?`<details><summary>Ранний контекст (${esc(p.news_date||'дата неизвестна')})</summary><p>${esc(p.news)}</p></details>`:''}`;
}
function compareModal(){const ids=UI.compare;return `<div class="titledetail"><h2>Сравнение ${ids.length} игроков</h2><button class="close" data-action="close-modal">×</button></div><div class="tablewrap"><table><thead><tr><th>Метрика</th>${ids.map(id=>`<th>${esc(P[id].name)}</th>`).join('')}</tr></thead><tbody>${[['Клуб',p=>p.team],['Позиция',p=>p.pos],['Цена*',p=>round(prices(p.id))],['FP/игра 25/26',p=>p.history.at(-1)?.fp_avg??'—'],['FP/7 дней',p=>prediction(p.id,now(),7).available?round(prediction(p.id,now(),7).fp):'—'],['FP/14 дней',p=>prediction(p.id,now(),14).available?round(prediction(p.id,now(),14).fp):'—'],['Игр/14 дней',p=>prediction(p.id,now(),14).available?prediction(p.id,now(),14).games:'—'],['КЭ',p=>p.expert_pop==null?'—':round(p.expert_pop,1)+'%']].map(([label,get])=>`<tr><td>${label}</td>${ids.map(id=>`<td>${esc(get(P[id]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div><div class="info warning" style="margin-top:14px">Сравнивайте не только FP. При покупке проверьте остаток денег, позицию и максимум двух из клуба. Прогнозы — не фактические результаты.</div>`;}
function calendarPage(){
 const mode=UI.calendarMode==='window'?'window':'tours';
 return header('Календарь','Туры и игровые окна','Игровые дни и туры — по календарной дате NBA (ET, США). Время каждого матча — по Москве.')+
 `<div class="card calendar-mode-picker"><div class="horizontal" style="align-items:center"><label class="compact" for="cal-view">Режим календаря<select id="cal-view"><option value="tours" ${mode==='tours'?'selected':''}>По турам · Пн–Вс по дате NBA</option><option value="window" ${mode==='window'?'selected':''}>Любой диапазон дат</option></select></label><span class="small">Ночные матчи понедельника по Москве, проведённые в воскресенье США, относятся к предыдущему туру. Внутри ячеек показано московское время (МСК).</span></div></div>`+
 (mode==='tours'?calendarToursPage():calendarWindowPage());
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
 return `<div class="shortlist-panel" style="margin-top:18px"><div class="titledetail"><h3>Проверить альтернативы</h3><span class="small">Свободных замен на выбранной неделе: ${remaining}/3</span></div>
 <p class="small">Тот же слот, бюджет и лимит команд. Разница FP рассчитана с выбранного момента замены относительно KEEP, с учётом уже существующего черновика. Цены приблизительные; покупка всегда проверяется на Sports.ru.</p>
 ${rows?`<div class="tablewrap"><table><thead><tr><th>Кандидат</th><th>Цена</th><th>Игр 7/14 дней</th><th>Δ 7 дней</th><th>Δ 14 дней</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`:'<div class="info warning">Нет условно допустимых кандидатов. Сохранение игрока (KEEP) — допустимое решение.</div>'}
 <div class="small" style="margin-top:8px">${ranked.eligible} условно допустимых из ${ranked.checked} рассмотренных. Это сценарные оценки, не доказанные вероятности и не гарантия выгодного трансфера. Если нет положительной разницы — KEEP.</div></div>`;
}
function chainSignature(){return JSON.stringify({r:S.roster,d:S.draft,c:S.cash,e:S.executed,
 p:S.prices,t:S.teamOverrides,m:S.medical,live:LIVE.updated_at_utc,cal:CALENDAR?.updated_at_utc,
 model:S.modelMode,risk:S.riskMode});}
function chainPanel(out,when){
 if(!window.NBAChainPlanner||S.roster.length!==10)return '';
 const result=UI.chainResult;
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
  <div class="toolbar"><button class="primary" data-action="calculate-chains">Сравнить цепочки для ${esc(P[out]?.name||'игрока')}</button><span class="small">Старт: ${dateText(when)} МСК</span></div>
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
 const result=UI.budgetResult?.signature===budgetSignature()?UI.budgetResult:null;
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
  <div class="toolbar"><button class="primary" data-action="calculate-budget" ${!target||!remaining?'disabled':''}>Найти пакеты под покупку</button><span class="small">Свободно: ${remaining} из 3 ходов · момент ${dateText(t)} МСК</span></div>
  ${detail}<p class="small">Черновик не совершает трансферы. Если цены на Sports.ru отличаются, обновите их и пересчитайте. Цена цели в этом поле используется только для сценария, не меняя профиль.</p></div>`;
}
function calculateBudget(){
 if(!window.NBABudgetPackage)return showMsg('Модуль финансирования покупки недоступен.');
 const t=moscowEpoch(document.getElementById('budget-when')?.value);
 if(!Number.isFinite(t))return showMsg('Укажите момент замены по Москве.');
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
function multiPanel(){
 if(!window.NBAMultiPlanner||S.roster.length!==10)return '';
 const result=UI.multiResult?.signature===chainSignature()?UI.multiResult:null;
 const choices=['all',...POS].map(p=>`<option value="${p}" ${UI.multiFocus===p?'selected':''}>${p==='all'?'Вся десятка':p+' · '+POSRU[p]}</option>`).join('');
 const gain=n=>`<strong class="${n>=0?'delta-plus':'delta-minus'}">${n>=0?'+':''}${round(n,1)} FP</strong>`;
 const types={keep:'KEEP · не менять',multi_slot:'Несколько слотов',same_slot_chain:'Цепочка в одном слоте',later:'Отложить замену',now:'Заменить сейчас'};
 let detail='';
 if(result&&!result.ready)detail=`<div class="info warning" role="status">${esc(result.reason)}</div>`;
 else if(result?.ready){
  detail=`<div class="multi-results" role="status"><p class="small">Прогноз KEEP всей команды: ${round(result.baseline,1)} FP за ${result.horizonDays} дней. Проверено ${result.tested} промежуточных вариантов, полную проверку прошли ${result.eligible}. Это ограниченный поиск, не доказанный оптимум.</p>
   ${result.routes.map((route,i)=>`<div class="multi-route"><div class="horizontal" style="justify-content:space-between"><b>${esc(types[route.kind]||route.kind)}</b>${gain(route.gain)}</div>
    <div class="small">С резервом ${result.opportunityPenalty} FP за ход: ${gain(route.net)} · новых ходов ${route.moves.length} · касса ${round(route.cash)}</div>
    ${route.moves.length?route.moves.map((m,j)=>`<div class="multi-step"><span>${j+1}.</span> ${esc(P[m.out]?.name||m.out)} → <b>${esc(P[m.in_]?.name||m.in_)}</b><span class="small">${dateText(m.epoch)} МСК · ${round(m.sell)} → ${round(m.buy)}</span></div>`).join(''):'<p class="small">Состав сохраняется, новые ходы не расходуются.</p>'}
    <div class="chain-weeks">${route.weeks.map(w=>`<span class="chain-week">${esc(w.week)}: ${w.gain==null?'н/д':(w.gain>=0?'+':'')+round(w.gain,1)} FP · ходов ${w.used}/3</span>`).join('')}</div>
    ${route.warnings?.length?`<p class="small warntext">Проверить перед покупкой: ${esc(route.warnings.slice(0,2).join(' · '))}</p>`:''}
    ${route.moves.length?`<button class="button" data-multi-apply="${i}">Добавить ${route.moves.length} шаг(а) только в черновик</button>`:''}</div>`).join('')}
   <p class="small">Будущие цены и разблокировки неизвестны; при необходимости проверьте статус в официальном отчёте NBA. Сигналы Telegram не повышают вероятность участия автоматически.</p></div>`;
 }
 return `<div class="card multi-panel" id="multi-panel"><div class="titledetail"><h2>План замен для всей команды</h2><span class="pill">Не совершает трансферы</span></div>
  <p>Что выгоднее: сохранить три хода, заменить одного игрока или распределить их по нескольким слотам и неделям? Учитываются общая касса, позиции и не более двух игроков из клуба.</p>
  <div class="formgrid"><label>Игроки для поиска<select id="multi-focus">${choices}</select></label>
   <label>Окно<select id="multi-days">${[14,21,28].map(v=>`<option value="${v}" ${UI.multiDays===v?'selected':''}>${v} дней</option>`).join('')}</select></label>
   <label>Новых ходов максимум<select id="multi-moves">${[1,2,3,4].map(v=>`<option value="${v}" ${UI.multiMoves===v?'selected':''}>${v} ${v===1?'ход':'хода'}</option>`).join('')}</select></label>
   <label>Резерв FP за ход<select id="multi-penalty">${[0,4,8].map(v=>`<option value="${v}" ${UI.multiPenalty===v?'selected':''}>${v} FP</option>`).join('')}</select></label></div>
  <div class="toolbar"><button class="primary" data-action="calculate-multi">Сравнить планы команды</button><span class="small">Начало анализа: время замены выше (${dateText(Number.isFinite(UI.plannerWhen)?UI.plannerWhen:now()+20*60000)} МСК)</span></div>
  ${detail}<p class="small">* Резерв FP — эвристика, а не штраф Sports.ru. Поиск ограничен несколькими датами для быстрого расчёта на телефоне. Не заменяет проверку цены и блокировки.</p></div>`;
}
function calculateMulti(){
 if(!window.NBAMultiPlanner)return showMsg('Модуль общего планировщика не загрузился.');
 const t=moscowEpoch(document.getElementById('when')?.value);
 if(!Number.isFinite(t))return showMsg('Укажите время первого решения в поле «Момент замены».');
 UI.plannerWhen=t;
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
 const result=UI.multiResult;
 if(!result?.ready||result.signature!==chainSignature())return showMsg('Данные изменились: пересчитайте план.');
 const route=result.routes?.[index];
 if(!route?.moves?.length)return showMsg('Это KEEP — добавлять в черновик нечего.');
 if(route.moves.some(m=>m.epoch<now()-60000))return showMsg('Запланированное время уже прошло: пересчитайте план.');
 if(!calendarCoverage(result.start,result.horizonDays).ok)return showMsg('Календарь изменился: пересчитайте план.');
 const checked=planResult([...S.draft,...route.moves]);
 if(!checked.valid)return showMsg('План больше не допустим: '+checked.errors.join(' · '));
 const summary=route.moves.map(m=>`${P[m.out]?.name||m.out} → ${P[m.in_]?.name||m.in_} (${dateText(m.epoch)} МСК)`).join('\n');
 if(!confirm('Добавить только в ЧЕРНОВИК '+route.moves.length+' шаг(а)?\n\n'+summary+'\n\nСверьте фактические цены и разблокировки на Sports.ru. Реальных трансферов не будет.'))return;
 S.draft.push(...route.moves);save();view();showMsg('План добавлен только в черновик. Реальные операции необходимо отдельно выполнить на Sports.ru.');
}
function calculateChains(){
 if(!window.NBAChainPlanner)return showMsg('Модуль цепочек ещё не загрузился.');
 const t=moscowEpoch(document.getElementById('when')?.value);
 const out=document.getElementById('out')?.value;
 if(!Number.isFinite(t)||!out)return showMsg('Укажите игрока OUT и время начала.');
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
 const start=Date.parse(moscowWeek(now())+'T00:00:00+03:00');
 if(!calendarCoverage(now(),28).ok)return `<div class="card"><h2>Помесячный план по неделям</h2><div class="info warning">${esc(calendarCoverage(now(),28).reason)}. Не показываем ложные нулевые FP по неделям.</div></div>`;
 const result=planResult(draft);
 const spans=Array.from({length:4},(_,i)=>{
  const a=start+i*7*86400000,b=a+7*86400000;
  const base=rangeMean(S.roster,[],Math.max(now(),a),b);
  const withPlan=rangeMean(S.roster,draft,Math.max(now(),a),b);
  return {a,base,withPlan,diff:withPlan-base,used:result.used[moscowWeek(a)]||0};
 });
 const max=Math.max(1,...spans.map(z=>Math.max(z.base,z.withPlan)));
 return `<div class="card"><div class="titledetail"><h2>Что изменится по неделям</h2><span class="small">Прогноз, не начисленные FP</span></div><div class="weekrows">${spans.map((r,i)=>`<div class="weekrow"><div class="horizontal"><b>Неделя ${i+1}</b><span class="small">с ${justDay(r.a)} · замен ${r.used}/3</span></div><div class="weekbar" aria-hidden="true"><span style="width:${Math.round(r.base/max*100)}%"></span></div><div class="weekbar planned" aria-hidden="true"><span style="width:${Math.round(r.withPlan/max*100)}%"></span></div><div class="horizontal"><span class="small">Без плана ${round(r.base)} → с планом <b>${round(r.withPlan)}</b></span><b class="${r.diff>=0?'delta-plus':'delta-minus'}">${r.diff>=0?'+':''}${round(r.diff,1)} FP</b></div></div>`).join('')}</div><p class="small">Рассчитаны только игры, уже присутствующие в календаре. Штраф за использованный трансфер не переводится в FP: решение оценивается отдельно.</p></div>`;
}
function plannerPage(){const prior=planResult(S.draft);const available=prior.valid?prior.roster:S.roster;const out=available.includes(UI.plannerOut)?UI.plannerOut:available[0];const choices=allowedIds(out,available);const dst=choices.some(p=>p.id===UI.plannerIn)?UI.plannerIn:choices[0]?.id;const when=UI.plannerWhen&&Number.isFinite(UI.plannerWhen)?UI.plannerWhen:now()+20*60000;
 const form=`<div class="formgrid"><label>Кого продать<select id="out">${available.map(id=>`<option value="${id}" ${out===id?'selected':''}>${esc(P[id].name)} · ${P[id].pos}</option>`).join('')}</select></label><label>Кого купить<select id="in">${choices.map(p=>`<option value="${p.id}" ${dst===p.id?'selected':''}>${esc(p.name)} · ${p.team} · ${round(prices(p.id))}${prices(p.id)>planResult(S.draft).cash+prices(out)?' · не хватает денег':''}</option>`).join('')}</select></label><label>Момент замены, Москва<input id="when" type="datetime-local" value="${moscowInput(when)}"></label><label>Цена продажи, фактическая<input id="sell" type="number" min="0" value="${UI.plannerSell!=null?UI.plannerSell:prices(out)}"></label><label>Цена покупки, фактическая<input id="buy" type="number" min="0" value="${UI.plannerBuy!=null?UI.plannerBuy:prices(dst)}"></label><div class="horizontal" style="align-self:end"><button class="button" data-action="preview-transfer">Проверить вариант</button><button class="primary" data-action="add-draft">Добавить в черновик</button></div></div>`;
 const checked=planResult(S.draft);const seven=plannedMean(S.roster,S.draft,7),fourteen=plannedMean(S.roster,S.draft,14),base7=plannedMean(S.roster,[],7),base14=plannedMean(S.roster,[],14);
 const ordered=[...S.draft].sort((a,b)=>a.epoch-b.epoch);
 const steps=ordered.length?ordered.map((t,i)=>{const st=checked.steps.find(x=>x.t===t);return `<div class="step"><span class="step-index">${i+1}</span><div style="flex:1"><b>${esc(P[t.out]?.name)} → ${esc(P[t.in_]?.name)}</b><div class="small">${dateText(t.epoch)} МСК · ${round(t.sell)} → ${round(t.buy)} · касса после: ${round(st?.cash)}</div>${st?.errors.length?`<span class="pill bad">${esc(st.errors.join(' · '))}</span>`:''}${st?.warnings.length?`<span class="pill warn">${esc(st.warnings.join(' · '))}</span>`:''}</div><button class="ghost" data-remove-draft="${S.draft.indexOf(t)}">Удалить</button></div>`;}).join(''):'<div class="empty">Черновик пуст. Сначала определите срок удержания, потом выбирайте игрока и дату.</div>';

 const officialCandidates=officialForPlayers([out,dst]);
 const officialHint=officialCandidates.length?`<div class="info warning" style="margin-top:12px"><b>Официальные статусы на ближайший матч</b>${officialCandidates.map(officialCard).join('')}<span class="small">Эти сведения не меняют прогноз FP автоматически. Участие в остальных матчах неизвестно.</span></div>`:'';
 return header('Решения','Планировщик замен','Только расчёт. Фактическую замену выполняете на Sports.ru, затем отмечаете здесь как совершённую.')+planningControls()+(S.roster.length===10?budgetPanel():'')+
 `<div class="grid columns"><div><div class="card"><h2>Новая замена</h2>${form}${officialHint}${UI.quickPreview?`<div class="info ${UI.quickPreview.valid?'':'error'}" role="status" style="margin-top:12px"><b>${UI.quickPreview.valid?'Условно допустимо: проверьте Sports.ru':'Проверка: недопустимо'}</b><div>${UI.quickPreview.valid?'Дополнительно к текущему черновику: '+(Number.isFinite(UI.quickPreview.gain7)&&UI.quickPreview.gain7>=0?'+':'')+approx(UI.quickPreview.gain7)+' FP за 7 дней; '+(Number.isFinite(UI.quickPreview.gain14)&&UI.quickPreview.gain14>=0?'+':'')+approx(UI.quickPreview.gain14)+' FP за 14 дней.':esc(UI.quickPreview.errors.join(' · '))}</div>${UI.quickPreview.warnings.length?'<div>'+esc(UI.quickPreview.warnings.join(' · '))+'</div>':''}</div>`:''}<div class="info" style="margin-top:14px">Сначала нажмите «Проверить вариант». Добавление в черновик ничего не меняет на Sports.ru. Цена после будущего матча неизвестна; укажите фактическую вручную.</div>${shortlistPanel(out,when,available)}</div><div class="card"><h2>Черновик · ${S.draft.length} замен (не более 3 в неделю)</h2>${steps}<div class="review"><div class="horizontal"><span>Выгода за 7 дней</span><span class="spacer"></span><strong>${Number.isFinite(seven-base7)&&seven-base7>=0?'+':''}${approx(seven-base7)} FP</strong></div><div class="horizontal"><span>Выгода за 14 дней</span><span class="spacer"></span><strong>${Number.isFinite(fourteen-base14)&&fourteen-base14>=0?'+':''}${approx(fourteen-base14)} FP</strong></div><div class="horizontal"><span>Остаток денег после плана</span><span class="spacer"></span><strong>${round(checked.cash)}</strong></div>${checked.errors.length?`<div class="info error">${checked.errors.map(esc).join(' · ')}</div>`:''}${checked.warnings.length?`<div class="info warning" style="margin-top:9px">${checked.warnings.map(esc).join(' · ')}</div>`:''}<div class="small" style="margin-top:12px">* Подсчёт квоты: Пн–Вс по МСК. Время сброса квоты на Sports.ru не подтверждено, при неоднозначности показывается предупреждение. Будущие цены не прогнозируются.</div></div><div class="toolbar"><button class="button" data-action="clear-draft">Очистить черновик</button><button class="primary" data-action="confirm-draft" ${(!S.draft.length||!checked.valid||S.draft.some(t=>t.epoch>now()+2*60000))?'disabled':''}>Отметить выполненной</button></div><div class="small">Подтверждение меняет только локальную историю. Перед нажатием требуется действительно выполнить план на Sports.ru.</div></div></div><div><div class="card"><h2>Состояние команды</h2><div class="donut"><span>Свободно сейчас</span><b>${round(S.cash)}</b></div><div class="donut"><span>Замен в текущей неделе</span><b>${S.executed.filter(t=>moscowWeek(t.epoch)===moscowWeek(now())).length} / 3</b></div><div class="donut"><span>Игроков в составе</span><b>${S.roster.length}</b></div><div class="separator"></div><h3>Подтверждённая история</h3>${S.executed.length?S.executed.slice().reverse().map(t=>`<div class="lined"><b>${esc(P[t.out]?.name)} → ${esc(P[t.in_]?.name)}</b><div class="small">${dateText(t.epoch)} · ${round(t.sell)} → ${round(t.buy)}</div></div>`).join(''):'<p>Ещё нет подтверждённых замен. Черновики не влияют на текущий состав.</p>'}</div><div class="card"><h2>Перед каждой покупкой</h2><div class="small">1. Убедиться в статусе игрока.<br>2. Проверить реальную цену.<br>3. Сравнить прирост на 7 и 14 дней.<br>4. Проверить блокировку и остаток замен.<br>5. Только затем покупать.</div></div></div></div>${S.roster.length===10?multiPanel()+chainPanel(out,when)+scenarioPanel(S.draft,checked)+planByWeeks(S.draft):''}`;
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
function dataPage(){const age=(now()-Date.parse(LIVE.updated_at_utc||0))/3600000;const partial=['seed_partial_verified','sync_failed_using_cache','schedule_sync_only'].includes(LIVE.mode);const report=LIVE.source_status;const providers=typeof report==='object'?Object.entries(report).map(([k,v])=>`<div class="donut"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join(''):esc(report||'статический файл');
 const pricesHtml=S.roster.map(id=>`<div class="donut"><span>${esc(P[id].name)} · ${P[id].team}</span><div class="horizontal"><input class="priceedit" data-price-id="${id}" type="number" min="0" aria-label="Цена ${esc(P[id].name)}" value="${round(prices(id)).replace(/\s/g,'')}" style="width:100px;max-width:100px;padding:5px 6px;border:1px solid var(--line);border-radius:6px"><button class="ghost" data-price-reset="${id}" title="Вернуть расчётную">↻</button></div></div>`).join('');
 const teamsHtml=S.roster.map(id=>`<div class="donut"><span>${esc(P[id].name)}</span><select class="teamedit" data-team-id="${id}" aria-label="Клуб ${esc(P[id].name)}" style="max-width:155px"><option value="auto" ${!(S.teamOverrides||{})[id]?'selected':''}>Авто · ${P[id].team}</option>${Object.keys(CLUBS).sort().map(t=>`<option value="${t}" ${S.teamOverrides?.[id]===t?'selected':''}>${t}</option>`).join('')}</select></div>`).join('');
 const note=Array.isArray(LIVE.injuries)?LIVE.injuries.slice(0,8):[];
 return header('Контроль','Источники и настройки','Никаких скрытых автообновлений: источник, время и статус каждого набора данных отображаются явно.')+sourceHealth()+
 `<div class="grid columns"><div><div class="card"><h2>Обновления</h2><div class="horizontal"><span class="pill ${age>24||partial?'warn':'good'}">${esc(currentStatus())}</span><span class="small">${esc(LIVE.mode)}</span></div><p>Завершённые NBA-матчи и FP поступают из <a href="https://github.com/mih98967-afk/nba-season-lab-data/blob/main/data/live.json" target="_blank" rel="noopener">публичного GitHub</a>. Данные обновляются по расписанию GitHub Actions; отсутствие результата не означает ноль.</p><p class="small">Текущий источник: ${esc(liveSource)}. ${onlineError?'<span class="warn">'+esc(onlineError)+'</span>':''}</p><div class="toolbar"><button class="primary" data-action="refresh">Обновить сейчас</button><label class="button" style="flex:0 1 auto;position:relative;cursor:pointer">Импорт NBA JSON<input id="feedfile" type="file" accept="application/json,.json" style="display:none"></label><button class="button" data-action="export-state">Скачать копию моих данных</button><label class="button" style="flex:0 1 auto;position:relative;cursor:pointer">Импорт копии<input id="backupfile" type="file" accept="application/json,.json" style="display:none"></label></div><div class="info">Кнопка проверяет публичный GitHub. Программа собирает статистику каждые четыре часа; сам сайт сверяет файл каждые 15 минут при открытой вкладке. Это не синхронизация цен Sports.ru и не онлайн-трансляция матча.</div><div class="separator"></div><h3>Статус поставщиков</h3>${providers}<div class="donut"><span>Полный календарь</span><b>${esc(CALENDAR_STATUS)} · ${CALENDAR?.games?.length||0} игр</b></div><div class="small">Загружено ${LIVE.rows?.length||0} записей игроков, матчей со счётом ${LIVE.games?.length||0}, календарных игр ${normalizedGames().length}. История Sports.ru — три сезона из ваших таблиц. Подробная NBA-история загружается отдельным набором.</div>${LIVE.warnings?.length?`<details><summary>Ошибки или ограничения (${LIVE.warnings.length})</summary><ul class="warninglist">${LIVE.warnings.slice(0,12).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>`:''}</div><div class="card"><h2>Новости и медицинские риски</h2><div class="info warning">Telegram — вторичный источник. Сообщение о травме не меняет вероятность игры без проверки и выбора статуса в карточке игрока.</div>${note.length?note.map(n=>`<div class="lined"><div class="small">${n.date?esc(n.date):'Дата не определена'} · <a href="${esc(n.source||'https://t.me/s/nba_injurynews')}" target="_blank" rel="noopener noreferrer">Источник</a></div><div>${esc(n.text)}</div></div>`).join(''):'<p>Свежая подборка из канала пока не была загружена. <a href="https://t.me/s/nba_injurynews" target="_blank" rel="noopener noreferrer">Открыть @nba_injurynews</a></p>'}</div></div><div><div class="card"><h2>Цены Sports.ru</h2><p>Если цены расходятся с расчётными, исправьте их здесь. Обновление не затронет стартовый состав или реальные трансферы.</p>${pricesHtml}<p><b>Свободная касса:</b></p><div class="horizontal"><input type="number" min="0" id="cash" value="${round(S.cash).replace(/\s/g,'')}" style="width:120px;padding:9px;border:1px solid var(--line);border-radius:7px"><button class="button" data-action="set-cash">Сохранить кассу</button></div><div class="small" style="margin-top:10px">После реального трансфера касса автоматически изменится на цена продажи − цена покупки.</div></div><div class="card"><h2>Команда игрока после перехода</h2><p>Клуб определяется по последней загруженной игре NBA. Если Sports.ru уже обновил его до дебюта, выберите клуб вручную. Для новых игроков автоматическое сопоставление может запаздывать.</p>${teamsHtml}<div class="small">Изменение клуба пересчитывает календарь и лимит двух игроков. Проверьте клуб в Sports.ru: NBA не определяет fantasy-позицию.</div></div><div class="card"><h2>Интерпретация прогноза</h2><p>Исторический сигнал: 2023/24, 2024/25, 2025/26. Текущий сезон: новые результаты NBA с небольшим весом, чтобы не переоценивать один матч.</p><p><b>Прогноз FP при выходе</b> — результативность в одном сыгранном матче. <b>FP за период</b> дополнительно учитывает число игр и модельный риск пропуска.</p><p><b>Диапазон</b> — сценарное моделирование, не проверенный доверительный интервал будущего сезона.</p><p>Официальный <a href="https://official.nba.com/nba-injury-report-2026-27-season/" target="_blank" rel="noopener noreferrer">NBA injury report</a> и <a href="https://t.me/s/nba_injurynews" target="_blank" rel="noopener noreferrer">канал травм</a>.</p></div></div></div>`;
}
function renderModal(){let target=document.getElementById('modal-root');if(!MODAL){target?.remove();return;}if(!target){target=document.createElement('div');target.id='modal-root';document.body.appendChild(target);}target.className='modal';target.innerHTML=`<div class="modalpanel" role="dialog" aria-modal="true">${MODAL==='compare'?compareModal():playerModal(MODAL)}</div>`;target.onclick=e=>{if(e.target===target){MODAL=null;renderModal();}};}
function setTab(t){tab=t;MODAL=null;view();window.scrollTo({top:0,behavior:'instant'});}
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
 LIVE=v;UI.chainResult=null;UI.multiResult=null;UI.budgetResult=null;liveSource=origin;onlineError='';
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
document.addEventListener('click',e=>{const el=e.target.closest('[data-action],[data-tabto],[data-player],[data-compare],[data-uncompare],[data-remove-draft],[data-price-reset],[data-shortlist],[data-chain-apply],[data-multi-apply],[data-budget-apply]');if(!el)return;
 if(el.dataset.tabto){setTab(el.dataset.tabto);return;}
 if(el.dataset.player){MODAL=el.dataset.player;renderModal();return;}
 if(el.dataset.compare){const id=el.dataset.compare;if(UI.compare.includes(id))UI.compare=UI.compare.filter(x=>x!==id);else if(UI.compare.length<4)UI.compare.push(id);else return showMsg('Можно сравнивать максимум четырёх игроков.');view();return;}
 if(el.dataset.uncompare){UI.compare=UI.compare.filter(id=>id!==el.dataset.uncompare);view();return;}
 if(el.dataset.chainApply!==undefined){applyChain(Number(el.dataset.chainApply));return;}
 if(el.dataset.multiApply!==undefined){applyMulti(Number(el.dataset.multiApply));return;}
 if(el.dataset.budgetApply!==undefined){applyBudget(Number(el.dataset.budgetApply));return;}
 if(el.dataset.shortlist){UI.plannerIn=el.dataset.shortlist;UI.plannerBuy=null;UI.quickPreview=null;view();return;}
 if(el.dataset.removeDraft!==undefined){S.draft.splice(Number(el.dataset.removeDraft),1);save();view();return;}
 if(el.dataset.priceReset){delete S.prices[el.dataset.priceReset];save();view();return;}
 switch(el.dataset.action){case 'dismiss':notice='';view();break;case 'create-roster':createRoster();break;case 'reset-roster':resetRoster();break;case 'close-modal':MODAL=null;renderModal();break;case 'compare':if(UI.compare.length>=2){MODAL='compare';renderModal();}else showMsg('Выберите хотя бы двух игроков.');break;case 'cal-prev-tours':UI.calendarTour=Math.max(1,(UI.calendarTour||window.NBACalendarTours.tourNumber(now()))-UI.calendarTourCount);view();break;case 'cal-next-tours':UI.calendarTour=Math.min(Math.max(1,window.NBACalendarTours.seasonTourCount()-UI.calendarTourCount+1),(UI.calendarTour||window.NBACalendarTours.tourNumber(now()))+UI.calendarTourCount);view();break;case 'cal-current-tours':UI.calendarTour=window.NBACalendarTours.tourNumber(now());view();break;case 'cal-prev-window':{const T=window.NBACalendarTours,n=Math.min(UI.calendarDays,T.daysBetween(T.FIRST_DATE,UI.calendarStart));UI.calendarStart=T.addDays(UI.calendarStart,-n);UI.calendarEnd=T.addDays(UI.calendarStart,UI.calendarDays-1);view();break;}case 'cal-next-window':{const T=window.NBACalendarTours,n=Math.min(UI.calendarDays,T.daysBetween(UI.calendarEnd,T.LAST_DATE));UI.calendarStart=T.addDays(UI.calendarStart,n);UI.calendarEnd=T.addDays(UI.calendarStart,UI.calendarDays-1);view();break;}case 'calculate-chains':calculateChains();break;case 'calculate-multi':calculateMulti();break;case 'calculate-budget':calculateBudget();break;case 'add-draft':addDraft();break;case 'preview-transfer':previewTransfer();break;case 'clear-draft':S.draft=[];save();view();break;case 'confirm-draft':confirmDraft();break;case 'refresh':remoteRefresh();break;case 'history-more':UI.histLimit=Math.min(10000,UI.histLimit+100);view();break;case 'retry-history':{const pid=UI.playerId||S.roster[0];if(HISTORY_INDEX){const file=HISTORY_INDEX.player_shards?.[pid];if(file)HISTORY_SHARD_ERRORS.delete(file);scheduleHistory(pid);}else loadAux();break;}case 'export-state':download('nba-season-lab-backup.json',S);break;case 'set-cash':{const val=num(document.getElementById('cash')?.value);if(!Number.isFinite(val)||val<0)return showMsg('Некорректная касса');S.cash=val;save();view();break;}}});
document.getElementById('navigation').addEventListener('click',e=>{const b=e.target.closest('button[data-tab]');if(b)setTab(b.dataset.tab);});
document.addEventListener('change',e=>{const el=e.target;if(!el)return;
 if(el.id==='feedfile'&&el.files?.[0])return upload(el.files[0],'feed');if(el.id==='backupfile'&&el.files?.[0])return upload(el.files[0],'backup');
 if(el.id==='medical'){S.medical[el.dataset.id]=el.value;save();view();return;}
 if(el.classList.contains('teamedit')){if(!S.teamOverrides)S.teamOverrides={};if(el.value==='auto')delete S.teamOverrides[el.dataset.teamId];else if(CLUBS[el.value])S.teamOverrides[el.dataset.teamId]=el.value;save();view();return;}
 if(el.classList.contains('priceedit')){const v=num(el.value);if(Number.isFinite(v)&&v>=0)S.prices[el.dataset.priceId]=v;save();view();return;}
 if(el.id==='hist-player'){UI.playerId=el.value;UI.histSeason='all';UI.histOpponent='all';UI.histLimit=25;view();return;}if(el.id==='hist-season'){UI.histSeason=el.value;UI.histLimit=25;view();return;}if(el.id==='hist-opponent'){UI.histOpponent=el.value;UI.histLimit=25;view();return;}if(el.id==='hist-limit'){UI.histLimit=Number(el.value);view();return;}if(el.id==='pos'){UI.position=el.value;view();return;}if(el.id==='club'){UI.club=el.value;view();return;}if(el.id==='sort'){UI.sort=el.value;view();return;}if(el.id==='window'){UI.window=Number(el.value);view();return;}
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
let searchTimer;document.addEventListener('input',e=>{if(e.target.id==='search'){UI.search=e.target.value;clearTimeout(searchTimer);searchTimer=setTimeout(()=>{const field=document.activeElement===e.target;const cursor=e.target.selectionStart;view();const n=document.getElementById('search');if(field&&n){n.focus();n.setSelectionRange(cursor,cursor);}},180);}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&MODAL){MODAL=null;renderModal();}});
window.PythosNBA={base:BASE,getState:()=>JSON.parse(JSON.stringify(S)),getFeed:()=>LIVE,getFeedSource:()=>liveSource,getFeedError:()=>onlineError,validateFeed:checkPublicFeed,refreshFeed:loadFeed,score:(s,home,win)=>{const minutes=Number(s.min)||0;if(!minutes)return 0;return s.pts+s.reb+s.ast+s.stl+s.blk+s.fgm+s.ftm-s.fga-s.fta-s.pf-2*s.tov+(minutes>=10?2:1)+(win?(home?2:3):(home?-3:-2));},check:hardCheck,planCheck:planResult,setState:x=>{S=x;save();view();},updateFeed:x=>{LIVE=x;view();},preview:plannedMean,planWorlds,modelSignal:id=>validatedModelSignal(P[id]),estimate:(id,g)=>learnedMean(P[id],g),modelReport:()=>MODEL_V2};


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

function newsPage(){const arr=(TG_NEWS?.events||[]).slice().sort((a,b)=>Date.parse(b.published_at||0)-Date.parse(a.published_at||0));const mine=arr.filter(a=>(a.player_ids||[]).some(id=>S.roster.includes(id)));
 const age=TG_NEWS?.updated_at_utc?(Date.now()-Date.parse(TG_NEWS.updated_at_utc))/3600000:Infinity;
 const status=TG_NEWS?.status==='public_preview_unverified'?(age>12?'Последняя проверка более 12 часов назад':'Последняя проверка выполнена'):'Автоматическая загрузка не подтверждена';
 const stat={out:'Сообщают: не сыграет',doubtful:'Под большим вопросом',questionable:'Участие под вопросом',probable:'Вероятно сыграет',available:'Сообщают: доступен',injury_update:'Сообщение о состоянии'};
 const card=n=>`<div class="lined"><div class="horizontal"><b>${(n.player_ids||[]).map(id=>esc(P[id]?.name||id)).join(', ')}</b><span class="pill ${['out','doubtful'].includes(n.status)?'bad':n.status==='available'?'good':'warn'}">${esc(stat[n.status]||'Сообщение')}</span></div><div class="small">${esc(n.published_at?dateText(Date.parse(n.published_at)):'Дата неизвестна')} · Telegram · не подтверждено</div><p>${esc(n.text)}</p><a href="${esc(n.url||'https://t.me/s/nba_injurynews')}" target="_blank" rel="noopener noreferrer">Открыть исходный пост</a></div>`;
 const official=officialForRoster();const q=window.NBAOfficialStatus?.validate(OFFICIAL_FEED);
 const officialBlock=`<div class="card"><div class="titledetail"><h2>Официальный injury report · мой состав</h2><span class="pill">${official.length} сопоставлено</span></div><p class="small">${esc(OFFICIAL_STATUS)}. Статусы относятся только к конкретным ближайшим матчам. Доступность остальных игроков неизвестна.</p>${official.length?official.map(officialCard).join(''):'<div class="empty">Официальных сопоставленных статусов на ближайшие 72 часа нет. Это НЕ подтверждение выхода.</div>'}</div>`;
 return header('Новости','Травмы и участие','Официальные NBA Injury Reports и неофициальный Telegram — отдельно. Прогноз FP не изменяется автоматически.')+officialBlock+
 `<div class="card"><div class="horizontal" style="justify-content:space-between"><div><b>${esc(status)}</b><div class="small">${TG_NEWS?.updated_at_utc?esc(dateText(Date.parse(TG_NEWS.updated_at_utc))):'Загрузка не выполнена'} · ${round(arr.length)} сопоставленных сообщений</div></div><a href="https://t.me/s/nba_injurynews" target="_blank" rel="noopener noreferrer">Открыть канал</a></div><p class="small">Сообщения не меняют прогноз участия автоматически. Перед трансфером проверь официальный injury report и дату публикации.</p></div>`+
 `<div class="grid columns"><div class="card"><h2>Новости о моих игроках · ${mine.length}</h2>${mine.length?mine.slice(0,40).map(card).join(''):'<div class="empty">По вашим 10 игрокам в последних доступных публикациях нет сопоставленных новостей. Это не означает, что все здоровы.</div>'}</div><div class="card"><h2>Новости об остальных игроках · ${arr.length-mine.length}</h2>${arr.filter(x=>!mine.includes(x)).slice(0,35).map(card).join('')||'<div class="empty">Пока нет данных.</div>'}<div class="info">Источник вторичный; неполный доступ к публичному каналу будет показан как отсутствие обновлений, а не как отсутствие травм.</div></div></div>`;
}

function accountPage(){const st=window.NBA_CLOUD_STATUS||{state:'local',label:'Облачная настройка не загружена'};
 return header('Мой профиль','Сохранение и доступ','Каждый пользователь хранит свою десятку, бюджет и подтверждённые замены отдельно.')+
 `<div class="grid columns"><div class="card"><h2>${esc(st.label||st.state)}</h2>${st.user?`<p>Аккаунт: <b>${esc(st.user)}</b></p><button class="button" data-cloud="logout">Выйти</button>`:st.state==='unconfigured'?`<p>Облачная синхронизация не подключена. Весь инструмент уже работает в локальном режиме. Для публикации владелец проекта должен подключить Firebase.</p>`:`<div class="formgrid"><label>Email<input id="cloud-email" type="email" placeholder="email@example.com" autocomplete="email"></label><label>Пароль<input id="cloud-password" type="password" autocomplete="current-password" minlength="8"></label></div><div class="toolbar" style="margin-top:14px"><button class="primary" data-cloud="login">Войти</button><button class="button" data-cloud="signup">Создать профиль</button></div>`}<p class="small">Облачный сервис не меняет состав на Sports.ru. Перед выходом из аккаунта экспортируйте резервную копию, если есть несохранённые изменения.</p></div><div class="card"><h2>Мои данные</h2><div class="donut"><span>Текущий состав</span><b>${S.roster.length} / 10</b></div><div class="donut"><span>Подтверждённые замены</span><b>${S.executed.length}</b></div><button class="button" data-action="export-state">Скачать резервную копию</button><button class="button" data-action="reset-roster" style="margin-left:8px">Создать новую десятку</button><p class="small">Firebase использует отдельный документ для каждого UID. Правила Firestore запрещают пользователям доступ к чужим профилям.</p></div></div>`;
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
 OFFICIAL_FEED=payload;
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
