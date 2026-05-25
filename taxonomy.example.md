---
# Taxonomy Override File for x-bookmarks
#
# This is the maintainer's real, in-production AI/engineering taxonomy — the same
# scheme used to organize a ~615-note bookmark vault. Copy it and edit to taste, or
# read it as a worked example of how a mature override file looks.
#
# FORMAT:
# -------
#   taxonomy:    Dict mapping Category (Domain) -> list of subcategories (Disciplines)
#   entity_tags: Dict mapping facet prefixes to known entities. Claude tags specific
#                tools/frameworks/models/concepts as `prefix/entity` (e.g. `framework/langgraph`).
#                Prefixes are CLOSED (only these keys); entities are OPEN (Claude may add new ones).
#   deprecate:   List of categories to steer Claude away from (e.g. legacy/ad-hoc labels).
#
# Note: this override is MERGED (union) with whatever categories already exist in your
# vault. The shipped DEFAULT_TAXONOMY (used only when vault AND override are empty) stays
# domain-neutral and is unaffected by this file.
# ---

taxonomy:
  'Agentic Systems':
    - Agent Harnesses
    - Agent Design & Patterns
    - Multi-Agent Systems
    - Agent Memory & Context
    - RAG & Retrieval
    - Evals & Observability
    - Autonomous Agents
    - Agent Skills & Marketplaces
  'Development & Tooling':
    - Coding Workflows
    - Coding Agents
    - Prompt & Context Engineering
    - Agent Infrastructure
    - Agent Skills
    - Docs & Knowledge Tooling
    - MCP & Integrations
    - Dev Environment & Terminal
    - Testing & QA
    - Planning & Spec
  'Models & Inference':
    - Foundation Models
    - Serving & Endpoints
    - Model Routing
    - ML Research
    - Applied ML
  'Strategy & Ontology':
    - AI-Augmented Vaults
    - PKM Methodology
    - Capture & Ingestion
    - Personal AI Operating Systems
    - Knowledge Graphs & Ontology
    - Monetization & Income
    - AI Services & Agencies
    - Go-To-Market & Growth
    - Startups & Business Models
    - Market Analysis & Theses
  'Execution & Career':
    - Career Strategy
    - Skill-Building & Roadmaps
    - Mindset & Psychology
    - Engineering Judgment
    - Performance & Habits
  'Security & Privacy':
    - Privacy & Anonymity
    - Security Practices & Threats
    - Networking & Infrastructure
  'Society & Commentary':
    - Politics & Policy
    - Conspiracy & Fringe

# Known seeds only — Claude may discover new entities under each (closed) prefix.
entity_tags:
  framework:
    - langgraph
    - langchain
    - crewai
    - letta
    - mastra
    - autogen
  harness:
    - hermes
    - openclaw
    - pi
    - droid
    - flue
  model:
    - claude-opus
    - claude-sonnet
    - kimi-k2
    - deepseek
    - minimax
    - gpt
    - qwen3
    - gemini
  provider:
    - anthropic
    - openai
    - google
    - openrouter
    - nvidia
  tool:
    - claude-code
    - codex
    - obsidian
    - mcp
    - notebooklm
    - qmd
    - tmux
    - llama-cpp
  concept:
    - multi-agent
    - harness-engineering
    - context-engineering
    - rag
    - persistent-memory
    - prompt-caching
    - vibe-coding
    - second-brain
    - knowledge-graph
    - services-as-software

# Legacy / ad-hoc labels this taxonomy replaced — keep Claude from recreating them.
deprecate:
  - General
  - Uncategorized
  - Technology
  - 'Miscellaneous/Other'
  - Agent Architectures
  - AI Coding
  - Context Engineering
  - Model Systems
  - AI Productivity
  - Unrelated Content
---

## Domain Guidance

Category (Domain) + Subcategory (Discipline) capture _what the post is fundamentally about_.
Tags capture _the specific tools, frameworks, models, or concepts named in it_.

### Worked examples

- Hermes' layered memory architecture → **Agentic Systems / Agent Memory & Context**, tags `["harness/hermes", "concept/persistent-memory"]`
- A Claude Code workflow that cuts token usage 60% → **Development & Tooling / Prompt & Context Engineering**, tags `["tool/claude-code", "concept/token-optimization"]`
- Benchmarking DeepSeek via OpenRouter for cost → **Models & Inference / Model Routing**, tags `["model/deepseek", "provider/openrouter"]`
- Building a second brain in Obsidian with Claude Code → **Strategy & Ontology / AI-Augmented Vaults**, tags `["tool/obsidian", "tool/claude-code", "concept/second-brain"]`

### Disambiguation rules (the non-obvious calls)

- **Harness vs framework vs coding-agent:** a harness *product*/platform or harness-engineering essay → `Agentic Systems / Agent Harnesses`; a library you import to build agents (LangGraph, LangChain, an SDK) → `Development & Tooling / Coding Agents`; vendor-neutral architecture principles → `Agentic Systems / Agent Design & Patterns`.
- **Agent memory vs human PKM:** the *agent's* internal memory → `Agentic Systems / Agent Memory & Context`; a *human's* knowledge vault that merely uses an agent → `Strategy & Ontology / AI-Augmented Vaults`.
- **Inference substrate vs the model:** local inference, GPUs, quantization, inference chips → `Models & Inference / Serving & Endpoints`; a specific model's release/capabilities → `Foundation Models`; cost/use-case selection across models → `Model Routing`.
- **Off-topic content** (not AI/eng): politics/policy/sovereignty → `Society & Commentary / Politics & Policy`; conspiracy/pseudoscience/fringe → `Society & Commentary / Conspiracy & Fringe`.
- No catch-all. Never assign `General`, `Uncategorized`, or any deprecated label — pick the closest real discipline instead.
