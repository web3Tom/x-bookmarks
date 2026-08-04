# Proposed GitHub Issues

These issues were extracted from [`docs/roadmap.md`](x-bookmarks/docs/roadmap.md) and normalized into a standard tracking format.

## Issue: Add incremental bookmark fetch with since_id

### Summary

Store the latest fetched bookmark ID and stop pagination once older bookmarks are reached instead of always scanning the full fetch window.

### Why It Matters

This reduces API calls, runtime, and unnecessary downstream categorization work for normal repeat runs.

### Scope

- Persist the newest bookmark ID from a successful run
- Update fetch logic to stop once `since_id` is reached
- Document the behavior and fallback path for first-run or reset scenarios

### Acceptance Criteria

- [ ] Repeated runs fetch fewer pages when no new bookmarks exist
- [ ] The first run still performs a full fetch safely
- [ ] Tests cover both cold-start and incremental-fetch behavior

### Notes

Touches fetch behavior and run-state persistence. Coordinate with any future history or reporting changes.

### Labels

- `enhancement`
- `performance`

### Priority

`high`

## Issue: Expose bookmark cap as configuration

### Summary

Replace the hardcoded bookmark fetch cap with a CLI flag or environment variable so users can tune runtime and API usage.

### Why It Matters

A public tool should let different users trade off completeness, speed, and API consumption without editing source code.

### Scope

- Add a configurable bookmark cap
- Surface the setting in CLI or environment configuration
- Document the default and expected tradeoffs

### Acceptance Criteria

- [ ] Users can override the fetch cap without editing code
- [ ] The default behavior remains backward compatible
- [ ] Tests verify configured and default cap behavior

### Notes

Pairs naturally with incremental fetch but can ship independently.

### Labels

- `enhancement`
- `configuration`

### Priority

`medium`

## Issue: Add article extraction for external links

### Summary

Fetch and clean article content from bookmarked external URLs instead of relying only on X article content when available.

### Why It Matters

This increases note quality for article bookmarks and makes the knowledge base more useful when X provides limited content.

### Scope

- Detect supported external article links during bookmark processing
- Extract clean article content through a content-cleaning step
- Integrate the extracted content into note generation

### Acceptance Criteria

- [ ] External article bookmarks can include extracted body content
- [ ] Unsupported or failed extraction falls back gracefully
- [ ] Documentation explains the enrichment behavior and limitations

### Notes

May introduce new dependency or network behavior. Keep failure handling explicit.

### Labels

- `enhancement`
- `content`

### Priority

`high`

## Issue: Backfill missing external link titles via defuddle

### Summary

After the X API fetch, run `defuddle` against any `ExternalLink.expanded_url` where `title is None` to populate the missing title field before note generation.

### Why It Matters

The X API frequently returns `None` for `ExternalLink.title`. Empty titles reduce note readability and give Claude less signal during categorization. Defuddle can extract a clean page title from the resolved URL at low cost — no full article body fetch required.

### Scope

- After `api_client.py` builds `ExternalLink` objects, identify those with `title is None`
- Run `defuddle parse <expanded_url> -p title` for each missing title
- Backfill the result into the `ExternalLink` before passing to the categorizer and note renderer
- Fall back gracefully if the URL is unreachable or defuddle returns no title
- Make the enrichment step opt-in via env var or CLI flag (avoids unexpected network calls in offline/test runs)

### Acceptance Criteria

- [ ] `ExternalLink.title` is populated for supported URLs that the API left blank
- [ ] Failed or slow fetches do not block the main pipeline
- [ ] The enrichment step is skippable without code changes
- [ ] Tests cover the backfill path and the graceful fallback

### Notes

Complements `#3` (full article body extraction) but is intentionally lighter — title-only fetch. Can ship independently before `#3` is implemented. Requires `defuddle` to be installed and on PATH.

### Labels

- `enhancement`
- `content`

### Priority

`medium`

## Issue: Unroll X threads into single notes

### Summary

Detect thread bookmarks and stitch related posts into one coherent note instead of treating each post in isolation.

### Why It Matters

Many technical bookmarks are threads; preserving thread context improves note usefulness and downstream categorization quality.

### Scope

- Detect thread relationships
- Fetch or assemble related posts in order
- Render combined thread content cleanly in Markdown output

