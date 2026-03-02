## Purpose

This directory stores AI-focused bookmark notes (mostly X posts/articles) in Obsidian Markdown under `x-posts/`.

Primary goals:

- Keep notes readable and structured.
- Keep frontmatter consistent for Dataview.
- Classify content with deep AI subject categories.

## Directory Layout

- `x-posts/`: note files and index.
- `x-posts/index.md`: Dataview dashboard.

## File Naming

- Notes should use: `YYYY-MM-DD-handle.md`
- Example: `2026-02-23-theo.md`
- Keep one note per source post/article.

## Required Frontmatter Schema

Use this exact key set and casing:

```yaml
---
title: '...'
author: '@handle'
author_name: 'Display Name'
category: '...'
subCategory: '...'
date: 2026-02-25
read: false
type: 'post' # or "article"
tweet_id: '...'
tweet_url: 'https://x.com/...'
article_url: 'https://...' # optional
likes: 0
retweets: 0
replies: 0
bookmarks: 0
has_media: false
has_links: false
---
```

Rules:

- `subCategory` must be camelCase (not `sub-category`).
- `title` must be human-readable, not truncated (`...`), and no raw URLs.
- Keep booleans unquoted (`true`/`false`), numbers unquoted.
- Unknown frontmatter keys should be removed unless explicitly required.

## Body Structure

Preferred structure:

```md
## Notes

<cleaned content>

## References

- 🔗 [Original tweet](...)
- 🌐 [Article](...)
```

Rules:

- Keep `## Notes` as the main content section.
- Use `## References` for links.
- Promote clear article markers (`TL;DR`, `Part`, `Section`) to headings when helpful.
- Avoid giant unbroken text blocks when possible.

## Taxonomy Policy

Top-level `category` should be specific AI subject depth, not generic "AI Engineering".

Current allowed categories/subcategories:

- `AI Coding`
  - `Coding Workflows`
  - `Prompt & Context Engineering`
- `Agent Architectures`
  - `Applied Agents`
  - `Frameworks & Patterns`
- `Agent Reliability`
  - `Evals & Observability`
- `Context Engineering`
  - `RAG & Context`
  - `Agent Memory`
- `Model Systems`
  - `Inference & Serving`
  - `Model Releases`
- `AI Knowledge Systems`
  - `Obsidian & PKM`
- `ML Research`
  - `Research Digest`
  - `Applied ML`
- `AI Product & Strategy`
  - `Monetization & GTM`
- `AI Productivity`
  - `Workflows & Execution`
- `AI Career & Mindset`
  - `Performance & Habits`

Guidance:

- Choose category from core technical subject first.
- Use business/career categories only when content is clearly non-technical.

## index.md Contract

`/x-posts/index.md` Dataview must continue to work with `subCategory`:

```dataview
TABLE
  author,
  category,
  subCategory,
  type,
  date,
  read,
  likes
FROM "03_AI/x"
WHERE type
SORT category ASC, subCategory ASC, date DESC
```

If schema changes, update both note frontmatter and Dataview together.

## Skills to Use

When available in this environment:

- `obsidian-markdown`:
  - Any `.md` cleanup, frontmatter normalization, wikilinks/callouts, heading cleanup.
- `defuddle`:
  - When ingesting/cleaning content from URLs before summarizing into notes.
- `obsidian-cli`:
  - Vault operations, note search, and Obsidian automation tasks.

Use `obsidian-markdown` by default for this directory.

## Validation Checklist (Before Finishing)

- No note in `x-test/` (except `index.md`) is missing `category` or `subCategory`.
- No note uses `sub-category`.
- No malformed frontmatter keys.
- No broken/truncated title placeholders.
- `index.md` Dataview parses without errors.
