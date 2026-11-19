"""The release boundary must reject stale, changed or fixture-only evidence."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_hosting_v621 as build


class ReleaseBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'site/hosting_v620'
        self.source.mkdir(parents=True)
        self.data = self.root / 'data'
        self.data.mkdir()
        self.now = dt.datetime(2026, 11, 18, 13, tzinfo=dt.timezone.utc)
        model_path = self.root / 'research_extension/production_20261118/models/MANIFEST.json'
        model_path.parent.mkdir(parents=True)
        model_path.write_text('{"synthetic":true}\n')
        self.model_sha = build.sha(model_path.read_bytes())
        for name in build.BROWSER_ASSETS:
            (self.source / name).write_text('synthetic browser fixture for ' + name)
        policy = {'site_default': True, 'economic_gain_proven': False,
                  'optimizer_policy_validated': False, 'day_ewma_selected': False,
                  'fit_current_season': False, 'intraday_injury_model_selected': False}
        self.forecast = {'schema_version': 1, 'kind': 'nba_per_game_model_forecasts',
                         'status': 'ready', 'model_policy': policy,
                         'source_capture_completed_at_utc': '2026-11-18T11:00:00Z',
                         'issued_at_utc': '2026-11-18T12:00:00Z',
                         'valid_until_utc': '2026-11-19T12:00:00Z',
                         'model_manifest_sha256': self.model_sha,
                         'source_manifest_sha256': 'a' * 64, 'rows': [{'synthetic': True}]}
        self.difficulty = {'schema': 'nba_matchup_difficulty_v1',
                           'as_of_utc': '2026-11-18T11:00:00Z',
                           'production_forecasts_adjusted': False,
                           'opponents': {f'T{i:02}': dict.fromkeys(('ALL', 'PG', 'SG', 'SF', 'PF', 'C'), {})
                                         for i in range(30)}}
        self.write('model_forecasts_v1.json', self.forecast)
        self.write('matchup_difficulty_v1.json', self.difficulty)
        self.write('live.json', {'schema_version': 4, 'mode': 'live_sync',
                                 'updated_at_utc': '2026-11-18T11:00:00Z'})
        self.write('schedule.json', {'schema_version': 1, 'games': [{'id': i} for i in range(1100)],
                                     'updated_at_utc': '2026-11-18T11:00:00Z'})
        for name, value in [('ROOT', self.root), ('SOURCE', self.source)]:
            self.addCleanup(patch.stopall)
            patch.object(build, name, value).start()

    def write(self, name, value):
        path = self.data / name
        path.write_text(json.dumps(value) + '\n')
        return path

    def evidence(self):
        generated, meta = build.snapshots(self.data, self.now)
        parity = {'schema': 'nba_frozen_release_qa_v1', 'status': 'PASS',
                  'feed_sha256': build.sha(generated['data/model_forecasts_v1.json']),
                  'model_manifest_sha256': self.model_sha,
                  'source_manifest_sha256': self.forecast['source_manifest_sha256'],
                  'feed_issued_at_utc': self.forecast['issued_at_utc'],
                  'feed_valid_until_utc': self.forecast['valid_until_utc'],
                  'verified_at_utc': '2026-11-18T12:10:00Z'}
        browser = {'schema': 'nba_hosting_browser_qa_v1', 'status': 'PASS', 'mode': 'actual',
                   'verified_at_utc': '2026-11-18T12:20:00Z',
                   'data_sha256': {Path(n).name: build.sha(v) for n, v in generated.items()},
                   'source_sha256': {n: build.sha((self.source / n).read_bytes()) for n in build.BROWSER_ASSETS}}
        return generated, meta, self.write('RELEASE_QA.json', parity), self.write('BROWSER_QA.json', browser)

    def test_same_bytes_have_complete_evidence(self):
        generated, meta, parity, browser = self.evidence()
        result = build.release_evidence(parity, browser, generated, meta)
        self.assertEqual(result['weight_prediction_parity'], 'PASS')
        self.assertEqual(result['actual_data_browser_qa'], 'PASS')

    def test_expired_feed_cannot_be_repackaged_as_new_release(self):
        self.forecast['valid_until_utc'] = '2026-11-18T12:59:00Z'
        self.write('model_forecasts_v1.json', self.forecast)
        with self.assertRaisesRegex(AssertionError, 'expired'):
            build.snapshots(self.data, self.now)

    def test_a_fixture_browser_pass_is_not_actual_data_acceptance(self):
        generated, meta, parity, browser = self.evidence()
        obj = json.loads(browser.read_text()); obj['mode'] = 'fixture'; browser.write_text(json.dumps(obj))
        with self.assertRaisesRegex(AssertionError, 'Synthetic'):
            build.release_evidence(parity, browser, generated, meta)

    def test_changed_prediction_bytes_invalidate_passed_qa(self):
        generated, meta, parity, browser = self.evidence()
        generated['data/model_forecasts_v1.json'] += b' '
        with self.assertRaisesRegex(AssertionError, 'different forecast bytes'):
            build.release_evidence(parity, browser, generated, meta)

    def test_changed_calendar_invalidates_browser_acceptance(self):
        generated, meta, parity, browser = self.evidence()
        generated['data/matchup_difficulty_v1.json'] += b' '
        with self.assertRaisesRegex(AssertionError, 'different public data'):
            build.release_evidence(parity, browser, generated, meta)

    def test_layout_changes_require_another_browser_check(self):
        generated, meta, parity, browser = self.evidence()
        (self.source / 'styles.css').write_text('changed after browser check')
        with self.assertRaisesRegex(AssertionError, 'source changed: styles.css'):
            build.release_evidence(parity, browser, generated, meta)

    def test_partial_position_grid_cannot_look_complete(self):
        del self.difficulty['opponents']['T00']['PG']
        self.write('matchup_difficulty_v1.json', self.difficulty)
        with self.assertRaisesRegex(AssertionError, 'five positional'):
            build.snapshots(self.data, self.now)

    def test_different_weights_manifest_is_not_the_tested_release(self):
        self.forecast['model_manifest_sha256'] = 'b' * 64
        self.write('model_forecasts_v1.json', self.forecast)
        with self.assertRaisesRegex(AssertionError, 'weights manifest differs'):
            build.snapshots(self.data, self.now)


if __name__ == '__main__':
    unittest.main()
