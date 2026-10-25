import unittest
from datetime import datetime,timezone
from src.official_injury_archive import extract_index,update,asof
URL='https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-10-25_05_15AM.pdf'
BODY=('<a href="'+URL+'">NBA</a>').encode()
PDF=b'%PDF-1.7 '+b'X'*3500
class TestInventory(unittest.TestCase):
 def test_et_to_utc(self):
  self.assertEqual(extract_index(BODY)[0]['report_at_utc'],'2026-10-25T09:15:00Z')
 def test_no_hindsight(self):
  data=update(BODY,PDF,now=datetime(2026,10,25,11,tzinfo=timezone.utc))
  self.assertEqual(asof(data['snapshots'],'2026-10-25T10:00:00Z'),[])
  self.assertEqual(len(asof(data['snapshots'],'2026-10-25T11:00:00Z')),1)
 def test_append_only_first_seen(self):
  a=update(BODY,PDF,now=datetime(2026,10,25,11,tzinfo=timezone.utc))
  b=update(BODY,PDF,a,now=datetime(2026,10,25,12,tzinfo=timezone.utc))
  self.assertEqual(a['snapshots'][0]['first_seen_at_utc'],b['snapshots'][0]['first_seen_at_utc'])
 def test_not_a_pdf(self):
  with self.assertRaises(ValueError):update(BODY,b'bad',now=datetime(2026,10,25,11,tzinfo=timezone.utc))
if __name__=='__main__':unittest.main()
