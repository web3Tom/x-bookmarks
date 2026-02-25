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

Bookmarks are written to `~/Documents/notes/obsidianVaults/dev-notes/03_AI/x/` as categorized Markdown files.

## Features

- Fetches up to 800 bookmarks with automatic pagination
- Automatic OAuth token refresh on expiry
- Single-batch categorization via Claude (claude-sonnet-4-6)
- Deduplication: re-running skips already-saved bookmarks
- Obsidian-compatible frontmatter with bookmark counts and timestamps
- Supports long-form tweets (note_tweet) and X Articles

## Development

```bash
uv run pytest --cov=src --cov-report=term-missing
```
