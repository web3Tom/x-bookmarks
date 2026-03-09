# x-bookmarks

Fetch your `x.com` bookmarks through the X API, classify them with Claude, and save them as structured Obsidian Markdown notes.

Project URL: `https://github.com/web3Tom/x-bookmarks`

## Who This Is For

This project is for developers who want to turn saved X posts and articles into a categorized knowledge base. To use it, you need:

- an X developer app/project with bookmark access
- Python 3.11+
- `uv`
- an Anthropic API key
- an Obsidian vault or another target directory for the generated notes

## Quick Start

### 1. Install dependencies

```bash
uv sync
```

### 2. Create your local environment file

```bash
cp .env.example .env
```

Add your `CLIENT_ID` first. The OAuth helper will fill in the access token, refresh token, and user ID.

### 3. Authenticate with X

```bash
uv run x-bookmarks-auth
```

This opens a browser for OAuth 2.0 PKCE authorization and writes the returned credentials to `.env`.

### 4. Add your Anthropic API key

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
```

### 5. Set your output location

Set `KNOWLEDGE_BASE_DIR` in `.env` if you want to override the default output root.

Generated notes are written under:

```text
${KNOWLEDGE_BASE_DIR}/03_AI/x/x-posts/
```

If `KNOWLEDGE_BASE_DIR` is unset, the tool defaults to `~/x-bookmarks-data`.

### 6. Run the pipeline

```bash
uv run x-bookmarks
```

## Features

- Fetches bookmarks from the X API with pagination
- Refreshes expired access tokens automatically
- Uses Claude to generate a title plus `category` and `subCategory`
- Writes Obsidian-friendly Markdown with Dataview-compatible frontmatter
- Uses title-based filenames such as `{title-slug}.md`
- Skips bookmarks that were already written
- Supports long-form posts and X Articles
- Includes a migration command for older bookmark files

## Migration

Use the migration command to normalize older bookmark notes to the current schema.

What it does:

- removes deprecated frontmatter fields
- replaces raw-text titles with LLM-generated titles
- renames files from date/author slugs to title slugs
- normalizes frontmatter quoting and body headings

### Dry run

```bash
uv run x-bookmarks-migrate /path/to/x-posts --dry-run --verbose
```

### Live migration

```bash
uv run x-bookmarks-migrate /path/to/x-posts --verbose
```

### Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview changes without writing files |
| `--verbose` | Show per-file details |
| `--batch-size N` | Files per Claude API call |
| `--api-key KEY` | Anthropic API key override |

## Development

Run the test suite with coverage:

```bash
uv run pytest --cov=src --cov-report=term-missing
```

## Project Docs

- [`docs/overview.md`](docs/overview.md)
- [`docs/roadmap.md`](docs/roadmap.md)
- [`docs/public-release-audit.md`](docs/public-release-audit.md)
- [`docs/public-release-plan.md`](docs/public-release-plan.md)
- [`docs/github-issues.md`](docs/github-issues.md)
- [`AGENTS.md`](AGENTS.md)

## Security Notes

- OAuth tokens and your Anthropic API key are stored locally in `.env`.
- `.env` is ignored by Git, but you should still review `git status` before every push.
- The repository does not currently encrypt local token storage.
