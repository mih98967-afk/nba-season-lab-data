"""No competing short-minute publishers or retrospective reissuance."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parent
class ShortRiskOwner(unittest.TestCase):
    def test_single_authoritative_writer(self):
        s=(ROOT/'.github/workflows/nba-sync.yml').read_text()
        self.assertIn('python -m src.short_minutes_prospective_research',s)
        self.assertIn('python -m src.short_minutes_prospective_evaluation_research',s)
        self.assertIn('data/short_minutes_prospective_evaluation_research.json',s)
        self.assertIn('test_short_minutes_prospective_evaluation_research',s)
        for p in ('short-minutes-prospective.yml','short-minutes-prospective-evaluation.yml'):
            t=(ROOT/'.github/workflows'/p).read_text()
            self.assertIn('contents: read',t)
            self.assertNotIn('  schedule:',t)
            self.assertNotIn('  workflow_run:',t)
            self.assertNotIn('  workflow_dispatch:',t)
            self.assertNotIn('git add data/',t)
            self.assertNotIn('nba-season-lab-shared-write',t)
if __name__=='__main__':unittest.main()
