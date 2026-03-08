# x-bookmarks — Project Overview

## Purpose

x-bookmarks is a CLI pipeline that fetches saved bookmarks from an X.com (Twitter) profile via the X API v2, categorizes them using Claude, and writes each bookmark as an individual Obsidian Markdown note into a target vault directory. The result is a searchable, queryable knowledge base of AI-focused content saved on X.

## Target Output

| Setting | Value |
|---------|-------|
| Knowledge base | `~/Documents/projects/workspace/knowledge/` (override via `KNOWLEDGE_BASE_DIR` env var) |
| Output subdirectory | `03_AI/x/x-posts/` |
| File naming | `YYYY-MM-DD-handle.md` (e.g., `2026-02-23-theo.md`) |
| Collision handling | Numeric suffix (`-2`, `-3`, …) for same-day, same-author posts |

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐     ┌────────────────┐
│  X API v2    │────▶│  Categorizer │────▶│ Markdown Writer  │────▶│ Obsidian Vault │
│  (bookmarks) │     │  (Claude)    │     │ (frontmatter +   │     │ (03_AI/x/      │
│  x-posts/)     │
│              │     │              │     │  body generation) │     │                │
└──────────────┘     └──────────────┘     └──────────────────┘     └────────────────┘
      ▲                                          │
      │                                          ▼
  OAuth 2.0 PKCE                         index.md (Dataview)
  token refresh
```

## Pipeline Stages

### 1. Authentication (`src/auth_helper.py`)

- One-time interactive OAuth 2.0 PKCE flow
- Spins up a local callback server on port 8000
- Generates a PKCE `code_verifier` / `code_challenge` pair
- Exchanges the authorization code for access + refresh tokens
- Fetches the authenticated user's ID via `/2/users/me`
- Persists all credentials to `.env`

Run via: `uv run x-bookmarks-auth`

### 2. Configuration (`src/config.py`)

- Loads credentials and settings from `.env` using `python-dotenv`
- Frozen dataclass (`Config`) with fields: `client_id`, `client_secret` (optional), `access_token`, `refresh_token`, `user_id`, `anthropic_api_key`, `output_dir`
- Validates that all required variables are present (`CLIENT_SECRET` is optional); raises `ValueError` on missing keys
- `output_dir` resolves from `KNOWLEDGE_BASE_DIR` env var (default: `~/Documents/projects/workspace/knowledge`) + `03_AI/x/x-posts`

### 3. Bookmark Fetching (`src/api_client.py`)

- Hits `GET /2/users/{user_id}/bookmarks` with expansions for authors, media, and full tweet fields
- Paginates using `next_token` with 100 results per page, capped at **800 bookmarks** total
- On `401 Unauthorized`, automatically refreshes the access token via `POST /2/oauth2/token` (client credentials + refresh token), updates `.env` in place, and retries
- Parses each bookmark into a `Tweet` data model (see below)

**URL filtering logic:**
- External links exclude self-referential domains (`x.com`, `twitter.com`, `t.co`)
- Detects article URLs matching `x.com/i/article/` pattern and extracts article content when available

### 4. Data Models (`src/models.py`)

All models are **frozen dataclasses** (immutable). Collection fields use `tuple` instead of `list`.

| Model | Key Fields |
|-------|-----------|
| `User` | id, name, username, profile_image_url, verified |
| `Media` | media_key, type, url, preview_image_url, variants |
| `ExternalLink` | url, expanded_url, display_url, title |
| `Tweet` | id, text, author_id, created_at, author, public_metrics, media, external_links, note_tweet_text, article_url, article_content, article_title |
| `Category` | slug (kebab-case), display_name (Title Case), sub_category |
| `CategorizedTweet` | tweet, category, title |
| `BookmarkPage` | tweets, next_token |

`Tweet.display_text` property prefers `note_tweet_text` (long-form) over `text` (truncated).

### 5. Categorization (`src/categorizer.py`)

- Sends the full batch of bookmarks to **Claude claude-sonnet-4-6** in a single API call
- Constructs a JSON payload per tweet: `tweet_id`, `text` (display_text), `author` (username), and optionally `article_excerpt` (truncated to 2,000 chars)
- System prompt lists the **fixed 10-category taxonomy** (from AGENTS.md) and instructs Claude to pick from it exclusively
- Each category has defined subcategories; Claude must return both `category` and `sub_category`
- Claude also generates a concise, descriptive **title** (max 80 chars, YAML-safe) for each bookmark
  - For articles: prefers the article's actual title/topic
  - For posts: summarizes the key insight or topic (not just truncated tweet text)
- Response format: `[{"tweet_id": "...", "category": "AI Coding", "sub_category": "Coding Workflows", "title": "LangGraph Agent Memory Patterns"}, ...]`
- Response parsing handles both raw JSON and markdown-fenced (` ```json `) output
- Slug is generated from display name via `_slugify()` (lowercase, spaces/& → hyphens)
- Tweets not mapped in Claude's response fall back to **General / Uncategorized** with a sanitized `display_text` fallback title
- Empty titles from Claude fall back to sanitized `display_text` via `_sanitize_title()`

