from __future__ import annotations

import json
import re

import anthropic

from src.models import Category, CategorizedTweet, Tweet

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 8192
_FALLBACK_CATEGORY = Category(slug="general", display_name="General")

SYSTEM_PROMPT = """\
You are a bookmark categorizer. Given a JSON array of tweets (bookmarks), \
assign each one to exactly one category.

Rules:
- Use conservative, broad categories (aim for ~10 max total).
- Use kebab-case slugs (e.g., "machine-learning", "web-dev", "career-advice").
- Each display_name should be Title Case (e.g., "Machine Learning").
- Group similar topics together rather than creating many narrow categories.
- Return ONLY a JSON array, no other text.

Response format:
[{"tweet_id": "...", "slug": "category-slug", "display_name": "Category Name"}, ...]
"""


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


def parse_categorization_response(text: str) -> dict[str, Category]:
    """Parse the categorization response into a tweet_id -> Category mapping."""
    cleaned = text.strip()
    fenced = re.match(r"```(?:json)?\s*\n?(.*?)\n?```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    entries = json.loads(cleaned)
    return {
        entry["tweet_id"]: Category(
            slug=entry["slug"],
            display_name=entry["display_name"],
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
        category = category_map.get(tweet.id, _FALLBACK_CATEGORY)
        categorized.append(CategorizedTweet(tweet=tweet, category=category))

    return tuple(categorized), usage