### Acceptance Criteria

- [ ] Thread bookmarks are represented as one coherent note
- [ ] Single-post bookmarks continue to work unchanged
- [ ] Tests cover thread detection and formatting

### Notes

Likely interacts with API expansion logic and markdown rendering.

### Labels

- `enhancement`
- `content`

### Priority

`medium`

## Issue: Expand quoted tweets inline

### Summary

Include quoted-post content inside the generated note for a bookmarked post when a quote tweet is present.

### Why It Matters

Quoted content often provides the context that makes a bookmark worth saving.

### Scope

- Detect quoted tweet relationships
- Fetch or parse quoted tweet content
- Render quoted content distinctly in the note body

### Acceptance Criteria

- [ ] Notes include quoted tweet context when available
- [ ] Missing quoted content does not break note generation
- [ ] Output formatting remains readable in Obsidian

### Notes

Related to richer tweet parsing and note formatting.

### Labels

- `enhancement`
- `content`

### Priority

`medium`

## Issue: Chunk large categorization batches

### Summary

Split large bookmark sets into smaller Claude requests instead of sending one large categorization payload.

### Why It Matters

This lowers the risk of malformed responses, token pressure, and failures on large bookmark collections.

### Scope

- Add batch chunking to categorization
- Merge chunked responses into one consistent result set
- Preserve token accounting and error reporting

### Acceptance Criteria

- [ ] Large runs are processed in deterministic chunks
- [ ] Existing small runs still use a simple path
- [ ] Tests cover chunk merging and partial-failure handling

### Notes

Should preserve current output semantics while improving reliability.

### Labels

- `enhancement`
- `reliability`

### Priority

`high`

## Issue: Generate Obsidian tags from categories

### Summary

Add tags derived from category or subcategory values to improve Obsidian navigation and filtering.

### Why It Matters

Tags make the generated vault more useful for browsing beyond Dataview tables.

### Scope

- Define tag-generation rules
- Add tags to generated note output
- Document the tagging scheme

### Acceptance Criteria

- [ ] Generated notes include stable, predictable tags
- [ ] Existing frontmatter remains valid
- [ ] Tag formatting is documented

### Notes

Keep the taxonomy-to-tag mapping simple and deterministic.

### Labels

- `enhancement`
- `obsidian`

### Priority

`medium`

## Issue: Add wikilinks between related notes

### Summary

Create Obsidian wikilinks between notes that share authors, categories, or closely related topics.

### Why It Matters

Cross-linking improves graph navigation and makes the output feel like a knowledge base instead of a flat export.

### Scope

- Define heuristics for related-note detection
- Add wikilinks during note generation or post-processing
- Avoid generating noisy or low-value links

### Acceptance Criteria

- [ ] Related notes include useful wikilinks
- [ ] Link generation avoids obvious spam or excessive linking
- [ ] Behavior is documented and test-covered

### Notes

May require scanning existing notes efficiently to avoid slow writes.

### Labels

- `enhancement`
- `obsidian`

### Priority

`low`

## Issue: Integrate daily note summaries

### Summary

Append a summary of newly saved bookmarks to an Obsidian daily note after each successful run.

### Why It Matters

This makes the tool more useful for active PKM workflows and daily review habits.

### Scope

- Define the daily note target and format
- Append a run summary with links to newly created notes
- Make the feature configurable

### Acceptance Criteria

- [ ] Successful runs can append a daily-note summary
- [ ] Users can disable or configure the feature
- [ ] Documentation explains expected daily note behavior

### Notes

Should remain optional to avoid imposing one vault structure on all users.

### Labels

- `enhancement`
- `obsidian`

### Priority

`low`

## Issue: Add CLI dry-run mode

### Summary

Provide a dry-run mode that fetches and categorizes bookmarks without writing files.

### Why It Matters

Dry-run support makes the tool safer to test, demo, and troubleshoot before users modify their vault.

### Scope

- Add a `--dry-run` execution path to the main CLI
- Show what would be written without touching disk
- Document dry-run output and limitations

### Acceptance Criteria

- [ ] Users can run the main pipeline without creating files
- [ ] Dry-run clearly reports projected outputs
- [ ] Tests verify no files are written in dry-run mode

### Notes

Useful for recruiters and evaluators who want to inspect behavior safely.

### Labels

