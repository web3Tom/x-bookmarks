# x-bookmarks Changelog

Reverse-chronological log of session-level outcomes for this repository.
Newest entry at the top. Long-form reasoning lives in the author's external spec system, not here.

## 2026-06-03

**Deterministic mechanics alias collapse**

- Added an optional `aliases:` map (`retired-slug: canonical-slug`) to the taxonomy override. Synonyms emitted by Claude are rewritten to their canonical form and de-duplicated in `normalize_mechanics`, after the response — independent of model behavior.
- Threaded the alias map through both emission paths (`categorize_tweets` sync writer and `migrate` re-processing) so re-processed notes also adopt canonical slugs.
- Hardened the categorizer prompt: cap mechanics at 1–4, instruct against stacking near-synonyms / facets of one idea, and pick the most specific applicable terms.
- Documented `aliases:` in `docs/taxonomy.md` and `taxonomy.example.md`. Added tests for alias parsing, type-guarding, collapse + dedup, and end-to-end threading.

## 2026-06-02

**Faceted taxonomy schema**

- Replaced `category`/`subCategory` hierarchical taxonomy with a faceted schema: `pillar` (scalar, strategic mode) + `mechanics` (list, techniques/concepts) + `entity_tags` (nested dict, tools/frameworks/models).
- Dropped the `provider` and `concept` entity tag prefixes; concept values migrated into mechanics.
- Updated `taxonomy.example.md` to the new override format (pillars, mechanics, entity_tags, deprecate, guidance) with domain-neutral examples and worked scenarios.
- Rewrote `docs/taxonomy.md` with comprehensive coverage of the faceted model, union-merge semantics, all four entity tag prefixes (framework, harness, model, tool), and common patterns.
- Updated `README.md`, `AGENTS.md`, and `docs/overview.md` frontmatter schema examples and categorization descriptions.
- Tests: all 418 passing; schema refactoring already complete from prior sessions.

## 2026-05-24

**Taxonomy example populated from production vault**

- Replaced the placeholder draft in `taxonomy.example.md` with the maintainer's real, in-production AI/engineering taxonomy: 7 domains (Agentic Systems, Development & Tooling, Models & Inference, Strategy & Ontology, Execution & Career, Security & Privacy, Society & Commentary) and 43 empirically-derived subcategories — the same scheme used to reshape a ~615-note bookmark vault.
- Seeded `entity_tags` for all six prefixes from actual vault usage (e.g. `tool/claude-code`, `harness/hermes`, `concept/multi-agent`); expanded `deprecate:` to cover the legacy ad-hoc categories the new scheme replaced.
- Added worked examples + disambiguation rules (harness vs framework vs coding-agent; agent-memory vs human-PKM; inference-substrate vs model) to the example's guidance body.
- Refreshed `docs/taxonomy.md` illustrative examples to current category names (dropped now-deprecated `AI Coding`/`Agent Architectures`) and linked the example file from the overview. `DEFAULT_TAXONOMY` stays domain-neutral.

**Configurable taxonomy overrides**

- Added `src/taxonomy.py` centralizing taxonomy logic; removed the duplicated `_build_taxonomy_block` from `src/categorizer.py` and `src/migrate.py`.
- Added a neutral, domain-agnostic `DEFAULT_TAXONOMY` (7 top-level categories, no catch-all bucket) used only when both the vault and any override are empty.
- Added an optional override file via `X_BOOKMARKS_TAXONOMY_FILE` (resolved from env or `.envrc.local`): frontmatter `taxonomy:` is merged (union) with vault categories, `deprecate:` steers Claude away from unwanted categories, and the Markdown body is appended to the system prompt as domain guidance.
- Added `migrate.py --taxonomy-file` and independent taxonomy-file resolution so bulk re-categorization works without X API credentials.
- Tightened cold-start prompt rules and switched cold-start examples to domain-neutral placeholders.
- Added `docs/taxonomy.md`, `taxonomy.example.md` (neutral template with commented AI/eng example), and updated README, `.env.example`, AGENTS.md, and roadmap; reconciled the stale v1.2 "fixed 10-category taxonomy" claim.
- Tests: new `tests/test_taxonomy.py` plus extended categorizer/migrate/config suites; full suite 296 passing at ~89% coverage.

**Entity tagging layer**

- Added lateral entity tagging: `tags: tuple[str, ...]` field to `CategorizedTweet` and frontmatter YAML flow array.
- Added `TaxonomyOverride` dataclass unifying taxonomy, entity_tags, deprecations, and guidance loading; single-read parse with type-guards for all fields.
- Entity tags gated on `entity_tags` config: when absent/empty, no tags are requested in Claude prompt and `tags:` frontmatter is omitted. Preserves zero-config UX.
- Closed-prefix/open-entity governance: allowed prefixes are keys of configured `entity_tags` dict; Claude can invent new entities under known prefixes but unknown-prefix tags are dropped.
- Added `normalize_tag()` and `normalize_tags()`: slugify entity names (spaces/underscores → dashes, drop invalid chars), deduplicate preserving first-seen order, validate against allowed prefixes.
- Added `build_entity_tags_section()` for sorted reference block in system prompts.
- Threaded entity_tags through both `categorizer.py` and `migrate.py` system prompts with verbatim instruction when non-empty.
- Updated `markdown_writer.py._build_frontmatter()` and `migrate.py._build_migrated_frontmatter()` to emit tags as YAML flow arrays, omit when empty.
- Existing tags in migration files are preserved when Claude returns no tags (maintains backward compatibility).
- Tests: 72 new tests for tag normalization, entity_tags parsing, TaxonomyOverride; full suite 339 passing at 88% coverage.
- Updated `taxonomy.example.md` to maintainer's AI ontology with 6 entity tag prefixes (framework, harness, model, provider, tool, concept).
- Added "Entity tags" section to `docs/taxonomy.md` with format, gating rules, and closed-prefix/open-entity governance.

