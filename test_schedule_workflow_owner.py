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
if __name__=='__main__':unittest.main()
