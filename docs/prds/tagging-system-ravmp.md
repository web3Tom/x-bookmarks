---
description: Rafactor of tagging systemn
created: 2026-06-02
---

# Overview

I want to revise our approach to tagging - so below are some opinions from leading experts.

## The New System

The taxonomy we have fails because it attempts to force a strict, hierarchical tree structure onto a domain that is inherently a graph. In an ecosystem moving as fast as AI engineering, concepts do not exist in isolated buckets; they are highly relational.

When you categorize a piece on a "Hermes agent," forcing it into `Agent Harnesses` strips it of its connection to `Coding Agents` or `Agent Infrastructure`. Furthermore, your current setup creates massive redundancy between your subcategories and your `concept` entity tags (e.g., having "RAG & Retrieval" as a subcategory while having "rag" as a concept tag).

To fix this, you need an ontology that separates **Intent (Why am I saving this?)** from **Mechanics (How does it work?)** and **Entities (What tools are involved?)**.

Here is a proposed, refactored taxonomy designed for a highly connected knowledge vault.

---

### The Proposed Architecture: Faceted Classification

Instead of nested subcategories, use a flattened approach consisting of three distinct layers in your frontmatter: **Pillars**, **Mechanics**, and **Entities**.

#### 1. Pillars (The High-Level Domain)

Replace your 7 rigid categories with 4 broad, mutually exclusive Pillars. A Pillar describes the _primary lens_ through which the article is viewed. An article should ideally have one Pillar, occasionally two.

- **Theory & Architecture:** System design, ML research, cognitive architectures, ontology, and PKM methodologies. (Focus: _How things should work conceptually._)
- **Applied Engineering:** Building agentic microservices, prompt engineering, coding workflows, terminal environments, and integrations. (Focus: _Writing the code and building the harnesses._)
- **Operations & Evals:** Observability, infrastructure provisioning, serving endpoints, security, and testing. (Focus: _Deploying, measuring, and protecting the systems._)
- **Strategy & Synthesis:** Go-to-market, career roadmaps, market analysis, mindset, and performance. (Focus: _The human, business, and market elements._)

#### 2. Entities (The "Nouns")

Your current `entity_tags` system is excellent. Keep it exactly as it is. It effectively captures the exact models (DeepSeek, Claude), frameworks (LangGraph), harnesses (Hermes, Droid), and tools (Obsidian, Codex, Gemini) referenced in the text.

#### 3. Mechanics (The "Verbs & Concepts")

This is the critical change. **Abolish all subcategories.** Instead, merge them into your existing `concept` list to create a unified `mechanics` or `capabilities` pool.

Concepts like `rag`, `persistent-memory`, `context-engineering`, and `knowledge-graph` are mechanics. When an article discusses an agent doing RAG with persistent memory, you simply tag those mechanics. You no longer have to agonize over whether the article "belongs" in a Memory folder or a Retrieval folder.

---

### Why This Solution is Better

1. **Eliminates Categorization Friction:** You no longer waste cognitive load deciding if an article on a multi-agent framework belongs in `Agentic Systems` or `Development & Tooling`. It gets the **Applied Engineering** Pillar, the `multi-agent` Mechanic, and the `crewai` Entity tag.
2. **Powers Graph-Based Queries:** In a Zettelkasten-style environment, this structure allows for powerful, multidimensional queries. You can easily query your vault for all notes intersecting `Pillar: Applied Engineering` + `Mechanic: context-engineering` + `Entity: claude-sonnet`.
3. **Future-Proofs the Vault:** When a new paradigm drops next month, you don't need to restructure your entire category tree. You simply add a new `mechanic` or `entity` tag. The four core Pillars will remain stable.

### Frontmatter Comparison

Here is how an article detailing a new Hermes agent setup with persistent memory would look under both systems.

**The Old, Rigid Way:**

```yaml
category: Agentic Systems # Wait, is it Development & Tooling?
subcategory: Agent Harnesses # But it also covers Agent Memory...
entity_tags:
  harness: [hermes]
  concept: [persistent-memory] # Redundant with subcategories
```

**The New, Relational Way:**

```yaml
pillar: Applied Engineering
entity_tags:
  harness: [hermes]
  model: [gemini, claude-sonnet]
  tool: [mcp]
mechanics:
  - agent-harness
  - persistent-memory
  - context-engineering
```

This decoupled approach ensures your knowledge intake aligns with how these systems are actually architected in reality—as interlocking components rather than isolated academic disciplines.

## The Handover

You can salvage practically the entire structure. Shifting your 600+ files into this new schema for Phase 4 of the vault refactor is just a matter of remapping your existing variables, not destroying them.

### 1. Entity Tags (100% Transferrable)

Your entire `entity_tags` object (`framework`, `harness`, `model`, `provider`, `tool`) remains completely untouched. They are already perfect for faceted search and graph linking.

