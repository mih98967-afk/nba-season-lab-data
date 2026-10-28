"""Research-only evaluation of frozen, genuinely prelock short-minute risk."""
import json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from math import log,log1p,isfinite
from random import Random
from zoneinfo import ZoneInfo
from src.sync import DATA
from src.rolling_decision_research import canonical_hash,instant,stamp
STATUS="research_only_not_deployed"
ET = ZoneInfo("America/New_York")
# Preregistered BEFORE the first 2026/27 short-minute prospective game is scored.
# These are exploratory screening floors, not model-adoption thresholds.
MIN_ET_DATES = 8
MIN_PLAYED = 100
MIN_GAMES = 24
RESAMPLES = 2000
SEED = 20261028

def date_cluster_paired_uncertainty(rows, seed=SEED, draws=RESAMPLES):
    """Paired global-minus-group gain; resample whole ET dates, not athletes.

    None means the genuinely post-lock, played-only cohort is too immature.
    A non-None interval is still exploratory selected-cohort evidence.
    """
    if type(seed) is not int or type(draws) is not int or draws < 200:
        raise ValueError("Invalid preregistered resampling settings")
    by_date = defaultdict(list)
    games = set()
    keys = set()
    for r in rows:
        key = (r.get("game_id"), r.get("player_id"))
        et_date = r.get("ET_date")
        if not all(isinstance(v, str) and v for v in (*key, et_date)) or key in keys:
            raise ValueError("Bad/duplicate prospective short-minute player-game")
        datetime.fromisoformat(et_date).date()
        values = [r.get(k) for k in ("bg", "bp", "lg", "lp")]
        if any(type(v) not in (int,float) or not isfinite(v) or v < 0 for v in values):
            raise ValueError("Invalid prospective short-minute loss")
        keys.add(key)
        games.add(key[0])
        by_date[et_date].append((values[0]-values[1], values[2]-values[3]))
    if (len(by_date) < MIN_ET_DATES or len(rows) < MIN_PLAYED
            or len(games) < MIN_GAMES):
        return None
    cohorts = [by_date[k] for k in sorted(by_date)]
    rng = Random(seed)
    brier_samples = []
    logloss_samples = []
    for _ in range(draws):
        sampled = [x for _ in cohorts for x in cohorts[rng.randrange(len(cohorts))]]
        count = len(sampled)
        brier_samples.append(sum(x[0] for x in sampled)/count)
        logloss_samples.append(sum(x[1] for x in sampled)/count)
    brier_samples.sort()
    logloss_samples.sort()
    def quantile(sorted_values, p):
        x = (len(sorted_values)-1)*p
        low = int(x)
        high = min(low+1,len(sorted_values)-1)
        return round(sorted_values[low]*(high-x)+sorted_values[high]*(x-low),6)
    return {
        "resampling_unit":"NBA_ET_date_with_all_verified_played_player_games",
        "fixed_seed":seed,"resamples":draws,
        "independent_ET_dates":len(cohorts),
        "distinct_NBA_games":len(games),
        "scored_played_player_games":len(rows),
        "paired_global_minus_group_Brier_gain_95pct_exploratory": [
            quantile(brier_samples,0.025),quantile(brier_samples,0.975)],
        "paired_global_minus_group_logloss_gain_95pct_exploratory": [
            quantile(logloss_samples,0.025),quantile(logloss_samples,0.975)],
        "positive_gain_favors_group_model":True,
        "descriptive_bootstrap_not_confirmatory_inference":True,
        "not_population_or_transfer_value_evidence":True,
    }

def unique(rows):
 d={}
 for x in rows:
  k=(x["game_id"],x["player_id"])
  if k in d:raise ValueError("Duplicate player-game")
  d[k]=x
 return d
