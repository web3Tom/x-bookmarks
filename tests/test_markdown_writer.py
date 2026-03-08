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
)
from src.models import (
    Tweet, User, Media, ExternalLink, Category, CategorizedTweet,
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


def _make_category(
    slug: str = "ai-agents",
    display_name: str = "AI Agents",
    sub_category: str = "Applied Agents",
) -> Category:
    return Category(slug=slug, display_name=display_name, sub_category=sub_category)


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
        # Title that would end with a hyphen when truncated
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


class TestBuildFrontmatter:
    def test_post_fields(self):
        tweet = _make_tweet()
        cat = _make_category()
        fm = _build_frontmatter(tweet, cat, "post", "Hello world")
        assert fm.startswith("---\n")
        assert fm.endswith("---\n")
        assert 'title: "Hello world"' in fm
        assert 'author: "@alice"' in fm
        assert 'category: "AI Agents"' in fm
        assert 'subCategory: "Applied Agents"' in fm
        assert "date: 2026-02-24" in fm
        assert "read: false" in fm
        assert 'type: "post"' in fm
        assert 'tweet_url: "https://x.com/alice/status/1"' in fm
        assert "author_name" not in fm
        assert "tweet_id:" not in fm
        assert "likes:" not in fm
        assert "retweets:" not in fm
        assert "replies:" not in fm
        assert "bookmarks:" not in fm
        assert "has_media:" not in fm
        assert "has_links:" not in fm

    def test_frontmatter_is_valid_yaml(self):
        tweet = _make_tweet()
        cat = _make_category()
        fm = _build_frontmatter(tweet, cat, "post", "Hello world")
        lines = fm.strip().split("\n")
        yaml_body = "\n".join(lines[1:-1])
        parsed = yaml.safe_load(yaml_body)
        assert parsed["title"] == "Hello world"
        assert parsed["category"] == "AI Agents"
        assert parsed["subCategory"] == "Applied Agents"
        assert parsed["type"] == "post"

    def test_subcategory_in_frontmatter(self):
        tweet = _make_tweet()
        cat = _make_category(sub_category="Coding Workflows")
        fm = _build_frontmatter(tweet, cat, "post", "Test Title")
        assert 'subCategory: "Coding Workflows"' in fm

    def test_subcategory_after_category(self):
        tweet = _make_tweet()
        cat = _make_category()
        fm = _build_frontmatter(tweet, cat, "post", "Test Title")
        lines = fm.split("\n")
        cat_idx = next(i for i, l in enumerate(lines) if l.startswith("category:"))
        sub_idx = next(i for i, l in enumerate(lines) if l.startswith("subCategory:"))
        assert sub_idx == cat_idx + 1

    def test_article_fields(self):
        tweet = _make_tweet(
            article_url="https://x.com/alice/articles/1",
            article_content="Some content",
        )
        cat = _make_category(slug="tech", display_name="Tech", sub_category="General")
        fm = _build_frontmatter(tweet, cat, "article", "My Great Article")
        assert 'type: "article"' in fm
        assert 'article_url: "https://x.com/alice/articles/1"' in fm
        assert 'title: "My Great Article"' in fm

    def test_explicit_title_used(self):
        tweet = _make_tweet()
        cat = _make_category()
        fm = _build_frontmatter(tweet, cat, "post", "Claude Generated Title")
        assert 'title: "Claude Generated Title"' in fm

    def test_quote_escaping_in_title(self):
        tweet = _make_tweet()
        cat = _make_category()
        fm = _build_frontmatter(tweet, cat, "post", 'He said "hello" to me')
        assert 'title: "He said \\"hello\\" to me"' in fm

    def test_ampersand_in_subcategory_valid_yaml(self):
        tweet = _make_tweet()
        cat = _make_category(sub_category="Inference & Serving")
        fm = _build_frontmatter(tweet, cat, "post", "Test Title")
        lines = fm.strip().split("\n")
        yaml_body = "\n".join(lines[1:-1])
        parsed = yaml.safe_load(yaml_body)
        assert parsed["subCategory"] == "Inference & Serving"

    def test_removed_fields_not_present(self):
        media = Media(
            media_key="3_100", type="photo",
            url="https://pbs.twimg.com/media/photo.jpg",
            preview_image_url=None, variants=(),
        )
        link = ExternalLink(
            url="https://t.co/abc",
            expanded_url="https://example.com",
            display_url="example.com",
            title="Example",
        )
        tweet = _make_tweet(media=(media,), external_links=(link,))
        cat = _make_category()
        fm = _build_frontmatter(tweet, cat, "post", "Test Title")
        assert "has_media:" not in fm
        assert "has_links:" not in fm
        assert "likes:" not in fm
        assert "author_name:" not in fm


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
            'category: "Model Systems"\n'
            'subCategory: "Inference & Serving"\n'
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
        # External links should be in References section
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
        # Media should be in title section, before References
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

    def test_index_md_skipped(self, tmp_output_dir):
        (tmp_output_dir / "index.md").write_text(
            '---\ntitle: X Bookmarks\ntweet_url: "https://x.com/x/status/999"\n---\nDataview query\n'
        )
        (tmp_output_dir / "2026-02-24-alice.md").write_text(
            '---\ntitle: "Hello"\ntweet_url: "https://x.com/alice/status/100"\n---\n> Hello\n'
        )
        result = read_existing_ids(tmp_output_dir)
        assert result == {"100"}

    def test_nonexistent_dir(self, tmp_path):
        result = read_existing_ids(tmp_path / "nonexistent")
        assert result == set()


class TestWriteBookmarks:
    def test_post_creation(self, tmp_output_dir):
        cat = _make_category()
        tweet = _make_tweet(id="123", username="alice")
        ct = CategorizedTweet(tweet=tweet, category=cat, title="Hello world")
        stats = write_bookmarks((ct,), tmp_output_dir)

        assert (tmp_output_dir / "hello-world.md").exists()
        content = (tmp_output_dir / "hello-world.md").read_text()
        assert 'type: "post"' in content
        assert "## Hello world" in content
        assert "> Hello world" in content
        assert "## References" in content
        assert stats["bookmarks_written"] == 1

    def test_article_creation(self, tmp_output_dir):
        cat = _make_category(slug="tech", display_name="Tech", sub_category="General")
        tweet = _make_tweet(
            id="456", username="bob",
            article_url="https://x.com/bob/articles/456",
            article_content="# Great Article\n\nBody text.",
        )
        ct = CategorizedTweet(tweet=tweet, category=cat, title="Great Article")
        stats = write_bookmarks((ct,), tmp_output_dir)

        assert (tmp_output_dir / "great-article.md").exists()
        content = (tmp_output_dir / "great-article.md").read_text()
        assert 'type: "article"' in content
        assert "## Great Article" in content
        assert "# Great Article" in content
        assert "## References" in content
        assert stats["bookmarks_written"] == 1

    def test_dedup_skips_existing(self, tmp_output_dir):
        (tmp_output_dir / "2026-02-24-alice.md").write_text(
            '---\ntitle: "Hello"\ntweet_url: "https://x.com/alice/status/123"\n---\n> Hello\n'
        )
        cat = _make_category()
        tweet = _make_tweet(id="123", username="alice")
        ct = CategorizedTweet(tweet=tweet, category=cat, title="Hello world")
        stats = write_bookmarks((ct,), tmp_output_dir)
        assert stats["duplicates_skipped"] == 1
        assert stats["bookmarks_written"] == 0

    def test_collisions_get_suffix(self, tmp_output_dir):
        cat = _make_category()
        tweet1 = _make_tweet(id="1", username="alice", text="Same title")
        tweet2 = _make_tweet(id="2", username="alice", text="Same title")
        ct1 = CategorizedTweet(tweet=tweet1, category=cat, title="Same title")
        ct2 = CategorizedTweet(tweet=tweet2, category=cat, title="Same title")
        stats = write_bookmarks((ct1, ct2), tmp_output_dir)

        assert (tmp_output_dir / "same-title.md").exists()
        assert (tmp_output_dir / "same-title-2.md").exists()
        assert stats["bookmarks_written"] == 2

    def test_stats(self, tmp_output_dir):
        cat = _make_category()
        tweet1 = _make_tweet(id="1")
        tweet2 = _make_tweet(id="2")
        ct1 = CategorizedTweet(tweet=tweet1, category=cat, title="Title 1")
        ct2 = CategorizedTweet(tweet=tweet2, category=cat, title="Title 2")
        stats = write_bookmarks((ct1, ct2), tmp_output_dir)
        assert stats["bookmarks_written"] == 2
        assert stats["duplicates_skipped"] == 0
        assert stats["files_written"] == 2

    def test_empty_input(self, tmp_output_dir):
        stats = write_bookmarks((), tmp_output_dir)
        assert stats["bookmarks_written"] == 0
        assert stats["files_written"] == 0
        assert stats["duplicates_skipped"] == 0

    def test_written_file_has_valid_yaml(self, tmp_output_dir):
        cat = _make_category(sub_category="Inference & Serving")
        tweet = _make_tweet(id="1", name="Alice O'Brien")
        ct = CategorizedTweet(tweet=tweet, category=cat, title="Test YAML Safety")
        write_bookmarks((ct,), tmp_output_dir)

        files = [f for f in tmp_output_dir.glob("*.md") if f.name != "index.md"]
        assert len(files) == 1
        content = files[0].read_text()
        # Extract YAML between --- markers
        parts = content.split("---")
        yaml_body = parts[1]
        parsed = yaml.safe_load(yaml_body)
        assert parsed["title"] == "Test YAML Safety"
        assert parsed["subCategory"] == "Inference & Serving"


