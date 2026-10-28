"""Fail-closed consistency gate for the atomic public NBA research sync.

This checks same-snapshot *sets and source labels*, not timestamp proximity.
It never infers DNP from absence, status OUT, or zero minutes.
"""
from collections import Counter, defaultdict
import json

from src.sync import DATA

STATUS = 'research_only_not_deployed'
FILES = {
    'live': 'live.json',
    'explicit': 'explicit_dnp_research.json',
    'cohort': 'participation_cohort_research.json',
    'coverage': 'participation_coverage_research.json',
    'shadow': 'p_play_shadow_research.json',
    'selection': 'p_play_selection_bias_audit.json',
    'ledger': 'participation_evidence_ledger_research.json',
    'paired': 'p_play_precommitted_paired_evaluation_research.json',
    'history': 'historical_prior_prospective_shadow_research.json',
}


def ensure(ok, message):
    if not ok:
        raise ValueError('Atomic public sync integrity: ' + message)


def indexed(rows, name):
    ensure(isinstance(rows, list), name + ' is not a row list')
    result = {}
    for r in rows:
        ensure(isinstance(r, dict), name + ' contains malformed row')
        key = (r.get('game_id'), r.get('player_id'))
        ensure(all(isinstance(v, str) and v for v in key) and key not in result,
               name + ' has duplicate/invalid player-game')
        result[key] = r
    return result


