"""Conservative public Telegram preview watcher. Only open @nba_injurynews posts.
News is secondary information, never a confirmed injury or automatic FP adjustment.
"""
from __future__ import annotations
import datetime as dt
from collections import defaultdict
from html.parser import HTMLParser
import json, pathlib, re, unicodedata, urllib.request
CHANNEL="nba_injurynews"
URL="https://t.me/s/"+CHANNEL
ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
MAX_PAGES=3
MAX_AGE=dt.timedelta(days=14)
VOID_TAGS={"area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"}

def canonical(value):
    value=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+"," ",value).strip()

class TelegramPreview(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack=[];self.active=None;self.text_depth=None;self.posts=[]
    def handle_starttag(self,tag,attributes):
        attrs=dict(attributes);cls=(attrs.get("class") or "").split()
        if tag not in VOID_TAGS:self.stack.append(tag)
        if tag=="div" and "tgme_widget_message" in cls:
            ref=attrs.get("data-post","")
            if re.fullmatch(rf"{CHANNEL}/[0-9]+",ref):
                self.active={"id":int(ref.rsplit("/",1)[1]),"text_parts":[],
                             "published_at":None,"url":"https://t.me/"+ref}
                self.post_depth=len(self.stack);self.text_depth=None
        if self.active:
            if tag=="div" and "tgme_widget_message_text" in cls:
                self.text_depth=len(self.stack)
            if tag=="time" and attrs.get("datetime") and not self.active["published_at"]:
                self.active["published_at"]=attrs["datetime"]
            if tag=="br" and self.text_depth is not None:
                self.active["text_parts"].append("\n")
    def handle_endtag(self,tag):
        if tag in VOID_TAGS:return
        if self.active and self.text_depth is not None and len(self.stack)==self.text_depth and tag=="div":
            self.text_depth=None
        if self.active and tag=="div" and len(self.stack)==self.post_depth:
            txt="".join(self.active.pop("text_parts"))
            txt=re.sub(r"[ \t\r]+"," ",txt)
            txt=re.sub(r"\n{3,}","\n\n",txt).strip()
            if txt and self.active["published_at"]:
                self.active["text"]=txt;self.posts.append(self.active)
            self.active=None;self.text_depth=None
        if tag in self.stack:
            while self.stack:
                if self.stack.pop()==tag:break
    def handle_data(self,data):
        if self.active and self.text_depth is not None and len(self.stack)>=self.text_depth:
            self.active["text_parts"].append(data)

def parse_posts(html):
    p=TelegramPreview();p.feed(html)
    return sorted({x["id"]:x for x in p.posts}.values(),key=lambda x:x["id"],reverse=True)

def fetch_html(url):
    if not url.startswith(URL):raise ValueError("Unexpected URL")
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; NBASeasonLab/1.0; public-preview)","Accept":"text/html","Accept-Language":"en-US,en;q=0.9"})
    with urllib.request.urlopen(req,timeout=24) as response:
        body=response.read(2_500_001)
        if len(body)>2_500_000:raise ValueError("Telegram response too large")
        return body.decode("utf-8",errors="replace")

def fetch_posts(fetch=fetch_html):
    found={};before=None
    for _ in range(MAX_PAGES):
        posts=parse_posts(fetch(URL if before is None else URL+"?before="+str(before)))
        if not posts:
            if not found:raise ValueError("Telegram preview unavailable or HTML schema changed")
            break
        for p in posts:found[p["id"]]=p
        oldest=min(p["id"] for p in posts)
        if before is not None and oldest>=before:break
        before=oldest
        if len(posts)<15:break
    return sorted(found.values(),key=lambda p:p["id"],reverse=True)

def player_aliases(catalog,identity=None):
    mapping=(identity or {}).get("players") or {}
    full=defaultdict(set);lastnames=defaultdict(set)
    for p in catalog.get("players") or []:
        english=(mapping.get(p.get("id")) or {}).get("english") or p.get("english")
        if not english:continue
        words=canonical(english).split()
        if len(words)<2:continue
        full[" ".join(words)].add(p["id"])
        last=words[-2] if words[-1] in ("jr","sr","ii","iii","iv") and len(words)>=3 else words[-1]
        if len(last)>=5:lastnames[last].add(p["id"])
    return ({a:next(iter(v)) for a,v in full.items() if len(v)==1},
            {a:next(iter(v)) for a,v in lastnames.items() if len(v)==1})

