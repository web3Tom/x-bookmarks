"""CLI-level tests for mechanism selection.

`twitter-cli` is the default for both fetching and removal; `--official`
selects the OAuth path instead. These tests pin the selection logic and the
credential guard, since OAuth credentials are now optional and "user ran
--official without an X developer app" is a reachable state rather than an
impossible one.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.config import Config
from src.main import _build_deleter, _parse_args, main
from src.models import CategorizedTweet, Tweet
from src.unofficial_client import (
    AUTH_TOKEN_ENV,
    CT0_ENV,
    UnofficialFetchError,
)


def _config(**overrides):
    base = dict(
        client_id="", client_secret=None, access_token="",
        refresh_token="", user_id="", anthropic_api_key="sk-ant-test",
        output_dir=None, taxonomy_file=None,
    )
    base.update(overrides)
    return Config(**base)


class TestDefaults:
    def test_free_path_is_the_default(self):
        """A bare run must use twitter-cli and cost nothing."""
        args = _parse_args([])
        assert args.official is False
        assert args.max_bookmarks is None
        assert args.enrich_titles is False

    def test_official_is_opt_in(self):
        assert _parse_args(["--official"]).official is True


class TestFlagGuards:
    def test_max_bookmarks_rejected_with_official(self, capsys):
        """The official path paginates on the API's own cap, so accepting a
        limit there would imply control the flag does not actually have."""
        with pytest.raises(SystemExit):
            _parse_args(["--official", "--max-bookmarks", "500"])
        assert "--max-bookmarks" in capsys.readouterr().err

    def test_max_bookmarks_rejects_non_positive(self, capsys):
        with pytest.raises(SystemExit):
            _parse_args(["--max-bookmarks", "0"])
        assert "greater than zero" in capsys.readouterr().err

    def test_enrich_titles_rejected_with_removal(self, capsys):
        """Removal never fetches or categorizes, so enrichment there would
        imply work that never happens."""
        with pytest.raises(SystemExit):
            _parse_args(["--enrich-titles", "--remove-synthesized-bookmarks"])
        assert "enrich" in capsys.readouterr().err.lower()

    def test_official_combines_with_removal(self):
        """This combination is now valid and meaningful: it selects OAuth
        deletes, which retain the documented 404-means-absent contract."""
        args = _parse_args(["--official", "--remove-synthesized-bookmarks"])
        assert args.official is True
        assert args.remove_synthesized_bookmarks is True


class TestDeleterSelection:
    def test_default_deleter_uses_twitter_cli(self, monkeypatch):
        """Deletion must follow the same mechanism as fetching by default."""
        called = {}

        def fake_delete(tweet_id, *, env):
            called["tweet_id"] = tweet_id
            called["env_has_creds"] = bool(env.get(AUTH_TOKEN_ENV))
            return "unofficial-result"

        monkeypatch.setattr("src.main.delete_bookmark_unofficial", fake_delete)
        monkeypatch.setenv(AUTH_TOKEN_ENV, "tok")
        monkeypatch.setenv(CT0_ENV, "ct0")

        deleter = _build_deleter(_config(), official=False)
        assert deleter("999") == "unofficial-result"
        assert called["tweet_id"] == "999"
        assert called["env_has_creds"] is True

    def test_official_deleter_uses_api_client(self, monkeypatch):
        captured = {}

        def fake_delete(config, tweet_id):
            captured["tweet_id"] = tweet_id
            return "official-result"

        monkeypatch.setattr("src.main.delete_bookmark", fake_delete)
        deleter = _build_deleter(_config(user_id="42"), official=True)
        assert deleter("999") == "official-result"
        assert captured["tweet_id"] == "999"


class TestDefaultPathEndToEnd:
    """The default path must be exercised through main(), not just unit-tested.

    Every pre-existing pipeline test in test_main.py now runs with --official,
    so without this the free path would have no end-to-end coverage at all.
    """

    @patch("src.main.write_bookmarks")
    @patch("src.main.categorize_tweets")
    @patch("src.main.read_existing_ids")
    @patch("src.main.fetch_bookmarks_unofficial")
    @patch("src.main.fetch_bookmarks")
    @patch("src.main.load_config")
    def test_bare_run_uses_twitter_cli_and_never_the_official_api(
        self, mock_config, mock_official, mock_unofficial,
        mock_existing, mock_categorize, mock_write, tmp_path, capsys,
    ):
        mock_config.return_value = _config(output_dir=tmp_path)
        mock_existing.return_value = set()

        tweet = Tweet(
            id="1", text="hello", author_id="2",
            created_at=datetime(2026, 8, 4, tzinfo=timezone.utc), author=None,
            public_metrics={}, media=(), external_links=(),
            note_tweet_text=None, article_url=None,
        )
        mock_unofficial.return_value = (tweet,)
        mock_categorize.return_value = (
            (CategorizedTweet(tweet=tweet, pillar="Applied Practice", title="Hello"),),
            {"input_tokens": 10, "output_tokens": 5},
        )
        mock_write.return_value = {
            "files_written": 1, "duplicates_skipped": 0,
            "filenames": ["hello.md"], "failed": [],
        }

        main([])

        assert mock_unofficial.called
        assert not mock_official.called, "bare run must not touch the paid API"
        assert "twitter-cli" in capsys.readouterr().out

    @patch("src.main.fetch_bookmarks_unofficial")
    @patch("src.main.load_config")
    def test_missing_cookies_exit_without_falling_back(
        self, mock_config, mock_unofficial, tmp_path, capsys
    ):
        """Failure must not silently degrade to the paid path: that would spend
        money the user did not ask to spend."""
        mock_config.return_value = _config(output_dir=tmp_path)
        mock_unofficial.side_effect = UnofficialFetchError("no credentials")

        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 1
        assert "Fetch failed" in capsys.readouterr().out


class TestOfficialCredentialGuard:
    def test_config_without_oauth_reports_unusable(self):
        """OAuth credentials are optional now, so this is a real user state."""
        assert _config().has_official_credentials is False

    def test_config_with_full_oauth_reports_usable(self):
        assert _config(
            client_id="c", access_token="a", refresh_token="r", user_id="u"
        ).has_official_credentials is True

    def test_partial_oauth_is_not_usable(self):
        """A half-configured app would fail mid-run rather than at startup."""
        assert _config(
            client_id="c", access_token="a"
        ).has_official_credentials is False
