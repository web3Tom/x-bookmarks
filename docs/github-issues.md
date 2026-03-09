# Proposed GitHub Issues

These issues were extracted from [`docs/roadmap.md`](/home/tom/Documents/projects/workspace/x-bookmarks/docs/roadmap.md) and normalized into a standard tracking format.

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
