"""Research-only Sports.ru NBA KEEP vs TRANSFER economic replay.

Pure, fail-closed and no account/network/file access. A future case must
supply contemporaneous observed Sports.ru prices, ownership, player cards,
lock/unlock state and quota plus a validated PIT schedule; retrospective
current catalog or price guesses are not accepted. Scores must be Sports.ru
CREDITED player-by-game records covering every relevant remaining fixture.
Presence/absence in NBA boxscore, OUT, Telegram and reconstructed FP are NOT
Sports.ru credited zeros. This is a one-decision, up-to-three-move comparison,
not an automatic optimizer or a season-wide strategy.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from math import isfinite
from re import fullmatch
from zoneinfo import ZoneInfo

from src.live_calendar_fallback import TEAMS

ET = ZoneInfo("America/New_York")
UTC = timezone.utc
STATUS = "research_only_not_deployed"
POS = ("PG", "SG", "SF", "PF", "C")
MAX_MOVES = 3
HALF_HOUR = timedelta(minutes=30)
SOURCE_AGE = {
    "account": timedelta(minutes=30),
    "card": timedelta(hours=4),
    "quote": timedelta(minutes=30),
    "lock": timedelta(minutes=15),
    "schedule": timedelta(hours=8),
}
NO_CLAIMS = {
    "adopt_on_site": False,
    "real_transfer_advantage_proven": False,
    "user_account_mutated": False,
    "population_p_play_calibrated": False,
}


class InsufficientEvidence(ValueError):
    """A legal/observable state is missing or inconsistent. Never impute it."""


def ensure(ok, reason):
    if not ok:
        raise InsufficientEvidence(reason)


def moment(value):
    ensure(isinstance(value, str) and value, "MISSING_TIMESTAMP")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise InsufficientEvidence("INVALID_TIMESTAMP") from error
    ensure(instant.utcoffset() is not None, "NAIVE_TIMESTAMP")
    return instant.astimezone(UTC)


def numerical(value, name, *, minimum=0):
    ensure(type(value) in (int, float) and isfinite(value) and value >= minimum,
           "INVALID_" + name)
    return float(value)


def observed(row, *, kind, cutoff, age=None, after=None):
    ensure(isinstance(row, dict), "MISSING_" + kind)
    ensure(row.get("source_kind") == kind and
           row.get("verified_by_owner") is True and
           isinstance(row.get("source_sha256"), str) and
           fullmatch(r"[a-fA-F0-9]{64}", row["source_sha256"]) is not None,
           "UNVERIFIED_" + kind)
    at = moment(row.get("first_observed_at_utc"))
    ensure(at <= cutoff, "FUTURE_SOURCE_" + kind)
    if age is not None:
        ensure(cutoff - at <= age, "STALE_SOURCE_" + kind)
    if after is not None:
        ensure(at >= after, "SOURCE_BEFORE_GAME_" + kind)
    return at


def week_window(snapshot):
    decision = moment(snapshot.get("decision_at_utc"))
    try:
        monday = date.fromisoformat(snapshot.get("week_et_monday", ""))
    except ValueError as error:
        raise InsufficientEvidence("BAD_ET_WEEK") from error
    ensure(monday.weekday() == 0, "ET_WEEK_NOT_MONDAY")
    monday_start = datetime.combine(monday, time(), ET).astimezone(UTC)
    next_monday = datetime.combine(monday + timedelta(days=7),
                                   time(), ET).astimezone(UTC)
    ensure(monday_start <= decision < next_monday,
           "DECISION_NOT_IN_DECLARED_ET_WEEK")
    return decision, next_monday


def roster_check(roster, cards):
    ensure(isinstance(roster, list) and len(roster) == 10 and
           len(set(roster)) == 10, "NOT_TEN_UNIQUE_PLAYERS")
    pos, clubs = Counter(), Counter()
    for pid in roster:
        ensure(pid in cards, "MISSING_PLAYER_CARD")
        p = cards[pid]
        pos[p["position"]] += 1
        clubs[p["club"]] += 1
    ensure(all(pos[p] == 2 for p in POS) and sum(pos.values()) == 10,
           "POSITIONS_NOT_TWO_EACH")
    ensure(all(count <= 2 for count in clubs.values()),
           "MORE_THAN_TWO_PER_CLUB")


def validate_decision(snapshot, moves):
    """Return validated, price-aware, pre-lock decision state, no outcomes."""
    ensure(isinstance(snapshot, dict) and
           snapshot.get("schema_version") == 1 and
           snapshot.get("status") == STATUS and
           snapshot.get("adopt_on_site") is False, "UNTRUSTED_SNAPSHOT")
    decision, end = week_window(snapshot)
    account = snapshot.get("account")
    observed(account, kind="sportsru_account", cutoff=decision,
             age=SOURCE_AGE["account"])
    original_roster = account.get("roster")
    ensure(isinstance(original_roster, list), "NO_OWNER_ROSTER")
    roster = list(original_roster)
    cash = numerical(account.get("cash"), "CASH")
    remaining = account.get("quota_remaining")
    ensure(type(remaining) is int and 0 <= remaining <= MAX_MOVES,
           "UNVERIFIED_QUOTA_REMAINING")
    ensure(account.get("quota_reset_verified") is True,
           "QUOTA_RESET_RULE_UNVERIFIED")
    ensure(isinstance(moves, list) and len(moves) <= MAX_MOVES and
           len(moves) <= remaining, "TRANSFER_QUOTA_EXCEEDED")
    raw_cards = snapshot.get("player_cards")
    ensure(isinstance(raw_cards, dict), "NO_PLAYER_CARDS")
    cards = {}
    for pid in set(roster) | {m.get("in") for m in moves if isinstance(m, dict)}:
        ensure(isinstance(pid, str) and pid in raw_cards, "MISSING_PLAYER_CARD")
        p = raw_cards[pid]
        observed(p, kind="sportsru_player_card", cutoff=decision,
                 age=SOURCE_AGE["card"])
        ensure(p.get("position") in POS and p.get("club") in TEAMS,
               "INVALID_POSITION_OR_CLUB")
        cards[pid] = p
    roster_check(roster, cards)
    schedule = snapshot.get("schedule")
    observed(schedule, kind="verified_public_schedule_PIT",
             cutoff=decision, age=SOURCE_AGE["schedule"])
    ensure(schedule.get("complete_for_declared_week") is True,
           "UNKNOWN_FIXTURE_DENOMINATOR")
    games = schedule.get("games")
    ensure(isinstance(games, list), "MISSING_SCHEDULE")
    fixtures = {}
    for game in games:
        ensure(isinstance(game, dict) and
               isinstance(game.get("id"), str) and game["id"] and
               game["id"] not in fixtures, "INVALID_OR_DUPLICATE_GAME")
        tip = moment(game.get("utc"))
        ensure(game.get("home") in TEAMS and game.get("away") in TEAMS and
               game["home"] != game["away"], "INVALID_GAME_TEAMS")
        # Both before-week and after-week fixtures can exist in a full schedule.
        fixtures[game["id"]] = {"tip": tip, "home": game["home"],
                                 "away": game["away"]}
    quotes, locks, forecasts = (snapshot.get(k) for k in
                               ("price_quotes", "lock_receipts", "forecasts"))
    ensure(isinstance(quotes, dict) and isinstance(locks, dict) and
           isinstance(forecasts, dict), "MISSING_DECISION_EVIDENCE")
    used = set()
    predicted_delta = 0.
    for move in moves:
        ensure(isinstance(move, dict), "INVALID_MOVE")
        out, target = move.get("out"), move.get("in")
        ensure(isinstance(out, str) and isinstance(target, str) and
               out != target and out not in used and target not in used,
               "REPEATED_OR_INVALID_MOVE")
        ensure(out in roster and target not in roster, "NONEXECUTABLE_ROSTER_MOVE")
        ensure(target in cards, "MISSING_INCOMING_CARD")
        ensure(cards[out]["position"] == cards[target]["position"],
               "POSITION_MISMATCH")
        for pid, side in ((out, "sell"), (target, "buy")):
            receipt = quotes.get(pid)
            observed(receipt, kind="sportsru_price_quote", cutoff=decision,
                     age=SOURCE_AGE["quote"])
            ensure(receipt.get("side") == side, "WRONG_QUOTE_SIDE")
            numerical(receipt.get("price"), "PRICE")
            lock = locks.get(pid)
            observed(lock, kind="sportsru_lock_receipt", cutoff=decision,
                     age=SOURCE_AGE["lock"])
            ensure(lock.get("state") == "unlocked", "PLAYER_LOCK_NOT_VERIFIED_OPEN")
            club = cards[pid]["club"]
            for game in fixtures.values():
                if club not in (game["home"], game["away"]):
                    continue
                tip = game["tip"]
                if tip - HALF_HOUR <= decision < tip:
                    raise InsufficientEvidence("T_MINUS_30_LOCK")
                if tip <= decision < tip + timedelta(hours=24):
                    ensure(lock.get("explicit_after_tip_unlock") is True and
                           moment(lock["first_observed_at_utc"]) >= tip,
                           "POSTGAME_UNLOCK_UNVERIFIED")
            forecast = forecasts.get(pid)
            ensure(isinstance(forecast, dict) and
                   forecast.get("status") == STATUS and
                   forecast.get("adopt_on_site") is False and
                   isinstance(forecast.get("frozen_hash_sha256"), str) and
                   fullmatch(r"[0-9a-fA-F]{64}", forecast["frozen_hash_sha256"])
                   is not None, "UNTRUSTED_FROZEN_FORECAST")
            ensure(moment(forecast.get("issued_at_utc")) <= decision,
                   "FORECAST_ISSUED_AFTER_DECISION")
            numerical(forecast.get("predicted_remaining_fp"),
                      "PREDICTED_FP", minimum=-1e6)
        cash += float(quotes[out]["price"]) - float(quotes[target]["price"])
        ensure(cash >= -1e-8, "INSUFFICIENT_CASH")
        predicted_delta += (float(forecasts[target]["predicted_remaining_fp"])
                            - float(forecasts[out]["predicted_remaining_fp"]))
        roster[roster.index(out)] = target
        used.update((out, target))
        roster_check(roster, cards)
    return {
        "decision": decision, "end": end, "fixtures": fixtures,
        "moves": moves, "cards": cards, "cash_after": round(cash, 4),
        "quota_after": remaining - len(moves),
        "expected_delta_fp": round(predicted_delta, 4),
    }



def verified_club_tenure(checked, outcomes, player_id):
    """Post-week independent club timeline; NEVER a pre-decision roster claim.

    A dated owner-attested receipt has to cover the whole remaining ET window.
    Changes of club must be explicit, contiguous, and connected to official
    transaction/game-day evidence. One current catalogue club cannot stand
    in for every subsequent game.
    """
    bundle = outcomes.get("game_day_club_tenure")
    ensure(isinstance(bundle, dict) and player_id in bundle,
           "MISSING_GAME_DAY_CLUB_TENURE")
    receipt = bundle[player_id]
    evaluated = moment(outcomes.get("evaluated_at_utc"))
    observed(receipt, kind="official_complete_game_day_club_tenure",
             cutoff=evaluated, after=checked["end"])
    ensure(receipt.get("player_id") == player_id
           and receipt.get("complete_entire_window_from_official_transactions") is True
           and receipt.get("independent_game_day_club_check") is True
           and receipt.get("evidence_is_not_current_catalog_proxy") is True,
           "UNVERIFIED_GAME_DAY_CLUB_TENURE")
    periods = receipt.get("intervals")
    ensure(isinstance(periods, list) and 1 <= len(periods) <= 32,
           "MISSING_CLUB_TENURE_INTERVALS")
    cursor = checked["decision"]
    verified = []
    for item in periods:
        ensure(isinstance(item, dict), "INVALID_CLUB_TENURE_INTERVAL")
        begin = moment(item.get("from_utc"))
        end = moment(item.get("until_utc"))
        club = item.get("club")
        ensure(begin == cursor and begin < end <= checked["end"]
               and club in TEAMS, "CLUB_TENURE_GAP_OVERLAP_OR_INVALID_CLUB")
        verified.append((begin, end, club))
        cursor = end
    ensure(cursor == checked["end"], "CLUB_TENURE_DOES_NOT_COVER_ET_WEEK")
    ensure(verified[0][2] == checked["cards"][player_id]["club"],
           "DECISION_CLUB_VERSUS_RECONSTRUCTED_TENURE_CONFLICT")
    return verified


def club_at(verified, stamp):
    for begin, end, club in verified:
        if begin <= stamp < end:
            return club
    raise InsufficientEvidence("GAME_OUTSIDE_VERIFIED_CLUB_TENURE")


def score_replay(checked, outcomes):
    """Only postweek credited Sports.ru FP; explicitly verify game-day clubs.

    Fixed-branch counterfactual: KEEP owns every OUT, TRANSFER owns every IN
    from the decision onward with no additional simulated moves. Actual
    ownership, true profitability and Sports.ru credited zero are NEVER
    inferred from missing player rows, OUT or NBA boxscores.
    """
    ensure(isinstance(outcomes, dict), "NO_SPORTSRU_CREDIT_OUTCOMES")
    after = checked["end"]
    evaluated = moment(outcomes.get("evaluated_at_utc"))
    observed(outcomes, kind="sportsru_final_credits_batch",
             cutoff=evaluated, after=after)
    ensure(outcomes.get("complete_final_fixture_set") is True,
           "FINAL_FIXTURE_SET_NOT_VERIFIED")
    final = outcomes.get("final_games")
    records = outcomes.get("credited_player_games")
    ensure(isinstance(final, list) and isinstance(records, list),
           "MISSING_FINAL_GAMES_OR_CREDITS")
    fixture_index = checked["fixtures"]
    involved = {p for m in checked["moves"] for p in (m["out"], m["in"])}
    # The entire declared ET-week calendar must have finished: selecting only
    # games of the decision-day clubs misses the games of a player traded later.
    expected_fixtures = {gid for gid, g in fixture_index.items()
                         if checked["decision"] <= g["tip"] < after}
    final_ids = set()
    final_observed = {}
    for g in final:
        ensure(isinstance(g, dict) and isinstance(g.get("id"), str)
               and g["id"] not in final_ids, "DUPLICATE_FINAL_GAME")
        gid = g["id"]
        ensure(gid in expected_fixtures and g.get("status") == "final",
               "UNMATCHED_OR_UNFINISHED_GAME")
        asof = fixture_index[gid]
        ensure(moment(g.get("utc")) == asof["tip"] and
               g.get("home") == asof["home"] and
               g.get("away") == asof["away"],
               "RESCHEDULED_OR_CLUB_CONFLICT")
        verified_final_at = moment(g.get("final_verified_at_utc"))
        ensure(asof["tip"] < verified_final_at <= evaluated,
               "FINAL_STATUS_NOT_OBSERVED_AFTER_TIPOFF")
        final_ids.add(gid)
        final_observed[gid] = verified_final_at
    ensure(final_ids == expected_fixtures,
           "INCOMPLETE_OR_EXTRA_FINAL_FIXTURES")

    tenures = {pid: verified_club_tenure(checked, outcomes, pid)
               for pid in involved}
    expected = {}
    for pid in involved:
        for gid in expected_fixtures:
            game = fixture_index[gid]
            club = club_at(tenures[pid], game["tip"])
            if club in (game["home"], game["away"]):
                # A new owner cannot receive credit for a game that was
                # already locked at the time of this decision.
                ensure(checked["decision"] < game["tip"] - HALF_HOUR,
                       "OWNERSHIP_AT_LOCK_ALREADY_CLOSED")
                expected[(pid, gid)] = club

    actual = {}
    for row in records:
        ensure(isinstance(row, dict), "MALFORMED_FP_CREDIT")
        key = (row.get("player_id"), row.get("game_id"))
        ensure(key in expected and key not in actual,
               "EXTRA_OR_DUPLICATE_FP_CREDIT")
        ensure(row.get("club_at_game") == expected[key],
               "CREDIT_GAME_DAY_CLUB_CONFLICT")
        # A credited FP receipt observed BEFORE the game was declared final
        # cannot be accepted as the final Sports.ru result.
        observed(row, kind="sportsru_credited_fp", cutoff=evaluated,
                 after=final_observed[key[1]])
        actual[key] = numerical(row.get("credited_fp"),
                                "SPORTSRU_CREDIT", minimum=-1e6)
    ensure(set(actual) == set(expected),
           "MISSING_SPORTSRU_CREDIT_NOT_ZERO")
    delta = 0.
    for move in checked["moves"]:
        for pid, sign in ((move["out"], -1), (move["in"], 1)):
            for (member, _), fp in actual.items():
                if member == pid:
                    delta += sign * fp
    return round(delta, 4)

def evaluate(snapshot, moves, outcomes=None):
    """No private state is read or persisted. A refusal is a useful result."""
    common = {"status": STATUS, **NO_CLAIMS}
    try:
        legal = validate_decision(snapshot, moves)
    except (InsufficientEvidence, TypeError, KeyError) as error:
        return {**common, "phase": "BLOCKED_UNVERIFIED_DECISION",
                "reason": str(error), "expected_delta_fp": None,
                "actual_delta_fp": None}
    report = {**common, "phase": "PRELOCK_DECISION_CHECKED",
              "decision_at_utc": legal["decision"].isoformat(),
              "period_end_utc": legal["end"].isoformat(),
              "moves": len(legal["moves"]),
              "cash_after": legal["cash_after"],
              "quota_after": legal["quota_after"],
              "expected_delta_fp": legal["expected_delta_fp"],
              "actual_delta_fp": None,
              "comparison_scope": "single_decision_fixed_roster_no_followup_moves",
              "game_day_club_tenure_required_postweek": True,
              "ownership_at_lock_from_hypothetical_scenario_only": True,
              "verified_source_representativeness": False,
              "source_evidence_self_attested_not_independently_audited": True}
    if outcomes is not None:
        try:
            report["actual_delta_fp"] = score_replay(legal, outcomes)
            report["phase"] = "SCORED_USER_ATTESTED_RESEARCH_ONLY"
        except (InsufficientEvidence, KeyError, TypeError) as error:
            report["phase"] = "UNSCORABLE_POSTGAME"
            report["reason"] = str(error)
    return report


if __name__ == "__main__":
    import json
    print(json.dumps({"status": STATUS, "protocol_ready": True,
                      "actual_cases_scored": 0, **NO_CLAIMS,
                      "message": "No private receipts or historical prices provided; no economic claims."}))
