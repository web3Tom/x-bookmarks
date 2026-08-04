"""Tests for the opt-in unofficial (cookie/GraphQL) backfill path.

These tests exist to protect two things that matter more than the feature:

1. The path is OFF unless explicitly enabled. A silent fallback to an
   unsanctioned mechanism would violate the account-risk posture recorded in
   docs/feasibility-agent-reach.md.
2. Credentials must be supplied explicitly. `twitter-cli` scans Chrome/Edge
   cookie jars when TWITTER_AUTH_TOKEN/TWITTER_CT0 are absent, which harvests
   session cookies without consent. Refusing to run without both variables is
   what prevents that scan from ever happening.
"""

from __future__ import annotations

import json
import subprocess
from datetime import timezone

import pytest

from src.unofficial_client import (
    AUTH_TOKEN_ENV,
    CT0_ENV,
    ENABLE_ENV,
    UnofficialDisabledError,
    UnofficialFetchError,
    ensure_ready,
    fetch_bookmarks_unofficial,
    is_enabled,
    parse_cli_tweet,
    parse_cli_tweets,
)


@pytest.fixture
def enabled_env():
    """Environment with the path enabled and explicit credentials present."""
    return {
        ENABLE_ENV: "1",
        AUTH_TOKEN_ENV: "cookie-auth-token",
        CT0_ENV: "cookie-ct0",
    }


@pytest.fixture
def cli_tweet_data():
    """A single tweet as `twitter bookmarks --json` emits it."""
    return {
        "id": "1900000000000000001",
        "text": "Full long-form text already resolved from note_tweet by twitter-cli",
        "author": {
            "id": "555666777",
            "name": "Cookie User",
            "screenName": "cookieuser",
            "profileImageUrl": "https://pbs.twimg.com/profile_images/c.jpg",
            "verified": True,
        },
        "metrics": {
            "likes": 10, "retweets": 2, "replies": 1,
            "quotes": 0, "views": 900, "bookmarks": 4,
        },
        "createdAtISO": "2026-03-07T05:51:02+00:00",
        "media": [
            {"type": "photo", "url": "https://pbs.twimg.com/media/a.jpg",
             "width": 100, "height": 200},
        ],
        "urls": [
            "https://example.com/deep-dive",
            "https://x.com/someone/status/123",
        ],
    }


class TestGating:
    def test_disabled_when_env_absent(self):
        """Default state must be OFF: absence of the flag is not consent."""
        assert is_enabled({}) is False

    @pytest.mark.parametrize("value", ["0", "", "false", "no"])
    def test_disabled_for_non_affirmative_values(self, value):
        """Only an explicit affirmative enables an unsanctioned mechanism."""
        assert is_enabled({ENABLE_ENV: value}) is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes"])
    def test_enabled_for_affirmative_values(self, value):
        assert is_enabled({ENABLE_ENV: value}) is True

    def test_ensure_ready_refuses_when_disabled(self):
        env = {AUTH_TOKEN_ENV: "a", CT0_ENV: "b"}
        with pytest.raises(UnofficialDisabledError):
            ensure_ready(env)

    @pytest.mark.parametrize("missing", [AUTH_TOKEN_ENV, CT0_ENV])
    def test_ensure_ready_refuses_without_explicit_credentials(
        self, enabled_env, missing
    ):
        """Missing either cookie must abort BEFORE twitter-cli is invoked.

        If we invoked it anyway, upstream would silently scan the browser
        cookie jar. Refusing here is the only thing preventing that.
        """
        env = dict(enabled_env)
        del env[missing]
        with pytest.raises(UnofficialFetchError) as exc:
            ensure_ready(env)
        assert missing in str(exc.value)

    def test_ensure_ready_passes_when_fully_configured(self, enabled_env):
        ensure_ready(enabled_env)  # must not raise


