import pytest
import httpx
import respx
from datetime import datetime

from src.api_client import (
    fetch_bookmarks,
    refresh_access_token,
    parse_tweet,
    parse_bookmarks_response,
    BOOKMARKS_URL,
    TOKEN_URL,
)
from src.models import Tweet, User, Media, ExternalLink, BookmarkPage
from src.config import Config
from pathlib import Path


@pytest.fixture
def config(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CLIENT_ID=test_client\n"
        "ACCESS_TOKEN=test_access\n"
        "REFRESH_TOKEN=test_refresh\n"
        "USER_ID=999\n"
        "ANTHROPIC_API_KEY=sk-ant-test\n"
    )
    return Config(
        client_id="test_client",
        client_secret=None,
        access_token="test_access",
        refresh_token="test_refresh",
        user_id="999",
        anthropic_api_key="sk-ant-test",
        output_dir=tmp_path,
    )


@pytest.fixture
def full_api_response():
    return {
        "data": [
            {
                "id": "100",
                "text": "Check out this article https://t.co/abc123",
                "author_id": "42",
                "created_at": "2025-03-10T14:30:00.000Z",
                "public_metrics": {
                    "retweet_count": 10,
                    "reply_count": 2,
                    "like_count": 50,
                    "quote_count": 1,
                    "bookmark_count": 5,
                    "impression_count": 2000,
                },
                "entities": {
                    "urls": [
                        {
                            "start": 22,
                            "end": 45,
                            "url": "https://t.co/abc123",
                            "expanded_url": "https://example.com/article",
                            "display_url": "example.com/article",
                            "title": "Great Article",
                        }
                    ]
                },
            },
            {
                "id": "101",
                "text": "A short tweet",
                "author_id": "43",
                "created_at": "2025-03-11T09:00:00.000Z",
                "public_metrics": {
                    "retweet_count": 0,
                    "reply_count": 0,
                    "like_count": 1,
                    "quote_count": 0,
                    "bookmark_count": 0,
                    "impression_count": 100,
                },
            },
        ],
        "includes": {
            "users": [
                {
                    "id": "42",
                    "name": "Alice",
                    "username": "alice",
                    "profile_image_url": "https://pbs.twimg.com/alice.jpg",
                    "verified": True,
                },
                {
                    "id": "43",
                    "name": "Bob",
                    "username": "bob",
                    "profile_image_url": None,
                    "verified": False,
                },
            ],
            "media": [
                {
                    "media_key": "3_200",
                    "type": "photo",
                    "url": "https://pbs.twimg.com/media/photo.jpg",
                }
            ],
        },
        "meta": {"result_count": 2, "next_token": "abc_next"},
    }


