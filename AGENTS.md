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

- Keep [`README.md`](/home/tom/Documents/projects/workspace/x-bookmarks/README.md) aligned with the real setup flow.
- Keep [`docs/overview.md`](/home/tom/Documents/projects/workspace/x-bookmarks/docs/overview.md) aligned with current architecture and behavior.
- Keep [`docs/roadmap.md`](/home/tom/Documents/projects/workspace/x-bookmarks/docs/roadmap.md) as the planning source unless replaced intentionally.
- Keep [`docs/github-issues.md`](/home/tom/Documents/projects/workspace/x-bookmarks/docs/github-issues.md) in sync when roadmap items are re-scoped materially.

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

- [`docs/github-issues.md`](/home/tom/Documents/projects/workspace/x-bookmarks/docs/github-issues.md)
- [`docs/roadmap.md`](/home/tom/Documents/projects/workspace/x-bookmarks/docs/roadmap.md)

If GitHub API workflow is available:

- create issues from `docs/github-issues.md`
- avoid duplicating existing issue titles
- preserve the issue title and body structure unless there is a clear repo-specific reason to change it

### Pull Down Issues

If a local issue-sync workflow is established later, use it to refresh planning docs from GitHub before editing roadmap-derived work. Until then:

- treat GitHub Issues as the live execution backlog
- treat `docs/roadmap.md` as the higher-level planning document
- manually reconcile issue status back into docs when major planning changes are made

## Validation Checklist

Before finishing:

- no secrets or local-only files are staged
- tests pass for code changes
- docs reflect the current behavior
- no stale personal paths or private URLs were introduced
- generated note schema expectations remain intact
