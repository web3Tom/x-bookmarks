"""Bookmark retrieval and removal via the `twitter-cli` delegate.

This is the DEFAULT mechanism. It reads X's private GraphQL API with session
cookies, requires no X developer account, and costs nothing.

Risk posture (see docs/feasibility-agent-reach.md) — accepted deliberately:

- This violates X's Developer Agreement and can get the account flagged.
  `twitter-cli` ships TLS fingerprint impersonation and timing jitter
  documented as evading pattern detection, so the traffic is designed to be
  indistinguishable from a browser rather than to identify itself.
- `auth_token` is roughly full-account access, not a `bookmark.*`-scoped
  revocable token.
- Running on every sync, including destructive removals, is a recurring
  automated pattern against a real named account.

The official OAuth path remains implemented and reachable via `--official`.
It is no longer required, no longer default, and needs no credentials to be
configured for the tool to run.

The credential requirement below is a safety mechanism, not ergonomics. When
TWITTER_AUTH_TOKEN/TWITTER_CT0 are absent, upstream `twitter-cli` scans
Chrome/Edge cookie jars to find them. Refusing to invoke it without both
variables is what prevents that unconsented scan.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from src.api_client import DeleteBookmarkResult, _is_article_url, _is_external_url
from src.models import ExternalLink, Media, Tweet, User

AUTH_TOKEN_ENV = "TWITTER_AUTH_TOKEN"
CT0_ENV = "TWITTER_CT0"

_CLI_NAME = "twitter"
_SUBPROCESS_TIMEOUT_S = 300

# Substrings that identify "this bookmark is already gone" in twitter-cli's
# stderr. The official API answered this with a documented 404; the private
# surface has no such contract, so we pattern-match a narrow allowlist and
# treat everything else as a hard failure.
_ALREADY_ABSENT_MARKERS = ("not found", "does not exist", "no such")

# twitter-cli metric names -> official X API v2 names. Downstream consumers
# (markdown_writer, categorizer) read the official names; emitting twitter-cli's
# names would silently render empty metrics rather than fail loudly.
_METRIC_MAP = {
    "likes": "like_count",
    "retweets": "retweet_count",
    "replies": "reply_count",
    "quotes": "quote_count",
    "bookmarks": "bookmark_count",
    "views": "impression_count",
}


class UnofficialFetchError(RuntimeError):
    """Raised when the unofficial call cannot run or returns unusable output."""


def _missing_credentials(env: Mapping[str, str]) -> list[str]:
    """Names of credentials that are absent or blank. Blank counts as absent."""
    return [
        name
        for name in (AUTH_TOKEN_ENV, CT0_ENV)
        if not (env.get(name) or "").strip()
    ]


def has_credentials(env: Mapping[str, str]) -> bool:
    """Report readiness without raising, for CLI path selection."""
    return not _missing_credentials(env)


def ensure_credentials(env: Mapping[str, str]) -> None:
    """Require both cookies before any subprocess is spawned.

    Raises:
        UnofficialFetchError: either credential is absent or blank.
    """
    missing = _missing_credentials(env)
    if missing:
        raise UnofficialFetchError(
            f"Missing required credential(s): {', '.join(missing)}. Export them "
            "explicitly from a Cookie-Editor / DevTools export. They are "
            "required rather than optional on purpose: without them "
            "`twitter-cli` scans your browser cookie jars, which harvests "
            "session cookies without consent."
        )


def _parse_created_at(raw: str | None) -> datetime:
    """Parse twitter-cli's ISO timestamp, always returning an aware datetime.

    A naive datetime would render an ambiguous date in note frontmatter and
    could shift across a day boundary depending on the reader's locale.
    """
    if not raw:
        return datetime.now(tz=timezone.utc)
    text = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(tz=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_author(data: dict) -> tuple[User | None, str]:
    author_data = data.get("author")
    if not isinstance(author_data, dict) or not author_data:
        return None, ""
    author_id = str(author_data.get("id") or "")
    author = User(
        id=author_id,
        name=str(author_data.get("name") or ""),
        username=str(author_data.get("screenName") or ""),
        profile_image_url=author_data.get("profileImageUrl") or None,
        verified=bool(author_data.get("verified", False)),
    )
    return author, author_id


def _parse_media(data: dict, tweet_id: str) -> tuple[Media, ...]:
    """Build Media entries, synthesizing the media_key the official API supplies.

    twitter-cli has no media_key concept, so keys are derived from the tweet id
    plus position. They must stay unique or downstream lookups would collide.
    """
    items = data.get("media") or []
    return tuple(
        Media(
            media_key=f"{tweet_id}-{index}",
            type=str(item.get("type") or ""),
            url=item.get("url") or None,
            preview_image_url=None,
            variants=(),
        )
        for index, item in enumerate(items)
        if isinstance(item, dict)
    )


def _parse_urls(data: dict) -> tuple[tuple[ExternalLink, ...], str | None]:
    """Split twitter-cli's bare URL strings into external links and an article URL.

    Unlike the official API, twitter-cli emits plain strings with no title
    metadata, so every ExternalLink.title starts as None. That is what the
    Jina Reader backfill in src/enrichment.py is for.
    """
    raw_urls = [u for u in (data.get("urls") or []) if isinstance(u, str) and u]

    external_links = tuple(
        ExternalLink(url=url, expanded_url=url, display_url=url, title=None)
        for url in raw_urls
        if _is_external_url(url)
    )

    article_url = next((url for url in raw_urls if _is_article_url(url)), None)
    return external_links, article_url


def parse_cli_tweet(data: dict) -> Tweet:
    """Adapt one `twitter bookmarks --json` entry into the pipeline's Tweet."""
    tweet_id = str(data.get("id") or "")
    if not tweet_id:
        raise ValueError("tweet entry has no id")

    author, author_id = _parse_author(data)
    external_links, article_url = _parse_urls(data)

    raw_metrics = data.get("metrics") or {}
    public_metrics = {
        official: raw_metrics[cli_name]
        for cli_name, official in _METRIC_MAP.items()
        if cli_name in raw_metrics
    }

    return Tweet(
        id=tweet_id,
        text=str(data.get("text") or ""),
        author_id=author_id,
        created_at=_parse_created_at(data.get("createdAtISO")),
        author=author,
        public_metrics=public_metrics,
        media=_parse_media(data, tweet_id),
        external_links=external_links,
        # twitter-cli already resolves note_tweet into `text` (parser.py:464),
        # so populating this would double-render the body.
        note_tweet_text=None,
        article_url=article_url,
        article_content=data.get("articleText") or None,
        article_title=data.get("articleTitle") or None,
    )


