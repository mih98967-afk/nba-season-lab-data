import unittest
from datetime import datetime, timezone
from src.official_nba_gameday_status_research import (
    SCHEDULE_URL, fetch_public_json,
    fixture_match, official_box, official_schedule, verdict, STATUS, build,
)
GAME={"id":"espn_123","utc":"2026-10-26T23:00:00Z","home":"CHA","away":"WAS","status":"final"}
OFF={"id":"0022600012","utc":GAME["utc"],"home":"CHA","away":"WAS"}

def box():
    def team(code, base):
        return {"teamTricode":code,"teamId":base,
                "players":[{"personId":base*100+i,"status":"ACTIVE","played":"1",
                    "statistics":{"minutes":"12:00"}} for i in range(5)] +
                [{"personId":base*100+6,"status":"INACTIVE","played":"0",
                  "statistics":{"minutes":"0:00"},"notPlayingReason":"Injury"},
                 {"personId":base*100+7,"status":"ACTIVE","played":"0",
                  "statistics":{"minutes":"0:00"},"notPlayingReason":"DNP - Coach Decision"}]}
    return {"game":{"gameId":OFF["id"],"gameStatus":3,"gameTimeUTC":GAME["utc"],
                    "homeTeam":team("CHA",1610612766),
                    "awayTeam":team("WAS",1610612764)}}

class OfficialGameTests(unittest.TestCase):
    def test_current_official_schedule_version_and_schema(self):
        self.assertTrue(SCHEDULE_URL.endswith("/scheduleLeagueV2_1.json"))
        self.assertFalse("scheduleLeagueV2.json" in SCHEDULE_URL)
        days=[{"games":[]} for _ in range(110)]
        for i in range(1100):
            days[i%110]["games"].append({"gameId":f"00226{i:05d}",
                "gameDateTimeUTC":"2026-10-26T23:00:00Z",
                "homeTeam":{"teamTricode":"CHA"},
                "awayTeam":{"teamTricode":"WAS"}})
        self.assertEqual(len(official_schedule({"leagueSchedule":{"gameDates":days}})),1100)
        self.assertEqual(len(official_schedule({"scheduleLeagueV2":{"gameDates":days}})),1100)
        days[0]["games"].append({"gameId":"0022699999",
            "gameDateTimeUTC":"2026-10-26T23:00:00Z",
            "homeTeam":{"teamTricode":"TBD"},
            "awayTeam":{"teamTricode":"CHA"}})
        self.assertEqual(len(official_schedule({"leagueSchedule":{"gameDates":days}})),1100)
        with self.assertRaises(ValueError):
            official_schedule({"leagueSchedule":{"gameDates":[{"games":[]}]} })
        with self.assertRaises(ValueError):
            fetch_public_json("https://arbitrary.example/api.json")
    def test_game_specific_inactive_and_active_dnp_are_distinct(self):
        b=box()
        index=official_box(b,OFF,GAME)
        inactive=str(1610612766*100+6)
        nonplay=str(1610612766*100+7)
        self.assertEqual(verdict(index["players"],"CHA",inactive,{})[0],"VERIFIED_GAME_DAY_INACTIVE")
        self.assertEqual(verdict(index["players"],"CHA",nonplay,{})[0],"VERIFIED_ACTIVE_NONPLAY")
        self.assertEqual(verdict(index["players"],"CHA","98765",{})[0],"UNKNOWN")
        self.assertEqual(verdict(index["players"],"CHA",None,{})[0],"UNKNOWN")
        self.assertTrue(verdict(index["players"],"WAS",inactive,{})[2])
        self.assertTrue(verdict(index["players"],"CHA",str(1610612766*100),{})[2])
    def test_fixture_never_assumed_from_order(self):
        self.assertEqual(fixture_match(GAME,[OFF])[0]["id"],OFF["id"])
        self.assertIsNone(fixture_match(GAME, [OFF,OFF])[0])
        self.assertIsNone(fixture_match(GAME,[{**OFF,"utc":"2026-10-27T01:00:00Z"}])[0])
    def test_no_negatives_on_unsupported_official_schema(self):
        b=box();b["game"]["awayTeam"]["players"]=[]
        with self.assertRaises(ValueError):official_box(b,OFF,GAME)
        b=box();b["game"]["homeTeam"]["players"][0]["personId"]=b["game"]["awayTeam"]["players"][0]["personId"]
        with self.assertRaises(ValueError):official_box(b,OFF,GAME)
        b=box();b["game"]["homeTeam"]["players"][5]["played"]="1"
        with self.assertRaises(ValueError):official_box(b,OFF,GAME)
        b=box();b["game"]["gameStatus"]=2
        with self.assertRaises(ValueError):official_box(b,OFF,GAME)
    def test_unavailable_schedule_never_yields_negative(self):
        evidence={"status":STATUS,"adopt_on_site":False,
                  "no_inferred_DNP_from_unlisted_athletes":True,
                  "existing_p_play_shadow_untouched":True,"records":[{
                 "game_id":GAME["id"],"player_id":"n01","team":"CHA",
                 "game_utc":GAME["utc"],"boxscore_athlete_verdict":"ESPN_person_not_listed_in_two_team_boxscore",
                 "p_play_target_still_UNKNOWN_in_original_pipeline":True,
                 "model_training_negative":False,"first_prediction_issued_at_utc":"2026-10-26T21:00:00Z",
                 "official_source_url":"https://example.org/injury.pdf",
                 "source_ESPN_game_url":"https://example.org/espn",
                 "source_ESPN_boxscore_sha256":"abc"}]}
        explicit={"status":STATUS,"adopt_on_site":False,
                  "checked_final_game_ids":[GAME["id"]]}
        report=build(evidence,{"players":{"n01":{"confidence":"high","nba_id":"123"}}},
                     {"games":[GAME]},explicit,None,
                     lambda _: (_ for _ in ()).throw(AssertionError("network invoked")),
                     datetime(2026,10,27,12,tzinfo=timezone.utc))
        self.assertEqual(report["resolved_confirmed"],0)
        self.assertEqual(report["unresolved_unknown"],1)
        self.assertEqual(report["source_failures"],1)
        self.assertFalse(report["adopt_on_site"])
        self.assertFalse(report["records"][0]["model_training_negative"])

if __name__=="__main__":
    unittest.main()
