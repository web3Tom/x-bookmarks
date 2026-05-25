from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from src.api_client import (
    BookmarkDeleteRateLimitError,
    BookmarkWriteScopeError,
    delete_bookmark,
    fetch_bookmarks,
)
from src.categorizer import categorize_tweets
from src.config import load_config
from src.markdown_writer import read_existing_ids, write_bookmarks
from src.removal import (
    backfill_synthesized_false,
    max_live_removals,
    remove_candidates,
    scan_synthesized_bookmark_notes,
)

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


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="x-bookmarks",
        description="Fetch X bookmarks or remove synthesized bookmarks.",
    )
    parser.add_argument(
        "--remove-synthesized-bookmarks",
        action="store_true",
        help="Remove X bookmarks for active notes with strict synthesized: true.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview synthesized bookmark removal without deleting or archiving.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Skip the interactive confirmation for live removal mode.",
    )
    parser.add_argument(
        "--max",
        type=int,
        dest="max_removals",
        help=f"Maximum live removals to attempt, capped at {max_live_removals()}.",
    )
    args = parser.parse_args(argv)
    if (args.dry_run or args.confirm or args.max_removals is not None) and not args.remove_synthesized_bookmarks:
        parser.error("--dry-run, --confirm, and --max require --remove-synthesized-bookmarks")
    if args.max_removals is not None and args.max_removals < 1:
        parser.error("--max must be greater than zero")
    return args


def _build_removal_record(
    *,
    run_id: str,
    status: str,
    started_at: str,
    duration_ms: int,
    output_dir: Path,
    archive_dir: Path,
    dry_run: bool,
    confirmed: bool,
    eligible: int = 0,
    attempted: int = 0,
    removed: int = 0,
    archived: int = 0,
    skipped: int = 0,
    failed: int = 0,
    removed_tweet_ids: tuple[str, ...] = (),
    failed_tweet_ids: tuple[dict[str, str], ...] = (),
    warnings: tuple[str, ...] = (),
    error: str | None = None,
) -> dict:
    record = {
        "run_id": run_id,
        "status": status,
        "mode": "remove_synthesized_bookmarks",
        "started_at": started_at,
        "duration_ms": duration_ms,
        "dry_run": dry_run,
        "confirmed": confirmed,
        "output_dir": str(output_dir),
        "archive_dir": str(archive_dir),
        "removal": {
            "eligible": eligible,
            "attempted": attempted,
            "removed": removed,
            "archived": archived,
            "skipped": skipped,
            "failed": failed,
            "removed_tweet_ids": list(removed_tweet_ids),
            "failed_tweet_ids": list(failed_tweet_ids),
            "warnings": list(warnings),
        },
    }
    if error:
        record["error"] = error
    return record


