/* NBA Season Lab v6.14 — positional visual grouping only.
 * Two rows of five are a drawing convention, NOT starter/bench status.
 * No user-state mutations, scoring, pricing or transfers.
 */
(function(root,factory){
 'use strict';
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 root.NBATeamCourtLayout=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const POSITIONS=['PG','SG','SF','PF','C'];
 function group(roster,players){
  const issues=[];
  if(!Array.isArray(roster)||roster.length!==10)issues.push('TEN_PLAYERS_REQUIRED');
  if(!Array.isArray(roster)||new Set(roster).size!==roster.length)issues.push('DUPLICATE_PLAYER');
  const byPosition={};
  for(const pos of POSITIONS){
   byPosition[pos]=(Array.isArray(roster)?roster:[]).filter(id=>players?.[id]?.pos===pos);
   if(byPosition[pos].length!==2)issues.push('POSITION_COUNT_'+pos);
  }
  const quintets=[0,1].map(i=>POSITIONS.map(pos=>({pos,playerId:byPosition[pos][i]||null})));
  return {valid:issues.length===0,issues,positions:[...POSITIONS],quintets,byPosition,
    represents_substitutions:false,view_only:true};
 }
 return {group,POSITIONS};
});