class TestParseTweet:
    def test_parse_basic_tweet(self):
        data = {
            "id": "1",
            "text": "Hello world",
            "author_id": "10",
            "created_at": "2025-01-01T00:00:00.000Z",
            "public_metrics": {"like_count": 5},
        }
        tweet = parse_tweet(data, users_lookup={}, media_lookup={})
        assert tweet.id == "1"
        assert tweet.text == "Hello world"
        assert tweet.author is None
        assert tweet.media == ()
        assert tweet.external_links == ()

    def test_parse_tweet_with_author(self):
        data = {
            "id": "1",
            "text": "Hi",
            "author_id": "10",
            "created_at": "2025-01-01T00:00:00.000Z",
            "public_metrics": {},
        }
        user = User(id="10", name="Test", username="test", profile_image_url=None, verified=False)
        tweet = parse_tweet(data, users_lookup={"10": user}, media_lookup={})
        assert tweet.author is not None
        assert tweet.author.username == "test"

    def test_parse_tweet_filters_external_links(self):
        data = {
            "id": "1",
            "text": "Check links",
            "author_id": "10",
            "created_at": "2025-01-01T00:00:00.000Z",
            "public_metrics": {},
            "entities": {
                "urls": [
                    {
                        "url": "https://t.co/a",
                        "expanded_url": "https://example.com/article",
                        "display_url": "example.com/article",
                        "title": "Article",
                    },
                    {
                        "url": "https://t.co/b",
                        "expanded_url": "https://x.com/user/status/123",
                        "display_url": "x.com/user/status/123",
                    },
                    {
                        "url": "https://t.co/c",
                        "expanded_url": "https://twitter.com/user/status/456",
                        "display_url": "twitter.com/user/status/456",
                    },
                ]
            },
        }
        tweet = parse_tweet(data, users_lookup={}, media_lookup={})
        assert len(tweet.external_links) == 1
        assert tweet.external_links[0].expanded_url == "https://example.com/article"

    def test_parse_tweet_with_note_tweet(self):
        data = {
            "id": "1",
            "text": "Short version...",
            "author_id": "10",
            "created_at": "2025-01-01T00:00:00.000Z",
            "public_metrics": {},
            "note_tweet": {"text": "This is the full long-form tweet text"},
        }
        tweet = parse_tweet(data, users_lookup={}, media_lookup={})
        assert tweet.note_tweet_text == "This is the full long-form tweet text"

    def test_parse_tweet_with_article_url(self):
        data = {
            "id": "1",
            "text": "Read my article",
            "author_id": "10",
            "created_at": "2025-01-01T00:00:00.000Z",
            "public_metrics": {},
            "entities": {
                "urls": [
                    {
                        "url": "https://t.co/art",
                        "expanded_url": "https://x.com/i/article/123456",
                        "display_url": "Article Title",
                        "title": "My Article",
                    }
                ]
            },
        }
        tweet = parse_tweet(data, users_lookup={}, media_lookup={})
        assert tweet.article_url == "https://x.com/i/article/123456"

    def test_old_article_url_format_not_detected(self):
        data = {
            "id": "1",
            "text": "Old format",
            "author_id": "10",
            "created_at": "2025-01-01T00:00:00.000Z",
            "public_metrics": {},
            "entities": {
                "urls": [
                    {
                        "url": "https://t.co/art",
                        "expanded_url": "https://x.com/user/articles/123",
                        "display_url": "Article Title",
                        "title": "My Article",
                    }
                ]
            },
        }
        tweet = parse_tweet(data, users_lookup={}, media_lookup={})
        assert tweet.article_url is None

    def test_parse_tweet_extracts_article_content_and_title(self):
        data = {
            "id": "1",
            "text": "Read my article",
            "author_id": "10",
            "created_at": "2025-01-01T00:00:00.000Z",
            "public_metrics": {},
            "article": {
                "title": "My Great Article",
                "plain_text": "This is the full article body text.",
            },
        }
        tweet = parse_tweet(data, users_lookup={}, media_lookup={})
        assert tweet.article_content == "This is the full article body text."
        assert tweet.article_title == "My Great Article"

    def test_parse_tweet_no_article_field(self):
        data = {
            "id": "1",
            "text": "No article",
            "author_id": "10",
            "created_at": "2025-01-01T00:00:00.000Z",
            "public_metrics": {},
        }
        tweet = parse_tweet(data, users_lookup={}, media_lookup={})
        assert tweet.article_content is None
        assert tweet.article_title is None

    def test_parse_tweet_with_media(self):
        data = {
            "id": "1",
            "text": "Photo tweet",
            "author_id": "10",
            "created_at": "2025-01-01T00:00:00.000Z",
            "public_metrics": {},
            "attachments": {"media_keys": ["3_100"]},
        }
        media = Media(media_key="3_100", type="photo", url="https://example.com/img.jpg", preview_image_url=None, variants=())
        tweet = parse_tweet(data, users_lookup={}, media_lookup={"3_100": media})
        assert len(tweet.media) == 1
        assert tweet.media[0].url == "https://example.com/img.jpg"

    def test_parse_tweet_datetime(self):
        data = {
            "id": "1",
            "text": "t",
            "author_id": "10",
            "created_at": "2025-06-15T08:30:45.000Z",
            "public_metrics": {},
        }
        tweet = parse_tweet(data, users_lookup={}, media_lookup={})
        assert tweet.created_at == datetime(2025, 6, 15, 8, 30, 45)


class TestParseBookmarksResponse:
    def test_parse_full_response(self, full_api_response):
        page = parse_bookmarks_response(full_api_response)
        assert len(page.tweets) == 2
        assert page.next_token == "abc_next"
        assert page.tweets[0].author.username == "alice"
        assert page.tweets[1].author.username == "bob"

    def test_parse_empty_response(self):
        response = {"meta": {"result_count": 0}}
        page = parse_bookmarks_response(response)
        assert page.tweets == ()
        assert page.next_token is None

    def test_parse_response_no_next_token(self, full_api_response):
        del full_api_response["meta"]["next_token"]
        page = parse_bookmarks_response(full_api_response)
        assert page.next_token is None


