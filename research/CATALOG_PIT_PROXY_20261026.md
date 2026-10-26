# Prospective catalog / fixture proxy research

Existing NBA Season Lab, research-only. Static `data/catalog.json` is not a historical roster, and its club assignment is not a verified official game-day active list.

This scheduled pipeline captures the state of the *existing* static catalog and the verified upcoming fixture list at a truthful UTC time, and never retroactively assigns an earlier timestamp. Each Moscow calendar date gets one immutable snapshot file. If an earlier file exists it is preserved, including when current source data change.

After final games, selected independently verified positive-minute participation or explicit ESPN `didNotPlay=true` outcomes are joined to player-game opportunities **only** when the snapshot existed before the -30m individual lock, is no older than 36h at that lock, and contains an exact matching fixture. Missing athletes, historical roster uncertainty, changed fixtures and events preceding the first snapshot stay UNKNOWN or excluded.

Official injury PDFs and Telegram are attached only using the existing point-in-time provenance checks, never as confirmed games-played labels. This research is NOT an online source refresh of Sports.ru club membership; that will require a separately validated catalog retrieval pipeline and historical team-tenure proof.

No p_play, Brier, log-loss, keep/transfer advantage, production site or account mutation. `research_only_not_deployed`, `adopt_on_site=false`.
