import pytest
from datetime import datetime
from pathlib import Path

from src.markdown_writer import (
    _build_filename,
    _build_frontmatter,
    _format_post_body,
    _format_article_body,
    _read_all_existing_ids,
    _write_index_file,
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


class TestBuildFilename:
    def test_basic_naming(self):
        tweet = _make_tweet(username="alice", created_at=datetime(2026, 2, 24))
        result = _build_filename(tweet, set())
        assert result == "2026-02-24-alice.md"

    def test_unknown_author(self):
        tweet = Tweet(
            id="1", text="Hello", author_id="10",
            created_at=datetime(2026, 2, 24),
            author=None,
            public_metrics={}, media=(), external_links=(),
            note_tweet_text=None, article_url=None,
        )
        result = _build_filename(tweet, set())
        assert result == "2026-02-24-unknown.md"

    def test_collision_adds_suffix(self):
        tweet = _make_tweet(username="alice", created_at=datetime(2026, 2, 24))
        existing = {"2026-02-24-alice.md"}
        result = _build_filename(tweet, existing)
        assert result == "2026-02-24-alice-2.md"

    def test_multiple_collisions(self):
        tweet = _make_tweet(username="alice", created_at=datetime(2026, 2, 24))
        existing = {"2026-02-24-alice.md", "2026-02-24-alice-2.md"}
        result = _build_filename(tweet, existing)
        assert result == "2026-02-24-alice-3.md"


class TestBuildFrontmatter:
    def test_post_fields(self):
        tweet = _make_tweet()
        cat = Category(slug="ai-agents", display_name="AI Agents")
        fm = _build_frontmatter(tweet, cat, "post")
        assert fm.startswith("---\n")
        assert fm.endswith("---\n")
        assert 'author: "@alice"' in fm
        assert "author_name: Alice" in fm
        assert "category: AI Agents" in fm
        assert "date: 2026-02-24" in fm
        assert "read: false" in fm
        assert "type: post" in fm
        assert 'tweet_id: "1"' in fm
        assert 'tweet_url: "https://x.com/alice/status/1"' in fm
        assert "likes: 196" in fm
        assert "retweets: 12" in fm
        assert "replies: 7" in fm
        assert "bookmarks: 319" in fm
        assert "has_media: false" in fm
        assert "has_links: false" in fm

    def test_article_fields(self):
        tweet = _make_tweet(
            article_url="https://x.com/alice/articles/1",
            article_title="My Great Article",
            article_content="Some content",
        )
        cat = Category(slug="tech", display_name="Tech")
        fm = _build_frontmatter(tweet, cat, "article")
        assert "type: article" in fm
        assert 'article_url: "https://x.com/alice/articles/1"' in fm
        assert 'title: "My Great Article"' in fm

    def test_untitled_fallback(self):
        tweet = _make_tweet()
        cat = Category(slug="tech", display_name="Tech")
        fm = _build_frontmatter(tweet, cat, "post")
        assert 'title: "Hello world"' in fm

    def test_title_truncation(self):
        long_text = "A" * 200
        tweet = _make_tweet(text=long_text)
        cat = Category(slug="tech", display_name="Tech")
        fm = _build_frontmatter(tweet, cat, "post")
        # Title should be truncated to 80 chars + "..."
        lines = fm.split("\n")
        title_line = [l for l in lines if l.startswith("title:")][0]
        # Extract value between quotes
        title_val = title_line.split('"')[1]
        assert len(title_val) == 83  # 80 + "..."

    def test_quote_escaping(self):
        tweet = _make_tweet(text='He said "hello" to me')
        cat = Category(slug="tech", display_name="Tech")
        fm = _build_frontmatter(tweet, cat, "post")
        assert 'title: "He said \\"hello\\" to me"' in fm

    def test_metrics(self):
        tweet = _make_tweet(like_count=0, retweet_count=0, reply_count=0, bookmark_count=0)
        cat = Category(slug="tech", display_name="Tech")
        fm = _build_frontmatter(tweet, cat, "post")
        assert "likes: 0" in fm
        assert "retweets: 0" in fm

    def test_has_media_true(self):
        media = Media(
            media_key="3_100", type="photo",
            url="https://pbs.twimg.com/media/photo.jpg",
            preview_image_url=None, variants=(),
        )
        tweet = _make_tweet(media=(media,))
        cat = Category(slug="tech", display_name="Tech")
        fm = _build_frontmatter(tweet, cat, "post")
        assert "has_media: true" in fm

    def test_has_links_true(self):
        link = ExternalLink(
            url="https://t.co/abc",
            expanded_url="https://example.com",
            display_url="example.com",
            title="Example",
        )
        tweet = _make_tweet(external_links=(link,))
        cat = Category(slug="tech", display_name="Tech")
        fm = _build_frontmatter(tweet, cat, "post")
        assert "has_links: true" in fm


class TestFormatPostBody:
    def test_blockquote(self):
        tweet = _make_tweet(text="Hello world")
        body = _format_post_body(tweet)
        assert "> Hello world" in body

    def test_multiline_blockquote(self):
        tweet = _make_tweet(text="Line 1\nLine 2\nLine 3")
        body = _format_post_body(tweet)
        assert "> Line 1" in body
        assert "> Line 2" in body
        assert "> Line 3" in body

    def test_tweet_link(self):
        tweet = _make_tweet(id="999", username="bob")
        body = _format_post_body(tweet)
        assert "\U0001f517 [Original tweet](https://x.com/bob/status/999)" in body

    def test_external_links(self):
        link = ExternalLink(
            url="https://t.co/abc",
            expanded_url="https://example.com/article",
            display_url="example.com/article",
            title="Great Article",
        )
        tweet = _make_tweet(external_links=(link,))
        body = _format_post_body(tweet)
        assert "\U0001f310 [Great Article](https://example.com/article)" in body

    def test_external_link_uses_display_url_when_no_title(self):
        link = ExternalLink(
            url="https://t.co/abc",
            expanded_url="https://example.com/page",
            display_url="example.com/page",
            title=None,
        )
        tweet = _make_tweet(external_links=(link,))
        body = _format_post_body(tweet)
        assert "\U0001f310 [example.com/page](https://example.com/page)" in body

    def test_media(self):
        media = Media(
            media_key="3_100", type="photo",
            url="https://pbs.twimg.com/media/photo.jpg",
            preview_image_url=None, variants=(),
        )
        tweet = _make_tweet(media=(media,))
        body = _format_post_body(tweet)
        assert "\U0001f4f7 [photo](https://pbs.twimg.com/media/photo.jpg)" in body

    def test_note_tweet_uses_display_text(self):
        tweet = _make_tweet(text="Short", note_tweet_text="Full long-form text here")
        body = _format_post_body(tweet)
        assert "> Full long-form text here" in body
        assert "Short" not in body


class TestFormatArticleBody:
    def test_content_passthrough(self):
        tweet = _make_tweet(article_content="# Great Article\n\nSome body text.")
        body = _format_article_body(tweet)
        assert body == "# Great Article\n\nSome body text."

    def test_none_handling(self):
        tweet = _make_tweet(article_content=None)
        body = _format_article_body(tweet)
        assert body == ""


class TestReadAllExistingIds:
    def test_empty_dir(self, tmp_output_dir):
        result = _read_all_existing_ids(tmp_output_dir)
        assert result == set()

    def test_frontmatter_scanning(self, tmp_output_dir):
        (tmp_output_dir / "2026-02-24-alice.md").write_text(
            '---\ntitle: "Hello"\ntweet_id: "100"\n---\n> Hello\n'
        )
        (tmp_output_dir / "2026-02-24-bob.md").write_text(
            '---\ntitle: "World"\ntweet_id: "200"\n---\n> World\n'
        )
        result = _read_all_existing_ids(tmp_output_dir)
        assert result == {"100", "200"}

    def test_index_md_skipped(self, tmp_output_dir):
        (tmp_output_dir / "index.md").write_text(
            '---\ntitle: X Bookmarks\ntweet_id: "999"\n---\nDataview query\n'
        )
        (tmp_output_dir / "2026-02-24-alice.md").write_text(
            '---\ntitle: "Hello"\ntweet_id: "100"\n---\n> Hello\n'
        )
        result = _read_all_existing_ids(tmp_output_dir)
        assert result == {"100"}

    def test_nonexistent_dir(self, tmp_path):
        result = _read_all_existing_ids(tmp_path / "nonexistent")
        assert result == set()


class TestWriteBookmarks:
    def test_post_creation(self, tmp_output_dir):
        cat = Category(slug="ai-agents", display_name="AI Agents")
        tweet = _make_tweet(id="123", username="alice")
        ct = CategorizedTweet(tweet=tweet, category=cat)
        stats = write_bookmarks((ct,), tmp_output_dir)

        files = list(tmp_output_dir.glob("2026-02-24-alice.md"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "type: post" in content
        assert "> Hello world" in content
        assert stats["bookmarks_written"] == 1

    def test_article_creation(self, tmp_output_dir):
        cat = Category(slug="tech", display_name="Tech")
        tweet = _make_tweet(
            id="456", username="bob",
            article_url="https://x.com/bob/articles/456",
            article_content="# Great Article\n\nBody text.",
            article_title="Great Article",
        )
        ct = CategorizedTweet(tweet=tweet, category=cat)
        stats = write_bookmarks((ct,), tmp_output_dir)

        files = list(tmp_output_dir.glob("2026-02-24-bob.md"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "type: article" in content
        assert "# Great Article" in content
        assert "Body text." in content
        # No blockquote for articles
        assert "> Hello world" not in content
        assert stats["bookmarks_written"] == 1

    def test_dedup_skips_existing(self, tmp_output_dir):
        # Pre-create a file with tweet_id 123
        (tmp_output_dir / "2026-02-24-alice.md").write_text(
            '---\ntitle: "Hello"\ntweet_id: "123"\n---\n> Hello\n'
        )
        cat = Category(slug="tech", display_name="Tech")
        tweet = _make_tweet(id="123", username="alice")
        ct = CategorizedTweet(tweet=tweet, category=cat)
        stats = write_bookmarks((ct,), tmp_output_dir)
        assert stats["duplicates_skipped"] == 1
        assert stats["bookmarks_written"] == 0

    def test_collisions_get_suffix(self, tmp_output_dir):
        cat = Category(slug="tech", display_name="Tech")
        tweet1 = _make_tweet(id="1", username="alice", text="First tweet")
        tweet2 = _make_tweet(id="2", username="alice", text="Second tweet")
        ct1 = CategorizedTweet(tweet=tweet1, category=cat)
        ct2 = CategorizedTweet(tweet=tweet2, category=cat)
        stats = write_bookmarks((ct1, ct2), tmp_output_dir)

        assert (tmp_output_dir / "2026-02-24-alice.md").exists()
        assert (tmp_output_dir / "2026-02-24-alice-2.md").exists()
        assert stats["bookmarks_written"] == 2

    def test_index_creation(self, tmp_output_dir):
        cat = Category(slug="tech", display_name="Tech")
        tweet = _make_tweet(id="1")
        ct = CategorizedTweet(tweet=tweet, category=cat)
        write_bookmarks((ct,), tmp_output_dir)

        index = tmp_output_dir / "index.md"
        assert index.exists()
        content = index.read_text()
        assert "dataview" in content.lower()
        assert "X Bookmarks" in content

    def test_stats(self, tmp_output_dir):
        cat = Category(slug="tech", display_name="Tech")
        tweet1 = _make_tweet(id="1")
        tweet2 = _make_tweet(id="2")
        ct1 = CategorizedTweet(tweet=tweet1, category=cat)
        ct2 = CategorizedTweet(tweet=tweet2, category=cat)
        stats = write_bookmarks((ct1, ct2), tmp_output_dir)
        assert stats["bookmarks_written"] == 2
        assert stats["duplicates_skipped"] == 0
        assert stats["files_written"] == 2  # 2 bookmark files

    def test_empty_input(self, tmp_output_dir):
        stats = write_bookmarks((), tmp_output_dir)
        assert stats["bookmarks_written"] == 0
        assert stats["files_written"] == 0
        assert stats["duplicates_skipped"] == 0
        # Index should still be written
        assert (tmp_output_dir / "index.md").exists()


class TestWriteIndexFile:
    def test_dataview_query_present(self, tmp_output_dir):
        _write_index_file(tmp_output_dir)
        content = (tmp_output_dir / "index.md").read_text()
        assert "```dataview" in content
        assert "TABLE" in content
        assert "SORT date DESC" in content

    def test_title_frontmatter(self, tmp_output_dir):
        _write_index_file(tmp_output_dir)
        content = (tmp_output_dir / "index.md").read_text()
        assert content.startswith("---\n")
        assert "title: X Bookmarks" in content

    def test_overwrite_behavior(self, tmp_output_dir):
        (tmp_output_dir / "index.md").write_text("old content")
        _write_index_file(tmp_output_dir)
        content = (tmp_output_dir / "index.md").read_text()
        assert "old content" not in content
        assert "dataview" in content.lower()
