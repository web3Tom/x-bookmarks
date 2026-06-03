from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import anthropic
import yaml
from dotenv import load_dotenv

load_dotenv()

from src.categorizer import _resolve_facets, _sanitize_title
from src.config import resolve_taxonomy_file
from src.markdown_writer import (
    _slugify_title,
    build_faceted_frontmatter,
)
from src.taxonomy import (
    ENTITY_PREFIXES,
    build_entity_tags_section,
    build_mechanics_section,
    build_pillars_section,
    group_entity_tags,
    load_taxonomy_override,
    normalize_mechanics,
    normalize_tags,
    validate_pillar,
)

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 16384

_DEPRECATED_FIELDS = frozenset({
    "author_name", "tweet_id", "likes", "retweets",
    "replies", "bookmarks", "has_media", "has_links",
})

_ALLOWED_FIELDS = frozenset({
    "title", "author", "pillar", "mechanics", "entity_tags", "date",
    "read", "synthesized", "type", "tweet_url", "article_url",
    "bookmark_removed", "bookmark_removed_at",
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
    old_filename: str = ""
    new_filename: str = ""
    old_pillar: str = ""
    new_pillar: str = ""
    mechanics: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


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


def _existing_mechanics(fm: dict) -> list[str]:
    """Read an existing note's mechanics list (tolerant of missing/non-list)."""
    value = fm.get("mechanics", [])
    return [str(m) for m in value] if isinstance(value, list) else []


def _existing_entity_tags(fm: dict) -> list[str]:
    """Flatten an existing note's nested entity_tags dict back into prefix/entity tags."""
    value = fm.get("entity_tags")
    if not isinstance(value, dict):
        return []
    flat: list[str] = []
    for prefix, entities in value.items():
        if not isinstance(entities, list):
            continue
        for entity in entities:
            flat.append(f"{prefix}/{entity}")
    return flat


def _build_migration_prompt(
    pillars: list[str],
    pillar_descriptions: dict[str, str] | None = None,
    mechanics_vocab: tuple[str, ...] = (),
    deprecations: list[str] | None = None,
    guidance: str | None = None,
    entity_tags: dict[str, list[str]] | None = None,
) -> str:
    """System prompt for re-titling and re-classifying existing bookmarks."""
    prompt_parts = [
        "You are a bookmark migration assistant using a faceted classification model. "
        "Given a JSON array of existing bookmarks, for each one generate a concise, "
        "descriptive title and assign exactly one `pillar` and one or more `mechanics`.\n\n"
        "Pillars (choose exactly one per bookmark):\n"
        f"{build_pillars_section(pillars, pillar_descriptions)}\n\n"
        "Rules:\n"
        "- Use ONLY the pillars listed above; if the existing pillar is valid, keep it.\n"
        "- Provide at least one mechanic (lowercase-dashed slug); prefer the established list.\n"
        "- Never use a catch-all pillar."
    ]

    mechanics_section = build_mechanics_section(mechanics_vocab)
    if mechanics_section:
        prompt_parts.append(f"\n\nEstablished mechanics (reference):\n{mechanics_section}")

    if deprecations:
        deprecation_text = "\n\nAvoid these (do not assign or create them):\n"
        for dep in deprecations:
            deprecation_text += f"- {dep}\n"
        prompt_parts.append(deprecation_text.rstrip())

    if guidance:
        prompt_parts.append(f"\n\nDomain guidance:\n{guidance}")

    if entity_tags:
        entity_section = build_entity_tags_section(entity_tags)
        if entity_section:
            prompt_parts.append(f"\n\nKnown entity tags (reference):\n{entity_section}")
        prompt_parts.append(
            "\n\nAlso extract entities as `prefix/entity-name` tags. Allowed prefixes "
            f"(nouns only): {', '.join(ENTITY_PREFIXES)} (e.g., framework/langgraph, "
            "model/llama3). Use the entity_tags list as a primary reference; you may add "
            "new entities under the established prefixes."
        )

    prompt_parts.append(
        "\n\nTitle rules:\n"
        "- Generate a title (max 80 chars) for each bookmark.\n"
        "- For articles: prefer the article's actual title or topic.\n"
        "- For posts: summarize the key insight or topic (do not just truncate the text).\n"
        "- Title must be YAML-safe: no colons, no quotes, no newlines, no brackets.\n\n"
        "Return ONLY a JSON array, no other text.\n\n"
        "Response format:\n"
    )

    if entity_tags:
        prompt_parts.append(
            '[{"filename": "...", "title": "...", "pillar": "Applied Practice", '
            '"mechanics": ["rag"], "tags": ["framework/langgraph"]}, ...]'
        )
    else:
        prompt_parts.append(
            '[{"filename": "...", "title": "...", "pillar": "Applied Practice", '
            '"mechanics": ["rag"]}, ...]'
        )

    return "".join(prompt_parts)


def _build_migration_payload(bookmarks: list[ParsedBookmark]) -> str:
    """JSON array with filename, existing metadata, and body text."""
    entries = []
    for bm in bookmarks:
        fm = bm.frontmatter
        bm_type = fm.get("type", "post")
        body_text = bm.body
        if len(body_text) > 2000:
            body_text = body_text[:2000]
        entries.append({
            "filename": bm.filepath.name,
            "title": str(fm.get("title", "")),
            "pillar": str(fm.get("pillar", "")),
            "mechanics": _existing_mechanics(fm),
            "type": str(bm_type),
            "body": body_text,
        })
    return json.dumps(entries, ensure_ascii=False)


def _parse_migration_response(text: str) -> dict[str, dict]:
    """Parse Claude response into {filename: {title, pillar, mechanics, tags}}."""
    cleaned = text.strip()
    fenced = re.match(r"```(?:json)?\s*\n?(.*?)\n?```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    entries = json.loads(cleaned)
    return {
        entry["filename"]: {
            "title": entry.get("title", ""),
            "pillar": entry.get("pillar", ""),
            "mechanics": entry.get("mechanics", []) or [],
            "tags": entry.get("tags", []),
        }
        for entry in entries
    }


def generate_titles_batch(
    bookmarks: list[ParsedBookmark],
    api_key: str,
    batch_size: int = 150,
    override_file: Path | None = None,
) -> dict[str, dict]:
    """Send batches to Claude, return {filename: {title, pillar, mechanics, tags}}.

    Default batch_size=150 sends all bookmarks in a single call.
    The Anthropic SDK handles rate-limit retries automatically.
    """
    client = anthropic.Anthropic(api_key=api_key)

    override_data = load_taxonomy_override(override_file)
    pillars, descriptions, mechanics_vocab, entity_tags = _resolve_facets(override_data)
    deprecations = override_data.deprecations if override_data else None
    guidance = override_data.guidance if override_data else None

    system_prompt = _build_migration_prompt(
        pillars, descriptions, mechanics_vocab, deprecations, guidance, entity_tags,
    )
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

        for bm in batch:
            if bm.filepath.name not in batch_results:
                logger.warning(
                    "No Claude response for %s, will use fallback", bm.filepath.name,
                )

    return all_results


def _build_migrated_frontmatter(
    parsed: dict,
    new_title: str,
    pillar: str,
    mechanics: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
) -> str:
    """Build frontmatter string using ONLY allowed fields (faceted schema)."""
    author = str(parsed.get("author", "@unknown"))
    if not author.startswith("@"):
        author = f"@{author}"

    tail_lines: list[str] = []
    if parsed.get("bookmark_removed") is True:
        tail_lines.append("bookmark_removed: true")
    if parsed.get("bookmark_removed_at"):
        tail_lines.append(f"bookmark_removed_at: {parsed.get('bookmark_removed_at')}")

    return build_faceted_frontmatter(
        title=new_title,
        author=author,
        pillar=pillar,
        mechanics=mechanics,
        entity_tags=group_entity_tags(tags),
        date=str(parsed.get("date", "")),
        read=bool(parsed.get("read", False)),
        synthesized=parsed.get("synthesized", False) is True,
        bookmark_type=str(parsed.get("type", "post")),
        tweet_url=str(parsed.get("tweet_url", "")),
        article_url=parsed.get("article_url"),
        tail_lines=tuple(tail_lines),
    )


def _replace_body_heading(body: str, new_title: str) -> str:
    """Replace the first ## heading with ## {new_title}."""
    return re.sub(r"^## .+$", f"## {new_title}", body, count=1, flags=re.MULTILINE)


def _build_rename_filename(title: str, existing_names: set[str]) -> str:
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


def _resolve_pillar(title_data: dict, fm: dict, pillars: list[str], fallback: str) -> str:
    """Pick the pillar: LLM's value if valid, else existing note's, else fallback."""
    raw = str(title_data.get("pillar") or fm.get("pillar") or "")
    return validate_pillar(raw, pillars, fallback)


def _resolve_mechanics(
    title_data: dict, fm: dict, aliases: dict[str, str] | None = None
) -> tuple[str, ...]:
    """Pick mechanics: LLM's value if any, else the existing note's.

    Collapses synonyms via `aliases` so re-processed notes adopt canonical slugs.
    """
    raw = title_data.get("mechanics") or _existing_mechanics(fm)
    return normalize_mechanics(raw, aliases)


def _resolve_tags(title_data: dict, fm: dict, allowed_prefixes: set[str]) -> tuple[str, ...]:
    """Pick entity tags: LLM's value if any, else the existing note's."""
    raw = title_data.get("tags") or _existing_entity_tags(fm)
    return normalize_tags(list(raw), allowed_prefixes)


def migrate_single_file(
    parsed: ParsedBookmark,
    title_data: dict,
    existing_names: set[str] | None = None,
    pillars: list[str] | None = None,
    fallback_pillar: str = "",
    allowed_prefixes: set[str] | None = None,
    aliases: dict[str, str] | None = None,
) -> MigrationResult:
    """Rebuild frontmatter + body, write file in-place, rename to title slug."""
    fm = parsed.frontmatter
    pillars = pillars or []
    allowed_prefixes = allowed_prefixes if allowed_prefixes is not None else set(ENTITY_PREFIXES)
    old_title = str(fm.get("title", ""))
    old_filename = parsed.filepath.name

    new_title = title_data.get("title", "")
    if not new_title:
        new_title = _sanitize_title(old_title)

    pillar = _resolve_pillar(title_data, fm, pillars, fallback_pillar)
    mechanics = _resolve_mechanics(title_data, fm, aliases)
    tags = _resolve_tags(title_data, fm, allowed_prefixes)

    removed = tuple(k for k in fm if k in _DEPRECATED_FIELDS)

    new_frontmatter = _build_migrated_frontmatter(fm, new_title, pillar, mechanics, tags)

    old_body = parsed.body
    new_body = _replace_body_heading(old_body, new_title)
    heading_changed = old_body != new_body

    content = new_frontmatter + "\n" + new_body

    names = existing_names if existing_names is not None else set()
    new_filename = _build_rename_filename(new_title, names)

    new_path = parsed.filepath.parent / new_filename
    parsed.filepath.write_text(content, encoding="utf-8")

    if new_filename != old_filename:
        parsed.filepath.rename(new_path)

    return MigrationResult(
        filepath=new_path,
        old_title=old_title,
        new_title=new_title,
        fields_removed=removed,
        heading_changed=heading_changed,
        skipped=False,
        old_filename=old_filename,
        new_filename=new_filename,
        old_pillar=str(fm.get("pillar", "")),
        new_pillar=pillar,
        mechanics=mechanics,
        tags=tags,
    )


def migrate_directory(
    directory: Path,
    api_key: str,
    batch_size: int = 150,
    dry_run: bool = False,
    override_file: Path | None = None,
    limit: int | None = None,
) -> list[MigrationResult]:
    """Scan directory for *.md, batch Claude calls, migrate each file.

    When ``limit`` is set, only the first ``limit`` files (sorted by name) are
    parsed and sent to Claude — useful for cheap, token-bounded previews.
    """
    md_files = sorted(directory.glob("*.md"))

    if not md_files:
        logger.info("No markdown files found in %s", directory)
        return []

    logger.info("Found %d markdown files in %s", len(md_files), directory)

    if limit is not None and limit < len(md_files):
        md_files = md_files[:limit]
        logger.info("Limiting to first %d file(s) per --limit", limit)

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
    title_map = generate_titles_batch(
        parsed_bookmarks,
        api_key,
        batch_size,
        override_file=override_file,
    )

    # Resolve the allowed pillars + entity prefixes once for the whole batch.
    override_data = load_taxonomy_override(override_file)
    pillars, _descriptions, _mechanics_vocab, _entity_tags = _resolve_facets(override_data)
    aliases = override_data.aliases if override_data else None
    fallback_pillar = pillars[0] if pillars else ""
    allowed_prefixes = set(ENTITY_PREFIXES)

    existing_names: set[str] = set()

    for bm in parsed_bookmarks:
        title_data = title_map.get(bm.filepath.name, {})
        if not title_data:
            title_data = {
                "title": _sanitize_title(str(bm.frontmatter.get("title", ""))),
                "pillar": str(bm.frontmatter.get("pillar", "")),
                "mechanics": _existing_mechanics(bm.frontmatter),
            }

        if dry_run:
            old_title = str(bm.frontmatter.get("title", ""))
            new_title = title_data.get("title", old_title)
            removed = tuple(k for k in bm.frontmatter if k in _DEPRECATED_FIELDS)
            has_notes_heading = bool(re.search(r"^## .+$", bm.body, re.MULTILINE))
            new_filename = _build_rename_filename(new_title, existing_names)
            existing_names.add(new_filename)
            results.append(MigrationResult(
                filepath=bm.filepath,
                old_title=old_title,
                new_title=new_title,
                fields_removed=removed,
                heading_changed=has_notes_heading,
                skipped=False,
                old_filename=bm.filepath.name,
                new_filename=new_filename,
                old_pillar=str(bm.frontmatter.get("pillar", "")),
                new_pillar=_resolve_pillar(title_data, bm.frontmatter, pillars, fallback_pillar),
                mechanics=_resolve_mechanics(title_data, bm.frontmatter, aliases),
                tags=_resolve_tags(title_data, bm.frontmatter, allowed_prefixes),
            ))
        else:
            result = migrate_single_file(
                bm, title_data, existing_names, pillars, fallback_pillar, allowed_prefixes,
                aliases,
            )
            existing_names.add(result.new_filename)
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
        default=150,
        help="Number of files per Claude API call (default: 150)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N markdown files (token-bounded previews)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and generate titles without writing files",
    )
    parser.add_argument(
        "--taxonomy-file",
        type=Path,
        default=None,
        help="Optional taxonomy override file (YAML frontmatter with pillars/mechanics/entity_tags/deprecate/guidance)",
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

    if args.limit is not None and args.limit < 1:
        logger.error("--limit must be greater than zero")
        sys.exit(1)

    # Resolve taxonomy file from explicit flag or env/envrc
    taxonomy_file = args.taxonomy_file or resolve_taxonomy_file(Path.cwd())

    mode = "DRY RUN" if args.dry_run else "LIVE"
    logger.info("Starting migration (%s) on %s", mode, args.directory)

    results = migrate_directory(
        directory=args.directory,
        api_key=api_key,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        override_file=taxonomy_file,
        limit=args.limit,
    )

    skipped = sum(1 for r in results if r.skipped)
    migrated = sum(1 for r in results if not r.skipped)
    heading_changes = sum(1 for r in results if r.heading_changed)
    total_removed = sum(len(r.fields_removed) for r in results)
    renamed = sum(1 for r in results if not r.skipped and r.old_filename != r.new_filename)
    pillar_changes = sum(
        1 for r in results
        if not r.skipped and r.old_pillar != r.new_pillar
    )
    tagged = sum(1 for r in results if not r.skipped and r.tags)

    print(f"\n--- Migration Summary ({mode}) ---")
    print(f"Files processed: {len(results)}")
    print(f"Migrated:        {migrated}")
    print(f"Renamed:         {renamed}")
    print(f"Pillar changes:  {pillar_changes}")
    print(f"Notes tagged:    {tagged}")
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
                print(f"  {label:4}  {r.old_filename} -> {r.new_filename}  {title_change}")
                if r.old_pillar != r.new_pillar:
                    print(f"        pillar: {r.old_pillar}  ->  {r.new_pillar}")
                if r.mechanics:
                    print(f"        mechanics: {', '.join(r.mechanics)}")
                if r.tags:
                    print(f"        tags: {', '.join(r.tags)}")
                if r.fields_removed:
                    print(f"        removed: {', '.join(r.fields_removed)}")


if __name__ == "__main__":
    main()
