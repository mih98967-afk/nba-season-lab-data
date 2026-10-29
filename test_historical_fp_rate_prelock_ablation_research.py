"""FP/minute challenger must not learn same-game outcomes and never infer DNP."""
import unittest
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path

from src.historical_prelock_minutes_replay_research import reconstruct_player
from src.historical_fp_rate_prelock_ablation_research import (
    enrich_issued_proxy,summary,STATUS,SCORE_FIELDS,CONTROL,
)
from src.rolling_decision_research import instant


def sample():
    previous=[{"min":30.0,"fp":30.0,"g":"002230%04d"%i,
               "d":"2024-03-%02d"%(i+1),"team":"BOS"} for i in range(25)]
    games=[]
    played=[]
    for i in range(7):
        tip=datetime(2024,11,1+3*i,2,tzinfo=timezone.utc)
        gid="002240%04d"%i
        et=(tip-timedelta(days=1)).date().isoformat()
        games.append({"id":gid,"utc":tip,"et_date":et,
                      "home":"BOS","away":"NYK"})
        if i<6:
            played.append({"g":gid,"d":et,"team":"BOS",
                           "min":float(20+i),"fp":float(10+i),"tip":tip})
    return previous,played,games


class RateResearchTests(unittest.TestCase):
    def test_current_rate_uses_only_earlier_games(self):
        prior,played,games=sample()
        issued,_=reconstruct_player("n007",prior,played,games,24)
        rows=enrich_issued_proxy(issued,played,prior,24)
        self.assertEqual(len(rows),len(issued))
        self.assertEqual(rows[0]["prior_current_same_team_n"],3)
        self.assertLess(rows[0]["variants"]["updated_minutes_shrunk_current_rate_5_FP"],
                        rows[0]["variants"][CONTROL])
        for row in rows:
            self.assertLessEqual(instant(row["last_feature_assumed_available_utc"]),
                                 instant(row["simulated_prelock_cutoff"]))

    def test_own_future_outcome_cannot_change_own_rate_prediction(self):
        prior,played,games=sample()
        issued,_=reconstruct_player("n007",prior,played,games,24)
        original=enrich_issued_proxy(issued,played,prior,24)
        changed=deepcopy(played)
        changed[3]["fp"]=150.0
        issued2,_=reconstruct_player("n007",prior,changed,games,24)
        altered=enrich_issued_proxy(issued2,changed,prior,24)
        self.assertEqual(original[0]["variants"],altered[0]["variants"])
        self.assertEqual(original[0]["simulated_prelock_cutoff"],
                         altered[0]["simulated_prelock_cutoff"])
        self.assertNotEqual(original[0]["actual_FP"],altered[0]["actual_FP"])

    def test_no_result_can_be_dnp_or_zero_imputed(self):
        prior,played,games=sample()
        issued,_=reconstruct_player("n007",prior,played,games,24)
        rows=enrich_issued_proxy(issued,played,prior,24)
        self.assertEqual(rows[-1]["result_label"],"UNKNOWN_no_positive_log_not_DNP")
        self.assertNotIn("actual_FP",rows[-1])
        result=summary(rows)
        self.assertEqual(result["prelock_proxy_issues"],
                         result["scored_positive_minutes_only"]+
                         result["UNKNOWN_not_DNP_or_zero"])
        self.assertEqual(result["UNKNOWN_not_DNP_or_zero"],1)

    def test_reject_mismatched_source_clock_and_club(self):
        prior,played,games=sample()
        issued,_=reconstruct_player("n007",prior,played,games,24)
        wrong=deepcopy(issued);wrong[0]["source_last_played_tipoff_utc"]="2024-12-20T10:00:00Z"
        with self.assertRaises(ValueError):
            enrich_issued_proxy(wrong,played,prior,24)
        wrong=deepcopy(issued);wrong[0]["club_from_previous_positive_game"]="NYK"
        with self.assertRaises(ValueError):
            enrich_issued_proxy(wrong,played,prior,24)

    def test_sensitivity_and_immutable_original_baseline(self):
        prior,played,games=sample()
        for lag in (12,24,48):
            issued,_=reconstruct_player("n007",prior,played,games,lag)
            rows=enrich_issued_proxy(issued,played,prior,lag)
            for x,y in zip(rows,issued):
                self.assertEqual(x["variants"][SCORE_FIELDS[0]],y["baseline_fp"])
                self.assertEqual(x["variants"][SCORE_FIELDS[1]],y["challenger_fp"])
                self.assertFalse("actual_FP" in x and x["result_label"].startswith("UNKNOWN"))

    def test_one_publisher_and_research_only(self):
        root=Path(__file__).resolve().parent
        sync=(root/".github/workflows/nba-sync.yml").read_text()
        self.assertEqual(sync.count("python -m src.historical_fp_rate_prelock_ablation_research"),2)
        self.assertIn("data/historical_fp_rate_prelock_ablation_research.json",sync)
        self.assertIn("test_historical_fp_rate_prelock_ablation_research",sync)
        self.assertEqual(STATUS,"research_only_not_deployed")


if __name__=="__main__":
    unittest.main()
