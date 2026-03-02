import json
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock, call
from pathlib import Path

from src.main import main, _build_run_record, _append_history, _count_categories, _HISTORY_FILENAME
from src.models import Tweet, User, Category, CategorizedTweet
from src.config import Config


def _make_tweet(id: str = "1", text: str = "Hello", article_url: str | None = None, article_content: str | None = None) -> Tweet:
    return Tweet(
        id=id, text=text, author_id="10",
        created_at=datetime(2025, 1, 1),
        author=User(id="10", name="Test", username="test", profile_image_url=None, verified=False),
        public_metrics={"like_count": 1}, media=(), external_links=(),
        note_tweet_text=None, article_url=article_url,
        article_content=article_content,
    )


def _make_config(tmp_path: Path) -> Config:
    return Config(
        client_id="c", client_secret=None,
        access_token="a", refresh_token="r",
        user_id="999", anthropic_api_key="sk-test",
        output_dir=tmp_path,
    )


def _write_stats(files: int = 0, dupes: int = 0, filenames: list[str] | None = None) -> dict:
    return {
        "files_written": files,
        "bookmarks_written": files,
        "duplicates_skipped": dupes,
        "filenames": filenames or [],
    }


class TestMain:
    @patch("src.main.write_bookmarks")
    @patch("src.main.categorize_tweets")
    @patch("src.main.read_existing_ids")
    @patch("src.main.fetch_bookmarks")
    @patch("src.main.load_config")
    def test_full_pipeline(self, mock_config, mock_fetch, mock_existing, mock_categorize, mock_write, tmp_path, capsys):
        config = _make_config(tmp_path)
        mock_config.return_value = config
        mock_existing.return_value = set()

        tweets = (_make_tweet("1"), _make_tweet("2"))
        mock_fetch.return_value = tweets

        cat = Category(slug="general", display_name="General", sub_category="Uncategorized")
        categorized = tuple(CategorizedTweet(tweet=t, category=cat, title="Hello") for t in tweets)
        mock_categorize.return_value = (categorized, {"input_tokens": 100, "output_tokens": 50})

        mock_write.return_value = _write_stats(2, filenames=["2025-01-01-test.md", "2025-01-01-test-2.md"])

        main()

        mock_fetch.assert_called_once_with(config)
        mock_categorize.assert_called_once_with(tweets, api_key="sk-test")
        mock_write.assert_called_once_with(categorized, tmp_path)

        output = capsys.readouterr().out
        assert "Fetched 2 bookmarks" in output
        assert "New bookmarks:      2" in output
        assert "+ 2025-01-01-test.md" in output
        assert "+ 2025-01-01-test-2.md" in output
        assert "~ index.md (updated)" in output

    @patch("src.main.load_config")
    def test_config_error_exits(self, mock_config, capsys):
        mock_config.side_effect = ValueError("Missing: CLIENT_ID")
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        assert "Configuration error" in capsys.readouterr().out

    @patch("src.main.fetch_bookmarks")
    @patch("src.main.load_config")
    def test_no_bookmarks(self, mock_config, mock_fetch, tmp_path, capsys):
        mock_config.return_value = _make_config(tmp_path)
        mock_fetch.return_value = ()

        main()

        output = capsys.readouterr().out
        assert "No bookmarks found" in output

    @patch("src.main.write_bookmarks")
    @patch("src.main.categorize_tweets")
    @patch("src.main.read_existing_ids")
    @patch("src.main.fetch_bookmarks")
    @patch("src.main.load_config")
    def test_article_summary_printed_when_articles_present(
        self, mock_config, mock_fetch, mock_existing, mock_categorize, mock_write, tmp_path, capsys,
    ):
        config = _make_config(tmp_path)
        mock_config.return_value = config
        mock_existing.return_value = set()

        article_tweet = _make_tweet(
            "1",
            article_url="https://x.com/i/article/1",
            article_content="Full article text",
        )
        tweets = (article_tweet, _make_tweet("2"))
        mock_fetch.return_value = tweets

        cat = Category(slug="general", display_name="General", sub_category="Uncategorized")
        categorized = tuple(CategorizedTweet(tweet=t, category=cat, title="Hello") for t in tweets)
        mock_categorize.return_value = (categorized, {"input_tokens": 50, "output_tokens": 25})
        mock_write.return_value = _write_stats(2, filenames=["a.md", "b.md"])

        main()

        output = capsys.readouterr().out
        assert "Found 1 article(s) (1 with content from API)" in output

    @patch("src.main.write_bookmarks")
    @patch("src.main.categorize_tweets")
    @patch("src.main.read_existing_ids")
    @patch("src.main.fetch_bookmarks")
    @patch("src.main.load_config")
    def test_no_article_summary_when_no_articles(
        self, mock_config, mock_fetch, mock_existing, mock_categorize, mock_write, tmp_path, capsys,
    ):
        config = _make_config(tmp_path)
        mock_config.return_value = config
        mock_existing.return_value = set()

        tweets = (_make_tweet("1"), _make_tweet("2"))
        mock_fetch.return_value = tweets

        cat = Category(slug="general", display_name="General", sub_category="Uncategorized")
        categorized = tuple(CategorizedTweet(tweet=t, category=cat, title="Hello") for t in tweets)
        mock_categorize.return_value = (categorized, {"input_tokens": 50, "output_tokens": 25})
        mock_write.return_value = _write_stats(2, filenames=["a.md", "b.md"])

        main()

        output = capsys.readouterr().out
        assert "Found" not in output
        assert "article" not in output.lower().split("categorizing")[0]

    @patch("src.main.categorize_tweets")
    @patch("src.main.read_existing_ids")
    @patch("src.main.fetch_bookmarks")
    @patch("src.main.load_config")
    def test_all_duplicates_skips_categorization(
        self, mock_config, mock_fetch, mock_existing, mock_categorize, tmp_path, capsys,
    ):
        """When all fetched bookmarks already exist, Claude is never called."""
        config = _make_config(tmp_path)
        mock_config.return_value = config

        tweets = (_make_tweet("1"), _make_tweet("2"))
        mock_fetch.return_value = tweets
        mock_existing.return_value = {"1", "2"}

        main()

        mock_categorize.assert_not_called()
        output = capsys.readouterr().out
        assert "Skipping 2 already-saved" in output
        assert "All bookmarks already saved" in output

    @patch("src.main.write_bookmarks")
    @patch("src.main.categorize_tweets")
    @patch("src.main.read_existing_ids")
    @patch("src.main.fetch_bookmarks")
    @patch("src.main.load_config")
    def test_partial_duplicates_only_categorizes_novel(
        self, mock_config, mock_fetch, mock_existing, mock_categorize, mock_write, tmp_path, capsys,
    ):
        """Only novel tweets are sent to Claude for categorization."""
        config = _make_config(tmp_path)
        mock_config.return_value = config

        tweet_old = _make_tweet("1")
        tweet_new = _make_tweet("2")
        mock_fetch.return_value = (tweet_old, tweet_new)
        mock_existing.return_value = {"1"}

        cat = Category(slug="general", display_name="General", sub_category="Uncategorized")
        categorized = (CategorizedTweet(tweet=tweet_new, category=cat, title="Hello"),)
        mock_categorize.return_value = (categorized, {"input_tokens": 50, "output_tokens": 25})
        mock_write.return_value = _write_stats(1, filenames=["2025-01-01-test.md"])

        main()

        mock_categorize.assert_called_once_with((tweet_new,), api_key="sk-test")
        output = capsys.readouterr().out
        assert "Skipping 1 already-saved" in output
        assert "Categorizing 1 new bookmark(s)" in output

    @patch("src.main.write_bookmarks")
    @patch("src.main.categorize_tweets")
    @patch("src.main.read_existing_ids")
    @patch("src.main.fetch_bookmarks")
    @patch("src.main.load_config")
    def test_category_breakdown_printed(
        self, mock_config, mock_fetch, mock_existing, mock_categorize, mock_write, tmp_path, capsys,
    ):
        config = _make_config(tmp_path)
        mock_config.return_value = config
        mock_existing.return_value = set()

        t1 = _make_tweet("1")
        t2 = _make_tweet("2")
        mock_fetch.return_value = (t1, t2)

        cat_ai = Category(slug="ai-coding", display_name="AI Coding", sub_category="Coding Workflows")
        cat_ml = Category(slug="ml-research", display_name="ML Research", sub_category="Applied ML")
        categorized = (CategorizedTweet(tweet=t1, category=cat_ai, title="Hello"), CategorizedTweet(tweet=t2, category=cat_ml, title="Hello"))
        mock_categorize.return_value = (categorized, {"input_tokens": 50, "output_tokens": 25})
        mock_write.return_value = _write_stats(2, filenames=["a.md", "b.md"])

        main()

        output = capsys.readouterr().out
        assert "AI Coding: 1" in output
        assert "ML Research: 1" in output