def score(rows):
 if not rows:return {"n":0,"Brier_global":None,"Brier_group":None,"logloss_global":None,"logloss_group":None,"band_coverage_global":None,"band_coverage_group":None,"actual_under_10":0,"paired_global_minus_group_Brier_gain":None,"paired_global_minus_group_logloss_gain":None}
 def avg(k):return round(sum(x[k] for x in rows)/len(rows),6)
 return {"n":len(rows),"Brier_global":avg("bg"),"Brier_group":avg("bp"),"logloss_global":avg("lg"),"logloss_group":avg("lp"),"band_coverage_global":avg("cg"),"band_coverage_group":avg("cp"),"actual_under_10":sum(x["y"] for x in rows),"paired_global_minus_group_Brier_gain":round(sum(x["bg"]-x["bp"] for x in rows)/len(rows),6),"paired_global_minus_group_logloss_gain":round(sum(x["lg"]-x["lp"] for x in rows)/len(rows),6)}
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
  if (r.get("short_actual_minutes_threshold")!=10.0
      or r.get("minutes_first_issued_at_utc")!=o["issued_at_utc"]
      or r.get("p_play_first_issued_at_utc")!=o["p_play_first_issued_at_utc"]
      or r.get("dev_only_model_sha256")!=risk["dev_only_model_sha256"]
      or r.get("development_year")!="2024/25"
      or r.get("observed_minutes_used_as_feature") is not False
      or r.get("game_day_roster_verified") is not False
      or r.get("new_historical_holdout_unseen") is not False):
   raise ValueError("Short-minute prelock target/provenance changed")
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
  entry={"game_id":key[0],"player_id":key[1],"ET_date":tip.astimezone(ET).date().isoformat(),"y":y,"bg":(g-y)**2,"bp":(p-y)**2,
    "lg":-(y*log(g)+(1-y)*log1p(-g)),"lp":-(y*log(p)+(1-y)*log1p(-p)),
    "cg":int(r["global_dev_q90_minutes_band"][0]<=m<=r["global_dev_q90_minutes_band"][1]),
    "cp":int(r["group_dev_q90_minutes_band"][0]<=m<=r["group_dev_q90_minutes_band"][1])}
  result.append(entry);dates[tip.astimezone(ZoneInfo("America/New_York")).date().isoformat()].append(entry);roles[r["preissue_predicted_minutes_group"]].append(entry)
 if sum(counts.values())!=len(issued):raise ValueError("Missing results")
 n_dates=len(dates); n_games=len({x["game_id"] for x in result})
 enough_dates=n_dates>=MIN_ET_DATES
 enough_cases=len(result)>=MIN_PLAYED
 enough_games=n_games>=MIN_GAMES
 exploratory= enough_dates and enough_cases and enough_games
 uncertainty=date_cluster_paired_uncertainty(result)
 if (uncertainty is not None)!=exploratory:raise ValueError("ET-date eligibility drift")
 return {"schema_version":1,"status":STATUS,"adopt_on_site":False,"updated_at_utc":stamp(now),
  "target":"short_minutes_given_verified_positive_minutes_only",
  "summary":{"issued":len(issued),"played_verified":counts["played"],"explicit_DNP_excluded":counts["explicit_DNP"],"UNKNOWN_not_imputed":counts["UNKNOWN"],"awaiting_or_unchecked":counts["awaiting_or_unchecked"],"distinct_ET_dates_scored":n_dates,"distinct_NBA_games_scored":n_games},
  "conditional_played_only_metrics":score(result),"by_ET_date":{k:score(v) for k,v in sorted(dates.items())},"by_predicted_minutes":{k:score(v) for k,v in sorted(roles.items())},"outcome_audit":audit,
  "precommitted_exploratory_date_cluster_gates":{"min_independent_ET_dates":MIN_ET_DATES,"min_verified_played_player_games":MIN_PLAYED,"min_distinct_NBA_games":MIN_GAMES,"date_gate":enough_dates,"played_gate":enough_cases,"games_gate":enough_games,"interval_eligible":exploratory},
  "paired_global_minus_group_uncertainty_if_eligible":uncertainty,
  "quality_gate":{"at_least_8_independent_ET_dates":enough_dates,"at_least_100_verified_played":enough_cases,"at_least_24_NBA_games":enough_games,"DNP_scored_as_zero":False,"UNKNOWN_imputed":False,"full_population_calibration_proven":False,"unconditional_FP_allowed":False,"KEEP_TRANSFER_gain_proven":False,"adopt_on_site":False},
  "limitations":["No FP or minutes scoring for DNP and unlisted UNKNOWN","No retrospective backfill and no new prediction fitting","Date-cluster uncertainty uses whole NBA ET dates, never player rows as independent units","Screening floors are not adoption criteria; even positive exploratory gain cannot prove whole-population calibration","Not P(play); no site, Firestore, roster, price or automatic transfers"]}
def run():
 read=lambda name:json.loads((DATA/name).read_text(encoding="utf8"))
 j=build(read("short_minutes_prospective_research.json"),read("conditional_minutes_fp_research.json"),read("conditional_minutes_fp_evaluation_research.json"),datetime.now(timezone.utc))
 path=DATA/"short_minutes_prospective_evaluation_research.json"
 old=read(path.name) if path.exists() else {}
 if not old or {k:v for k,v in j.items() if k!="updated_at_utc"}!={k:v for k,v in old.items() if k!="updated_at_utc"}:
  tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(j,ensure_ascii=False,indent=2),encoding="utf8");tmp.replace(path)
 return j["summary"]
if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False,indent=2))