class TestAdapter:
    def test_maps_core_identity_fields(self, cli_tweet_data):
        tweet = parse_cli_tweet(cli_tweet_data)
        assert tweet.id == "1900000000000000001"
        assert tweet.author_id == "555666777"
        assert tweet.author.username == "cookieuser"
        assert tweet.author.verified is True

    def test_created_at_is_timezone_aware_utc(self, cli_tweet_data):
        """Downstream note frontmatter renders a date; a naive/local datetime
        would silently shift the date across a day boundary."""
        tweet = parse_cli_tweet(cli_tweet_data)
        assert tweet.created_at.tzinfo is not None
        assert tweet.created_at.astimezone(timezone.utc).year == 2026

    def test_note_tweet_text_is_none_because_text_is_already_full(
        self, cli_tweet_data
    ):
        """twitter-cli resolves note_tweet into `text` (parser.py:464), so
        duplicating it into note_tweet_text would double-render the body."""
        tweet = parse_cli_tweet(cli_tweet_data)
        assert tweet.note_tweet_text is None
        assert tweet.display_text == cli_tweet_data["text"]

    def test_self_links_are_excluded_from_external_links(self, cli_tweet_data):
        """x.com/t.co self-links are navigation noise, not references."""
        tweet = parse_cli_tweet(cli_tweet_data)
        assert [link.expanded_url for link in tweet.external_links] == [
            "https://example.com/deep-dive"
        ]

    def test_external_link_title_is_none(self, cli_tweet_data):
        """twitter-cli emits bare URL strings with no title metadata, which is
        precisely why the Jina title backfill pairs with this path."""
        tweet = parse_cli_tweet(cli_tweet_data)
        assert tweet.external_links[0].title is None

    def test_media_keys_are_synthesized_and_unique(self, cli_tweet_data):
        """The official API supplies media_key; twitter-cli does not. Keys must
        still be unique or downstream media lookups would collide."""
        cli_tweet_data["media"].append(
            {"type": "photo", "url": "https://pbs.twimg.com/media/b.jpg"}
        )
        tweet = parse_cli_tweet(cli_tweet_data)
        keys = [m.media_key for m in tweet.media]
        assert len(set(keys)) == 2
        assert all(tweet.id in k for k in keys)

    def test_article_url_detected_from_urls(self, cli_tweet_data):
        cli_tweet_data["urls"].append("https://x.com/i/article/998877")
        tweet = parse_cli_tweet(cli_tweet_data)
        assert tweet.article_url == "https://x.com/i/article/998877"

    def test_article_content_mapped_when_present(self, cli_tweet_data):
        cli_tweet_data["articleTitle"] = "The Title"
        cli_tweet_data["articleText"] = "Body text"
        tweet = parse_cli_tweet(cli_tweet_data)
        assert tweet.article_title == "The Title"
        assert tweet.article_content == "Body text"

    def test_public_metrics_use_official_api_key_names(self, cli_tweet_data):
        """markdown_writer and categorizer read official metric names; emitting
        twitter-cli's names would silently render empty metrics."""
        tweet = parse_cli_tweet(cli_tweet_data)
        assert tweet.public_metrics["like_count"] == 10
        assert tweet.public_metrics["bookmark_count"] == 4

    def test_missing_author_does_not_crash(self, cli_tweet_data):
        del cli_tweet_data["author"]
        tweet = parse_cli_tweet(cli_tweet_data)
        assert tweet.author is None

    def test_parse_cli_tweets_skips_unusable_entries(self, cli_tweet_data):
        """A single malformed entry must not abort a 2,000-bookmark backfill."""
        payload = [cli_tweet_data, {"no_id": True}]
        tweets = parse_cli_tweets(payload)
        assert len(tweets) == 1


