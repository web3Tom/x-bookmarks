# x-bookmarks Overview

## Purpose

`x-bookmarks` is a Python CLI that fetches your `x.com` bookmarks, categorizes them with Claude, and writes them as Obsidian-friendly Markdown notes. The output is designed for a personal knowledge base, especially AI-focused research and workflow capture.

Project URL:

- `https://github.com/web3Tom/x-bookmarks`

## Repository Workflow

- push code and doc changes through `main`
- track planned work in GitHub Issues
- use [`docs/roadmap.md`](x-bookmarks/docs/roadmap.md) for higher-level planning
- use [`docs/github-issues.md`](x-bookmarks/docs/github-issues.md) as the issue-seeding document

## Output Model

| Setting            | Value                               |
| ------------------ | ----------------------------------- |
| Env var            | `KNOWLEDGE_BASE_DIR`                |
| Fallback env var   | `KNOWLEDGE_DIR`                     |
| Default            | `~/x-bookmarks-data`               |
| Filename format    | `{title-slug}.md`                   |
| Collision handling | Numeric suffixes such as `-2`, `-3` |

`KNOWLEDGE_BASE_DIR` is the exact directory where notes are written. No subdirectory is appended.
`KNOWLEDGE_DIR` is accepted as a compatibility fallback, but `KNOWLEDGE_BASE_DIR` remains the canonical public setting.
If neither variable is exported in the process environment, the CLI also reads simple assignments from ignored `.envrc.local`.

## Core Flow

1. Authenticate with X via OAuth 2.0 PKCE.
2. Load credentials and local config from `.env`.
3. Fetch bookmarks from the X API.
4. Skip bookmarks that already exist in the target directory.
5. Ask Claude to generate a title plus `category` and `sub_category`.
6. Write one Markdown note per bookmark.
7. Append structured run metadata to `.x-bookmarks-history.jsonl`.

Removal mode is separate from this flow. `uv run x-bookmarks --remove-synthesized-bookmarks` scans existing active notes, removes eligible X bookmarks, annotates successful removals, and archives the notes without fetching bookmarks or calling Claude.

## Main Components

### Authentication

[`src/auth_helper.py`](x-bookmarks/src/auth_helper.py) opens a browser-based OAuth flow, exchanges the code for tokens, fetches the authenticated user ID, and writes credentials to `.env`.
The OAuth scope list includes `bookmark.write` for explicit removal mode. Users who authenticated before that scope was added must re-run `uv run x-bookmarks-auth`; refresh tokens cannot upgrade scope in place.
When rewriting `.env`, it preserves local non-token config for `ANTHROPIC_API_KEY` and `KNOWLEDGE_BASE_DIR`; if only `KNOWLEDGE_DIR` is present, it writes that value back as `KNOWLEDGE_BASE_DIR`.

### Configuration

[`src/config.py`](x-bookmarks/src/config.py) loads `CLIENT_ID`, `ACCESS_TOKEN`, `REFRESH_TOKEN`, `USER_ID`, `ANTHROPIC_API_KEY`, and the optional `KNOWLEDGE_BASE_DIR`.
For output directory resolution, exported `KNOWLEDGE_BASE_DIR` takes precedence over exported `KNOWLEDGE_DIR`, then local `.envrc.local` entries are checked in the same order; if none are set, the default is `~/x-bookmarks-data`.

### Bookmark Fetching

[`src/api_client.py`](x-bookmarks/src/api_client.py) fetches bookmarks from `GET /2/users/{user_id}/bookmarks` with the following behavior:

- Requests up to 100 bookmarks per page (`max_results=100`).
- Paginates via `next_token` until either 800 total bookmarks are collected or the API returns no more pages.
- Refreshes the OAuth access token automatically on `401`.
- The X API returns bookmarks newest-first and has a known pagination bug where `next_token` stops being returned after approximately 3 pages (~300 bookmarks), even when the user has more.

### Deduplication

Dedup runs after all fetching completes, not during pagination:

