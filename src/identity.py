"""Conservative NBA player identity resolution for Sports.ru Russian roster.

Evidence order: stable NBA person ID, verified English name, complete FP sequence,
then multiple seasons of player-game counts, fantasy averages and team.
Never match solely on fuzzy surname or current (possibly changed) team.
"""
from __future__ import annotations

from collections import defaultdict, Counter
from difflib import SequenceMatcher
from statistics import fmean
import re
import unicodedata

RU2LAT={
"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"yo",
"ж":"zh","з":"z","и":"i","й":"y","к":"k","л":"l","м":"m",
"н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u",
"ф":"f","х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"shch",
"ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya"
}

def latin(text):
    raw=str(text or "").lower().replace("ё","е")
    raw="".join(RU2LAT.get(c,c) for c in raw)
    raw=unicodedata.normalize("NFKD",raw).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+"," ",raw).strip()

def canon(text):
    s=unicodedata.normalize("NFKD",str(text or "")).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+"," ",s).strip()

def similarity(ru,eng):
    a=latin(ru)
    b=canon(eng)
    if not a or not b:return 0.
    aa=a.split();bb=b.split()
    # Most fantasy Russian names are surnames; comparing entire full names is misleading.
    candidates=[b]
    for i in range(len(bb)):
        for j in range(i+1,min(len(bb)+1,i+4)):
            candidates.append(" ".join(bb[i:j]))
    def one(s,t):
        return SequenceMatcher(None,s,t).ratio()
    return max((one(a,c) for c in candidates),default=0.)

def team_map(teams):
    result={}
    for t in teams:
        code=t["team"];result[latin(t.get("name_ru",""))]=code
    result.update({latin(x):code for x,code in {
        "Новый Орлеан":"NOP","Нью-Орлеан":"NOP","Клипперс":"LAC",
        "Лейкерс":"LAL","Юта":"UTA","Голден Стэйт":"GSW",
        "Оклахома-Сити":"OKC","Сан-Антонио":"SAS"
    }.items()})
    return result

def people_index(season_rows):
    grouped=defaultdict(lambda:defaultdict(list))
    namecount=defaultdict(Counter)
    for season,rows in season_rows.items():
        for r in rows:
            person=str(r.get("nba_id") or "").strip()
            if person in ("", "0", "None", "NA"):
                key="name:"+canon(r["name"])
            else:
                key="id:"+person
            grouped[key][season].append(r)
            namecount[key][r["name"]]+=1
    out={}
    for key,seasons in grouped.items():
        for rows in seasons.values():
            rows.sort(key=lambda r:(r["date"],r["game"]))
        name=namecount[key].most_common(1)[0][0]
        out[key]={
            "name":name,"nba_id":key[3:] if key.startswith("id:") else None,
            "byseason":seasons,
            "name_key":canon(name)
        }
    return out

def stats_evidence(p,person,teamcodes):
    history={h.get("season"):h for h in p.get("history",[]) if h.get("games") and h.get("fp_avg") is not None}
    result={"score":0.,"close":0,"team_ok":0,"log_verified":False,"log_ratio":0.,"max_diff":99.,"evidence":[]}
    for season,h in history.items():
        rows=person["byseason"].get(season)
        if not rows:continue
        n=len(rows)
        g=abs(n-int(h["games"]))
        mean=fmean(float(r["fp"]) for r in rows)
        diff=abs(mean-float(h["fp_avg"]))
        pts=18 if g==0 else 12 if g<=2 else 3 if g<=5 else -18
        pts+=24 if diff<=.35 else 15 if diff<=1.0 else 7 if diff<=2 else -12 if diff>4 else 0
        hteam=teamcodes.get(latin(h.get("team","")))
        teams={r.get("team") for r in rows}
        if hteam and hteam in teams:
            pts+=11
            result["team_ok"]+=1
        if g<=2 and diff<=2:
            result["close"]+=1
            result["max_diff"]=min(result["max_diff"],diff)
        log=h.get("log") or []
        fp_series=[int(round(float(v))) for v in log if v is not None]
        if h.get("log_valid") and len(fp_series)>=12 and len(fp_series)==n:
            computed=[int(round(float(r["fp"]))) for r in rows]
            fraction=sum(a==b for a,b in zip(fp_series,computed))/len(fp_series)
            result["log_ratio"]=max(result["log_ratio"],round(fraction,4))
            if fraction>=.83:
                result["log_verified"]=True;pts+=90
            elif fraction>=.60:pts+=25
        result["score"]+=pts
        result["evidence"].append({"season":season,"games_catalog":int(h["games"]),
                   "games_nba":n,"fp_catalog":round(float(h["fp_avg"]),2),
                   "fp_nba":round(mean,2),"avg_diff":round(diff,2),
                   "team_consistent":bool(hteam and hteam in teams)})
    return result

