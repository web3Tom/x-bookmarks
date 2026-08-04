"""Keyless external-link title enrichment via Jina Reader.

Backfills `ExternalLink.title` where the source left it empty, by reading
`https://r.jina.ai/{url}` — an unauthenticated GET that returns the page as
Markdown with a `Title:` header.

Why this pairs with the unofficial backfill: `twitter-cli` emits bare URL
strings with no title metadata at all, so on that path every title starts as
None. The official API populates titles only sometimes.

Risk posture: this path holds no credential and touches no X endpoint, so it
carries none of the account risk documented in docs/feasibility-agent-reach.md.
The trade-off is that every enriched URL is disclosed to a third-party service,
which is why it is opt-in rather than automatic.
"""

from __future__ import annotations

import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import replace

from src.models import Tweet

JINA_PREFIX = "https://r.jina.ai/"

_USER_AGENT = "x-bookmarks/1.0 (+https://github.com/web3Tom/x-bookmarks)"
_TITLE_PREFIX = "Title:"
_BODY_MARKER = "Markdown Content:"
_TIMEOUT_S = 20


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
    fetcher: Callable[[str], str] = fetch_page,
) -> tuple[Tweet, ...]:
    """Return tweets with missing external-link titles populated.

    Never mutates its input — Tweet is frozen and shared downstream. Repeated
    URLs are fetched once, so the same link bookmarked twice costs one request.
    """
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
                cache[target] = _safe_title(target, fetcher)

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
