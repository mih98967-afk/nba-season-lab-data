"""Regression for daily frozen inference safety net (no training/deploy)."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
WORKFLOW=ROOT/'.github/workflows/match-context-distribution.yml'


class FrozenFallbackWorkflowTests(unittest.TestCase):
    def test_schedule_runs_only_existing_guarded_inference(self):
        w=WORKFLOW.read_text()
        self.assertIn("cron: '37 12 * * *'",w)
        self.assertIn("github.event_name == 'schedule' && github.ref == 'refs/heads/main'",w)
        self.assertIn("python research_extension/production_20261118/refresh_decision.py --root . --github-output",w)
        self.assertIn("if: steps.cadence.outputs.refresh == 'true'",w)
        self.assertIn('without fitting',w)
        self.assertNotIn('firebase deploy',w)
        self.assertNotIn('firebase deploy',w.lower())
        # Historical fitting remains an explicit workflow_dispatch-only action.
        self.assertIn("inputs.full_research",w)
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.full_research",w)

if __name__=='__main__':unittest.main()
