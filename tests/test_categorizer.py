import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.categorizer import (
    build_prompt_payload,
    parse_categorization_response,
    categorize_tweets,
    _sanitize_title,
    _build_system_prompt,
    _resolve_facets,
)
from src.models import Tweet, CategorizedTweet, User
from src.taxonomy import DEFAULT_PILLAR_NAMES, DEFAULT_MECHANICS, TaxonomyOverride


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


class TestResolveFacets:
    def test_defaults_when_no_override(self):
        pillars, descriptions, mechanics_vocab, entity_tags = _resolve_facets(None)
        assert pillars == list(DEFAULT_PILLAR_NAMES)
        assert descriptions is not None  # Should have focus descriptions
        assert mechanics_vocab == DEFAULT_MECHANICS
        assert entity_tags == {}

    def test_uses_override_pillars_when_provided(self):
        override = TaxonomyOverride(
            pillars=("Theory & Concepts", "Applied Practice"),
            mechanics=("rag", "persistent-memory"),
            entity_tags={"model": ["deepseek"]},
        )
        pillars, descriptions, mechanics_vocab, entity_tags = _resolve_facets(override)
        assert pillars == ["Theory & Concepts", "Applied Practice"]
        assert descriptions is None  # Descriptions only for defaults
        assert mechanics_vocab == ("rag", "persistent-memory")
        assert entity_tags == {"model": ["deepseek"]}

    def test_uses_override_mechanics_only(self):
        override = TaxonomyOverride(mechanics=("custom-mechanic",))
        pillars, descriptions, mechanics_vocab, entity_tags = _resolve_facets(override)
        assert pillars == list(DEFAULT_PILLAR_NAMES)
        assert descriptions is not None
        assert mechanics_vocab == ("custom-mechanic",)
        assert entity_tags == {}

    def test_uses_override_entity_tags_only(self):
        override = TaxonomyOverride(entity_tags={"tool": ["docker", "k8s"]})
        pillars, descriptions, mechanics_vocab, entity_tags = _resolve_facets(override)
        assert entity_tags == {"tool": ["docker", "k8s"]}


