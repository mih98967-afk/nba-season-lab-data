"""No-network regression tests for the historical importer."""
import gzip
import io
import unittest
from unittest.mock import patch
from src.history import get_csv, parse_schedule, parse_box

class FakeResponse:
    def __init__(self,payload):self.payload=payload
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):return self.payload

class HistoryTests(unittest.TestCase):
    def test_gz_csv_decode(self):
        raw="game_id,home_pts\n0022300001,101\n"
        with patch("urllib.request.urlopen",return_value=FakeResponse(gzip.compress(raw.encode()))):
            self.assertEqual(get_csv("https://example.org/nba_schedule_2024.csv.gz"),raw)
    def test_reject_incomplete_calendar(self):
        raw="game_id,home_team_abbreviation,away_team_abbreviation,home_pts,away_pts,game_date\n0022300001,BOS,NYK,110,105,2023-10-24\n"
        with self.assertRaisesRegex(ValueError,"Not enough valid"):
            parse_schedule(raw)
    def test_reject_empty_box(self):
        with self.assertRaisesRegex(ValueError,"Boxscore columns missing"):
            parse_box("game_id,player_name\n",{},"2023/24")
    def test_gz_guard(self):
        with patch("urllib.request.urlopen",return_value=FakeResponse(gzip.compress(b"A"*19_000_000))):
            with self.assertRaisesRegex(ValueError,"Oversized"):
                get_csv("https://example.org/schedule.csv.gz")

if __name__=="__main__":unittest.main()
