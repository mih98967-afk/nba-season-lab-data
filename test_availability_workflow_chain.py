"""Ensure provenance reports only publish within the coherent NBA sync."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parent
class AvailabilityWorkflow(unittest.TestCase):
    def test_one_publisher_and_ordered_provenance(self):
        s=(ROOT/'.github/workflows/nba-sync.yml').read_text()
        for name in ('python -m src.p_play_selection_bias_audit',
                     'python -m src.participation_evidence_ledger_research',
                     'python -m src.official_nba_nonout_unknown_research',
                     'python -m src.availability_source_reconciliation_research'):
            self.assertIn(name,s)
        self.assertLess(s.index('python -m src.participation_evidence_ledger_research'),
                        s.index('python -m src.availability_source_reconciliation_research'))
        self.assertIn('data/official_nba_nonout_unknown_research.json data/availability_source_reconciliation_research.json',s)
        for filename in ('official-nba-nonout-unknown.yml','availability-source-reconciliation.yml'):
            t=(ROOT/'.github/workflows'/filename).read_text()
            self.assertIn('contents: read',t)
            self.assertNotIn('  schedule:',t)
            self.assertNotIn('  workflow_run:',t)
            self.assertNotIn('  workflow_dispatch:',t)
            self.assertNotIn('git add data/',t)
            self.assertNotIn('nba-season-lab-shared-write',t)
if __name__=='__main__':unittest.main()
