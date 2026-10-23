"""Deterministic offline tests for UTC/Moscow NBA calendar."""
import datetime as dt
import unittest
from src.schedule_sync import UTC, TEAMS, assemble, moscow_week, parse_events, segments

def event(i,stamp,home="BOS",away="NYK",season=2):
    return {"id":str(i),"date":stamp,"season":{"type":season},
            "status":{"type":{"state":"pre","completed":False}},
            "competitions":[{"competitors":[
                {"homeAway":"home","team":{"abbreviation":home}},
                {"homeAway":"away","team":{"abbreviation":away}}]}]}

class CalendarTests(unittest.TestCase):
    def test_moscow_sunday_to_monday(self):
        self.assertEqual(moscow_week("2026-10-25T20:30:00Z"),"2026-10-19")
        self.assertEqual(moscow_week("2026-10-25T21:00:00Z"),"2026-10-26")
        self.assertEqual(moscow_week("2026-10-26T11:59:00Z"),"2026-10-26")
        self.assertEqual(moscow_week("2026-10-26T12:00:00Z"),"2026-10-26")
        self.assertEqual(moscow_week("2027-03-14T22:30:00Z"),"2027-03-15")
    def test_parse_season_and_zone_offsets(self):
        a=event(101,"2026-10-25T21:15:00Z")
        b=event(102,"2026-10-26T01:00:00-04:00")
        c=event(103,"2026-10-25T21:00:00Z",season=1)
        got=parse_events({"events":[a,b,c]})
        self.assertEqual(len(got),2)
        self.assertEqual(got[0]["msk_date"],"2026-10-26")
        self.assertEqual(got[1]["utc"],"2026-10-26T05:00:00Z")
    def test_segments_no_missing_days(self):
        chunks=list(segments(length=12))
        self.assertEqual(chunks[0][0],dt.date(2026,10,20))
        self.assertEqual(chunks[-1][1],dt.date(2027,4,11))
        self.assertEqual(sum((b-a).days+1 for a,b in chunks),174)
    def test_truncated_feed_rejected(self):
        with self.assertRaisesRegex(ValueError,"full-calendar validation failed"):
            assemble([{"events":[event(1,"2026-10-20T19:00:00Z")]}])
    def test_calendar_1200_known_cup_unassigned(self):
        teams=sorted(TEAMS);days=[]
        for i in range(80):
            day=dt.date(2026,10,20)+dt.timedelta(days=i*2)
            rotate=teams[i%30:]+teams[:i%30]
            games=[event(i*15+j,day.isoformat()+"T23:00:00Z",rotate[j],rotate[j+15]) for j in range(15)]
            days.append({"events":games})
        result=assemble(days,dt.datetime(2026,10,23,tzinfo=UTC))
        self.assertEqual(len(result["games"]),1200)
        self.assertEqual(result["completeness"]["teams"],30)
        self.assertEqual(result["completeness"]["unassigned_or_unavailable_games"],30)

if __name__=="__main__":unittest.main()