class TestRunHistory:
    @patch("src.main.fetch_bookmarks")
    @patch("src.main.load_config")
    def test_history_written_on_empty(self, mock_config, mock_fetch, tmp_path, capsys):
        mock_config.return_value = _make_config(tmp_path)
        mock_fetch.return_value = ()

        main()

        history_path = tmp_path / _HISTORY_FILENAME
        assert history_path.exists()
        record = json.loads(history_path.read_text().strip())
        assert record["status"] == "empty"
        assert record["bookmarks"]["fetched"] == 0

    @patch("src.main.categorize_tweets")
    @patch("src.main.read_existing_ids")
    @patch("src.main.fetch_bookmarks")
    @patch("src.main.load_config")
    def test_history_written_on_noop(self, mock_config, mock_fetch, mock_existing, mock_categorize, tmp_path, capsys):
        mock_config.return_value = _make_config(tmp_path)
        mock_fetch.return_value = (_make_tweet("1"),)
        mock_existing.return_value = {"1"}

        main()

        history_path = tmp_path / _HISTORY_FILENAME
        record = json.loads(history_path.read_text().strip())
        assert record["status"] == "noop"
        assert record["bookmarks"]["fetched"] == 1
        assert record["bookmarks"]["skipped_existing"] == 1

    @patch("src.main.write_bookmarks")
    @patch("src.main.categorize_tweets")
    @patch("src.main.read_existing_ids")
    @patch("src.main.fetch_bookmarks")
    @patch("src.main.load_config")
    def test_history_written_on_success(
        self, mock_config, mock_fetch, mock_existing, mock_categorize, mock_write, tmp_path, capsys,
    ):
        mock_config.return_value = _make_config(tmp_path)
        mock_existing.return_value = set()

        tweets = (_make_tweet("1"),)
        mock_fetch.return_value = tweets

        cat = Category(slug="general", display_name="General", sub_category="Uncategorized")
        categorized = (CategorizedTweet(tweet=tweets[0], category=cat, title="Hello"),)
        mock_categorize.return_value = (categorized, {"input_tokens": 10, "output_tokens": 5})
        mock_write.return_value = _write_stats(1, filenames=["2025-01-01-test.md"])

        main()

        history_path = tmp_path / _HISTORY_FILENAME
        record = json.loads(history_path.read_text().strip())
        assert record["status"] == "success"
        assert record["bookmarks"]["novel"] == 1
        assert record["output"]["files_written"] == 1
        assert record["output"]["filenames"] == ["2025-01-01-test.md"]
        assert record["output"]["index_updated"] is True
        assert record["token_usage"] == {"input_tokens": 10, "output_tokens": 5}
        assert "run_id" in record
        assert "started_at" in record
        assert record["duration_ms"] >= 0

    @patch("src.main.write_bookmarks")
    @patch("src.main.categorize_tweets")
    @patch("src.main.read_existing_ids")
    @patch("src.main.fetch_bookmarks")
    @patch("src.main.load_config")
    def test_history_appends_multiple_runs(
        self, mock_config, mock_fetch, mock_existing, mock_categorize, mock_write, tmp_path, capsys,
    ):
        mock_config.return_value = _make_config(tmp_path)
        mock_existing.return_value = set()

        tweets = (_make_tweet("1"),)
        mock_fetch.return_value = tweets

        cat = Category(slug="general", display_name="General", sub_category="Uncategorized")
        categorized = (CategorizedTweet(tweet=tweets[0], category=cat, title="Hello"),)
        mock_categorize.return_value = (categorized, {"input_tokens": 10, "output_tokens": 5})
        mock_write.return_value = _write_stats(1, filenames=["a.md"])

        main()
        main()

        history_path = tmp_path / _HISTORY_FILENAME
        lines = history_path.read_text().strip().split("\n")
        assert len(lines) == 2
        r1 = json.loads(lines[0])
        r2 = json.loads(lines[1])
        assert r1["run_id"] != r2["run_id"]


