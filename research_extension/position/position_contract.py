"""Point-in-time fantasy-position contract; never infer PG/SG/SF/PF from G/F.

The contract allows a mapping to be used only after its actual observation,
inside its effective interval and season. Names help construct a reviewable
mapping, but inference uses an exact NBA person_id. Catalog snapshots remain
catalog evidence and are not labelled independently verified Sports.ru data.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata

POSITIONS = frozenset({"PG", "SG", "SF", "PF", "C"})


def timestamp(value: str) -> datetime:
    out = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if out.tzinfo is None:
        raise ValueError("POSITION_TIMEZONE_REQUIRED")
    return out.astimezone(timezone.utc)


def normalize_name(value: str) -> str:
    """Diacritic/punctuation normalization only; no fuzzy matching or nicknames."""
    value = "".join(
        char for char in unicodedata.normalize("NFKD", str(value))
        if not unicodedata.combining(char)
    ).casefold()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", value).split())


def resolve_position(records, person_id, season, issue_at):
    issue = timestamp(issue_at)
    eligible = []
    rejected = []
    for row in records:
        if str(row.get("person_id", "")) != str(person_id):
            continue
        if row.get("season") != season:
            rejected.append("season_mismatch")
            continue
        if row.get("position") not in POSITIONS:
            rejected.append("unknown_or_coarse_position")
            continue
        if row.get("identity_status") != "exact_unique_normalized_name":
            rejected.append("unresolved_identity")
            continue
        if row.get("source_kind") not in {"fantasy_catalog_snapshot", "official_fantasy_position"}:
            rejected.append("unapproved_position_source")
            continue
        if not row.get("source_sha256") or not row.get("source_ref"):
            rejected.append("missing_provenance")
            continue
        observed = timestamp(row["observed_at"])
        effective = timestamp(row["effective_from"])
        if observed > issue or effective > issue:
            rejected.append("not_yet_available")
            continue
        if row.get("effective_until") and issue >= timestamp(row["effective_until"]):
            rejected.append("expired")
            continue
        eligible.append(row)
    if not eligible:
        return {"position": "UNKNOWN", "status": "unresolved", "reasons": sorted(set(rejected))}
    # Explicit effective intervals are required to supersede conflicting rows.
    # Picking the newest observation alone would hide an unresolved discrepancy.
    choices = {r["position"] for r in eligible}
    if len(choices) != 1:
        return {"position": "UNKNOWN", "status": "conflict", "reasons": ["conflicting_valid_snapshots"]}
    source = max(eligible, key=lambda r: timestamp(r["observed_at"]))
    return {"position": source["position"], "status": "resolved_catalog" if source["source_kind"] == "fantasy_catalog_snapshot" else "resolved_official", "source_ref": source["source_ref"], "source_sha256": source["source_sha256"], "observed_at": source["observed_at"]}
