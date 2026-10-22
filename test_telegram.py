import datetime as dt
import unittest
from src.telegram_feed import parse_posts,build_feed,player_aliases,matches_for_line,fetch_posts
NOW=dt.datetime(2026,10,22,12,tzinfo=dt.timezone.utc)
HTML='''<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="nba_injurynews/845"><div class="tgme_widget_message_text">Amen Thompson (knee) questionable tonight.<br>Jaylen Brown available to play.</div><time datetime="2026-10-22T10:20:00+00:00"></time></div></div>'''
CAT={"players":[{"id":"a","english":"Amen Thompson"},{"id":"b","english":"Jaylen Brown"},{"id":"c","english":"Troy Brown Jr"},{"id":"d","english":"Ausar Thompson"},{"id":"e","english":"Jalen Johnson"}]}
class Tests(unittest.TestCase):
    def test_extraction(self):
        p=parse_posts(HTML);self.assertEqual(len(p),1);self.assertIn("Amen Thompson",p[0]["text"])
    def test_alerts(self):
        a=build_feed(parse_posts(HTML),CAT,now=NOW)["events"]
        self.assertEqual({e["player_ids"][0] for e in a},{"a","b"})
        self.assertEqual({e["status"] for e in a},{"questionable","available"})
    def test_ambiguous_alias(self):
        a=player_aliases(CAT)
        self.assertEqual(matches_for_line("Brown is out",a),{})
        self.assertEqual(matches_for_line("Thompson questionable",a),{})
    def test_empty_html_rejected(self):
        with self.assertRaises(ValueError):fetch_posts(lambda _: "<html></html>")
if __name__=="__main__":unittest.main()
