# Taxonomy Customization Guide

## Overview

The x-bookmarks tool categorizes bookmarks into `category` and `subCategory` fields using Claude. By default, it uses a **neutral, domain-agnostic taxonomy** that works for any user. However, you can customize the taxonomy by:

1. **Merging with an override file** — provide additional categories
2. **Specifying deprecations** — mark categories to avoid
3. **Adding domain guidance** — provide rules for your specific use case

This guide explains how to set up and use taxonomy overrides.

> **A complete, real-world override** lives at [`taxonomy.example.md`](../taxonomy.example.md) (repo root) — the maintainer's in-production AI/engineering taxonomy: 7 domains, 43 disciplines, `entity_tags` seeds drawn from actual usage, and a `deprecate:` list of the legacy labels it replaced. Copy it as a starting point. The shipped `DEFAULT_TAXONOMY` below stays domain-neutral regardless.

## Three Sources of Taxonomy

When categorizing a bookmark, x-bookmarks considers three sources in this order:

1. **Vault taxonomy** — existing categories in your saved notes (extracted from frontmatter)
2. **Override file** — custom categories you define (optional, via `X_BOOKMARKS_TAXONOMY_FILE`)
3. **DEFAULT_TAXONOMY** — fallback categories used when vault and override are both empty

### Precedence: Union Semantics

The vault and override taxonomies are **merged using union semantics**:
- Every category in the vault is available
- Every category in the override is added to the result
- Subcategories are combined (not replaced)

This means the override file **expands** the available taxonomy, rather than replacing it.

**Example:**

Vault contains: `Agentic Systems` → `[Agent Harnesses, Multi-Agent Systems]`
Override contains: `Agentic Systems` → `[RAG & Retrieval]`
Result: `Agentic Systems` → `[Agent Harnesses, Multi-Agent Systems, RAG & Retrieval]`

## Default Taxonomy

If both your vault and override file are empty, Claude uses this neutral taxonomy:

```
Technology
  - Software Development
  - Hardware
  - Infrastructure & DevOps
  - Data & Analytics

Business & Finance
  - Markets & Investing
  - Entrepreneurship
  - Career

Science & Research
  - Research & Papers
  - Engineering
  - Environment

Health & Wellness
  - Fitness
  - Nutrition
  - Mental Health

Learning & Education
  - Tutorials & Guides
  - Books
  - Courses

Culture & Society
  - Arts & Media
  - Politics & Policy
  - History

Productivity & Tools
  - Workflows
  - Apps & Utilities
  - Automation
```

## Override File Format

An override file is a Markdown file with YAML frontmatter. Set its path via the `X_BOOKMARKS_TAXONOMY_FILE` environment variable.

### Frontmatter Keys

#### `taxonomy` (optional)

A YAML dict mapping category names to lists of subcategories:

```yaml
---
taxonomy:
  Development & Tooling:
    - Coding Workflows
    - Coding Agents
    - Prompt & Context Engineering
  Strategy & Ontology:
    - Startups & Business Models
    - Monetization & Income
---
```

Categories and subcategories from the override are **added** to your vault taxonomy (union merge).

#### `deprecate` (optional)

A YAML list of category or "Category/Subcategory" strings to avoid:

```yaml
---
deprecate:
  - General
  - Uncategorized
  - "Miscellaneous/Other"
---
```

Claude will **never assign or create** these categories. Useful for preventing clutter.

#### `entity_tags` (optional)

A YAML dict mapping entity tag prefixes to lists of known entities. Claude uses these as a reference for tagging specific tools, frameworks, models, etc. in the text:

```yaml
---
entity_tags:
  framework:
    - langgraph
    - autogen
    - crewai
  model:
    - deepseek
    - claude
    - llama3
  tool:
    - docker
    - obsidian
---
```

- **Only active if non-empty.** If `entity_tags` is absent or empty, Claude will not extract tags, and the `tags:` frontmatter field will be omitted from generated notes.
- **Prefix governance:** Claude can invent new entities under known prefixes (e.g., `model/gpt-4o` if `model` is a prefix), but any tag whose prefix is not in the configured set is dropped during normalization.
- **Format:** Tags are written to frontmatter as a YAML flow array, e.g., `tags: ["model/deepseek", "tool/docker"]`.

#### Body (optional)

After the closing `---`, you can add domain-specific guidance as Markdown. This text is appended to Claude's system prompt under "Domain guidance:":

```yaml
---
taxonomy: {...}
entity_tags: {...}
deprecate: [...]
---

## Domain Guidance

When categorizing a bookmark:
- Prefer AI-related categories for technical content
- Use Entrepreneurship for startup-related posts
- Group similar topics under existing categories when possible
```

## Entity Tags

Entity tags are a lateral tagging layer on top of the hierarchical Category/Subcategory taxonomy. They capture specific entities (tools, frameworks, models, concepts) mentioned in a bookmark's text.

### Format

Tags use the format `prefix/entity-name`, where:
- `prefix` is one of the allowed prefixes (keys in `entity_tags` dict)
- `entity-name` is slugified (lowercase, spaces/underscores → dashes, invalid chars removed)

Examples:
- `framework/langgraph`
- `model/deepseek-v2`
- `tool/docker-compose`

### When Tags Appear

Tags **only appear** when:
1. You configure `entity_tags` in the override file (non-empty dict), AND
2. Claude identifies relevant entities in the bookmark text

