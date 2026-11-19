import json,pathlib,tempfile,unittest
import pandas as pd
from infer import load_verified,predict_frame

class InferenceGuards(unittest.TestCase):
    def test_hash_checked_before_unpickling(self):
        with tempfile.TemporaryDirectory() as f:
            p=pathlib.Path(f);(p/'research_models.pkl').write_bytes(b'not a pickle');(p/'MODEL_RESEARCH_REPORT.json').write_text(json.dumps({'model_sha256':'0'*64}))
            with self.assertRaisesRegex(ValueError,'MODEL_HASH_MISMATCH'):load_verified(p)
    def test_unsupported_lead_rejected(self):
        frame=pd.DataFrame({'pid':['a'],'game':['g'],'horizon_days':[2]})
        with self.assertRaisesRegex(ValueError,'UNVALIDATED_LEAD_TIME'):predict_frame({'leads':[0,1,3]},frame)
    def test_empty_batch_does_not_fabricate_forecasts(self):
        frame=pd.DataFrame(columns=['pid','game','horizon_days'])
        self.assertEqual(len(predict_frame({},frame)),0)
class NearInferenceGuards(unittest.TestCase):
    def test_partial_group_cannot_create_teammate_context(self):
        from infer_near import near_features
        d=pd.DataFrame({'horizon_days':[0],'fp10':[20.],'min10':[30.],'inj_out':[0]})
        with self.assertRaisesRegex(ValueError,'COMPLETE_TEAM_CONTEXT_REQUIRED'):near_features(d)
    def test_near_model_rejects_long_lead(self):
        from infer_near import near_features
        with self.assertRaisesRegex(ValueError,'NEAR_GAME_ONLY'):near_features(pd.DataFrame({'horizon_days':[7]}))
    def test_teammate_burden_excludes_self(self):
        from infer_near import near_features
        d=pd.DataFrame({'horizon_days':[0,0],'issue_date':['2026-11-16']*2,'game':['g']*2,'team':['AAA']*2,'fp10':[20.,10.],'min10':[30.,15.],'inj_out':[1,0]})
        f=near_features(d,complete_team_groups=True)
        self.assertEqual(list(f.inj_teammate_out_fp),[0.,20.]);self.assertEqual(list(f.inj_teammate_out_minutes),[0.,30.])
class DistributionCalibrationGuards(unittest.TestCase):
    def test_status_adjustment_never_narrows(self):
        from infer_near import conditional_offsets
        b={'conditional_offsets':{.2:1.},'conditional_status_offsets':{.2:{'Questionable':.3,'Probable':2.}}}
        d=pd.DataFrame({'inj_questionable':[1,0,0],'inj_probable':[0,1,0]})
        self.assertEqual(list(conditional_offsets(b,d,.2)),[1.,2.,1.])
    def test_absent_status_keeps_global_offset(self):
        from infer_near import conditional_offsets
        b={'conditional_offsets':{.2:.5},'conditional_status_offsets':{.2:{'Questionable':2.}}}
        self.assertEqual(list(conditional_offsets(b,pd.DataFrame({'a':[1,2]}),.2)),[.5,.5])
if __name__=='__main__':unittest.main()
