# Feasibility: Cookie/GraphQL X Access vs. the Official X API

**Status:** Analysis — no migration performed
**Date:** 2026-06-12
**Audience:** Maintainers of `x-bookmarks` and related X-data tooling

> **Partially revised 2026-08-03** by [`feasibility-agent-reach.md`](feasibility-agent-reach.md). Two updates:
>
> - **§3's capability caveat is obsolete.** This doc noted the bookmark swap was "not a drop-in" of `bird`'s search code. [`public-clis/twitter-cli`](https://github.com/public-clis/twitter-cli) has since implemented the full bookmark surface — read, folders, create, delete — under Apache-2.0, in Python, with dynamically-resolved queryIds. A free, capable mechanism now exists.
> - **§5's risk verdict is strengthened, not weakened.** That mechanism ships an explicit anti-detection stack (TLS fingerprint impersonation, `x-client-transaction-id` forgery, timing jitter documented as evading pattern detection, full browser-cookie forwarding). The recommendation below stands, now on named countermeasures rather than inference.
>
> Everything else here — §2's mechanism description, §4's comparison, §6's conditions — remains accurate.

---

## 1. Why this document exists

The `last30days` research skill reads live X.com posts **without** holding an X
API key or paying for an API tier. This raised an obvious question: if a skill
can pull X data for free, could `x-bookmarks` drop its official X API v2
integration and do the same?

This document explains exactly how `last30days` does it, names the underlying
technology, and assesses whether `x-bookmarks` should adopt the same approach.

**Bottom line up front:** It is technically feasible and the code already exists
(MIT-licensed), but it trades a *sanctioned, rate-limited, billable* path for an
*unsanctioned, brittle, account-risking* one. Recommendation is to **keep OAuth2
as the default** and, at most, add cookie auth as an opt-in fallback behind a
flag — never as the primary path for a credential tied to a real personal
account.

---

## 2. How `last30days` reads X without the API

### 2.1 The technology in one sentence

It **replays a logged-in browser session against X's private web-app GraphQL
endpoint** — the same internal API that `x.com`'s own front-end JavaScript
calls — rather than the public, documented `api.x.com/2/...` REST surface.

### 2.2 The components

| Layer | What it is |
|-------|-----------|
| Vendored client | A trimmed subset of [`@steipete/bird`](https://github.com/steipete/bird) v0.8.0 (MIT License), shipped in-tree as `bird-search/` — no external CLI or npm install at runtime |
| Runtime | Node.js subprocess (`bird-search.mjs`), invoked from Python (`bird_x.py`) via `subproc.run_with_timeout` |
| Endpoint | `POST https://x.com/i/api/graphql/{queryId}/SearchTimeline` with `product: "Latest"` |
| Auth model | **Session impersonation**, not OAuth: a hardcoded public web Bearer token + the user's `auth_token` and `ct0` cookies |

### 2.3 The authentication trick (the important part)

The official API wants OAuth 2.0 bearer tokens minted through an app
registration. This client instead sends the headers a *browser* sends:

```
authorization: Bearer AAAAAAAAAAAAAAAAAAAAANRILgAA…   ← the public, hardcoded
                                                        web-client Bearer that
                                                        x.com ships in its own JS
x-csrf-token: <ct0 cookie value>
x-twitter-auth-type: OAuth2Session
x-twitter-active-user: yes
cookie: auth_token=<…>; ct0=<…>
```

- The `Bearer AAAA…` token is **not a secret** — it is the same constant baked
  into x.com's front-end, identical for every visitor. It only identifies "the
  web app," not the user.
- The **actual identity** comes from two cookies:
  - `auth_token` — the session cookie proving you're logged in.
  - `ct0` — the CSRF token, echoed back in the `x-csrf-token` header (X's
    double-submit-cookie CSRF defense).
- Provide both and X's servers treat the request as coming from your own
  logged-in browser tab.

### 2.4 Where the cookies come from

`cookies.js` resolves credentials in priority order:

1. **Environment variables** `AUTH_TOKEN` / `CT0` (the documented path for the
   skill — you paste them from DevTools once).
2. **Browser cookie jars** (Safari/Chrome/Firefox) — *disabled by default* in
   the pipeline via `BIRD_DISABLE_BROWSER_COOKIES=1` so normal runs never
   trigger an OS Keychain prompt. Only an explicit "scan my browser" consent
   flow turns this on.

### 2.5 Operational hardening already in the vendored code

The fact that these mitigations exist tells you how fragile the approach is:

- **Dynamic `queryId` discovery** — GraphQL operation IDs change when X ships
  front-end builds, so the client fetches current IDs rather than hardcoding
  them, and iterates over candidates.
- **`features.json` payload** — X rejects GraphQL calls unless every current
  feature flag is present in the request; the client maintains this list.
- **Anti-bot HTML interstitial retry** — when X returns an HTML challenge page
  instead of JSON, the client retries with backoff (`MAX_JSON_DECODE_RETRIES`).
- **Literal keyword AND-matching** — `bird_x.py` aggressively strips a verbose
  research question down to ≤5 core keywords because `SearchTimeline` does
  literal matching, not semantic search.

---

## 3. How `x-bookmarks` reads X today

For contrast, `x-bookmarks` uses the **sanctioned** path end-to-end:

| Layer | What it is |
|-------|-----------|
| Auth | OAuth 2.0 **PKCE** flow (`auth_helper.py`) — opens a browser, user authorizes the registered app, exchanges a code for scoped tokens |
| Scopes | `tweet.read users.read bookmark.read bookmark.write offline.access` |
| Endpoint | `GET https://api.x.com/2/users/{user_id}/bookmarks` (+ `DELETE` for removal) |
| Tokens | Short-lived `ACCESS_TOKEN` + `REFRESH_TOKEN`, refreshable offline |
| Capability | Reads the user's **own bookmarks** (a private, per-user resource) |

A key product difference: `last30days` does **search** (public timeline
queries); `x-bookmarks` reads a **private per-user list**. They are different
GraphQL operations. `bird` *does* implement a Bookmarks operation, so the swap
is real — but it is not a drop-in of the search code; it's a different op with
different pagination cursors.

---

## 4. Side-by-side

| Dimension | Official X API v2 (current) | Cookie/GraphQL (`last30days` style) |
|-----------|-----------------------------|-------------------------------------|
| Sanctioned by X | ✅ Yes | ❌ No — violates the Developer Agreement / ToS |
| Auth artifact | OAuth2 scoped tokens (app-registered) | Session cookies (`auth_token`/`ct0`) |
| Cost | Tiered; bookmark reads effectively require a paid tier | "Free" (no API quota) |
| Rate limits | Documented, low for bookmarks (≈10 req/15 min/user on Basic; Free can't read) | Undocumented; throttled/challenged ad hoc by anti-bot |
| Stability | Versioned, deprecation notices | Breaks on any front-end build (queryId/feature churn) |
| Account risk | None (sanctioned) | **Real** — automated session use can get the *personal* account flagged/locked |
| Credential blast radius | Scoped (`bookmark.*` only), revocable | `auth_token` ≈ full account access; revoke = log out everywhere |
| Maintenance burden | Low (stable contract) | High (track queryIds, features, interstitials) |
| Setup friction | OAuth browser dance once | Paste 2 cookies (or scan browser jar) |

---

## 5. Feasibility verdict

### Technically feasible? — **Yes.**
- The client exists, is MIT-licensed, and is already vendored locally.
- `bird` supports a Bookmarks GraphQL operation, so the capability gap is
  closeable.
- Cookie extraction and the Node↔Python bridge are solved problems in the
  existing code.

### Advisable as the primary path? — **No.** Four blocking concerns:

1. **Terms-of-Service / account ban risk (the decisive one).**
   `x-bookmarks` operates on **your own, named X account** — the exact credential
   you cannot afford to lose. Driving it via replayed session cookies is
   precisely the automation X's anti-bot systems look for. A flagged or locked
   account is a far worse outcome than a paid API tier. `last30days` tolerates
   this risk because it is *optional, read-only search* the user opts into; a
   bookmark-management tool you run regularly is a different risk profile.

2. **Brittleness / maintenance tax.**
   The mitigations in §2.5 exist because the private endpoint changes without
   notice. You would inherit a permanent chase: queryIds, feature flags, and
   anti-bot interstitials. The official API gives you a versioned contract and
   deprecation warnings instead.

3. **Credential blast radius.**
   OAuth tokens are scoped to `bookmark.*` and individually revocable. The
   `auth_token` cookie is roughly **full account access**; if it leaks, the
   mitigation is "log out of all sessions." For a tool whose output (and repo)
   is treated as public, that is a poor secret to standardize on.

4. **Loss of write semantics correctness.**
   The official `DELETE …/bookmarks/{id}` is a documented, idempotent operation
   with clear error semantics (scope errors, rate-limit reset headers — already
   handled in `api_client.py`). Reproducing safe *deletes* over the private
   GraphQL surface is higher-stakes than read-only search.

---

## 6. Recommendation

1. **Keep OAuth 2.0 PKCE as the default and only documented path.** It is the
   correct contract for operating on a private, per-user resource on a real
   account.

2. **If — and only if — the official bookmarks rate limits are a genuine
   blocker** (confirm current API tier first; see open question), consider a
   **clearly-labelled, opt-in fallback** that reuses the vendored `bird`
   Bookmarks op, gated behind an explicit env flag (e.g.
   `X_BOOKMARKS_UNOFFICIAL=1`) and documented as ToS-violating and
   account-risking. Never silent, never default.

3. **Do not commit cookies anywhere.** If a cookie path is ever added, read
   `AUTH_TOKEN`/`CT0` from the environment only, mirror `last30days`'
   `BIRD_DISABLE_BROWSER_COOKIES` default, and add both names to the
   secret-scan denylist used before commits.

4. **Prefer the sanctioned middle ground for cost:** if the driver is purely
   API cost, re-evaluate the X API tier and quota math before taking on ban risk
   — a one-time tier bump is cheaper than a locked account.

---

## 7. Source references

- `last30days` skill — `scripts/lib/bird_x.py`, `scripts/lib/vendor/bird-search/`
  (`bird-search.mjs`, `lib/twitter-client-base.js`, `lib/twitter-client-search.js`,
  `lib/cookies.js`, `lib/twitter-client-constants.js`).
- `x-bookmarks` — `src/api_client.py`, `src/auth_helper.py`, `.env.example`.
- Upstream client: `@steipete/bird` (MIT License).
