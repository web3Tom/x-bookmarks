from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaxonomyOverride:
    """Parsed taxonomy override file with all optional fields."""

    pillars: tuple[str, ...] | None = None
    mechanics: tuple[str, ...] | None = None
    entity_tags: dict[str, list[str]] = None  # type: ignore
    deprecations: list[str] | None = None
    aliases: dict[str, str] = None  # type: ignore
    guidance: str | None = None

    def __post_init__(self) -> None:
        """Type-guard all fields; convert None to empty defaults for safe access."""
        if self.entity_tags is None:
            object.__setattr__(self, "entity_tags", {})
        if self.aliases is None:
            object.__setattr__(self, "aliases", {})


# Neutral, domain-agnostic default pillars (name -> focus). The user's real
# domain pillars live only in the private override file, never in this repo.
DEFAULT_PILLARS: tuple[tuple[str, str], ...] = (
    ("Theory & Concepts", "Foundational ideas, research, and how things work conceptually."),
    ("Applied Practice", "Building, implementing, and hands-on workflows."),
    ("Operations", "Deploying, measuring, securing, and maintaining systems."),
    ("Strategy", "Business, career, market, and human/decision elements."),
)
DEFAULT_PILLAR_NAMES: tuple[str, ...] = tuple(name for name, _ in DEFAULT_PILLARS)

# Neutral default mechanics vocabulary (empty; seeded via the override file).
DEFAULT_MECHANICS: tuple[str, ...] = ()

# Closed set of allowed entity-tag prefixes (nouns). `provider` and `concept`
# were dropped in the faceted refactor — concepts live in `mechanics` now.
ENTITY_PREFIXES: tuple[str, ...] = ("framework", "harness", "model", "tool")


def _slugify(value: str) -> str:
    """Lowercase kebab-case slug: spaces/underscores -> -, drop chars outside
    [a-z0-9-], collapse repeats, trim edges. Mirrors the vault-migration rule."""
    slug = value.lower().strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


def slugify_mechanic(value: str) -> str | None:
    """Slugify a single mechanic; return None if nothing survives."""
    return _slugify(value) or None


def normalize_mechanics(
    raw: Iterable[str] | None,
    aliases: dict[str, str] | None = None,
) -> tuple[str, ...]:
    """Slugify mechanics, collapse synonyms via `aliases`, dedupe, drop empties.

    Each slug is mapped through `aliases` (retired -> canonical) before dedup, so
    a note carrying both a synonym and its canonical form collapses to one entry
    in first-seen order. The collapse is deterministic and independent of the LLM.
    """
    if not raw:
        return ()
    alias_map = aliases or {}
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        slug = slugify_mechanic(str(item))
        if not slug:
            continue
        slug = alias_map.get(slug, slug)
        if slug not in seen:
            result.append(slug)
            seen.add(slug)
    return tuple(result)


def validate_pillar(raw: str, allowed: Sequence[str], fallback: str) -> str:
    """Return `raw` if it is one of `allowed`, else `fallback` with a loud warning."""
    if raw in allowed:
        return raw
    logger.warning(
        "Pillar %r not in allowed pillars %s — falling back to %r",
        raw, list(allowed), fallback,
    )
    return fallback


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


def group_entity_tags(tags: Iterable[str]) -> dict[str, list[str]]:
    """Split flat `prefix/entity` tags into a nested {prefix: [entity, ...]} dict.

    Only keeps prefixes in ENTITY_PREFIXES, in that fixed order. Dedupes entities
    within each prefix (first-seen order). Returns {} when nothing qualifies.
    """
    grouped: dict[str, list[str]] = {}
    for tag in tags:
        if "/" not in tag:
            continue
        prefix, entity = tag.split("/", 1)
        prefix = prefix.strip()
        entity = entity.strip()
        if prefix not in ENTITY_PREFIXES or not entity:
            continue
        bucket = grouped.setdefault(prefix, [])
        if entity not in bucket:
            bucket.append(entity)
    # Re-emit in fixed prefix order
    return {p: grouped[p] for p in ENTITY_PREFIXES if p in grouped}


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


def build_pillars_section(
    pillars: Sequence[str],
    descriptions: Mapping[str, str] | None = None,
) -> str:
    """Build a bulleted list of pillars, with optional `- Name: focus` descriptions."""
    lines: list[str] = []
    for name in pillars:
        focus = descriptions.get(name) if descriptions else None
        lines.append(f"- {name}: {focus}" if focus else f"- {name}")
    return "\n".join(lines)


def build_mechanics_section(mechanics: Sequence[str]) -> str:
    """Build a comma-separated reference list of established mechanics.

    Returns empty string when no mechanics are provided.
    """
    if not mechanics:
        return ""
    return ", ".join(sorted(set(mechanics)))


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


def _coerce_str_list(value: object) -> tuple[str, ...] | None:
    """Coerce a YAML value into a tuple of stripped strings, or None if not a list."""
    if not isinstance(value, list):
        return None
    return tuple(str(item).strip() for item in value if str(item).strip())


def load_taxonomy_override(filepath: Path | None) -> TaxonomyOverride | None:
    """Load and parse a taxonomy override file completely.

    Reads the YAML frontmatter and Markdown body once. Type-guards all fields.
    Returns TaxonomyOverride with pillars/mechanics/entity_tags/deprecations/guidance.
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
        return TaxonomyOverride(guidance=body.strip() or None)

    if not isinstance(parsed, dict):
        logger.warning("Override file frontmatter is not a YAML dict: %s", filepath)
        return TaxonomyOverride(guidance=body.strip() or None)

    pillars = _coerce_str_list(parsed.get("pillars"))
    if parsed.get("pillars") is not None and pillars is None:
        logger.warning("Override file 'pillars:' is not a list: %s", filepath)

    mechanics = _coerce_str_list(parsed.get("mechanics"))
    if parsed.get("mechanics") is not None and mechanics is None:
        logger.warning("Override file 'mechanics:' is not a list: %s", filepath)

    entity_tags = parsed.get("entity_tags")
    if entity_tags is not None and not isinstance(entity_tags, dict):
        logger.warning("Override file 'entity_tags:' is not a dict: %s", filepath)
        entity_tags = {}

    deprecations = parsed.get("deprecate")
    if deprecations is not None and not isinstance(deprecations, list):
        logger.warning("Override file 'deprecate:' is not a list: %s", filepath)
        deprecations = None

    aliases = parsed.get("aliases")
    if aliases is not None and not isinstance(aliases, dict):
        logger.warning("Override file 'aliases:' is not a dict: %s", filepath)
        aliases = None
    elif isinstance(aliases, dict):
        aliases = {
            str(k): str(v) for k, v in aliases.items() if k is not None and v is not None
        }

    guidance = body.strip() or None

    return TaxonomyOverride(
        pillars=pillars,
        mechanics=mechanics,
        entity_tags=entity_tags or {},
        deprecations=deprecations,
        aliases=aliases or {},
        guidance=guidance,
    )


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