- `enhancement`
- `cli`

### Priority

`high`

## Issue: Add verbose and quiet CLI modes

### Summary

Allow users to control command output verbosity for debugging and automation contexts.

### Why It Matters

Public CLI tools need both human-friendly debugging output and automation-friendly quiet mode.

### Scope

- Add verbosity flags
- Normalize logging/output paths
- Document expected output modes

### Acceptance Criteria

- [ ] Users can select verbose and quiet output modes
- [ ] Default output remains readable
- [ ] Tests cover flag parsing and output behavior

### Notes

This can share implementation work with broader CLI cleanup.

### Labels

- `enhancement`
- `cli`

### Priority

`medium`

## Issue: Generate periodic bookmark summary reports

### Summary

Create weekly or monthly digest reports summarizing saved bookmarks by category.

### Why It Matters

This adds a higher-level review layer on top of raw note generation and improves long-term usefulness.

### Scope

- Define report cadence and output format
- Aggregate bookmark history by time window and category
- Document how reports are generated and where they are stored

### Acceptance Criteria

- [ ] Users can generate periodic summary reports
- [ ] Reports use existing run or note data instead of duplicating state
- [ ] Output format is documented and tested

### Notes

Can likely build on existing run-history data.

### Labels

- `enhancement`
- `reporting`

### Priority

`low`

## Issue: Add scheduled run support

### Summary

Document and support automated periodic execution through cron, systemd, or a comparable scheduler.

### Why It Matters

Scheduled runs make the tool more useful as an always-on personal ingestion pipeline.

### Scope

- Define supported scheduling approaches
- Provide example automation setup
- Ensure the CLI behaves predictably in unattended mode

### Acceptance Criteria

- [ ] Users have documented examples for scheduled runs
- [ ] Scheduled execution works without interactive prompts after initial setup
- [ ] Failure behavior is documented for unattended runs

### Notes

Depends on stable auth refresh behavior and non-interactive execution paths.

### Labels

- `enhancement`
- `automation`

### Priority

`medium`

## Issue: Improve token persistence security

### Summary

Replace plaintext token storage in `.env` with a more secure persistence strategy.

### Why It Matters

Credential handling is one of the biggest trust issues for a public tool that uses OAuth tokens and API keys.

### Scope

- Evaluate secure storage options
- Design a migration path from existing `.env` storage
- Update auth and refresh flows to use the new storage mechanism

### Acceptance Criteria

- [ ] Access and refresh tokens are no longer stored in plaintext by default
- [ ] Existing users have a documented migration path
- [ ] Security tradeoffs are documented clearly

### Notes

This is a good candidate for a post-v1 public hardening milestone.

### Labels

- `security`
- `enhancement`

### Priority

`high`

## Issue: Add X API rate-limit backoff handling

### Summary

Respect X API rate-limit headers and back off automatically instead of failing abruptly under tighter limits.

### Why It Matters

A public integration tool needs predictable behavior under real-world API constraints.

### Scope

- Parse relevant X rate-limit signals
- Add retry/backoff behavior
- Surface rate-limit events clearly to users

### Acceptance Criteria

- [ ] The client backs off when rate limits are encountered
- [ ] Retries are bounded and visible in logs
- [ ] Tests cover rate-limit handling behavior

### Notes

This improves reliability for both manual and scheduled runs.

### Labels

- `enhancement`
- `reliability`

### Priority

`high`

## Issue: Zero-cost bookmark retrieval path

### Summary

Remove the paid X API tier from the critical path and lift the per-run fetch ceiling, without making the user's personal X account the credential of record. This issue is scoped to a **goal**, not a mechanism: candidate approaches are evaluated against cost, ToS posture, and credential blast radius before one is selected.

### Why It Matters

Bookmark reads on the official X API v2 effectively require a paid tier, and runs are bounded by an observed ceiling of roughly 300 bookmarks per invocation (the 2026-08-03 run fetched 199). Cost is recurring and the ceiling blocks any full backfill of an established bookmark history. Both constraints are structural — no amount of tuning inside the current mechanism removes them.

### Scope

- Define the acceptance bar before choosing a mechanism: no recurring API cost, no full-account credential, no unbounded maintenance tax
- Evaluate candidate mechanisms against that bar and record findings in `docs/feasibility-*.md`
- Keep OAuth 2.0 PKCE as the default and only documented path until a candidate clears the bar
- If a candidate is adopted, gate it behind an explicit opt-in env flag; never silent, never default
- Add any new credential names to the pre-commit secret-scan denylist

