const assert = require('node:assert/strict');
const { build } = require('./today_brief.js');
const known = {rosterCount:10,feedAgeHours:4,feedMode:'live',calendar7:true,calendar21:true,
 officialRiskNames:[],manualOutCount:0,telegramCount:0,fp7:179.3,fp21:515.9,games7:21,games21:69};
let a=build(known);assert.equal(a.state,'review');assert.equal(a.hasResults,false);assert.equal(a.shortFP,179.3);assert.equal(a.longFP,515.9);assert.equal(a.reasons.length,2);
a=build({...known,rosterCount:0});assert.equal(a.state,'onboarding');assert.equal(a.showForecast,false);
a=build({...known,feedMode:'seed'});assert.equal(a.state,'blocked');assert.equal(a.shortFP,null);
a=build({...known,feedAgeHours:28});assert.equal(a.state,'blocked');assert.equal(a.longFP,null);
a=build({...known,calendar21:false});assert.equal(a.state,'blocked');assert.equal(a.longFP,null);assert.equal(a.games21,null);
a=build({...known,fp7:NaN,fp21:Infinity});assert.equal(a.shortFP,null);assert.equal(a.longFP,null);
a=build({...known,officialRiskNames:['Игрок А']});assert.equal(a.state,'risk');assert.match(a.reasons[0],/Игрок А/);
a=build({...known,manualOutCount:1});assert.equal(a.state,'risk');
a=build({...known,telegramCount:2});assert.equal(a.state,'review');assert.match(a.reasons[0],/неофициальных/);
a=build({...known, resultFresh:true,bestExplanationVerified:true,bestRoute:{kind:'keep'}});assert.equal(a.state,'scenario');assert.equal(a.hasResults,true);assert.match(a.title,/сохранить/);
a=build({...known, resultFresh:true,bestExplanationVerified:false,bestRoute:{kind:'now'}});assert.equal(a.state,'review');
a=build({...known, resultFresh:true,bestExplanationVerified:true,bestRoute:{kind:'now'},officialRiskNames:['Игрок А']});assert.equal(a.state,'risk');
a=build({...known,feedAgeHours:-1,resultFresh:true,bestExplanationVerified:true,bestRoute:{kind:'now'}});assert.equal(a.state,'blocked');
console.log('PASS: user-first daily decision brief, risk and source gates');