class TestBuildSystemPrompt:
    def test_contains_pillar_names(self):
        pillars = ["Theory & Concepts", "Applied Practice"]
        prompt = _build_system_prompt(pillars)
        assert "Theory & Concepts" in prompt
        assert "Applied Practice" in prompt

    def test_includes_pillar_descriptions_when_provided(self):
        pillars = ["Theory & Concepts", "Applied Practice"]
        descriptions = {
            "Theory & Concepts": "Foundational ideas",
            "Applied Practice": "Building and implementing",
        }
        prompt = _build_system_prompt(pillars, descriptions)
        assert "Foundational ideas" in prompt
        assert "Building and implementing" in prompt

    def test_includes_mechanics_section_when_non_empty(self):
        pillars = ["Theory & Concepts"]
        mechanics = ("rag", "persistent-memory", "vector-search")
        prompt = _build_system_prompt(pillars, mechanics_vocab=mechanics)
        assert "Established mechanics" in prompt
        assert "rag" in prompt
        assert "persistent-memory" in prompt
        assert "vector-search" in prompt

    def test_omits_mechanics_section_when_empty(self):
        pillars = ["Theory & Concepts"]
        prompt = _build_system_prompt(pillars, mechanics_vocab=())
        assert "Established mechanics" not in prompt

    def test_includes_deprecations_when_provided(self):
        pillars = ["Theory & Concepts"]
        deprecations = ["General", "Uncategorized"]
        prompt = _build_system_prompt(pillars, deprecations=deprecations)
        assert "Avoid these" in prompt
        assert "General" in prompt
        assert "Uncategorized" in prompt

    def test_includes_guidance_when_provided(self):
        pillars = ["Theory & Concepts"]
        guidance = "Prefer Applied Practice for hands-on content."
        prompt = _build_system_prompt(pillars, guidance=guidance)
        assert "Domain guidance:" in prompt
        assert guidance in prompt

    def test_includes_entity_tags_section_when_non_empty(self):
        pillars = ["Theory & Concepts"]
        entity_tags = {"model": ["deepseek", "llama3"], "tool": ["docker"]}
        prompt = _build_system_prompt(pillars, entity_tags=entity_tags)
        assert "Known entity tags" in prompt
        assert "model: deepseek, llama3" in prompt
        assert "tool: docker" in prompt

    def test_omits_entity_tags_section_when_empty(self):
        pillars = ["Theory & Concepts"]
        prompt = _build_system_prompt(pillars, entity_tags={})
        assert "Known entity tags" not in prompt

    def test_includes_response_format_example_with_entity_tags(self):
        pillars = ["Applied Practice"]
        entity_tags = {"model": ["deepseek"]}
        prompt = _build_system_prompt(pillars, entity_tags=entity_tags)
        assert '"tags"' in prompt

    def test_includes_response_format_example_without_entity_tags(self):
        pillars = ["Applied Practice"]
        prompt = _build_system_prompt(pillars, entity_tags={})
        assert '"pillar":' in prompt
        assert '"mechanics":' in prompt
        assert '"title":' in prompt

    def test_contains_title_rules(self):
        prompt = _build_system_prompt(["Theory & Concepts"])
        assert "max 80 chars" in prompt
        assert "YAML-safe" in prompt

    def test_all_parts_together(self):
        pillars = ["Theory & Concepts", "Applied Practice"]
        descriptions = {"Theory & Concepts": "Foundational", "Applied Practice": "Practical"}
        mechanics = ("rag", "memory")
        deprecations = ["Old1", "Old2"]
        guidance = "Custom guidance here."
        entity_tags = {"tool": ["langchain"]}
        prompt = _build_system_prompt(
            pillars, descriptions, mechanics, deprecations, guidance, entity_tags
        )
        assert "Foundational" in prompt
        assert "rag" in prompt
        assert "Old1" in prompt
        assert "Custom guidance here." in prompt
        assert "langchain" in prompt


