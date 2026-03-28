import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.categorizer import (
    build_prompt_payload,
    parse_categorization_response,
    categorize_tweets,
    _slugify,
    _sanitize_title,
    _build_system_prompt,
    read_existing_taxonomy,
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


_FRONTMATTER_TEMPLATE = (
    '---\ntitle: "{title}"\nauthor: "@{username}"\n'
    'category: "{category}"\nsubCategory: "{sub}"\n'
    'date: 2025-01-01\nread: false\ntype: "post"\n'
    'tweet_url: "https://x.com/{username}/status/{id}"\n---\n\n## {title}\n\n> tweet text\n'
)


def _write_bookmark(path: Path, *, title: str, username: str, category: str, sub: str, id: str) -> None:
    path.write_text(
        _FRONTMATTER_TEMPLATE.format(
            title=title, username=username, category=category, sub=sub, id=id
        )
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


class TestSlugify:
    def test_simple_name(self):
        assert _slugify("AI Coding") == "ai-coding"

    def test_ampersand(self):
        assert _slugify("AI Product & Strategy") == "ai-product-strategy"

    def test_multiple_spaces(self):
        assert _slugify("ML  Research") == "ml-research"

    def test_general(self):
        assert _slugify("General") == "general"


class TestReadExistingTaxonomy:
    def test_returns_empty_when_dir_missing(self, tmp_path):
        result = read_existing_taxonomy(tmp_path / "nonexistent")
        assert result == {}

    def test_reads_category_and_subcategory(self, tmp_path):
        _write_bookmark(
            tmp_path / "2025-01-01-user.md",
            title="Test", username="user", category="AI Coding", sub="Coding Workflows", id="1",
        )
        result = read_existing_taxonomy(tmp_path)
        assert result == {"AI Coding": {"Coding Workflows"}}

    def test_aggregates_multiple_files(self, tmp_path):
        _write_bookmark(tmp_path / "a.md", title="A", username="u1", category="AI Coding", sub="Coding Workflows", id="1")
        _write_bookmark(tmp_path / "b.md", title="B", username="u2", category="AI Coding", sub="Prompt & Context Engineering", id="2")
        _write_bookmark(tmp_path / "c.md", title="C", username="u3", category="ML Research", sub="Applied ML", id="3")
        result = read_existing_taxonomy(tmp_path)
        assert result == {
            "AI Coding": {"Coding Workflows", "Prompt & Context Engineering"},
            "ML Research": {"Applied ML"},
        }

    def test_skips_files_without_both_fields(self, tmp_path):
        (tmp_path / "2025-01-01-user.md").write_text('---\ntitle: "No category here"\n---')
        result = read_existing_taxonomy(tmp_path)
        assert result == {}

    def test_returns_empty_when_dir_is_empty(self, tmp_path):
        result = read_existing_taxonomy(tmp_path)
        assert result == {}


class TestBuildSystemPrompt:
    def test_empty_taxonomy_prohibits_general_and_uncategorized(self):
        prompt = _build_system_prompt({})
        assert 'Do NOT use "General" or "Uncategorized"' in prompt

    def test_empty_taxonomy_first_run_message(self):
        prompt = _build_system_prompt({})
        assert "first run" in prompt

    def test_populated_taxonomy_lists_existing_categories(self):
        taxonomy = {"AI Coding": {"Coding Workflows"}, "ML Research": {"Applied ML"}}
        prompt = _build_system_prompt(taxonomy)
        assert "AI Coding" in prompt
        assert "Coding Workflows" in prompt
        assert "ML Research" in prompt
        assert "Applied ML" in prompt

    def test_populated_taxonomy_prohibits_general_and_uncategorized(self):
        prompt = _build_system_prompt({"AI Coding": {"Coding Workflows"}})
        assert 'Do NOT use "General" or "Uncategorized"' in prompt

    def test_contains_title_generation_rules(self):
        prompt = _build_system_prompt({})
        assert "max 80 chars" in prompt
        assert "YAML-safe" in prompt

    def test_allows_new_categories_when_taxonomy_exists(self):
        prompt = _build_system_prompt({"AI Coding": {"Coding Workflows"}})
        assert "Title Case" in prompt

    def test_prefers_existing_categories(self):
        prompt = _build_system_prompt({"AI Coding": {"Coding Workflows"}})
        assert "Prefer the existing" in prompt

    def test_contains_response_format_example(self):
        prompt = _build_system_prompt({})
        assert "tweet_id" in prompt
        assert "sub_category" in prompt


class TestParseCategorizationResponse:
    def test_parse_clean_json(self):
        response = json.dumps([
            {"tweet_id": "1", "category": "AI Coding", "sub_category": "Coding Workflows", "title": "Python Coding Tips"},
            {"tweet_id": "2", "category": "ML Research", "sub_category": "Applied ML", "title": "New LLM Benchmarks"},
        ])
        result = parse_categorization_response(response)
        assert len(result) == 2
        cat1, title1 = result["1"]
        assert cat1 == Category(slug="ai-coding", display_name="AI Coding", sub_category="Coding Workflows")
        assert title1 == "Python Coding Tips"
        cat2, title2 = result["2"]
        assert cat2 == Category(slug="ml-research", display_name="ML Research", sub_category="Applied ML")
        assert title2 == "New LLM Benchmarks"

    def test_parse_markdown_fenced_json(self):
        response = '```json\n[{"tweet_id": "1", "category": "Agent Architectures", "sub_category": "Applied Agents", "title": "Multi-Agent Orchestration"}]\n```'
        result = parse_categorization_response(response)
        assert len(result) == 1
        cat, title = result["1"]
        assert cat.slug == "agent-architectures"
        assert cat.sub_category == "Applied Agents"
        assert title == "Multi-Agent Orchestration"

    def test_parse_with_backtick_only(self):
        response = '```\n[{"tweet_id": "1", "category": "Model Systems", "sub_category": "Inference & Serving", "title": "vLLM Serving Guide"}]\n```'
        result = parse_categorization_response(response)
        cat, title = result["1"]
        assert cat.slug == "model-systems"
        assert cat.sub_category == "Inference & Serving"
        assert title == "vLLM Serving Guide"

    def test_empty_response_returns_empty(self):
        result = parse_categorization_response("[]")
        assert result == {}

    def test_slug_generated_from_category(self):
        response = json.dumps([
            {"tweet_id": "1", "category": "AI Product & Strategy", "sub_category": "Monetization & GTM", "title": "AI Startup Pricing"},
        ])
        result = parse_categorization_response(response)
        cat, _ = result["1"]
        assert cat.slug == "ai-product-strategy"

    def test_missing_title_returns_empty_string(self):
        response = json.dumps([
            {"tweet_id": "1", "category": "AI Coding", "sub_category": "Coding Workflows"},
        ])
        result = parse_categorization_response(response)
        _, title = result["1"]
        assert title == ""


class TestSanitizeTitle:
    def test_removes_newlines(self):
        assert _sanitize_title("Line 1\nLine 2\rLine 3") == "Line 1 Line 2 Line 3"

    def test_replaces_colons(self):
        assert _sanitize_title("Key: Value") == "Key - Value"

    def test_replaces_quotes(self):
        assert _sanitize_title('He said "hello"') == "He said 'hello'"

    def test_replaces_brackets(self):
        assert _sanitize_title("Use [this] library") == "Use (this) library"

    def test_truncates_long_text(self):
        long = "A" * 200
        result = _sanitize_title(long)
        assert len(result) == 83  # 80 + "..."
        assert result.endswith("...")

    def test_short_text_unchanged(self):
        assert _sanitize_title("Simple title") == "Simple title"


class TestCategorizeTweets:
    @patch("src.categorizer.anthropic")
    def test_categorize_tweets(self, mock_anthropic_module):
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {"tweet_id": "1", "category": "AI Coding", "sub_category": "Coding Workflows", "title": "Python Tips and Tricks"},
            {"tweet_id": "2", "category": "ML Research", "sub_category": "Applied ML", "title": "Latest LLM Advances"},
        ])
        mock_response.usage.input_tokens = 500
        mock_response.usage.output_tokens = 100
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "Python tips"), _make_tweet("2", "New LLM"))
        result, usage = categorize_tweets(tweets, api_key="sk-test")

        assert len(result) == 2
        assert result[0].category.slug == "ai-coding"
        assert result[0].category.sub_category == "Coding Workflows"
        assert result[0].title == "Python Tips and Tricks"
        assert result[1].category.slug == "ml-research"
        assert result[1].title == "Latest LLM Advances"
        assert usage["input_tokens"] == 500

    @patch("src.categorizer.anthropic")
    def test_missing_tweet_falls_back_to_general(self, mock_anthropic_module):
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {"tweet_id": "1", "category": "AI Coding", "sub_category": "Coding Workflows", "title": "Python Insights"},
        ])
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "Python"), _make_tweet("2", "Omitted by Claude"))
        result, _ = categorize_tweets(tweets, api_key="sk-test")

        assert len(result) == 2
        categorized_map = {ct.tweet.id: ct for ct in result}
        assert categorized_map["1"].category.slug == "ai-coding"
        assert categorized_map["1"].title == "Python Insights"
        # tweet 2 was omitted from Claude response — code-level fallback applies
        assert categorized_map["2"].category.slug == "general"
        assert categorized_map["2"].category.sub_category == "Uncategorized"

    @patch("src.categorizer.anthropic")
    def test_fallback_title_when_claude_returns_empty(self, mock_anthropic_module):
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {"tweet_id": "1", "category": "AI Coding", "sub_category": "Coding Workflows", "title": ""},
        ])
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 25
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "Python tips"),)
        result, _ = categorize_tweets(tweets, api_key="sk-test")

        assert result[0].title == "Python tips"  # sanitized display_text fallback

    @patch("src.categorizer.anthropic")
    def test_dynamic_prompt_used_no_general_fallback(self, mock_anthropic_module):
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
        system = call_kwargs.kwargs["system"]
        assert "bookmark categorizer" in system
        assert 'Do NOT use "General" or "Uncategorized"' in system
        assert call_kwargs.kwargs["model"] == "claude-sonnet-4-6"
        assert call_kwargs.kwargs["max_tokens"] == 8192

    @patch("src.categorizer.anthropic")
    def test_existing_taxonomy_injected_into_prompt(self, mock_anthropic_module, tmp_path):
        mock_client = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "[]"
        mock_response.usage.input_tokens = 0
        mock_response.usage.output_tokens = 0
        mock_client.messages.create.return_value = mock_response

        _write_bookmark(tmp_path / "a.md", title="A", username="u", category="AI Coding", sub="Coding Workflows", id="1")

        categorize_tweets((), api_key="sk-test", output_dir=tmp_path)

        call_kwargs = mock_client.messages.create.call_args
        system = call_kwargs.kwargs["system"]
        assert "AI Coding" in system
        assert "Coding Workflows" in system
        assert "Prefer the existing" in system
