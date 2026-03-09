# Contributing

## Scope

This project is a Python CLI for exporting and categorizing `x.com` bookmarks into Obsidian-friendly Markdown. Contributions should keep the tool simple, reproducible, and safe for local use.

## Local Setup

```bash
uv sync
cp .env.example .env
```

Then configure your local credentials and run tests:

```bash
.venv/bin/python -m pytest
```

## Guidelines

- Keep changes focused and easy to review.
- Do not commit `.env`, tokens, local caches, generated coverage files, or virtualenv changes.
- Preserve the Markdown frontmatter schema and note structure unless the change is intentional and documented.
- Add or update tests when behavior changes.
- Update docs when setup, config, or output behavior changes.

## Pull Requests

- Explain the user-facing change.
- Note any migration or compatibility impact.
- Include verification steps.

## Security

- Never commit live credentials.
- Treat OAuth and Anthropic tokens as local-only secrets.
- If you find a security issue, report it privately to the maintainer before opening a public issue.