## 2026-05-13

**Synthesized bookmark removal**

- Added `--remove-synthesized-bookmarks` mode with `--dry-run`, `--confirm`, interactive confirmation, and `--max` capped at 50 live deletions.
- Added strict `synthesized` handling: generated notes now use `synthesized: false`; removal is eligible only for exact `synthesized: true`; backfill covers active notes before removal scans.
- Added X bookmark DELETE support with 401 refresh retry, 403 `bookmark.write` guidance, 404 idempotent success, and 429 reset reporting.
- Successful or already-absent removals now add `bookmark_removed` metadata, archive notes under `output_dir / "archive"`, and append removal-mode records to `.x-bookmarks-history.jsonl`.
- Updated README, overview, roadmap, PRD, repo instructions, and vault template/Base/feed docs for the removal workflow.

**Output directory persistence**

- `x-bookmarks-auth` now preserves local output configuration when it rewrites `.env` after OAuth, preventing `KNOWLEDGE_BASE_DIR` from being dropped during re-authentication.
- `src/config.py` now accepts `KNOWLEDGE_DIR` as a compatibility fallback while keeping `KNOWLEDGE_BASE_DIR` canonical.
- `src/config.py` also reads simple `KNOWLEDGE_BASE_DIR` / `KNOWLEDGE_DIR` assignments from ignored `.envrc.local`, so `uv run x-bookmarks` does not depend on direnv having exported the variable.
- `src/main.py` now logs the resolved output directory before fetching bookmarks to make configuration mistakes visible before categorization.
- Updated README and overview docs to explain one-time output directory setup and the privacy expectation for machine-specific paths.

## 2026-05-11

**`pass` vault fallback for `ANTHROPIC_API_KEY`**

- `src/config.py` now resolves `ANTHROPIC_API_KEY` from the user's `pass` store at `ai/anthropic/api-key` when the environment variable is unset or empty after `load_dotenv`.
- Fallback is gated on `pass` being on `PATH`; missing binary or missing entry returns an empty string and lets the existing "missing required env vars" error fire normally.
- Closes the gap where a `.env` (or `.envrc.local`) with an empty `ANTHROPIC_API_KEY=` would override a shell-exported value loaded via direnv.

**Pipeline log clarity**

- `src/main.py` article-count line now reports `{articles} of {novel} new bookmark(s) link to articles ({with_content} with content from API)` instead of the prior `Found {articles} article(s)` phrasing. Makes the article-vs-bookmark ratio explicit in run logs.

## 2026-05-09

**Transition to Secure Secret Management**

- Migrated from hardcoded `.env` to a `direnv` + `pass` workflow.
- Implemented a "smart" `.envrc` that supports `.envrc.local` for private, secure overrides.
- Updated `.gitignore` to protect `.envrc.local`.
- Updated `AGENTS.md` to codify the new Secret Management standards.
- Removed hardcoded API keys from local `.env`.

## 2026-04-21

**Roadmap restructure and protocol adoption**

- Reorganized `docs/roadmap.md` Planned section into five priority tiers. Order: `#14 → #10 → #1` (Tier 1) → `#15 → #6 → #2` (Tier 2) → `#3 → #4 → #5` (Tier 3) → `#11 → #7 → #13` (Tier 4) → `#8 → #9 → #12` (Tier 5). Rationale captured in the roadmap's Priority Rationale block.
- Validated backlog: all 15 planned items are live as open GitHub issues `#1`–`#15` on `web3Tom/x-bookmarks`; no drift between docs and tracker.
- Adopted `docs/CHANGELOG.md` (this file) and added a Roadmap & Change-Log Conventions section to `AGENTS.md`.
- Confirmed `main` in sync with `origin/main`.

**Pipeline run (`6b296cf26734`)**

- Fetched 99 bookmarks in one page (X API pagination bug capped return).
- 58 already saved, 41 new notes written in 46.6s.
- Claude token usage: 19,782 in / 2,366 out, single call.
- No 401 token refresh triggered; `.env` credentials still valid.

**Public/private audit**

- Untracked `docs/public-release-plan.md` and `docs/public-release-audit.md` (kept local). Internal planning artifacts; not intended for public consumption.
- Added a Pre-Commit Privacy Review directive in `AGENTS.md` requiring a public/private check of every staged file before commit, with an explicit untrack recipe.
- Pruned broken Project Docs links from `README.md` and added a pointer to `docs/CHANGELOG.md`.
- Caveat: past commits on the public GitHub repo still contain the now-untracked files. Decision: **accept the historical leak** — content is internal planning, not secrets; no history rewrite or force-push. Going forward, `.gitignore` + the pre-commit privacy directive prevent recurrence.
