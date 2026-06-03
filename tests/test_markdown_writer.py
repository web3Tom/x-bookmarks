import pytest
from datetime import datetime
from pathlib import Path

import yaml

from src.markdown_writer import (
    _build_filename,
    _build_frontmatter,
    _escape_yaml_string,
    _slugify_title,
    _validate_frontmatter,
    _format_post_body,
    _format_article_body,
    read_existing_ids,
    write_bookmarks,
    build_faceted_frontmatter,
)
from src.models import (
    Tweet, User, Media, ExternalLink, CategorizedTweet,
)


def _make_tweet(
    id: str = "1",
    text: str = "Hello world",
    username: str = "alice",
    name: str | None = None,
    created_at: datetime = datetime(2026, 2, 24, 10, 30),
    like_count: int = 196,
    retweet_count: int = 12,
    reply_count: int = 7,
    bookmark_count: int = 319,
    media: tuple = (),
    external_links: tuple = (),
    note_tweet_text: str | None = None,
    article_url: str | None = None,
    article_content: str | None = None,
    article_title: str | None = None,
) -> Tweet:
    return Tweet(
        id=id,
        text=text,
        author_id="10",
        created_at=created_at,
        author=User(
            id="10",
            name=name or username.title(),
            username=username,
            profile_image_url=None,
            verified=False,
        ),
        public_metrics={
            "like_count": like_count,
            "retweet_count": retweet_count,
            "reply_count": reply_count,
            "bookmark_count": bookmark_count,
            "impression_count": 1000,
        },
        media=media,
        external_links=external_links,
        note_tweet_text=note_tweet_text,
        article_url=article_url,
        article_content=article_content,
        article_title=article_title,
    )


class TestSlugifyTitle:
    def test_basic_title(self):
        assert _slugify_title("Hello World") == "hello-world"

    def test_special_chars_removed(self):
        assert _slugify_title("What's Next?") == "whats-next"

    def test_underscores_become_hyphens(self):
        assert _slugify_title("hello_world") == "hello-world"

    def test_empty_string(self):
        assert _slugify_title("") == "untitled"

    def test_only_special_chars(self):
        assert _slugify_title("@#$%") == "untitled"

    def test_truncation_at_80(self):
        long = "word " * 30
        result = _slugify_title(long)
        assert len(result) <= 80

    def test_no_trailing_hyphens_after_truncation(self):
        long = "a-" * 50
        result = _slugify_title(long)
        assert not result.endswith("-")


class TestBuildFilename:
    def test_basic_naming(self):
        result = _build_filename("Hello World", set())
        assert result == "hello-world.md"

    def test_collision_adds_suffix(self):
        existing = {"hello-world.md"}
        result = _build_filename("Hello World", existing)
        assert result == "hello-world-2.md"

    def test_multiple_collisions(self):
        existing = {"hello-world.md", "hello-world-2.md"}
        result = _build_filename("Hello World", existing)
        assert result == "hello-world-3.md"

    def test_empty_title_uses_untitled(self):
        result = _build_filename("", set())
        assert result == "untitled.md"


class TestEscapeYamlString:
    def test_plain_string(self):
        assert _escape_yaml_string("Hello world") == "Hello world"

    def test_escapes_backslashes(self):
        assert _escape_yaml_string("path\\to\\file") == "path\\\\to\\\\file"

    def test_escapes_double_quotes(self):
        assert _escape_yaml_string('He said "hello"') == 'He said \\"hello\\"'

    def test_combined_escaping(self):
        assert _escape_yaml_string('a\\b "c"') == 'a\\\\b \\"c\\"'


