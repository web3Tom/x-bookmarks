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
5. For link-only bookmarks, read the linked page so the categorizer has something to work with.
6. Ask Claude to generate a title plus `pillar`, `mechanics`, and optional `entity_tags`.
7. Write one Markdown note per bookmark.
8. Append structured run metadata to `.x-bookmarks-history.jsonl`.

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

1. `read_existing_ids` scans `*.md` files in the output directory and extracts tweet IDs from `tweet_url` frontmatter. A missing output directory yields an empty ID set; the CLI warns at startup so this does not silently re-categorize the whole vault when `KNOWLEDGE_BASE_DIR` is misconfigured.
2. Fetched bookmarks are filtered against these IDs. Only novel tweets proceed to categorization.
3. If all fetched bookmarks are already saved, the run exits immediately with `noop` status.
4. A second defensive dedup check runs during file writing.

### Link Enrichment

[`src/enrichment.py`](x-bookmarks/src/enrichment.py) fills in what the bookmark source leaves empty, reading `https://r.jina.ai/{url}` — an unauthenticated GET returning the page as Markdown with a `Title:` header and a `Markdown Content:` body. Two backfills share that one response:

- `backfill_titles` populates `ExternalLink.title`. Opt-in via `--enrich-titles`, because it touches every external link.
- `backfill_articles` populates `Tweet.article_content` for link-only bookmarks — a tweet whose whole text is a shortlink. Automatic, but scoped to tweets that have no substantive text of their own, no article text already, and an external link to follow. A bookmark with its own prose is never fetched.

Both run after deduplication, so only genuinely new bookmarks cost a request, and repeated URLs are fetched once per run. Any fetch failure degrades to leaving the field empty; enrichment never aborts a run.

Neither holds a credential nor touches an X endpoint, so this path carries none of the account risk in [`feasibility-agent-reach.md`](x-bookmarks/docs/feasibility-agent-reach.md). The cost is that each enriched URL is disclosed to a third party.

### Categorization

[`src/categorizer.py`](x-bookmarks/src/categorizer.py) builds a prompt using the override taxonomy file or neutral defaults. The schema is faceted:

- **Pillar**: Selects exactly one pillar (strategic mode). Pillars come from the override file if present, else neutral `DEFAULT_PILLARS`. The tool does not read existing vault notes to discover pillars.
- **Mechanics**: Optional vocabulary of categorization techniques. Mechanics come from the override file if present, else `DEFAULT_MECHANICS` (empty). Claude can invent new mechanics beyond the seed vocabulary.
- **Entity tags**: Optional nested dict tagging specific tools, frameworks, models. Entity tags come from the override file if present, else empty. Closed prefixes (framework, harness, model, tool), open entity vocabulary.

Claude's categorization is guided by optional domain-specific guidance appended from the override file body.

Each tweet is sent as `text` plus `author`, with `article_title` and `article_excerpt` added when available. `article_title` matters disproportionately: for a link-only X Article bookmark it is the only signal present, and without it Claude sees a bare shortlink and falls back to a placeholder title.

An unparseable reply is retried once, then raises `CategorizationError`. This is deliberately not a bare `JSONDecodeError`: by that point the bookmarks have been fetched, so the failure must name the stage it came from rather than look like a fetch bug.

### Markdown Output

[`src/markdown_writer.py`](x-bookmarks/src/markdown_writer.py) writes notes with the faceted frontmatter schema and body structure:

```yaml
---
title: "LangGraph Agent Memory Patterns"
author: "@handle"
pillar: "Applied Practice"
mechanics:
  - tutorials
  - design-patterns
entity_tags:
  framework: [langgraph]
date: 2026-02-23
read: false
synthesized: false
type: "post"
tweet_url: "https://x.com/handle/status/123456789"
---
```

Notes may omit `mechanics` and `entity_tags` if empty (not present in YAML if the lists/dicts are empty). Posts use blockquoted tweet text. Articles write article content directly. Both include `## References`.

`article_url` is emitted whenever the tweet carries one, independently of `type`. It is deliberately not gated on article text being present: `twitter-cli` never returns article text, so gating the two together dropped the URL for every X Article and left the note pointing at an opaque `t.co` redirect.

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
- X Article bodies cannot be retrieved. `twitter-cli` does not return article text (observed: 0 of 200 bookmarks in a live sample carried `articleText`), and Jina Reader refuses `x.com`. Notes for X Articles get accurate frontmatter and a working `article_url`, but their body shows only the original shortlink.

## Testing

The project currently uses `pytest`, `pytest-cov`, `pytest-asyncio`, and `respx`. Coverage is configured with an `80%` threshold in [`pyproject.toml`](x-bookmarks/pyproject.toml).

Run:

```bash
.venv/bin/python -m pytest
```