### Acceptance Criteria

- [ ] Acceptance bar is written down and each candidate is scored against it
- [ ] A decision is recorded — adopt, reject, or defer — with the rationale
- [ ] The OAuth path remains functional and default regardless of outcome
- [ ] If adopted: the alternate path is opt-in, documented as to its risk posture, and covered by tests
- [ ] If adopted: no credential is written to a tracked file, and secret-scan rules cover the new names

### Notes

Depends on `#14` — any non-OAuth mechanism introduces a second credential with a larger blast radius than the current scoped tokens, and plaintext `.env` storage is unacceptable for it.

Partially subsumes `#1` and `#2`: a mechanism without the official pagination ceiling changes what `since_id` and `_MAX_BOOKMARKS` are for. Do not implement all three in parallel.

Prior analysis in `docs/feasibility-graphql-vs-x-api.md` assessed cookie/GraphQL session replay and recommended **against** it as a primary path, on account-ban risk and credential blast radius. That recommendation stands until superseded. Further candidate assessments: `docs/feasibility-agent-reach.md`, `docs/feasibility-x-research-skill.md`.

### Labels

- `enhancement`
- `reliability`
- `needs-decision`

### Priority

`high`

## Issue: Opt-in unofficial backfill via twitter-cli (hybrid)

### Summary

Add a read-only, double-gated backfill path that fetches bookmarks through `public-clis/twitter-cli` instead of the official X API, to recover bookmark history beyond the official endpoint's observed ~300-per-run ceiling. The official OAuth path remains the default for all routine syncs, and deletion remains on the official API permanently.

### Why It Matters

`#17` established that a free, fully capable mechanism exists but fails the account-risk bar. Rather than adopt it wholesale or reject it outright, this splits the problem by job:

- The **fetch ceiling** is a one-time problem. A single manual backfill recovers the history that the official endpoint will not paginate to.
- The **API cost** is recurring but small, since incremental syncs fetch few new items and stay comfortably inside the official tier.

A single interactive backfill presents a far smaller detection surface than a recurring automated job, which is the traffic pattern anti-bot systems are built to identify. This captures most of the value of `#17` at a fraction of the exposure.

### Scope

- `src/unofficial_client.py`: adapt `twitter bookmarks --json` output into the existing `Tweet` model
- Two independent gates: `X_BOOKMARKS_UNOFFICIAL=1` **and** explicitly supplied `TWITTER_AUTH_TOKEN` / `TWITTER_CT0`
- `--backfill-unofficial` and `--backfill-max N` CLI flags; refuse to combine with `--remove-synthesized-bookmarks`
- Credentials passed via child process environment only, never argv
- Fail loudly on any error; never fall back to or from the official path silently

### Acceptance Criteria

- [x] Default runs are byte-for-byte unchanged; the path is unreachable without the flag
- [x] Invocation is refused when either credential is absent, before any subprocess spawns
- [x] `--backfill-unofficial` cannot be combined with `--remove-synthesized-bookmarks`
- [x] Credentials never appear in argv
- [x] Adapter maps metrics to official API key names, synthesizes unique media keys, and emits timezone-aware timestamps
- [x] A malformed entry is skipped rather than aborting the whole backfill
- [x] Missing `twitter-cli` reports the install command
- [x] Tests cover both gates, the adapter, and every error path

### Notes

The credential requirement is a safety mechanism, not ergonomics: when `TWITTER_AUTH_TOKEN`/`TWITTER_CT0` are absent, upstream `twitter-cli` scans Chrome/Edge cookie jars to find them. Refusing to invoke it without both variables is what prevents that unconsented scan. This mirrors the "Cookie-Editor-only policy" documented in `docs/feasibility-agent-reach.md` §5.2.

This path violates the X Developer Agreement and can get the account flagged. It is documented as such in `--help`, in the runtime banner, and in `README.md`. It is intended to be run once, manually, and then left off.

Depends on `#14` for credential storage hardening if this ever becomes routine rather than one-time.

### Labels

- `enhancement`
- `reliability`
- `opt-in`

### Priority

`medium`
