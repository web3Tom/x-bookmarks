from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from src.config import Config
from src.models import BookmarkPage, ExternalLink, Media, Tweet, User

BOOKMARKS_URL = "https://api.x.com/2/users/{user_id}/bookmarks"
TOKEN_URL = "https://api.x.com/2/oauth2/token"

_MAX_RESULTS = 100
_MAX_BOOKMARKS = 800

_TWEET_FIELDS = ",".join([
    "author_id", "created_at", "public_metrics", "entities",
    "attachments", "note_tweet", "article",
])
_EXPANSIONS = ",".join([
    "author_id", "attachments.media_keys",
])
_USER_FIELDS = ",".join([
    "id", "name", "username", "profile_image_url", "verified",
])
_MEDIA_FIELDS = ",".join([
    "media_key", "type", "url", "preview_image_url", "variants",
])

_EXCLUDED_DOMAINS = {"x.com", "twitter.com", "t.co"}
_ARTICLE_PATTERN = re.compile(r"x\.com/i/article/")


def _is_external_url(expanded_url: str) -> bool:
    """Check if a URL is external (not x.com/twitter.com/t.co self-links)."""
    host = urlparse(expanded_url).netloc.lower()
    return not any(host == d or host.endswith(f".{d}") for d in _EXCLUDED_DOMAINS)


def _is_article_url(expanded_url: str) -> bool:
    """Check if a URL points to an X Article."""
    return bool(_ARTICLE_PATTERN.search(expanded_url))


def parse_tweet(
    data: dict,
    users_lookup: dict[str, User],
    media_lookup: dict[str, Media],
) -> Tweet:
    """Parse a single tweet from API response data."""
    author_id = data.get("author_id", "")
    author = users_lookup.get(author_id)

    raw_urls = data.get("entities", {}).get("urls", [])
    external_links = tuple(
        ExternalLink(
            url=u["url"],
            expanded_url=u["expanded_url"],
            display_url=u.get("display_url", ""),
            title=u.get("title"),
        )
        for u in raw_urls
        if _is_external_url(u.get("expanded_url", ""))
    )

    article_url = None
    for u in raw_urls:
        if _is_article_url(u.get("expanded_url", "")):
            article_url = u["expanded_url"]
            break

    media_keys = data.get("attachments", {}).get("media_keys", [])
    media = tuple(
        media_lookup[key] for key in media_keys if key in media_lookup
    )

    note_tweet_text = None
    note_tweet = data.get("note_tweet")
    if note_tweet:
        note_tweet_text = note_tweet.get("text")

    article_data = data.get("article") or {}
    article_content = article_data.get("plain_text") or None
    article_title = article_data.get("title") or None

    created_at = datetime.strptime(
        data["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ"
    )

    return Tweet(
        id=data["id"],
        text=data["text"],
        author_id=author_id,
        created_at=created_at,
        author=author,
        public_metrics=data.get("public_metrics", {}),
        media=media,
        external_links=external_links,
        note_tweet_text=note_tweet_text,
        article_url=article_url,
        article_content=article_content,
        article_title=article_title,
    )


def parse_bookmarks_response(response_json: dict) -> BookmarkPage:
    """Parse a full bookmarks API response into a BookmarkPage."""
    data = response_json.get("data", [])
    if not data:
        return BookmarkPage(tweets=(), next_token=None)

    includes = response_json.get("includes", {})

    users_lookup = {
        u["id"]: User.from_api(u) for u in includes.get("users", [])
    }
    media_lookup = {
        m["media_key"]: Media.from_api(m) for m in includes.get("media", [])
    }

    tweets = tuple(
        parse_tweet(t, users_lookup, media_lookup) for t in data
    )

    next_token = response_json.get("meta", {}).get("next_token")
    return BookmarkPage(tweets=tweets, next_token=next_token)


def _build_query_params(pagination_token: str | None = None) -> dict:
    """Build query parameters for the bookmarks endpoint."""
    params = {
        "max_results": str(_MAX_RESULTS),
        "tweet.fields": _TWEET_FIELDS,
        "expansions": _EXPANSIONS,
        "user.fields": _USER_FIELDS,
        "media.fields": _MEDIA_FIELDS,
    }
    if pagination_token:
        params["pagination_token"] = pagination_token
    return params


def refresh_access_token(
    config: Config,
    env_path: Path | None = None,
) -> Config:
    """Refresh the OAuth 2.0 access token using the refresh token."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": config.refresh_token,
        "client_id": config.client_id,
    }
    with httpx.Client() as client:
        resp = client.post(TOKEN_URL, data=data)
        resp.raise_for_status()
        tokens = resp.json()

    new_config = replace(
        config,
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token", config.refresh_token),
    )

    _persist_tokens(new_config, env_path)
    return new_config


def _persist_tokens(config: Config, env_path: Path | None = None) -> None:
    """Write updated tokens back to the .env file."""
    target = env_path or Path(".env")
    if not target.exists():
        return

    lines = target.read_text().splitlines()
    new_lines = []
    for line in lines:
        if line.startswith("ACCESS_TOKEN="):
            new_lines.append(f"ACCESS_TOKEN={config.access_token}")
        elif line.startswith("REFRESH_TOKEN="):
            new_lines.append(f"REFRESH_TOKEN={config.refresh_token}")
        else:
            new_lines.append(line)
    target.write_text("\n".join(new_lines) + "\n")


def fetch_bookmarks(
    config: Config,
    env_path: Path | None = None,
) -> tuple[Tweet, ...]:
    """Fetch all bookmarks, handling pagination and token refresh."""
    all_tweets: list[Tweet] = []
    pagination_token: str | None = None
    current_config = config

    with httpx.Client() as client:
        while len(all_tweets) < _MAX_BOOKMARKS:
            params = _build_query_params(pagination_token)
            headers = {"Authorization": f"Bearer {current_config.access_token}"}

            resp = client.get(
                BOOKMARKS_URL.format(user_id=current_config.user_id),
                params=params,
                headers=headers,
            )

            if resp.status_code == 401:
                current_config = refresh_access_token(current_config, env_path)
                headers = {"Authorization": f"Bearer {current_config.access_token}"}
                resp = client.get(
                    BOOKMARKS_URL.format(user_id=current_config.user_id),
                    params=params,
                    headers=headers,
                )

            resp.raise_for_status()
            page = parse_bookmarks_response(resp.json())

            all_tweets.extend(page.tweets)

            if not page.next_token:
                break
            pagination_token = page.next_token

    return tuple(all_tweets)
