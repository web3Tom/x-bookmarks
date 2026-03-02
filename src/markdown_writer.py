from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

from src.models import CategorizedTweet, Category, Tweet

logger = logging.getLogger(__name__)

_TWEET_URL_ID_PATTERN = re.compile(r'^tweet_url:\s*"https://x\.com/\S+/status/(\d+)"', re.MULTILINE)


def read_existing_ids(output_dir: Path) -> set[str]:
    """Scan *.md frontmatter for tweet IDs extracted from tweet_url values (skip index.md)."""
    all_ids: set[str] = set()
    if not output_dir.exists():
        return all_ids
    for md_file in output_dir.glob("*.md"):
        if md_file.name == "index.md":
            continue
        content = md_file.read_text()
        all_ids.update(_TWEET_URL_ID_PATTERN.findall(content))
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


def _build_frontmatter(tweet: Tweet, category: Category, bookmark_type: str, title: str) -> str:
    """YAML block with all metadata fields."""
    username = tweet.author.username if tweet.author else "unknown"
    date_str = tweet.created_at.strftime("%Y-%m-%d")

    escaped_title = _escape_yaml_string(title)
    tweet_url = f"https://x.com/{username}/status/{tweet.id}"

    lines = [
        "---",
        f'title: "{escaped_title}"',
        f'author: "@{username}"',
        f'category: "{_escape_yaml_string(category.display_name)}"',
        f'subCategory: "{_escape_yaml_string(category.sub_category)}"',
        f"date: {date_str}",
        "read: false",
        f'type: "{bookmark_type}"',
        f'tweet_url: "{tweet_url}"',
    ]

    if bookmark_type == "article" and tweet.article_url:
        lines.append(f'article_url: "{tweet.article_url}"')

    lines.append("---")
    return "\n".join(lines) + "\n"


def _validate_frontmatter(frontmatter: str) -> str:
    """Validate YAML frontmatter; attempt repair if broken."""
    lines = frontmatter.strip().split("\n")
    if len(lines) < 3 or lines[0] != "---" or lines[-1] != "---":
        return frontmatter

    yaml_body = "\n".join(lines[1:-1])
    try:
        yaml.safe_load(yaml_body)
        return frontmatter
    except yaml.YAMLError as exc:
        logger.warning("Frontmatter YAML validation failed: %s — attempting repair", exc)
        repaired_lines = []
        for line in lines[1:-1]:
            if line.startswith("title: "):
                safe_title = _escape_yaml_string(
                    line[len('title: "'):-1] if line.endswith('"') else line[len("title: "):]
                )
                repaired_lines.append(f'title: "{safe_title}"')
            else:
                repaired_lines.append(line)
        repaired = "---\n" + "\n".join(repaired_lines) + "\n---\n"
        try:
            yaml.safe_load("\n".join(repaired_lines))
            return repaired
        except yaml.YAMLError:
            logger.warning("Frontmatter repair failed; returning original")
            return frontmatter


def _format_post_body(tweet: Tweet, title: str) -> str:
    """## {title} (blockquoted text + media) then ## References (links)."""
    username = tweet.author.username if tweet.author else "unknown"
    text = tweet.display_text
    tweet_url = f"https://x.com/{username}/status/{tweet.id}"

    notes_lines: list[str] = [f"## {title}", ""]
    for line in text.split("\n"):
        notes_lines.append(f"> {line}")

    if tweet.media:
        notes_lines.append("")
        for m in tweet.media:
            url = m.url or m.preview_image_url or ""
            if url:
                notes_lines.append(f"\U0001f4f7 [{m.type}]({url})")

    ref_lines: list[str] = ["## References", ""]
    ref_lines.append(f"- \U0001f517 [Original tweet]({tweet_url})")

    if tweet.external_links:
        for link in tweet.external_links:
            label = link.title or link.display_url
            ref_lines.append(f"- \U0001f310 [{label}]({link.expanded_url})")

    return "\n".join(notes_lines) + "\n\n" + "\n".join(ref_lines) + "\n"


def _format_article_body(tweet: Tweet, title: str) -> str:
    """## {title} (article content) then ## References (tweet link)."""
    username = tweet.author.username if tweet.author else "unknown"
    tweet_url = f"https://x.com/{username}/status/{tweet.id}"
    content = tweet.article_content or ""

    notes = f"## {title}\n\n{content}"
    refs = f"## References\n\n- \U0001f517 [Original tweet]({tweet_url})"
    return notes + "\n\n" + refs + "\n"


def _write_index_file(output_dir: Path) -> None:
    """Dataview query table, always overwritten."""
    content = """---
title: X Bookmarks
---

```dataview
TABLE
  author,
  category,
  subCategory,
  type,
  date,
  read
FROM "03_AI/x"
WHERE type
SORT category ASC, subCategory ASC, date DESC
```
"""
    (output_dir / "index.md").write_text(content)


def write_bookmarks(
    categorized: tuple[CategorizedTweet, ...],
    output_dir: Path,
) -> dict[str, int]:
    """Main entry point — one file per bookmark, flat directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    existing_ids = read_existing_ids(output_dir)
    existing_names: set[str] = {
        f.name for f in output_dir.glob("*.md") if f.name != "index.md"
    }

    stats: dict[str, int | list[str]] = {
        "files_written": 0,
        "bookmarks_written": 0,
        "duplicates_skipped": 0,
        "filenames": [],
    }

    for ct in categorized:
        tweet = ct.tweet
        if tweet.id in existing_ids:
            stats["duplicates_skipped"] += 1
            continue

        is_article = bool(tweet.article_content)
        bookmark_type = "article" if is_article else "post"

        filename = _build_filename(tweet, existing_names)
        existing_names.add(filename)

        frontmatter = _build_frontmatter(tweet, ct.category, bookmark_type, ct.title)
        frontmatter = _validate_frontmatter(frontmatter)
        body = _format_article_body(tweet, ct.title) if is_article else _format_post_body(tweet, ct.title)

        file_path = output_dir / filename
        file_path.write_text(frontmatter + "\n" + body)

        stats["files_written"] += 1
        stats["bookmarks_written"] += 1
        stats["filenames"].append(filename)
        existing_ids.add(tweet.id)

    _write_index_file(output_dir)

    return stats