class TestBuildRunRecord:
    def test_minimal_record(self):
        record = _build_run_record(
            run_id="abc123", status="empty",
            started_at="2025-01-01T00:00:00+00:00", duration_ms=42,
        )
        assert record["run_id"] == "abc123"
        assert record["status"] == "empty"
        assert record["duration_ms"] == 42
        assert record["bookmarks"]["fetched"] == 0
        assert record["output"]["filenames"] == []
        assert "error" not in record

    def test_error_included(self):
        record = _build_run_record(
            run_id="x", status="error",
            started_at="2025-01-01T00:00:00+00:00", duration_ms=0,
            error="API failure",
        )
        assert record["error"] == "API failure"

    def test_full_record(self):
        record = _build_run_record(
            run_id="full", status="success",
            started_at="2025-01-01T00:00:00+00:00", duration_ms=1500,
            output_dir="/tmp/out", fetched=10, skipped=3, novel=7,
            articles=2, files_written=7, duplicates_skipped=0,
            filenames=["a.md", "b.md"],
            token_usage={"input_tokens": 500, "output_tokens": 100},
            categories={"AI Coding": 5, "ML Research": 2},
        )
        assert record["bookmarks"]["novel"] == 7
        assert record["output"]["files_written"] == 7
        assert record["output"]["index_updated"] is True
        assert record["categories"] == {"AI Coding": 5, "ML Research": 2}


