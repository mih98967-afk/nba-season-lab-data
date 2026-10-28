"""Keep availability provenance workflow source-consistent and research-only."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent
class AvailabilityWorkflow(unittest.TestCase):
    def test_order_and_atomic_public_snapshot(self):
        s=(ROOT/'.github/workflows/availability-source-reconciliation.yml').read_text()
        steps=[
          'python -m src.p_play_selection_bias_audit',
          'python -m src.participation_evidence_ledger_research',
          'python -m src.official_nba_nonout_unknown_research',
          'python -m unittest -v test_availability_source_reconciliation_research',
          'python -m src.availability_source_reconciliation_research'
        ]
        positions=[s.index(x) for x in steps]
        self.assertEqual(positions,sorted(positions))
        self.assertIn('git add data/p_play_selection_bias_audit.json data/participation_evidence_ledger_research.json data/official_nba_nonout_unknown_research.json data/availability_source_reconciliation_research.json',s)
        self.assertIn("workflows: ['NBA game-specific NON-OUT unknown independent research']",s)
        self.assertNotIn("cron: '47 15 * * *'",s)
        self.assertIn('nba-season-lab-shared-write',s)
if __name__=='__main__':unittest.main()
