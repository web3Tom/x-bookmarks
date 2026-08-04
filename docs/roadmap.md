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

### v1.6 — Hybrid Free Retrieval

> **Superseded by v1.7.** The gates and flags described below (`X_BOOKMARKS_UNOFFICIAL`, `--backfill-unofficial`, `--backfill-max`) no longer exist; `twitter-cli` became the default rather than an opt-in backfill. Retained for the decision trail. `#16` is unaffected and still current.

- [x] **[#18] Opt-in unofficial backfill** — `src/unofficial_client.py` adapts `twitter bookmarks --json` into the existing `Tweet` model behind two independent gates (`X_BOOKMARKS_UNOFFICIAL=1` **and** explicit `TWITTER_AUTH_TOKEN`/`TWITTER_CT0`). Read-only, `--backfill-unofficial` / `--backfill-max`, refused in combination with `--remove-synthesized-bookmarks`, credentials passed via child env never argv, fails loudly with no silent fallback in either direction
- [x] **[#16] External link title backfill** — implemented in `src/enrichment.py` via **Jina Reader** (`https://r.jina.ai/{url}`) rather than the originally-planned `defuddle`. Opt-in with `--enrich-titles`, applied after deduplication so only new bookmarks are enriched, results cached per URL, failures degrade to `title: None` without aborting the run

#### Why Jina Reader instead of `defuddle` for `#16`

`#16` was originally scoped around `defuddle`, which requires the binary on `PATH`. Jina Reader is a keyless unauthenticated `GET` with no local dependency, discovered while assessing Agent-Reach (see [`feasibility-agent-reach.md`](feasibility-agent-reach.md) §5.1). It removes the install precondition entirely and carries no credential.

The trade-off, recorded rather than averaged away: Jina discloses every enriched URL to a third party, whereas `defuddle` fetches locally. That is why enrichment is opt-in rather than automatic. `#3` (full article body extraction) remains open and should reuse whichever mechanism `#16` settles on in practice.

This pairing is not incidental. The unofficial path emits bare URL strings with no title metadata at all, so **every** `ExternalLink.title` starts as `None` there, versus only some on the official path. `#18` makes `#16` substantially more valuable.

### v1.7 — Full Free Replacement
- [x] **[#19] `twitter-cli` as the default mechanism** — reads **and** removals now go through `twitter-cli` by default. `--official` selects the OAuth path for both. The X developer platform is no longer required to run the tool at all
- [x] **Optional OAuth configuration** — `CLIENT_ID`/`ACCESS_TOKEN`/`REFRESH_TOKEN`/`USER_ID` dropped from `config._REQUIRED`; only `ANTHROPIC_API_KEY` remains mandatory. `Config.has_official_credentials` gates `--official` and fails at startup rather than mid-run
- [x] **Unofficial deletion** — `delete_bookmark_unofficial` via `twitter unbookmark`, injected through the existing `remove_candidates(delete_bookmark=...)` seam so eligibility, archiving, and the 50-per-run cap are untouched
- [x] **Consent flag removed** — `X_BOOKMARKS_UNOFFICIAL` deleted. It was a consent gate on an opt-in path; gating the only default path would just mean the tool never runs. The **credential requirement stays**, because that is the mechanism preventing `twitter-cli` from scanning browser cookie jars

#### Accepted trade-offs

Recorded rather than glossed, since these are now the tool's normal operating conditions:

| Property | Before | After |
|---|---|---|
| Cost | Paid tier | **Free** |
| Fetch ceiling | ~300/run | Cursor-paginated |
| Credential | OAuth, `bookmark.*` scoped, revocable | `auth_token`, ≈ full account access |
| Sanctioned | Yes | **No** — violates the Developer Agreement |
| Exposure | One-time backfill (v1.6 hybrid) | **Every sync, including deletes** |
| Delete semantics | Documented 404 = already absent | Inferred from a narrow stderr allowlist |

The delete-semantics regression is the sharpest edge. Anything not positively matched as "already absent" raises rather than reporting success, because a false success would archive the note while the bookmark still exists on X. Use `--official` for removal when that distinction matters.

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
- [ ] **[#3] Article extraction for external links** — fetch and clean article body for non-X URLs. Originally scoped to `defuddle`; reconsider against Jina Reader, which `#16` now uses in production (see v1.6)
- [ ] **[#4] Thread unrolling** — detect tweet threads and stitch related posts into a single coherent note
- [ ] **[#5] Quote tweet expansion** — inline quoted tweet content into the parent note

> `#16` moved to **Completed (v1.6)**, implemented via Jina Reader rather than `defuddle`. See the v1.6 section for the mechanism rationale and its trade-off.

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
- `#17` **requires `#14`** — any non-OAuth path introduces a second, higher-blast-radius credential; storing it in plaintext `.env` is unacceptable, so token hardening must land first
- `#17` partially subsumes `#1` and `#2` — a mechanism without the official pagination ceiling changes what `since_id` and `_MAX_BOOKMARKS` are for; do not implement all three in parallel

### Priority Rationale
- **Why `#14` first:** public-release audit flags plaintext token storage as the highest remaining risk.
- **Why `#10` second:** tiny effort, but makes every later content feature safer to iterate on and demo.
- **Why `#1` third:** today's run showed 58 of 99 fetched bookmarks were already on disk — `since_id` would avoid fetching them in the first place.
- **Alternate ordering:** if use is single-user and local-only, promote `#3` (article extraction) above `#14` — bigger day-to-day quality win at the cost of leaving token handling untouched.
- **Why `#17` sits in Tier 2, not Tier 1:** cost and the fetch ceiling are live, recurring constraints — the 2026-08-03 run fetched 199 bookmarks against an observed ~300/run ceiling — so it outranks content polish. It is deliberately *not* Tier 1 because the leading candidate mechanism (cookie/GraphQL session replay) inverts the roadmap's safety-first ordering: it would introduce full-account session cookies while `#14` still leaves tokens in plaintext. Sequencing `#14` before `#17` resolves that inversion rather than averaging it away.
- **`#17` is goal-scoped, not means-scoped.** The roadmap commits to removing the paid tier from the critical path; it does **not** commit to cookie/GraphQL as the mechanism. `feasibility-graphql-vs-x-api.md` recommends against that mechanism as the primary path, and that recommendation stands until a candidate clears the cost / ToS / blast-radius bar.

#### `#17` candidate log

| Date | Candidate | Verdict | Reason |
|------|-----------|---------|--------|
| 2026-06-12 | Cookie/GraphQL via vendored `bird` | Rejected as primary | Account-ban risk; `auth_token` ≈ full-account blast radius. Opt-in fallback only, if ever |
| 2026-08-03 | [`Panniantong/Agent-Reach`](feasibility-agent-reach.md) | Not the right unit | Contains no bookmark code itself; it is an installer/router. Assessment redirected to its X delegate, below |
| 2026-08-03 | [`public-clis/twitter-cli`](feasibility-agent-reach.md) (Agent-Reach's delegate) | **Rejected on risk, not capability** | **Clears the capability bar outright** — free, Apache-2.0, Python, reads own bookmarks + folders + create/delete, cursor-paginated, dynamic queryIds. Declined because it ships an explicit anti-detection stack: TLS fingerprint impersonation, `x-client-transaction-id` forgery, timing jitter documented as evading pattern detection, and full browser-cookie forwarding |
| 2026-08-03 | [`rohunvora/x-research-skill`](feasibility-x-research-skill.md) | Rejected | Wrapper over the **paid** official API (~$0.50/search) — wrong cost direction; bookmarks command was added and reverted 116s later, absent at `HEAD` |

**Status: RESOLVED 2026-08-04 by `#19` (v1.7).**

`#17` asked to remove the paid tier from the critical path without making the personal account the credential of record. It was resolved by accepting the second half of that trade rather than satisfying it: `twitter-cli` is now the default for reads and deletes, the X developer platform is gone, and `auth_token` **is** the credential of record.

The decision was made explicitly by the maintainer with the risk documented (see `Accepted trade-offs` under v1.7). The candidate log below is retained as the evidence trail for *why* no lower-risk option was adopted: none existed. `--official` remains available as an escape hatch, since the chosen mechanism is known to be brittle against X front-end builds.

`#17` was deliberately written goal-scoped so a safer third mechanism could be adopted if one existed. The 2026-08-03 sweep establishes that none does:

- The **free** mechanisms are fully capable and all converge on the same cookie/GraphQL substrate, now with active anti-detection.
- The **sanctioned** mechanisms cost money.

A capable free mechanism therefore exists today and could be integrated in days. The blocker is not engineering and not discovery — it is whether driving the user's real, named X account through a tool engineered to evade platform detection is an acceptable trade for removing API cost. **That is a user decision, and until it is made `#17` should not be picked up.** If the answer is ever yes, `feasibility-agent-reach.md` §5.2 and §5.4 define the required shape: explicit paste-in credentials only, never a browser-jar scan, opt-in behind a flag, OAuth remaining default.