class TestBuildFacetedFrontmatter:
    """Direct tests of build_faceted_frontmatter to verify intent and canonical field order."""

    def test_canonical_field_order_with_entity_tags(self):
        """Verify field order: title, author, pillar, mechanics, entity_tags, date, read, synthesized, type, tweet_url, article_url."""
        fm = build_faceted_frontmatter(
            title="Test Title",
            author="alice",
            pillar="Applied Practice",
            mechanics=("agent", "rag"),
            entity_tags={"model": ["gpt-4"], "framework": ["langgraph"]},
            date="2026-02-24",
            read=True,
            synthesized=False,
            bookmark_type="post",
            tweet_url="https://x.com/alice/status/123",
            article_url=None,
        )
        lines = fm.strip().split("\n")

        # Extract field positions
        field_indices = {}
        for i, line in enumerate(lines):
            if line.startswith("title:"):
                field_indices["title"] = i
            elif line.startswith("author:"):
                field_indices["author"] = i
            elif line.startswith("pillar:"):
                field_indices["pillar"] = i
            elif line.startswith("mechanics:"):
                field_indices["mechanics"] = i
            elif line.startswith("entity_tags:"):
                field_indices["entity_tags"] = i
            elif line.startswith("date:"):
                field_indices["date"] = i
            elif line.startswith("read:"):
                field_indices["read"] = i
            elif line.startswith("synthesized:"):
                field_indices["synthesized"] = i
            elif line.startswith("type:"):
                field_indices["type"] = i
            elif line.startswith("tweet_url:"):
                field_indices["tweet_url"] = i

        # Verify canonical order
        order = ["title", "author", "pillar", "mechanics", "entity_tags", "date", "read", "synthesized", "type", "tweet_url"]
        positions = [field_indices[key] for key in order]
        assert positions == sorted(positions), f"Fields not in canonical order: {field_indices}"

    def test_author_gets_at_prefix_if_missing(self):
        """Author lacking @ prefix should get one prepended."""
        fm = build_faceted_frontmatter(
            title="Test",
            author="alice",  # no @
            pillar="Theory & Concepts",
            mechanics=(),
            entity_tags={},
            date="2026-02-24",
            read=False,
            synthesized=False,
            bookmark_type="post",
            tweet_url="https://x.com/alice/status/1",
        )
        assert 'author: "@alice"' in fm

    def test_author_already_with_at_prefix_unchanged(self):
        """Author with @ prefix should not get another."""
        fm = build_faceted_frontmatter(
            title="Test",
            author="@alice",
            pillar="Theory & Concepts",
            mechanics=(),
            entity_tags={},
            date="2026-02-24",
            read=False,
            synthesized=False,
            bookmark_type="post",
            tweet_url="https://x.com/alice/status/1",
        )
        assert 'author: "@alice"' in fm
        assert 'author: "@@alice"' not in fm

    def test_mechanics_empty_becomes_uncategorized(self):
        """When mechanics is empty, emit a single 'uncategorized' mechanic."""
        fm = build_faceted_frontmatter(
            title="Test",
            author="alice",
            pillar="Theory & Concepts",
            mechanics=(),  # empty
            entity_tags={},
            date="2026-02-24",
            read=False,
            synthesized=False,
            bookmark_type="post",
            tweet_url="https://x.com/alice/status/1",
        )
        assert "mechanics:" in fm
        assert "  - uncategorized" in fm

    def test_mechanics_non_empty_all_emitted(self):
        """When mechanics is non-empty, emit all items as block list."""
        fm = build_faceted_frontmatter(
            title="Test",
            author="alice",
            pillar="Applied Practice",
            mechanics=("agent-orchestration", "rag-retrieval"),
            entity_tags={},
            date="2026-02-24",
            read=False,
            synthesized=False,
            bookmark_type="post",
            tweet_url="https://x.com/alice/status/1",
        )
        assert "mechanics:" in fm
        assert "  - agent-orchestration" in fm
        assert "  - rag-retrieval" in fm

    def test_entity_tags_omitted_when_empty(self):
        """entity_tags block should be entirely absent when empty dict."""
        fm = build_faceted_frontmatter(
            title="Test",
            author="alice",
            pillar="Theory & Concepts",
            mechanics=("concept-learning",),
            entity_tags={},  # empty
            date="2026-02-24",
            read=False,
            synthesized=False,
            bookmark_type="post",
            tweet_url="https://x.com/alice/status/1",
        )
        assert "entity_tags:" not in fm

    def test_entity_tags_nested_format_when_present(self):
        """entity_tags block should nest as prefix: [entity1, entity2] format."""
        fm = build_faceted_frontmatter(
            title="Test",
            author="alice",
            pillar="Applied Practice",
            mechanics=("rag",),
            entity_tags={"model": ["gpt-4", "claude"], "framework": ["langgraph"]},
            date="2026-02-24",
            read=False,
            synthesized=False,
            bookmark_type="post",
            tweet_url="https://x.com/alice/status/1",
        )
        assert "entity_tags:" in fm
        assert "  model: [gpt-4, claude]" in fm
        assert "  framework: [langgraph]" in fm

    def test_article_url_included_when_truthy(self):
        """article_url field should appear only when truthy."""
        fm = build_faceted_frontmatter(
            title="Test",
            author="alice",
            pillar="Theory & Concepts",
            mechanics=(),
            entity_tags={},
            date="2026-02-24",
            read=False,
            synthesized=False,
            bookmark_type="article",
            tweet_url="https://x.com/alice/status/1",
            article_url="https://example.com/article",
        )
        assert 'article_url: "https://example.com/article"' in fm

    def test_article_url_omitted_when_none(self):
        """article_url field should not appear when None."""
        fm = build_faceted_frontmatter(
            title="Test",
            author="alice",
            pillar="Theory & Concepts",
            mechanics=(),
            entity_tags={},
            date="2026-02-24",
            read=False,
            synthesized=False,
            bookmark_type="post",
            tweet_url="https://x.com/alice/status/1",
            article_url=None,
        )
        assert "article_url:" not in fm

    def test_tail_lines_appended_before_closing_delimiter(self):
        """tail_lines tuple should be appended in order before closing ---."""
        fm = build_faceted_frontmatter(
            title="Test",
            author="alice",
            pillar="Theory & Concepts",
            mechanics=(),
            entity_tags={},
            date="2026-02-24",
            read=False,
            synthesized=False,
            bookmark_type="post",
            tweet_url="https://x.com/alice/status/1",
            tail_lines=("custom_field_1: value1", "custom_field_2: value2"),
        )
        lines = fm.strip().split("\n")
        closing_delimiter_idx = len(lines) - 1
        assert lines[closing_delimiter_idx] == "---"
        assert "custom_field_1: value1" in fm
        assert "custom_field_2: value2" in fm
        # Verify tail_lines come before closing delimiter
        custom_line_idx = next(i for i, l in enumerate(lines) if "custom_field_1" in l)
        assert custom_line_idx < closing_delimiter_idx

    def test_frontmatter_ends_with_newline(self):
        """Emitted frontmatter should end with a trailing newline."""
        fm = build_faceted_frontmatter(
            title="Test",
            author="alice",
            pillar="Theory & Concepts",
            mechanics=(),
            entity_tags={},
            date="2026-02-24",
            read=False,
            synthesized=False,
            bookmark_type="post",
            tweet_url="https://x.com/alice/status/1",
        )
        assert fm.endswith("\n")

    def test_emitted_yaml_is_valid(self):
        """The emitted YAML between --- markers should parse successfully."""
        fm = build_faceted_frontmatter(
            title="Test with 'quotes'",
            author="alice",
            pillar="Theory & Concepts",
            mechanics=("concept-learning",),
            entity_tags={"model": ["gpt-4"]},
            date="2026-02-24",
            read=True,
            synthesized=False,
            bookmark_type="post",
            tweet_url="https://x.com/alice/status/123",
        )
        lines = fm.strip().split("\n")
        yaml_body = "\n".join(lines[1:-1])
        parsed = yaml.safe_load(yaml_body)
        assert parsed["title"] == "Test with 'quotes'"
        assert parsed["author"] == "@alice"
        assert parsed["pillar"] == "Theory & Concepts"
        assert parsed["mechanics"] == ["concept-learning"]
        assert parsed["entity_tags"]["model"] == ["gpt-4"]
        assert parsed["read"] is True
        assert parsed["synthesized"] is False


