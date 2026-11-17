"""Join future NBA identities to preserved UTC entries; never invent tipoffs."""
from pathlib import Path
import collections
import datetime as dt
import json
from zoneinfo import ZoneInfo

import pandas as pd

OUT = Path(__file__).resolve().parent


def main():
    future = pd.read_pickle(OUT / "future_feature_frame.pkl")
    source = OUT / "source"
    sc = pd.read_csv(source / "current/nba_schedule_2027.csv.gz", dtype=str, keep_default_na=False)
    game_map = {r.game_id:r for r in sc.itertuples(index=False)}
    sched = json.loads((source / "data/schedule.json").read_text())
    by_key = collections.defaultdict(list);invalid = []
    for g in sched["games"]:
        try:
            stamp = dt.datetime.fromisoformat(g["utc"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:raise ValueError("naive UTC field")
            day = stamp.astimezone(ZoneInfo("America/New_York")).date().isoformat()
            if g.get("et_date", day) != day:raise ValueError("ET date disagrees with UTC")
            by_key[(day, g["home"], g["away"])].append(g)
        except Exception as e:invalid.append({"id": g.get("id"), "error": str(e)})
    now = dt.datetime.now(dt.timezone.utc);matched = [];missing = [];ambiguous = [];too_late = []
    for gid in sorted(future.game.astype(str).unique()):
        g = game_map[gid];key = (g.game_date[:10], g.home_team_abbreviation, g.away_team_abbreviation)
        candidates = by_key.get(key, [])
        if not candidates:missing.append({"game": gid, "key": list(key)});continue
        if len(candidates) != 1:ambiguous.append({"game": gid, "key": list(key), "n": len(candidates)});continue
        c = candidates[0];stamp = dt.datetime.fromisoformat(c["utc"].replace("Z", "+00:00"))
        entry = {"game": gid, "et_date": key[0], "home": key[1], "away": key[2],
                 "utc": c["utc"], "espn_id": c.get("espn_id"), "source_url": c.get("url"),
                 "strict_before_Tminus30_at_audit": now < stamp - dt.timedelta(minutes=30)}
        matched.append(entry)
        if not entry["strict_before_Tminus30_at_audit"]:too_late.append(gid)
    report = {"status": "EXACT_FUTURE_GAME_UTC_JOIN_PASS" if not invalid and not missing and not ambiguous and not too_late else "INCOMPLETE_OR_BLOCKED_FUTURE_UTC_JOIN",
              "audited_at_utc": now.isoformat(), "future_games": future.game.nunique(), "matched": len(matched),
              "invalid_utc_entries": invalid, "missing_games": missing, "ambiguous_games": ambiguous, "already_past_prelock_at_audit": too_late,
              "games": matched, "calendar_completeness_proven": False,
              "earliest_included_tipoff_utc": min([g["utc"] for g in matched], default=None),
              "must_recheck_Tminus30_at_actual_issuance": True}
    (OUT / "FUTURE_UTC_SCHEDULE_QA.json").write_text(json.dumps(report, indent=2, default=int) + "\n")
    print(json.dumps({k:v for k,v in report.items() if k != "games"}, indent=2, default=int))


if __name__ == "__main__":main()
