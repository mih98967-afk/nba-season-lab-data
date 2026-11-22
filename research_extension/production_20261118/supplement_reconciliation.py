"""Fail-closed reconciliation of independently advancing NBA archive feeds.

An archived inactive roster may arrive before the archive's scores or boxscore.
Official final supplementation must not append that same player-game twice.
Only exact NBA player/team/season/jersey identity is reusable; archived boxscores
remain protected against silent replacement. Display-name spellings are not IDs.
"""
from __future__ import annotations


IDENTITY_FIELDS = ('team_id', 'team_abbreviation', 'season', 'season_type_id')


def reconcile_official_inactive(game_id, archive_box, archive_rosters, official_box, official_inactive):
    """Return strictly new official inactive rows and an auditable per-game ledger.

    Inputs are unmodified. Every retained archived inactive row must match the
    final official roster's person and team identities. An official INACTIVE is
    not inferred from an absent boxscore player; UNKNOWN never becomes DNP.
    """
    if not game_id:
        raise ValueError('SUPPLEMENT_MISSING_GAME_ID')
    if any(r.get('game_id') == game_id for r in archive_box):
        raise ValueError('SUPPLEMENT_DUPLICATES_ARCHIVE_ROWS:BOXSCORE')
    if not official_box or any(r.get('game_id') != game_id for r in official_box):
        raise ValueError('SUPPLEMENT_OFFICIAL_BOXSCORE_IDENTITY_CONFLICT')
    official_players = [str(r.get('person_id', '')) for r in official_box]
    if any(not pid for pid in official_players) or len(set(official_players)) != len(official_players):
        raise ValueError('SUPPLEMENT_DUPLICATE_OFFICIAL_BOXSCORE_PLAYER')
    players = set(official_players)
    verified = {}
    for row in official_inactive:
        pid = str(row.get('player_id', ''))
        if row.get('game_id') != game_id or not pid or pid not in players:
            raise ValueError('SUPPLEMENT_OFFICIAL_INACTIVE_IDENTITY_CONFLICT')
        if pid in verified:
            raise ValueError('SUPPLEMENT_DUPLICATE_OFFICIAL_INACTIVE_PLAYER')
        verified[pid] = row
    reused = {}
    for row in archive_rosters:
        if row.get('game_id') != game_id:
            continue
        pid = str(row.get('player_id', ''))
        if not pid or pid in reused:
            raise ValueError('SUPPLEMENT_DUPLICATE_ARCHIVE_INACTIVE_PLAYER')
        official = verified.get(pid)
        if official is None:
            raise ValueError('SUPPLEMENT_ARCHIVE_INACTIVE_CONFLICT:PLAYER')
        for field in IDENTITY_FIELDS:
            if str(row.get(field, '')) != str(official.get(field, '')):
                raise ValueError('SUPPLEMENT_ARCHIVE_INACTIVE_CONFLICT:' + field.upper())
        # A changed jersey number is a conflict when both snapshots state it.
        old_jersey = str(row.get('jersey_num') or '').strip()
        new_jersey = str(official.get('jersey_num') or '').strip()
        if old_jersey and new_jersey and old_jersey.lstrip('0') != new_jersey.lstrip('0'):
            raise ValueError('SUPPLEMENT_ARCHIVE_INACTIVE_CONFLICT:JERSEY')
        reused[pid] = row
    to_add = [row for row in official_inactive if str(row['player_id']) not in reused]
    return to_add, {
        'archive_inactive_rows_verified_and_retained': len(reused),
        'official_inactive_rows_total': len(official_inactive),
        'new_official_inactive_rows_added': len(to_add),
        'archive_box_rows_for_game': 0,
        'reconciliation': 'verified_identity_reuse_without_duplicate_inactive_player_game',
        'unknown_assumed_inactive': False,
    }