def verify(b):
    for name in ('explicit', 'cohort', 'coverage', 'shadow', 'selection', 'ledger', 'paired'):
        source = b[name]
        ensure(source.get('schema_version') == 1 and source.get('status') == STATUS
               and source.get('adopt_on_site') is False,
               name + ' must remain research-only')
    ensure(b['shadow'].get('population_brier_enabled') is False,
           'selected p_play cannot represent the full fantasy population')
    ensure(b['coverage'].get('full_population_brier_enabled') is False,
           'catalog proxy cannot become a population label')
    ensure(b['selection'].get('quality_gate', {}).get('unknown_are_not_DNP') is True,
           'UNKNOWN provenance protection was weakened')
    ensure(b['paired'].get('unknown_never_mapped_to_DNP') is True,
           'paired UNKNOWN provenance protection was weakened')

    finals = [g for g in b['live'].get('games', []) if g.get('status') == 'final']
    final_ids = {g.get('id') for g in finals}
    ensure(len(final_ids) == len(finals) and all(isinstance(gid, str) for gid in final_ids),
           'duplicate or invalid final games')
    checked = b['explicit'].get('checked_final_game_ids')
    ensure(isinstance(checked, list) and len(checked) == len(set(checked))
           and set(checked).issubset(final_ids),
           'DNP-checked game IDs must be unique finalized games')
    checked = set(checked)
    cohort = b['cohort']
    ensure(cohort.get('summary', {}).get('verified_full_boxscores_checked') == len(checked),
           'cohort does not use current DNP-checked game set')
    labelled = indexed(cohort.get('records'), 'cohort verified labels')
    ensure(len(labelled) == cohort['summary'].get('listed_player_game_labels'),
           'cohort labelled row denominator differs')
    for (gid, _), r in labelled.items():
        ensure(gid in checked, 'cohort label is outside checked-game set')
        y = r.get('participation_label')
        ensure(type(y) is int and y in (0, 1) and
               r.get('evidence') == ('positive_minutes_verified_sportsru_fp' if y else
                                      'explicit_espn_didNotPlay_true'),
               'cohort has unsupported outcome or evidence')

    coverage = b['coverage']
    cs = coverage.get('summary', {})
    ensure(set(coverage.get('by_game', {})) == checked,
           'coverage by_game does not equal the checked-game source set')
    ensure(cs.get('checked_games') == len(checked)
           and cs.get('games_without_complete_dnp_audit') == len(final_ids)-len(checked),
           'coverage game denominators are stale')
    proxy = indexed(coverage.get('catalog_proxy_records'), 'catalog proxy')
    outside = coverage.get('verified_outcomes_outside_proxy')
    ensure(isinstance(outside, list), 'missing out-of-proxy confirmed label records')
    counts = Counter(r.get('observed_outcome') for r in proxy.values())
    for label in ('played_verified', 'explicit_dnp_verified',
                  'unknown_roster_membership_or_unlisted'):
        ensure(counts[label] == cs.get(label, 0), 'catalog proxy ' + label + ' count stale')
    ensure(set(counts).issubset({'played_verified', 'explicit_dnp_verified',
                                'unknown_roster_membership_or_unlisted'})
           and len(proxy) == cs.get('catalog_proxy_candidate_player_games')
           and counts['unknown_roster_membership_or_unlisted'] ==
               cs.get('unknown_is_not_absent_or_injured'),
           'proxy unknown/known accounting changed')
    ensure(cs.get('verified_labels_total') == len(labelled)
           and cs.get('verified_labels_outside_catalog_proxy') == len(outside)
           and (counts['played_verified'] + counts['explicit_dnp_verified']
                + len(outside) == len(labelled)),
           'confirmed cohort labels lost or fabricated by catalog proxy')
    for key, row in proxy.items():
        outcome = row['observed_outcome']
        if outcome != 'unknown_roster_membership_or_unlisted':
            source = labelled.get(key)
            ensure(source is not None and source.get('team') == row.get('match_team')
                   and outcome == ('played_verified' if source['participation_label']
                                   else 'explicit_dnp_verified')
                   and source['evidence'] == row.get('evidence'),
                   'catalog proxy labelled an unverified player-game')

    shadow = b['shadow']
    issued = indexed(shadow.get('issued'), 'frozen p_play first issues')
    observed = indexed(shadow.get('observations'), 'verified p_play observations')
    ensure(set(observed).issubset(issued), 'p_play verified observation without first issue')
    for observation in observed.values():
        y = observation.get('actual_played')
        ensure(type(y) is int and y in (0, 1) and
               observation.get('label_provenance') == (
                   'positive_minutes_verified_sportsru_fp' if y else
                   'explicit_espn_didNotPlay_true'),
               'UNKNOWN or weak evidence cannot become a verified negative')
    ensure(len(issued) == shadow.get('summary', {}).get('issued_prelock_forecasts')
           and len(observed) == shadow['summary'].get('verified_selected_labels'),
           'frozen p_play issued/verified counts changed')
    finished = {key: row for key, row in issued.items() if key[0] in checked}
    known = {key: row for key, row in observed.items() if key in finished}
    ensure(set(known).issubset(finished), 'selection observed outside issued/checked set')
    sel = b['selection']
    unknown = len(finished) - len(known)
    ensure(sel.get('total_issued_predictions') == len(issued)
           and sel.get('finished_checked') == len(finished)
           and sel.get('verified_postgame_results') == len(known)
           and sel.get('unknown_postgame_results') == unknown
           and sel.get('future_or_not_checked') == len(issued)-len(finished),
           'p_play selection denominator or UNKNOWN are stale')
    groups = defaultdict(Counter)
    for key in finished:
        gid = key[0]
        groups[gid]['finished_checked'] += 1
        if key in known:
            groups[gid]['verified_played' if known[key].get('actual_played') == 1
                        else 'explicit_DNP'] += 1
        else:
            groups[gid]['outcome_UNKNOWN'] += 1
    ensure(set(sel.get('by_game', {})) == set(groups),
           'p_play selection checked-game groups are stale')
    for gid, counter in groups.items():
        ensure(set(sel['by_game'][gid]).issubset(
            {'finished_checked', 'verified_played', 'explicit_DNP', 'outcome_UNKNOWN'}),
            'selection has an unsupported game-level classification')
        for category, total in counter.items():
            ensure(sel['by_game'][gid].get(category, 0) == total,
                   'p_play selection game-level ' + category + ' stale: ' + gid)
    outqueue = sel.get('out_status_missing_review_queue')
    ensure(isinstance(outqueue, list) and
           len(outqueue) == sel.get('official_OUT_unknown_review_priority_count'),
           'official OUT review queue count is stale')
    for key, row in indexed(outqueue, 'official OUT UNKNOWN review').items():
        ensure(key in finished and key not in known and
               row.get('actual_played') == 'UNKNOWN_NOT_INFERRED',
               'official OUT has been silently promoted to DNP')
    sensitivity = sel.get('all_finished_with_unknown_binary_sensitivity') or {}
    ensure(sensitivity.get('n') == len(finished)
           and sensitivity.get('verified') == len(known)
           and sensitivity.get('missing') == unknown,
           'selection unknown sensitivity has a stale cohort')

    ledger = b['ledger']
    lc = ledger.get('overall_selected_opportunity_coverage', {})
    played = sum(r.get('actual_played') == 1 for r in known.values())
    dnp = len(known) - played
    ensure(lc.get('finished_checked') == len(finished)
           and lc.get('verified_played') == played
           and lc.get('verified_explicit_DNP') == dnp
           and lc.get('outcome_UNKNOWN') == unknown
           and ledger.get('issued_total_including_future') == len(issued),
           'evidence ledger is not coherent with new selection source')
    paired = b['paired']
    historical_issues = indexed(b['history'].get('issued'), 'frozen historical paired issues')
    pc = paired.get('paired_cohort', {})
    ensure(paired.get('p_play_first_issued_total') == len(issued)
           and paired.get('historical_prelock_overlapping_issued_total') == len(historical_issues)
           and pc.get('issued') == len(historical_issues)
           and pc.get('finished_checked') == pc.get('verified_pairs', 0)
               + pc.get('outcome_UNKNOWN', 0) + pc.get('waiting_historical_reconciliation', 0),
           'historical paired evaluation was not synchronized')
    return {'checked_games': len(checked), 'cohort_verified': len(labelled),
            'proxy_unknown': counts['unknown_roster_membership_or_unlisted'],
            'frozen_issued': len(issued), 'selection_finished': len(finished),
            'selection_verified': len(known), 'selection_UNKNOWN': unknown,
            'historical_pairs_issued': len(historical_issues),
            'evidence_ledger_coherent': True, 'adopt_on_site': False}


def run():
    snapshots = {k: json.loads((DATA/name).read_text(encoding='utf8'))
                 for k, name in FILES.items()}
    return verify(snapshots)


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False, indent=2))
