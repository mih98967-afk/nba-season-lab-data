"""Regression: schedule has a single publishing owner; live sync follows calendar."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parent
class TestWorkflowOwnership(unittest.TestCase):
 def test_single_writer(self):
  live=(ROOT/'.github/workflows/nba-sync.yml').read_text()
  schedule=(ROOT/'.github/workflows/nba-schedule.yml').read_text()
  self.assertNotIn('git add data/live.json data/catalog.json data/schedule.json',live)
  self.assertNotIn('python -m src.schedule_sync',live)
  self.assertIn('git add data/schedule.json',schedule)
  self.assertIn("cron: '7 */4 * * *'",schedule)
  self.assertIn("cron: '17 */4 * * *'",live)
  self.assertLess(live.index('python -m src.sync'),live.index('python -m src.espn_roster_pit'))
  self.assertLess(live.index('python -m src.espn_roster_pit'),
                  live.index('python -m src.p_play_shadow_research', live.index('python -m src.espn_roster_pit')))
  self.assertIn('data/espn_roster_pit/*.json',live)
  self.assertIn('data/catalog_pit/*.json',live)
  self.assertLess(live.index('python -m src.sync'),live.index('from src.catalog_pit_research import run'))
  # Publish PIT-derived diagnostics only after the coherent main sync.
  sync=live
  for command in ("python -m src.p_play_shadow_research",
                  "python -m src.p_play_precommitted_paired_evaluation",
                  "python -m src.p_play_issuance_readiness_research",
                  "python -m src.public_sync_integrity"):
   self.assertIn(command,sync)
  self.assertIn('data/catalog_pit_coverage_research.json',sync)
  self.assertIn('data/p_play_issuance_readiness_research.json',sync)
  for workflow in ('catalog-pit-research.yml','p-play-issuance-readiness.yml'):
   t=(ROOT/'.github/workflows'/workflow).read_text()
   self.assertIn('contents: read',t)
   self.assertNotIn('contents: write',t)
   self.assertNotIn('git add data/',t)
   self.assertNotIn('git push origin',t)
  espn=(ROOT/'.github/workflows/espn-roster-pit.yml').read_text()
  self.assertNotIn('  push:',espn)
  self.assertIn('  schedule:',espn)
  self.assertIn("github.event_name == 'pull_request'",espn)
if __name__=='__main__':unittest.main()

