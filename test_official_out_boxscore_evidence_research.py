import unittest
from src.official_out_boxscore_evidence_research import _outcome,_index_summary
class Tests(unittest.TestCase):
 def test_unlisted_is_unknown_not_dnp(self):
  index={"played":{},"members":{}}
  self.assertEqual(_outcome(index,"123","BOS"),("ESPN_person_not_listed_in_two_team_boxscore",False))
 def test_explicit_dnp_only(self):
  index={"played":{},"members":{"123":{"team":"BOS","explicit_didNotPlay":True,"active_minutes_positive":False}}}
  self.assertEqual(_outcome(index,"123","BOS"),("ESPN_explicit_didNotPlay_true",True))
 def test_positive_contradiction_quarantined(self):
  index={"played":{"123":"BOS"},"members":{"123":{"team":"BOS","explicit_didNotPlay":False,"active_minutes_positive":True}}}
  self.assertEqual(_outcome(index,"123","BOS"),("positive_minutes_conflicts_with_official_OUT",False))
 def test_wrong_club_quarantined(self):
  index={"played":{},"members":{"123":{"team":"NYK","explicit_didNotPlay":True,"active_minutes_positive":False}}}
  self.assertEqual(_outcome(index,"123","BOS"),("opposing_team_conflict",False))
 def test_not_listed_is_not_equivalent_to_unverified_minutes(self):
  index={"played":{},"members":{"123":{"team":"BOS","explicit_didNotPlay":False,"active_minutes_positive":False}}}
  self.assertEqual(_outcome(index,"123","BOS"),("ESPN_listed_without_positive_or_explicit_DNP",False))
if __name__=="__main__":unittest.main()