class TestFetch:
    def _runner(self, stdout, returncode=0):
        def run(cmd, **kwargs):
            class Result:
                pass
            r = Result()
            r.returncode = returncode
            r.stdout = stdout
            r.stderr = "boom" if returncode else ""
            r.cmd = cmd
            r.kwargs = kwargs
            run.captured = r
            return r
        return run

    def test_invokes_cli_with_json_and_max(self, enabled_env, cli_tweet_data):
        runner = self._runner(json.dumps([cli_tweet_data]))
        tweets = fetch_bookmarks_unofficial(
            max_count=250, env=enabled_env, runner=runner
        )
        cmd = runner.captured.cmd
        assert cmd[:2] == ["twitter", "bookmarks"]
        assert "--json" in cmd
        assert "--max" in cmd and "250" in cmd
        assert len(tweets) == 1

    def test_credentials_passed_via_env_not_argv(self, enabled_env, cli_tweet_data):
        """Credentials in argv leak into shell history, ps output, and agent
        transcripts. They must travel only in the child environment."""
        runner = self._runner(json.dumps([cli_tweet_data]))
        fetch_bookmarks_unofficial(max_count=10, env=enabled_env, runner=runner)
        assert "cookie-auth-token" not in " ".join(runner.captured.cmd)
        child_env = runner.captured.kwargs["env"]
        assert child_env[AUTH_TOKEN_ENV] == "cookie-auth-token"
        assert child_env[CT0_ENV] == "cookie-ct0"

    def test_nonzero_exit_raises(self, enabled_env):
        runner = self._runner("", returncode=1)
        with pytest.raises(UnofficialFetchError):
            fetch_bookmarks_unofficial(max_count=10, env=enabled_env, runner=runner)

    def test_invalid_json_raises(self, enabled_env):
        runner = self._runner("not json")
        with pytest.raises(UnofficialFetchError):
            fetch_bookmarks_unofficial(max_count=10, env=enabled_env, runner=runner)

    def test_refuses_when_disabled(self, cli_tweet_data):
        runner = self._runner(json.dumps([cli_tweet_data]))
        with pytest.raises(UnofficialDisabledError):
            fetch_bookmarks_unofficial(max_count=10, env={}, runner=runner)

    def test_missing_cli_reports_install_hint(self, enabled_env):
        """`twitter-cli` is an external pipx install, so a missing binary is a
        likely first-run failure and must say how to fix it."""
        def runner(cmd, **kwargs):
            raise FileNotFoundError(cmd[0])

        with pytest.raises(UnofficialFetchError) as exc:
            fetch_bookmarks_unofficial(max_count=10, env=enabled_env, runner=runner)
        assert "pipx install twitter-cli" in str(exc.value)

    def test_timeout_is_surfaced_not_swallowed(self, enabled_env):
        """A hung backfill must fail loudly rather than look like zero results."""
        def runner(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, timeout=1)

        with pytest.raises(UnofficialFetchError) as exc:
            fetch_bookmarks_unofficial(max_count=10, env=enabled_env, runner=runner)
        assert "timed out" in str(exc.value)


class TestPayloadShapes:
    def test_accepts_dict_wrapper(self, cli_tweet_data):
        """Output shape may be wrapped; unwrap rather than silently return zero."""
        assert len(parse_cli_tweets({"tweets": [cli_tweet_data]})) == 1

    def test_rejects_unusable_payload_type(self):
        with pytest.raises(UnofficialFetchError):
            parse_cli_tweets("a string is not a tweet list")

    def test_malformed_timestamp_falls_back_to_aware_now(self, cli_tweet_data):
        """Never emit a naive datetime: downstream frontmatter would render an
        ambiguous date rather than fail."""
        cli_tweet_data["createdAtISO"] = "not-a-date"
        assert parse_cli_tweet(cli_tweet_data).created_at.tzinfo is not None

    def test_missing_timestamp_falls_back_to_aware_now(self, cli_tweet_data):
        del cli_tweet_data["createdAtISO"]
        assert parse_cli_tweet(cli_tweet_data).created_at.tzinfo is not None

    def test_naive_timestamp_is_assumed_utc(self, cli_tweet_data):
        cli_tweet_data["createdAtISO"] = "2026-03-07T05:51:02"
        parsed = parse_cli_tweet(cli_tweet_data).created_at
        assert parsed.tzinfo == timezone.utc
