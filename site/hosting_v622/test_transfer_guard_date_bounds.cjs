const assert=require('node:assert/strict');
const guard=require('./transfer_guard.js');
const day=(s)=>Date.parse(s);
const players={};
const positions=['PG','SG','SF','PF','C'];
const roster=Array.from({length:10},(_,i)=>'p'+i);
for(let i=0;i<10;i++)players['p'+i]={id:'p'+i,pos:positions[Math.floor(i/2)],team:'T'+i};
for(let i=0;i<5;i++)players['q'+i]={id:'q'+i,pos:positions[Math.floor(i/2)],team:'U'+i};
const mkMove=(i,when)=>({out:'p'+i,in_:'q'+i,sell:100,buy:100,epoch:day(when)});
const dateOnly=(date,placeholder)=>({timePrecision:'date_only',epochIsPlaceholder:true,
 sportsRuDateMoscow:date,epoch:day(placeholder)});
const input=(executed,draft,now)=>({players,roster,cash:100,executed,draft,games:[],
 nowEpoch:day(now),scheduleVerified:false});
{
 // A Monday date with unknown hours can belong to either weekly window.
 const m=dateOnly('2026-11-16','2026-11-16T21:00:00Z');
 const b=guard.historicalWeekBounds([m],day('2026-11-17T12:00:00Z'));
 assert.equal(b.min15['2026-11-09']||0,0);
 assert.equal(b.min15['2026-11-16']||0,0);
 assert.equal(b.max15['2026-11-09'],1);
 assert.equal(b.max15['2026-11-16'],1);
 assert.equal(b.min00['2026-11-16'],1);
}
{
 // The synthetic placeholder is an intentionally misleading next-week hour.
 const exec=[
 dateOnly('2026-11-16','2026-11-18T18:00:00Z'),
 {epoch:day('2026-11-17T10:00:00Z')},
 {epoch:day('2026-11-18T10:00:00Z')}
 ];
 const r=guard.validate(input(exec,[mkMove(0,'2026-11-19T10:00:00Z')],
 '2026-11-19T09:00:00Z'));
 assert.equal(r.valid,true,'Monday date-only transfer must not fabricate definitive over-quota');
 assert(r.warnings.some(w=>w.includes('Недостаточно данных о недельной квоте')));
 assert.equal(r.quotaUpperBounds.monday15['2026-11-16'],4);
 assert.equal(r.used['2026-11-16'],3);
}
{
 // Fully contained Wednesday transfers give exact counts under both resets.
 const exec=[{epoch:day('2026-11-17T10:00:00Z')},
 {epoch:day('2026-11-18T10:00:00Z')},{epoch:day('2026-11-19T08:00:00Z')}];
 const r=guard.validate(input(exec,[mkMove(0,'2026-11-19T10:00:00Z')],
 '2026-11-19T09:00:00Z'));
 assert.equal(r.valid,false);
 assert(r.errors.some(e=>e.includes('Превышены три замены')));
}
{
 // An old Monday ambiguity cannot contaminate a later fantasy week.
 const exec=[dateOnly('2026-11-02','2026-11-19T10:00:00Z')];
 const r=guard.validate(input(exec,[mkMove(0,'2026-11-19T10:00:00Z')],
 '2026-11-19T09:00:00Z'));
 assert.equal(r.valid,true);
 assert.equal(r.used['2026-11-16'],1);
}
{
 // Missing or future date is never converted into a fabricated timestamp.
 const b=guard.historicalWeekBounds([
 dateOnly('2026-11-25','2026-11-10T00:00:00Z'),
 dateOnly('garbage','2026-11-10T00:00:00Z')],
 day('2026-11-19T09:00:00Z'));
 assert.equal(b.invalid,2);
}
console.log('date-only quota bounds regression passed');
