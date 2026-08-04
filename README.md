# x-bookmarks

Fetch your `x.com` bookmarks for free, classify them with Claude, and save them as structured Obsidian Markdown notes. No X developer account required.

Project URL: `https://github.com/web3Tom/x-bookmarks`

## Who This Is For

This project is for developers who want to turn saved X posts and articles into a categorized knowledge base. To use it, you need:

- Python 3.11+
- `uv`
- an Anthropic API key
- an Obsidian vault or another target directory for the generated notes
- `twitter-cli` (`pipx install twitter-cli`) and your X session cookies

**No X developer account or API subscription is required.** By default the tool reads bookmarks through `twitter-cli`, which uses X's private GraphQL API with your session cookies rather than the paid developer platform. See [Retrieval mechanism](#retrieval-mechanism) for what that means and its risks. The official OAuth path is still available via `--official` if you have a developer app and prefer the sanctioned route.

## Quick Start

### 1. Install dependencies

```bash
uv sync
```

### 2. Create your local environment file

```bash
cp .env.example .env
```

Only `ANTHROPIC_API_KEY` and `KNOWLEDGE_BASE_DIR` are needed for a default run. The X OAuth entries are optional and used only with `--official`.

### 3. Supply your X session cookies

```bash
pipx install twitter-cli

# Export from x.com via DevTools > Application > Cookies, or the Cookie-Editor extension
export TWITTER_AUTH_TOKEN='...'
export TWITTER_CT0='...'
```

Both are **required**, not optional. This is a safety mechanism: when they are absent, `twitter-cli` scans your Chrome/Edge cookie jars to find them. Refusing to run without both is what prevents that unconsented scan.

<details>
<summary>Using the official OAuth path instead (optional)</summary>

If you have an X developer app and prefer the sanctioned API, run:

```bash
uv run x-bookmarks-auth
```

This opens a browser for OAuth 2.0 PKCE authorization and writes the returned credentials to `.env`.
The requested X scopes include `bookmark.read` and `bookmark.write`; the write scope is only used by the explicit removal mode.
Then pass `--official` on every run. This costs money and is subject to the ~300-per-run pagination ceiling.

</details>

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

- Fetches bookmarks for free via `twitter-cli`, cursor-paginated with no ~300-per-run ceiling
- Optional `--official` OAuth path with automatic token refresh
- Deduplicates against previously saved notes before categorizing
- Uses Claude to generate a title plus `pillar`, `mechanics`, and optional `entity_tags`
- Writes Obsidian-friendly Markdown with Dataview-compatible frontmatter
- Uses title-based filenames such as `{title-slug}.md`
- Supports long-form posts and X Articles
- Includes a migration command for older bookmark files
- Includes an explicit, confirmed removal mode for bookmarks whose notes are marked `synthesized: true`

## Known Limitations

