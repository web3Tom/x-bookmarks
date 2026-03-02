from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import anthropic
import yaml
from dotenv import load_dotenv

load_dotenv()

from src.categorizer import TAXONOMY, _sanitize_title, _slugify
from src.markdown_writer import _escape_yaml_string, _validate_frontmatter

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 8192

_DEPRECATED_FIELDS = frozenset({
    "author_name", "tweet_id", "likes", "retweets",
    "replies", "bookmarks", "has_media", "has_links",
})

_ALLOWED_FIELDS = frozenset({
    "title", "author", "category", "subCategory", "date",
    "read", "type", "tweet_url", "article_url",
})


@dataclass(frozen=True)
class ParsedBookmark:
    filepath: Path
    frontmatter: dict[str, str]
    body: str


@dataclass(frozen=True)
class MigrationResult:
    filepath: Path
    old_title: str
    new_title: str
    fields_removed: tuple[str, ...]
    heading_changed: bool
    skipped: bool


def _split_frontmatter_body(content: str) -> tuple[str, str]:
    """Split on --- delimiters. Returns (yaml_block, body)."""
    if not content.startswith("---"):
        raise ValueError("No frontmatter found: file does not start with ---")
    end_idx = content.find("\n---", 3)
    if end_idx == -1:
        raise ValueError("No closing --- delimiter found")
    yaml_block = content[4:end_idx]
    body = content[end_idx + 4:]
    if body.startswith("\n"):
        body = body[1:]
    return yaml_block, body


def _parse_frontmatter(yaml_block: str) -> dict | None:
    """yaml.safe_load() the block into a dict. Returns None on failure."""
    try:
        parsed = yaml.safe_load(yaml_block)
        if not isinstance(parsed, dict):
            return None
        return parsed
    except yaml.YAMLError as exc:
        logger.warning("YAML parse error: %s", exc)
        return None


def parse_existing_bookmark(filepath: Path) -> ParsedBookmark | None:
    """Read file, split, parse, return ParsedBookmark. Returns None on failure."""
    try:
        content = filepath.read_text(encoding="utf-8")
        yaml_block, body = _split_frontmatter_body(content)
        parsed = _parse_frontmatter(yaml_block)
        if parsed is None:
            logger.warning("Failed to parse frontmatter in %s", filepath.name)
            return None
        return ParsedBookmark(filepath=filepath, frontmatter=parsed, body=body)
    except (ValueError, OSError) as exc:
        logger.warning("Failed to read %s: %s", filepath.name, exc)
        return None


def _build_taxonomy_block() -> str:
    """Format taxonomy for the migration prompt."""
    lines: list[str] = []
    for category, subs in TAXONOMY.items():
        lines.append(f"- {category}")
        for sub in subs:
            lines.append(f"  - {sub}")
    return "\n".join(lines)


def _build_migration_prompt() -> str:
    """System prompt for title generation and category validation."""
    return f"""\
You are a bookmark migration assistant. Given a JSON array of existing bookmarks, \
generate a concise, descriptive title for each and validate/correct the category \
and sub_category against the fixed taxonomy.

Allowed categories and subcategories:
{_build_taxonomy_block()}

Rules:
- Generate a title (max 80 chars) for each bookmark:
  - For articles: prefer the article's actual title or topic
  - For posts: summarize the key insight or topic (do not just truncate the text)
  - Title must be YAML-safe: no colons, no quotes, no newlines, no brackets
- Validate the existing category and sub_category against the taxonomy above.
  - If valid, keep them as-is.
  - If invalid or not in the taxonomy, pick the closest match from the taxonomy.
  - If nothing fits, use category "General" with sub_category "Uncategorized".
- Return ONLY a JSON array, no other text.

Response format:
[{{"filename": "...", "title": "...", "category": "AI Coding", "sub_category": "Coding Workflows"}}, ...]
"""


def _build_migration_payload(bookmarks: list[ParsedBookmark]) -> str:
    """JSON array with filename, existing metadata, and body text."""
    entries = []
    for bm in bookmarks:
        fm = bm.frontmatter
        bm_type = fm.get("type", "post")
        body_text = bm.body
        if bm_type != "article" and len(body_text) > 2000:
            body_text = body_text[:2000]
        entries.append({
            "filename": bm.filepath.name,
            "title": str(fm.get("title", "")),
            "category": str(fm.get("category", "")),
            "subCategory": str(fm.get("subCategory", "")),
            "type": str(bm_type),
            "body": body_text,
        })
    return json.dumps(entries, ensure_ascii=False)


