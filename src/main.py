from __future__ import annotations

import sys

from src.api_client import fetch_bookmarks
from src.categorizer import categorize_tweets
from src.config import load_config
from src.markdown_writer import write_bookmarks


def main() -> None:
    """Fetch bookmarks, categorize, and write to Obsidian vault."""
    try:
        config = load_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Run 'x-bookmarks-auth' to set up credentials, or check .env file.")
        sys.exit(1)

    print(f"Fetching bookmarks for user {config.user_id}...")
    tweets = fetch_bookmarks(config)

    if not tweets:
        print("No bookmarks found.")
        return

    print(f"Fetched {len(tweets)} bookmarks.")

    article_count = sum(1 for t in tweets if t.article_url)
    if article_count:
        with_content = sum(1 for t in tweets if t.article_content)
        print(f"Found {article_count} article(s) ({with_content} with content from API).")

    print("Categorizing with Claude...")

    categorized, usage = categorize_tweets(tweets, api_key=config.anthropic_api_key)

    print(f"Writing to {config.output_dir}...")
    stats = write_bookmarks(categorized, config.output_dir)

    print("\n--- Run Summary ---")
    print(f"Bookmarks fetched:  {len(tweets)}")
    print(f"Files written:      {stats['files_written']}")
    print(f"Bookmarks written:  {stats['bookmarks_written']}")
    print(f"Duplicates skipped: {stats['duplicates_skipped']}")
    print(f"Tokens used:        {usage['input_tokens']} in / {usage['output_tokens']} out")


if __name__ == "__main__":
    main()
