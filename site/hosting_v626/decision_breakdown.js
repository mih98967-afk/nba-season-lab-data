/* NBA Season Lab v6.16: read-only, reconciled counterfactual explanation.
 * Explains MODEL FP only, never actual credited Sports.ru points or a guaranteed gain.
 * A missing player forecast, missing schedule or inconsistent total fails closed.
 */
(function(root,factory){
 'use strict';
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 root.NBADecisionBreakdown=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const finite=v=>typeof v==='number'&&Number.isFinite(v);
 const fail=(code)=>({ready:false,code,kind:'not_verified'});
 const EPS=1e-6;
 const close=(a,b)=>finite(a)&&finite(b)&&Math.abs(a-b)<=EPS+1e-8*Math.max(Math.abs(a),Math.abs(b));
 const isId=id=>typeof id==='string'&&id.length>0;
 const unique=ids=>new Set(ids).size===ids.length;
 const normalizeMoves=items=>{
  if(!Array.isArray(items))return null;
  const result=[];
  for(let i=0;i<items.length;i++){
   const x=items[i];
   if(!x||!isId(x.out)||!isId(x.in_)||x.out===x.in_||!finite(x.epoch))return null;
   result.push({...x,_order:i});
  }
  return result.sort((a,b)=>a.epoch-b.epoch||a._order-b._order);
 };
 function ownedAt(initial,moves,lockEpoch){
  const ids=initial.slice();
  for(const x of moves){
   if(x.epoch>lockEpoch)break;
   const at=ids.indexOf(x.out);
   if(at<0||ids.includes(x.in_))return null;
   ids[at]=x.in_;
  }
  return ids;
 }
 function build(args){
  const o=args||{},route=o.route||{};
  const {baseRoster,existingDraft=[],start,end,games,players,scorePlayer,project}=o;
  const lockOffsetMs=o.lockOffsetMs===undefined?1800000:o.lockOffsetMs;
  if(!Array.isArray(baseRoster)||baseRoster.length!==10||!baseRoster.every(isId)||!unique(baseRoster)||
    !finite(start)||!finite(end)||end<=start||!Array.isArray(games)||!players||
    typeof scorePlayer!=='function'||typeof project!=='function'||
    !finite(lockOffsetMs)||lockOffsetMs<0||lockOffsetMs>86400000)return fail('INVALID_INPUT');
  if(!Array.isArray(route.moves)||!finite(route.gain))return fail('INVALID_ROUTE');
  const baselineMoves=normalizeMoves(existingDraft);
  const addedMoves=normalizeMoves(route.moves);
  const plannedMoves=normalizeMoves([...existingDraft,...route.moves]);
  if(!baselineMoves||!addedMoves||!plannedMoves||
     route.moves.some(x=>x.epoch>end))return fail('INVALID_MOVES');
  if(!ownedAt(baseRoster,baselineMoves,Infinity)||!ownedAt(baseRoster,plannedMoves,Infinity))
    return fail('INVALID_ROSTER_TRANSITION');
  let projectedBaseline,projectedPlan;
  try{projectedBaseline=project(existingDraft,start,end);
      projectedPlan=project([...existingDraft,...route.moves],start,end);}
  catch{return fail('MISSING_PROJECTED_FP');}
  if(!finite(projectedBaseline)||!finite(projectedPlan))return fail('MISSING_PROJECTED_FP');
  if(!close(projectedPlan-projectedBaseline,route.gain))return fail('ROUTE_TOTAL_MISMATCH');
  if(finite(o.baselineFP)&&!close(projectedBaseline,o.baselineFP))return fail('BASELINE_MISMATCH');
  const penalty=o.opportunityPenalty;
  if(finite(route.net)&&finite(penalty)&&
     !close(route.net,route.gain-penalty*route.moves.length))return fail('NET_MISMATCH');
  const sorted=games.filter(g=>g&&g.status!=='final'&&finite(g.epoch)&&g.epoch>=start&&g.epoch<end)
    .sort((a,b)=>a.epoch-b.epoch||String(a.id||'').localeCompare(String(b.id||'')));
  const seen=new Set();
  const effects=new Map();
  const changedGames=[];
  let sum=0;
  for(const g of sorted){
   if(!isId(g.home)||!isId(g.away)||g.home===g.away)return fail('INVALID_GAME');
   const gameKey=g.epoch+'|'+[g.home,g.away].sort().join('|');
   if(seen.has(gameKey))return fail('DUPLICATE_GAME');
   seen.add(gameKey);
   const cutoff=g.epoch-lockOffsetMs;
   const base=ownedAt(baseRoster,baselineMoves,cutoff);
   const plan=ownedAt(baseRoster,plannedMoves,cutoff);
   if(!base||!plan||!unique(base)||!unique(plan))return fail('INVALID_ROSTER_TRANSITION');
   const b=new Set(base),p=new Set(plan);
   const onlyIn=[...p].filter(id=>!b.has(id));
   const onlyOut=[...b].filter(id=>!p.has(id));
   const details=[];
   let delta=0;
   for(const [ids,sign] of [[onlyIn,1],[onlyOut,-1]]){
    for(const id of ids){
     const player=players[id];
     if(!player||!isId(player.team))return fail('MISSING_PLAYER');
     // Difference in games that do not involve the swapped player is zero.
     if(player.team!==g.home&&player.team!==g.away)continue;
     if(player.forecast!==true)return fail('MISSING_FORECAST');
     let fp;
     try{fp=scorePlayer(id,g.epoch,g.epoch+1);}
     catch{return fail('MISSING_GAME_FP');}
     if(!finite(fp))return fail('MISSING_GAME_FP');
     const effect=sign*fp;
     delta+=effect;
     const old=effects.get(id)||{id,intoFP:0,outFP:0,intoGames:0,outGames:0};
     if(sign===1){old.intoFP+=fp;old.intoGames++;}
     else{old.outFP+=fp;old.outGames++;}
     effects.set(id,old);
     details.push({id,sign,fp});
    }
   }
   if(details.length){
    changedGames.push({id:isId(g.id)?g.id:gameKey,epoch:g.epoch,
      home:g.home,away:g.away,deltaFP:delta,details});
    sum+=delta;
   }
  }
  if(!close(sum,route.gain))return fail('GAME_SUM_MISMATCH');
  let incoming=0,outgoing=0;
  for(const x of effects.values()){incoming+=x.intoFP;outgoing+=x.outFP;}
  if(!close(incoming-outgoing,sum))return fail('PLAYER_SUM_MISMATCH');
  const playersOut=[...effects.values()].filter(x=>x.outGames).sort((a,b)=>b.outFP-a.outFP);
  const playersIn=[...effects.values()].filter(x=>x.intoGames).sort((a,b)=>b.intoFP-a.intoFP);
  return {ready:true,kind:'reconciled_model_scenario_not_actual',
    baselineFP:projectedBaseline,plannedFP:projectedPlan,gainFP:sum,
    expectedIncomingFP:incoming,foregoneOutgoingFP:outgoing,
    heuristicNetFP:finite(route.net)?route.net:null,
    gamesConsidered:sorted.length,gamesChanged:changedGames.length,
    playersIn,playersOut,changedGames,
    caveat:'Scenario forecasts, not verified Sports.ru gains. Same fixed prices, model and lock assumptions as the planner.'};
 }
 return {build};
});
