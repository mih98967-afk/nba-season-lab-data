"""Research-only evaluation of frozen, genuinely prelock short-minute risk."""
import json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from math import log,log1p
from zoneinfo import ZoneInfo
from src.sync import DATA
from src.rolling_decision_research import canonical_hash,instant,stamp
STATUS="research_only_not_deployed"
def unique(rows):
 d={}
 for x in rows:
  k=(x["game_id"],x["player_id"])
  if k in d:raise ValueError("Duplicate player-game")
  d[k]=x
 return d
def score(rows):
 if not rows:return {"n":0,"Brier_global":None,"Brier_group":None,"logloss_global":None,"logloss_group":None,"band_coverage_global":None,"band_coverage_group":None}
 def avg(k):return round(sum(x[k] for x in rows)/len(rows),6)
 return {"n":len(rows),"Brier_global":avg("bg"),"Brier_group":avg("bp"),"logloss_global":avg("lg"),"logloss_group":avg("lp"),"band_coverage_global":avg("cg"),"band_coverage_group":avg("cp"),"actual_under_10":sum(x["y"] for x in rows)}
def build(risk,minutes,evaluation,now):
 if now.utcoffset() is None:raise ValueError("Naive clock")
 for x in (risk,minutes,evaluation):
  if x.get("schema_version")!=1 or x.get("status")!=STATUS or x.get("adopt_on_site") is not False:raise ValueError("Research source invalid")
 original=unique(minutes["issued"]); issued=unique(risk["issued"])
 played=unique(evaluation["scored_played"]); dnp=unique(evaluation["explicit_DNP_not_in_conditional_metrics"]); unknown=unique(evaluation["UNKNOWN_unscored"])
 if (len(issued)!=risk["issued_total"] or len(played)!=evaluation["summary"]["played"] or
     len(dnp)!=evaluation["summary"]["explicit_DNP_not_scored"] or
     len(unknown)!=evaluation["summary"]["UNKNOWN_not_imputed"] or
     set(played)&set(dnp) or set(played)&set(unknown) or set(dnp)&set(unknown)):raise ValueError("Evidence denominator drift")
 result=[];audit=[];counts=Counter();dates=defaultdict(list);roles=defaultdict(list)
 for key,r in sorted(issued.items()):
  o=original.get(key)
  if o is None or r["minutes_source_issue_sha256"]!=canonical_hash(o):raise ValueError("First issue changed")
  tip=instant(r["game_utc"]);lock=instant(r["individual_lock_utc"]);first=instant(r["risk_first_issued_at_utc"])
  if (not instant(o["issued_at_utc"])<=first<lock<tip or (tip-lock).total_seconds()!=1800 or first>now or
      r["team"]!=o["team"] or r["conditional_predicted_minutes"]!=o["min_if_play"] or
      r["outcome_at_first_issue"]!="UNKNOWN" or r["model_training_negative"] is not False or
      r["adopt_on_site"] is not False or r["p_play_probability_multiplied"] is not False):raise ValueError("Illegal retrospective risk")
  g=r["global_dev_short_given_played_probability"];p=r["group_dev_short_given_played_probability"]
  if not all(type(x) in (int,float) and 0<x<1 for x in (g,p)):raise ValueError("Invalid risk")
  for k in ("global_dev_q90_minutes_band","group_dev_q90_minutes_band"):
   bounds=r[k]
   if not isinstance(bounds,list) or len(bounds)!=2 or bounds[0]>bounds[1]:raise ValueError("Invalid band")
  label=("played" if key in played else "explicit_DNP" if key in dnp else "UNKNOWN" if key in unknown else "awaiting_or_unchecked")
  counts[label]+=1
  audit.append({"game_id":key[0],"player_id":key[1],"outcome":label})
  if label!="played":continue
  actual=played[key]
  if actual["team"]!=r["team"] or actual["game_utc"]!=r["game_utc"] or not tip<=instant(actual["postgame_first_seen_at_utc"])<=now or actual["actual_minutes"]<=0:raise ValueError("Invalid played evidence")
  m=actual["actual_minutes"]; y=int(m<10)
  entry={"game_id":key[0],"player_id":key[1],"y":y,"bg":(g-y)**2,"bp":(p-y)**2,
    "lg":-(y*log(g)+(1-y)*log1p(-g)),"lp":-(y*log(p)+(1-y)*log1p(-p)),
    "cg":int(r["global_dev_q90_minutes_band"][0]<=m<=r["global_dev_q90_minutes_band"][1]),
    "cp":int(r["group_dev_q90_minutes_band"][0]<=m<=r["group_dev_q90_minutes_band"][1])}
  result.append(entry);dates[tip.astimezone(ZoneInfo("America/New_York")).date().isoformat()].append(entry);roles[r["preissue_predicted_minutes_group"]].append(entry)
 if sum(counts.values())!=len(issued):raise ValueError("Missing results")
 return {"schema_version":1,"status":STATUS,"adopt_on_site":False,"updated_at_utc":stamp(now),
  "target":"short_minutes_given_verified_positive_minutes_only",
  "summary":{"issued":len(issued),"played_verified":counts["played"],"explicit_DNP_excluded":counts["explicit_DNP"],"UNKNOWN_not_imputed":counts["UNKNOWN"],"awaiting_or_unchecked":counts["awaiting_or_unchecked"],"distinct_ET_dates_scored":len(dates)},
  "conditional_played_only_metrics":score(result),"by_ET_date":{k:score(v) for k,v in sorted(dates.items())},"by_predicted_minutes":{k:score(v) for k,v in sorted(roles.items())},"outcome_audit":audit,
  "quality_gate":{"at_least_8_independent_ET_dates":len(dates)>=8,"at_least_100_verified_played":len(result)>=100,"DNP_scored_as_zero":False,"UNKNOWN_imputed":False,"full_population_calibration_proven":False,"adopt_on_site":False},
  "limitations":["No FP or minutes scoring for DNP and unlisted UNKNOWN","No retrospective backfill and no new prediction fitting","Not P(play); no site, Firestore, roster, price or automatic transfers"]}
def run():
 read=lambda name:json.loads((DATA/name).read_text(encoding="utf8"))
 j=build(read("short_minutes_prospective_research.json"),read("conditional_minutes_fp_research.json"),read("conditional_minutes_fp_evaluation_research.json"),datetime.now(timezone.utc))
 path=DATA/"short_minutes_prospective_evaluation_research.json"
 old=read(path.name) if path.exists() else {}
 if not old or {k:v for k,v in j.items() if k!="updated_at_utc"}!={k:v for k,v in old.items() if k!="updated_at_utc"}:
  tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(j,ensure_ascii=False,indent=2),encoding="utf8");tmp.replace(path)
 return j["summary"]
if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False,indent=2))
