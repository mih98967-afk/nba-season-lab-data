const test=require('node:test');
const assert=require('node:assert/strict');
const {group}=require('./team_court.js');
const pos=['PG','PG','SG','SG','SF','SF','PF','PF','C','C'];
const ids=pos.map((p,i)=>'n'+(101+i));
const players=Object.fromEntries(ids.map((id,i)=>[id,{pos:pos[i]}]));
test('valid 10 positions split into two complete quintets without bench',()=>{
 const before=JSON.stringify(ids),out=group(ids,players);
 assert.equal(out.valid,true);
 assert.equal(out.quintets.length,2);
 assert.deepEqual(out.quintets[0].map(x=>x.pos),['PG','SG','SF','PF','C']);
 assert.deepEqual(out.quintets[1].map(x=>x.pos),['PG','SG','SF','PF','C']);
 assert.deepEqual(out.quintets.flat().map(x=>x.playerId).sort(),[...ids].sort());
 assert.equal(out.represents_substitutions,false);
 assert.equal(JSON.stringify(ids),before);
});
test('bad position distribution must not fabricate a second SF',()=>{
 const copy={...players,n106:{pos:'SG'}};
 const out=group(ids,copy);
 assert.equal(out.valid,false);
 assert.ok(out.issues.includes('POSITION_COUNT_SF'));
 assert.equal(out.byPosition.SF.length,1);
 assert.equal(out.quintets[1].find(x=>x.pos==='SF').playerId,null);
});
test('missing and duplicate players explicitly invalidate the visual grouping',()=>{
 assert.equal(group(ids.slice(0,9),players).valid,false);
 assert.ok(group([...ids.slice(0,9),ids[0]],players).issues.includes('DUPLICATE_PLAYER'));
});