def _parse_migration_response(text: str) -> dict[str, dict]:
    """Parse Claude response into {filename: {title, category, sub_category}}."""
    cleaned = text.strip()
    fenced = re.match(r"```(?:json)?\s*\n?(.*?)\n?```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    entries = json.loads(cleaned)
    return {
        entry["filename"]: {
            "title": entry.get("title", ""),
            "category": entry.get("category", "General"),
            "sub_category": entry.get("sub_category", "Uncategorized"),
        }
        for entry in entries
    }


def generate_titles_batch(
    bookmarks: list[ParsedBookmark],
    api_key: str,
    batch_size: int = 10,
) -> dict[str, dict]:
    """Send batches to Claude, return {filename: {title, category, sub_category}}."""
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = _build_migration_prompt()
    all_results: dict[str, dict] = {}

    for i in range(0, len(bookmarks), batch_size):
        batch = bookmarks[i:i + batch_size]
        payload = _build_migration_payload(batch)

        logger.info(
            "Sending batch %d-%d of %d to Claude...",
            i + 1, min(i + batch_size, len(bookmarks)), len(bookmarks),
        )

        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": payload}],
        )

        raw_text = response.content[0].text
        batch_results = _parse_migration_response(raw_text)
        all_results.update(batch_results)

        if i + batch_size < len(bookmarks):
            logger.info("Rate limit pause (62s)...")
            time.sleep(62)

        # Log any bookmarks in the batch that didn't get a response
        for bm in batch:
            if bm.filepath.name not in batch_results:
                logger.warning(
                    "No Claude response for %s, will use fallback", bm.filepath.name,
                )

    return all_results


def _build_migrated_frontmatter(
    parsed: dict,
    new_title: str,
    category: str,
    sub_category: str,
) -> str:
    """Build frontmatter string using ONLY allowed fields."""
    escaped_title = _escape_yaml_string(new_title)
    author = str(parsed.get("author", "@unknown"))
    if not author.startswith("@"):
        author = f"@{author}"

    date_val = parsed.get("date", "")
    read_val = parsed.get("read", False)
    bm_type = str(parsed.get("type", "post"))
    tweet_url = str(parsed.get("tweet_url", ""))
    article_url = parsed.get("article_url")

    lines = [
        "---",
        f'title: "{escaped_title}"',
        f'author: "{_escape_yaml_string(author)}"',
        f'category: "{_escape_yaml_string(category)}"',
        f'subCategory: "{_escape_yaml_string(sub_category)}"',
        f"date: {date_val}",
        f"read: {'true' if read_val else 'false'}",
        f'type: "{_escape_yaml_string(bm_type)}"',
        f'tweet_url: "{_escape_yaml_string(tweet_url)}"',
    ]

    if article_url:
        lines.append(f'article_url: "{_escape_yaml_string(str(article_url))}"')

    lines.append("---")
    frontmatter = "\n".join(lines) + "\n"
    return _validate_frontmatter(frontmatter)


def _replace_body_heading(body: str, new_title: str) -> str:
    """Replace the first ## heading with ## {new_title}."""
    return re.sub(r"^## .+$", f"## {new_title}", body, count=1, flags=re.MULTILINE)


def migrate_single_file(
    parsed: ParsedBookmark,
    title_data: dict,
) -> MigrationResult:
    """Rebuild frontmatter + body, write file in-place, return result."""
    fm = parsed.frontmatter
    old_title = str(fm.get("title", ""))

    new_title = title_data.get("title", "")
    if not new_title:
        new_title = _sanitize_title(old_title)
    category = title_data.get("category", "General")
    sub_category = title_data.get("sub_category", "Uncategorized")

    removed = tuple(k for k in fm if k in _DEPRECATED_FIELDS)

    new_frontmatter = _build_migrated_frontmatter(
        fm, new_title, category, sub_category,
    )

    old_body = parsed.body
    new_body = _replace_body_heading(old_body, new_title)
    heading_changed = old_body != new_body

    content = new_frontmatter + "\n" + new_body
    parsed.filepath.write_text(content, encoding="utf-8")

    return MigrationResult(
        filepath=parsed.filepath,
        old_title=old_title,
        new_title=new_title,
        fields_removed=removed,
        heading_changed=heading_changed,
        skipped=False,
    )