**Taxonomy (preferred, with flexibility):**

Claude must pick from the fixed taxonomy whenever possible. If a tweet genuinely cannot fit any existing category and "General" would lose important signal, Claude may create a new category with Title Case naming, exactly one sub_category, concise 2-4 word names, and no overlap with existing categories.

| Category | Subcategories |
|----------|---------------|
| AI Coding | Coding Workflows, Prompt & Context Engineering |
| Agent Architectures | Applied Agents, Frameworks & Patterns |
| Agent Reliability | Evals & Observability |
| Context Engineering | RAG & Context, Agent Memory |
| Model Systems | Inference & Serving, Model Releases |
| AI Knowledge Systems | Obsidian & PKM |
| ML Research | Research Digest, Applied ML |
| AI Product & Strategy | Monetization & GTM |
| AI Productivity | Workflows & Execution |
| AI Career & Mindset | Performance & Habits |
| General | Uncategorized |

### 6. Markdown Generation (`src/markdown_writer.py`)

Each bookmark becomes an Obsidian note with:

**Frontmatter (YAML):**
```yaml
---
title: "LangGraph Agent Memory Patterns"
author: "@handle"
category: "AI Coding"
subCategory: "Coding Workflows"
date: 2026-02-23
read: false
type: "post"
tweet_url: "https://x.com/handle/status/123456789"
article_url: "https://..." # only for articles
---
```

- Title is Claude-generated (max 80 chars, YAML-safe) — not truncated tweet text
- All string fields are double-quoted to prevent YAML parsing issues (e.g., `&` in subcategories)
- Frontmatter is validated via `yaml.safe_load()` after generation; broken YAML triggers an automatic repair attempt

**Body structure:**

- **Posts**: `## {title}` (blockquoted tweet text + media) then `## References` (tweet link + external links)
- **Articles**: `## {title}` (article content) then `## References` (tweet link)

**Deduplication**: Scans all existing files' frontmatter for tweet IDs extracted from `tweet_url` values before writing. Skips any bookmark already present.

**Index file**: Overwrites `index.md` on every run with a Dataview TABLE query sorted by `category ASC, subCategory ASC, date DESC`, sourced from `"03_AI/x"`.

### 7. CLI Orchestration (`src/main.py`)

The `main()` function chains the pipeline sequentially:

1. `load_config()` — exits on error
2. Generate `run_id` (12-char UUID hex) used in all console output for the session
3. `fetch_bookmarks()` — paginated API calls
4. **Early deduplication** — `read_existing_ids()` is called here (before Claude) to filter out already-saved tweets; only `novel` tweets proceed
5. Print article summary (count of articles with/without API content, from novel set only)
6. `categorize_tweets(novel, ...)` — single Claude batch call on novel tweets only
7. `write_bookmarks()` — file generation + write-time deduplication guard
8. Print run summary (fetched / skipped / new / files written / token usage / duration / category breakdown)
9. Append structured JSON run record to `.x-bookmarks-history.jsonl` in `output_dir`

Run via: `uv run x-bookmarks`

### 8. Run History (`src/main.py` — `_append_history`)

Every run appends one JSON line to `{output_dir}/.x-bookmarks-history.jsonl`:

```json
{
  "run_id": "abc123def456",
  "status": "success|empty|noop",
  "started_at": "2026-02-23T12:00:00+00:00",
  "duration_ms": 4200,
  "output_dir": "/path/to/x-posts",
  "bookmarks": {
    "fetched": 50,
    "skipped_existing": 30,
    "novel": 20,
    "articles": 3
  },
  "output": {
    "files_written": 20,
    "duplicates_skipped": 0,
    "filenames": ["2026-02-23-handle.md", "..."],
    "index_updated": true
  },
  "token_usage": { "input_tokens": 12000, "output_tokens": 800 },
  "categories": { "AI Coding": 8, "Agent Architectures": 5 }
}
```

