from __future__ import annotations

import argparse
import json
import os
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
from src.enrichment import backfill_titles
from src.markdown_writer import read_existing_ids, write_bookmarks
from src.removal import (
    backfill_synthesized_false,
    max_live_removals,
    remove_candidates,
    scan_synthesized_bookmark_notes,
)
from src.unofficial_client import (
    AUTH_TOKEN_ENV,
    CT0_ENV,
    ENABLE_ENV,
    UnofficialDisabledError,
    UnofficialFetchError,
    fetch_bookmarks_unofficial,
)

_HISTORY_FILENAME = ".x-bookmarks-history.jsonl"
_DEFAULT_BACKFILL_MAX = 5000


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
    parser.add_argument(
        "--backfill-unofficial",
        action="store_true",
        help=(
            "Fetch bookmarks via twitter-cli instead of the official API. "
            f"Read-only, and requires {ENABLE_ENV}=1 plus explicit "
            f"{AUTH_TOKEN_ENV}/{CT0_ENV}. Uses X's private API with session "
            "cookies: violates the X Developer Agreement and can get your "
            "account flagged. Intended for a one-time historical backfill."
        ),
    )
    parser.add_argument(
        "--backfill-max",
        type=int,
        help=(
            "Maximum bookmarks to request during an unofficial backfill "
            f"(default {_DEFAULT_BACKFILL_MAX}). Requires --backfill-unofficial."
        ),
    )
    parser.add_argument(
        "--enrich-titles",
        action="store_true",
        help=(
            "Backfill missing external-link titles via Jina Reader "
            "(keyless, no credentials). Discloses bookmarked URLs to a "
            "third-party service."
        ),
    )
    args = parser.parse_args(argv)
    if (args.dry_run or args.confirm or args.max_removals is not None) and not args.remove_synthesized_bookmarks:
        parser.error("--dry-run, --confirm, and --max require --remove-synthesized-bookmarks")
    if args.max_removals is not None and args.max_removals < 1:
        parser.error("--max must be greater than zero")
    # Deletion stays on the official API permanently: the documented DELETE has
    # idempotency and error semantics the private GraphQL surface does not.
    if args.backfill_unofficial and args.remove_synthesized_bookmarks:
        parser.error(
            "--backfill-unofficial cannot be combined with "
            "--remove-synthesized-bookmarks; removal always uses the official API"
        )
    if args.enrich_titles and args.remove_synthesized_bookmarks:
        parser.error(
            "--enrich-titles cannot be combined with "
            "--remove-synthesized-bookmarks; removal mode never fetches or categorizes"
        )
    if args.backfill_max is not None and not args.backfill_unofficial:
        parser.error("--backfill-max requires --backfill-unofficial")
    if args.backfill_max is not None and args.backfill_max < 1:
        parser.error("--backfill-max must be greater than zero")
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


def _count_pillars(categorized: tuple) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ct in categorized:
        key = ct.pillar
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


def _fetch_tweets(
    config,
    run_id: str,
    *,
    backfill_unofficial: bool,
    backfill_max: int | None,
):
    """Fetch bookmarks from the official API, or the opt-in unofficial path.

    The official path stays the default. The unofficial path is only reachable
    through an explicit CLI flag, and fails loudly rather than falling back, so
    a misconfigured backfill can never silently become a normal run.
    """
    if not backfill_unofficial:
        print(f"[{run_id}] Fetching bookmarks for user {config.user_id}...")
        return fetch_bookmarks(config)

    limit = backfill_max or _DEFAULT_BACKFILL_MAX
    print(
        f"[{run_id}] UNOFFICIAL BACKFILL via twitter-cli (max {limit}).\n"
        f"[{run_id}]   Uses X's private API with session cookies. This violates\n"
        f"[{run_id}]   the X Developer Agreement and can get your account flagged.\n"
        f"[{run_id}]   Read-only: no bookmarks will be deleted on this path."
    )
    try:
        return fetch_bookmarks_unofficial(max_count=limit, env=os.environ)
    except UnofficialDisabledError as exc:
        print(f"[{run_id}] Refusing to run: {exc}")
        sys.exit(1)
    except UnofficialFetchError as exc:
        print(f"[{run_id}] Unofficial fetch failed: {exc}")
        sys.exit(1)


def _run_sync(
    config,
    run_id: str,
    started_at: str,
    t_start: float,
    *,
    backfill_unofficial: bool = False,
    backfill_max: int | None = None,
    enrich_titles: bool = False,
) -> None:
    """Fetch bookmarks, categorize, and write to Obsidian vault."""
    print(f"[{run_id}] Output directory: {config.output_dir}")
    if not config.output_dir.exists():
        print(
            f"[{run_id}] WARNING: output directory does not exist yet.\n"
            f"[{run_id}]   Deduplication will treat the vault as EMPTY, so every fetched\n"
            f"[{run_id}]   bookmark will be categorized as new. This is expected on a first\n"
            f"[{run_id}]   run, but if you expected existing notes here, KNOWLEDGE_BASE_DIR\n"
            f"[{run_id}]   is likely misconfigured (check .env and .envrc.local)."
        )
    tweets = _fetch_tweets(
        config,
        run_id,
        backfill_unofficial=backfill_unofficial,
        backfill_max=backfill_max,
    )

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

    if enrich_titles:
        missing = sum(
            1 for t in novel for link in t.external_links if not link.title
        )
        if missing:
            print(
                f"[{run_id}] Enriching {missing} external link title(s) "
                "via Jina Reader..."
            )
            novel = backfill_titles(novel)
            filled = sum(
                1 for t in novel for link in t.external_links if link.title
            )
            print(f"[{run_id}] {filled} link title(s) now populated.")

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
        override_file=config.taxonomy_file,
    )

    print(f"[{run_id}] Writing to {config.output_dir}...")
    stats = write_bookmarks(categorized, config.output_dir)

    filenames = stats["filenames"]
    for fname in filenames:
        print(f"  + {fname}")


    pillar_counts = _count_pillars(categorized)

    duration_ms = int((time.monotonic() - t_start) * 1000)

    print(f"\n--- Run Summary [{run_id}] ---")
    print(f"Bookmarks fetched:  {len(tweets)}")
    print(f"Already saved:      {skipped}")
    print(f"New bookmarks:      {len(novel)}")
    print(f"Files written:      {stats['files_written']}")
    print(f"Duplicates at write:{stats['duplicates_skipped']}")
    print(f"Tokens used:        {usage['input_tokens']} in / {usage['output_tokens']} out")
    print(f"Duration:           {duration_ms}ms")

    if pillar_counts:
        print("\nPillars:")
        for pillar, count in pillar_counts.items():
            print(f"  {pillar}: {count}")

    record = _build_run_record(
        run_id=run_id, status="success", started_at=started_at,
        duration_ms=duration_ms, output_dir=str(config.output_dir),
        fetched=len(tweets), skipped=skipped, novel=len(novel),
        articles=article_count, files_written=stats["files_written"],
        duplicates_skipped=stats["duplicates_skipped"],
        filenames=filenames, token_usage=usage,
        categories=pillar_counts,
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

    _run_sync(
        config,
        run_id,
        started_at,
        t_start,
        backfill_unofficial=args.backfill_unofficial,
        backfill_max=args.backfill_max,
        enrich_titles=args.enrich_titles,
    )


if __name__ == "__main__":
    main()
