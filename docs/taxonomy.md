# Taxonomy Customization Guide

## Overview

The x-bookmarks tool categorizes bookmarks using a **faceted schema**: `pillar` (the strategic mode), `mechanics` (the techniques/activities involved), and `entity_tags` (specific tools/frameworks/models mentioned). By default, it uses **neutral, domain-agnostic pillars and mechanics** that work for any user. However, you can customize the taxonomy by:

1. **Defining custom pillars** — replace the 4 neutral default pillars
2. **Controlling the mechanics vocabulary** — specify techniques and concepts Claude can use
3. **Seeding entity tag entities** — provide known tools, frameworks, models as reference
4. **Specifying deprecations** — mark values to avoid
5. **Adding domain guidance** — provide rules for your specific use case

This guide explains how to set up and use taxonomy overrides.

> **A complete, worked example** lives at [`taxonomy.example.md`](../taxonomy.example.md) (repo root) — an example override with custom pillars, mechanics, entity tag prefixes, and domain guidance. Copy it as a starting point. The shipped `DEFAULT_PILLARS` and `DEFAULT_MECHANICS` below are always available as fallback.

## How Taxonomy Resolution Works

When categorizing a bookmark, x-bookmarks resolves the available taxonomy as follows:

- **Pillars**: If you provide an override file with a `pillars:` key, those pillars are used. Otherwise, the tool uses the neutral `DEFAULT_PILLARS`. The tool does **not** read your existing vault notes to discover pillars.
- **Mechanics**: If you provide an override file with a `mechanics:` key, that vocabulary is used. Otherwise, the tool uses `DEFAULT_MECHANICS` (empty). Claude can still invent new mechanics when none fit the seed.
- **Entity tags**: If you provide an override file with an `entity_tags:` key, those prefixes and entities are used. Otherwise, entity tags are disabled (empty dict). The tool does **not** read your vault notes for entity tags.
- **Deprecations & Guidance**: Only loaded from the override file, if present.

**Key difference from earlier versions:** The tool **does not** read your existing vault notes to build the taxonomy. The override file's values **replace** the neutral defaults; values you omit fall back to the neutral defaults.

## Default Taxonomy

If you do not provide an override file, Claude uses these neutral defaults:

**Default Pillars:**
- Theory & Concepts
- Applied Practice
- Operations
- Strategy

**Default Mechanics:** (empty list — Claude applies its own judgment when no seed vocabulary is provided)

---

## Override File Format

An override file is a Markdown file with YAML frontmatter. Set its path via the `X_BOOKMARKS_TAXONOMY_FILE` environment variable.

### Frontmatter Keys

#### `pillars` (optional)

A YAML list of custom pillar names to use instead of the 4 neutral defaults:

```yaml
---
pillars:
  - Research & Learning
  - Product Development
  - Operations & Scale
  - Vision & Strategy
---
```

If you provide `pillars:`, only those values are available for categorization. If you omit `pillars:`, the neutral `DEFAULT_PILLARS` are used. There is no merging with other sources.

#### `mechanics` (optional)

A YAML list of categorization mechanics — lowercase-dashed slugs representing techniques, concepts, or activities:

```yaml
---
mechanics:
  - tutorials
  - automation
  - performance-optimization
  - case-studies
  - debugging-techniques
---
```

Mechanics are **flat** (no hierarchy). If you provide `mechanics:`, Claude uses that vocabulary and can invent new mechanics beyond the seed when appropriate. If you omit `mechanics:`, Claude uses an empty vocabulary and invents mechanics as needed. Mechanics are stored in frontmatter as a YAML list:

```yaml
mechanics:
  - tutorials
  - automation
```

#### `entity_tags` (optional)

A YAML dict mapping **closed-set prefixes** to lists of known entities. Claude uses these as reference values for tagging specific tools, frameworks, models, etc. in the text:

```yaml
---
entity_tags:
  framework:
    - react
    - fastapi
    - langgraph
  model:
    - claude
    - gpt
    - llama
  tool:
    - docker
    - obsidian
---
```

**Allowed prefixes** (closed set — only these 4):
- `framework` — libraries, SDKs, and frameworks you import (React, LangGraph, FastAPI)
- `harness` — development platforms, interactive notebooks (VSCode, Cursor, Jupyter)
- `model` — LLM names and specific model checkpoints (gpt, claude, llama, deepseek)
- `tool` — standalone CLI tools, utilities, infrastructure (Docker, Git, Obsidian, tmux)

The `provider` and `concept` prefixes from older schemas were **dropped**. Concepts are now folded into `mechanics`.

**Gating:** Entity tags **only appear** when:
1. You configure a non-empty `entity_tags` dict in the override, AND
2. Claude identifies relevant entities in the bookmark text

If you omit `entity_tags:` or provide an empty dict, no entity tags are requested and the `entity_tags:` field is omitted from generated frontmatter.

**Open Vocabulary:** Claude can invent new entities under known prefixes (e.g., discovering `tool/graphql` even if your config only lists `tool: [docker, obsidian]`). Unknown-prefix tags are dropped during normalization.

#### `deprecate` (optional)

A YAML list of pillar or mechanic values to avoid:

```yaml
---
deprecate:
  - General
  - Uncategorized
  - Legacy
---
```

Claude will **never assign or create** these values. Useful for preventing clutter from abandoned categories.

#### Body (optional)

After the closing `---`, you can add domain-specific guidance as Markdown. This text is appended to Claude's system prompt under "Domain guidance:":