class TestBuildFrontmatter:
    """Tests for _build_frontmatter (derives from tweet + pillar + title + mechanics + tags)."""

    def test_post_with_pillar_and_mechanics(self):
        """Post frontmatter should include pillar, mechanics, and grouped entity_tags from flat tags."""
        tweet = _make_tweet(id="123", username="alice")
        fm = _build_frontmatter(
            tweet,
            pillar="Applied Practice",
            bookmark_type="post",
            title="Hello world",
            mechanics=("agent-orchestration", "rag"),
            tags=("framework/langgraph", "model/gpt-4"),
        )
        assert fm.startswith("---\n")
        assert fm.endswith("---\n")
        assert 'title: "Hello world"' in fm
        assert 'author: "@alice"' in fm
        assert 'pillar: "Applied Practice"' in fm
        assert "mechanics:" in fm
        assert "  - agent-orchestration" in fm
        assert "  - rag" in fm
        assert "entity_tags:" in fm
        assert "  framework: [langgraph]" in fm
        assert "  model: [gpt-4]" in fm
        assert "date: 2026-02-24" in fm
        assert "read: false" in fm
        assert "synthesized: false" in fm
        assert 'type: "post"' in fm
        assert 'tweet_url: "https://x.com/alice/status/123"' in fm

    def test_article_includes_article_url_when_article_type(self):
        """When bookmark_type is 'article' and tweet has article_url, it should appear in frontmatter."""
        tweet = _make_tweet(
            id="456",
            username="bob",
            article_url="https://example.com/article",
            article_content="Some content",
        )
        fm = _build_frontmatter(
            tweet,
            pillar="Theory & Concepts",
            bookmark_type="article",
            title="My Article",
        )
        assert 'type: "article"' in fm
        assert 'article_url: "https://example.com/article"' in fm

    def test_article_url_omitted_when_not_article_type(self):
        """When bookmark_type is 'post' even if tweet has article_url, it should not appear."""
        tweet = _make_tweet(
            id="789",
            username="charlie",
            article_url="https://example.com/article",
        )
        fm = _build_frontmatter(
            tweet,
            pillar="Applied Practice",
            bookmark_type="post",
            title="Just a post",
        )
        assert "article_url:" not in fm

    def test_empty_mechanics_becomes_uncategorized(self):
        """When mechanics is empty, emit uncategorized."""
        tweet = _make_tweet()
        fm = _build_frontmatter(
            tweet,
            pillar="Theory & Concepts",
            bookmark_type="post",
            title="No mechanics",
            mechanics=(),
        )
        assert "  - uncategorized" in fm

    def test_flat_tags_grouped_by_prefix(self):
        """Flat tags like 'framework/langgraph' should be grouped into entity_tags nested structure."""
        tweet = _make_tweet()
        fm = _build_frontmatter(
            tweet,
            pillar="Applied Practice",
            bookmark_type="post",
            title="Test",
            mechanics=("agent",),
            tags=("framework/langgraph", "framework/crewai", "model/gpt-4", "tool/anthropic-sdk"),
        )
        lines = fm.strip().split("\n")
        # Extract YAML body between opening and closing --- delimiters
        yaml_body = "\n".join(lines[1:-1])
        parsed = yaml.safe_load(yaml_body)
        # Verify prefixes are properly grouped
        assert "framework" in parsed["entity_tags"]
        assert set(parsed["entity_tags"]["framework"]) == {"langgraph", "crewai"}
        assert "model" in parsed["entity_tags"]
        assert parsed["entity_tags"]["model"] == ["gpt-4"]
        assert "tool" in parsed["entity_tags"]
        assert parsed["entity_tags"]["tool"] == ["anthropic-sdk"]

    def test_no_tags_means_no_entity_tags_block(self):
        """When tags tuple is empty, entity_tags should not appear at all."""
        tweet = _make_tweet()
        fm = _build_frontmatter(
            tweet,
            pillar="Strategy",
            bookmark_type="post",
            title="No tags",
            mechanics=("business",),
            tags=(),
        )
        assert "entity_tags:" not in fm

    def test_frontmatter_is_valid_yaml(self):
        """The emitted frontmatter should always be valid YAML."""
        tweet = _make_tweet(created_at=datetime(2026, 3, 15, 14, 22))
        fm = _build_frontmatter(
            tweet,
            pillar="Applied Practice",
            bookmark_type="post",
            title="Inference & Serving",
            mechanics=("optimization",),
            tags=("harness/vllm",),
        )
        lines = fm.strip().split("\n")
        yaml_body = "\n".join(lines[1:-1])
        parsed = yaml.safe_load(yaml_body)
        assert parsed["title"] == "Inference & Serving"
        # YAML parses dates as date objects, so check the string representation
        assert str(parsed["date"]) == "2026-03-15"
        assert parsed["read"] is False
        assert parsed["synthesized"] is False