class TestParseCategorizationResponse:
    def test_parse_clean_json(self):
        response = json.dumps([
            {"tweet_id": "1", "pillar": "Applied Practice", "mechanics": ["rag"], "title": "Python Tips"},
            {"tweet_id": "2", "pillar": "Theory & Concepts", "mechanics": ["vector-search"], "title": "LLM Basics"},
        ])
        result = parse_categorization_response(response)
        assert len(result) == 2

        pillar1, mechanics1, title1, tags1 = result["1"]
        assert pillar1 == "Applied Practice"
        assert mechanics1 == ("rag",)
        assert title1 == "Python Tips"
        assert tags1 == []

        pillar2, mechanics2, title2, tags2 = result["2"]
        assert pillar2 == "Theory & Concepts"
        assert mechanics2 == ("vector-search",)
        assert title2 == "LLM Basics"
        assert tags2 == []

    def test_parse_markdown_fenced_json(self):
        response = '```json\n[{"tweet_id": "1", "pillar": "Applied Practice", "mechanics": ["rag", "memory"], "title": "Title"}]\n```'
        result = parse_categorization_response(response)
        assert len(result) == 1
        pillar, mechanics, title, tags = result["1"]
        assert pillar == "Applied Practice"
        assert mechanics == ("rag", "memory")
        assert title == "Title"
        assert tags == []

    def test_parse_with_backtick_only(self):
        response = '```\n[{"tweet_id": "1", "pillar": "Theory & Concepts", "mechanics": ["search"], "title": "Search Basics"}]\n```'
        result = parse_categorization_response(response)
        pillar, mechanics, title, tags = result["1"]
        assert pillar == "Theory & Concepts"
        assert mechanics == ("search",)
        assert title == "Search Basics"

    def test_empty_response_returns_empty_dict(self):
        result = parse_categorization_response("[]")
        assert result == {}

    def test_missing_title_returns_empty_string(self):
        response = json.dumps([
            {"tweet_id": "1", "pillar": "Applied Practice", "mechanics": ["rag"]},
        ])
        result = parse_categorization_response(response)
        pillar, mechanics, title, tags = result["1"]
        assert title == ""
        assert tags == []

    def test_missing_mechanics_returns_empty_tuple(self):
        response = json.dumps([
            {"tweet_id": "1", "pillar": "Applied Practice", "title": "Title"},
        ])
        result = parse_categorization_response(response)
        pillar, mechanics, title, tags = result["1"]
        assert mechanics == ()

    def test_parse_with_tags(self):
        response = json.dumps([
            {
                "tweet_id": "1",
                "pillar": "Applied Practice",
                "mechanics": ["rag"],
                "title": "LangGraph Tips",
                "tags": ["framework/langgraph", "model/deepseek"],
            },
        ])
        result = parse_categorization_response(response)
        pillar, mechanics, title, tags = result["1"]
        assert pillar == "Applied Practice"
        assert mechanics == ("rag",)
        assert title == "LangGraph Tips"
        assert tags == ["framework/langgraph", "model/deepseek"]

    def test_returns_raw_pillar_and_mechanics(self):
        """Pillar and mechanics are returned RAW — validation happens in categorize_tweets."""
        response = json.dumps([
            {
                "tweet_id": "1",
                "pillar": "INVALID PILLAR",
                "mechanics": ["INVALID-MECHANIC"],
                "title": "Title",
            },
        ])
        result = parse_categorization_response(response)
        pillar, mechanics, title, tags = result["1"]
        assert pillar == "INVALID PILLAR"
        assert mechanics == ("INVALID-MECHANIC",)


