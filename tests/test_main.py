import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock, call
from pathlib import Path

from src.main import main
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


class TestMain:
    @patch("src.main.write_bookmarks")
    @patch("src.main.categorize_tweets")
    @patch("src.main.fetch_bookmarks")
    @patch("src.main.load_config")
    def test_full_pipeline(self, mock_config, mock_fetch, mock_categorize, mock_write, tmp_path, capsys):
        config = _make_config(tmp_path)
        mock_config.return_value = config

        tweets = (_make_tweet("1"), _make_tweet("2"))
        mock_fetch.return_value = tweets

        cat = Category(slug="general", display_name="General")
        categorized = tuple(CategorizedTweet(tweet=t, category=cat) for t in tweets)
        mock_categorize.return_value = (categorized, {"input_tokens": 100, "output_tokens": 50})

        mock_write.return_value = {"files_written": 1, "bookmarks_written": 2, "duplicates_skipped": 0}

        main()

        mock_fetch.assert_called_once_with(config)
        mock_categorize.assert_called_once_with(tweets, api_key="sk-test")
        mock_write.assert_called_once_with(categorized, tmp_path)

        output = capsys.readouterr().out
        assert "Fetched 2 bookmarks" in output
        assert "Bookmarks written:  2" in output

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
    @patch("src.main.fetch_bookmarks")
    @patch("src.main.load_config")
    def test_article_summary_printed_when_articles_present(
        self, mock_config, mock_fetch, mock_categorize, mock_write, tmp_path, capsys,
    ):
        config = _make_config(tmp_path)
        mock_config.return_value = config

        article_tweet = _make_tweet(
            "1",
            article_url="https://x.com/i/article/1",
            article_content="Full article text",
        )
        tweets = (article_tweet, _make_tweet("2"))
        mock_fetch.return_value = tweets

        cat = Category(slug="general", display_name="General")
        categorized = tuple(CategorizedTweet(tweet=t, category=cat) for t in tweets)
        mock_categorize.return_value = (categorized, {"input_tokens": 50, "output_tokens": 25})
        mock_write.return_value = {"files_written": 1, "bookmarks_written": 2, "duplicates_skipped": 0}

        main()

        output = capsys.readouterr().out
        assert "Found 1 article(s) (1 with content from API)" in output

    @patch("src.main.write_bookmarks")
    @patch("src.main.categorize_tweets")
    @patch("src.main.fetch_bookmarks")
    @patch("src.main.load_config")
    def test_no_article_summary_when_no_articles(
        self, mock_config, mock_fetch, mock_categorize, mock_write, tmp_path, capsys,
    ):
        config = _make_config(tmp_path)
        mock_config.return_value = config

        tweets = (_make_tweet("1"), _make_tweet("2"))
        mock_fetch.return_value = tweets

        cat = Category(slug="general", display_name="General")
        categorized = tuple(CategorizedTweet(tweet=t, category=cat) for t in tweets)
        mock_categorize.return_value = (categorized, {"input_tokens": 50, "output_tokens": 25})
        mock_write.return_value = {"files_written": 1, "bookmarks_written": 2, "duplicates_skipped": 0}

        main()

        output = capsys.readouterr().out
        assert "Found" not in output
        assert "article" not in output.lower().split("categorizing")[0]
