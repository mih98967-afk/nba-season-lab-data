# General and five-position matchup difficulty

This package extends the existing NBA Season Lab scientific snapshot. It does not retrain the selected production forecast model or change frozen forecasts. It requires no paid service, database write, Firebase change or user workbook in the daily job.

## Decisions and limits

* The original 82-feature matchup-aware Ridge won the preregistered development comparison. The positional interaction was not retained. `ACCEPTANCE_SUMMARY.md` and the small readable reports contain the complete result.
* General opponent context is **already inside the Ridge forecast**. Adding this difficulty score to its E(FP) would double-count that context.
* Position-specific effects are **descriptive research only**. They must not adjust player means, P(play), match prediction intervals, transfers or any optimizer.
* Positive FP delta means an easier opponent; negative means harder. These are conditional played-game contrasts for a standard reference population, not an individual player's additional guaranteed points.
* `effect_interval95` describes approximate uncertainty of the effect estimate. It is not a per-match FP prediction interval or an interval for summed games. Coverage is not guaranteed.
* The four Sports.ru XLSX provide retrospective season positions. They do not prove historical pregame position vintages. NBA-ID mappings are season-specific; unmatched rows remain UNKNOWN. An undated recent-game tail is not an independent dated per-player-game credited target.
* The supplied quote is the observed current price, not the starting price or a verified T−30 quote. This package contains no ownership/transfer data.

## Daily inference after the existing model export

```bash
python research_extension/position_20261118/build_difficulty.py \
  --future-frame "$RUNNER_TEMP/nba-model-run/inference/future_features.pkl" \
  --source "$RUNNER_TEMP/nba-model-run/sources/derived/source" \
  --asof-date YYYY-MM-DD \
  --work "$RUNNER_TEMP/nba-model-run/difficulty" \
  --output data/matchup_difficulty_v1.json
```

Use the same coherent source snapshot and the same NBA game-date cutoff as `data/model_forecasts_v1.json['asof_date_et']`. The dependency versions are the existing pinned scientific/inference versions (numpy, pandas, scipy, scikit-learn and the shared source-loader dependencies). The code finds `research/match_context` in the public repository; `NBA_RESEARCH_BASE` can point at the preserved external bundle where applicable.

The command automatically decodes only the required public assets into its work directory and validates every chunk, complete byte size and SHA256 before use. It then reads current-season near-game replay features and calculates residuals using the unchanged frozen Ridge. It performs no model fitting, candidate selection or recalibration. Reusing `--current-frame` is permitted only with a matching generated `.source.json` sidecar; a different source or cutoff fails closed.

`PUBLIC_ASSETS_MANIFEST.json` pins all source bytes. Larger data/model files are stored as UTF-8 base64 chunks of at most59,001 bytes. Each reconstructed original file preserves its exact hash, including the binary Ridge and covariance assets. No XLSX, `research_base`, private folder or historical raw cache is required just to decode them. Historical raw sources remain required by the existing shared source/feature builder, exactly as for the normal model export.

## Contract

`opponents[team][ALL|PG|SG|SF|PF|C]` contains:

* `general_delta_fp`, `position_extra_fp`, `total_delta_fp`;
* `effect_interval95` and separate general/position effect intervals;
* `weighted_player_games`, `effective_games`, cumulative `n_games`, `n_players`, and current-season support;
* `shrinkage_fraction`, `latest_game_date`, and explicit validation/status flags.

The top level includes source timestamps/hashes, fixed reference weighting, rejected-candidate evidence, mapping provenance and limitations. Calendar panels should keep game count separate from average difficulty for the next match and7/14/21/28-day windows. Average each scheduled game once. The rating is a current snapshot; it is not a forecast of future opponent roster changes.

General contrasts give equal weight to each of the496 current eligible reference players and equal home/away weight. The neutral opponent averages30 team snapshots equally; extra fixtures do not increase a team's weight. Player quality, expected minutes and own-team context stay identical between alternatives. Opponent rest and player H2H are held fixed.

Positional descriptive residuals use60-day decay and100-player-game shrinkage. They subtract the opponent and position marginal means, then add the overall mean back. The stronger of the two preregistered priors is used for display only; no positional predictor was selected.

## Identity history overlay and current roster

`results/catalog_history_corrections.json` is a proven read-only overlay proposal for five namesake history errors across `n133`, `n326`, `n346`, `n406`. It blocks contaminated legacy-seed fallback. It does not change historical NBA-ID boxscore features or the archived inputs.

`results/CURRENT_ROSTER_COMPACT.json` is a small column-oriented snapshot: zip its `columns` with each row to reconstruct field names. Full row-level identity/source evidence is the encoded `results/CURRENT_ROSTER_PUBLIC.json` asset. Never map a null NBA ID to a namesake or copy these observed quotes into `start_price`.

The later `results/CURRENT_CATALOG_IDENTITY_OVERLAY.json` extends current release
identity coverage to459 of484 existing catalog cards. It uses exact full English
names observed in the catalog/public live rows, explicitly reviewed current-roster
name/team/position matches, or preserves existing high-confidence IDs. A medium
statistical historical match alone is not upgraded. It adds or upgrades98 IDs and
corrects two conflicting medium historical identities (Jaylon/Hunter Tyson and
Caleb/Kevin Love). It includes complete fingerprints for9 wrong history rows across
7 catalog cards, adding RayJ/Dexter Dennis to the earlier corrections. The original
five-row audit is retained as an earlier checkpoint. These identity improvements
are available only at their recorded current observation time and never rewrite
historical frozen forecasts or NBA-ID-keyed model weights.

Exactly450 of the459 release identities also have a resolved current Sports.ru
roster row; all450 have the same fantasy position as the existing catalog. Nine
known historical NBA IDs lack a resolved current roster row, and25 catalog cards
lack enough new exact evidence for model identity. Those limitations do not imply
DNP. The separately saved450-row position audit is `results/CURRENT_CATALOG_POSITION_AUDIT_RELEASE.json`.

## Tests and reproducibility

```bash
python -m unittest discover -s research_extension/position_20261118 -p 'test_*.py' -v
```

Tests cover date-batch leakage, future outcomes, unknown positions/labels, explicit namesake identities, shrinkage and interaction isolation, fixed neutral-reference weighting, incomplete/incoherent snapshots, historical mapping changes, and corrupted encoded chunks. The normal-equation consistency check reproduces the preserved Ridge coefficients within4.4e−14; the saved weights themselves are not replaced.

The complete current package has28 tests, including six identity-overlay checks:
no medium-only promotion, exact full-name upgrade, conflicting names, unreviewed
ID contradictions, duplicate catalog IDs, and complete historical fingerprints.

Historical experiment reproduction uses the preserved full handoff research sources and common historical feature/nuisance caches. `ingest_positions.py` is for explicit new roster ingestion when the four user workbooks are available, not for the daily inference workflow. Do not reselect on the already exposed2025/26 audit or current2026/27 outcomes.