def migrate_directory(
    directory: Path,
    api_key: str,
    batch_size: int = 30,
    dry_run: bool = False,
) -> list[MigrationResult]:
    """Scan directory for *.md, batch Claude calls, migrate each file."""
    md_files = sorted(
        f for f in directory.glob("*.md") if f.name != "index.md"
    )

    if not md_files:
        logger.info("No markdown files found in %s", directory)
        return []

    logger.info("Found %d markdown files in %s", len(md_files), directory)

    parsed_bookmarks: list[ParsedBookmark] = []
    results: list[MigrationResult] = []

    for filepath in md_files:
        bm = parse_existing_bookmark(filepath)
        if bm is None:
            results.append(MigrationResult(
                filepath=filepath,
                old_title="",
                new_title="",
                fields_removed=(),
                heading_changed=False,
                skipped=True,
            ))
            continue
        parsed_bookmarks.append(bm)

    if not parsed_bookmarks:
        logger.info("No parseable bookmarks found")
        return results

    logger.info("Generating titles for %d bookmarks...", len(parsed_bookmarks))
    title_map = generate_titles_batch(parsed_bookmarks, api_key, batch_size)

    for bm in parsed_bookmarks:
        title_data = title_map.get(bm.filepath.name, {})
        if not title_data:
            title_data = {
                "title": _sanitize_title(str(bm.frontmatter.get("title", ""))),
                "category": str(bm.frontmatter.get("category", "General")),
                "sub_category": str(bm.frontmatter.get("subCategory", "Uncategorized")),
            }

        if dry_run:
            old_title = str(bm.frontmatter.get("title", ""))
            removed = tuple(k for k in bm.frontmatter if k in _DEPRECATED_FIELDS)
            has_notes_heading = bool(re.search(r"^## .+$", bm.body, re.MULTILINE))
            results.append(MigrationResult(
                filepath=bm.filepath,
                old_title=old_title,
                new_title=title_data.get("title", old_title),
                fields_removed=removed,
                heading_changed=has_notes_heading,
                skipped=False,
            ))
        else:
            result = migrate_single_file(bm, title_data)
            results.append(result)

    return results


def main() -> None:
    """CLI entry point for bookmark migration."""
    parser = argparse.ArgumentParser(
        description="Migrate existing bookmark files to current standards",
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory containing bookmark .md files",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Anthropic API key (or ANTHROPIC_API_KEY env var)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=30,
        help="Number of files per Claude API call (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and generate titles without writing files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("No API key provided. Use --api-key or set ANTHROPIC_API_KEY.")
        sys.exit(1)

    if not args.directory.is_dir():
        logger.error("Directory not found: %s", args.directory)
        sys.exit(1)

    mode = "DRY RUN" if args.dry_run else "LIVE"
    logger.info("Starting migration (%s) on %s", mode, args.directory)

    results = migrate_directory(
        directory=args.directory,
        api_key=api_key,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )

    skipped = sum(1 for r in results if r.skipped)
    migrated = sum(1 for r in results if not r.skipped)
    heading_changes = sum(1 for r in results if r.heading_changed)
    total_removed = sum(len(r.fields_removed) for r in results)

    print(f"\n--- Migration Summary ({mode}) ---")
    print(f"Files processed: {len(results)}")
    print(f"Migrated:        {migrated}")
    print(f"Skipped (errors):{skipped}")
    print(f"Headings updated:{heading_changes}")
    print(f"Fields removed:  {total_removed}")

    if args.verbose:
        for r in results:
            if r.skipped:
                print(f"  SKIP  {r.filepath.name}")
            else:
                label = "DRY" if args.dry_run else "OK"
                title_change = f'"{r.old_title}" -> "{r.new_title}"'
                print(f"  {label:4}  {r.filepath.name}  {title_change}")
                if r.fields_removed:
                    print(f"        removed: {', '.join(r.fields_removed)}")


if __name__ == "__main__":
    main()
