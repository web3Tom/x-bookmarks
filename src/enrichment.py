"""Keyless external-link enrichment via Jina Reader.

Reads `https://r.jina.ai/{url}` — an unauthenticated GET returning the page as
Markdown with a `Title:` header and a `Markdown Content:` body — to fill in what
the bookmark source left empty. Two backfills share that one response:

- `backfill_titles` fills `ExternalLink.title`. `twitter-cli` emits bare URL
  strings with no title metadata at all, and the official API populates titles
  only sometimes. Opt-in via `--enrich-titles`.
- `backfill_articles` fills `Tweet.article_content` for link-only bookmarks —
  a tweet whose whole text is a shortlink, which the categorizer cannot
  describe and which otherwise became a "Shared Link - No Substantive Content"
  note. Automatic, because a run that silently emits empty notes is worse than
  one that reads the page.

Risk posture: this path holds no credential and touches no X endpoint, so it
carries none of the account risk documented in docs/feasibility-agent-reach.md.
The trade-off is that every enriched URL is disclosed to a third-party service.
That is why the automatic path is scoped to bookmarks with no text of their
own: a bookmark that says something stays off the wire entirely.
"""

from __future__ import annotations

import re
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import replace

from src.models import Tweet

JINA_PREFIX = "https://r.jina.ai/"

_USER_AGENT = "x-bookmarks/1.0 (+https://github.com/web3Tom/x-bookmarks)"
_TITLE_PREFIX = "Title:"
_BODY_MARKER = "Markdown Content:"
_TIMEOUT_S = 20

_URL_PATTERN = re.compile(r"https?://\S+")
_MIN_SUBSTANTIVE_CHARS = 25


def jina_url(url: str) -> str:
    """Build the keyless Jina Reader URL for a target page."""
    return f"{JINA_PREFIX}{url}"


def extract_title(body: str) -> str | None:
    """Pull the document title from a Jina Reader response.

    Only the header region is searched. A `Title:` line appearing inside page
    content is body text, not the document title, and using it would write
    arbitrary page prose into note frontmatter.
    """
    head = body.split(_BODY_MARKER, 1)[0]
    for line in head.splitlines():
        if line.startswith(_TITLE_PREFIX):
            return line[len(_TITLE_PREFIX):].strip() or None
    return None


def fetch_page(url: str) -> str:
    """Default fetcher: read a URL through Jina Reader as plain text."""
    request = urllib.request.Request(
        jina_url(url),
        headers={"User-Agent": _USER_AGENT, "Accept": "text/plain"},
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
        return response.read().decode("utf-8", errors="replace")


def _safe_title(url: str, fetcher: Callable[[str], str]) -> str | None:
    """Fetch one title, converting any failure into None.

    Enrichment is a quality improvement, not a correctness requirement: a dead
    link must never abort a run that is otherwise producing good notes.
    """
    try:
        return extract_title(fetcher(url))
    except Exception:
        return None


def backfill_titles(
    tweets: Iterable[Tweet],
    *,
    fetcher: Callable[[str], str] | None = None,
) -> tuple[Tweet, ...]:
    """Return tweets with missing external-link titles populated.

    Never mutates its input — Tweet is frozen and shared downstream. Repeated
    URLs are fetched once, so the same link bookmarked twice costs one request.
    """
    fetch = fetcher if fetcher is not None else fetch_page
    cache: dict[str, str | None] = {}
    enriched: list[Tweet] = []

    for tweet in tweets:
        if not tweet.external_links or all(
            link.title for link in tweet.external_links
        ):
            enriched.append(tweet)
            continue

        new_links = []
        changed = False
        for link in tweet.external_links:
            if link.title:
                new_links.append(link)
                continue

            target = link.expanded_url
            if target not in cache:
                cache[target] = _safe_title(target, fetch)

            title = cache[target]
            if title:
                new_links.append(replace(link, title=title))
                changed = True
            else:
                new_links.append(link)

        enriched.append(
            replace(tweet, external_links=tuple(new_links)) if changed else tweet
        )

    return tuple(enriched)


def extract_body(body: str) -> str | None:
    """Pull the article prose from a Jina Reader response.

    Everything before `Markdown Content:` is Jina's own header (Title, URL
    Source, published date) — metadata, not article text. Returning it would
    put scaffolding into the note body.
    """
    _, marker, content = body.partition(_BODY_MARKER)
    if not marker:
        return None
    return content.strip() or None


def has_substantive_text(tweet: Tweet) -> bool:
    """Whether a tweet says enough on its own to be categorized.

    A bookmark whose entire text is a shortlink (optionally with a "this 👇"
    lead-in) gives the categorizer nothing to work with, which is what produced
    the "Shared Link - No Substantive Content" notes. Such a tweet's meaning
    lives in the page it links to, so it is the one case worth fetching.
    """
    stripped = _URL_PATTERN.sub("", tweet.display_text)
    stripped = re.sub(r"[^\w\s]", "", stripped)
    return len(stripped.strip()) >= _MIN_SUBSTANTIVE_CHARS


def _safe_page(url: str, fetcher: Callable[[str], str]) -> str | None:
    """Fetch one page, converting any failure into None."""
    try:
        return fetcher(url)
    except Exception:
        return None


def backfill_articles(
    tweets: Iterable[Tweet],
    *,
    fetcher: Callable[[str], str] | None = None,
) -> tuple[Tweet, ...]:
    """Return tweets with `article_content` filled for link-only bookmarks.

    Scope is deliberately narrow: only a tweet that has no substantive text of
    its own, has a link to follow, and has no article text already. That keeps
    the fetch to the bookmarks that would otherwise become empty placeholder
    notes, and keeps every other bookmarked URL off the wire.

    Never mutates its input — Tweet is frozen and shared downstream. Repeated
    URLs are fetched once.
    """
    # Resolved here rather than as a default argument: a default binds
    # `fetch_page` at import time, which silently defeats monkeypatching and
    # lets a test suite make live network calls.
    fetch = fetcher if fetcher is not None else fetch_page
    cache: dict[str, tuple[str | None, str | None]] = {}
    enriched: list[Tweet] = []

    for tweet in tweets:
        if (
            tweet.article_content
            or not tweet.external_links
            or has_substantive_text(tweet)
        ):
            enriched.append(tweet)
            continue

        target = tweet.external_links[0].expanded_url
        if target not in cache:
            page = _safe_page(target, fetch)
            cache[target] = (
                (extract_body(page), extract_title(page)) if page else (None, None)
            )

        content, title = cache[target]
        if content:
            enriched.append(
                replace(
                    tweet,
                    article_content=content,
                    article_title=title or tweet.article_title,
                )
            )
        else:
            enriched.append(tweet)

    return tuple(enriched)
