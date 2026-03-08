## Purpose

This directory stores AI-focused bookmark notes (mostly X posts/articles) in Obsidian Markdown under `x-posts/`.

Primary goals:

- Keep notes readable and structured.
- Keep frontmatter consistent for Dataview.
- Classify content with deep AI subject categories.

## Directory Layout

- `x-posts/`: note files.

## File Naming

- Notes use a kebab-case slug of the LLM-generated title: `{title-slug}.md`
- Example: `mastering-prompt-engineering-fundamentals.md`
- Slugs are lowercase, max 80 chars, special chars removed, spaces/underscores become hyphens.
- Collisions get a `-2`, `-3` suffix.
- Keep one note per source post/article.

## Required Frontmatter Schema

Use this exact key set and casing:

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

- All string fields must be double-quoted.
- `subCategory` is camelCase (not `sub-category`).
- `title` must be human-readable, not truncated (`...`), and no raw URLs.
- `read` is an unquoted boolean (`true`/`false`).
- Deprecated fields (`author_name`, `tweet_id`, `likes`, `retweets`, `replies`, `bookmarks`, `has_media`, `has_links`) must not appear — run `x-bookmarks-migrate` to remove them.

## Body Structure

Preferred structure:

```md
## {title}

<cleaned content — blockquoted tweet text for posts, article body for articles>

## References

- 🔗 [Original tweet](...)
- 🌐 [Article](...)
```

Rules:

- The first `##` heading must match the frontmatter `title` exactly.
- Use `## References` for links.
- Post content is blockquoted (`> text`); article content is verbatim.
- Avoid giant unbroken text blocks when possible.

## Taxonomy Policy

Categories and subcategories are **dynamic** — they grow from the vault itself. The `x-bookmarks` pipeline reads all existing `category`/`subCategory` values from frontmatter at runtime and passes them to Claude as the preferred list.

Rules:

- **Prefer existing** categories and subcategories whenever a tweet fits one.
- **Extend** a category with a new subcategory when the category fits but no subcategory does.
- **Create** a new category + subcategory (both Title Case, 2-4 words) only when no existing category fits.
- **Never** use `"General"` or `"Uncategorized"` — every bookmark deserves a meaningful label.

Category names should reflect specific AI subject depth (e.g., `Agent Architectures`, `Context Engineering`), not generic buckets (e.g., `AI Engineering`, `Miscellaneous`).

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

- No note in `x-posts/` is missing `category` or `subCategory`.
- No note uses `sub-category`.
- No malformed frontmatter keys.
- No broken/truncated title placeholders.
