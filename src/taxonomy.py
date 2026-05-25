from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class TaxonomyOverride:
    """Parsed taxonomy override file with all optional fields."""

    taxonomy: dict[str, list[str]] | None = None
    entity_tags: dict[str, list[str]] = None  # type: ignore
    deprecations: list[str] | None = None
    guidance: str | None = None

    def __post_init__(self) -> None:
        """Type-guard all fields; convert None to empty defaults for safe access."""
        if self.entity_tags is None:
            object.__setattr__(self, "entity_tags", {})


# Neutral, domain-agnostic default taxonomy (no catch-all/"Miscellaneous" bucket)
DEFAULT_TAXONOMY: dict[str, list[str]] = {
    "Technology": [
        "Software Development",
        "Hardware",
        "Infrastructure & DevOps",
        "Data & Analytics",
    ],
    "Business & Finance": [
        "Markets & Investing",
        "Entrepreneurship",
        "Career",
    ],
    "Science & Research": [
        "Research & Papers",
        "Engineering",
        "Environment",
    ],
    "Health & Wellness": [
        "Fitness",
        "Nutrition",
        "Mental Health",
    ],
    "Learning & Education": [
        "Tutorials & Guides",
        "Books",
        "Courses",
    ],
    "Culture & Society": [
        "Arts & Media",
        "Politics & Policy",
        "History",
    ],
    "Productivity & Tools": [
        "Workflows",
        "Apps & Utilities",
        "Automation",
    ],
}


def normalize_tag(raw: str, allowed_prefixes: set[str] | None = None) -> str | None:
    """Normalize a single tag to `prefix/entity-name` format.

    Rules:
    - lowercase and strip whitespace
    - require exactly one `/` splitting prefix and entity
    - slugify entity: spaces/underscores → `-`, drop chars outside [a-z0-9-], collapse repeats
    - if allowed_prefixes is provided and prefix not in it, return None (drop tag)
    - return None if malformed

    Returns normalized tag or None if invalid/dropped.
    """
    raw = raw.lower().strip()
    if "/" not in raw:
        return None
    parts = raw.split("/", 1)
    if len(parts) != 2:
        return None
    prefix, entity = parts
    prefix = prefix.strip()
    entity = entity.strip()

    if not prefix or not entity:
        return None

    # Check prefix against allowed set
    if allowed_prefixes is not None and prefix not in allowed_prefixes:
        return None

    # Slugify entity: replace spaces/underscores with -, drop invalid chars, collapse repeats
    entity_slug = re.sub(r"[\s_]+", "-", entity)
    entity_slug = re.sub(r"[^a-z0-9-]", "", entity_slug)
    entity_slug = re.sub(r"-{2,}", "-", entity_slug)
    entity_slug = entity_slug.strip("-")

    if not entity_slug:
        return None

    return f"{prefix}/{entity_slug}"


def normalize_tags(
    raw_tags: list[str] | None,
    allowed_prefixes: set[str] | None = None,
) -> tuple[str, ...]:
    """Normalize a list of raw tags to tuple, deduping and dropping invalid ones.

    Preserves first-seen order; silently drops malformed or unknown-prefix tags.
    Returns tuple of normalized tags.
    """
    if not raw_tags:
        return ()

    seen: set[str] = set()
    result: list[str] = []
    for raw in raw_tags:
        normalized = normalize_tag(raw, allowed_prefixes)
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return tuple(result)


def build_entity_tags_section(entity_tags: dict[str, list[str]]) -> str:
    """Build a formatted reference block of allowed entity tags.

    Format: `- prefix: entity1, entity2, ...` (sorted by prefix, entities alphabetically).
    Returns empty string if entity_tags is empty.
    """
    if not entity_tags:
        return ""

    lines: list[str] = []
    for prefix in sorted(entity_tags.keys()):
        entities = sorted(set(entity_tags[prefix]))
        lines.append(f"- {prefix}: {', '.join(entities)}")
    return "\n".join(lines)


def build_taxonomy_section(taxonomy: dict[str, set[str] | list[str]]) -> str:
    """Build a formatted bulleted category/subcategory block from a taxonomy dict.

    Accepts either sets or lists of subcategories; converts sets to sorted lists.
    Returns a string with "- Category" then "  - Subcategory" lines, sorted.
    """
    lines: list[str] = []
    for category, subs in sorted(taxonomy.items()):
        lines.append(f"- {category}")
        # Convert to list if it's a set, then sort
        sub_list = sorted(subs) if isinstance(subs, (set, list)) else []
        for sub in sub_list:
            lines.append(f"  - {sub}")
    return "\n".join(lines)


