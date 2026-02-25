from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class User:
    id: str
    name: str
    username: str
    profile_image_url: str | None
    verified: bool

    @classmethod
    def from_api(cls, data: dict) -> User:
        return cls(
            id=data["id"],
            name=data["name"],
            username=data["username"],
            profile_image_url=data.get("profile_image_url"),
            verified=data.get("verified", False),
        )


@dataclass(frozen=True)
class Media:
    media_key: str
    type: str
    url: str | None
    preview_image_url: str | None
    variants: tuple[dict, ...]

    @classmethod
    def from_api(cls, data: dict) -> Media:
        raw_variants = data.get("variants") or []
        return cls(
            media_key=data["media_key"],
            type=data["type"],
            url=data.get("url"),
            preview_image_url=data.get("preview_image_url"),
            variants=tuple(raw_variants),
        )


@dataclass(frozen=True)
class ExternalLink:
    url: str
    expanded_url: str
    display_url: str
    title: str | None


@dataclass(frozen=True)
class Tweet:
    id: str
    text: str
    author_id: str
    created_at: datetime
    author: User | None
    public_metrics: dict
    media: tuple[Media, ...]
    external_links: tuple[ExternalLink, ...]
    note_tweet_text: str | None
    article_url: str | None
    article_content: str | None = None
    article_title: str | None = None

    @property
    def display_text(self) -> str:
        return self.note_tweet_text if self.note_tweet_text else self.text


@dataclass(frozen=True)
class Category:
    slug: str
    display_name: str


@dataclass(frozen=True)
class CategorizedTweet:
    tweet: Tweet
    category: Category


@dataclass(frozen=True)
class BookmarkPage:
    tweets: tuple[Tweet, ...]
    next_token: str | None
