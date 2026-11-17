"""Missing crosswalks must survive in the denominator without invented negatives."""
import unittest
from copy import deepcopy
from datetime import datetime, timezone
import test_official_nba_inactive_retry_research as fixtures
from test_official_nba_inactive_summary_research import input_reports, payload, GID
from src.official_nba_inactive_summary_research import plan_requests, reconcile, known_game_ids, UNKNOWN, VERIFIED
class MissingGameIdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.Catchup.setUpClass()
        cls.data,cls.espn,cls.live,cls.now=fixtures.Catchup.nba,fixtures.Catchup.espn,fixtures.Catchup.live,fixtures.Catchup.test_now
    def test_actual_missing_rows_preserved_without_requests(self):
        missing=sum(r.get('nba_game_id') is None for r in self.data['records'])
        req,defer,pending=plan_requests(self.data,{},self.now)
        report=reconcile(self.data,self.espn,self.live,{}, {},self.now,{},req,defer,pending)
        self.assertEqual(report['original_queue_count'],len(self.data['records']))
        self.assertEqual(report['unresolved_official_game_id_cases'],missing)
        unknown=[r for r in report['records'] if r.get('nba_game_id') is None]
        self.assertTrue(all(r['outcome']==UNKNOWN and r['source_url'] is None and r['model_training_negative'] is False for r in unknown))
    def test_all_crosswalks_missing_preserves_every_unknown(self):
        data=deepcopy(self.data)
        for r in data['records']:r.pop('nba_game_id',None)
        req,defer,pending=plan_requests(data,{},self.now)
        self.assertEqual((req,defer,pending),([],[],[]))
        report=reconcile(data,self.espn,self.live,{}, {},self.now,{},req,defer,pending)
        self.assertEqual(report['original_queue_count'],len(data['records']))
        self.assertEqual(report['unresolved_unknown'],len(data['records']))
        self.assertEqual(report['source_attempts_this_run'],0)
    def test_nonempty_malformed_id_rejected(self):
        data=deepcopy(self.data);data['records'][0]['nba_game_id']='espn_123'
        with self.assertRaisesRegex(ValueError,'Malformed'):plan_requests(data,{},self.now)
    def test_previous_verified_row_survives_missing_crosswalk(self):
        data,first,live,now,previous=self.verified_fixture()
        preserved=deepcopy(previous['records'][0])
        self.assertEqual(preserved['outcome'],VERIFIED)
        self.assertEqual(len(preserved['source_sha256']),64)
        self.assertTrue(preserved['game_match_complete_and_final'])
        data['records'][0].pop('nba_game_id')
        req,defer,pending=plan_requests(data,previous,now)
        report=reconcile(data,first,live,{}, {},now,previous,req,defer,pending)
        self.assertEqual(report['records'][0],preserved)
        self.assertEqual(report['resolved_confirmed'],1)

    def verified_fixture(self):
        data,first,live=input_reports()
        now=datetime(2026,10,27,10,tzinfo=timezone.utc)
        previous=reconcile(data,first,live,{GID:payload()},{},now)
        return data,first,live,now,previous

    def test_missing_game_does_not_bypass_high_person_id_validation(self):
        for malformed in ('invalid_person','',None,True):
            with self.subTest(identity=malformed):
                data,first,live=input_reports()
                data['records'][0].pop('nba_game_id')
                data['records'][0]['identity_nba_person_id']=malformed
                with self.assertRaisesRegex(ValueError,'High identity without NBA ID'):
                    reconcile(data,first,live,{}, {},datetime(2026,10,27,10,tzinfo=timezone.utc),{},[],[],[])

    def test_changed_high_person_id_cannot_inherit_prior_verdict(self):
        for missing_game in (False,True):
            with self.subTest(missing_game=missing_game):
                data,first,live,now,previous=self.verified_fixture()
                if missing_game:data['records'][0].pop('nba_game_id')
                data['records'][0]['identity_nba_person_id']='999999'
                req,defer,pending=plan_requests(data,previous,now)
                with self.assertRaisesRegex(ValueError,'conflicts with verified prior'):
                    reconcile(data,first,live,{}, {},now,previous,req,defer,pending)

    def test_missing_current_person_stays_unknown_and_retains_old_proof(self):
        for missing_game in (False,True):
            with self.subTest(missing_game=missing_game):
                data,first,live,now,previous=self.verified_fixture()
                old=deepcopy(previous['records'][0])
                if missing_game:data['records'][0].pop('nba_game_id')
                data['records'][0]['identity_nba_person_id']=None
                data['records'][0]['identity_NBA_ID_strength']='unknown'
                req,defer,pending=plan_requests(data,previous,now)
                report=reconcile(data,first,live,{}, {},now,previous,req,defer,pending)
                row=report['records'][0]
                self.assertEqual((report['original_queue_count'],report['resolved_confirmed'],report['unresolved_unknown']),(1,0,1))
                self.assertEqual(row['outcome'],UNKNOWN)
                self.assertIs(row['model_training_negative'],False)
                self.assertEqual(row['prior_verified_evidence'],old)
                self.assertEqual(previous['records'][0],old)

    def test_positive_played_conflict_cannot_inherit_prior_verdict(self):
        data,first,live,now,previous=self.verified_fixture()
        data['records'][0].pop('nba_game_id')
        data['records'][0]['observed_official_game_played_flag']='1'
        with self.assertRaisesRegex(ValueError,'conflicts with verified prior'):
            reconcile(data,first,live,{}, {},now,previous,[],[],[])

    def test_verified_marker_without_source_proof_is_rejected(self):
        data,first,live,now,previous=self.verified_fixture()
        data['records'][0].pop('nba_game_id')
        previous['records'][0]['source_sha256']=None
        with self.assertRaisesRegex(ValueError,'Invalid verified prior identity or source provenance'):
            reconcile(data,first,live,{}, {},now,previous,[],[],[])
if __name__=='__main__':unittest.main()
