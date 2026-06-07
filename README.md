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
The requested X scopes include `bookmark.read` and `bookmark.write`; the write scope is only used by the explicit removal mode.

### 4. Add your Anthropic API key

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
```

### 5. Set your output location once

Set `KNOWLEDGE_BASE_DIR` in `.env` to the directory where you want bookmark notes written.

```dotenv
KNOWLEDGE_BASE_DIR=/path/to/your/notes
```

If `KNOWLEDGE_BASE_DIR` is unset, the tool defaults to `~/x-bookmarks-data`.
The OAuth helper preserves this setting when it refreshes `.env`, so you do not need to re-export or re-add it after running `x-bookmarks-auth`.
If a private shell setup already exports `KNOWLEDGE_DIR`, the CLI can use it as a fallback and `x-bookmarks-auth` will write it back as the canonical `KNOWLEDGE_BASE_DIR` entry in local `.env`.
The CLI also reads simple `export KNOWLEDGE_BASE_DIR=...` entries from ignored `.envrc.local`, so the configured output directory still works when direnv has not populated the current shell.
If the resolved output directory does not exist, the CLI prints a warning before fetching: deduplication treats a missing directory as an empty vault, so every bookmark would be categorized as new. This is expected on a first run, but otherwise signals a misconfigured `KNOWLEDGE_BASE_DIR`.

#### Optional: customize the taxonomy

By default the tool uses neutral pillars and mechanics. To define custom pillars, mechanics, or entity tags for categorization, point `X_BOOKMARKS_TAXONOMY_FILE` at a Markdown override file:

```dotenv
X_BOOKMARKS_TAXONOMY_FILE=/path/to/taxonomy.md
```

The override file's `pillars`, `mechanics`, and `entity_tags` replace the neutral defaults. An optional `deprecate:` list steers Claude away from unwanted values, and an optional guidance body is appended to the prompt. See [`docs/taxonomy.md`](docs/taxonomy.md) for the full format and [`taxonomy.example.md`](taxonomy.example.md) for a copyable template. The same file works with `migrate.py --taxonomy-file` for bulk re-categorization.

### 6. Run the pipeline

```bash
uv run x-bookmarks
```

## Features

- Fetches bookmarks from the X API with pagination (up to 100 per page, 800 max per run)
- Refreshes expired access tokens automatically
- Deduplicates against previously saved notes before categorizing
- Uses Claude to generate a title plus `pillar`, `mechanics`, and optional `entity_tags`
- Writes Obsidian-friendly Markdown with Dataview-compatible frontmatter
- Uses title-based filenames such as `{title-slug}.md`
- Supports long-form posts and X Articles
- Includes a migration command for older bookmark files
- Includes an explicit, confirmed removal mode for bookmarks whose notes are marked `synthesized: true`

## Known Limitations

- **X API pagination bug:** The bookmarks endpoint often stops returning pages after approximately 300 bookmarks (~3 pages), even when you have more saved. This is a known X API issue. Run the tool regularly so new bookmarks stay within the retrievable window.
- **No fetch-time dedup:** All available pages are fetched before deduplication runs. There is no early-stop optimization that skips remaining pages when duplicates are found.
- **API tier requirement:** Bookmark access requires at least the X API Basic tier. The Free tier does not support bookmarks.

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

## Removing Synthesized X Bookmarks

Removal mode is destructive and opt-in. Normal sync never deletes X bookmarks or archives notes.

Preview eligible notes:

```bash
uv run x-bookmarks --remove-synthesized-bookmarks --dry-run
```

Live deletion requires confirmation:

```bash
uv run x-bookmarks --remove-synthesized-bookmarks --confirm
```

Eligibility is strict: only active notes in `KNOWLEDGE_BASE_DIR` with exact `synthesized: true` are candidates. Notes with `synthesized: false`, missing fields, quoted values, uppercase booleans, or malformed frontmatter are skipped. Before scanning, the CLI backfills active notes that lack the field with `synthesized: false`.

After a successful X deletion, or a `404` indicating the bookmark is already absent, the note is annotated with `bookmark_removed: true` and `bookmark_removed_at`, then moved to `KNOWLEDGE_BASE_DIR/archive`. Archived notes do not block future sync deduplication.

If deletion returns `403`, re-run `uv run x-bookmarks-auth`; older tokens do not gain the new `bookmark.write` scope automatically.

Live deletion is capped at 50 bookmarks per run. Use `--max N` to process fewer.

## Development

Run the test suite with coverage:

```bash
uv run pytest --cov=src --cov-report=term-missing
```

## Project Docs

- [`docs/overview.md`](docs/overview.md)
- [`docs/roadmap.md`](docs/roadmap.md)
- [`docs/github-issues.md`](docs/github-issues.md)
- [`docs/CHANGELOG.md`](docs/CHANGELOG.md)
- [`docs/prds/prd-x-bookmark-removal.md`](docs/prds/prd-x-bookmark-removal.md)
- [`AGENTS.md`](AGENTS.md)

## Security Notes

- OAuth tokens and local configuration are stored in `.env`.
- `.env` is ignored by Git, but you should still review `git status` before every push.
- The repository does not currently encrypt local token storage.
- `KNOWLEDGE_BASE_DIR` may contain a machine-specific path. Keep it in `.env` or `.envrc.local`, not in committed docs or code.
- If `ANTHROPIC_API_KEY` is unset (or blank) after loading `.env`, the loader falls back to fetching it from the user's [`pass`](https://www.passwordstore.org/) store at `ai/anthropic/api-key`. This lets you keep the key out of `.env` entirely and still run the tool through a `direnv`/`pass` workflow. The fallback is silently skipped if `pass` is not installed.