class TestFetchBookmarks:
    @respx.mock
    def test_fetch_single_page(self, config):
        url = BOOKMARKS_URL.format(user_id=config.user_id)
        respx.get(url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "1",
                            "text": "Hello",
                            "author_id": "10",
                            "created_at": "2025-01-01T00:00:00.000Z",
                            "public_metrics": {"like_count": 1},
                        }
                    ],
                    "includes": {
                        "users": [
                            {"id": "10", "name": "U", "username": "u", "verified": False}
                        ]
                    },
                    "meta": {"result_count": 1},
                },
            )
        )
        tweets = fetch_bookmarks(config)
        assert len(tweets) == 1
        assert tweets[0].id == "1"

    @respx.mock
    def test_fetch_paginated(self, config):
        url = BOOKMARKS_URL.format(user_id=config.user_id)
        respx.get(url, params__contains={"pagination_token": "page2"}).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "2",
                            "text": "Second",
                            "author_id": "10",
                            "created_at": "2025-01-02T00:00:00.000Z",
                            "public_metrics": {},
                        }
                    ],
                    "includes": {
                        "users": [
                            {"id": "10", "name": "U", "username": "u", "verified": False}
                        ]
                    },
                    "meta": {"result_count": 1},
                },
            )
        )
        respx.get(url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "1",
                            "text": "First",
                            "author_id": "10",
                            "created_at": "2025-01-01T00:00:00.000Z",
                            "public_metrics": {},
                        }
                    ],
                    "includes": {
                        "users": [
                            {"id": "10", "name": "U", "username": "u", "verified": False}
                        ]
                    },
                    "meta": {"result_count": 1, "next_token": "page2"},
                },
            )
        )

        tweets = fetch_bookmarks(config)
        assert len(tweets) == 2

    @respx.mock
    def test_token_refresh_on_401(self, config, tmp_path):
        url = BOOKMARKS_URL.format(user_id=config.user_id)
        env_file = tmp_path / ".env"
        env_file.write_text(
            "CLIENT_ID=test_client\n"
            "ACCESS_TOKEN=test_access\n"
            "REFRESH_TOKEN=test_refresh\n"
            "USER_ID=999\n"
            "ANTHROPIC_API_KEY=sk-ant-test\n"
        )

        call_count = {"n": 0}

        def side_effect(request):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(401, json={"detail": "Unauthorized"})
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "1",
                            "text": "After refresh",
                            "author_id": "10",
                            "created_at": "2025-01-01T00:00:00.000Z",
                            "public_metrics": {},
                        }
                    ],
                    "includes": {
                        "users": [
                            {"id": "10", "name": "U", "username": "u", "verified": False}
                        ]
                    },
                    "meta": {"result_count": 1},
                },
            )

        respx.get(url).mock(side_effect=side_effect)
        respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new_access",
                    "refresh_token": "new_refresh",
                    "token_type": "bearer",
                    "expires_in": 7200,
                },
            )
        )

        tweets = fetch_bookmarks(config, env_path=env_file)
        assert len(tweets) == 1
        assert tweets[0].text == "After refresh"

    @respx.mock
    def test_empty_bookmarks(self, config):
        url = BOOKMARKS_URL.format(user_id=config.user_id)
        respx.get(url).mock(
            return_value=httpx.Response(
                200,
                json={"meta": {"result_count": 0}},
            )
        )
        tweets = fetch_bookmarks(config)
        assert tweets == ()


class TestRefreshToken:
    @respx.mock
    def test_refresh_returns_new_tokens(self, config, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "CLIENT_ID=test_client\n"
            "ACCESS_TOKEN=old_access\n"
            "REFRESH_TOKEN=old_refresh\n"
            "USER_ID=999\n"
            "ANTHROPIC_API_KEY=sk-ant-test\n"
        )
        respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "new_access",
                    "refresh_token": "new_refresh",
                    "token_type": "bearer",
                    "expires_in": 7200,
                },
            )
        )
        new_config = refresh_access_token(config, env_path=env_file)
        assert new_config.access_token == "new_access"
        assert new_config.refresh_token == "new_refresh"

        content = env_file.read_text()
        assert "new_access" in content
        assert "new_refresh" in content
