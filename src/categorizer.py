from __future__ import annotations

import json
import re

import anthropic

from src.models import Category, CategorizedTweet, Tweet

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 8192
_FALLBACK_CATEGORY = Category(
    slug="general", display_name="General", sub_category="Uncategorized"
)

TAXONOMY: dict[str, list[str]] = {
    "AI Coding": ["Coding Workflows", "Prompt & Context Engineering"],
    "Agent Architectures": ["Applied Agents", "Frameworks & Patterns"],
    "Agent Reliability": ["Evals & Observability"],
    "Context Engineering": ["RAG & Context", "Agent Memory"],
    "Model Systems": ["Inference & Serving", "Model Releases"],
    "AI Knowledge Systems": ["Obsidian & PKM"],
    "ML Research": ["Research Digest", "Applied ML"],
    "AI Product & Strategy": ["Monetization & GTM"],
    "AI Productivity": ["Workflows & Execution"],
    "AI Career & Mindset": ["Performance & Habits"],
}


def _build_taxonomy_block() -> str:
    """Format the taxonomy as a readable block for the system prompt."""
    lines: list[str] = []
    for category, subs in TAXONOMY.items():
        lines.append(f"- {category}")
        for sub in subs:
            lines.append(f"  - {sub}")
    return "\n".join(lines)


SYSTEM_PROMPT = f"""\
You are a bookmark categorizer. Given a JSON array of tweets (bookmarks), \
assign each one to exactly one category and sub_category from the fixed taxonomy below, \
and generate a concise, descriptive title for each bookmark.

Allowed categories and subcategories:
{_build_taxonomy_block()}

Rules:
- You MUST pick from the categories and subcategories listed above whenever possible.
- If a tweet does not clearly fit any category, use category "General" with sub_category "Uncategorized".
- If a tweet genuinely cannot fit any existing category and "General" would lose important signal, \
you MAY create a new category. When doing so:
  - Use Title Case for the category name (e.g., "AI Ethics")
  - Provide exactly one sub_category in Title Case (e.g., "Bias & Fairness")
  - Keep names concise (2-4 words)
  - Do NOT duplicate or overlap with existing categories
- Generate a title (max 80 chars) for each bookmark:
  - For articles: prefer the article's actual title or topic
  - For posts: summarize the key insight or topic (do not just truncate the tweet)
  - Title must be YAML-safe: no colons, no quotes, no newlines, no brackets
- Return ONLY a JSON array, no other text.

Response format:
[{{"tweet_id": "...", "category": "AI Coding", "sub_category": "Coding Workflows", "title": "LangGraph Agent Memory Patterns"}}, ...]
"""


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
) -> tuple[tuple[CategorizedTweet, ...], dict]:
    """Categorize tweets using Claude in a single API call."""
    client = anthropic.Anthropic(api_key=api_key)

    payload = build_prompt_payload(tweets)

    response = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=SYSTEM_PROMPT,
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