1. `read_existing_ids` scans `*.md` files in the output directory and extracts tweet IDs from `tweet_url` frontmatter.
2. Fetched bookmarks are filtered against these IDs. Only novel tweets proceed to categorization.
3. If all fetched bookmarks are already saved, the run exits immediately with `noop` status.
4. A second defensive dedup check runs during file writing.

### Categorization

[`src/categorizer.py`](x-bookmarks/src/categorizer.py) builds a prompt from the current vault taxonomy when available. The taxonomy is dynamic:

- existing `category` and `subCategory` values are preferred
- new subcategories can be added under existing categories
- new categories are created only when no existing category fits
- `General` and `Uncategorized` are explicitly discouraged in the prompt

If Claude returns no mapping for a tweet, the current code still falls back internally to `General` / `Uncategorized` as a last-resort safety behavior.

### Markdown Output

[`src/markdown_writer.py`](x-bookmarks/src/markdown_writer.py) writes notes with the required frontmatter schema and body structure:

```yaml
---
title: "LangGraph Agent Memory Patterns"
author: "@handle"
category: "AI Coding"
subCategory: "Coding Workflows"
date: 2026-02-23
read: false
synthesized: false
type: "post"
tweet_url: "https://x.com/handle/status/123456789"
---
```

Posts use blockquoted tweet text. Articles write article content directly. Both include `## References`.

### Synthesized Bookmark Removal

[`src/removal.py`](x-bookmarks/src/removal.py) implements the destructive removal workflow. It backfills active notes missing `synthesized` with `synthesized: false`, then treats only exact lowercase `synthesized: true` as eligible.

For each eligible note, the CLI calls `DELETE /2/users/{id}/bookmarks/{tweet_id}` through [`src/api_client.py`](x-bookmarks/src/api_client.py). `404` is treated as idempotent success because the bookmark is already absent. After success, the note gets `bookmark_removed: true` and `bookmark_removed_at: YYYY-MM-DDTHH:MM:SSZ`, then moves to `output_dir / "archive"`.

Archived notes are intentionally excluded from active deduplication because `read_existing_ids` scans only `output_dir/*.md`. If the same tweet is bookmarked again later, normal sync can write a new active note.

### Migration

[`src/migrate.py`](x-bookmarks/src/migrate.py) updates older note files to the current schema, normalizes frontmatter, upgrades titles, and renames files to title slugs.

## Commands

| Command                                       | Purpose                                |
| --------------------------------------------- | -------------------------------------- |
| `uv run x-bookmarks-auth`                     | Run OAuth setup                        |
| `uv run x-bookmarks`                          | Fetch, categorize, and write bookmarks |
| `uv run x-bookmarks --remove-synthesized-bookmarks --dry-run` | Preview strict synthesized removals |
| `uv run x-bookmarks --remove-synthesized-bookmarks --confirm` | Remove eligible X bookmarks and archive notes |
| `uv run x-bookmarks-migrate /path/to/x-posts` | Migrate older bookmark notes           |

## Current Constraints

- Requires an X developer app with bookmark access (Basic tier or higher; Free tier has no bookmark access).
- Requires a valid Anthropic API key.
- Stores tokens locally in plaintext `.env`.
- Assumes an Obsidian-oriented output structure.
- Destructive bookmark removal requires `bookmark.write` and explicit confirmation.
- Uses a single Claude request per run today; large runs are a roadmap item for chunking.
- The X API has a known pagination bug that caps retrieval at approximately 300 bookmarks (~3 pages) even when the user has more. Run the tool regularly to keep new bookmarks within the retrievable window.
- There is no early-stop optimization during fetching; all pages are fetched before dedup runs.

## Testing

The project currently uses `pytest`, `pytest-cov`, `pytest-asyncio`, and `respx`. Coverage is configured with an `80%` threshold in [`pyproject.toml`](x-bookmarks/pyproject.toml).

Run:

```bash
.venv/bin/python -m pytest
```