### 2. Subcategories to Mechanics (100% Transferrable)

You won't lose a single concept. Every item in your previous subcategory list simply migrates into the new flattened `mechanics` list. The terminology stays; only the restrictive nesting is removed.

### 3. Categories to Pillars (Requires Translation)

This is the only piece that requires a logic shift. The 7 old categories need to be mapped to the 4 new Pillars. A simple mapping logic can handle this during migration:

| Old Category            | Primary Target Pillar |
| ----------------------- | --------------------- |
| `Agentic Systems`       | Applied Engineering   |
| `Development & Tooling` | Applied Engineering   |
| `Models & Inference`    | Theory & Architecture |
| `Strategy & Ontology`   | Strategy & Synthesis  |
| `Execution & Career`    | Strategy & Synthesis  |
| `Security & Privacy`    | Operations & Evals    |
| `Society & Commentary`  | Strategy & Synthesis  |

---

### Execution Strategy

To handle this programmatically without opening hundreds of notes manually, a Python script using a library like `python-frontmatter` is the most efficient route. The script would iterate through your markdown files, read the YAML, copy `entity_tags` directly, move the `subcategory` string into the `mechanics` array, and apply the dictionary mapping above to convert the `category` to a `pillar`.

---

## Subcategory Conversion: Curated Mapping

A literal 1:1 slugified transfer is a mistake. It imports the architectural debt of your old taxonomy directly into the new one.

When executing a structural overhaul across a vault containing over 600 files, the goal of this fourth phase should be deduplication and consolidation, not just renaming variables.

If you run a blind 1:1 transfer, you will immediately create redundant mechanic tags because your old subcategories heavily overlap with your existing `concept` entity tags. For example, an article currently has the subcategory `RAG & Retrieval` and the concept tag `rag`. A blind script would output `mechanics: [rag-and-retrieval, rag]`. This pollutes the graph and defeats the purpose of the refactor.

### The Solution: A Curated Consolidation Dictionary

Instead of a direct transfer, you should define a mapping dictionary within your migration script. The script should read the old `subcategory`, map it to one or more standardized `mechanics`, merge those with the existing `concept` tags, and then deduplicate the final array.

Here is a recommended curation mapping that resolves the redundancies between your previous subcategories and concepts:

#### 1. Consolidate Redundant Pairs (Map to Existing Concepts)

These subcategories should map directly to your established concept tags, dropping the academic labels.

| Old Subcategory                | Curated Mechanic                           |
| ------------------------------ | ------------------------------------------ |
| `RAG & Retrieval`              | `rag`                                      |
| `Agent Memory & Context`       | `persistent-memory`, `context-engineering` |
| `Prompt & Context Engineering` | `context-engineering`                      |
| `Multi-Agent Systems`          | `multi-agent`                              |
| `Agent Harnesses`              | `harness-engineering`                      |
| `AI-Augmented Vaults`          | `second-brain`                             |
| `Knowledge Graphs & Ontology`  | `knowledge-graph`                          |

#### 2. Standardize Standalone Subcategories

These subcategories represent valid mechanics but should be normalized into cleaner, hyphenated slugs.

| Old Subcategory              | Curated Mechanic                               |
| ---------------------------- | ---------------------------------------------- |
| `Coding Agents`              | `coding-agent` (pairs well with `vibe-coding`) |
| `Evals & Observability`      | `evals`                                        |
| `Model Routing`              | `model-routing`                                |
| `Serving & Endpoints`        | `inference-serving`                            |
| `Dev Environment & Terminal` | `local-dev-env`                                |
| `MCP & Integrations`         | `mcp-integration`                              |

#### 3. Deprecate "Bucket" Subcategories

Some subcategories are too broad to be mechanics. They represent the _Pillar_ itself rather than a specific capability. These should be dropped entirely during the migration, relying on the Pillar assignment and Entity tags to do the heavy lifting.

- `Agent Infrastructure` (Too vague; let the tags define if it's `evals`, `serving`, or `harness-engineering`)
- `Agent Skills` (Redundant; the specific tools/APIs are captured in Entity tags)
- `Foundation Models` (Redundant; the specific models are captured in `model: [claude-opus]`)

### Execution Logic

Your Python migration script should follow this logical flow:

1. Parse the YAML frontmatter.
2. Determine the `pillar` based on the old `category`.
3. Extract the old `subcategory` and pass it through the mapping dictionary to get the `curated_mechanics` array.
4. Extract the existing `concept` array.
5. Combine `curated_mechanics` and `concept` arrays into a single `mechanics` list.
6. Deduplicate the `mechanics` list (e.g., `list(set(mechanics))`).
7. Delete the old `category`, `subcategory`, and `concept` keys.
8. Write the new frontmatter back to the markdown file.

How are you currently handling the extraction and rewriting of YAML frontmatter in your Python environment—are you using `python-frontmatter`, or rolling a custom regex parser?
