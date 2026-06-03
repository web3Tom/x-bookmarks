from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import anthropic

from src.models import CategorizedTweet, Tweet
from src.taxonomy import (
    DEFAULT_MECHANICS,
    DEFAULT_PILLARS,
    DEFAULT_PILLAR_NAMES,
    ENTITY_PREFIXES,
    build_entity_tags_section,
    build_mechanics_section,
    build_pillars_section,
    load_taxonomy_override,
    normalize_mechanics,
    normalize_tags,
    validate_pillar,
)

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 8192


def _resolve_facets(
    override_data,
) -> tuple[list[str], dict[str, str] | None, tuple[str, ...], dict[str, list[str]]]:
    """Resolve (pillars, pillar_descriptions, mechanics_vocab, entity_tags).

    Pillars come from the override file if present, else the neutral defaults
    (which carry focus descriptions). Mechanics vocab and entity tags come from
    the override file, else neutral defaults.
    """
    if override_data and override_data.pillars:
        pillars = list(override_data.pillars)
        descriptions = None
    else:
        pillars = list(DEFAULT_PILLAR_NAMES)
        descriptions = {name: focus for name, focus in DEFAULT_PILLARS}

    if override_data and override_data.mechanics:
        mechanics_vocab = tuple(override_data.mechanics)
    else:
        mechanics_vocab = DEFAULT_MECHANICS

    entity_tags = override_data.entity_tags if override_data else {}
    return pillars, descriptions, mechanics_vocab, entity_tags


def _build_system_prompt(
    pillars: list[str],
    pillar_descriptions: dict[str, str] | None = None,
    mechanics_vocab: tuple[str, ...] = (),
    deprecations: list[str] | None = None,
    guidance: str | None = None,
    entity_tags: dict[str, list[str]] | None = None,
) -> str:
    """Build the categorization system prompt for the faceted schema.

    Teaches the fixed pillars, the established mechanics vocabulary, and the
    entity-tag prefixes. Optionally includes deprecations and domain guidance.
    """
    prompt_parts = [
        "You are a bookmark categorizer using a faceted classification model. "
        "Given a JSON array of tweets (bookmarks), assign each one:\n"
        "- exactly one `pillar` (the primary domain — pick from the fixed list below),\n"
        "- one or more `mechanics` (the verbs/concepts it is about — lowercase-dashed slugs),\n"
        "- a concise, descriptive `title`.\n\n"
        "Pillars (choose exactly one per tweet):\n"
        f"{build_pillars_section(pillars, pillar_descriptions)}\n\n"
        "Pillar rules:\n"
        "- Use ONLY the pillars listed above; do not invent new ones.\n"
        "- Pick the single closest pillar — never a catch-all.\n\n"
        "Mechanics rules:\n"
        "- Provide at least one mechanic per tweet.\n"
        "- Prefer reusing the established mechanics below; only coin a new one when none fit.\n"
        "- Mechanics are lowercase, dash-separated slugs (e.g. `rag`, `persistent-memory`)."
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

    # Entity tags section (only if non-empty)
    if entity_tags:
        entity_section = build_entity_tags_section(entity_tags)
        if entity_section:
            prompt_parts.append(f"\n\nKnown entity tags (reference):\n{entity_section}")
        prompt_parts.append(
            "\n\nAlso extract specific entities mentioned in the text as `prefix/entity-name` "
            f"tags. Allowed prefixes (nouns only): {', '.join(ENTITY_PREFIXES)} "
            "(e.g., framework/langgraph, model/llama3, tool/docker). Use the entity_tags "
            "list as a primary reference; you may add new entities under the established prefixes."
        )

    prompt_parts.append(
        "\n\nTitle rules:\n"
        "- Generate a title (max 80 chars) for each bookmark.\n"
        "- For articles: prefer the article's actual title or topic.\n"
        "- For posts: summarize the key insight or topic (do not just truncate the tweet).\n"
        "- Title must be YAML-safe: no colons, no quotes, no newlines, no brackets.\n\n"
        "Return ONLY a JSON array, no other text.\n\n"
        "Response format:\n"
    )

    if entity_tags:
        prompt_parts.append(
            '[{"tweet_id": "...", "pillar": "Applied Practice", '
            '"mechanics": ["rag", "persistent-memory"], "title": "Clear descriptive title", '
            '"tags": ["framework/langgraph", "model/deepseek"]}, ...]'
        )
    else:
        prompt_parts.append(
            '[{"tweet_id": "...", "pillar": "Applied Practice", '
            '"mechanics": ["rag", "persistent-memory"], "title": "Clear descriptive title"}, ...]'
        )

    return "".join(prompt_parts)


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


def parse_categorization_response(
    text: str,
) -> dict[str, tuple[str, tuple[str, ...], str, list[str]]]:
    """Parse the response into tweet_id -> (pillar, mechanics, title, tags).

    `pillar` and `mechanics` are returned raw (validation/normalization happens
    in categorize_tweets, which knows the allowed pillar set).
    """
    cleaned = text.strip()
    fenced = re.match(r"```(?:json)?\s*\n?(.*?)\n?```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    entries = json.loads(cleaned)
    return {
        entry["tweet_id"]: (
            str(entry.get("pillar", "")),
            tuple(entry.get("mechanics", []) or ()),
            entry.get("title", ""),
            entry.get("tags", []),
        )
        for entry in entries
    }


def categorize_tweets(
    tweets: tuple[Tweet, ...],
    api_key: str,
    override_file: Path | None = None,
) -> tuple[tuple[CategorizedTweet, ...], dict]:
    """Categorize tweets using Claude in a single API call.

    Loads the optional override file (pillars/mechanics/entity_tags/deprecations/
    guidance) and falls back to neutral defaults.
    """
    override_data = load_taxonomy_override(override_file)
    pillars, descriptions, mechanics_vocab, entity_tags = _resolve_facets(override_data)
    deprecations = override_data.deprecations if override_data else None
    guidance = override_data.guidance if override_data else None
    fallback_pillar = pillars[0]

    system_prompt = _build_system_prompt(
        pillars, descriptions, mechanics_vocab, deprecations, guidance, entity_tags,
    )

    client = anthropic.Anthropic(api_key=api_key)
    payload = build_prompt_payload(tweets)

    response = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": payload}],
    )

    raw_text = response.content[0].text
    response_map = parse_categorization_response(raw_text)

    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }

    allowed_prefixes = set(ENTITY_PREFIXES)
    categorized = []
    for tweet in tweets:
        entry = response_map.get(tweet.id)
        if entry:
            raw_pillar, raw_mechanics, title, raw_tags = entry
            pillar = validate_pillar(raw_pillar, pillars, fallback_pillar)
            mechanics = normalize_mechanics(raw_mechanics)
            if not mechanics:
                logger.warning("No mechanics for tweet %s; emitting fallback", tweet.id)
            if not title:
                title = _sanitize_title(tweet.display_text)
            tags = normalize_tags(list(raw_tags), allowed_prefixes)
        else:
            logger.warning("No categorization for tweet %s; using fallback pillar", tweet.id)
            pillar = fallback_pillar
            mechanics = ()
            title = _sanitize_title(tweet.display_text)
            tags = ()
        categorized.append(
            CategorizedTweet(
                tweet=tweet, pillar=pillar, title=title, mechanics=mechanics, tags=tags,
            )
        )

    return tuple(categorized), usage
