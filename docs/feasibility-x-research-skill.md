# Feasibility: x-research-skill as a Free Bookmark-Retrieval Path

**Status:** Analysis — no adoption performed
**Date:** 2026-08-03
**Repo assessed:** [`rohunvora/x-research-skill`](https://github.com/rohunvora/x-research-skill) @ `623cca7` (2026-02-19)
**Audience:** Maintainers of `x-bookmarks`
**Related:** [`feasibility-graphql-vs-x-api.md`](feasibility-graphql-vs-x-api.md), [`feasibility-agent-reach.md`](feasibility-agent-reach.md), roadmap item `#17`

---

## 1. Bottom line up front

**x-research-skill is the opposite of what `#17` needs.** It is a well-built wrapper around the **official, paid** X API v2 — the exact cost path we are trying to remove.
It uses an app-level Bearer token against `https://api.x.com/2`, and its own README prices a single search page at roughly **$0.50**.

**It also cannot read bookmarks.** A bookmarks command was added and then reverted **116 seconds later**, and the repo's `HEAD` *is* that revert commit.

It is therefore a non-candidate for `#17` on both counts: wrong cost direction, missing capability.
It retains modest value as a reference for cost-transparency and rate-limit handling, and as a cautionary data point about the bookmarks endpoint.

---

## 2. What it is

A Bun/TypeScript CLI for researching recent X activity: search sorted by engagement, thread fetching, user profile lookup, single-tweet retrieval, and account watchlists.
Packaged as an agent skill (`SKILL.md` + scripts) rather than a library.

| Attribute | Value | Evidence |
|---|---|---|
| Language / runtime | TypeScript on Bun | `x-search.ts`, README |
| Size | 1,032 lines across 4 files | `x-search.ts` 444, `lib/api.ts` 322, `lib/format.ts` 157, `lib/cache.ts` 109 |
| Commits | 17 | `git rev-list --count HEAD` |
| Last commit | `623cca7`, 2026-02-19 — **the bookmarks revert** | `git log -1` |
| License | "MIT" declared at `README.md:222` under a `## License` heading | — |
| `LICENSE` file | **Absent** | repo root |
| `package.json` | **Absent** | repo root |
| Star count | **Not verified** — README embeds a star-history badge but the figure was not independently confirmed | — |

### License caveat

The only license statement is the bare word `MIT` on `README.md:222`.
There is no `LICENSE` file, no named copyright holder, and no warranty disclaimer.
That is a weaker grant than a standard MIT file. It is probably sufficient for borrowing ideas, but if we ever wanted to *vendor* code we should ask the author to add a proper `LICENSE` first rather than rely on a one-word README line.

---

## 3. How it accesses X — official, paid, app-level

`lib/api.ts:8`:

```typescript
const BASE = "https://api.x.com/2";
```

`lib/api.ts:140-144`:

```typescript
const token = getToken();
const res = await fetch(url, {
  headers: { Authorization: `Bearer ${token}` },
});
```

The token comes from `X_BEARER_TOKEN` (`lib/api.ts:13, 21, 26`).
This is an **app-level** Bearer token, not an OAuth 2.0 user-context token and not session cookies.

Endpoints used, all verified in `lib/api.ts`:

| Endpoint | Line | Purpose |
|---|---|---|
| `${BASE}/tweets/search/recent` | 197 | Search — **last 7 days only** |
| `${BASE}/tweets/${conversationId}` | 226 | Thread assembly via `conversation_id:` |
| `${BASE}/users/by/username/${username}` | 251 | User lookup |
| `${BASE}/tweets/${tweetId}` | 276 | Single tweet |

There is no private GraphQL, no `queryId` discovery, no feature-flag payload, and no cookie handling anywhere in the codebase.
On the ToS axis this is entirely clean — it is the sanctioned path, same as ours. It simply costs money.

---

## 4. Cost — the disqualifying axis

README `§`pricing (lines 148-157) documents X's February 2026 pay-per-use model with prepaid credits:

| Resource | Price |
|---|---|
| Post read | $0.005 |
| User lookup | $0.010 |
| Post create | $0.010 |
| **One search page (up to 100 posts)** | **~$0.50** |

The tool treats cost as a first-class UX concern — "every search shows what it cost" (README:13), a cost summary after results (README:103), and single-page fetching as "the biggest cost saver" (README:118).

That design is honest and well-executed, but it confirms the verdict: this project's answer to "the X API costs money" is *make the cost visible and minimize it*, not *eliminate it*.
`#17`'s goal is elimination. x-research-skill does not advance it.

---

## 5. The bookmarks revert

The most informative finding in the repo, verified directly from git history:

```
67f5f9e  2026-02-19 03:40:54 -0500  feat: add bookmarks command for heartbeat monitoring
623cca7  2026-02-19 03:42:50 -0500  Revert "feat: add bookmarks command for heartbeat monitoring"
```

**116 seconds** between introduction and reversion. `HEAD` is the revert.
A repo-wide search for `bookmark` at `HEAD` returns nothing — the code is fully removed.

Per the peer analysis of commit `67f5f9e`, the reverted implementation used OAuth 2.0 PKCE with `X_OAUTH2_ACCESS_TOKEN` against `GET /2/users/{id}/bookmarks` with `max_results=100` — architecturally the same approach `x-bookmarks` already uses.

**Neither commit message nor `CHANGELOG.md` gives any rationale.** We should not over-read this:

- A two-minute lifespan strongly suggests the feature was never validated in practice — plausibly it was pushed by mistake, or failed immediately on the OAuth setup, or the author reconsidered scope.
- It is **not** evidence that the bookmarks endpoint is broken or unusable. Our own tool reads that endpoint successfully on every run.
- The one defensible inference: adding user-context OAuth to a codebase built entirely around an app-level Bearer token is a structural mismatch, and that friction is a plausible motive for backing it out.

Useful to us mainly as confirmation that we already occupy the harder, more complete position — we have working OAuth PKCE plus `bookmark.write` deletion semantics that this project attempted and abandoned.

---

## 6. What is worth borrowing

Thin, but non-zero.

### 6.1 Rate-limit handling

`lib/api.ts`:

```typescript
const RATE_DELAY_MS = 350;   // line 9 — "stay under 450 req/15min"
...
if (res.status === 429) {                              // line 146
  const reset = res.headers.get("x-rate-limit-reset"); // line 147
```

A fixed inter-request delay plus explicit `x-rate-limit-reset` parsing on `429`.
**Maps onto:** roadmap `#15` (X API rate-limit backoff). Modest, but it is precisely the pattern `#15` calls for, and it is only a few lines.

### 6.2 Cost transparency as a UX primitive

Reporting estimated spend after every operation is a good habit we could mirror for Claude token spend.
Our run summary already prints tokens in/out; extending it to an estimated dollar figure would make the categorization cost legible in the same way.
**Maps onto:** nothing on the roadmap currently — a small optional enhancement.

### 6.3 Response caching

`lib/cache.ts` (109 lines) caches API responses to avoid re-billing identical queries.
Less relevant to us — our early-dedupe step already prevents the expensive repeat work, and bookmark fetches are inherently fresh.

### 6.4 Credential exposure in agent transcripts — **applies to us today**

The `## Security` section (README:197-206) documents a risk we are actively exposed to:

> *"**AI coding agents** (Claude Code, Codex, etc.) may log tool calls — including HTTP headers — in session transcripts. If you're running x-search inside an agent session, your bearer token could appear in those logs."*

Its recommendations: set the token as a system env var **rather than inline in commands**, review agent session-log settings, use minimal-permission tokens, and rotate on suspected exposure.

This is not a defect in x-research-skill — it is a property of running any credentialed tool inside an agent session, and `x-bookmarks` is run exactly that way.

**Relevance to us:** our secrets already avoid the worst form of this. `ANTHROPIC_API_KEY` and the twitter-cli session cookies are resolved from `pass` at runtime (`config.py:_resolve_from_pass`) and `.env` deliberately holds empty values, so the secrets are never inline arguments. X tokens live in `pass` or the environment, not in command lines.

**Worth adopting:** the explicit `## Security` section itself. Our `README.md` has security notes, but does not warn that running `x-bookmarks` inside an agent session can surface credentials in transcripts. That warning costs nothing and is accurate.

**Reinforces `#14`:** the roadmap's token-persistence item is currently justified by plaintext-at-rest risk. Transcript capture is a second, independent exposure path for the same credentials, and strengthens the case for `#14` ahead of `#17`.

---

## 7. Verdict

| Question | Answer |
|---|---|
| Can it do what we need, for free? | **No, twice over.** It is paid by design (~$0.50/search), and it cannot read bookmarks. |
| Does it execute a workflow we can borrow? | **Marginally** — §6.1 for `#15`; §6.2 is a nice-to-have. |
| Adopt as a runtime dependency? | **No.** Wrong language for our stack, wrong cost direction, no capability we lack. |
| Vendor its code? | **No** — and the missing `LICENSE` file would need resolving first if that ever changed. |
| Borrow its ideas? | **Yes, narrowly** — the `429` / `x-rate-limit-reset` pattern when implementing `#15`. |

### Effect on roadmap `#17`

None. x-research-skill does not clear the acceptance bar and does not change the standing recommendation in [`feasibility-graphql-vs-x-api.md`](feasibility-graphql-vs-x-api.md).

Taken together with [`feasibility-agent-reach.md`](feasibility-agent-reach.md), the two assessments bracket the option space cleanly:

- **`twitter-cli`** (via Agent-Reach) — free and fully capable, including bookmarks, but reaches them through private GraphQL with an active anti-detection stack.
- **x-research-skill** — sanctioned, ToS-clean, and supply-chain-clean, but explicitly paid and without bookmark support.

That is the whole trade-off in two lines, and `#17` sits between them.
The axis is not capability — a free mechanism that does everything we need exists today.
The axis is **account risk**, so `#17` is blocked on a user decision rather than on further research. See the `#17` candidate log in [`roadmap.md`](roadmap.md).

x-research-skill's one lasting contribution to that decision is a negative result worth recording: an author who had a working OAuth 2.0 PKCE bookmarks implementation — proper PKCE, state validation, refresh-token support — chose to delete it two minutes later rather than maintain it, in a codebase otherwise built on app-level Bearer auth.

---

## 8. Source references

- `lib/api.ts` — `BASE` const (8), `RATE_DELAY_MS` (9), `X_BEARER_TOKEN` (13, 21, 26), `429` handling (146-147), endpoints (197, 226, 251, 276)
- `lib/cache.ts` — response caching
- `README.md` — cost model (148-157), cost-transparency claims (13, 103, 118, 121), license (220-222)
- `git log` — `67f5f9e` → `623cca7` bookmarks add/revert, 2026-02-19
