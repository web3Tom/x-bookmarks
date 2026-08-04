"""Tests for keyless external-link title enrichment via Jina Reader.

This path carries no credential and no account risk: `https://r.jina.ai/{url}`
is an unauthenticated GET. The tests therefore focus on the two ways it could
still hurt the pipeline:

1. Network failure on one link must never abort a run. Enrichment is a quality
   improvement, not a correctness requirement.
2. Tweets are frozen dataclasses consumed downstream; enrichment must return
   new objects rather than mutate, per the project's immutability rule.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.enrichment import (
    JINA_PREFIX,
    backfill_titles,
    extract_title,
    fetch_page,
    jina_url,
)
from src.models import ExternalLink, Tweet


def _tweet(links):
    return Tweet(
        id="1",
        text="text",
        author_id="2",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        author=None,
        public_metrics={},
        media=(),
        external_links=tuple(links),
        note_tweet_text=None,
        article_url=None,
    )


def _link(url, title=None):
    return ExternalLink(
        url=url, expanded_url=url, display_url=url, title=title
    )


class TestJinaUrl:
    def test_prefixes_target_url(self):
        assert jina_url("https://example.com/a") == f"{JINA_PREFIX}https://example.com/a"

    def test_is_keyless(self):
        """No token in the URL: this path must not acquire a credential."""
        built = jina_url("https://example.com/a")
        assert "key" not in built and "token" not in built


class TestExtractTitle:
    def test_reads_title_header(self):
        body = "Title: Real Page Title\n\nURL Source: https://example.com\n\nMarkdown Content:\nbody"
        assert extract_title(body) == "Real Page Title"

    def test_returns_none_without_title_header(self):
        assert extract_title("no header here") is None

    def test_returns_none_for_empty_title(self):
        assert extract_title("Title:   \n\nrest") is None

    def test_ignores_title_after_body_start(self):
        """A 'Title:' line inside page content is not the document title."""
        body = "Markdown Content:\nsome text\nTitle: Not The Title\n"
        assert extract_title(body) is None


class TestBackfillTitles:
    def test_fills_missing_title(self):
        tweets = (_tweet([_link("https://example.com/a")]),)
        result = backfill_titles(
            tweets, fetcher=lambda url: "Title: Fetched\n\nbody"
        )
        assert result[0].external_links[0].title == "Fetched"

    def test_preserves_existing_title(self):
        """The official API sometimes supplies a title; refetching it would
        waste a request and risk overwriting better metadata with worse."""
        called = []

        def fetcher(url):
            called.append(url)
            return "Title: Should Not Be Used\n"

        tweets = (_tweet([_link("https://example.com/a", title="Original")]),)
        result = backfill_titles(tweets, fetcher=fetcher)
        assert result[0].external_links[0].title == "Original"
        assert called == []

    def test_fetch_failure_leaves_title_none_and_continues(self):
        """One dead link must not abort enrichment of the rest."""
        def fetcher(url):
            if "bad" in url:
                raise OSError("connection reset")
            return "Title: Good\n"

        tweets = (
            _tweet([_link("https://bad.example.com/x")]),
            _tweet([_link("https://good.example.com/y")]),
        )
        result = backfill_titles(tweets, fetcher=fetcher)
        assert result[0].external_links[0].title is None
        assert result[1].external_links[0].title == "Good"

    def test_does_not_mutate_input(self):
        original = _tweet([_link("https://example.com/a")])
        tweets = (original,)
        backfill_titles(tweets, fetcher=lambda url: "Title: New\n")
        assert original.external_links[0].title is None

    def test_caches_repeated_urls(self):
        """The same link bookmarked twice must cost one request, not two."""
        calls = []

        def fetcher(url):
            calls.append(url)
            return "Title: Shared\n"

        tweets = (
            _tweet([_link("https://example.com/same")]),
            _tweet([_link("https://example.com/same")]),
        )
        result = backfill_titles(tweets, fetcher=fetcher)
        assert len(calls) == 1
        assert result[1].external_links[0].title == "Shared"

    def test_tweets_without_links_pass_through_unchanged(self):
        tweets = (_tweet([]),)
        result = backfill_titles(tweets, fetcher=lambda url: "Title: X\n")
        assert result[0] is tweets[0]

    def test_failed_url_is_cached_and_not_retried(self):
        """A dead host bookmarked many times must cost one timeout, not many."""
        calls = []

        def fetcher(url):
            calls.append(url)
            raise OSError("unreachable")

        tweets = (
            _tweet([_link("https://dead.example.com/a")]),
            _tweet([_link("https://dead.example.com/a")]),
        )
        backfill_titles(tweets, fetcher=fetcher)
        assert len(calls) == 1


class TestFetchPage:
    def test_requests_through_jina_without_credentials(self, monkeypatch):
        """Guards the core safety property: this path sends no credential."""
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b"Title: Live\n\nMarkdown Content:\nbody"

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["headers"] = request.headers
            return FakeResponse()

        monkeypatch.setattr(
            "src.enrichment.urllib.request.urlopen", fake_urlopen
        )
        body = fetch_page("https://example.com/a")

        assert captured["url"] == f"{JINA_PREFIX}https://example.com/a"
        joined = " ".join(f"{k}:{v}" for k, v in captured["headers"].items())
        assert "Authorization" not in joined and "Cookie" not in joined
        assert extract_title(body) == "Live"
