import pytest
from pathlib import Path


@pytest.fixture
def sample_tweet_data():
    """Raw API response data for a single tweet."""
    return {
        "id": "1234567890",
        "text": "This is a great article about Python testing https://t.co/abc123",
        "author_id": "111222333",
        "created_at": "2025-01-15T10:30:00.000Z",
        "public_metrics": {
            "retweet_count": 42,
            "reply_count": 5,
            "like_count": 128,
            "quote_count": 3,
            "bookmark_count": 15,
            "impression_count": 5000,
        },
        "entities": {
            "urls": [
                {
                    "start": 50,
                    "end": 73,
                    "url": "https://t.co/abc123",
                    "expanded_url": "https://example.com/python-testing",
                    "display_url": "example.com/python-testing",
                    "title": "Python Testing Guide",
                },
                {
                    "start": 0,
                    "end": 23,
                    "url": "https://t.co/xyz789",
                    "expanded_url": "https://x.com/somestatus",
                    "display_url": "x.com/somestatus",
                },
            ]
        },
    }


@pytest.fixture
def sample_user_data():
    """Raw API response data for a user."""
    return {
        "id": "111222333",
        "name": "Test User",
        "username": "testuser",
        "profile_image_url": "https://pbs.twimg.com/profile_images/test.jpg",
        "verified": False,
    }


@pytest.fixture
def sample_media_data():
    """Raw API response data for media."""
    return {
        "media_key": "3_1234567890",
        "type": "photo",
        "url": "https://pbs.twimg.com/media/test.jpg",
        "preview_image_url": None,
        "variants": None,
    }


@pytest.fixture
def sample_api_response(sample_tweet_data, sample_user_data, sample_media_data):
    """Full bookmarks API response with includes."""
    return {
        "data": [sample_tweet_data],
        "includes": {
            "users": [sample_user_data],
            "media": [sample_media_data],
        },
        "meta": {"result_count": 1, "next_token": None},
    }


@pytest.fixture
def tmp_output_dir(tmp_path):
    """Temporary directory for markdown output."""
    output = tmp_path / "vault" / "x"
    output.mkdir(parents=True)
    return output
