"""Guard the independent ledger writer against stale selection inputs."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent
class WorkflowGraph(unittest.TestCase):
    def test_selection_rebuilt_before_live_ledger_tests(self):
        s=(ROOT/'.github/workflows/participation-evidence-ledger.yml').read_text()
        a=s.index('python -m src.p_play_selection_bias_audit')
        b=s.index('python -m unittest -v test_participation_evidence_ledger_research')
        c=s.index('python -m src.participation_evidence_ledger_research')
        self.assertLess(a,b)
        self.assertLess(b,c)
        self.assertIn('git add data/p_play_selection_bias_audit.json data/participation_evidence_ledger_research.json',s)
        self.assertNotIn("workflows: ['NBA p-play missing-label selection audit'",s)
    def test_integrated_main_has_strict_atomic_gate(self):
        s=(ROOT/'.github/workflows/nba-sync.yml').read_text()
        self.assertIn('python -m src.public_sync_integrity',s)
        self.assertLess(s.index('python -m src.p_play_selection_bias_audit'),s.index('python -m src.participation_evidence_ledger_research'))
if __name__=='__main__':unittest.main()
