# Next work — priority and proof

## P0: Make user-facing evidence actionable without false certainty

**Best next release scope (proposed v6.29; NOT built or published):** inspect the *current* Today and Player views with a verified actual public snapshot and a synthetic/private-safe owner fixture; find one practical remaining read-only ambiguity, preferably distinguishing exact forecast coverage, missing injury evidence, unassigned Cup dates and owner-verified market readiness. Define a narrow UX invariant and a deterministic fail-closed oracle before changing any runtime. Preserve no needless new panels or tabs. If genuine owner data are required, ask only for explicit private owner-authorized evidence; never publish it. The next release number and features are a proposal, not an accepted or completed PR.

## P0: Reconcile owner Sports.ru scoring

First establish two consecutive dated owner checkpoints with authenticated/owner-attested totals, *actual* player/game credited FP when available, roster and transfer dates, any exact executed timestamps and price/quota snapshots. Keep this in browser/private channel. Compare against ownership at each game’s T-30 and verified corrected NBA boxscores; distinguish NBA calculation, Sports.ru credited score and unsolved residual. Date-only placeholders must never be treated as exact timestamps. Without evidence, show n/d and the reason rather than backsolving a score.

## P1: Truly independent prospective minutes

- Scientific protocol frozen at \`docs/NBA_MINUTES_FUTURE_PREREG_20261120.json\`, originally 21-Nov through 8-Dec UTC. Never reissue, backdate, alter thresholds or tune based on viewed outcomes.
- Daily read-only evaluation on frozen source/time hashes (PR #193); ET dates confirmed using NBA tipoff UTC and \`America/New_York\`. Track eligible, verified played, game count, ET dates, DNP/UNKNOWN, MAE/bias, grouped date-bootstrap lower bound.
- Locked progress (23-Nov 10:47 UTC): 161/600 played, 12/60 games, 2/12 ET dates. These are minimum sample **gates**, not green-lit superiority.
- Even after pass, study selected-cohort bias, game-day fantasy population denominator, reliable P(play), unconditional FP and effect on real decisions before changing deployed E(minutes) or FP.

## P1: Participation completeness and player-game matching

Study official roster/inactive entries and independently published status over game-day with provenance; ESPN explicit DNP alone covers only part of population. Retain UNKNOWN (19.79% in a 23-Nov selected finished opportunity cohort); source missing, no NBA ID, DNP, OUT and true not-playing are distinct. Do not publish derived absent=0 labels, fabricate P(play) calibration or use same checked postgame rows to select a predraft roster.

## P1: Independent matchup and FP research

Evaluate time-ordered, pre-T-30, same-eligibility FP performance against old baseline, minutes-only and FP/minute/shrinkage variants. Test opponent by position and recent-form weighting as independently added signal, not assumed uplift. Date cluster, role/club changes, uncertainty coverage, selection bias and forward validation; 2025/26 has already been inspected and is not a pristine holdout. Keep \`adopt_on_site=false\` absent new proof and owner approval.

## P2: Final site polish and documentation

Keep one obvious question “Нужно ли сегодня делать замену?” → KEEP/NOW/LATER → 2–3 evidence-backed reasons → action; compact player cards, position calendar easy to scan, consistent type scale and calm warm palette. Distinguish observed minutes / provisional historical guide / validated forecast. Test keyboard, mobile at 320/390/768 and desktop at 1280/1440, actual sources and all primary routes. Preserve client backup/export and non-automatic transfers.

## Every production release gate

Correct current main & source SHA → isolated \`site/hosting_vNNN\` candidate → regression/unit tests → browser fixture **and** actual public snapshot QA → matched frozen model bytes/source timestamps/expiry/coverage → green PR CI → owner-reviewed merge → verified main CI complete Hosting ZIP → owner manual Firebase Hosting deploy → owner profile smoke check. Do not reuse expired ZIP, assume workflow success is Hosting success, or leak owner records.
