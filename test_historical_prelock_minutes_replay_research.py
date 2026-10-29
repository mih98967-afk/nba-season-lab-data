"""No target-game leakage in historical T-30 conditional-minutes replay."""
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.historical_prelock_minutes_replay_research import (
    attach_played_to_calendar, reconstruct_player, summarize, STATUS,
)
from src.rolling_decision_research import instant


def sample():
    from datetime import date
    previous = [{"min":30.0,"fp":30.0,"g":"002230%04d"%i,
                 "d":"2024-03-%02d"%(i+1),"team":"BOS"} for i in range(25)]
    fixtures=[]
    played=[]
    for i in range(6):
        dt=datetime(2024,11,1+3*i,2,0,tzinfo=timezone.utc)
        gid="002240%04d"%i
        # ET date is previous calendar day in Boston in November.
        et=(dt-timedelta(days=1)).date().isoformat()
        fixtures.append({"id":gid,"utc":dt,"et_date":et,"home":"BOS","away":"NYK"})
        if i<5:
            played.append({"g":gid,"d":et,"team":"BOS","min":float(20+i),
                           "fp":float(25+i),"tip":dt})
    return previous,played,fixtures


class PrelockReplay(unittest.TestCase):
    def test_prelock_candidate_universe_includes_unknown_absence(self):
        old,played,fixtures=sample()
        rows,qa=reconstruct_player("n007",old,played,fixtures,24)
        self.assertEqual(len(rows),3)  # Games 4, 5 and 6 of the club schedule.
        self.assertEqual(qa["paired_positive_played_only"],2)
        self.assertEqual(qa["no_positive_minutes_log_UNKNOWN"],1)
        self.assertEqual(rows[-1]["result_label"],"UNKNOWN_no_positive_log_not_DNP")
        self.assertNotIn("actual_fp",rows[-1])
        self.assertEqual(summarize(rows)["verified_positive_played_pairs"],2)
        for r in rows:
            self.assertLessEqual(instant(r["assumed_last_played_available_utc"]),
                                 instant(r["simulated_individual_lock_utc"]))
            self.assertFalse(r["adopt_on_site"])

    def test_outcome_join_never_selects_target_player(self):
        old,played,fixtures=sample()
        all_rows,_=reconstruct_player("n007",old,played,fixtures,24)
        # Remove the outcome for the fourth game after it has already been
        # selected; the simulated prelock forecast for that game is unchanged.
        removed=[x for x in played if x["g"]!=fixtures[3]["id"]]
        without,_=reconstruct_player("n007",old,removed,fixtures,24)
        a=all_rows[0].copy();b=without[0].copy()
        for row in (a,b):
            for key in ("result_label","actual_minutes","actual_fp"):
                row.pop(key,None)
        self.assertEqual(a,b)
        self.assertEqual(without[0]["result_label"],"UNKNOWN_no_positive_log_not_DNP")

    def test_current_game_never_known_before_lock_even_at_twelve_hours(self):
        old,played,fixtures=sample()
        for lag in (12,24,48):
            rows,_=reconstruct_player("n007",old,played,fixtures,lag)
            for row in rows:
                self.assertNotEqual(row["source_last_played_tipoff_utc"],
                                    fixtures[int(row["game_id"][-4:])]["utc"].isoformat())

    def test_abstain_for_new_team_and_no_prior(self):
        old,played,fixtures=sample()
        rows,_=reconstruct_player("n007",[],played,fixtures,24)
        self.assertEqual(rows,[])
        swapped=deepcopy(played)
        for r in swapped:
            r["team"]="NYK"
        rows,_=reconstruct_player("n007",old,swapped,fixtures,24)
        self.assertEqual(rows,[])

    def test_fixture_join_rejects_bad_team_date_or_missing_game(self):
        old,played,fixtures=sample()
        bare=[{k:v for k,v in played[0].items() if k!="tip"}]
        rows=attach_played_to_calendar(bare,fixtures,"2024/25")
        self.assertEqual(len(rows),1)
        bad=deepcopy(bare);bad[0]["d"]="2024-11-09"
        with self.assertRaises(ValueError):
            attach_played_to_calendar(bad,fixtures,"2024/25")
        bad=deepcopy(bare);bad[0]["team"]="LAL"
        with self.assertRaises(ValueError):
            attach_played_to_calendar(bad,fixtures,"2024/25")

    def test_unchanged_previous_outcome_cannot_affect_earlier_issue(self):
        old,played,fixtures=sample()
        a,_=reconstruct_player("n007",old,played,fixtures,24)
        changed=deepcopy(played)
        changed[-1]["min"]=60.0
        b,_=reconstruct_player("n007",old,changed,fixtures,24)
        self.assertEqual(a[0],b[0])

    def test_one_writer_and_unadopted(self):
        root=Path(__file__).resolve().parent
        workflow=(root/".github/workflows/nba-sync.yml").read_text()
        self.assertEqual(workflow.count("python -m src.historical_prelock_minutes_replay_research"),2)
        self.assertIn("data/historical_prelock_minutes_replay_research.json",workflow)
        self.assertIn("test_historical_prelock_minutes_replay_research",workflow)
        self.assertEqual(STATUS,"research_only_not_deployed")


if __name__=="__main__":unittest.main()
