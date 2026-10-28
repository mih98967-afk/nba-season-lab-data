import copy
import unittest
from src.keep_transfer_economic_replay import evaluate

D="2026-10-26T12:00:00Z"
SHA="a"*64
def proof(kind,at=D,**extra):
 return {"source_kind":kind,"verified_by_owner":True,"source_sha256":SHA,"first_observed_at_utc":at,**extra}
def case():
 pos=["PG","PG","SG","SG","SF","SF","PF","PF","C","C"]
 clubs=["BOS","NYK","ATL","MIA","SAS","WAS","GSW","PHI","LAL","CLE"]
 cards={f"p{i}":proof("sportsru_player_card",position=pos[i],club=clubs[i]) for i in range(10)}
 cards["incoming"]=proof("sportsru_player_card",position="PG",club="DEN")
 snap={"schema_version":1,"status":"research_only_not_deployed","adopt_on_site":False,
       "decision_at_utc":D,"week_et_monday":"2026-10-26",
       "account":proof("sportsru_account",roster=list(cards)[:10],cash=100,quota_remaining=3,quota_reset_verified=True),
       "player_cards":cards,
       "schedule":proof("verified_public_schedule_PIT",complete_for_declared_week=True,games=[
           {"id":"g1","utc":"2026-10-27T00:00:00Z","home":"BOS","away":"DEN"}]),
       "price_quotes":{"p0":proof("sportsru_price_quote",side="sell",price=500),
                       "incoming":proof("sportsru_price_quote",side="buy",price=550)},
       "lock_receipts":{pid:proof("sportsru_lock_receipt",state="unlocked") for pid in ("p0","incoming")},
       "forecasts":{pid:{"status":"research_only_not_deployed","adopt_on_site":False,
                         "frozen_hash_sha256":SHA,"issued_at_utc":D,
                         "predicted_remaining_fp":x} for pid,x in (("p0",20),("incoming",30))}}
 return snap,[{"out":"p0","in":"incoming"}]
def outcomes():
 return proof("sportsru_final_credits_batch","2026-11-02T08:00:00Z",
     evaluated_at_utc="2026-11-02T08:00:00Z",complete_final_fixture_set=True,
     final_games=[{"id":"g1","utc":"2026-10-27T00:00:00Z","home":"BOS","away":"DEN","status":"final"}],
     credited_player_games=[
         proof("sportsru_credited_fp","2026-10-27T04:00:00Z",player_id="p0",game_id="g1",credited_fp=15),
         proof("sportsru_credited_fp","2026-10-27T04:00:00Z",player_id="incoming",game_id="g1",credited_fp=35)])
class Tests(unittest.TestCase):
 def test_valid_case_and_immutable_inputs(self):
  s,m=case();old=copy.deepcopy(s);a=evaluate(s,m,outcomes())
  self.assertEqual(a["phase"],"SCORED_USER_ATTESTED_RESEARCH_ONLY")
  self.assertEqual(a["expected_delta_fp"],10)
  self.assertEqual(a["actual_delta_fp"],20)
  self.assertEqual(a["cash_after"],50)
  self.assertFalse(a["adopt_on_site"])
  self.assertEqual(s,old)
 def test_missing_price_blocks(self):
  s,m=case();del s["price_quotes"]["incoming"]
  self.assertEqual(evaluate(s,m)["phase"],"BLOCKED_UNVERIFIED_DECISION")
 def test_future_forecast_blocks(self):
  s,m=case();s["forecasts"]["p0"]["issued_at_utc"]="2026-10-26T12:01:00Z"
  self.assertEqual(evaluate(s,m)["phase"],"BLOCKED_UNVERIFIED_DECISION")
 def test_quota_not_proven_blocks(self):
  s,m=case();s["account"]["quota_reset_verified"]=False
  self.assertEqual(evaluate(s,m)["phase"],"BLOCKED_UNVERIFIED_DECISION")
 def test_budget_and_team_cap(self):
  s,m=case();s["price_quotes"]["incoming"]["price"]=1000
  self.assertEqual(evaluate(s,m)["phase"],"BLOCKED_UNVERIFIED_DECISION")
  s,m=case();s["player_cards"]["incoming"]["club"]="NYK"
  self.assertEqual(evaluate(s,m)["phase"],"PRELOCK_DECISION_CHECKED")
 def test_missing_credit_not_zero(self):
  s,m=case();y=outcomes();y["credited_player_games"].pop()
  self.assertEqual(evaluate(s,m,y)["phase"],"UNSCORABLE_POSTGAME")
  self.assertEqual(evaluate(s,m,y)["actual_delta_fp"],None)
 def test_no_backdated_receipt_or_lock(self):
  s,m=case();s["price_quotes"]["p0"]["first_observed_at_utc"]="2026-10-26T12:01:00Z"
  self.assertEqual(evaluate(s,m)["phase"],"BLOCKED_UNVERIFIED_DECISION")
 def test_lock_and_unverified_unlock(self):
  s,m=case();s["schedule"]["games"][0]["utc"]="2026-10-26T12:15:00Z"
  self.assertEqual(evaluate(s,m)["phase"],"BLOCKED_UNVERIFIED_DECISION")
  s,m=case();s["schedule"]["games"][0]["utc"]="2026-10-26T11:00:00Z"
  self.assertEqual(evaluate(s,m)["phase"],"BLOCKED_UNVERIFIED_DECISION")
 def test_reconstructed_fp_not_credit(self):
  s,m=case();y=outcomes()
  y["credited_player_games"][0]["source_kind"]="reconstructed_fp"
  self.assertEqual(evaluate(s,m,y)["phase"],"UNSCORABLE_POSTGAME")
if __name__=="__main__":
 unittest.main()
