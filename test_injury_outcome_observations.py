import unittest
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from src.injury_outcome_observations import evaluate, monday_deadline

UTC=timezone.utc

class TestOutcomes(unittest.TestCase):
    def base(self):
        event={"event_id":"one","game_id":"g1","player_id":"n01","team":"BOS",
          "home":"NYK","away":"BOS","report_at_utc":"2026-10-25T13:00:00Z",
          "first_seen_at_utc":"2026-10-25T13:02:00Z",
          "tipoff_utc":"2026-10-25T22:00:00Z","status":"questionable"}
        game={"id":"g1","status":"final","home":"NYK","away":"BOS","utc":event["tipoff_utc"]}
        rows=[{"game_id":"g1","id":("n0" if club=="BOS" else "n1")+str(i),"team":club,"played":True,
               "minutes":20,"fp":15} for club in ("BOS","NYK") for i in range(1,8)]
        return {"status":"official_report_observed_pit_research_only","events":[event]},{
            "games":[game],"schedule":[game],"rows":rows}

    def test_positive_exact_team_minutes_fp(self):
        a,b=self.base()
        result=evaluate(a,b,datetime(2026,10,26,tzinfo=UTC))
        self.assertEqual(result["verified_played"],1)
        self.assertEqual(result["records"][0]["sports_ru_fp"],15)
        self.assertEqual(result["verified_dnp"],0)
        self.assertFalse(result["adopt_on_site"])

    def test_missing_row_remains_unknown(self):
        a,b=self.base();a["events"][0]["player_id"]="n99"
        r=evaluate(a,b,datetime(2026,10,26,tzinfo=UTC))
        self.assertEqual(r["unlisted_unknown"],1)
        self.assertEqual(r["verified_dnp"],0)

    def test_duplicate_reports_count_once_latest_before_lock(self):
        a,b=self.base();other=deepcopy(a["events"][0])
        other["event_id"]="two";other["status"]="probable"
        other["report_at_utc"]="2026-10-25T18:00:00Z"
        other["first_seen_at_utc"]="2026-10-25T18:03:00Z"
        a["events"].append(other)
        r=evaluate(a,b,datetime(2026,10,26,tzinfo=UTC))
        self.assertEqual(r["eligible_unique_player_games"],1)
        self.assertEqual(r["qa"]["superseded_pdf_observations"],1)
        self.assertEqual(r["records"][0]["official_status"],"probable")

    def test_late_report_does_not_replace_early(self):
        a,b=self.base();other=deepcopy(a["events"][0])
        other["event_id"]="late";other["status"]="available"
        other["first_seen_at_utc"]="2026-10-25T21:31:00Z"
        a["events"].append(other)
        r=evaluate(a,b,datetime(2026,10,26,tzinfo=UTC))
        self.assertEqual(r["qa"]["not_known_before_lock"],1)
        self.assertEqual(r["records"][0]["official_status"],"questionable")

    def test_future_game(self):
        a,b=self.base();r=evaluate(a,b,datetime(2026,10,25,15,tzinfo=UTC))
        self.assertEqual(r["qa"]["future_game"],1)
        self.assertEqual(r["verified_played"],0)

    def test_wrong_team_not_positive(self):
        a,b=self.base();a["events"][0]["team"]="NYK"
        r=evaluate(a,b,datetime(2026,10,26,tzinfo=UTC))
        self.assertEqual(r["verified_played"],0)
        self.assertEqual(r["records"][0]["outcome"],"missing_row_unknown")

    def test_monday_msk_deadline(self):
        d=monday_deadline(datetime(2026,10,26,22,tzinfo=UTC))
        self.assertEqual(d.isoformat(),"2026-10-26T12:00:00+00:00")

    def test_telegram_after_lock_excluded(self):
        a,b=self.base()
        t={"events":[{"id":"tg","player_ids":["n01"],"match_quality":"full_name",
          "verification":"unconfirmed_telegram","url":"https://t.me/nba_injurynews/1",
          "published_at":"2026-10-25T18:00:00Z","first_seen_at":"2026-10-25T21:31:00Z",
          "status":"out"}]}
        r=evaluate(a,b,datetime(2026,10,26,tzinfo=UTC),t)
        self.assertIsNone(r["records"][0]["telegram_context"])

    def test_telegram_context_not_ground_truth(self):
        a,b=self.base()
        t={"events":[{"id":"tg","player_ids":["n01"],"match_quality":"full_name",
          "verification":"unconfirmed_telegram","url":"https://t.me/nba_injurynews/1",
          "published_at":"2026-10-25T18:00:00Z","first_seen_at":"2026-10-25T18:02:00Z",
          "status":"out"}]}
        r=evaluate(a,b,datetime(2026,10,26,tzinfo=UTC),t)
        self.assertEqual(r["verified_played"],1)
        self.assertFalse(r["records"][0]["telegram_context"]["fixture_verified"])

if __name__=="__main__":
    unittest.main()
