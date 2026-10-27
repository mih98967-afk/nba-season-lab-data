"""PIT cross-source player-game opportunity audit, NOT a p_play model.

Join immutable cached Sports.ru catalog proxy + independent ESPN current team
roster only when *both* were actually captured before an individual game lock.
An ESPN club match is roster-list evidence, NOT active game-day eligibility.
No roster absence or unlisted athlete ever implies didNotPlay / zero FP.

Outcome labels are allowed only POSTGAME from independently verified played
Sports.ru FP or explicit ESPN didNotPlay=true in a finalized checked game.
No profile, pricing, transfer, Firestore, site, or future-source mutations.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

from src.catalog_pit_research import (
    _validated_snapshots as validate_catalog_snapshots,
    LOCK, MAX_SNAPSHOT_AGE, UNKNOWN,
)
from src.espn_roster_pit import STATUS
from src.espn_roster_pit import ESPN_TEAMS
from src.live_calendar_fallback import TEAMS
from src.rolling_decision_research import (
    canonical_hash, instant, stamp, official_asof, telegram_asof,
)
from src.sync import DATA

UTC = timezone.utc
ESPN_SOURCE = "ESPN public team roster current snapshot"
HIGH = "previously_named_played_ESPN_person_ID"
WEAK = "unique_english_name_only"
VALID_STATUS = {"parsed_not_game_day_eligibility", "invalid_or_unavailable"}
MAX_REPORT_ROWS = 150000


def validate_espn_snapshots(snapshots, now):
    """Reject changed previously saved snapshots and time/identity laundering."""
    if not isinstance(snapshots, list):
        raise ValueError("ESPN archive must be a list")
    out = []
    dates = {}
    for snap in snapshots:
        if (not isinstance(snap, dict) or snap.get("schema_version") != 1
                or snap.get("status") != STATUS
                or snap.get("adopt_on_site") is not False
                or snap.get("publication_time_unknown") is not True
                or snap.get("game_day_eligibility_verified") is not False
                or snap.get("source") != ESPN_SOURCE):
            raise ValueError("Untrusted or deployable ESPN roster capture")
        captured = instant(snap["captured_at_utc"])
        day = captured.strftime("%Y-%m-%d")
        if captured > now or dates.get(day, 0) >= 2:
            raise ValueError("Future or duplicate ESPN roster capture day")
        dates[day] = dates.get(day, 0) + 1
        teams = snap.get("teams")
        if not isinstance(teams, list) or len(teams) != len(TEAMS):
            raise ValueError("ESPN roster capture omitted clubs")
        if canonical_hash({"teams": teams, "captured": stamp(captured)}) != snap.get("snapshot_hash_sha256"):
            raise ValueError("ESPN roster snapshot modified since capture")
        seen_teams = set()
        seen_espn_athletes = set()
        seen_catalog_ids = set()
        available = 0
        for team in teams:
            if not isinstance(team, dict):
                raise ValueError("Malformed team snapshot")
            club = team.get("club")
            if club not in TEAMS or club in seen_teams:
                raise ValueError("Duplicate or unknown ESPN team")
            seen_teams.add(club)
            if team.get("url") != "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{}/roster".format(ESPN_TEAMS[club]):
                raise ValueError("ESPN team URL mismatches expected club ID")
            if team.get("source_first_seen_at_utc") != stamp(captured):
                raise ValueError("Team roster cannot predate source retrieval")
            state = team.get("source_status")
            athletes = team.get("athletes")
            if state not in VALID_STATUS or not isinstance(athletes, list):
                raise ValueError("Invalid team roster source state")
            if state == "invalid_or_unavailable":
                if athletes:
                    raise ValueError("Cannot claim athletes from an unavailable source")
                continue
            available += 1
            if not 8 <= len(athletes) <= 35:
                raise ValueError("Incomplete/implausible roster listing")
            for athlete in athletes:
                if not isinstance(athlete, dict):
                    raise ValueError("Malformed athlete in roster")
                espn_id = athlete.get("espn_person_id")
                name = athlete.get("display_name")
                if (not isinstance(espn_id, str) or not espn_id.isdigit()
                        or espn_id in seen_espn_athletes
                        or not isinstance(name, str) or not name.strip()):
                    raise ValueError("Duplicate ESPN athlete or missing identity")
                seen_espn_athletes.add(espn_id)
                pid = athlete.get("sportsru_player_id")
                method = athlete.get("identity_method")
                catalog_club = athlete.get("catalog_team_at_capture")
                if pid is None:
                    if method not in (None, "conflicting_ESPN_roster_teams_excluded") or catalog_club not in (None, *TEAMS):
                        raise ValueError("Untrusted unidentified athlete metadata")
                    continue
                if (not isinstance(pid, str) or not pid
                        or pid in seen_catalog_ids or method not in (HIGH, WEAK)
                        or catalog_club not in TEAMS):
                    raise ValueError("Repeated/ambiguous cross-provider athlete identity")
                seen_catalog_ids.add(pid)
        if seen_teams != TEAMS or snap.get("all_teams_available") is not (available == 30):
            raise ValueError("Incomplete roster availability flag")
        out.append((captured, snap))
    out.sort(key=lambda x: x[0])
    if any(b[0]-a[0] < timedelta(hours=4) and a[0].date() == b[0].date() for a,b in zip(out,out[1:])):
        raise ValueError("Duplicate ESPN daily snapshots too close")
    return out


def _verified_labels(cohort, explicit, live, now):
    if (cohort.get("schema_version") != 1 or cohort.get("status") != STATUS
            or cohort.get("adopt_on_site") is not False
            or explicit.get("schema_version") != 1
            or explicit.get("adopt_on_site") is not False):
        raise ValueError("Participation/DNP evidence has not passed research QA")
    checked = explicit.get("checked_final_game_ids")
    if (not isinstance(checked, list) or
            any(not isinstance(g, str) or not g for g in checked) or
            len(set(checked)) != len(checked) or
            len(checked) != cohort.get("summary", {}).get("verified_full_boxscores_checked")):
        raise ValueError("Participation cohort/explicit DNP game sets disagree")
    finals = {}
    for game in live.get("games", []):
        if not isinstance(game, dict) or game.get("status") != "final":
            continue
        gid = game.get("id")
        if not isinstance(gid, str) or gid in finals:
            raise ValueError("Missing or duplicate finalized fixture")
        finals[gid] = game
    for gid in checked:
        if gid not in finals or instant(finals[gid]["utc"]) > now:
            raise ValueError("Checked final game unavailable or in the future")
    outcomes = {}
    for row in cohort.get("records", []):
        if not isinstance(row, dict):
            raise ValueError("Malformed participation outcome")
        gid, pid = row.get("game_id"), row.get("player_id")
        key = gid, pid
        if (not all(isinstance(k, str) and k for k in key)
                or gid not in checked or gid not in finals or key in outcomes):
            raise ValueError("Duplicate/out-of-scope outcome")
        game = finals[gid]
        if (row.get("team") not in (game["home"], game["away"])
                or row.get("game_utc") != game["utc"]
                or row.get("participation_label") not in (0, 1)
                or row.get("evidence") != (
                    "positive_minutes_verified_sportsru_fp"
                    if row["participation_label"] else "explicit_espn_didNotPlay_true"
                )):
            raise ValueError("Verified label/game contradicts source")
        first_seen = row.get("source_first_observed_at_utc")
        # Positive boxscore labels can be verified with a missing archived first
        # seen clock, but must not be treated as dated pregame observations.
        # Explicit DNP evidence always requires a real postgame observed time.
        if first_seen is None:
            if row["participation_label"] == 0:
                raise ValueError("Explicit DNP without observed provenance time")
        elif not instant(game["utc"]) <= instant(first_seen) <= now:
            raise ValueError("Postgame outcome was observed before tipoff or after audit")
        outcomes[key] = row
    if (len(outcomes) != cohort.get("summary", {}).get("listed_player_game_labels")
            or {gid for gid, _ in outcomes} != set(checked)):
        raise ValueError("Verified labels do not cover the exact checked-game set")
    return set(checked), finals, outcomes


def build(live, cohort, explicit, catalog_snapshots, espn_snapshots,
          now, official=None, telegram=None):
    """Public, reproducible source agreement audit, only truly pre-lock inputs."""
    if now.utcoffset() is None:
        raise ValueError("Timezone-aware evaluation required")
    now = now.astimezone(UTC)
    c_snapshots = validate_catalog_snapshots(catalog_snapshots, now)
    e_snapshots = validate_espn_snapshots(espn_snapshots, now)
    checked, finals, labels = _verified_labels(cohort, explicit, live, now)
    if official is not None and official.get("status") != "official_report_observed_pit_research_only":
        raise ValueError("Untrusted official injury evidence")
    if telegram is not None and telegram.get("status") != "observed_unconfirmed_research_archive":
        raise ValueError("Untrusted Telegram evidence")
    games = {}
    for g in [*(live.get("schedule") or []), *(live.get("games") or [])]:
        if not isinstance(g, dict) or not g.get("id"):
            continue
        old = games.get(g["id"])
        if not old or (g.get("status") == "final" and old.get("status") != "final"):
            games[g["id"]] = g
    planned = {f["game_id"]
               for _, s in c_snapshots for f in s["future_fixtures_observed"]}
    checked_old = set(checked)
    qa = Counter()
    by_evidence = defaultdict(Counter)
    by_team = defaultdict(Counter)
    records = []
    samples = []
    for gid in sorted(planned | checked_old):
        game = games.get(gid)
        if game is None:
            qa["fixture_disappeared_from_live"] += 1
            continue
        tip = instant(game["utc"])
        lock = tip - LOCK
        eligible_catalog = [
            (at, snap, next(f for f in snap["future_fixtures_observed"]
                            if f["game_id"] == gid))
            for at, snap in c_snapshots
            if at <= lock and lock-at <= MAX_SNAPSHOT_AGE
            and any(f["game_id"] == gid for f in snap["future_fixtures_observed"])
        ]
        if not eligible_catalog:
            qa["without_recent_prelock_catalog_snapshot"] += 1
            continue
        cat_at, cat, fixture = eligible_catalog[-1]
        if ((fixture["home"], fixture["away"], fixture["tipoff_utc"]) !=
                (game["home"], game["away"], stamp(tip))):
            qa["fixture_changed_since_catalog_snapshot"] += 1
            continue
        eligible_espn = [(at, snap) for at, snap in e_snapshots
                         if at <= lock and lock-at <= MAX_SNAPSHOT_AGE]
        if not eligible_espn:
            qa["without_recent_prelock_espn_snapshot"] += 1
            continue
        espn_at, espn = eligible_espn[-1]
        if espn_at > now or cat_at > now:
            raise ValueError("Future input slipped into PIT opportunity")
        matches = {}
        team_state = {}
        for t in espn["teams"]:
            team_state[t["club"]] = t["source_status"]
            for athlete in t["athletes"]:
                pid = athlete["sportsru_player_id"]
                if pid:
                    matches[pid] = (t["club"], athlete)
        final = gid in finals
        if final and finals[gid]["utc"] != game["utc"]:
            qa["final_fixture_conflicts_with_schedule"] += 1
            continue
        qa["games_with_both_prelock_sources"] += 1
        if not final:
            qa["future_or_unverified_final_games"] += 1
        else:
            qa["verified_final_games_with_prelock_sources"] += 1
        samples.append(gid)
        for p in cat["catalog_players_proxy"]:
            if p["catalog_team"] not in (game["home"], game["away"]):
                continue
            key = (gid, p["player_id"])
            found = matches.get(p["player_id"])
            if (team_state.get(p["catalog_team"])
                    == "invalid_or_unavailable"):
                evidence = "ESPN_team_source_unavailable"
            elif found is None:
                evidence = "not_found_in_matched_ESPN_roster_IDs_UNKNOWN"
            elif found[0] != p["catalog_team"]:
                evidence = "club_conflict_between_observed_sources"
            elif found[1]["identity_method"] == HIGH:
                evidence = "same_club_independent_ESPN_ID_observed"
            elif found[1]["identity_method"] == WEAK:
                evidence = "same_club_unique_name_only_observed"
            else:
                raise ValueError("Unexpected independent roster confidence")
            label = labels.get(key) if gid in checked and final else None
            if (label is None or label["team"] != p["catalog_team"]
                    or label["position"] != p["position"]):
                outcome = UNKNOWN
            else:
                outcome = ("played_verified_after_game" if
                           label["participation_label"] == 1 else
                           "explicit_dnp_verified_after_game")
            # A live report produced BEFORE game lock must not see injury
            # signals published/first-observed between now and future lock.
            # Historical evaluation after lock uses the actual lock cutoff.
            evidence_cutoff = min(now, lock)
            official_at_lock = official_asof(
                official, gid, p["player_id"], p["catalog_team"], evidence_cutoff
            ) if official else None
            telegram_at_lock = telegram_asof(
                telegram, p["player_id"], evidence_cutoff
            ) if telegram else None
            row = {
                "game_id": gid, "player_id": p["player_id"],
                "team_in_catalog_snapshot": p["catalog_team"],
                "fantasy_position": p["position"],
                "game_utc": game["utc"], "individual_lock_utc": stamp(lock),
                "catalog_capture_utc": stamp(cat_at),
                "espn_roster_capture_utc": stamp(espn_at),
                "context_known_asof_utc": stamp(evidence_cutoff),
                "club_cross_source_evidence": evidence,
                "game_day_active_eligible": "UNVERIFIED",
                "postgame_outcome": outcome,
                "postgame_evidence": label["evidence"] if outcome != UNKNOWN else None,
                "postgame_first_seen_at_utc":
                    label.get("source_first_observed_at_utc") if outcome != UNKNOWN else None,
                "postgame_first_seen_timestamp_verified":
                    bool(outcome != UNKNOWN and
                         label.get("source_first_observed_at_utc")),
                "official_status_known_before_lock":
                    official_at_lock.get("status") if official_at_lock else None,
                "telegram_context_unconfirmed_before_lock": bool(telegram_at_lock),
                "unknown_NEVER_implies_DNP": True,
                "no_p_play_model": True,
            }
            records.append(row)
            for counter in (qa, by_evidence[evidence], by_team[p["catalog_team"]]):
                counter["catalog_proxy_player_games"] += 1
                counter[evidence] += 1
                counter[outcome] += 1
                if official_at_lock:
                    counter["official_prelock_context"] += 1
                if telegram_at_lock:
                    counter["telegram_unconfirmed_prelock_context"] += 1
            if len(records) > MAX_REPORT_ROWS:
                raise ValueError("Unsafe report expansion")
    conflicts = [
        {"player_id": a["sportsru_player_id"], "espn_club": t["club"],
         "catalog_club_at_capture": a["catalog_team_at_capture"],
         "identity_evidence": a["identity_method"],
         "espn_person_id": a["espn_person_id"]}
        for _, snapshot in e_snapshots[-1:] for t in snapshot["teams"]
        for a in t["athletes"] if a.get("sportsru_player_id")
        and a.get("catalog_team_at_capture") != t["club"]
    ]
    qa["verified_outcomes_missing_first_observed_clock"] = sum(
        row["postgame_outcome"] != UNKNOWN and
        not row["postgame_first_seen_timestamp_verified"]
        for row in records)
    qa["verified_finals_with_both_prelock_sources"] = qa[
        "verified_final_games_with_prelock_sources"]
    if qa["catalog_proxy_player_games"] != len(records):
        raise ValueError("Incomplete evidence accounting")
    if (qa["played_verified_after_game"]+qa["explicit_dnp_verified_after_game"]
            +qa[UNKNOWN] != len(records)):
        raise ValueError("Inferred an unverified negative participation label")
    return {
        "schema_version": 1, "status": STATUS, "model_status": STATUS,
        "adopt_on_site": False, "updated_at_utc": stamp(now),
        "unit": "catalog_player_x_fixture_with_both_sources_observed_before_lock",
        "summary": dict(qa), "by_evidence": {
            k: dict(v) for k,v in sorted(by_evidence.items())},
        "by_catalog_team": {k: dict(v) for k,v in sorted(by_team.items())},
        "last_espn_snapshot_conflicts": conflicts,
        "last_espn_snapshot_teams_available":
            e_snapshots[-1][1]["all_teams_available"] if e_snapshots else False,
        "sampled_game_ids": samples, "records": records,
        "verified_game_day_roster_denominator": False,
        "missing_athlete_is_dnp": False,
        "p_play_training_permitted": False,
        "population_brier_or_logloss_permitted": False,
        "keep_transfer_gain_estimated": False,
        "prospective_fixtures_prelock_only": True,
        "postgame_labels_are_not_pregame_features": True,
        "limitations": [
            "An ESPN CURRENT team roster is not a final NBA game-day active roster.",
            "Strong ESPN ID is a strong ID link only, NOT evidence that a player will play.",
            "A missing ESPN roster match, roster source error or club conflict remains UNKNOWN.",
            "Historical pre-snapshot games are excluded; no retrospective membership is invented.",
            "All postgame labels are learned only from final verified boxes after games.",
            "Official injury / Telegram context is capped at min(now, player lock); future observations cannot appear early.",
            "Postgame evidence without a recorded first-observed timestamp is explicitly counted, never backdated.",
            "No p_play training, validation, Brier or claimed KEEP/TRANSFER gain.",
        ],
    }


def run():
    def read(path):
        return json.loads(path.read_text(encoding="utf8"))
    now = datetime.now(UTC)
    c_path = DATA/"catalog_pit"
    e_path = DATA/"espn_roster_pit"
    catalog = [read(p) for p in sorted(c_path.glob("*.json"))]
    espn = [read(p) for p in sorted(e_path.glob("*.json"))]
    value = build(
        read(DATA/"live.json"),
        read(DATA/"participation_cohort_research.json"),
        read(DATA/"explicit_dnp_research.json"), catalog, espn, now,
        read(DATA/"official_injury_status_archive.json"),
        read(DATA/"telegram_archive.json"))
    target=DATA/"prelock_roster_opportunities_research.json"
    tmp=target.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False,
                              separators=(",",":")), encoding="utf8")
    tmp.replace(target)
    return {
        "status": value["status"], "adopt_on_site": value["adopt_on_site"],
        "summary": value["summary"],
        "last_espn_snapshot_conflicts": value["last_espn_snapshot_conflicts"],
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
