"""Real NBA PDF continuation-row regression; no network requests."""
import json,unittest
from pathlib import Path
from src import official_injury_rows as m
HERE=Path(__file__).resolve().parent
class Page:
 def __init__(self,words):self.words=words
 def extract_words(self,**kwargs):return self.words
class TestContinuation(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.fixture=json.loads((HERE/'tests/fixtures/official_injury_continuation_20261118.json').read_text());cls.pages=[Page(w) for w in cls.fixture['pages']]
 def test_all_102_native_status_cells_parse(self):
  events,qa=m.parse_pages(self.pages)
  self.assertEqual(events,self.fixture['expected_events'])
  self.assertEqual(m.validate_extracted_status_rows(self.pages,events)['explicit_status_cells'],102)
  self.assertNotIn('team_matchup_conflict',qa)
 def test_new_matchup_on_continuation_page_restores_sacramento(self):
  events,_=m.parse_pages(self.pages)
  sax=[e for e in events if e['team']=='SAC']
  self.assertEqual(len(sax),6)
  self.assertTrue(all((e['away'],e['home'])==('PHX','SAC') for e in sax))
  self.assertEqual(next(e['team'] for e in events if e['player_name']=='mark williams'),'PHX')
 def test_top_team_context_does_not_leak_previous_team(self):
  events,_=m.parse_pages(self.pages);teams={e['player_name']:e['team'] for e in events}
  self.assertEqual(teams['evan mobley'],'CLE');self.assertEqual(teams['joshua jefferson'],'BKN');self.assertEqual(teams['jalen williams'],'OKC')
 def test_cropped_event_list_cannot_pass_full_cell_denominator(self):
  events,_=m.parse_pages(self.pages)
  with self.assertRaisesRegex(ValueError,'context incomplete'):
   m.validate_extracted_status_rows(self.pages,events[:-1])
 def test_unanchored_top_status_fails_closed(self):
  page=Page([{'x0':426,'top':83.6,'text':'Example,'},{'x0':474,'top':83.6,'text':'Player'},{'x0':586,'top':83.6,'text':'Out'}])
  events,_=m.parse_pages([page]);self.assertEqual(events,[])
  with self.assertRaisesRegex(ValueError,'context incomplete'):
   m.validate_extracted_status_rows([page],events)
 def test_empty_or_duplicate_still_rejected(self):
  with self.assertRaisesRegex(ValueError,'context incomplete'):m.validate_extracted_status_rows([Page([])],[])
  events,_=m.parse_pages(self.pages);duplicate=[dict(e) for e in events];duplicate[1]=dict(duplicate[0])
  with self.assertRaisesRegex(ValueError,'Duplicate player'):m.validate_extracted_status_rows(self.pages,duplicate)
if __name__=='__main__':unittest.main()
