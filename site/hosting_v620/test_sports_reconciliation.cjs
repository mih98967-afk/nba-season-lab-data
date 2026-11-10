const assert=require('node:assert/strict');
const {compare,parseNumber}=require('./sports_reconciliation.js');
const guard=require('./transfer_guard.js');
const now=Date.parse('2026-11-02T09:00:00Z');
const service={calculatedNBAFP:691,initialRosterCount:10,cash:100,executed:[],
 feedUpdatedAtUtc:'2026-11-02T08:00:00Z'};
const input={owner:{fp:'686',cash:'99',remaining:'3',confirmedNow:true},
 service,nowEpoch:now,weekKey:guard.weekKey};
let x=compare(input);
assert.equal(x.valid,true);
assert.equal(x.checks.fp.difference,5);
assert.equal(x.checks.cash.difference,1);
assert.equal(x.checks.quota.kind,'AGREES_BOTH_UNVERIFIED');
assert.equal(x.verifiedSportsData,false);
assert.equal(x.readOnly,true);
assert.equal(x.checks.quota.resetRuleIndependentlyVerified,false);
assert.equal(compare({...input,owner:{...input.owner,fp:''}}).checks.fp,undefined);
assert.equal(compare({...input,owner:{...input.owner,fp:'0'}}).checks.fp.owner,0);
assert.equal(compare({...input,owner:{...input.owner,cash:'0'}}).checks.cash.owner,0);
assert.equal(compare({...input,owner:{fp:'',cash:'',remaining:'',confirmedNow:true}}).valid,false);
assert.equal(compare({...input,owner:{...input.owner,confirmedNow:false}}).valid,false);
assert.equal(compare({...input,owner:{...input.owner,remaining:'3.5'}}).valid,false);
assert.equal(compare({...input,owner:{...input.owner,fp:'NaN'}}).valid,false);
assert.equal(compare({...input,service:{...service,initialRosterCount:0}}).checks.fp.kind,'LOCAL_SCORE_UNAVAILABLE');
assert.equal(compare({...input,service:{...service,feedUpdatedAtUtc:'2026-10-31T00:00:00Z'}}).checks.fp.kind,'STALE_OR_UNDATED_NBA_FEED');
assert.equal(compare({...input,service:{...service,executed:null}}).checks.quota.kind,'LOCAL_LEDGER_UNVERIFIED');
assert.equal(compare({...input,service:{...service,executed:[{epoch:now+60000}]}}).checks.quota.kind,'LOCAL_LEDGER_UNVERIFIED');
assert.equal(parseNumber('2 821',0,5000),2821);
assert.equal(parseNumber('2\u00a0821',0,5000),2821);
assert.equal(parseNumber('2,5',0,5000),2.5);
assert.equal(parseNumber('',0,5000),null);
assert.equal(parseNumber('Infinity',0,5000),null);
const moves=['2026-10-30T09:00:00Z','2026-10-31T09:00:00Z','2026-11-01T09:00:00Z','2026-11-02T07:00:00Z'].map(x=>({epoch:Date.parse(x)}));
x=compare({...input,owner:{fp:'',cash:'',remaining:'2',confirmedNow:true},service:{...service,executed:moves}});
assert.equal(x.checks.quota.kind,'AGREES_00_ONLY_UNVERIFIED');
assert.equal(x.checks.quota.used15,4);
assert.equal(x.checks.quota.used00,1);
assert.equal(x.checks.quota.localRemaining15,null);
assert.equal(x.checks.quota.localRemaining00,2);
assert.equal(compare({...input,owner:{fp:'',cash:'',remaining:'0',confirmedNow:true},service:{...service,executed:moves}}).checks.quota.kind,'AGREES_NEITHER');
console.log('sports reconciliation: read-only checks passed');

// Missing FP and duplicated owned player-games cannot become a valid season total.
const {audit}=require('./score_audit.js');
const gameEpoch=Date.parse('2026-11-01T23:00:00Z');
const state={initialRoster:['owner-p',...Array.from({length:9},(_,i)=>'filler'+i)],initialEpoch:gameEpoch-86400000,executed:[]};
const fixture={mode:'live_sync',games:[{id:'g1',epoch:gameEpoch,status:'final',et_date:'2026-11-01'}],
 rows:[{id:'owner-p',game_id:'g1',played:true,fp:0}]};
let summary=audit(fixture,state,{sourceVerified:true});
assert.equal(summary.complete,true);
assert.equal(summary.fp,0,'An actual zero FP must remain a valid zero');
summary=audit({...fixture,rows:[{...fixture.rows[0],fp:-2}]},state,{sourceVerified:true});
assert.equal(summary.complete,true);
assert.equal(summary.fp,-2,'Negative actual FP are legitimate');
for(const invalid of [null,undefined,'',' ',NaN,'unknown']){
 summary=audit({...fixture,rows:[{...fixture.rows[0],fp:invalid}]},state,{sourceVerified:true});
 assert.equal(summary.complete,false,'Missing FP must fail closed: '+String(invalid));
 assert.equal(Number.isFinite(summary.fp),false);
 assert.equal(Number.isFinite(summary.earlierETFP),false);
}
summary=audit({...fixture,rows:[fixture.rows[0],{...fixture.rows[0]}]},state,{sourceVerified:true});
assert.equal(summary.complete,false,'Duplicate ownership row invalidates total');
assert.equal(Number.isFinite(summary.fp),false);
summary=audit({...fixture,rows:[fixture.rows[0],{id:'not-owned',game_id:'g1',played:true,fp:null}]},state,{sourceVerified:true});
assert.equal(summary.complete,true,'Unowned players do not affect private total');
assert.equal(summary.fp,0);
assert.equal(compare({...input,service:{...service,calculatedNBAFP:NaN}}).checks.fp.kind,'LOCAL_SCORE_UNAVAILABLE');


// Full historical FP cannot be asserted from a seed, missing ownership or a broken ledger.
summary=audit(fixture,state);
assert.equal(summary.complete,false,'Unverified source never produces an apparently exact FP total');
assert.equal(summary.sourceReady,false);
summary=audit({...fixture,mode:'schedule_sync_only'},state,{sourceVerified:true});
assert.equal(summary.complete,false);
summary=audit(fixture,{...state,initialRoster:[]},{sourceVerified:true});
assert.equal(summary.complete,false,'Missing initial 10 must not appear as valid zero FP');
assert.equal(summary.ownershipReady,false);
summary=audit(fixture,{...state,executed:[{epoch:null,out:'owner-p',in_:'replacement'}]},{sourceVerified:true});
assert.equal(summary.complete,false,'Unknown transfer timestamp invalidates historical attribution');
summary=audit(fixture,{...state,executed:[{epoch:gameEpoch-1000,out:'wrong-owner',in_:'replacement'}]},{sourceVerified:true});
assert.equal(summary.complete,false,'Impossible transfer OUT invalidates lineage');
summary=audit(fixture,{...state,executed:[{epoch:gameEpoch+1000,out:'owner-p',in_:'replacement'}],roster:state.initialRoster},{sourceVerified:true});
assert.equal(summary.complete,false,'Final roster must match replayed ownership');
summary=audit(fixture,{...state,executed:[{epoch:gameEpoch+1000,out:'owner-p',in_:'replacement'}],roster:['replacement',...state.initialRoster.slice(1)]},{sourceVerified:true});
assert.equal(summary.complete,true,'Valid completed move after match does not corrupt historical FP');
assert.equal(summary.fp,0);
