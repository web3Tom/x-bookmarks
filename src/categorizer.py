from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import anthropic

from src.models import Category, CategorizedTweet, Tweet
from src.taxonomy import (
    DEFAULT_TAXONOMY,
    build_entity_tags_section,
    build_taxonomy_section,
    load_override_file,
    load_taxonomy_override,
    merge_taxonomies,
    normalize_tags,
    parse_deprecations,
    parse_entity_tags,
    parse_override_guidance,
)

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 8192
_FALLBACK_CATEGORY = Category(
    slug="general", display_name="General", sub_category="Uncategorized"
)

_FRONTMATTER_CATEGORY_RE = re.compile(r'^category:\s*"(.+)"', re.MULTILINE)
_FRONTMATTER_SUBCATEGORY_RE = re.compile(r'^subCategory:\s*"(.+)"', re.MULTILINE)


def read_existing_taxonomy(output_dir: Path) -> dict[str, set[str]]:
    """Scan *.md frontmatter for existing category/subCategory values."""
    taxonomy: dict[str, set[str]] = {}
    if not output_dir.exists():
        return taxonomy
    for md_file in output_dir.glob("*.md"):
        content = md_file.read_text()
        cat_match = _FRONTMATTER_CATEGORY_RE.search(content)
        sub_match = _FRONTMATTER_SUBCATEGORY_RE.search(content)
        if cat_match and sub_match:
            cat = cat_match.group(1)
            sub = sub_match.group(1)
            taxonomy.setdefault(cat, set()).add(sub)
    return taxonomy


def _build_system_prompt(
    taxonomy: dict[str, set[str]],
    deprecations: list[str] | None = None,
    guidance: str | None = None,
    entity_tags: dict[str, list[str]] | None = None,
) -> str:
    """Build the categorization system prompt from the current vault taxonomy.

    Optionally includes deprecation rules, domain-specific guidance, and entity tags reference.
    """
    if taxonomy:
        taxonomy_section = (
            f"Existing categories and subcategories in the vault:\n"
            f"{build_taxonomy_section(taxonomy)}\n\n"
            "Rules:\n"
            "- Prefer the existing categories and subcategories listed above.\n"
            "- If a tweet fits an existing category but needs a new subcategory, add the new subcategory under that category.\n"
            "- If no existing category fits, create a new one in Title Case (e.g., \"Custom Category\") with a concise subcategory (e.g., \"Specific Topic\").\n"
            "- New names must be 2-4 words, Title Case, and must not duplicate or overlap existing ones.\n"
            "- Do NOT use \"General\" or \"Uncategorized\" — every tweet deserves a meaningful category."
        )
    else:
        taxonomy_section = (
            "No existing categories yet — this is the first run.\n\n"
            "Rules:\n"
            "- Create meaningful categories in Title Case (e.g., \"Technology\", \"Health & Wellness\").\n"
            "- Each category must have exactly one subcategory per tweet, also in Title Case.\n"
            "- Keep names concise (2-4 words). Group related content under the same category.\n"
            "- Do NOT use \"General\" or \"Uncategorized\" — every tweet deserves a meaningful category."
        )

    prompt_parts = [
        "You are a bookmark categorizer. Given a JSON array of tweets (bookmarks), "
        "assign each one to exactly one category and sub_category, and generate a concise, descriptive title.\n\n"
        f"{taxonomy_section}"
    ]

    if deprecations:
        deprecation_text = "\n\nAvoid these categories (do not assign or create them):\n"
        for dep in deprecations:
            deprecation_text += f"- {dep}\n"
        prompt_parts.append(deprecation_text.rstrip())

    if guidance:
        prompt_parts.append(f"\nDomain guidance:\n{guidance}")

    # Entity tags section (only if non-empty)
    if entity_tags:
        entity_section = build_entity_tags_section(entity_tags)
        if entity_section:
            prompt_parts.extend([
                "\n\nKnown entity tags (reference):\n",
                entity_section,
            ])
        prompt_parts.append(
            "\n\nIn addition to Domain (Category) and Discipline (Subcategory), "
            "extract specific entities mentioned in the text. Format them as prefix/entity-name "
            "(e.g., model/llama3, tool/docker). Use the provided entity_tags list as a primary reference, "
            "but you may generate new valid tags using the established prefixes if a new entity is encountered."
        )

    prompt_parts.extend([
        "\n\nTitle rules:\n"
        "- Generate a title (max 80 chars) for each bookmark.\n"
        "- For articles: prefer the article's actual title or topic.\n"
        "- For posts: summarize the key insight or topic (do not just truncate the tweet).\n"
        "- Title must be YAML-safe: no colons, no quotes, no newlines, no brackets.\n\n"
        "Return ONLY a JSON array, no other text.\n\n"
        "Response format:\n"
    ])

    if entity_tags:
        prompt_parts.append(
            '[{"tweet_id": "...", "category": "Technology", "sub_category": "Software Development", "title": "Clear descriptive title", "tags": ["model/deepseek", "provider/openrouter"]}, ...]'
        )
    else:
        prompt_parts.append(
            '[{"tweet_id": "...", "category": "Technology", "sub_category": "Software Development", "title": "Clear descriptive title"}, ...]'
        )

    return "".join(prompt_parts)


