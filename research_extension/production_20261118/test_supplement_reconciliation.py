"""Offline regression for partial archive + complete official NBA finals."""
import unittest
from supplement_reconciliation import reconcile_official_inactive


GID = '0022600274'


def box(pid, team='PHI'):
    return {'game_id': GID, 'person_id': pid, 'team_tricode': team}


def inactive(pid, team='PHI', team_id='1610612755', name='Normalized'):
    return {'game_id': GID, 'player_id': pid, 'team_id': team_id,
            'team_abbreviation': team, 'season': '2027', 'season_type_id': '2',
            'jersey_num': '7', 'last_name': name}


class SourceReconciliationRegressionTests(unittest.TestCase):
    def setUp(self):
        self.official_box = [box('1627759'), box('1630574'), box('1641737')]
        self.official_inactive = [inactive('1627759'), inactive('1630574'), inactive('1641737')]

    def test_archive_inactive_can_arrive_before_box_and_scores(self):
        archived = [dict(inactive('1627759'), last_name='Brown'),
                    dict(inactive('1630574'), last_name='Hukporti')]
        appended, ledger = reconcile_official_inactive(GID, [], archived,
                                                      self.official_box, self.official_inactive)
        self.assertEqual([row['player_id'] for row in appended], ['1641737'])
        self.assertEqual(ledger['archive_inactive_rows_verified_and_retained'], 2)
        self.assertEqual(ledger['new_official_inactive_rows_added'], 1)
        self.assertFalse(ledger['unknown_assumed_inactive'])
        self.assertEqual(len({r['player_id'] for r in archived + appended}), 3)
        self.assertEqual(len(archived), 2)  # no in-place mutation

    def test_clean_missing_game_adds_only_official_rows(self):
        appended, ledger = reconcile_official_inactive(GID, [], [],
                                                      self.official_box, self.official_inactive)
        self.assertEqual(len(appended), 3)
        self.assertEqual(ledger['archive_inactive_rows_verified_and_retained'], 0)

    def test_full_unchanged_archive_reuses_all_inactives(self):
        appended, ledger = reconcile_official_inactive(GID, [], list(self.official_inactive),
                                                      self.official_box, self.official_inactive)
        self.assertEqual(appended, [])
        self.assertEqual(ledger['archive_inactive_rows_verified_and_retained'], 3)

    def test_conflicting_player_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SUPPLEMENT_ARCHIVE_INACTIVE_CONFLICT:PLAYER'):
            reconcile_official_inactive(GID, [], [inactive('not-an-inactive-player')],
                                        self.official_box, self.official_inactive)

    def test_conflicting_team_or_jersey_is_rejected(self):
        for changed in (dict(inactive('1627759'), team_id='wrong'),
                        dict(inactive('1627759'), jersey_num='99')):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'SUPPLEMENT_ARCHIVE_INACTIVE_CONFLICT'):
                reconcile_official_inactive(GID, [], [changed], self.official_box, self.official_inactive)

    def test_duplicate_archive_inactive_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SUPPLEMENT_DUPLICATE_ARCHIVE_INACTIVE_PLAYER'):
            reconcile_official_inactive(GID, [], [inactive('1627759'), inactive('1627759')],
                                        self.official_box, self.official_inactive)

    def test_duplicate_official_inactive_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SUPPLEMENT_DUPLICATE_OFFICIAL_INACTIVE_PLAYER'):
            reconcile_official_inactive(GID, [], [], self.official_box,
                                        self.official_inactive + [inactive('1627759')])

    def test_archive_boxscore_is_still_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'SUPPLEMENT_DUPLICATES_ARCHIVE_ROWS'):
            reconcile_official_inactive(GID, [box('1627759')], [],
                                        self.official_box, self.official_inactive)

    def test_official_box_identity_is_verified(self):
        with self.assertRaisesRegex(ValueError, 'SUPPLEMENT_DUPLICATE_OFFICIAL_BOXSCORE_PLAYER'):
            reconcile_official_inactive(GID, [], [], self.official_box + [box('1627759')],
                                        self.official_inactive)

    def test_inactive_not_listed_in_boxscore_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SUPPLEMENT_OFFICIAL_INACTIVE_IDENTITY_CONFLICT'):
            reconcile_official_inactive(GID, [], [], self.official_box,
                                        self.official_inactive + [inactive('missing')])


if __name__ == '__main__':
    unittest.main()
