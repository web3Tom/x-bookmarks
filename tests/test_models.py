import pytest
from datetime import datetime

from src.models import (
    User,
    Media,
    ExternalLink,
    Tweet,
    Category,
    CategorizedTweet,
    BookmarkPage,
)


class TestUser:
    def test_create_user(self):
        user = User(
            id="123",
            name="Test User",
            username="testuser",
            profile_image_url="https://example.com/img.jpg",
            verified=True,
        )
        assert user.id == "123"
        assert user.username == "testuser"
        assert user.verified is True

    def test_user_is_frozen(self):
        user = User(id="1", name="N", username="u", profile_image_url=None, verified=False)
        with pytest.raises(AttributeError):
            user.name = "changed"

    def test_user_from_api(self, sample_user_data):
        user = User.from_api(sample_user_data)
        assert user.id == "111222333"
        assert user.username == "testuser"
        assert user.verified is False


class TestMedia:
    def test_create_media(self):
        media = Media(
            media_key="3_123",
            type="photo",
            url="https://example.com/photo.jpg",
            preview_image_url=None,
            variants=(),
        )
        assert media.type == "photo"
        assert media.variants == ()

    def test_media_is_frozen(self):
        media = Media(media_key="k", type="photo", url="u", preview_image_url=None, variants=())
        with pytest.raises(AttributeError):
            media.type = "video"

    def test_media_from_api(self, sample_media_data):
        media = Media.from_api(sample_media_data)
        assert media.media_key == "3_1234567890"
        assert media.type == "photo"

    def test_media_from_api_with_variants(self):
        data = {
            "media_key": "7_999",
            "type": "video",
            "url": None,
            "preview_image_url": "https://example.com/preview.jpg",
            "variants": [
                {"bit_rate": 832000, "content_type": "video/mp4", "url": "https://example.com/vid.mp4"}
            ],
        }
        media = Media.from_api(data)
        assert media.type == "video"
        assert len(media.variants) == 1
        assert media.variants[0]["url"] == "https://example.com/vid.mp4"


class TestExternalLink:
    def test_create_link(self):
        link = ExternalLink(
            url="https://t.co/abc",
            expanded_url="https://example.com/article",
            display_url="example.com/article",
            title="Article Title",
        )
        assert link.expanded_url == "https://example.com/article"

    def test_link_is_frozen(self):
        link = ExternalLink(url="u", expanded_url="e", display_url="d", title=None)
        with pytest.raises(AttributeError):
            link.title = "new"


class TestTweet:
    def test_create_tweet(self):
        tweet = Tweet(
            id="1",
            text="Hello world",
            author_id="42",
            created_at=datetime(2025, 1, 15, 10, 30),
            author=None,
            public_metrics={"like_count": 10},
            media=(),
            external_links=(),
            note_tweet_text=None,
            article_url=None,
        )
        assert tweet.id == "1"
        assert tweet.media == ()

    def test_tweet_is_frozen(self):
        tweet = Tweet(
            id="1", text="t", author_id="a",
            created_at=datetime.now(), author=None,
            public_metrics={}, media=(), external_links=(),
            note_tweet_text=None, article_url=None,
        )
        with pytest.raises(AttributeError):
            tweet.text = "changed"

    def test_tweet_collections_are_tuples(self):
        tweet = Tweet(
            id="1", text="t", author_id="a",
            created_at=datetime.now(), author=None,
            public_metrics={}, media=(), external_links=(),
            note_tweet_text=None, article_url=None,
        )
        assert isinstance(tweet.media, tuple)
        assert isinstance(tweet.external_links, tuple)

    def test_tweet_display_text_prefers_note_tweet(self):
        tweet = Tweet(
            id="1", text="Short version",
            author_id="a", created_at=datetime.now(),
            author=None, public_metrics={},
            media=(), external_links=(),
            note_tweet_text="Full long-form version of the tweet",
            article_url=None,
        )
        assert tweet.display_text == "Full long-form version of the tweet"

    def test_tweet_display_text_falls_back_to_text(self):
        tweet = Tweet(
            id="1", text="Regular tweet",
            author_id="a", created_at=datetime.now(),
            author=None, public_metrics={},
            media=(), external_links=(),
            note_tweet_text=None, article_url=None,
        )
        assert tweet.display_text == "Regular tweet"

    def test_article_content_defaults_to_none(self):
        tweet = Tweet(
            id="1", text="t", author_id="a",
            created_at=datetime.now(), author=None,
            public_metrics={}, media=(), external_links=(),
            note_tweet_text=None, article_url=None,
        )
        assert tweet.article_content is None

    def test_article_content_stores_value(self):
        tweet = Tweet(
            id="1", text="t", author_id="a",
            created_at=datetime.now(), author=None,
            public_metrics={}, media=(), external_links=(),
            note_tweet_text=None, article_url="https://x.com/u/articles/1",
            article_content="# My Article\nBody text here.",
        )
        assert tweet.article_content == "# My Article\nBody text here."

    def test_article_content_is_frozen(self):
        tweet = Tweet(
            id="1", text="t", author_id="a",
            created_at=datetime.now(), author=None,
            public_metrics={}, media=(), external_links=(),
            note_tweet_text=None, article_url=None,
        )
        with pytest.raises(AttributeError):
            tweet.article_content = "new"

    def test_article_title_defaults_to_none(self):
        tweet = Tweet(
            id="1", text="t", author_id="a",
            created_at=datetime.now(), author=None,
            public_metrics={}, media=(), external_links=(),
            note_tweet_text=None, article_url=None,
        )
        assert tweet.article_title is None

    def test_article_title_stores_value(self):
        tweet = Tweet(
            id="1", text="t", author_id="a",
            created_at=datetime.now(), author=None,
            public_metrics={}, media=(), external_links=(),
            note_tweet_text=None, article_url="https://x.com/i/article/1",
            article_content="Body text",
            article_title="My Article Title",
        )
        assert tweet.article_title == "My Article Title"


class TestCategory:
    def test_create_category(self):
        cat = Category(slug="machine-learning", display_name="Machine Learning")
        assert cat.slug == "machine-learning"

    def test_category_is_frozen(self):
        cat = Category(slug="s", display_name="d")
        with pytest.raises(AttributeError):
            cat.slug = "new"


class TestCategorizedTweet:
    def test_create_categorized_tweet(self):
        tweet = Tweet(
            id="1", text="t", author_id="a",
            created_at=datetime.now(), author=None,
            public_metrics={}, media=(), external_links=(),
            note_tweet_text=None, article_url=None,
        )
        cat = Category(slug="python", display_name="Python")
        ct = CategorizedTweet(tweet=tweet, category=cat)
        assert ct.category.slug == "python"


class TestBookmarkPage:
    def test_create_page(self):
        tweet = Tweet(
            id="1", text="t", author_id="a",
            created_at=datetime.now(), author=None,
            public_metrics={}, media=(), external_links=(),
            note_tweet_text=None, article_url=None,
        )
        page = BookmarkPage(tweets=(tweet,), next_token="abc123")
        assert len(page.tweets) == 1
        assert page.next_token == "abc123"

    def test_page_no_next_token(self):
        page = BookmarkPage(tweets=(), next_token=None)
        assert page.next_token is None

    def test_page_is_frozen(self):
        page = BookmarkPage(tweets=(), next_token=None)
        with pytest.raises(AttributeError):
            page.next_token = "new"