Statuses: `success` (files written), `noop` (all already saved), `empty` (API returned nothing).

Run via: `uv run x-bookmarks`

## Dependencies

| Package | Purpose |
|---------|---------|
| `httpx` | Async-capable HTTP client for X API and OAuth |
| `python-dotenv` | `.env` file loading |
| `anthropic` | Claude API client for categorization |
| `pyyaml` | YAML frontmatter validation |

Dev dependencies (via `uv`): `pytest`, `pytest-asyncio`, `pytest-cov`, `respx` (httpx mocking)

## Entry Points

| Command | Script | Purpose |
|---------|--------|---------|
| `uv run x-bookmarks-auth` | `src.auth_helper:main` | One-time OAuth setup |
| `uv run x-bookmarks` | `src.main:main` | Full fetch → categorize → write pipeline |
| `uv run x-bookmarks-migrate` | `src.migrate:main` | Migrate existing bookmark files to current standards |

## Test Coverage

- **Target**: 80% minimum (enforced via `pyproject.toml` `fail_under`)
- **Excluded**: `src/auth_helper.py` (interactive OAuth flow)
- **Mock strategy**: `respx` for HTTP, `unittest.mock` for Anthropic client
- **Run**: `uv run pytest --cov=src --cov-report=term-missing`

| Test File | Covers |
|-----------|--------|
| `test_models.py` | All dataclass creation, freezing, `from_api()` parsing |
| `test_config.py` | Env loading, validation, frozen enforcement |
| `test_api_client.py` | Tweet parsing, link filtering, pagination, 401 refresh |
| `test_categorizer.py` | Prompt building, response parsing, fallback categories |
| `test_markdown_writer.py` | Filename generation, frontmatter, body formatting, dedup, index |
| `test_migrate.py` | Frontmatter parsing, title generation, field removal, heading replacement, directory migration |
| `test_main.py` | Full pipeline integration (mocked) |

## Migration CLI (`src/migrate.py`)

Standalone module that retroactively applies current frontmatter and heading standards to existing bookmark files without calling the X API.

**What it fixes:**
- Removes deprecated frontmatter fields: `author_name`, `tweet_id`, `likes`, `retweets`, `replies`, `bookmarks`, `has_media`, `has_links`
- Ensures all string fields are double-quoted (prevents YAML breakage from `&` in subcategories)
- Replaces dumb titles (truncated tweet text) with Claude-generated descriptive titles
- Replaces `## Notes` body heading with `## {title}`
- Validates/corrects category and subcategory against the fixed taxonomy
- Preserves `read: true` values

**Usage:**

```bash
# Dry run (parse + generate titles, no file writes)
uv run x-bookmarks-migrate /path/to/bookmarks --dry-run --verbose

# Live migration
uv run x-bookmarks-migrate /path/to/bookmarks

# Custom batch size and explicit API key
uv run x-bookmarks-migrate /path/to/bookmarks --batch-size 20 --api-key sk-ant-...
```

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `directory` | (required) | Path to directory containing `*.md` bookmark files |
| `--api-key` | `ANTHROPIC_API_KEY` env var | Anthropic API key |
| `--batch-size` | 30 | Files per Claude API call |
| `--dry-run` | off | Parse and generate titles without writing files |
| `--verbose` | off | Enable debug logging and per-file output |

**How it works:**
1. Scans directory for `*.md` files (skips `index.md`)
2. Parses each file's YAML frontmatter and body
3. Batches bookmarks to Claude for title generation + taxonomy validation (~30 per API call)
4. Rebuilds frontmatter with only allowed fields, all strings double-quoted
5. Replaces the first `##` heading in the body with the new title
6. Writes the migrated file in-place

## Data Flow Summary

```
X.com bookmarks (up to 800)
  │
  ▼
fetch_bookmarks() ──pagination + 401 retry──▶ list[Tweet]
  │
  ▼
categorize_tweets() ──single Claude batch──▶ list[CategorizedTweet]
  │
  ▼
write_bookmarks() ──dedup + file I/O──▶ Obsidian notes (YYYY-MM-DD-handle.md)
                                         + index.md (Dataview query)
```