class TestValidateFrontmatter:
    def test_valid_frontmatter_passes_through(self):
        fm = '---\ntitle: "Hello"\nauthor: "@alice"\n---\n'
        assert _validate_frontmatter(fm) == fm

    def test_broken_yaml_attempts_repair(self):
        fm = '---\ntitle: "Bad: "yaml": here"\nauthor: "@alice"\n---\n'
        result = _validate_frontmatter(fm)
        assert result.startswith("---\n")
        assert result.endswith("---\n")

    def test_non_frontmatter_passes_through(self):
        text = "not frontmatter at all"
        assert _validate_frontmatter(text) == text

    def test_valid_complex_frontmatter(self):
        fm = (
            '---\n'
            'title: "Inference & Serving Guide"\n'
            'author: "@alice"\n'
            'pillar: "Applied Practice"\n'
            'mechanics:\n'
            '  - optimization\n'
            'entity_tags:\n'
            '  framework: [langgraph]\n'
            'type: "post"\n'
            '---\n'
        )
        assert _validate_frontmatter(fm) == fm


class TestFormatPostBody:
    def test_title_heading(self):
        tweet = _make_tweet(text="Hello world")
        body = _format_post_body(tweet, "Python Tips")
        assert "## Python Tips" in body
        assert "> Hello world" in body

    def test_references_section(self):
        tweet = _make_tweet(id="999", username="bob")
        body = _format_post_body(tweet, "Test Title")
        assert "## References" in body
        assert "- \U0001f517 [Original tweet](https://x.com/bob/status/999)" in body

    def test_multiline_blockquote(self):
        tweet = _make_tweet(text="Line 1\nLine 2\nLine 3")
        body = _format_post_body(tweet, "Multi Line")
        assert "> Line 1" in body
        assert "> Line 2" in body
        assert "> Line 3" in body

    def test_external_links_in_references(self):
        link = ExternalLink(
            url="https://t.co/abc",
            expanded_url="https://example.com/article",
            display_url="example.com/article",
            title="Great Article",
        )
        tweet = _make_tweet(external_links=(link,))
        body = _format_post_body(tweet, "Link Post")
        assert "- \U0001f310 [Great Article](https://example.com/article)" in body
        refs_idx = body.index("## References")
        link_idx = body.index("Great Article")
        assert link_idx > refs_idx

    def test_external_link_uses_display_url_when_no_title(self):
        link = ExternalLink(
            url="https://t.co/abc",
            expanded_url="https://example.com/page",
            display_url="example.com/page",
            title=None,
        )
        tweet = _make_tweet(external_links=(link,))
        body = _format_post_body(tweet, "Display URL")
        assert "- \U0001f310 [example.com/page](https://example.com/page)" in body

    def test_media_in_title_section(self):
        media = Media(
            media_key="3_100", type="photo",
            url="https://pbs.twimg.com/media/photo.jpg",
            preview_image_url=None, variants=(),
        )
        tweet = _make_tweet(media=(media,))
        body = _format_post_body(tweet, "Photo Post")
        assert "\U0001f4f7 [photo](https://pbs.twimg.com/media/photo.jpg)" in body
        title_idx = body.index("## Photo Post")
        media_idx = body.index("[photo]")
        refs_idx = body.index("## References")
        assert title_idx < media_idx < refs_idx

    def test_note_tweet_uses_display_text(self):
        tweet = _make_tweet(text="Short", note_tweet_text="Full long-form text here")
        body = _format_post_body(tweet, "Long Form")
        assert "> Full long-form text here" in body
        assert "Short" not in body

    def test_title_before_references(self):
        tweet = _make_tweet()
        body = _format_post_body(tweet, "My Title")
        title_idx = body.index("## My Title")
        refs_idx = body.index("## References")
        assert title_idx < refs_idx


