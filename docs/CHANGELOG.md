# x-bookmarks Changelog

Reverse-chronological log of session-level outcomes for this repository.
Newest entry at the top. Long-form reasoning lives in the author's external spec system, not here.

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
- Caveat: past commits on the public GitHub repo still contain the now-untracked files. Purging them from history requires `git filter-repo` or BFG + a force-push — deferred pending explicit user decision.
