# Independent ESPN roster point-in-time capture

After PR #30 established a strictly timed but **cached Sports.ru catalog proxy**, this component records a second, independent public-team-roster snapshot.

Never interpret an ESPN roster listing as an official active list for a specific game. Never infer DNP, injury or ineligibility from an absent athlete. Records are first observed at capture time, not assumed originally published then.

ESPN athlete ID links may be used only when independently seen alongside a named, played NBA boxscore row. Otherwise unambiguous English names are weaker evidence. Cross-team duplicates are quarantined. Source failures are retained per club.

No p_play fitting or deployment, no Sports.ru account, no Firestore, no Firebase Blaze, no paid APIs, no site changes. A first-run CI pass alone does not establish complete provider coverage; inspect the 30-team production capture before treating team mappings as useful.