class TestFormatArticleBody:
    def test_title_heading_with_content(self):
        tweet = _make_tweet(article_content="# Great Article\n\nSome body text.")
        body = _format_article_body(tweet, "Great Article")
        assert "## Great Article" in body
        assert "# Great Article\n\nSome body text." in body

    def test_references_section_with_tweet_link(self):
        tweet = _make_tweet(id="456", username="bob", article_content="Body text.")
        body = _format_article_body(tweet, "Body Text Summary")
        assert "## References" in body
        assert "- \U0001f517 [Original tweet](https://x.com/bob/status/456)" in body

    def test_none_handling(self):
        tweet = _make_tweet(article_content=None)
        body = _format_article_body(tweet, "Empty Article")
        assert "## Empty Article" in body
        assert "## References" in body


class TestReadAllExistingIds:
    def test_empty_dir(self, tmp_output_dir):
        result = read_existing_ids(tmp_output_dir)
        assert result == set()

    def test_frontmatter_scanning(self, tmp_output_dir):
        (tmp_output_dir / "2026-02-24-alice.md").write_text(
            '---\ntitle: "Hello"\ntweet_url: "https://x.com/alice/status/100"\n---\n> Hello\n'
        )
        (tmp_output_dir / "2026-02-24-bob.md").write_text(
            '---\ntitle: "World"\ntweet_url: "https://x.com/bob/status/200"\n---\n> World\n'
        )
        result = read_existing_ids(tmp_output_dir)
        assert result == {"100", "200"}

    def test_nonexistent_dir(self, tmp_path):
        result = read_existing_ids(tmp_path / "nonexistent")
        assert result == set()