def _count_categories(categorized: tuple) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ct in categorized:
        key = ct.category.display_name
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _run_remove_synthesized_bookmarks(
    *,
    config,
    run_id: str,
    started_at: str,
    t_start: float,
    dry_run: bool,
    confirmed: bool,
    max_removals: int | None,
    input_func=None,
) -> int:
    output_dir = config.output_dir
    archive_dir = output_dir / "archive"
    print(f"[{run_id}] Output directory: {output_dir}")
    print(f"[{run_id}] Removal mode: scanning active notes only.")

    backfill = backfill_synthesized_false(output_dir)
    print(
        f"[{run_id}] Backfill checked {backfill.scanned} active note(s); "
        f"updated {backfill.updated} with synthesized: false."
    )
    if backfill.missing_after:
        print(f"[{run_id}] Warning: {backfill.missing_after} active note(s) still missing synthesized.")
    if backfill.true_values:
        print(f"[{run_id}] Found {backfill.true_values} active note(s) with synthesized: true.")
    for warning in backfill.warnings:
        print(f"[{run_id}] Warning: {warning}")

    scan = scan_synthesized_bookmark_notes(output_dir)
    for warning in scan.warnings:
        print(f"[{run_id}] Warning: {warning}")

    eligible = scan.eligible
    print(f"[{run_id}] Eligible synthesized bookmark note(s): {len(eligible)}")

    if not eligible:
        duration_ms = int((time.monotonic() - t_start) * 1000)
        record = _build_removal_record(
            run_id=run_id,
            status="noop",
            started_at=started_at,
            duration_ms=duration_ms,
            output_dir=output_dir,
            archive_dir=archive_dir,
            dry_run=dry_run,
            confirmed=confirmed,
            skipped=scan.skipped,
            warnings=scan.warnings + backfill.warnings,
        )
        history_path = _append_history(output_dir, record)
        print(f"[{run_id}] History written to {history_path}")
        return 0

    limit = min(max_removals or max_live_removals(), max_live_removals())
    if not dry_run and len(eligible) > limit:
        print(
            f"[{run_id}] Processing first {limit} eligible bookmark(s); "
            "run again after the rate-limit reset for the remainder."
        )

    if dry_run:
        print(f"[{run_id}] Dry run: no X bookmarks will be removed and no files will be archived.")
    elif not confirmed:
        if input_func is None:
            input_func = input
        answer = input_func("Proceed? [y/N] ").strip().lower()
        if answer != "y":
            duration_ms = int((time.monotonic() - t_start) * 1000)
            record = _build_removal_record(
                run_id=run_id,
                status="cancelled",
                started_at=started_at,
                duration_ms=duration_ms,
                output_dir=output_dir,
                archive_dir=archive_dir,
                dry_run=dry_run,
                confirmed=False,
                eligible=len(eligible),
                skipped=scan.skipped,
                warnings=scan.warnings + backfill.warnings,
            )
            history_path = _append_history(output_dir, record)
            print(f"[{run_id}] Cancelled. History written to {history_path}")
            return 1

    try:
        stats = remove_candidates(
            eligible,
            output_dir=output_dir,
            dry_run=dry_run,
            max_removals=max_removals,
            delete_bookmark=lambda tweet_id: delete_bookmark(config, tweet_id),
        )
    except (BookmarkWriteScopeError, BookmarkDeleteRateLimitError) as exc:
        duration_ms = int((time.monotonic() - t_start) * 1000)
        message = str(exc)
        record = _build_removal_record(
            run_id=run_id,
            status="failed",
            started_at=started_at,
            duration_ms=duration_ms,
            output_dir=output_dir,
            archive_dir=archive_dir,
            dry_run=dry_run,
            confirmed=confirmed,
            eligible=len(eligible),
            skipped=scan.skipped,
            warnings=scan.warnings + backfill.warnings,
            error=message,
        )
        history_path = _append_history(output_dir, record)
        print(f"[{run_id}] Error: {message}")
        print(f"[{run_id}] History written to {history_path}")
        return 1

    duration_ms = int((time.monotonic() - t_start) * 1000)
    status = "dry_run" if dry_run else ("partial_failure" if stats.failed else "success")
    skipped = scan.skipped + stats.skipped
    warnings = backfill.warnings + scan.warnings + stats.warnings
    record = _build_removal_record(
        run_id=run_id,
        status=status,
        started_at=started_at,
        duration_ms=duration_ms,
        output_dir=output_dir,
        archive_dir=archive_dir,
        dry_run=dry_run,
        confirmed=confirmed,
        eligible=stats.eligible,
        attempted=stats.attempted,
        removed=stats.removed,
        archived=stats.archived,
        skipped=skipped,
        failed=stats.failed,
        removed_tweet_ids=stats.removed_tweet_ids,
        failed_tweet_ids=stats.failed_tweet_ids,
        warnings=warnings,
    )
    history_path = _append_history(output_dir, record)

    print(f"\n--- Removal Summary [{run_id}] ---")
    print(f"Eligible:       {stats.eligible}")
    print(f"Attempted:      {stats.attempted}")
    print(f"Removed:        {stats.removed}")
    print(f"Archived:       {stats.archived}")
    print(f"Skipped:        {skipped}")
    print(f"Failed:         {stats.failed}")
    print(f"Duration:       {duration_ms}ms")
    for warning in stats.warnings:
        print(f"[{run_id}] Warning: {warning}")
    for failure in stats.failed_tweet_ids:
        print(f"[{run_id}] Failed {failure['tweet_id']}: {failure['reason']}")
    print(f"\n[{run_id}] History appended to {history_path}")
    return 1 if stats.failed else 0


def _run_sync(config, run_id: str, started_at: str, t_start: float) -> None:
    """Fetch bookmarks, categorize, and write to Obsidian vault."""
    print(f"[{run_id}] Output directory: {config.output_dir}")
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
        print(
            f"[{run_id}] {article_count} of {len(novel)} new bookmark(s) "
            f"link to articles ({with_content} with content from API)."
        )

    print(f"[{run_id}] Categorizing {len(novel)} new bookmark(s) with Claude...")

    categorized, usage = categorize_tweets(
        novel,
        api_key=config.anthropic_api_key,
        output_dir=config.output_dir,
        override_file=config.taxonomy_file,
    )

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


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    run_id = uuid.uuid4().hex[:12]
    started_at = datetime.now(timezone.utc).isoformat()
    t_start = time.monotonic()

    try:
        config = load_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Run 'x-bookmarks-auth' to set up credentials, or check .env file.")
        sys.exit(1)

    if args.remove_synthesized_bookmarks:
        code = _run_remove_synthesized_bookmarks(
            config=config,
            run_id=run_id,
            started_at=started_at,
            t_start=t_start,
            dry_run=args.dry_run,
            confirmed=args.confirm,
            max_removals=args.max_removals,
        )
        if code:
            sys.exit(code)
        return

    _run_sync(config, run_id, started_at, t_start)


if __name__ == "__main__":
    main()
