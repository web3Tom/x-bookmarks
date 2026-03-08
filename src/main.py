from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.api_client import fetch_bookmarks
from src.categorizer import categorize_tweets
from src.config import load_config
from src.markdown_writer import read_existing_ids, write_bookmarks

_HISTORY_FILENAME = ".x-bookmarks-history.jsonl"


def _build_run_record(
    *,
    run_id: str,
    status: str,
    started_at: str,
    duration_ms: int,
    output_dir: str = "",
    fetched: int = 0,
    skipped: int = 0,
    novel: int = 0,
    articles: int = 0,
    files_written: int = 0,
    duplicates_skipped: int = 0,
    filenames: list[str] | None = None,
    token_usage: dict[str, int] | None = None,
    categories: dict[str, int] | None = None,
    error: str | None = None,
) -> dict:
    record = {
        "run_id": run_id,
        "status": status,
        "started_at": started_at,
        "duration_ms": duration_ms,
        "output_dir": output_dir,
        "bookmarks": {
            "fetched": fetched,
            "skipped_existing": skipped,
            "novel": novel,
            "articles": articles,
        },
        "output": {
            "files_written": files_written,
            "duplicates_skipped": duplicates_skipped,
            "filenames": filenames or [],
            "index_updated": False,
        },
        "token_usage": token_usage or {},
        "categories": categories or {},
    }
    if error:
        record["error"] = error
    return record


def _append_history(output_dir: Path, record: dict) -> Path:
    history_path = output_dir / _HISTORY_FILENAME
    output_dir.mkdir(parents=True, exist_ok=True)
    with history_path.open("a") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")
    return history_path


def _count_categories(categorized: tuple) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ct in categorized:
        key = ct.category.display_name
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def main() -> None:
    """Fetch bookmarks, categorize, and write to Obsidian vault."""
    run_id = uuid.uuid4().hex[:12]
    started_at = datetime.now(timezone.utc).isoformat()
    t_start = time.monotonic()

    try:
        config = load_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Run 'x-bookmarks-auth' to set up credentials, or check .env file.")
        sys.exit(1)

    print(f"[{run_id}] Fetching bookmarks for user {config.user_id}...")
    tweets = fetch_bookmarks(config)

    if not tweets:
        duration_ms = int((time.monotonic() - t_start) * 1000)
        print("No bookmarks found.")
        record = _build_run_record(
            run_id=run_id, status="empty", started_at=started_at,
            duration_ms=duration_ms, output_dir=str(config.output_dir),
        )
        history_path = _append_history(config.output_dir, record)
        print(f"[{run_id}] History written to {history_path}")
        return

    print(f"[{run_id}] Fetched {len(tweets)} bookmarks.")

    existing_ids = read_existing_ids(config.output_dir)
    novel = tuple(t for t in tweets if t.id not in existing_ids)
    skipped = len(tweets) - len(novel)

    if skipped:
        print(f"[{run_id}] Skipping {skipped} already-saved bookmark(s).")

    if not novel:
        duration_ms = int((time.monotonic() - t_start) * 1000)
        print("All bookmarks already saved. Nothing to do.")
        record = _build_run_record(
            run_id=run_id, status="noop", started_at=started_at,
            duration_ms=duration_ms, output_dir=str(config.output_dir),
            fetched=len(tweets), skipped=skipped,
        )
        history_path = _append_history(config.output_dir, record)
        print(f"[{run_id}] History written to {history_path}")
        return

    article_count = sum(1 for t in novel if t.article_url)
    if article_count:
        with_content = sum(1 for t in novel if t.article_content)
        print(f"[{run_id}] Found {article_count} article(s) ({with_content} with content from API).")

    print(f"[{run_id}] Categorizing {len(novel)} new bookmark(s) with Claude...")

    categorized, usage = categorize_tweets(novel, api_key=config.anthropic_api_key, output_dir=config.output_dir)

    print(f"[{run_id}] Writing to {config.output_dir}...")
    stats = write_bookmarks(categorized, config.output_dir)

    filenames = stats["filenames"]
    for fname in filenames:
        print(f"  + {fname}")


    category_counts = _count_categories(categorized)

    duration_ms = int((time.monotonic() - t_start) * 1000)

    print(f"\n--- Run Summary [{run_id}] ---")
    print(f"Bookmarks fetched:  {len(tweets)}")
    print(f"Already saved:      {skipped}")
    print(f"New bookmarks:      {len(novel)}")
    print(f"Files written:      {stats['files_written']}")
    print(f"Duplicates at write:{stats['duplicates_skipped']}")
    print(f"Tokens used:        {usage['input_tokens']} in / {usage['output_tokens']} out")
    print(f"Duration:           {duration_ms}ms")

    if category_counts:
        print("\nCategories:")
        for cat, count in category_counts.items():
            print(f"  {cat}: {count}")

    record = _build_run_record(
        run_id=run_id, status="success", started_at=started_at,
        duration_ms=duration_ms, output_dir=str(config.output_dir),
        fetched=len(tweets), skipped=skipped, novel=len(novel),
        articles=article_count, files_written=stats["files_written"],
        duplicates_skipped=stats["duplicates_skipped"],
        filenames=filenames, token_usage=usage,
        categories=category_counts,
    )
    history_path = _append_history(config.output_dir, record)
    print(f"\n[{run_id}] History appended to {history_path}")


if __name__ == "__main__":
    main()