def _slugify(display_name: str) -> str:
    """Convert a display name to a kebab-case slug."""
    return re.sub(r"[\s&]+", "-", display_name.lower()).strip("-")


def build_prompt_payload(tweets: tuple[Tweet, ...]) -> str:
    """Build the JSON payload describing tweets for categorization."""
    entries = []
    for tweet in tweets:
        entry: dict[str, str] = {
            "tweet_id": tweet.id,
            "text": tweet.display_text,
            "author": tweet.author.username if tweet.author else "unknown",
        }
        if tweet.article_content:
            entry["article_excerpt"] = tweet.article_content[:2000]
        entries.append(entry)
    return json.dumps(entries, ensure_ascii=False)


def _sanitize_title(text: str) -> str:
    """Create a YAML-safe fallback title from raw tweet text."""
    title = text.replace("\n", " ").replace("\r", " ")
    title = title.replace(":", " -").replace('"', "'")
    title = title.replace("[", "(").replace("]", ")")
    if len(title) > 80:
        title = title[:80] + "..."
    return title


def parse_categorization_response(text: str) -> dict[str, tuple[Category, str, list[str]]]:
    """Parse the categorization response into a tweet_id -> (Category, title, tags) mapping."""
    cleaned = text.strip()
    fenced = re.match(r"```(?:json)?\s*\n?(.*?)\n?```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    entries = json.loads(cleaned)
    return {
        entry["tweet_id"]: (
            Category(
                slug=_slugify(entry["category"]),
                display_name=entry["category"],
                sub_category=entry["sub_category"],
            ),
            entry.get("title", ""),
            entry.get("tags", []),
        )
        for entry in entries
    }


def categorize_tweets(
    tweets: tuple[Tweet, ...],
    api_key: str,
    output_dir: Path | None = None,
    override_file: Path | None = None,
) -> tuple[tuple[CategorizedTweet, ...], dict]:
    """Categorize tweets using Claude in a single API call.

    Loads vault taxonomy, merges with optional override file, and applies deprecations/guidance/entity_tags.
    """
    vault_taxonomy = read_existing_taxonomy(output_dir) if output_dir is not None else {}

    # Load override file once using TaxonomyOverride
    override_data = load_taxonomy_override(override_file)
    override_taxonomy = override_data.taxonomy if override_data else None
    available = merge_taxonomies(vault_taxonomy, override_taxonomy)

    # Use DEFAULT_TAXONOMY if both vault and override are empty
    if not available:
        available = {cat: set(subs) for cat, subs in DEFAULT_TAXONOMY.items()}

    deprecations = override_data.deprecations if override_data else None
    guidance = override_data.guidance if override_data else None
    entity_tags = override_data.entity_tags if override_data else {}
    allowed_prefixes = set(entity_tags.keys()) if entity_tags else None

    system_prompt = _build_system_prompt(available, deprecations, guidance, entity_tags)

    client = anthropic.Anthropic(api_key=api_key)
    payload = build_prompt_payload(tweets)

    response = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": payload}],
    )

    raw_text = response.content[0].text
    category_map = parse_categorization_response(raw_text)

    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }

    categorized = []
    for tweet in tweets:
        entry = category_map.get(tweet.id)
        if entry:
            category, title, raw_tags = entry
            if not title:
                title = _sanitize_title(tweet.display_text)
            tags = normalize_tags(raw_tags, allowed_prefixes) if entity_tags else ()
        else:
            category = _FALLBACK_CATEGORY
            title = _sanitize_title(tweet.display_text)
            tags = ()
        categorized.append(CategorizedTweet(tweet=tweet, category=category, title=title, tags=tags))

    return tuple(categorized), usage
