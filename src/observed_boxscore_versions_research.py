"""Append-only, actually observed player-game value versions for future as-of replay.

The legacy rolling ledger stores first-seen times and LATEST row hashes, but
its snapshots contain only aggregate correction COUNTS, not earlier values.
As of 29 Oct 2026, 27 corrected row events were observed. Never assume a
current value existed at an earlier first-seen clock! The initial version of
each legacy row is sealed at the CURRENT observation time. Every subsequent
observed correction appends a row version with its OWN real UTC timestamp.

Research-only public NBA boxscores. This does not track historical edits
between observations, establish original provider publication time, or prove
that a player was eligible on Sports.ru.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json

from src.sync import DATA
from src.rolling_decision_research import (
    canonical_hash, instant, player_games, stamp,
)

STATUS = "research_only_not_deployed"
SCHEMA = 1


def _index(player_id, game_id):
    if (not isinstance(game_id, str) or not game_id
            or not isinstance(player_id, str) or not player_id
            or "|" in game_id or "|" in player_id):
        raise ValueError("Unsafe player-game version key")
    return game_id + "|" + player_id


def _entry(row, first_seen, captured, prior_value_not_archived):
    if not instant(row["utc"]) <= first_seen <= captured:
        raise ValueError("Boxscore first-seen provenance before tipoff or after capture")
    return {
        "version_observed_at_utc": stamp(captured),
        "rolling_first_seen_at_utc": stamp(first_seen),
        "row": row,
        "row_sha256": canonical_hash(row),
        "legacy_value_before_version_not_proven":
            bool(prior_value_not_archived),
    }


def replay_asof(archive, cutoff):
    """Use only versions actually SEALED by cutoff; never the latest posthoc row."""
    if cutoff.utcoffset() is None:
        raise ValueError("As-of time must be timezone aware")
    at = cutoff.astimezone(timezone.utc)
    if (archive.get("schema_version") != SCHEMA
            or archive.get("status") != STATUS
            or archive.get("adopt_on_site") is not False):
        raise ValueError("Version archive unavailable or deployable")
    result = {}
    for key, versions in archive.get("versions", {}).items():
        if not isinstance(versions, list) or not versions:
            raise ValueError("Invalid version chain")
        latest = None
        for v in versions:
            observed = instant(v["version_observed_at_utc"])
            if observed > at:
                break
            latest = v
        if latest:
            if canonical_hash(latest["row"]) != latest["row_sha256"]:
                raise ValueError("Corrupted earlier source value")
            result[key] = dict(latest["row"])
    return result


def build(previous, live, rolling, now):
    if now.utcoffset() is None:
        raise ValueError("An actual, aware observation time is required")
    now = now.astimezone(timezone.utc)
    if (live.get("schema_version") != 4
            or rolling.get("schema_version") != 1
            or rolling.get("status") != STATUS
            or rolling.get("adopt_on_site") is not False
            or not isinstance(rolling.get("row_hashes"), dict)
            or not isinstance(rolling.get("row_first_seen_at_utc"), dict)):
        raise ValueError("Current live and rolling source not authenticated")
    if instant(live["updated_at_utc"]) > now:
        raise ValueError("Version input updated in the future")
    indexed, _ = player_games(live, now)
    current = {_index(pid, gid): row for (gid, pid), row in indexed.items()}
    hashes = rolling["row_hashes"]
    first = rolling["row_first_seen_at_utc"]
    if not current or current.keys() != hashes.keys() or current.keys() != first.keys():
        raise ValueError("Live rows must exactly match the authoritative rolling ledger")
    if any(canonical_hash(row) != hashes[k] for k, row in current.items()):
        raise ValueError("Latest live row value does not match authoritative rolling hash")

    if previous and (previous.get("schema_version") != SCHEMA
                     or previous.get("status") != STATUS
                     or previous.get("adopt_on_site") is not False
                     or previous.get("source") != "public_reconstructed_NBA_played_boxscores"
                     or not isinstance(previous.get("versions"), dict)):
        raise ValueError("Archived observation provenance no longer valid")
    versions = {k: [dict(v) for v in history]
                for k, history in (previous or {}).get("versions", {}).items()}
    if set(versions) - set(current):
        raise ValueError("A once-observed row disappeared from NBA public source")
    for key, history in versions.items():
        if not isinstance(history, list) or not history:
            raise ValueError("Empty archived row history")
        last = None
        orig_clock = stamp(instant(first[key]))
        for version in history:
            v_at = instant(version["version_observed_at_utc"])
            row = version["row"]
            if (version.get("rolling_first_seen_at_utc") != orig_clock
                    or version.get("row_sha256") != canonical_hash(row)
                    or row.get("game_id") + "|" + row.get("player_id") != key
                    or v_at < instant(orig_clock)
                    or v_at > now
                    or (last is not None and v_at <= last)):
                raise ValueError("Existing observed row versions were altered")
            last = v_at
    qa = Counter()
    time_label = stamp(now)
    for key, row in sorted(current.items()):
        first_at = instant(first[key])
        prior = versions.get(key)
        if prior is None:
            # Legacy first-seen did not preserve the actual historical ROW.
            # Anchor the current value at this new independent observation time.
            versions[key] = [_entry(row, first_at, now, first_at < now)]
            qa["new_first_valued_versions"] += 1
            if previous and first_at < now:
                qa["previously_seen_unversioned_values_bootstrapped_now"] += 1
        elif prior[-1]["row_sha256"] == hashes[key]:
            qa["unchanged_existing_rows"] += 1
        else:
            last = instant(prior[-1]["version_observed_at_utc"])
            if not last < instant(time_label):
                raise ValueError("Cannot sequence two corrections in the same timestamp")
            prior.append(_entry(row, first_at, now, False))
            qa["new_correction_versions"] += 1
    if previous and not qa["new_first_valued_versions"] and not qa["new_correction_versions"]:
        return previous

    total = sum(len(v) for v in versions.values())
    if len(versions) != len(current) or total < len(current):
        raise ValueError("Versioned row coverage drift")
    first_capture = (previous or {}).get("first_version_archive_at_utc", time_label)
    result = {
        "schema_version": SCHEMA, "status": STATUS,
        "model_status": STATUS, "adopt_on_site": False,
        "source": "public_reconstructed_NBA_played_boxscores",
        "first_version_archive_at_utc": first_capture,
        "updated_at_utc": time_label,
        "source_rolling_latest_hashes_sha256": canonical_hash(hashes),
        "versions": dict(sorted(versions.items())),
        "summary": {
            "unique_player_games": len(versions),
            "captured_row_versions": total,
            "observed_corrections_since_version_archive_started": total-len(versions),
            "new_versions_this_run": qa["new_first_valued_versions"]+qa["new_correction_versions"],
            "new_correction_versions_this_run": qa["new_correction_versions"],
            "legacy_rows_first_versioned_at_archive_start_not_prior_first_seen": sum(
                bool(versions[k][0]["legacy_value_before_version_not_proven"])
                for k in versions),
            "rolling_observed_corrections_total_no_row_values": sum(
                int(snapshot["corrected_rows"])
                for snapshot in rolling.get("snapshots", [])),
            "first_capture_before_version_archive_does_not_prove_row_values": True,
        },
        "quality_gate": {
            "asof_queries_use_version_observed_at_not_legacy_first_seen": True,
            "legacy_row_versions_retroactively_reconstructed": False,
            "future_unobserved_intermediate_corrections_known": False,
            "posthoc_data_can_create_old_prelock_forecast": False,
            "deployment_allowed": False,
            "adopt_on_site": False,
        },
        "limitations": [
            "Original row values from the old rolling ledger were not versioned before this archive.",
            "Initial values of all previously captured rows are only proven at the new archive time.",
            "Earlier rolling timestamps reflect that a row existed, NOT that the current version was available.",
            "An observation at every 4h sync can miss modifications between syncs.",
            "The source is public reconstructed NBA FP, not personal credited Sports.ru FP.",
            "Current values after a corrected score may differ from historic forecast-time values.",
            "No original provider publication clocks or true game-day roster membership inferred.",
            "Research-only; no production forecasts, prices, roster, Firebase or transfers changed.",
        ],
    }
    if previous:
        prev = previous.get("first_version_archive_at_utc")
        if not isinstance(prev, str) or instant(prev) > now:
            raise ValueError("First version archive origin changed")
    return result


def run():
    read = lambda p: json.loads((DATA/p).read_text(encoding="utf8"))
    target = DATA/"observed_boxscore_versions_research.json"
    previous = read(target.name) if target.exists() else {}
    result = build(previous, read("live.json"),
                   read("rolling_decision_research.json"),
                   datetime.now(timezone.utc))
    if result != previous:
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":")),
                       encoding="utf8")
        tmp.replace(target)
    return {
        "research_only": True, "adopt_on_site": False,
        "summary": result["summary"],
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
