---
# Taxonomy Override File for x-bookmarks
#
# This is an example of a domain-specific taxonomy override. Copy and edit to taste,
# or read it as a worked example of how a mature override file looks.
#
# FORMAT (all keys optional):
# -------
#   pillars:      List of custom pillar names (replaces the 4 neutral defaults)
#   mechanics:    Controlled vocabulary of categorization mechanics (flat list of dashed slugs)
#   entity_tags:  Dict mapping facet prefixes to known entities. Claude tags specific
#                 tools, frameworks, models as `prefix/entity` (e.g. `tool/docker`).
#                 Prefixes are CLOSED (only these 4 keys allowed); entities are OPEN.
#   deprecate:    List of pillar/mechanic values to steer Claude away from.
#
# Note: the override file's pillars, mechanics, and entity_tags REPLACE the neutral
# defaults when you provide them. Fields you omit fall back to the neutral defaults.
# The tool does not read your existing vault notes to build the taxonomy.
# ---

pillars:
  - Applied Practice
  - Theory & Concepts
  - Operations
  - Strategy

mechanics:
  - tutorials
  - automation
  - design-patterns
  - case-studies
  - performance-optimization
  - data-pipelines
  - testing-strategies
  - integration-workflows
  - debugging-techniques
  - architecture
  - best-practices
  - troubleshooting
  - frameworks-overview
  - workflow-comparison
  - ecosystem-tools
  - note-taking
  - knowledge-management
  - ai-systems

# Allowed prefixes: framework, harness, model, tool (closed set)
# Claude may discover new entities under each prefix (open vocabulary)
entity_tags:
  framework:
    - react
    - langgraph
    - langchain
    - flask
    - fastapi
    - django
  harness:
    - vscode
    - cursor
  model:
    - gpt
    - claude
    - llama
    - deepseek
  tool:
    - docker
    - git
    - obsidian
    - tmux
    - graphql

# Legacy / ad-hoc mechanics this taxonomy replaced — keep Claude from recreating them.
deprecate:
  - general
  - uncategorized
  - misc
---

## Domain Guidance

**Pillars** capture the mode of thinking required:
- **Applied Practice:** Hands-on implementation, workflows, tutorials, code examples, how-to guides
- **Theory & Concepts:** Foundational ideas, research papers, conceptual frameworks, why things work
- **Operations:** Deployment, monitoring, security, scaling, reliability, maintaining systems
- **Strategy:** Business models, market analysis, career decisions, organizational dynamics

**Mechanics** are the specific techniques, concepts, or activities described:
- Use `tutorials` for step-by-step guides, walkthroughs, or how-to posts
- Use `automation` for scripting, workflows, or efficiency patterns
- Use `performance-optimization` for speed, cost, token-usage improvements
- Use `data-pipelines` for ETL, data processing, streaming workflows
- Use `testing-strategies` for test methodology, QA approaches
- Use `design-patterns` for architectural or software design principles
- Use `best-practices` for conventions, standards, or recommended approaches
- Use `case-studies` for real-world examples, failures, or post-mortems
- Combine mechanics freely (one post can have 2–5 mechanics)

**Entity tags** are specific tools, frameworks, models, or products named in the post:
- **framework:** Web frameworks, libraries you import, orchestration SDKs (react, langgraph, fastapi)
- **harness:** Development environments or end-user platforms (vscode, cursor)
- **model:** LLM names, specific model checkpoints (gpt, claude, llama, deepseek)
- **tool:** Standalone CLI tools, utilities, infrastructure services (docker, git, obsidian, tmux)

### Worked Examples

- A Docker + Kubernetes deployment guide → **Applied Practice + Operations**, mechanics `[tutorials, automation]`, tags `["tool/docker"]`
- A research paper on transformer attention → **Theory & Concepts**, mechanics `[design-patterns]`, tags `["model/llama"]`
- A performance tuning case study using Claude API → **Applied Practice**, mechanics `[case-studies, performance-optimization]`, tags `["model/claude", "tool/obsidian"]`
- A testing methodology for data pipelines → **Applied Practice + Operations**, mechanics `[data-pipelines, testing-strategies]`, tags `["framework/fastapi"]`

### Disambiguation Notes

- **Tutorial vs. Case Study:** a step-by-step guide → `tutorials`; a real-world outcome (success or failure analysis) → `case-studies`
- **Framework vs. Tool:** a library you import (React, LangGraph, FastAPI) → `framework`; a standalone binary (Docker, Git, Obsidian) → `tool`
- **Theory vs. Applied:** a research paper or conceptual deep-dive → **Theory & Concepts**; implementation guidance → **Applied Practice**
- No catch-all pillar. Always pick the nearest fit; if unsure, pick **Applied Practice**
