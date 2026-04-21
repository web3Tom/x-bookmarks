# Repository Instructions

## Purpose

This repository contains `x-bookmarks`, a Python CLI that fetches `x.com` bookmarks, categorizes them with Claude, and writes them as Obsidian-friendly Markdown notes.

Public repository URL:

- `https://github.com/web3Tom/x-bookmarks`

Primary goals:

- keep the CLI reliable and easy to set up
- keep public docs accurate and safe to publish
- preserve the Markdown/frontmatter contract used by generated notes
- avoid committing secrets, local caches, or machine-specific artifacts

## Repository Layout

- `src/`: application code
- `tests/`: test suite
- `docs/`: public project documentation, roadmap, and issue planning
- `README.md`: public onboarding
- `.env.example`: safe configuration template

## Skills To Use

When available in this environment:

- `obsidian-markdown`
  - Use for `.md` cleanup, heading normalization, and Markdown structure work.
- `defuddle`
  - Use when a roadmap item or feature work involves extracting article content from URLs.
- `obsidian-cli`
  - Use only when work explicitly involves Obsidian vault automation or integration testing.

Use `obsidian-markdown` by default for Markdown files in this repository.

## Configuration And Security Rules

- Never commit `.env`, access tokens, refresh tokens, API keys, or copied terminal output containing secrets.
- Treat `.env.example` as the only publishable env file.
- Before finishing, review `git diff --staged` or `git status` for accidental local-only changes.
- Keep default paths portable; avoid author-specific home-directory assumptions in public docs or code unless clearly justified.

## Generated Markdown Contract

Generated bookmark notes must continue to follow this frontmatter schema:

```yaml
---
title: "..."
author: "@handle"
category: "..."
subCategory: "..."
date: 2026-02-25
read: false
type: "post" # or "article"
tweet_url: "https://x.com/..."
article_url: "https://..." # optional — articles only
---
```

Rules:

- all string fields must be double-quoted
- `subCategory` must remain camelCase
- deprecated fields must not be reintroduced
- the first `##` heading in generated note bodies must match the frontmatter title exactly
- use `## References` for outbound links

## Documentation Expectations

- Keep [`README.md`](README.md) aligned with the real setup flow.
- Keep [`docs/overview.md`](docs/overview.md) aligned with current architecture and behavior.
- Keep [`docs/roadmap.md`](docs/roadmap.md) as the planning source unless replaced intentionally.
- Keep [`docs/github-issues.md`](docs/github-issues.md) in sync when roadmap items are re-scoped materially.

## Roadmap & Change-Log Conventions

### Roadmap Structure

- Planned work in [`docs/roadmap.md`](docs/roadmap.md) is organized into five priority tiers (Safety & Efficiency Foundations → Reliability → Content Quality → UX & Automation → Polish).
- Each Planned item is prefixed with its GitHub issue reference in `[#NN]` form, keyed to [`docs/github-issues.md`](docs/github-issues.md) and the live issue tracker at `https://github.com/web3Tom/x-bookmarks/issues`.
- When re-ordering, update tier assignment and keep the Priority Rationale and Dependency Notes blocks in sync.
- Do not revert to topic-based subheadings (Fetch Efficiency, Content Enrichment, etc.) — tiers convey execution order, which topic groupings did not.

### Change-Log Conventions

- [`docs/CHANGELOG.md`](docs/CHANGELOG.md) is the in-repo session log. Append a dated entry for every work session that produces a meaningful outcome (feature work, pipeline runs, roadmap changes, protocol updates).
- Keep entries short, outcome-focused, and reverse-chronological (newest entry at top).
- Long-form reasoning, open questions, and cross-session context belong in the author's external spec system — not in this repo.

## GitHub Workflow

Repository:

- `https://github.com/web3Tom/x-bookmarks`

### Push Changes

Use this when local changes are ready to publish:

```bash
git status
git add .
git commit -m "<clear summary>"
git push origin main
```

Before pushing:

- verify no secrets are staged
- verify tests pass
- verify generated docs still reflect the current implementation

### Create Issues

Canonical source for issue creation:

- [`docs/github-issues.md`](docs/github-issues.md)
- [`docs/roadmap.md`](docs/roadmap.md)

If GitHub API workflow is available:

- create issues from `docs/github-issues.md`
- avoid duplicating existing issue titles
- preserve the issue title and body structure unless there is a clear repo-specific reason to change it

### Pull Down Issues

If a local issue-sync workflow is established later, use it to refresh planning docs from GitHub before editing roadmap-derived work. Until then:

- treat GitHub Issues as the live execution backlog
- treat `docs/roadmap.md` as the higher-level planning document
- manually reconcile issue status back into docs when major planning changes are made

## Fetch, Pagination, And Deduplication

### X API Behavior

- The bookmarks endpoint (`GET /2/users/{user_id}/bookmarks`) returns bookmarks **newest-first**.
- Each page returns up to 100 results (`max_results=100`).
- The API supports pagination via `next_token` in the response metadata.
- **Known API limitation:** pagination often stops after approximately 3 pages (~300 bookmarks) even when the user has more. The API stops returning `next_token` prematurely. This is a documented X API bug, not a code issue.
- Bookmarks require at least the Basic tier ($100/month). The Free tier has no bookmark access.

### Fetch Logic (`src/api_client.py`)

- `fetch_bookmarks` loops requesting pages of 100 until either:
  - 800 total tweets are collected (`_MAX_BOOKMARKS`), or
  - the API returns no `next_token` (no more pages available)
- On `401`, the client refreshes the OAuth token automatically and retries the request.
- **No dedup logic exists during fetching.** The fetch loop has no awareness of which bookmarks are already saved locally.

### Deduplication (`src/main.py` and `src/markdown_writer.py`)

Dedup happens in two passes, both **after** all fetching completes:

1. **Pre-categorization** (`main.py` lines 107-124): `read_existing_ids` scans all `*.md` files in the output directory, extracts tweet IDs from `tweet_url` frontmatter fields, and filters the fetched list. Only novel tweets (IDs not on disk) proceed to categorization. If zero novel tweets remain, the run exits with `noop` status.
2. **At write time** (`markdown_writer.py` lines 164-178): a defensive second check skips any tweet ID that appeared on disk between the pre-categorization check and file writing.

### Practical Implications

- Each run fetches whatever the X API returns (typically 1-3 pages) and then deduplicates against disk.
- There is **no early-stop optimization** that skips remaining pages when duplicates are found during fetching.
- Because the API returns newest-first and often caps at ~300 bookmarks, the tool works best when run regularly so new bookmarks stay within the retrievable window.

## Validation Checklist

Before finishing:

- no secrets or local-only files are staged
- tests pass for code changes
- docs reflect the current behavior
- no stale personal paths or private URLs were introduced
- generated note schema expectations remain intact
