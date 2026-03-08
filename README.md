# X Bookmarks to Obsidian

Fetch all your X (Twitter) bookmarks via API v2, categorize them with Claude, and write categorized Markdown files into an Obsidian vault.

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Authenticate with X

```bash
uv run x-bookmarks-auth
```

This opens your browser for OAuth 2.0 PKCE authorization and saves tokens to `.env`.

### 3. Add your Anthropic API key

Edit `.env` and set `ANTHROPIC_API_KEY`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

### 4. Run

```bash
uv run x-bookmarks
```

Bookmarks are written to `~/Documents/projects/workspace/knowledge/03_AI/x/x-posts/` as categorized Markdown files (override with `KNOWLEDGE_BASE_DIR` env var).

## Features

- Fetches up to 800 bookmarks with automatic pagination
- Automatic OAuth token refresh on expiry
- Single-batch categorization via Claude (claude-sonnet-4-6)
- LLM-generated titles and title-based filenames (`{title-slug}.md`)
- Deduplication: re-running skips already-saved bookmarks
- Obsidian-compatible frontmatter with Dataview support
- Supports long-form tweets (note_tweet) and X Articles

## Migration

Migrate existing bookmark files to the current schema. This will:

- Strip deprecated frontmatter fields (`author_name`, `tweet_id`, `likes`, `retweets`, `replies`, `bookmarks`, `has_media`, `has_links`)
- Generate LLM titles via Claude (replaces raw tweet text titles)
- Rename files from `{date}-{author}.md` to `{title-slug}.md`
- Normalize frontmatter quoting and update body headings

### Dry run (preview changes, no files modified)

```bash
uv run python -m src.migrate ~/Documents/projects/workspace/knowledge/03_AI/x/x-posts --dry-run --verbose
```

### Live migration

```bash
uv run python -m src.migrate ~/Documents/projects/workspace/knowledge/03_AI/x/x-posts --verbose
```

### Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview changes without writing or renaming files |
| `--verbose` | Show per-file details (old→new filename, title changes, removed fields) |
| `--batch-size N` | Files per Claude API call (default: 150) |
| `--api-key KEY` | Anthropic API key (defaults to `ANTHROPIC_API_KEY` env var) |

## Development

```bash
uv run python -m pytest --cov=src --cov-report=term-missing
```