PATTERNS=[
 ("out",r"\b(?:ruled out|is out|out|out for|will miss|to miss|won t play|will not play|inactive|sidelined)\b"),
 ("doubtful",r"\bdoubtful\b"),
 ("questionable",r"\b(?:questionable|game time decision|game time call)\b"),
 ("probable",r"\bprobable\b"),
 ("available",r"\b(?:available tonight|available to play|will play|cleared to play|set to play|returns tonight)\b"),
 ("injury_update",r"\b(?:injur(?:y|ed)|ankle|knee|hamstring|calf|illness|back spasms|concussion|shoulder|wrist|finger|hip|groin|soreness|minutes restriction|minutes limit|limited in practice|return timeline|sprain|strain|torn)\b")
]
def classify(line):
    s=canonical(line)
    if not s or len(s)>450 or any(x in s for x in ("promocode","betting","buy ads","book your ad")):return None
    return next((tag for tag,pattern in PATTERNS if re.search(pattern,s)),None)

def matches_for_line(line,aliases):
    full,short=aliases;txt=" "+canonical(line)+" ";found={}
    for alias,pid in full.items():
        if " "+alias+" " in txt:found[pid]="full_name"
    for alias,pid in short.items():
        if pid not in found and " "+alias+" " in txt:found[pid]="unique_surname"
    return found

def utc(text):
    try:
        v=dt.datetime.fromisoformat(str(text).replace("Z","+00:00"))
        return v.astimezone(dt.timezone.utc) if v.tzinfo else None
    except (ValueError,TypeError):return None

def build_feed(posts,catalog,identity=None,existing=None,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    aliases=player_aliases(catalog,identity);events={}
    for post in posts:
        published=utc(post.get("published_at"))
        if not published or published<now-MAX_AGE or published>now+dt.timedelta(hours=2):continue
        for index,line in enumerate(re.split(r"\n+",post["text"])):
            status=classify(line)
            if not status:continue
            for pid,method in matches_for_line(line,aliases).items():
                ident=f"{CHANNEL}/{post['id']}:{pid}:{index}"
                events[ident]={"id":ident,"url":post["url"],
                  "published_at":published.isoformat(timespec="seconds").replace("+00:00","Z"),
                  "player_ids":[pid],"status":status,"match_quality":method,
                  "text":line[:360].strip(),"source":CHANNEL,"verification":"unconfirmed_telegram"}
    for old in (existing or {}).get("events") or []:
        published=utc(old.get("published_at"))
        if not published or published<now-MAX_AGE or published>now+dt.timedelta(hours=2):continue
        if not isinstance(old.get("player_ids"),list) or not old.get("url","").startswith("https://t.me/"+CHANNEL+"/"):continue
        if old.get("id"):events.setdefault(old["id"],old)
    selected=sorted(events.values(),key=lambda e:(e["published_at"],e["id"]),reverse=True)[:250]
    return {"schema_version":1,"status":"public_preview_unverified","channel":"@"+CHANNEL,
     "updated_at_utc":now.isoformat(timespec="seconds").replace("+00:00","Z"),
     "posts_checked":len(posts),"events":selected,
     "note":"Public Telegram signals are unconfirmed; no automatic medical or FP changes"}

def publish(fetch=fetch_html,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    base=DATA/"catalog.json"
    if not base.exists():raise ValueError("Public player catalog missing")
    catalog=json.loads(base.read_text(encoding="utf-8"))
    ip=DATA/"identity.json"
    identity=json.loads(ip.read_text(encoding="utf-8")) if ip.exists() else None
    op=DATA/"telegram.json"
    previous=json.loads(op.read_text(encoding="utf-8")) if op.exists() else {}
    posts=fetch_posts(fetch)
    if not posts:raise RuntimeError("No public Telegram posts; preserve earlier feed")
    out=build_feed(posts,catalog,identity,previous,now)
    tmp=op.with_suffix(".tmp")
    tmp.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    tmp.replace(op)
    return {"posts":len(posts),"signals":len(out["events"]),"updated_at_utc":out["updated_at_utc"]}

if __name__=="__main__":print(json.dumps(publish(),ensure_ascii=False,indent=2))
