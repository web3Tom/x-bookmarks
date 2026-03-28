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

### Fetch Efficiency
- [ ] **Incremental fetch with since_id** — store the most recent tweet_id from last run, use it as a floor to stop pagination early instead of always fetching 800
- [ ] **Configurable bookmark cap** — expose `_MAX_BOOKMARKS` (currently hardcoded to 800) as a CLI flag or env var

### Content Enrichment
- [ ] **Article extraction via Defuddle** — for bookmarks linking to external URLs, fetch and extract clean article content using the `defuddle` skill instead of relying solely on X API article content
- [ ] **Thread unrolling** — detect tweet threads and stitch them into a single note
- [ ] **Quote tweet expansion** — inline quoted tweet content into the parent note

### Categorization
- [ ] **Batch chunking** — split large bookmark sets into smaller Claude batches to reduce risk of malformed responses on 500+ tweet payloads

### Output & Obsidian Integration
- [ ] **Obsidian tags** — generate `#tags` from category slugs for Obsidian tag-based navigation
- [ ] **Wikilinks to related notes** — cross-link bookmarks that share authors or categories
- [ ] **Daily note integration** — append a summary of newly saved bookmarks to the daily note

### CLI & UX
- [ ] **Dry-run mode** — `--dry-run` flag that fetches and categorizes but writes nothing, showing what would be saved
- [ ] **Verbose/quiet modes** — control output verbosity
- [ ] **Summary report** — generate a periodic digest (weekly/monthly) of saved bookmarks by category

### Infrastructure
- [ ] **Scheduled runs** — cron/systemd timer for automated periodic fetching
- [ ] **Token persistence improvements** — encrypted token storage instead of plaintext `.env`
- [ ] **Rate limit handling** — respect X API rate limit headers with backoff