def _split_frontmatter_body(content: str) -> tuple[str, str]:
    """Split frontmatter and body on --- delimiters.

    Returns (yaml_block, body) where yaml_block is the content between --- markers
    (without the delimiters themselves).
    Raises ValueError if format is malformed.
    """
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


def load_taxonomy_override(filepath: Path | None) -> TaxonomyOverride | None:
    """Load and parse a taxonomy override file completely.

    Reads the YAML frontmatter and Markdown body once. Type-guards all fields.
    Returns TaxonomyOverride with all four fields populated (or None values).
    Returns None if filepath is None or file is missing/unreadable.
    Logs warnings on errors; on YAML errors returns safe defaults with body text.
    """
    if filepath is None:
        return None

    if not filepath.exists():
        logger.warning("Taxonomy override file not found: %s", filepath)
        return None

    try:
        content = filepath.read_text(encoding="utf-8")
        yaml_block, body = _split_frontmatter_body(content)
    except (ValueError, OSError) as exc:
        logger.warning("Failed to read override file %s: %s", filepath, exc)
        return None

    try:
        parsed = yaml.safe_load(yaml_block)
    except yaml.YAMLError as exc:
        logger.warning("Failed to parse YAML in override file %s: %s", filepath, exc)
        # Return safe defaults with body text preserved
        return TaxonomyOverride(
            taxonomy=None,
            entity_tags={},
            deprecations=None,
            guidance=body.strip() or None,
        )

    if not isinstance(parsed, dict):
        logger.warning("Override file frontmatter is not a YAML dict: %s", filepath)
        return TaxonomyOverride(taxonomy=None, entity_tags={}, deprecations=None, guidance=body.strip() or None)

    # Type-guard each field
    taxonomy = parsed.get("taxonomy")
    if taxonomy is not None and not isinstance(taxonomy, dict):
        logger.warning("Override file 'taxonomy:' is not a dict: %s", filepath)
        taxonomy = None

    entity_tags = parsed.get("entity_tags")
    if entity_tags is not None and not isinstance(entity_tags, dict):
        logger.warning("Override file 'entity_tags:' is not a dict: %s", filepath)
        entity_tags = {}

    deprecations = parsed.get("deprecate")
    if deprecations is not None and not isinstance(deprecations, list):
        logger.warning("Override file 'deprecate:' is not a list: %s", filepath)
        deprecations = None

    guidance = body.strip() or None

    return TaxonomyOverride(
        taxonomy=taxonomy,
        entity_tags=entity_tags or {},
        deprecations=deprecations,
        guidance=guidance,
    )


def load_override_file(filepath: Path | None) -> dict[str, list[str]] | None:
    """Load taxonomy from override file's YAML frontmatter.

    Delegates to load_taxonomy_override; returns only the taxonomy dict.
    Returns None if: filepath is None, file missing, malformed YAML, or no `taxonomy:` key.
    """
    override = load_taxonomy_override(filepath)
    if override is None or override.taxonomy is None:
        return None
    return override.taxonomy


def parse_deprecations(filepath: Path | None) -> list[str] | None:
    """Extract `deprecate:` list from override file's YAML frontmatter.

    Delegates to load_taxonomy_override; returns only the deprecations list.
    Returns None if: filepath is None, file missing, malformed, or no `deprecate:` key.
    """
    override = load_taxonomy_override(filepath)
    if override is None:
        return None
    return override.deprecations


def parse_override_guidance(filepath: Path | None) -> str | None:
    """Extract Markdown body (after closing ---) from override file.

    Delegates to load_taxonomy_override; returns only the guidance text.
    Returns None if no file or file is None.
    Returns empty string if no body.
    """
    override = load_taxonomy_override(filepath)
    if override is None:
        return None
    return override.guidance or ""


def parse_entity_tags(filepath: Path | None) -> dict[str, list[str]]:
    """Extract `entity_tags:` dict from override file's YAML frontmatter.

    Delegates to load_taxonomy_override; returns the entity_tags dict.
    Returns {} if: filepath is None, file missing, malformed, or no `entity_tags:` key.
    """
    override = load_taxonomy_override(filepath)
    if override is None:
        return {}
    return override.entity_tags


def merge_taxonomies(
    vault: dict[str, set[str]],
    override: dict[str, list[str]] | None,
) -> dict[str, set[str]]:
    """Merge vault and override taxonomies using union semantics.

    Every category and subcategory from override is added to the result.
    Subcategories are unioned as sets.
    If override is None, returns vault unchanged.
    """
    if override is None:
        return vault

    result = {cat: set(subs) for cat, subs in vault.items()}

    for cat, subs in override.items():
        if cat not in result:
            result[cat] = set()
        result[cat].update(subs if isinstance(subs, list) else [])

    return result
