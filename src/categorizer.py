from __future__ import annotations

import json
import re
from pathlib import Path

import anthropic

from src.models import Category, CategorizedTweet, Tweet

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


def _build_taxonomy_block(taxonomy: dict[str, set[str]]) -> str:
    lines: list[str] = []
    for category, subs in sorted(taxonomy.items()):
        lines.append(f"- {category}")
        for sub in sorted(subs):
            lines.append(f"  - {sub}")
    return "\n".join(lines)


def _build_system_prompt(taxonomy: dict[str, set[str]]) -> str:
    """Build the categorization system prompt from the current vault taxonomy."""
    if taxonomy:
        taxonomy_section = (
            f"Existing categories and subcategories in the vault:\n"
            f"{_build_taxonomy_block(taxonomy)}\n\n"
            "Rules:\n"
            "- Prefer the existing categories and subcategories listed above.\n"
            "- If a tweet fits an existing category but needs a new subcategory, add the new subcategory under that category.\n"
            "- If no existing category fits, create a new one in Title Case (e.g., \"AI Ethics\") with a concise subcategory (e.g., \"Bias & Fairness\").\n"
            "- New names must be 2-4 words, Title Case, and must not duplicate or overlap existing ones.\n"
            "- Do NOT use \"General\" or \"Uncategorized\" — every tweet deserves a meaningful category."
        )
    else:
        taxonomy_section = (
            "No existing categories yet — this is the first run.\n\n"
            "Rules:\n"
            "- Create meaningful categories in Title Case (e.g., \"AI Coding\", \"Agent Architectures\").\n"
            "- Each category must have exactly one subcategory per tweet, also in Title Case.\n"
            "- Keep names concise (2-4 words). Group related content under the same category.\n"
            "- Do NOT use \"General\" or \"Uncategorized\" — every tweet deserves a meaningful category."
        )

    return (
        "You are a bookmark categorizer. Given a JSON array of tweets (bookmarks), "
        "assign each one to exactly one category and sub_category, and generate a concise, descriptive title.\n\n"
        f"{taxonomy_section}\n\n"
        "Title rules:\n"
        "- Generate a title (max 80 chars) for each bookmark.\n"
        "- For articles: prefer the article's actual title or topic.\n"
        "- For posts: summarize the key insight or topic (do not just truncate the tweet).\n"
        "- Title must be YAML-safe: no colons, no quotes, no newlines, no brackets.\n\n"
        "Return ONLY a JSON array, no other text.\n\n"
        "Response format:\n"
        '[{"tweet_id": "...", "category": "AI Coding", "sub_category": "Coding Workflows", "title": "LangGraph Agent Memory Patterns"}, ...]'
    )


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


def parse_categorization_response(text: str) -> dict[str, tuple[Category, str]]:
    """Parse the categorization response into a tweet_id -> (Category, title) mapping."""
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
        )
        for entry in entries
    }


def categorize_tweets(
    tweets: tuple[Tweet, ...],
    api_key: str,
    output_dir: Path | None = None,
) -> tuple[tuple[CategorizedTweet, ...], dict]:
    """Categorize tweets using Claude in a single API call."""
    taxonomy = read_existing_taxonomy(output_dir) if output_dir is not None else {}
    system_prompt = _build_system_prompt(taxonomy)

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
            category, title = entry
            if not title:
                title = _sanitize_title(tweet.display_text)
        else:
            category = _FALLBACK_CATEGORY
            title = _sanitize_title(tweet.display_text)
        categorized.append(CategorizedTweet(tweet=tweet, category=category, title=title))

    return tuple(categorized), usage
