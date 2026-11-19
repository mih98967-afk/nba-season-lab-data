import unittest
from src.official_injury_rows import norm,parse_pages,group_lines,validate_extracted_status_rows
class FakePage:
 def __init__(self,words):self.words=words
 def extract_words(self,**kwargs):return self.words
def word(x,top,text):return {"x0":x,"top":top,"text":text}
class TestOfficial(unittest.TestCase):
 def test_normalize(self):self.assertEqual(norm("Dončić, Luka"),"luka doncic")
 def test_official_row_only(self):
  words=[word(24,128,"10/25/2026"),word(201,128,"LAL@UTA"),
    word(265,128,"Los"),word(281,128,"Angeles"),word(316,128,"Lakers"),
    word(426,128,"Carr,"),word(448,128,"Cameron"),word(586,128,"Out"),
    word(426,151,"Kessler,"),word(459,151,"Walker"),word(586,151,"Available"),
    word(266,151,"Utah"),word(289,151,"Jazz"),
    word(586,176,"NOT"),word(610,176,"YET"),word(630,176,"SUBMITTED")]
  rows,qa=parse_pages([FakePage(words)])
  self.assertEqual(len(rows),2)
  self.assertEqual(rows[0]["team"],"LAL")
  self.assertEqual(rows[1]["team"],"UTA")
  self.assertEqual(qa["not_yet_submitted_team"],1)
 def test_small_complete_official_slate_is_valid(self):
  words=[word(24,128,"10/25/2026"),word(201,128,"LAL@UTA"),
    word(265,128,"Los"),word(281,128,"Angeles"),word(316,128,"Lakers"),
    word(426,128,"Carr,"),word(448,128,"Cameron"),word(586,128,"Out")]
  page=FakePage(words)
  rows,qa=parse_pages([page])
  self.assertEqual(len(rows),1)
  self.assertTrue(validate_extracted_status_rows([page],rows)["status_cell_coverage_complete"])
 def test_unanchored_status_cell_rejected(self):
  page=FakePage([word(426,135,"Carr,"),word(460,135,"Cameron"),word(586,135,"Out")])
  rows,_=parse_pages([page])
  with self.assertRaisesRegex(ValueError,"context incomplete"):
   validate_extracted_status_rows([page],rows)
 def test_duplicate_official_player_game_rejected(self):
  words=[word(24,128,"10/25/2026"),word(201,128,"LAL@UTA"),
    word(265,128,"Los"),word(281,128,"Angeles"),word(316,128,"Lakers"),
    word(426,128,"Carr,"),word(448,128,"Cameron"),word(586,128,"Out"),
    word(426,151,"Carr,"),word(448,151,"Cameron"),word(586,151,"Out")]
  page=FakePage(words)
  rows,_=parse_pages([page])
  with self.assertRaisesRegex(ValueError,"Duplicate player"):
   validate_extracted_status_rows([page],rows)
 def test_no_context(self):
  rows,qa=parse_pages([FakePage([word(426,135,"Carr,"),word(460,135,"Cameron"),word(586,135,"Out")])])
  self.assertEqual(len(rows),0)

 def test_continuation_row_above_old_crop_keeps_full_context(self):
  first=FakePage([word(24,128,"11/18/2026"),word(201,128,"LAL@UTA"),
   word(265,128,"Los Angeles Lakers"),word(426,128,"Carr, Cameron"),word(586,128,"Out")])
  second=FakePage([word(201,83.61,"PHX@SAC"),word(265,83.61,"Sacramento Kings"),
   word(426,83.61,"Carter, Devin"),word(586,83.61,"Questionable")])
  rows,_=parse_pages([first,second])
  self.assertEqual(len(rows),2)
  self.assertEqual((rows[1]["away"],rows[1]["home"],rows[1]["team"]),("PHX","SAC","SAC"))
  self.assertEqual(validate_extracted_status_rows([first,second],rows)["explicit_status_cells"],2)
 def test_continuation_team_switch_is_not_inherited_from_previous_page(self):
  first=FakePage([word(24,128,"11/18/2026"),word(201,128,"LAL@UTA"),
   word(265,128,"Los Angeles Lakers"),word(426,128,"Carr, Cameron"),word(586,128,"Out")])
  second=FakePage([word(265,83.61,"Utah Jazz"),word(426,83.61,"Kessler, Walker"),word(586,83.61,"Out"),
   word(426,109,"Collier, Isaiah"),word(586,109,"Available")])
  rows,_=parse_pages([first,second])
  self.assertEqual([r["team"] for r in rows],["LAL","UTA","UTA"])
  self.assertTrue(validate_extracted_status_rows([first,second],rows)["status_cell_coverage_complete"])
 def test_unanchored_top_cell_is_counted_and_rejected(self):
  page=FakePage([word(426,83.61,"Carr, Cameron"),word(586,83.61,"Out")])
  rows,_=parse_pages([page])
  with self.assertRaisesRegex(ValueError,"parsed=0 cells=1"):
   validate_extracted_status_rows([page],rows)
 def test_semantic_columns_allow_lower_real_row(self):
  page=FakePage([word(24,592,"11/18/2026"),word(201,592,"LAL@UTA"),
   word(265,592,"Los Angeles Lakers"),word(426,592,"Carr, Cameron"),word(586,592,"Out")])
  rows,_=parse_pages([page])
  self.assertEqual(len(rows),1)
  self.assertTrue(validate_extracted_status_rows([page],rows)["status_cell_coverage_complete"])
 def test_heading_and_page_number_do_not_create_a_status(self):
  page=FakePage([word(24,35,"Injury Report"),word(426,60,"Player Name"),word(586,60,"Current Status"),
   word(24,128,"11/18/2026"),word(201,128,"LAL@UTA"),word(265,128,"Los Angeles Lakers"),
   word(426,128,"Carr, Cameron"),word(586,128,"Out"),word(586,610,"Page 1 of 3")])
  rows,_=parse_pages([page])
  self.assertEqual(validate_extracted_status_rows([page],rows)["explicit_status_cells"],1)
 def test_invisible_fragments_do_not_make_a_line(self):
  self.assertEqual(group_lines([word(24,83,""),word(120,83,"   ")]),[])
if __name__=='__main__':unittest.main()