class TestCategorizeTweets:
    @patch("src.categorizer.anthropic.Anthropic")
    def test_categorize_tweets_end_to_end(self, mock_anthropic_class):
        """End-to-end test with mocked Claude API."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {
                "tweet_id": "1",
                "pillar": "Applied Practice",
                "mechanics": ["rag", "memory"],
                "title": "RAG Systems Guide",
                "tags": ["framework/langgraph"],
            },
            {
                "tweet_id": "2",
                "pillar": "Theory & Concepts",
                "mechanics": ["embeddings"],
                "title": "Embedding Theory",
            },
        ])
        mock_response.usage.input_tokens = 500
        mock_response.usage.output_tokens = 150
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "RAG tips"), _make_tweet("2", "Embeddings"))
        result, usage = categorize_tweets(tweets, api_key="sk-test")

        assert len(result) == 2
        assert result[0].pillar == "Applied Practice"
        assert result[0].mechanics == ("rag", "memory")
        assert result[0].title == "RAG Systems Guide"
        assert result[0].tags == ("framework/langgraph",)

        assert result[1].pillar == "Theory & Concepts"
        assert result[1].mechanics == ("embeddings",)
        assert result[1].title == "Embedding Theory"

        assert usage["input_tokens"] == 500
        assert usage["output_tokens"] == 150

    @patch("src.categorizer.anthropic.Anthropic")
    def test_pillar_validation_and_fallback(self, mock_anthropic_class):
        """Test that invalid pillars trigger fallback with warning."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {
                "tweet_id": "1",
                "pillar": "INVALID PILLAR",
                "mechanics": ["rag"],
                "title": "Bad Pillar",
            },
        ])
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "Test"),)
        result, _ = categorize_tweets(tweets, api_key="sk-test")

        # Fallback pillar is pillars[0] (first default pillar)
        assert result[0].pillar == DEFAULT_PILLAR_NAMES[0]

    @patch("src.categorizer.anthropic.Anthropic")
    def test_mechanics_normalization(self, mock_anthropic_class):
        """Test that mechanics are normalized (slugified, deduped)."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {
                "tweet_id": "1",
                "pillar": "Applied Practice",
                "mechanics": ["RAG", "Persistent Memory", "rag"],  # duped, mixed case
                "title": "Title",
            },
        ])
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "Test"),)
        result, _ = categorize_tweets(tweets, api_key="sk-test")

        # Should normalize to lowercase-slug and dedupe
        assert "rag" in result[0].mechanics
        assert "persistent-memory" in result[0].mechanics
        assert result[0].mechanics.count("rag") == 1  # No dupes

    @patch("src.categorizer.anthropic.Anthropic")
    def test_aliases_collapse_synonyms_end_to_end(self, mock_anthropic_class, tmp_path):
        """An override alias must collapse an LLM-emitted synonym to canonical."""
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text(
            "---\npillars:\n  - Applied Practice\n"
            "aliases:\n  persistent-memory: agent-memory\n---\n"
        )
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {
                "tweet_id": "1",
                "pillar": "Applied Practice",
                # LLM emits both the synonym and the canonical term.
                "mechanics": ["agent-memory", "persistent-memory"],
                "title": "Title",
            },
        ])
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "Test"),)
        result, _ = categorize_tweets(tweets, api_key="sk-test", override_file=override_file)

        # Synonym snaps to canonical and collapses to a single entry.
        assert result[0].mechanics == ("agent-memory",)

    @patch("src.categorizer.anthropic.Anthropic")
    def test_tags_normalization_and_filtering(self, mock_anthropic_class):
        """Test that tags are normalized and filtered by prefix."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {
                "tweet_id": "1",
                "pillar": "Applied Practice",
                "mechanics": ["rag"],
                "title": "Title",
                "tags": [
                    "framework/LangGraph",  # Mixed case
                    "model/Deepseek",  # Mixed case
                    "invalid_prefix/something",  # Invalid prefix, should be dropped
                    "framework/LangGraph",  # Duplicate
                ],
            },
        ])
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "Test"),)
        result, _ = categorize_tweets(tweets, api_key="sk-test")

        # Invalid prefix dropped, normalized to lowercase
        assert "framework/langgraph" in result[0].tags
        assert "model/deepseek" in result[0].tags
        assert len(result[0].tags) == 2  # No duplicates
        # Invalid prefix should not appear
        assert not any("invalid_prefix" in tag for tag in result[0].tags)

    @patch("src.categorizer.anthropic.Anthropic")
    def test_missing_tweet_in_response_uses_fallback(self, mock_anthropic_class):
        """Test fallback when a tweet is missing from Claude's response."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {
                "tweet_id": "1",
                "pillar": "Applied Practice",
                "mechanics": ["rag"],
                "title": "Tweet 1",
            },
        ])
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "Test 1"), _make_tweet("2", "Test 2"))
        result, _ = categorize_tweets(tweets, api_key="sk-test")

        assert len(result) == 2
        # Tweet 1 categorized normally
        assert result[0].pillar == "Applied Practice"
        assert result[0].title == "Tweet 1"

        # Tweet 2 uses fallback
        assert result[1].pillar == DEFAULT_PILLAR_NAMES[0]
        assert result[1].mechanics == ()
        assert result[1].tags == ()
        assert result[1].title == "Test 2"  # Sanitized from display_text

    @patch("src.categorizer.anthropic.Anthropic")
    def test_empty_mechanics_list_triggers_warning(self, mock_anthropic_class):
        """Test that empty mechanics list is logged as warning but tweet still categorized."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {
                "tweet_id": "1",
                "pillar": "Applied Practice",
                "mechanics": [],
                "title": "No Mechanics",
            },
        ])
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "Test"),)
        result, _ = categorize_tweets(tweets, api_key="sk-test")

        # Tweet still categorized, mechanics empty
        assert result[0].pillar == "Applied Practice"
        assert result[0].mechanics == ()
        assert result[0].title == "No Mechanics"

    @patch("src.categorizer.anthropic.Anthropic")
    def test_fallback_title_when_empty(self, mock_anthropic_class):
        """Test fallback title when Claude returns empty string."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {
                "tweet_id": "1",
                "pillar": "Applied Practice",
                "mechanics": ["rag"],
                "title": "",
            },
        ])
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "Original tweet text"),)
        result, _ = categorize_tweets(tweets, api_key="sk-test")

        assert result[0].title == "Original tweet text"

    @patch("src.categorizer.anthropic.Anthropic")
    def test_uses_override_file_when_provided(self, mock_anthropic_class, valid_override_file):
        """Test that override file is loaded and facets resolved."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {
                "tweet_id": "1",
                "pillar": "Applied Practice",
                "mechanics": ["rag"],
                "title": "Title",
                "tags": ["model/deepseek"],
            },
        ])
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "Test"),)
        result, usage = categorize_tweets(tweets, api_key="sk-test", override_file=valid_override_file)

        assert len(result) == 1
        assert result[0].pillar == "Applied Practice"
        # Override pillars [Theory & Concepts, Applied Practice] used, both available
        assert result[0].pillar in ["Theory & Concepts", "Applied Practice"]

    @patch("src.categorizer.anthropic.Anthropic")
    def test_system_prompt_contains_override_data(self, mock_anthropic_class, valid_override_file):
        """Test that system prompt includes override pillars, mechanics, deprecations, guidance."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "[]"
        mock_response.usage.input_tokens = 0
        mock_response.usage.output_tokens = 0
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "Test"),)
        categorize_tweets(tweets, api_key="sk-test", override_file=valid_override_file)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        system_prompt = call_kwargs["system"]

        # From valid_override_file: pillars [Theory & Concepts, Applied Practice]
        assert "Theory & Concepts" in system_prompt
        assert "Applied Practice" in system_prompt

        # From valid_override_file: mechanics [rag, persistent-memory]
        assert "rag" in system_prompt
        assert "persistent-memory" in system_prompt

        # From valid_override_file: deprecate [General, Uncategorized]
        assert "General" in system_prompt
        assert "Uncategorized" in system_prompt

        # From valid_override_file: guidance text
        assert "Prefer Applied Practice" in system_prompt

    @patch("src.categorizer.anthropic.Anthropic")
    def test_api_called_with_correct_model_and_tokens(self, mock_anthropic_class):
        """Test that Claude API is called with correct model and max_tokens."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "[]"
        mock_response.usage.input_tokens = 0
        mock_response.usage.output_tokens = 0
        mock_client.messages.create.return_value = mock_response

        categorize_tweets((), api_key="sk-test")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-6"
        assert call_kwargs["max_tokens"] == 8192

    @patch("src.categorizer.anthropic.Anthropic")
    def test_api_key_passed_to_client(self, mock_anthropic_class):
        """Test that API key is correctly passed to Anthropic client."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "[]"
        mock_response.usage.input_tokens = 0
        mock_response.usage.output_tokens = 0
        mock_client.messages.create.return_value = mock_response

        categorize_tweets((), api_key="sk-secret-key")

        mock_anthropic_class.assert_called_once_with(api_key="sk-secret-key")

    @patch("src.categorizer.anthropic.Anthropic")
    def test_defaults_used_when_no_override(self, mock_anthropic_class):
        """Test that default pillars/mechanics are used when no override file."""
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps([
            {
                "tweet_id": "1",
                "pillar": "Theory & Concepts",
                "mechanics": [],
                "title": "Title",
            },
        ])
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        tweets = (_make_tweet("1", "Test"),)
        result, _ = categorize_tweets(tweets, api_key="sk-test", override_file=None)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        system_prompt = call_kwargs["system"]

        # Default pillars should be present
        for pillar_name in DEFAULT_PILLAR_NAMES:
            assert pillar_name in system_prompt
