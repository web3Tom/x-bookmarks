from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

from src.models import CategorizedTweet, Tweet
from src.taxonomy import group_entity_tags

logger = logging.getLogger(__name__)

_TWEET_URL_ID_PATTERN = re.compile(r'^tweet_url:\s*"https://x\.com/\S+/status/(\d+)"', re.MULTILINE)


def read_existing_ids(output_dir: Path) -> set[str]:
    """Scan *.md frontmatter for tweet IDs extracted from tweet_url values."""
    all_ids: set[str] = set()
    if not output_dir.exists():
        return all_ids
    for md_file in output_dir.glob("*.md"):
        content = md_file.read_text()
        all_ids.update(_TWEET_URL_ID_PATTERN.findall(content))
    return all_ids


def _slugify_title(title: str) -> str:
    """Convert a title string to a kebab-case filename slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")
    if len(slug) > 80:
        slug = slug[:80].rstrip("-")
    return slug or "untitled"


def _build_filename(title: str, existing_names: set[str]) -> str:
    """{title-slug}.md with -2, -3 collision suffix."""
    base = _slugify_title(title)
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


_FALLBACK_MECHANIC = "uncategorized"


def build_faceted_frontmatter(
    *,
    title: str,
    author: str,
    pillar: str,
    mechanics: tuple[str, ...],
    entity_tags: dict[str, list[str]],
    date: str,
    read: bool,
    synthesized: bool,
    bookmark_type: str,
    tweet_url: str,
    article_url: str | None = None,
    tail_lines: tuple[str, ...] = (),
) -> str:
    """Emit the canonical faceted frontmatter block.

    Field order: title, author, pillar, mechanics, entity_tags, date, read,
    synthesized, type, tweet_url, article_url, <tail_lines>. `mechanics` always
    emits at least one item; `entity_tags` is omitted entirely when empty.

    Shared by the sync writer and the migration writer so the two paths cannot
    drift apart.
    """
    if not author.startswith("@"):
        author = f"@{author}"
    safe_mechanics = mechanics or (_FALLBACK_MECHANIC,)

    lines = [
        "---",
        f'title: "{_escape_yaml_string(title)}"',
        f'author: "{_escape_yaml_string(author)}"',
        f'pillar: "{_escape_yaml_string(pillar)}"',
        "mechanics:",
    ]
    lines.extend(f"  - {m}" for m in safe_mechanics)

    if entity_tags:
        lines.append("entity_tags:")
        for prefix, entities in entity_tags.items():
            lines.append(f"  {prefix}: [{', '.join(entities)}]")

    lines.extend([
        f"date: {date}",
        f"read: {'true' if read else 'false'}",
        f"synthesized: {'true' if synthesized else 'false'}",
        f'type: "{_escape_yaml_string(bookmark_type)}"',
        f'tweet_url: "{_escape_yaml_string(tweet_url)}"',
    ])

    if article_url:
        lines.append(f'article_url: "{_escape_yaml_string(str(article_url))}"')

    lines.extend(tail_lines)
    lines.append("---")
    return "\n".join(lines) + "\n"


def _build_frontmatter(
    tweet: Tweet,
    pillar: str,
    bookmark_type: str,
    title: str,
    mechanics: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
) -> str:
    """YAML block with all metadata fields for a freshly-synced bookmark."""
    username = tweet.author.username if tweet.author else "unknown"
    date_str = tweet.created_at.strftime("%Y-%m-%d")
    tweet_url = f"https://x.com/{username}/status/{tweet.id}"
    article_url = (
        tweet.article_url if (bookmark_type == "article" and tweet.article_url) else None
    )

    return build_faceted_frontmatter(
        title=title,
        author=f"@{username}",
        pillar=pillar,
        mechanics=mechanics,
        entity_tags=group_entity_tags(tags),
        date=date_str,
        read=False,
        synthesized=False,
        bookmark_type=bookmark_type,
        tweet_url=tweet_url,
        article_url=article_url,
    )


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



def write_bookmarks(
    categorized: tuple[CategorizedTweet, ...],
    output_dir: Path,
) -> dict[str, int]:
    """Main entry point — one file per bookmark, flat directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    existing_ids = read_existing_ids(output_dir)
    existing_names: set[str] = {
        f.name for f in output_dir.glob("*.md")
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

        filename = _build_filename(ct.title, existing_names)
        existing_names.add(filename)

        frontmatter = _build_frontmatter(
            tweet, ct.pillar, bookmark_type, ct.title, ct.mechanics, ct.tags
        )
        frontmatter = _validate_frontmatter(frontmatter)
        body = _format_article_body(tweet, ct.title) if is_article else _format_post_body(tweet, ct.title)

        file_path = output_dir / filename
        file_path.write_text(frontmatter + "\n" + body)

        stats["files_written"] += 1
        stats["bookmarks_written"] += 1
        stats["filenames"].append(filename)
        existing_ids.add(tweet.id)

    return stats
