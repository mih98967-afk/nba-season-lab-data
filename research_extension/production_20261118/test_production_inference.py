from pathlib import Path
import copy
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from model_store import HERE,ROOT,KNOWN_MODELS,assemble_model_bytes,load_model,load_manifest,sha256
from inference import calibration_bucket,check_predictions,PREDICTION_COLUMNS,predict_long_actual,predict_current
from export_feed import windows_for_rows,legacy_fallback,utc,schedule_key,injury_reason,check_freshness,finalize_issuance,SEED_EXCLUSIONS,publish_live_feed
from injury_extension import apply_shadow


class FrozenInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.near=load_model('near_latest');cls.long=load_model('long_latest')
        cls.fixture=json.loads((HERE/'long_parity_fixture.json').read_text())
        cls.frame=pd.DataFrame(cls.fixture['features'])

    def test_all_bundles_are_original_bytes(self):
        for name,digest in KNOWN_MODELS.items():self.assertEqual(sha256(assemble_model_bytes(name)),digest)

    def test_model_tamper_is_rejected_before_unpickle(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp);shutil.copytree(HERE/'models',dest/'models')
            chunk=next((dest/'models').glob('near_latest.*.b64'))
            blob=chunk.read_bytes();chunk.write_bytes(b'X'+blob[1:])
            with self.assertRaisesRegex(ValueError,'CHUNK_HASH'):assemble_model_bytes('near_latest',dest/'models')

    def test_manifest_cannot_select_untrusted_model(self):
        with self.assertRaisesRegex(ValueError,'UNKNOWN_TRUSTED'):assemble_model_bytes('external_pickle')

    def test_long_original_prediction_parity_all_anchors(self):
        actual=predict_long_actual(self.long,self.frame)
        expected=pd.DataFrame(self.fixture['expected'])
        np.testing.assert_allclose(actual[PREDICTION_COLUMNS],expected[PREDICTION_COLUMNS],rtol=1e-10,atol=1e-8)

    def test_near_original_fixture_parity(self):
        choices=[ROOT/'research/match_context/fixtures/near_game_parity_20261116.json',
                 ROOT/'nba-release-20261118/research/match_context/fixtures/near_game_parity_20261116.json']
        path=next((p for p in choices if p.is_file()),None)
        self.assertIsNotNone(path,'Preserved public near fixture must be shipped with release')
        fixture=json.loads(path.read_text());frame=pd.DataFrame(fixture['features'])
        from infer_near import predict_near
        pred=predict_near(self.near,frame)
        fields=fixture['expected_prediction_fields'];expected=pd.DataFrame(fixture['expected_predictions'])
        np.testing.assert_allclose(pred[fields],expected[fields],rtol=1e-7,atol=1e-7)

    def test_actual_horizon_remains_model_input(self):
        frame=self.frame.iloc[2:3].copy();frame['horizon_days']=2
        out=predict_long_actual(self.long,frame)
        self.assertEqual(frame.horizon_days.iloc[0],2)
        self.assertEqual(calibration_bucket(2),3)
        check_predictions(out)

    def test_invalid_horizon_rejected(self):
        for value in (-1,29,1.5,float('nan')):
            with self.assertRaises(ValueError):calibration_bucket(value)

    def test_target_outcomes_blocked(self):
        frame=self.frame.copy();frame['y_play']=np.nan
        with self.assertRaisesRegex(ValueError,'TARGET_LABEL'):predict_current(frame,self.near,self.long)

    def test_missing_model_feature_falls_back(self):
        frame=self.frame[self.frame.horizon_days==3].copy().reset_index(drop=True)
        frame.loc[0,'min10']=np.nan
        _,valid,_=predict_current(frame,self.near,self.long)
        self.assertFalse(valid[0]);self.assertTrue(valid[1])

    def test_expected_value_can_be_negative(self):
        row={c:0. for c in PREDICTION_COLUMNS};row.update(p_play=.5,mean_if_play=-4.,expected_fp=-2.)
        for pr in ('conditional_',''):
            for n in (50,80,95):row[f'{pr}lo{n}']=-10;row[f'{pr}hi{n}']=2
        self.assertTrue(check_predictions(pd.DataFrame([row])))

    def test_nonfinite_probability_rejected(self):
        p=predict_long_actual(self.long,self.frame.iloc[:1]).copy();p.loc[0,'p_play']=np.nan
        with self.assertRaisesRegex(ValueError,'NONFINITE'):check_predictions(p)

    def test_crossed_interval_rejected(self):
        p=predict_long_actual(self.long,self.frame.iloc[:1]).copy();p.loc[0,'lo80']=100;p.loc[0,'hi80']=-100
        with self.assertRaisesRegex(ValueError,'CROSSED'):check_predictions(p)

    def test_window_sums_expectation_not_endpoints(self):
        rows=[dict(player_id='n1',game_utc='2026-11-19T01:00:00Z',expected_fp=10,mean_if_play=20,p_play=.5,
                   support='exact_lead',eligible_for_decision=True,unconditional_intervals={'80':[-5,30]})]
        w=windows_for_rows(rows,'2026-11-18T12:00:00Z',True)[0]
        self.assertEqual(w['expected_fp'],10);self.assertIsNone(w['predictive_intervals'])

    def test_unknown_window_is_not_zero(self):
        rows=[dict(player_id='n1',game_utc='2026-11-19T01:00:00Z',expected_fp=None,mean_if_play=None,p_play=None,
                   support='unavailable',eligible_for_decision=False)]
        w=windows_for_rows(rows,'2026-11-18T12:00:00Z')[0]
        self.assertIsNone(w['expected_fp']);self.assertEqual(w['unavailable_games'],1)

    def test_no_seed_no_fabricated_cold_start(self):
        self.assertIsNone(legacy_fallback({'id':'n1','forecast':False},{'id':'g','utc':'2026-11-19T01:00:00Z'}, {},'2026-11-18T12:00:00Z'))

    def test_naive_source_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError,'NAIVE'):utc('2026-11-18T12:00:00')

    def test_moscow_date_does_not_replace_nba_date(self):
        self.assertEqual(schedule_key({'home':'BOS','away':'NYK','utc':'2026-11-19T01:00:00Z'})[0],'2026-11-18')

    def test_bucket_failures_are_preserved(self):
        report=json.loads((HERE/'BUCKET_ELIGIBILITY.json').read_text())['actual_horizons']
        self.assertTrue(report['2']['eligible']);self.assertFalse(report['18']['eligible'])
        self.assertEqual(report['22']['known'],0)


    def test_contaminated_seeds_never_fallback(self):
        for pid in SEED_EXCLUSIONS:
            self.assertIsNone(legacy_fallback({'id':pid,'forecast':True,'mean_if_play':30,'availability_p1':.9},
                                             {'id':'g','utc':'2026-11-19T01:00:00Z'}, {},'2026-11-18T12:00:00Z'))

    def test_reason_is_plain_russian_not_machine_enum(self):
        reason=injury_reason('REPORT_NOT_AVAILABLE_AT_FEATURE_CUTOFF')
        self.assertNotIn('REPORT_',reason);self.assertIn('вероятность основана на истории',reason)

    def test_fresh_capture_with_missing_final_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'current').mkdir()
            (root/'current/manifest.json').write_text('[]')
            (root/'current/nba_schedule_2027.csv.gz').write_bytes(__import__('gzip').compress(b'game_date,home_team_abbreviation,away_team_abbreviation,home_pts,away_pts\n2026-11-16,BOS,NYK,110,100\n'))
            game={'id':'g','utc':'2026-11-18T01:00:00Z','home':'LAL','away':'PHX','status':'final'}
            qa={'status':'INTERNAL_COHERENCE_PASS','schedule':{'latest_coherent_completed_date':'2026-11-16'}}
            result=check_freshness(root,qa,{'completed_at_utc':'2026-11-18T11:59:00Z'},{'games':[game]},
                                   {'updated_at_utc':'2026-11-18T11:50:00Z'},'2026-11-18T12:00:00Z','2026-11-18')
            self.assertFalse(result['fresh']);self.assertIn('COMPLETED_GAMES_MISSING_FROM_MODEL_HISTORY',result['failures'])

    def test_fresh_live_feed_cannot_refresh_a_stale_full_calendar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'current').mkdir()
            (root/'current/manifest.json').write_text('[]')
            (root/'current/nba_schedule_2027.csv.gz').write_bytes(__import__('gzip').compress(b'game_date,home_team_abbreviation,away_team_abbreviation,home_pts,away_pts\n2026-11-17,BOS,NYK,110,100\n'))
            qa={'status':'INTERNAL_COHERENCE_PASS','schedule':{'latest_coherent_completed_date':'2026-11-17'}}
            result=check_freshness(root,qa,{'completed_at_utc':'2026-11-18T11:59:00Z'},
                {'games':[],'updated_at_utc':'2026-11-10T12:00:00Z'},
                {'updated_at_utc':'2026-11-18T11:50:00Z'},'2026-11-18T12:00:00Z','2026-11-18')
            self.assertFalse(result['fresh']);self.assertIn('UTC_SCHEDULE_STALE',result['failures'])

    def test_intraday_shadow_never_mutates_base_features(self):
        frame=self.frame[self.frame.horizon_days==0].copy().reset_index(drop=True)
        frame['date']='2026-11-18';frame['issue_date']='2026-11-18'
        before=frame.copy(deep=True);row=frame.iloc[0]
        home=str(row.team) if row.home else str(row.opp);away=str(row.opp) if row.home else str(row.team)
        state={'nba_game_id':str(row.game),'calendar_game_id':'public1','date_ET':'2026-11-18','team':str(row.team),
               'home':home,'away':away,'tipoff_utc':'2026-11-19T01:00:00Z','report_at_utc':'2026-11-18T10:00:00Z',
               'available_at_utc':'2026-11-18T11:00:00Z','NOT_YET_SUBMITTED':False,'allow_missing_player_as_NOT_LISTED_feature':True}
        event=dict(state,nba_player_id=str(row.pid),status='questionable',source_url='https://example.test/report.pdf',source_sha256='a'*64)
        artifact={'schema':'nba-fresh-official-pdf-exact-ID-status-v1','native_cells_complete':True,
                  'minimum_inference_issue_after_utc':'2026-11-18T11:01:00Z','team_report_states':[state],'events':[event]}
        annotations,shadow,qa=apply_shadow(frame,self.near,artifact,'2026-11-18T12:00:00Z',
                                         [{'id':'public1','home':home,'away':away,'utc':state['tipoff_utc']}])
        pd.testing.assert_frame_equal(frame,before)
        self.assertEqual(annotations[0]['status'],'questionable');self.assertTrue(shadow[0]['timing_extension_not_validated'])
        self.assertFalse(qa['base_model_changed']);self.assertFalse(shadow[0]['selected_for_production'])

    def test_future_official_status_cannot_enter_shadow(self):
        artifact={'schema':'nba-fresh-official-pdf-exact-ID-status-v1','native_cells_complete':True,
                  'minimum_inference_issue_after_utc':'2026-11-19T12:00:00Z'}
        with self.assertRaisesRegex(ValueError,'NOT_YET_AVAILABLE'):
            apply_shadow(self.frame,self.near,artifact,'2026-11-18T12:00:00Z',[])

    def test_optional_newer_pdf_does_not_extend_core_input_expiry(self):
        feed={'asof_date_et':'2026-11-18','source_capture_completed_at_utc':'2026-11-18T11:59:00Z',
              'core_source_capture_completed_at_utc':'2026-11-17T00:01:00Z','rows':[],'coverage':{}}
        finalize_issuance(feed,utc('2026-11-18T12:00:00Z'))
        self.assertEqual(feed['valid_until_utc'],'2026-11-18T12:01:00Z')

    def test_stale_publication_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'feed.json';path.write_text('previous verified feed')
            with self.assertRaisesRegex(ValueError,'REFUSE_TO_PUBLISH_STALE'):
                publish_live_feed({'status':'stale_inputs','source_quality':{'fresh':False}},path)
            self.assertEqual(path.read_text(),'previous verified feed')

    def test_nonfinite_publication_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'feed.json';path.write_text('previous verified feed')
            feed={'status':'ready','source_quality':{'fresh':True},'valid_until_utc':'2026-11-19T12:00:00Z',
                  'source_capture_completed_at_utc':'2026-11-18T11:00:00Z','bad':float('nan')}
            with self.assertRaises(ValueError):publish_live_feed(feed,path,utc('2026-11-18T12:00:00Z'))
            self.assertEqual(path.read_text(),'previous verified feed')

    def test_expired_feed_is_not_skipped_by_unchanged_cadence(self):
        from refresh_decision import decision
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').mkdir()
            (root/'data/model_forecasts_v1.json').write_text(json.dumps({'refresh_fingerprint':'same','status':'ready',
                'issued_at_utc':'2026-11-18T11:00:00Z','valid_until_utc':'2026-11-18T11:30:00Z'}))
            with patch('refresh_decision.fingerprint',return_value='same'):
                result=decision(root,now=utc('2026-11-18T12:00:00Z'))
            self.assertTrue(result['refresh'])

    def test_missing_ids_cannot_authorize_an_official_out_overlay(self):
        from verify_release import verify_annotation
        row={'official_status':{'exact_player_team_game_time':True,'status':'out'},'nba_id':None,'nba_game_id':None}
        with self.assertRaisesRegex(ValueError,'INVALID_ANNOTATED_PLAYER_ID'):
            verify_annotation(row,utc('2026-11-18T12:00:00Z'))

    def test_reviewed_current_identity_never_backdates_into_old_forecast(self):
        from catalog_identity import apply_reviewed_identity
        overlay={'schema':'nba_catalog_identity_overlay_v1','observed_at_utc':'2026-11-18T12:51:00Z','players':{}}
        with self.assertRaisesRegex(ValueError,'NOT_YET_OBSERVED'):
            apply_reviewed_identity({}, {},'2026-11-17T12:00:00Z',overlay=overlay)

    def test_identity_overlay_rejects_changed_catalog_fingerprint(self):
        from catalog_identity import apply_reviewed_identity
        overlay={'schema':'nba_catalog_identity_overlay_v1','observed_at_utc':'2026-11-18T12:51:00Z','players':{
            'n1':{'nba_id':'1642484','confidence':'high','catalog_name':'Current player','catalog_team':'ATL','catalog_position':'PG'}}}
        with self.assertRaisesRegex(ValueError,'FINGERPRINT_MISMATCH'):
            apply_reviewed_identity({}, {'n1':{'name':'Another player','team':'ATL','pos':'PG'}},'2026-11-18T13:00:00Z',overlay=overlay)

    def test_identity_overlay_rejects_duplicate_nba_ids(self):
        from catalog_identity import apply_reviewed_identity
        player={'name':'Current player','team':'ATL','pos':'PG'}
        entry={'nba_id':'1642484','confidence':'high','catalog_name':player['name'],'catalog_team':'ATL','catalog_position':'PG'}
        overlay={'schema':'nba_catalog_identity_overlay_v1','observed_at_utc':'2026-11-18T12:51:00Z','players':{'n1':entry,'n2':entry}}
        with self.assertRaisesRegex(ValueError,'DUPLICATE_NBA_ID'):
            apply_reviewed_identity({}, {'n1':player,'n2':player},'2026-11-18T13:00:00Z',overlay=overlay)


class OfficialSupplementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0,str(ROOT/'research_extension/prospective_20261118'))
        from derive_current_supplement import normalize
        cls.normalize=staticmethod(normalize)
        cls.payload=json.loads((HERE/'fixtures/official_game_0022600253.json').read_text())
        g=cls.payload['game']
        cls.calendar={'id':'espn_401910002','utc':g['gameTimeUTC'],'home':g['homeTeam']['teamTricode'],'away':g['awayTeam']['teamTricode']}
        cls.official={'id':str(g['gameId']),'utc':g['gameTimeUTC'],'home':g['homeTeam']['teamTricode'],'away':g['awayTeam']['teamTricode']}

    def test_exact_complete_official_final_normalizes(self):
        box,inactive,schedule=self.normalize(self.payload,self.official,self.calendar)
        self.assertEqual(len(box),34);self.assertEqual(len(inactive),7);self.assertEqual(schedule['game_date'],'2026-11-17')

    def test_active_zero_without_reason_stays_unknown(self):
        box,inactive,_=self.normalize(self.payload,self.official,self.calendar)
        ids={r['player_id'] for r in inactive}
        original={str(p['personId']):p for team in ('homeTeam','awayTeam') for p in self.payload['game'][team]['players']}
        checked=0
        for row in box:
            p=original[row['person_id']]
            if p['status']=='ACTIVE' and str(p['played'])=='0' and not p.get('notPlayingReason'):
                self.assertEqual(row['comment'],'');self.assertNotIn(row['person_id'],ids);checked+=1
        self.assertGreater(checked,0)

    def test_wrong_game_identity_fails(self):
        with self.assertRaises(ValueError):self.normalize(self.payload,dict(self.official,id='0022600999'),self.calendar)

    def test_incomplete_team_points_fail(self):
        payload=copy.deepcopy(self.payload);payload['game']['homeTeam']['score']+=1
        with self.assertRaisesRegex(ValueError,'Incomplete official team totals'):
            self.normalize(payload,self.official,self.calendar)

    def test_positive_minute_missing_stat_fails(self):
        payload=copy.deepcopy(self.payload)
        player=next(p for p in payload['game']['homeTeam']['players'] if str(p['played'])=='1')
        player['statistics']['points']=None
        with self.assertRaisesRegex(ValueError,'Invalid played stat component'):
            self.normalize(payload,self.official,self.calendar)


if __name__=='__main__':unittest.main()