class TestWriteBookmarks:
    def test_post_creation_with_faceted_schema(self, tmp_output_dir):
        """Post creation should emit pillar, mechanics, entity_tags in new faceted schema."""
        tweet = _make_tweet(id="123", username="alice")
        ct = CategorizedTweet(
            tweet=tweet,
            pillar="Applied Practice",
            title="Hello world",
            mechanics=("agent-orchestration",),
            tags=("framework/langgraph",),
        )
        stats = write_bookmarks((ct,), tmp_output_dir)

        assert (tmp_output_dir / "hello-world.md").exists()
        content = (tmp_output_dir / "hello-world.md").read_text()
        assert 'type: "post"' in content
        assert 'pillar: "Applied Practice"' in content
        assert "mechanics:" in content
        assert "  - agent-orchestration" in content
        assert "entity_tags:" in content
        assert "  framework: [langgraph]" in content
        assert "## Hello world" in content
        assert "> Hello world" in content
        assert "## References" in content
        assert stats["bookmarks_written"] == 1

    def test_article_creation_with_faceted_schema(self, tmp_output_dir):
        """Article creation should include article_url and faceted schema."""
        tweet = _make_tweet(
            id="456", username="bob",
            article_url="https://example.com/article",
            article_content="# Great Article\n\nBody text.",
        )
        ct = CategorizedTweet(
            tweet=tweet,
            pillar="Theory & Concepts",
            title="Great Article",
            mechanics=("research",),
            tags=("model/gpt-4", "tool/claude-api"),
        )
        stats = write_bookmarks((ct,), tmp_output_dir)

        assert (tmp_output_dir / "great-article.md").exists()
        content = (tmp_output_dir / "great-article.md").read_text()
        assert 'type: "article"' in content
        assert 'pillar: "Theory & Concepts"' in content
        assert 'article_url: "https://example.com/article"' in content
        assert "## Great Article" in content
        assert "# Great Article" in content
        assert "## References" in content
        assert stats["bookmarks_written"] == 1

    def test_dedup_skips_existing(self, tmp_output_dir):
        """Duplicate tweets should be skipped based on tweet_url ID extraction."""
        (tmp_output_dir / "2026-02-24-alice.md").write_text(
            '---\ntitle: "Hello"\ntweet_url: "https://x.com/alice/status/123"\n---\n> Hello\n'
        )
        tweet = _make_tweet(id="123", username="alice")
        ct = CategorizedTweet(
            tweet=tweet,
            pillar="Applied Practice",
            title="Hello world",
        )
        stats = write_bookmarks((ct,), tmp_output_dir)
        assert stats["duplicates_skipped"] == 1
        assert stats["bookmarks_written"] == 0

    def test_collisions_get_suffix(self, tmp_output_dir):
        """Files with same title should get numeric suffixes."""
        tweet1 = _make_tweet(id="1", username="alice", text="Same title")
        tweet2 = _make_tweet(id="2", username="alice", text="Same title")
        ct1 = CategorizedTweet(
            tweet=tweet1,
            pillar="Applied Practice",
            title="Same title",
        )
        ct2 = CategorizedTweet(
            tweet=tweet2,
            pillar="Applied Practice",
            title="Same title",
        )
        stats = write_bookmarks((ct1, ct2), tmp_output_dir)

        assert (tmp_output_dir / "same-title.md").exists()
        assert (tmp_output_dir / "same-title-2.md").exists()
        assert stats["bookmarks_written"] == 2

    def test_stats(self, tmp_output_dir):
        """Stats should correctly count written and skipped bookmarks."""
        tweet1 = _make_tweet(id="1")
        tweet2 = _make_tweet(id="2")
        ct1 = CategorizedTweet(
            tweet=tweet1,
            pillar="Applied Practice",
            title="Title 1",
        )
        ct2 = CategorizedTweet(
            tweet=tweet2,
            pillar="Theory & Concepts",
            title="Title 2",
        )
        stats = write_bookmarks((ct1, ct2), tmp_output_dir)
        assert stats["bookmarks_written"] == 2
        assert stats["duplicates_skipped"] == 0
        assert stats["files_written"] == 2

    def test_empty_input(self, tmp_output_dir):
        """Empty input should produce zero stats."""
        stats = write_bookmarks((), tmp_output_dir)
        assert stats["bookmarks_written"] == 0
        assert stats["files_written"] == 0
        assert stats["duplicates_skipped"] == 0

    def test_written_file_has_valid_yaml(self, tmp_output_dir):
        """Written files should always have valid YAML frontmatter."""
        tweet = _make_tweet(id="1", name="Alice O'Brien")
        ct = CategorizedTweet(
            tweet=tweet,
            pillar="Applied Practice",
            title="Test YAML Safety",
            mechanics=("optimization",),
            tags=("framework/langgraph", "model/gpt-4"),
        )
        write_bookmarks((ct,), tmp_output_dir)

        files = list(tmp_output_dir.glob("*.md"))
        assert len(files) == 1
        content = files[0].read_text()
        parts = content.split("---")
        yaml_body = parts[1]
        parsed = yaml.safe_load(yaml_body)
        assert parsed["title"] == "Test YAML Safety"
        assert parsed["pillar"] == "Applied Practice"
        assert parsed["mechanics"] == ["optimization"]
        assert "framework" in parsed["entity_tags"]

    def test_no_entity_tags_when_no_tags(self, tmp_output_dir):
        """When no tags provided, entity_tags block should be entirely absent."""
        tweet = _make_tweet(id="1")
        ct = CategorizedTweet(
            tweet=tweet,
            pillar="Strategy",
            title="No Tags Bookmark",
            mechanics=("business-strategy",),
            tags=(),
        )
        write_bookmarks((ct,), tmp_output_dir)

        content = list(tmp_output_dir.glob("*.md"))[0].read_text()
        assert "entity_tags:" not in content

    def test_mechanics_fallback_to_uncategorized(self, tmp_output_dir):
        """When mechanics is empty, the emitted file should have uncategorized."""
        tweet = _make_tweet(id="1")
        ct = CategorizedTweet(
            tweet=tweet,
            pillar="Theory & Concepts",
            title="No Mechanics",
            mechanics=(),  # empty
            tags=(),
        )
        write_bookmarks((ct,), tmp_output_dir)

        content = list(tmp_output_dir.glob("*.md"))[0].read_text()
        assert "  - uncategorized" in content
