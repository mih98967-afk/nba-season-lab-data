"""Keep conditional FP evaluation and robustness behind one coherent writer."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent
class ConditionalOwner(unittest.TestCase):
    def test_single_publisher_order(self):
        s=(ROOT/'.github/workflows/nba-sync.yml').read_text()
        for part in ("if: github.event_name == 'pull_request'", "Reconcile official explicit DNP"):
            self.assertIn(part,s)
        parts=s.split("python -m src.participation_cohort_research")
        self.assertEqual(len(parts),3)
        for tail in parts[1:]:
            names=[
                "python -m src.p_play_shadow_research",
                "python -m src.conditional_minutes_fp_research",
                "python -m src.conditional_minutes_fp_evaluation_research",
                "python -m src.conditional_minutes_robustness_research",
            ]
            positions=[tail.index(name) for name in names]
            self.assertEqual(positions,sorted(positions))
        self.assertIn("data/conditional_minutes_robustness_research.json",s)
        self.assertIn("test_conditional_minutes_fp_evaluation_research",s)
    def test_no_independent_writer_or_stale_scheduled_test(self):
        for path in ("conditional-minutes-fp-evaluation.yml","conditional-minutes-robustness.yml"):
            s=(ROOT/'.github/workflows'/path).read_text()
            self.assertIn("contents: read",s)
            self.assertNotIn("git add data/",s)
            self.assertNotIn("workflow_run:",s)
            self.assertNotIn("  schedule:",s)
            self.assertNotIn("  workflow_dispatch:",s)
            self.assertNotIn("python -m src.conditional_minutes_",s)
if __name__=="__main__":unittest.main()