- **`--official` pagination ceiling:** On the official path the bookmarks endpoint often stops returning pages after approximately 300 bookmarks (~3 pages). This is a known X API issue and does not affect the default `twitter-cli` path, which is cursor-paginated.
- **No fetch-time dedup:** All available pages are fetched before deduplication runs. There is no early-stop optimization that skips remaining pages when duplicates are found.
- **`--official` tier requirement:** The official path requires at least the X API Basic tier; the Free tier does not support bookmarks. The default path needs no developer account at all.
- **Default path is unsanctioned:** It violates the X Developer Agreement and can get your account flagged. See [Retrieval mechanism](#retrieval-mechanism).

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

Deletion uses `twitter-cli` by default. Add `--official` to delete through the OAuth API instead, which has stricter, documented error semantics; if that returns `403`, re-run `uv run x-bookmarks-auth`, as older tokens do not gain the `bookmark.write` scope automatically.

Live deletion is capped at 50 bookmarks per run. Use `--max N` to process fewer.

## Enriching Link Titles

External link titles are frequently missing (always, on the default path, which emits bare URLs), which makes notes less readable and gives Claude less signal during categorization. Opt in to backfill those titles:

```bash
uv run x-bookmarks --enrich-titles
```

Titles are fetched from [Jina Reader](https://r.jina.ai) with `GET https://r.jina.ai/{url}` — no API key, no account, no credential of any kind. Enrichment runs *after* deduplication, so only genuinely new bookmarks cost a request, and repeated URLs are fetched once per run. A failed or slow fetch leaves the title empty and never aborts the run.

**Trade-off:** every enriched URL is disclosed to a third-party service. That is why this is opt-in rather than automatic. If your bookmarks include private or sensitive links, leave it off.

## Retrieval Mechanism

By default, fetching **and removal** go through `twitter-cli`, which calls X's private GraphQL API using your session cookies.

> **This violates the X Developer Agreement and can get your account flagged or locked.** `twitter-cli` ships TLS fingerprint impersonation and request timing jitter documented as evading pattern detection, so its traffic is built to be indistinguishable from a browser. Running it on every sync is a recurring automated pattern against your real, named account. Read [`docs/feasibility-agent-reach.md`](docs/feasibility-agent-reach.md) for the full assessment.

This was chosen deliberately: it removes the paid API entirely and lifts the official endpoint's ~300-per-run pagination ceiling.

### What changes versus the official API

| | Default (`twitter-cli`) | `--official` |
|---|---|---|
| Cost | Free | Paid tier required |
| Fetch ceiling | Cursor-paginated, bounded only by `--max-bookmarks` | ~300 per run |
| Credential | `auth_token` (≈ full account access) | OAuth, scoped to `bookmark.*`, revocable |
| Sanctioned | No | Yes |
| Link titles | Never populated (bare URLs) | Sometimes populated |
| Delete semantics | Inferred from stderr | Documented 404 = already absent |

### Delete semantics caveat

The official `DELETE` documents 404 as "already absent", which makes re-running a removal safe. The private surface has no such contract, so absence is inferred from a narrow stderr allowlist. Anything not positively matched raises rather than reporting success, because reporting a failed delete as success would archive the note while the bookmark still exists on X.

If that matters for a given cleanup, run removal with `--official`.

### Flags

| Flag | Description |
|------|-------------|
| `--official` | Use the official X API (OAuth) for fetching and removal. Requires a developer app; incurs cost. |
| `--max-bookmarks N` | Maximum bookmarks to request via `twitter-cli` (default 5000). Not valid with `--official`. |
| `--enrich-titles` | Backfill missing external-link titles via Jina Reader. Works on either path. |

Pair `--enrich-titles` with the default path: `twitter-cli` emits bare URL strings with no title metadata, so on this path *every* external link title starts empty.

```bash
uv run x-bookmarks --enrich-titles
uv run x-bookmarks --max-bookmarks 5000 --enrich-titles   # deep backfill
uv run x-bookmarks --official                             # sanctioned, paid
```

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

### Feasibility Studies

Candidate-mechanism assessments backing roadmap item `#17` (zero-cost bookmark retrieval). Each records a verdict and the evidence behind it; none has been adopted.

- [`docs/feasibility-graphql-vs-x-api.md`](docs/feasibility-graphql-vs-x-api.md) — cookie/GraphQL session replay vs. the official API
- [`docs/feasibility-agent-reach.md`](docs/feasibility-agent-reach.md) — `Panniantong/Agent-Reach`
- [`docs/feasibility-x-research-skill.md`](docs/feasibility-x-research-skill.md) — `rohunvora/x-research-skill`

## Security Notes

- OAuth tokens and local configuration are stored in `.env`.
- `.env` is ignored by Git, but you should still review `git status` before every push.
- The repository does not currently encrypt local token storage.
- `KNOWLEDGE_BASE_DIR` may contain a machine-specific path. Keep it in `.env` or `.envrc.local`, not in committed docs or code.
- If `ANTHROPIC_API_KEY` is unset (or blank) after loading `.env`, the loader falls back to fetching it from the user's [`pass`](https://www.passwordstore.org/) store at `ai/anthropic/api-key`. This lets you keep the key out of `.env` entirely and still run the tool through a `direnv`/`pass` workflow. The fallback is silently skipped if `pass` is not installed.
- **Agent session transcripts:** AI coding agents may log tool calls, including environment and HTTP headers, into session transcripts. If you run this tool inside an agent session, credentials can end up in those logs. Prefer exported environment variables over inline command arguments, and review your agent's log settings.
- **`TWITTER_AUTH_TOKEN` is not a scoped token.** Unlike the OAuth tokens used on the default path, which are scoped to `bookmark.*` and individually revocable, the `auth_token` cookie is roughly full account access. Never commit it, never pass it as a command-line argument, and revoke it by logging out of all X sessions if you suspect exposure. The unofficial backfill passes it only through the child process environment, never argv.
