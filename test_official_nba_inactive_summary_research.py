import unittest
from datetime import datetime, timezone
from src.official_nba_inactive_summary_research import validate_summary, reconcile, VERIFIED, UNKNOWN, STATUS

GID="0022600119"
GAME={"id":"espn_401909868","utc":"2026-10-26T23:00:00Z","home":"CHA","away":"WAS","status":"final"}
def payload(team="CHA",person=1642851):
    home,away=1610612766,1610612764
    return {"resultSets":[
      {"name":"GameSummary","headers":["GAME_ID","GAME_STATUS_ID","HOME_TEAM_ID","VISITOR_TEAM_ID"],
       "rowSet":[[GID,3,home,away]]},
      {"name":"LineScore","headers":["TEAM_ID","TEAM_ABBREVIATION"],
       "rowSet":[[home,"CHA"],[away,"WAS"]]},
      {"name":"InactivePlayers","headers":["PLAYER_ID","TEAM_ID","TEAM_ABBREVIATION"],
       "rowSet":[[person,home if team=="CHA" else away,team]]}]}
def input_reports():
    first={"status":STATUS,"adopt_on_site":False,"records":[{
        "game_id":GAME["id"],"player_id":"n066",
        "boxscore_athlete_verdict":"ESPN_person_not_listed_in_two_team_boxscore"}]}
    live={"games":[GAME]}
    nba={"status":STATUS,"adopt_on_site":False,"model_training_negative_allowed":False,
         "records":[{"game_id":GAME["id"],"player_id":"n066","nba_game_id":GID,
          "game_utc":GAME["utc"],"team":"CHA","outcome":UNKNOWN,
          "p_play_shadow_untouched":True,
          "identity_nba_person_id":"1642851","identity_NBA_ID_strength":"high",
          "first_prediction_issued_at_utc":"2026-10-26T21:15:00Z",
          "observed_official_game_played_flag":None}]}
    return nba,first,live
class Tests(unittest.TestCase):
    def test_literal_matching_inactive_is_separate_evidence(self):
        args=input_reports()
        got=reconcile(*args,{GID:payload()},{},datetime(2026,10,27,10,tzinfo=timezone.utc))
        self.assertEqual((got["resolved_confirmed"],got["unresolved_unknown"]),(1,0))
        self.assertFalse(got["training_negatives_allowed"])
        self.assertTrue(got["records"][0]["matched_explicit_official_inactive"])
    def test_missing_player_not_negative(self):
        got=reconcile(*input_reports(),{GID:payload(person=12345)},{},
                      datetime(2026,10,27,10,tzinfo=timezone.utc))
        self.assertEqual((got["resolved_confirmed"],got["unresolved_unknown"]),(0,1))
    def test_source_unavailable_not_negative(self):
        got=reconcile(*input_reports(),{}, {GID:"HTTP_403"},
                      datetime(2026,10,27,10,tzinfo=timezone.utc))
        self.assertEqual((got["source_unavailable_games"],got["resolved_confirmed"]),(1,0))
    def test_wrong_team_quarantined(self):
        got=reconcile(*input_reports(),{GID:payload(team="WAS")},{},
                      datetime(2026,10,27,10,tzinfo=timezone.utc))
        self.assertEqual(got["conflicts"],1)
        self.assertEqual(got["resolved_confirmed"],0)
    def test_summary_wrong_game_or_not_final_rejected(self):
        bad=payload();bad["resultSets"][0]["rowSet"][0][0]="0022600120"
        with self.assertRaises(ValueError):
            validate_summary(bad,GID,"CHA","WAS")
        bad=payload();bad["resultSets"][0]["rowSet"][0][1]=2
        with self.assertRaises(ValueError):
            validate_summary(bad,GID,"CHA","WAS")
    def test_duplicate_inactive_rejected(self):
        bad=payload();bad["resultSets"][2]["rowSet"].append(bad["resultSets"][2]["rowSet"][0][:])
        with self.assertRaises(ValueError):
            validate_summary(bad,GID,"CHA","WAS")
if __name__=="__main__":
    unittest.main()