def resolve(base,season_rows):
    people=people_index(season_rows)
    teamcodes=team_map(base.get("teams") or [])
    mapped={};taken={}
    skipped=[];candidates={}
    exact_by_name=defaultdict(list)
    for key,person in people.items():exact_by_name[person["name_key"]].append(key)
    # Proven English names take precedence; never assume the 2026 current club equals 2025 club.
    for p in base["players"]:
        english=canon(p.get("english"))
        matching=exact_by_name.get(english,[]) if english else []
        if len(matching)==1 and matching[0] not in taken:
            key=matching[0];person=people[key]
            mapped[p["id"]]={"english":person["name"],"nba_id":person["nba_id"],
              "key":key,"method":"verified_english","confidence":"high",
              "evidence":stats_evidence(p,person,teamcodes)["evidence"]}
            taken[key]=p["id"]
    # Evaluate every remaining candidate on multiple independent signals.
    pending=[p for p in base["players"] if p["id"] not in mapped]
    for p in pending:
        scored=[]
        for key,person in people.items():
            if key in taken:continue
            st=stats_evidence(p,person,teamcodes)
            if not st["evidence"]:continue
            name=similarity(p.get("name"),person["name"])
            english=canon(p.get("english"))
            english_similarity=SequenceMatcher(None,english,person["name_key"]).ratio() if english else 0.
            name=max(name,english_similarity)
            st["score"]+=round(name*18,2)
            st["name_similarity"]=round(name,3)
            st["key"]=key;st["english"]=person["name"];st["nba_id"]=person["nba_id"]
            scored.append(st)
        scored.sort(key=lambda z:z["score"],reverse=True)
        candidates[p["id"]]=scored[:3]
    # Resolve single best candidate globally, not independently: no NBA player can
    # be used by two Sports.ru cards, even if both Russian names are similar.
    proposed=[]
    for p in pending:
        choices=candidates[p["id"]]
        if not choices:continue
        a=choices[0];b=choices[1] if len(choices)>1 else None
        gap=a["score"]-(b["score"] if b else -1e6)
        evidence=a["evidence"]
        exact_log=a["log_verified"] and a["log_ratio"]>=.83
        multi=(a["close"]>=2 and a["team_ok"]>=1 and a["score"]>=89)
        single=(a["close"]>=1 and a["team_ok"]>=1 and a["name_similarity"]>=.77 and a["score"]>=60
                and any(v["avg_diff"]<=1.0 and abs(v["games_catalog"]-v["games_nba"])<=2 for v in evidence))
        verified_english=(p.get("english") and canon(p["english"])==canon(a["english"]))
        if gap<14:continue
        if not (exact_log or multi or single or verified_english):continue
        method="matching_fp_log" if exact_log else "multiseason_statistical" if multi else "season_and_name"
        if verified_english:method="verified_english"
        proposed.append((a["score"],gap,p,a,method))
    proposed.sort(key=lambda z:(z[0],z[1]),reverse=True)
    for score,gap,p,a,method in proposed:
        key=a["key"]
        if key in taken:continue
        mapped[p["id"]]={"english":a["english"],"nba_id":a["nba_id"],
              "key":key,"method":method,"confidence":"high" if method in ("matching_fp_log","verified_english") else "medium",
              "evidence":a["evidence"],"name_similarity":a["name_similarity"],"log_ratio":a["log_ratio"]}
        taken[key]=p["id"]
    for p in base["players"]:
        if p["id"] in mapped:continue
        out={"id":p["id"],"name":p["name"],"english":p.get("english"),"team":p.get("team"),
             "historical_seasons":len(p.get("history") or []),
             "reason":"no_three_season_history" if not p.get("history") else "ambiguous_or_not_found",
             "candidates":[{"name":v["english"],"score":round(v["score"],1),
                "name_similarity":v["name_similarity"],"close_seasons":v["close"],
                "log_ratio":v["log_ratio"],"evidence":v["evidence"][-1:]} for v in candidates.get(p["id"],[])[:3]]}
        skipped.append(out)
    lookup={meta["key"]:pid for pid,meta in mapped.items()}
    names={canon(meta["english"]):pid for pid,meta in mapped.items()
           if sum(canon(o["english"])==canon(meta["english"]) for o in mapped.values())==1}
    report={
      "schema_version":1,"catalog_players":len(base["players"]),
      "matched":len(mapped),"unresolved":len(skipped),
      "with_nba_history":sum(bool(p.get("history")) for p in base["players"]),
      "by_method":dict(Counter(meta["method"] for meta in mapped.values())),
      "english_missing_before":sum(not p.get("english") for p in base["players"]),
      "english_recovered":sum(bool(pid in mapped and not next(p for p in base["players"] if p["id"]==pid).get("english")) for pid in mapped),
      "unresolved_examples":skipped[:50],
      "players":mapped
    }
    return lookup,names,report
