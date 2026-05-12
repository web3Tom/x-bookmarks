# x-bookmarks Changelog

Reverse-chronological log of session-level outcomes for this repository.
Newest entry at the top. Long-form reasoning lives in the author's external spec system, not here.

## 2026-05-11

**`pass` vault fallback for `ANTHROPIC_API_KEY`**

- `src/config.py` now resolves `ANTHROPIC_API_KEY` from the user's `pass` store at `ai/anthropic/api-key` when the environment variable is unset or empty after `load_dotenv`.
- Fallback is gated on `pass` being on `PATH`; missing binary or missing entry returns an empty string and lets the existing "missing required env vars" error fire normally.
- Closes the gap where a `.env` (or `.envrc.local`) with an empty `ANTHROPIC_API_KEY=` would override a shell-exported value loaded via direnv.

**Pipeline log clarity**

- `src/main.py` article-count line now reports `{articles} of {novel} new bookmark(s) link to articles ({with_content} with content from API)` instead of the prior `Found {articles} article(s)` phrasing. Makes the article-vs-bookmark ratio explicit in run logs.

## 2026-05-09

**Transition to Secure Secret Management**

- Migrated from hardcoded `.env` to a `direnv` + `pass` workflow.
- Implemented a "smart" `.envrc` that supports `.envrc.local` for private, secure overrides.
- Updated `.gitignore` to protect `.envrc.local`.
- Updated `AGENTS.md` to codify the new Secret Management standards.
- Removed hardcoded API keys from local `.env`.

## 2026-04-21

**Roadmap restructure and protocol adoption**

- Reorganized `docs/roadmap.md` Planned section into five priority tiers. Order: `#14 → #10 → #1` (Tier 1) → `#15 → #6 → #2` (Tier 2) → `#3 → #4 → #5` (Tier 3) → `#11 → #7 → #13` (Tier 4) → `#8 → #9 → #12` (Tier 5). Rationale captured in the roadmap's Priority Rationale block.
- Validated backlog: all 15 planned items are live as open GitHub issues `#1`–`#15` on `web3Tom/x-bookmarks`; no drift between docs and tracker.
- Adopted `docs/CHANGELOG.md` (this file) and added a Roadmap & Change-Log Conventions section to `AGENTS.md`.
- Confirmed `main` in sync with `origin/main`.

**Pipeline run (`6b296cf26734`)**

- Fetched 99 bookmarks in one page (X API pagination bug capped return).
- 58 already saved, 41 new notes written in 46.6s.
- Claude token usage: 19,782 in / 2,366 out, single call.
- No 401 token refresh triggered; `.env` credentials still valid.

**Public/private audit**

- Untracked `docs/public-release-plan.md` and `docs/public-release-audit.md` (kept local). Internal planning artifacts; not intended for public consumption.
- Added a Pre-Commit Privacy Review directive in `AGENTS.md` requiring a public/private check of every staged file before commit, with an explicit untrack recipe.
- Pruned broken Project Docs links from `README.md` and added a pointer to `docs/CHANGELOG.md`.
- Caveat: past commits on the public GitHub repo still contain the now-untracked files. Decision: **accept the historical leak** — content is internal planning, not secrets; no history rewrite or force-push. Going forward, `.gitignore` + the pre-commit privacy directive prevent recurrence.