class TestAppendHistory:
    def test_creates_file(self, tmp_path):
        record = {"run_id": "test", "status": "ok"}
        path = _append_history(tmp_path, record)
        assert path.exists()
        assert json.loads(path.read_text().strip()) == record

    def test_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "a" / "b"
        record = {"run_id": "test"}
        path = _append_history(nested, record)
        assert path.exists()

    def test_appends_jsonl(self, tmp_path):
        _append_history(tmp_path, {"run": 1})
        _append_history(tmp_path, {"run": 2})
        lines = (tmp_path / _HISTORY_FILENAME).read_text().strip().split("\n")
        assert len(lines) == 2


class TestCountCategories:
    def test_counts(self):
        t1 = _make_tweet("1")
        t2 = _make_tweet("2")
        t3 = _make_tweet("3")
        cat_a = Category(slug="ai-coding", display_name="AI Coding", sub_category="Coding Workflows")
        cat_b = Category(slug="ml-research", display_name="ML Research", sub_category="Applied ML")
        categorized = (
            CategorizedTweet(tweet=t1, category=cat_a, title="Hello"),
            CategorizedTweet(tweet=t2, category=cat_a, title="Hello"),
            CategorizedTweet(tweet=t3, category=cat_b, title="Hello"),
        )
        result = _count_categories(categorized)
        assert result == {"AI Coding": 2, "ML Research": 1}

    def test_empty(self):
        assert _count_categories(()) == {}
