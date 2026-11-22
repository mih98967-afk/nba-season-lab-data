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
        'archive_box_rows_for_game': sum(r.get('game_id') == game_id for r in archive_box),
        'reconciliation': 'verified_identity_reuse_without_duplicate_inactive_player_game',
        'unknown_assumed_inactive': False,
    }

# All boxscore components used by the preserved FP feature pipeline are checked.
# The archive rounds percentages to three decimals; other values must agree.
BOX_NUMERIC_FIELDS = (
    'field_goals_made', 'field_goals_attempted', 'field_goals_percentage',
    'three_pointers_made', 'three_pointers_attempted', 'three_pointers_percentage',
    'free_throws_made', 'free_throws_attempted', 'free_throws_percentage',
    'rebounds_offensive', 'rebounds_defensive', 'rebounds_total', 'assists',
    'steals', 'blocks', 'turnovers', 'fouls_personal', 'points', 'plus_minus_points',
)
BOX_IDENTITY_FIELDS = ('team_id', 'team_tricode', 'season', 'season_type_id', 'side')


def _numeric(value):
    import math
    if value in (None, ''):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError('SUPPLEMENT_ARCHIVE_BOXSCORE_INVALID_NUMBER')
    if not math.isfinite(result):
        raise ValueError('SUPPLEMENT_ARCHIVE_BOXSCORE_INVALID_NUMBER')
    return result


def _minute_seconds(value):
    if value in ('', None):
        return 0.0
    if isinstance(value, str) and ':' in value:
        parts = value.split(':')
        if len(parts) != 2:
            raise ValueError('SUPPLEMENT_BOXSCORE_INVALID_MINUTES')
        minutes, seconds = map(float, parts)
        if not (0 <= seconds < 60):
            raise ValueError('SUPPLEMENT_BOXSCORE_INVALID_MINUTES')
        return minutes * 60 + seconds
    number = _numeric(value)
    if number is None:
        return 0.0
    return number * 60


def reconcile_official_box(game_id, archive_box, official_box):
    """Keep verified archival player-games, append only genuinely missing IDs.

    Do not normalize or rewrite existing archive game rows; in particular their
    literal DNP/DND comments are source evidence, not inferred from zero minutes.
    """
    if not game_id or not official_box:
        raise ValueError('SUPPLEMENT_OFFICIAL_BOXSCORE_IDENTITY_CONFLICT')
    official = {}
    for row in official_box:
        pid = str(row.get('person_id') or '')
        if row.get('game_id') != game_id or not pid or pid in official:
            raise ValueError('SUPPLEMENT_OFFICIAL_BOXSCORE_IDENTITY_CONFLICT')
        official[pid] = row
    retained = {}
    for row in archive_box:
        if row.get('game_id') != game_id:
            continue
        pid = str(row.get('person_id') or '')
        if not pid or pid in retained:
            raise ValueError('SUPPLEMENT_DUPLICATE_ARCHIVE_BOXSCORE_PLAYER')
        other = official.get(pid)
        if other is None:
            raise ValueError('SUPPLEMENT_ARCHIVE_BOXSCORE_CONFLICT:PLAYER')
        for field in BOX_IDENTITY_FIELDS:
            if str(row.get(field, '')) != str(other.get(field, '')):
                raise ValueError('SUPPLEMENT_ARCHIVE_BOXSCORE_CONFLICT:' + field.upper())
        # Older archive may lack jersey and use broader positions: these are
        # not stable keys. Never rely on display names for identity matching.
        jersey = str(row.get('jersey_num') or '').strip()
        official_jersey = str(other.get('jersey_num') or '').strip()
        if jersey and official_jersey and jersey.lstrip('0') != official_jersey.lstrip('0'):
            raise ValueError('SUPPLEMENT_ARCHIVE_BOXSCORE_CONFLICT:JERSEY')
        if abs(_minute_seconds(row.get('minutes')) - _minute_seconds(other.get('minutes'))) > 0.02:
            raise ValueError('SUPPLEMENT_ARCHIVE_BOXSCORE_CONFLICT:MINUTES')
        for field in BOX_NUMERIC_FIELDS:
            a, b = _numeric(row.get(field)), _numeric(other.get(field))
            if a is None or b is None:
                if a != b:
                    raise ValueError('SUPPLEMENT_ARCHIVE_BOXSCORE_CONFLICT:' + field.upper())
            elif abs(a-b) > (0.00050001 if field.endswith('_percentage') else 0.00000001):
                raise ValueError('SUPPLEMENT_ARCHIVE_BOXSCORE_CONFLICT:' + field.upper())
        retained[pid] = row
    missing = [row for row in official_box if str(row['person_id']) not in retained]
    return missing, {
        'archive_box_rows_verified_and_retained': len(retained),
        'official_box_rows_total': len(official_box),
        'new_official_box_rows_added': len(missing),
        'reconciliation': 'verified_identity_minutes_all_stat_components_no_duplicate_player_game',
        'archive_comments_preserved_without_DNP_inference': True,
    }
