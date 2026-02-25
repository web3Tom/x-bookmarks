from __future__ import annotations

import re
from pathlib import Path

from src.models import CategorizedTweet, Category, Tweet

_TWEET_ID_PATTERN = re.compile(r'^tweet_id:\s*"(\S+)"', re.MULTILINE)


def _read_all_existing_ids(output_dir: Path) -> set[str]:
    """Scan *.md frontmatter for tweet_id: values (skip index.md)."""
    all_ids: set[str] = set()
    if not output_dir.exists():
        return all_ids
    for md_file in output_dir.glob("*.md"):
        if md_file.name == "index.md":
            continue
        content = md_file.read_text()
        all_ids.update(_TWEET_ID_PATTERN.findall(content))
    return all_ids


def _build_filename(tweet: Tweet, existing_names: set[str]) -> str:
    """{date}-{username}.md with -2, -3 collision suffix."""
    date_str = tweet.created_at.strftime("%Y-%m-%d")
    username = tweet.author.username if tweet.author else "unknown"
    base = f"{date_str}-{username}"
    candidate = f"{base}.md"
    if candidate not in existing_names:
        return candidate
    counter = 2
    while True:
        candidate = f"{base}-{counter}.md"
        if candidate not in existing_names:
            return candidate
        counter += 1


def _escape_yaml_string(value: str) -> str:
    """Escape a string for YAML double-quoted scalar."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_frontmatter(tweet: Tweet, category: Category, bookmark_type: str) -> str:
    """YAML block with all metadata fields."""
    username = tweet.author.username if tweet.author else "unknown"
    author_name = tweet.author.name if tweet.author else "Unknown"
    date_str = tweet.created_at.strftime("%Y-%m-%d")
    metrics = tweet.public_metrics

    if bookmark_type == "article" and tweet.article_title:
        title = tweet.article_title
    else:
        title = tweet.display_text

    if len(title) > 80:
        title = title[:80] + "..."

    escaped_title = _escape_yaml_string(title)
    tweet_url = f"https://x.com/{username}/status/{tweet.id}"

    lines = [
        "---",
        f'title: "{escaped_title}"',
        f'author: "@{username}"',
        f"author_name: {author_name}",
        f"category: {category.display_name}",
        f"date: {date_str}",
        "read: false",
        f"type: {bookmark_type}",
        f'tweet_id: "{tweet.id}"',
        f'tweet_url: "{tweet_url}"',
        f"likes: {metrics.get('like_count', 0)}",
        f"retweets: {metrics.get('retweet_count', 0)}",
        f"replies: {metrics.get('reply_count', 0)}",
        f"bookmarks: {metrics.get('bookmark_count', 0)}",
        f"has_media: {'true' if tweet.media else 'false'}",
        f"has_links: {'true' if tweet.external_links else 'false'}",
    ]

    if bookmark_type == "article" and tweet.article_url:
        lines.append(f'article_url: "{tweet.article_url}"')

    lines.append("---")
    return "\n".join(lines) + "\n"


def _format_post_body(tweet: Tweet) -> str:
    """Blockquoted text + original link + external links + media."""
    username = tweet.author.username if tweet.author else "unknown"
    text = tweet.display_text
    lines: list[str] = []

    for line in text.split("\n"):
        lines.append(f"> {line}")

    tweet_url = f"https://x.com/{username}/status/{tweet.id}"
    lines.append("")
    lines.append(f"\U0001f517 [Original tweet]({tweet_url})")

    if tweet.external_links:
        lines.append("")
        for link in tweet.external_links:
            label = link.title or link.display_url
            lines.append(f"\U0001f310 [{label}]({link.expanded_url})")

    if tweet.media:
        lines.append("")
        for m in tweet.media:
            url = m.url or m.preview_image_url or ""
            if url:
                lines.append(f"\U0001f4f7 [{m.type}]({url})")

    return "\n".join(lines) + "\n"


def _format_article_body(tweet: Tweet) -> str:
    """Just tweet.article_content."""
    return tweet.article_content or ""


def _write_index_file(output_dir: Path) -> None:
    """Dataview query table, always overwritten."""
    content = """---
title: X Bookmarks
---

```dataview
TABLE
  author,
  category,
  type,
  date,
  read,
  likes
FROM "03_AI/x/x-test"
WHERE type
SORT date DESC
```
"""
    (output_dir / "index.md").write_text(content)


def write_bookmarks(
    categorized: tuple[CategorizedTweet, ...],
    output_dir: Path,
) -> dict[str, int]:
    """Main entry point — one file per bookmark, flat directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    existing_ids = _read_all_existing_ids(output_dir)
    existing_names: set[str] = {
        f.name for f in output_dir.glob("*.md") if f.name != "index.md"
    }

    stats = {"files_written": 0, "bookmarks_written": 0, "duplicates_skipped": 0}

    for ct in categorized:
        tweet = ct.tweet
        if tweet.id in existing_ids:
            stats["duplicates_skipped"] += 1
            continue

        is_article = bool(tweet.article_content)
        bookmark_type = "article" if is_article else "post"

        filename = _build_filename(tweet, existing_names)
        existing_names.add(filename)

        frontmatter = _build_frontmatter(tweet, ct.category, bookmark_type)
        body = _format_article_body(tweet) if is_article else _format_post_body(tweet)

        file_path = output_dir / filename
        file_path.write_text(frontmatter + "\n" + body)

        stats["files_written"] += 1
        stats["bookmarks_written"] += 1
        existing_ids.add(tweet.id)

    _write_index_file(output_dir)

    return stats