def parse_cli_tweets(payload: Any) -> tuple[Tweet, ...]:
    """Adapt a full CLI payload, skipping entries that cannot be parsed.

    One malformed entry must not abort a multi-thousand-bookmark backfill.
    """
    if isinstance(payload, dict):
        payload = payload.get("tweets") or payload.get("data") or []
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        raise UnofficialFetchError(
            f"Expected a list of tweets, got {type(payload).__name__}."
        )

    tweets = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        try:
            tweets.append(parse_cli_tweet(entry))
        except (ValueError, KeyError, TypeError):
            continue
    return tuple(tweets)


def fetch_bookmarks_unofficial(
    *,
    max_count: int,
    env: Mapping[str, str],
    runner: Callable[..., Any] = subprocess.run,
) -> tuple[Tweet, ...]:
    """Fetch bookmarks through `twitter-cli`.

    Cursor-paginated by the delegate, so unlike the official endpoint's
    observed ~300-per-run ceiling, `max_count` is the only practical bound.
    """
    result = _run_cli(
        ["bookmarks", "--json", "--max", str(max_count), "--full-text"],
        env=env,
        runner=runner,
    )

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise UnofficialFetchError(
            f"`{_CLI_NAME} bookmarks` exited {result.returncode}: {stderr}"
        )

    try:
        payload = json.loads(result.stdout or "")
    except json.JSONDecodeError as exc:
        raise UnofficialFetchError(
            f"`{_CLI_NAME} bookmarks` returned output that is not valid JSON."
        ) from exc

    return parse_cli_tweets(payload)


def delete_bookmark_unofficial(
    tweet_id: str,
    *,
    env: Mapping[str, str],
    runner: Callable[..., Any] = subprocess.run,
) -> DeleteBookmarkResult:
    """Remove one bookmark via `twitter unbookmark`.

    Semantics note: the official `DELETE .../bookmarks/{id}` documents 404 as
    "already absent", which makes re-running a removal safe. The private
    GraphQL surface offers no such contract, so absence is inferred from a
    narrow stderr allowlist. Anything not positively matched is raised rather
    than reported as a successful deletion — reporting a failed delete as
    success would archive the note while the bookmark still exists on X.
    """
    result = _run_cli(["unbookmark", tweet_id], env=env, runner=runner)

    if result.returncode == 0:
        return DeleteBookmarkResult(tweet_id=tweet_id)

    stderr = (result.stderr or "").strip()
    if any(marker in stderr.lower() for marker in _ALREADY_ABSENT_MARKERS):
        return DeleteBookmarkResult(tweet_id=tweet_id, already_absent=True)

    raise UnofficialFetchError(
        f"`{_CLI_NAME} unbookmark {tweet_id}` exited {result.returncode}: {stderr}"
    )


def _run_cli(
    args: Sequence[str],
    *,
    env: Mapping[str, str],
    runner: Callable[..., Any],
) -> Any:
    """Spawn twitter-cli after validating credentials.

    Credentials travel in the child environment, never in argv, because argv
    lands in shell history, `ps` output, and agent session transcripts.
    """
    ensure_credentials(env)

    cmd = [_CLI_NAME, *args]
    child_env = dict(os.environ)
    child_env[AUTH_TOKEN_ENV] = env[AUTH_TOKEN_ENV]
    child_env[CT0_ENV] = env[CT0_ENV]

    try:
        return runner(
            cmd,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_S,
            env=child_env,
        )
    except FileNotFoundError as exc:
        raise UnofficialFetchError(
            f"`{_CLI_NAME}` not found on PATH. Install it with "
            "`pipx install twitter-cli`."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise UnofficialFetchError(
            f"`{_CLI_NAME} {' '.join(args)}` timed out after "
            f"{_SUBPROCESS_TIMEOUT_S}s."
        ) from exc