If `entity_tags` is absent or empty, no tags are requested in the Claude prompt, and the `tags:` field is omitted from generated frontmatter.

### Closed Prefixes, Open Entities

- **Prefixes are closed:** Only prefixes in your configured `entity_tags` dict are allowed
- **Entities are open:** Claude can invent new entities under those prefixes (e.g., discovering `model/granite` even if your config only lists `model: [deepseek, llama3]`)
- **Unknown prefixes are dropped:** If Claude returns `unknown_prefix/entity`, it is silently discarded

## Configuration

### Setting the Override File Path

#### Option 1: Environment Variable

```bash
export X_BOOKMARKS_TAXONOMY_FILE=/path/to/your/taxonomy.md
uv run x-bookmarks
```

#### Option 2: `.envrc.local` (direnv)

```bash
export X_BOOKMARKS_TAXONOMY_FILE=/path/to/your/taxonomy.md
```

The x-bookmarks tool reads simple `export KEY=value` entries from `.envrc.local` if the environment variable is not set.

#### Option 3: CLI Flag (migrate only)

```bash
uv run x-bookmarks-migrate /path/to/bookmarks --taxonomy-file /path/to/taxonomy.md
```

### Path Resolution

The tool expands `~` and resolves to absolute paths. If the file does not exist, a warning is logged and the tool continues without an override (falling back to vault + DEFAULT_TAXONOMY).

## Examples

### Example 1: Cold Start (No Vault)

You're starting fresh with no saved bookmarks. You want to use a custom taxonomy:

**taxonomy.md:**
```yaml
---
taxonomy:
  Technology:
    - Web Development
    - DevOps
    - AI & ML
  Business:
    - Startups
    - Finance
    - Marketing
deprecate:
  - General
---

## Domain Guidance

Prefer Technology categories for developer-focused content.
Use Business for founder/investor posts.
```

**Result:** Claude uses your 6 categories (3 Technology + 3 Business) plus deprecation rules.

### Example 2: Expanding Existing Vault

You have a vault with `Agentic Systems`, `Models & Inference`, and `Strategy & Ontology`. You want to add new subcategories:

**taxonomy.md:**
```yaml
---
taxonomy:
  Models & Inference:
    - Fine-tuning
    - Evaluation
  Strategy & Ontology:
    - Fundraising
---
```

**Result:** Your vault categories are preserved and expanded:
- `Models & Inference` gains `Fine-tuning` and `Evaluation` alongside its existing subcategories
- `Strategy & Ontology` gains `Fundraising`
- All other vault categories remain unchanged

### Example 3: Deprecating Unwanted Categories

After some months, you notice Claude created a `Miscellaneous` category you don't like. Add it to deprecations:

**taxonomy.md:**
```yaml
---
deprecate:
  - Miscellaneous
  - Uncategorized
---
```

**Result:** Going forward, Claude will not use these categories, forcing cleaner categorization.

## Edge Cases

### Malformed YAML

If the override file has invalid YAML, a warning is logged and the file is skipped. The tool continues with vault + DEFAULT_TAXONOMY.

### Missing File

If `X_BOOKMARKS_TAXONOMY_FILE` points to a nonexistent file, a warning is logged and the file is skipped.

### Empty `taxonomy:` Key

If the override file has an empty `taxonomy:` dict, it contributes nothing (union of empty set is the vault).

### Non-Dict `taxonomy:` Value

If `taxonomy:` is a list or scalar, it is ignored with a warning.

## Performance Notes

### Token Budget

The taxonomy block and guidance text are included in the Claude API prompt. Keep guidance text concise (under 1000 characters recommended) to control token usage:

- Each category/subcategory pair costs ~10 tokens
- Guidance text costs ~0.3 tokens per character
- For a 20-category taxonomy + 500-char guidance: ~200-250 tokens

Monitor token usage in run history (`.x-bookmarks-history.jsonl`) to see the impact.

### Vault Scanning

Each sync reads your vault files to extract existing categories. If you have thousands of bookmarks, this can be slow. The read is a one-time cost per run.

## Migration and Overrides

The `x-bookmarks-migrate` command also accepts a `--taxonomy-file` flag:

```bash
uv run x-bookmarks-migrate /path/to/bookmarks --taxonomy-file /path/to/taxonomy.md
```

This allows you to apply custom categorization rules when backfilling old notes. No X API credentials are required for migration (only an Anthropic API key).

## Troubleshooting

### Claude Still Creates "General" or "Uncategorized"

This can happen if:
1. No override file is set (`X_BOOKMARKS_TAXONOMY_FILE` unset)
2. Your vault is empty
3. The DEFAULT_TAXONOMY is being used

**Solution:** Create an override file with a `deprecate:` list including these terms.

### My Override Categories Aren't Being Used

Check:
1. File path is correct and file exists
2. YAML frontmatter syntax is valid (run `yaml` parser locally if unsure)
3. `taxonomy:` key is present and is a dict
4. Vault categories are being merged in (try running with `--verbose`)

### Vault Categories Are Not Appearing in Prompts

This is expected if vault files use different field names or format. The tool extracts categories from:
- `category:` field (case-sensitive, quoted)
- `subCategory:` field (camelCase, quoted)

If your vault uses different names (e.g., `topic:` instead of `category:`), the tool will not find them.
