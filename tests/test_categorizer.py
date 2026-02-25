import json
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.categorizer import (
    build_prompt_payload,
    parse_categorization_response,
    categorize_tweets,
    SYSTEM_PROMPT,
)
from src.models import Tweet, Category, CategorizedTweet, User


def _make_tweet(id: str, text: str, username: str = "user") -> Tweet:
    return Tweet(
        id=id,
        text=text,
        author_id="10",
        created_at=datetime(2025, 1, 1),
        author=User(id="10", name=username, username=username, profile_image_url=None, verified=False),
        public_metrics={"like_count": 5},
        media=(),
        external_links=(),
        note_tweet_text=None,
        article_url=None,
    )


class TestBuildPromptPayload:
    def test_builds_json_array(self):
        tweets = (_make_tweet("1", "Python is great"), _make_tweet("2", "New AI model"))
        payload = build_prompt_payload(tweets)
        parsed = json.loads(payload)
        assert len(parsed) == 2
        assert parsed[0]["tweet_id"] == "1"
        assert parsed[0]["text"] == "Python is great"

    def test_includes_author_username(self):
        tweets = (_make_tweet("1", "Hello", username="alice"),)
        payload = build_prompt_payload(tweets)
        parsed = json.loads(payload)
        assert parsed[0]["author"] == "alice"

    def test_empty_tweets(self):
        payload = build_prompt_payload(())
        parsed = json.loads(payload)
        assert parsed == []

    def test_uses_display_text(self):
        tweet = Tweet(
            id="1", text="Short",
            author_id="10", created_at=datetime(2025, 1, 1),
            author=None, public_metrics={},
            media=(), external_links=(),
            note_tweet_text="Full long-form text here",
            article_url=None,
        )
        payload = build_prompt_payload((tweet,))
        parsed = json.loads(payload)
        assert parsed[0]["text"] == "Full long-form text here"

    def test_article_excerpt_included_when_content_present(self):
        tweet = Tweet(
            id="1", text="Check out my article",
            author_id="10", created_at=datetime(2025, 1, 1),
            author=User(id="10", name="u", username="u", profile_image_url=None, verified=False),
            public_metrics={}, media=(), external_links=(),
            note_tweet_text=None, article_url="https://x.com/u/articles/1",
            article_content="# Article Title\n\nBody of the article.",
        )
        payload = build_prompt_payload((tweet,))
        parsed = json.loads(payload)
        assert parsed[0]["article_excerpt"] == "# Article Title\n\nBody of the article."

    def test_article_excerpt_truncated_to_2000_chars(self):
        long_content = "x" * 3000
        tweet = Tweet(
            id="1", text="Article tweet",
            author_id="10", created_at=datetime(2025, 1, 1),
            author=User(id="10", name="u", username="u", profile_image_url=None, verified=False),
            public_metrics={}, media=(), external_links=(),
            note_tweet_text=None, article_url="https://x.com/u/articles/1",
            article_content=long_content,
        )
        payload = build_prompt_payload((tweet,))
        parsed = json.loads(payload)
        assert len(parsed[0]["article_excerpt"]) == 2000

    def test_no_article_excerpt_when_content_none(self):
        tweet = _make_tweet("1", "No article")
        payload = build_prompt_payload((tweet,))
        parsed = json.loads(payload)
        assert "article_excerpt" not in parsed[0]


class TestParseCategorizationResponse:
    def test_parse_clean_json(self):
        response = json.dumps([
            {"tweet_id": "1", "slug": "python", "display_name": "Python"},
            {"tweet_id": "2", "slug": "ai-ml", "display_name": "AI & ML"},
        ])
        result = parse_categorization_response(response)
        assert len(result) == 2
        assert result["1"] == Category(slug="python", display_name="Python")
        assert result["2"] == Category(slug="ai-ml", display_name="AI & ML")

    def test_parse_markdown_fenced_json(self):
        response = '```json\n[{"tweet_id": "1", "slug": "dev", "display_name": "Development"}]\n```'
        result = parse_categorization_response(response)
        assert len(result) == 1
        assert result["1"].slug == "dev"

    def test_parse_with_backtick_only(self):
        response = '```\n[{"tweet_id": "1", "slug": "dev", "display_name": "Dev"}]\n```'
        result = parse_categorization_response(response)
        assert result["1"].slug == "dev"

    def test_empty_response_returns_empty(self):
        result = parse_categorization_response("[]")
        assert result == {}


class TestCategorizeTweets:
    @patch("src.categorizer.anthropic")
    def test_categorize_tweets(self, mock_anthropic_module):
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {"tweet_id": "1", "slug": "python", "display_name": "Python"},
            {"tweet_id": "2", "slug": "ai-ml", "display_name": "AI & ML"},
        ])
        mock_response.usage.input_tokens = 500
        mock_response.usage.output_tokens = 100
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "Python tips"), _make_tweet("2", "New LLM"))
        result, usage = categorize_tweets(tweets, api_key="sk-test")

        assert len(result) == 2
        assert result[0].category.slug == "python"
        assert result[1].category.slug == "ai-ml"
        assert usage["input_tokens"] == 500

    @patch("src.categorizer.anthropic")
    def test_uncategorized_tweets_get_general(self, mock_anthropic_module):
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {"tweet_id": "1", "slug": "python", "display_name": "Python"},
        ])
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "Python"), _make_tweet("2", "Uncategorized"))
        result, _ = categorize_tweets(tweets, api_key="sk-test")

        assert len(result) == 2
        categorized_ids = {ct.tweet.id: ct.category.slug for ct in result}
        assert categorized_ids["1"] == "python"
        assert categorized_ids["2"] == "general"

    @patch("src.categorizer.anthropic")
    def test_system_prompt_used(self, mock_anthropic_module):
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "[]"
        mock_response.usage.input_tokens = 0
        mock_response.usage.output_tokens = 0
        mock_client.messages.create.return_value = mock_response

        categorize_tweets((), api_key="sk-test")

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == SYSTEM_PROMPT
        assert call_kwargs.kwargs["model"] == "claude-sonnet-4-6"
        assert call_kwargs.kwargs["max_tokens"] == 8192
