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
- [x] **Align taxonomy with AGENTS.md** — *(superseded in v1.4)* originally enforced a fixed 10-category AI taxonomy in the Claude system prompt; this was later replaced by the dynamic, vault-derived approach and is now formalized in v1.4 with a neutral built-in default plus an optional user override
- [x] **subCategory frontmatter field** — added `subCategory` (camelCase) to frontmatter for finer-grained Dataview queries
- [x] **Body structure alignment** — restructured note body to `## {title}` / `## References` sections (initial v1.2 used `## Notes`; subsequently replaced with `## {title}` for descriptive headings; `migrate.py` exists to backfill old files)

### v1.3 — Synthesized Bookmark Removal
- [x] **Strict synthesized marker** — generated and backfilled active notes include `synthesized: false`; only exact `synthesized: true` is eligible for X-side removal
- [x] **Explicit removal mode** — `uv run x-bookmarks --remove-synthesized-bookmarks` scans existing notes without fetching bookmarks or calling Claude
- [x] **Destructive-mode safeguards** — live deletion requires confirmation, supports `--dry-run`, caps live runs at 50 deletions, and reports missing `bookmark.write` scope on 403
- [x] **Archive and history records** — successful or already-absent removals add `bookmark_removed` metadata, move notes to `output_dir / "archive"`, and append removal records to `.x-bookmarks-history.jsonl`

### v1.4 — Configurable Taxonomy
- [x] **Centralized taxonomy module** — `src/taxonomy.py` holds `DEFAULT_TAXONOMY`, override loading, merge, and the shared `build_taxonomy_section`; removes duplication between `categorizer.py` and `migrate.py`
- [x] **Neutral built-in default** — domain-agnostic `DEFAULT_TAXONOMY` used only when both vault and override are empty (no catch-all bucket)
- [x] **Optional override file** — `X_BOOKMARKS_TAXONOMY_FILE` (env or `.envrc.local`): frontmatter `taxonomy:` merged (union) with vault categories, `deprecate:` list steers Claude away, Markdown body appended as prompt guidance
- [x] **Migration support** — `migrate.py --taxonomy-file` with independent resolution (no X API credentials required)

### v1.5 — Entity Tagging Layer
- [x] **Entity tags parsing** — `entity_tags` frontmatter key in override file, dict of prefix → list of known entities
- [x] **Gated tagging** — tags only appear when `entity_tags` is configured (non-empty); preserves zero-config UX when omitted
- [x] **Closed-prefix governance** — allowed prefixes are keys of `entity_tags` dict; unknown-prefix tags dropped, open entities (new discoveries) preserved
- [x] **Tags frontmatter array** — YAML flow array `tags: ["prefix/entity"]`, omitted when empty
- [x] **Lateral tagging in categorization** — Claude extracts tags alongside Category/Subcategory in both `categorizer.py` and `migrate.py`
- [x] **Migration backward compatibility** — existing tags preserved in migrated files when Claude returns no new tags

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
