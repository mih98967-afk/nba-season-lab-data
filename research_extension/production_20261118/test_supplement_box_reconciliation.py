"""Fail-closed partial archive player boxscore reconciliation regressions."""
import unittest
from supplement_reconciliation import reconcile_official_box, BOX_NUMERIC_FIELDS

GID = '0022600275'


def box(pid, pts=10, mins='27:40', **overrides):
    d = {'game_id': GID, 'person_id': pid, 'team_id': '1610612752',
         'team_tricode': 'NYK', 'season': '2027', 'season_type_id': '2',
         'side': 'home', 'jersey_num': '', 'minutes': mins,
         'comment': "DNP - Coach's Decision"}
    d.update({f: '0' for f in BOX_NUMERIC_FIELDS})
    d['points'] = str(pts)
    d.update(overrides)
    return d


class BoxReconciliationRegression(unittest.TestCase):
    def setUp(self):
        self.archive = [box('1', 10, '27:40'), box('2', 0, '')]
        self.official = [box('1', 10, str(27+40/60), jersey_num='23', comment=''),
                         box('2', 0, '0.0', jersey_num='12', comment=''),
                         box('3', 0, '0.0', jersey_num='9', comment='')]

    def test_partial_boxscore_appends_only_missing(self):
        new, ledger = reconcile_official_box(GID, self.archive, self.official)
        self.assertEqual([r['person_id'] for r in new], ['3'])
        self.assertEqual(ledger['archive_box_rows_verified_and_retained'], 2)
        self.assertEqual(ledger['new_official_box_rows_added'], 1)
        self.assertEqual(self.archive[1]['comment'], "DNP - Coach's Decision")

    def test_clean_missing_game_appends_all(self):
        new, ledger = reconcile_official_box(GID, [], self.official)
        self.assertEqual(len(new), 3)

    def test_archive_all_verified_appends_nothing(self):
        new, ledger = reconcile_official_box(GID, self.archive, self.official[:2])
        self.assertEqual(len(new), 0)

    def test_identity_and_player_conflicts_fail(self):
        for row in (box('4'), box('1', team_id='wrong'),
                    box('1', side='away'), box('1', jersey_num='88')):
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, 'SUPPLEMENT_ARCHIVE_BOXSCORE_CONFLICT'):
                reconcile_official_box(GID, [row], self.official)

    def test_duplicate_archive_fails(self):
        with self.assertRaisesRegex(ValueError, 'SUPPLEMENT_DUPLICATE_ARCHIVE_BOXSCORE_PLAYER'):
            reconcile_official_box(GID, self.archive+self.archive[:1], self.official)

    def test_duplicate_official_fails(self):
        with self.assertRaisesRegex(ValueError, 'SUPPLEMENT_OFFICIAL_BOXSCORE_IDENTITY_CONFLICT'):
            reconcile_official_box(GID, self.archive, self.official+self.official[:1])

    def test_stats_minutes_and_nan_conflicts_fail(self):
        for row in (box('1', 11), box('1', 10, '27:39'),
                    box('1', 10, '27:40', assists='1'),
                    box('1', 10, '27:40', rebounds_total='nan')):
            with self.subTest(row=row), self.assertRaises(ValueError):
                reconcile_official_box(GID, [row], self.official)

    def test_rounded_percentages_within_upstream_precision(self):
        old = box('1', 10, '27:40', field_goals_percentage='0.313')
        exact = box('1', 10, str(27+40/60), field_goals_percentage='0.3125')
        new, ledger = reconcile_official_box(GID, [old], [exact])
        self.assertEqual(new, [])
        self.assertEqual(ledger['archive_box_rows_verified_and_retained'], 1)
        with self.assertRaisesRegex(ValueError, 'FIELD_GOALS_PERCENTAGE'):
            reconcile_official_box(GID, [dict(old, field_goals_percentage='0.315')], [exact])


if __name__ == '__main__':
    unittest.main()
