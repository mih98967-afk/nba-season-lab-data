"""Regression tests for fail-closed latest public NBA research consistency."""
import copy
import unittest
from src.public_sync_integrity import verify

def fixture():
    def r(**kw):
        return dict(schema_version=1, status="research_only_not_deployed", adopt_on_site=False, **kw)
    return dict(
        live={"games":[{"id":"g","status":"final"}]},
        explicit=r(checked_final_game_ids=["g"]),
        cohort=r(records=[dict(game_id="g",player_id="p",team="BOS",participation_label=1,evidence="positive_minutes_verified_sportsru_fp")],
                 summary={"verified_full_boxscores_checked":1,"listed_player_game_labels":1}),
        coverage=r(full_population_brier_enabled=False,by_game={"g":{}},
                   catalog_proxy_records=[dict(game_id="g",player_id="p",match_team="BOS",observed_outcome="played_verified",evidence="positive_minutes_verified_sportsru_fp"),dict(game_id="g",player_id="x",match_team="BOS",observed_outcome="unknown_roster_membership_or_unlisted")],
                   verified_outcomes_outside_proxy=[],
                   summary={"checked_games":1,"games_without_complete_dnp_audit":0,"catalog_proxy_candidate_player_games":2,"played_verified":1,"explicit_dnp_verified":0,"unknown_roster_membership_or_unlisted":1,"unknown_is_not_absent_or_injured":1,"verified_labels_total":1,"verified_labels_outside_catalog_proxy":0}),
        shadow=r(population_brier_enabled=False,issued=[{"game_id":"g","player_id":pid} for pid in ("p","x")],
                 observations=[{"game_id":"g","player_id":"p","actual_played":1,"label_provenance":"positive_minutes_verified_sportsru_fp"}],
                 summary={"issued_prelock_forecasts":2,"verified_selected_labels":1}),
        selection=r(quality_gate={"unknown_are_not_DNP":True},total_issued_predictions=2,finished_checked=2,verified_postgame_results=1,unknown_postgame_results=1,future_or_not_checked=0,by_game={"g":{"finished_checked":2,"verified_played":1,"outcome_UNKNOWN":1}},out_status_missing_review_queue=[],official_OUT_unknown_review_priority_count=0,all_finished_with_unknown_binary_sensitivity={"n":2,"verified":1,"missing":1}),
        ledger=r(overall_selected_opportunity_coverage={"finished_checked":2,"verified_played":1,"verified_explicit_DNP":0,"outcome_UNKNOWN":1},issued_total_including_future=2),
        history=r(issued=[]),
        paired=r(unknown_never_mapped_to_DNP=True,p_play_first_issued_total=2,historical_prelock_overlapping_issued_total=0,paired_cohort={"issued":0,"finished_checked":0,"verified_pairs":0,"outcome_UNKNOWN":0,"waiting_historical_reconciliation":0})
    )

class IntegrityTests(unittest.TestCase):
    def test_unknown_remains_unknown(self):
        self.assertEqual(verify(fixture())["selection_UNKNOWN"],1)
    def test_stale_coverage_fails(self):
        x=fixture();x["coverage"]["by_game"]={}
        with self.assertRaisesRegex(ValueError,"coverage by_game"):verify(x)
    def test_stale_selection_fails(self):
        x=fixture();x["selection"]["verified_postgame_results"]=0
        with self.assertRaisesRegex(ValueError,"selection denominator"):verify(x)
    def test_stale_ledger_fails(self):
        x=fixture();x["ledger"]["overall_selected_opportunity_coverage"]["outcome_UNKNOWN"]=0
        with self.assertRaisesRegex(ValueError,"evidence ledger"):verify(x)
    def test_stale_pair_fails(self):
        x=fixture();x["paired"]["p_play_first_issued_total"]=0
        with self.assertRaisesRegex(ValueError,"historical paired"):verify(x)
    def test_out_cannot_become_negative(self):
        x=fixture();x["selection"]["out_status_missing_review_queue"]=[{"game_id":"g","player_id":"x","actual_played":0}]
        x["selection"]["official_OUT_unknown_review_priority_count"]=1
        with self.assertRaisesRegex(ValueError,"official OUT"):verify(x)
    def test_unverified_negative_evidence_fails(self):
        x=fixture();x["shadow"]["observations"][0]["actual_played"]=0
        with self.assertRaisesRegex(ValueError,"weak evidence"):verify(x)

if __name__=="__main__":unittest.main()