```yaml
---
pillars: [...]
mechanics: [...]
entity_tags: {...}
deprecate: [...]
---

## Domain Guidance

When categorizing a bookmark:
- Prefer **Applied Practice** for hands-on implementation posts
- Use **Theory & Concepts** for research or conceptual deep-dives
- Always tag known frameworks with their framework/ prefix
```

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

The tool expands `~` and resolves to absolute paths. If the file does not exist, a warning is logged and the tool continues with the neutral defaults.

## Examples

### Example 1: Cold Start (No Vault)

You're starting fresh with no saved bookmarks. You want to use custom pillars and a controlled mechanics vocabulary:

**taxonomy.md:**
```yaml
---
pillars:
  - Learning
  - Implementation
  - Scaling
  - Strategy

mechanics:
  - tutorials
  - case-studies
  - performance-optimization
  - architecture
  - debugging

deprecate:
  - General
---

## Domain Guidance

Prefer Implementation pillar for hands-on code and workflow posts.
Use Learning for research and conceptual content.
Use Scaling for operations and deployment guidance.
```

**Result:** Claude uses your custom pillars + mechanics + deprecation rules. Any generated notes will use only these pillars and mechanics.

### Example 2: Using Neutral Defaults

You want to start with the built-in neutral pillars and mechanics:

**No override file needed.** Just leave `X_BOOKMARKS_TAXONOMY_FILE` unset.

**Result:** Claude uses `DEFAULT_PILLARS` (Theory & Concepts, Applied Practice, Operations, Strategy) and an empty mechanics vocabulary, inventing mechanics as needed.

### Example 3: Seeding Entity Tags

You want Claude to tag specific tools and frameworks in your bookmarks:

**taxonomy.md:**
```yaml
---
entity_tags:
  framework:
    - react
    - fastapi
  tool:
    - docker
    - obsidian
---
```

**Result:** When provided an override with `entity_tags:`, the tool uses only those prefixes and seed entities. Going forward, generated notes will include `entity_tags:` with values like `["framework/react", "tool/docker"]` when Claude identifies these entities in the text. The default pillars and mechanics are used (since they are not overridden).

### Example 4: Deprecating Unwanted Values

After some months, you notice Claude created pillars or mechanics you don't like. Add them to deprecations:

**taxonomy.md:**
```yaml
---
deprecate:
  - Miscellaneous
  - Uncategorized
  - rough-draft
---
```

**Result:** Going forward, Claude will not assign these values, forcing cleaner categorization. If you have not provided custom pillars or mechanics, the defaults are used alongside the deprecation rules.

## Edge Cases

### Malformed YAML

If the override file has invalid YAML, a warning is logged and the file is skipped. The tool continues with the neutral defaults.

### Missing File

If `X_BOOKMARKS_TAXONOMY_FILE` points to a nonexistent file, a warning is logged and the file is skipped. The tool continues with the neutral defaults.

### Empty Collections

If the override file has empty `pillars: []`, `mechanics: []`, or `entity_tags: {}`, those fields are treated as "not provided" and the corresponding neutral defaults are used instead.

### Non-Dict `entity_tags:` Value

If `entity_tags:` is a list or scalar, it is ignored with a warning. The tool falls back to no entity tags.

## Performance Notes

### Token Budget

The taxonomy block (pillars, mechanics, entity tags) and guidance text are included in the Claude API prompt. Keep guidance text concise (under 1000 characters recommended) to control token usage:

- Each pillar costs ~5 tokens
- Each mechanic costs ~3 tokens
- Each entity tag costs ~2 tokens
- Guidance text costs ~0.3 tokens per character
- For a 4-pillar + 15-mechanic + 20-entity-tag taxonomy + 500-char guidance: ~150-200 tokens

Monitor token usage in run history (`.x-bookmarks-history.jsonl`) to see the impact.

### No Vault Scanning

The tool does **not** scan your vault files during categorization. The taxonomy comes entirely from the override file (if provided) or the neutral defaults. This means categorization speed does not degrade with vault size.

## Migration and Overrides

The `x-bookmarks-migrate` command also accepts a `--taxonomy-file` flag:

```bash
uv run x-bookmarks-migrate /path/to/bookmarks --taxonomy-file /path/to/taxonomy.md
```

This allows you to apply custom categorization rules when backfilling old notes. No X API credentials are required for migration (only an Anthropic API key).

## Troubleshooting

### Generated Notes Still Use `category` and `subCategory`

The legacy `category` and `subCategory` fields have been replaced with the faceted `pillar` + `mechanics` + `entity_tags` schema. If you see old-style frontmatter, either:
1. Run the migration command on those files: `uv run x-bookmarks-migrate /path/to/x-posts --verbose`
2. Or use the override file to ensure new notes use the new schema

### My Override Isn't Being Used

Check:
1. File path is correct and file exists
2. YAML frontmatter syntax is valid (run a YAML parser locally if unsure)
3. At least one of `pillars:`, `mechanics:`, `entity_tags:`, or `deprecate:` is present and non-empty
4. The override file is being read (try running with `--verbose`)

### I Want My Old Vault Categories Back

If you had old `category`/`subCategory` notes and want to preserve that structure, you'll need to run the migration command with a custom `--taxonomy-file` that defines pillars matching your old categories. The override file cannot discover old vault frontmatter — you must explicitly provide the pillar list.

### Claude Creates Unwanted Mechanics

Add them to the `deprecate:` list in the override file to prevent future use.
