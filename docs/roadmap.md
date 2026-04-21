# x-bookmarks — Roadmap

## Completed

### v1 — Core Pipeline
- [x] OAuth 2.0 PKCE authentication flow
- [x] Bookmark fetching with pagination (up to 800)
- [x] Automatic token refresh on 401
- [x] Claude-based categorization (single batch)
- [x] Obsidian Markdown generation with frontmatter
- [x] Deduplication at write time by `tweet_id`
- [x] Long-form tweet (`note_tweet`) support
- [x] X Article detection and content extraction

### v1.1 — Efficiency & Configuration
- [x] Early deduplication — filter already-saved bookmarks **before** Claude API call to avoid wasting credits
- [x] `KNOWLEDGE_BASE_DIR` env var — configurable knowledge base root path

### v1.2 — Taxonomy Alignment
- [x] **Align taxonomy with AGENTS.md** — enforce the fixed 10-category AI taxonomy in the Claude system prompt instead of free-form categorization
- [x] **subCategory frontmatter field** — added `subCategory` (camelCase) to frontmatter for finer-grained Dataview queries
- [x] **Body structure alignment** — restructured note body to `## {title}` / `## References` sections (initial v1.2 used `## Notes`; subsequently replaced with `## {title}` for descriptive headings; `migrate.py` exists to backfill old files)

## Planned

Items are grouped into execution tiers in priority order. Each links to the corresponding GitHub issue in [`docs/github-issues.md`](github-issues.md). Priority reflects safety-first sequencing: credential hardening and dev-safety scaffolding precede content features.

### Tier 1 — Safety & Efficiency Foundations
- [ ] **[#14] Token persistence security** — replace plaintext `.env` token storage with a more secure mechanism
- [ ] **[#10] CLI dry-run mode** — `--dry-run` fetches and categorizes without writing files; unlocks safer iteration on later tiers
- [ ] **[#1] Incremental fetch with `since_id`** — store newest tweet_id from last run and stop pagination once reached

### Tier 2 — Reliability
- [ ] **[#15] X API rate-limit backoff** — respect rate-limit headers with bounded retries; prerequisite for scheduled runs
- [ ] **[#6] Chunk large categorization batches** — split 500+ bookmark runs into deterministic Claude calls; avoid silent JSON corruption
- [ ] **[#2] Configurable bookmark cap** — expose `_MAX_BOOKMARKS` (currently hardcoded at 800) via CLI flag or env var

### Tier 3 — Content Quality
- [ ] **[#3] Article extraction for external links** — fetch and clean article body via `defuddle` for non-X URLs
- [ ] **[#4] Thread unrolling** — detect tweet threads and stitch related posts into a single coherent note
- [ ] **[#5] Quote tweet expansion** — inline quoted tweet content into the parent note

### Tier 4 — UX & Automation
- [ ] **[#11] Verbose and quiet CLI modes** — control output verbosity for debugging vs automation contexts
- [ ] **[#7] Obsidian tags from categories** — generate `#tags` from category slugs for tag-based navigation
- [ ] **[#13] Scheduled run support** — cron/systemd examples; depends on `#14` and `#15`

### Tier 5 — Polish
- [ ] **[#8] Wikilinks between related notes** — cross-link notes that share authors or categories
- [ ] **[#9] Daily note integration** — append a summary of new bookmarks to the daily note
- [ ] **[#12] Periodic summary reports** — weekly/monthly digest of saved bookmarks by category

### Dependency Notes
- `#13` requires `#14` and `#15`
- `#1` and `#2` pair naturally (both touch fetch loop configuration)
- `#10` and `#11` pair naturally (both CLI flag work)
- `#4` and `#5` share tweet-parsing expansion logic

### Priority Rationale
- **Why `#14` first:** public-release audit flags plaintext token storage as the highest remaining risk.
- **Why `#10` second:** tiny effort, but makes every later content feature safer to iterate on and demo.
- **Why `#1` third:** today's run showed 58 of 99 fetched bookmarks were already on disk — `since_id` would avoid fetching them in the first place.
- **Alternate ordering:** if use is single-user and local-only, promote `#3` (article extraction) above `#14` — bigger day-to-day quality win at the cost of leaving token handling untouched.
