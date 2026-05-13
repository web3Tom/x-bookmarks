from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml

from src.api_client import (
    BookmarkDeleteRateLimitError,
    BookmarkWriteScopeError,
    DeleteBookmarkResult,
)

_SYNTHESIZED_PATTERN = re.compile(r"^synthesized:\s*(.*)$", re.MULTILINE)
_SYNTHESIZED_CASE_PATTERN = re.compile(r"^([A-Za-z_]+):\s*.*$", re.MULTILINE)
_TWEET_URL_ID_PATTERN = re.compile(
    r'^tweet_url:\s*"https://x\.com/\S+/status/(\d+)"', re.MULTILINE
)
_MAX_LIVE_REMOVALS = 50


@dataclass(frozen=True)
class RemovalCandidate:
    filepath: Path
    tweet_id: str


@dataclass(frozen=True)
class ScanResult:
    eligible: tuple[RemovalCandidate, ...]
    skipped: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class BackfillResult:
    scanned: int
    updated: int
    missing_after: int
    true_values: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class RemovalStats:
    eligible: int
    attempted: int
    removed: int
    archived: int
    skipped: int
    failed: int
    removed_tweet_ids: tuple[str, ...]
    failed_tweet_ids: tuple[dict[str, str], ...]
    warnings: tuple[str, ...]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _split_frontmatter(content: str) -> tuple[str, str]:
    if not content.startswith("---\n"):
        raise ValueError("missing opening frontmatter delimiter")
    end_idx = content.find("\n---", 4)
    if end_idx == -1:
        raise ValueError("missing closing frontmatter delimiter")
    yaml_block = content[4:end_idx]
    body = content[end_idx + 4 :]
    return yaml_block, body


def _validate_yaml_block(yaml_block: str) -> dict:
    parsed = yaml.safe_load(yaml_block)
    if not isinstance(parsed, dict):
        raise ValueError("frontmatter is not a mapping")
    return parsed


def _active_note_paths(output_dir: Path) -> list[Path]:
    if not output_dir.exists():
        return []
    return sorted(output_dir.glob("*.md"))


def _has_synthesized_field(yaml_block: str) -> bool:
    return bool(_SYNTHESIZED_PATTERN.search(yaml_block))


def _insert_line_before_closing_frontmatter(content: str, line: str) -> str:
    yaml_block, body = _split_frontmatter(content)
    lines = yaml_block.splitlines()
    insert_at = None
    for idx, current in enumerate(lines):
        if current.startswith("read:"):
            insert_at = idx + 1
            break
    if insert_at is None:
        insert_at = len(lines)
    lines.insert(insert_at, line)
    updated_yaml = "\n".join(lines) + "\n"
    _validate_yaml_block(updated_yaml)
    return "---\n" + updated_yaml + "---" + body


def _atomic_write(path: Path, content: str) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(content)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def backfill_synthesized_false(output_dir: Path) -> BackfillResult:
    warnings: list[str] = []
    updated = 0

    for path in _active_note_paths(output_dir):
        try:
            content = path.read_text(encoding="utf-8")
            yaml_block, _ = _split_frontmatter(content)
            _validate_yaml_block(yaml_block)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            warnings.append(f"{path.name}: skipped backfill ({exc})")
            continue

        if not _TWEET_URL_ID_PATTERN.findall(yaml_block):
            continue
        if _has_synthesized_field(yaml_block):
            continue

        _atomic_write(path, _insert_line_before_closing_frontmatter(content, "synthesized: false"))
        updated += 1

    validation = validate_synthesized_backfill(output_dir)
    return BackfillResult(
        scanned=len(_active_note_paths(output_dir)),
        updated=updated,
        missing_after=validation["missing"],
        true_values=validation["true"],
        warnings=tuple(warnings),
    )


def validate_synthesized_backfill(output_dir: Path) -> dict[str, int]:
    missing = 0
    true_values = 0
    for path in _active_note_paths(output_dir):
        try:
            yaml_block, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not _TWEET_URL_ID_PATTERN.findall(yaml_block):
            continue
        match = _SYNTHESIZED_PATTERN.search(yaml_block)
        if not match:
            missing += 1
        elif match.group(1).strip() == "true":
            true_values += 1
    return {"missing": missing, "true": true_values}


def _strict_synthesized_value(yaml_block: str, path: Path) -> tuple[bool | None, str | None]:
    match = _SYNTHESIZED_PATTERN.search(yaml_block)
    if not match:
        for key_match in _SYNTHESIZED_CASE_PATTERN.finditer(yaml_block):
            key = key_match.group(1)
            if key.lower() == "synthesized" and key != "synthesized":
                return None, f"{path.name}: ignored case-mismatched synthesized field"
        return False, None

    raw_value = match.group(1).strip()
    if raw_value == "true":
        return True, None
    if raw_value == "false":
        return False, None
    return None, f"{path.name}: ignored non-strict synthesized value {raw_value!r}"


def scan_synthesized_bookmark_notes(output_dir: Path) -> ScanResult:
    eligible: list[RemovalCandidate] = []
    warnings: list[str] = []
    skipped = 0

    for path in _active_note_paths(output_dir):
        try:
            yaml_block, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
            _validate_yaml_block(yaml_block)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            warnings.append(f"{path.name}: skipped malformed frontmatter ({exc})")
            skipped += 1
            continue

        value, warning = _strict_synthesized_value(yaml_block, path)
        if warning:
            warnings.append(warning)
        if value is not True:
            skipped += 1
            continue

        tweet_ids = _TWEET_URL_ID_PATTERN.findall(yaml_block)
        if not tweet_ids:
            warnings.append(f"{path.name}: synthesized note missing strict tweet_url")
            skipped += 1
            continue
        eligible.append(RemovalCandidate(filepath=path, tweet_id=tweet_ids[0]))

    return ScanResult(eligible=tuple(eligible), skipped=skipped, warnings=tuple(warnings))


def _archive_destination(path: Path, archive_dir: Path, tweet_id: str) -> Path:
    candidate = archive_dir / path.name
    if not candidate.exists():
        return candidate
    return archive_dir / f"{path.stem}-{tweet_id}{path.suffix}"


def _upsert_frontmatter_fields(content: str, fields: dict[str, str]) -> str:
    yaml_block, body = _split_frontmatter(content)
    lines = yaml_block.splitlines()
    seen: set[str] = set()

    for idx, line in enumerate(lines):
        key = line.split(":", 1)[0] if ":" in line else ""
        if key in fields:
            lines[idx] = f"{key}: {fields[key]}"
            seen.add(key)

    for key, value in fields.items():
        if key not in seen:
            lines.append(f"{key}: {value}")

    updated_yaml = "\n".join(lines) + "\n"
    _validate_yaml_block(updated_yaml)
    return "---\n" + updated_yaml + "---" + body


def _archive_ids(archive_dir: Path) -> set[str]:
    ids: set[str] = set()
    if not archive_dir.exists():
        return ids
    for path in archive_dir.glob("*.md"):
        try:
            yaml_block, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ids.update(_TWEET_URL_ID_PATTERN.findall(yaml_block))
    return ids


def remove_candidates(
    candidates: tuple[RemovalCandidate, ...],
    *,
    output_dir: Path,
    dry_run: bool,
    max_removals: int | None,
    delete_bookmark: Callable[[str], DeleteBookmarkResult],
) -> RemovalStats:
    archive_dir = output_dir / "archive"
    limit = min(max_removals or _MAX_LIVE_REMOVALS, _MAX_LIVE_REMOVALS)
    selected = candidates[:limit] if max_removals is not None or not dry_run else candidates
    warnings: list[str] = []
    failed: list[dict[str, str]] = []
    removed_ids: list[str] = []
    archived = 0
    archive_ids = _archive_ids(archive_dir)

    for candidate in selected:
        if candidate.tweet_id in archive_ids:
            warnings.append(f"{candidate.filepath.name}: tweet {candidate.tweet_id} already exists in archive")

        if dry_run:
            continue

        try:
            result = delete_bookmark(candidate.tweet_id)
        except BookmarkDeleteRateLimitError as exc:
            reason = str(exc)
            failed.append({"tweet_id": candidate.tweet_id, "reason": reason})
            warnings.append(reason)
            break
        except BookmarkWriteScopeError:
            raise
        except Exception as exc:
            failed.append({"tweet_id": candidate.tweet_id, "reason": str(exc)})
            continue

        if result.already_absent:
            warnings.append(f"{candidate.filepath.name}: bookmark already absent on X")

        try:
            content = candidate.filepath.read_text(encoding="utf-8")
            updated = _upsert_frontmatter_fields(
                content,
                {
                    "bookmark_removed": "true",
                    "bookmark_removed_at": utc_timestamp(),
                },
            )
            _atomic_write(candidate.filepath, updated)
            archive_dir.mkdir(parents=True, exist_ok=True)
            candidate.filepath.replace(_archive_destination(candidate.filepath, archive_dir, candidate.tweet_id))
        except Exception as exc:
            failed.append({"tweet_id": candidate.tweet_id, "reason": f"local archive failed: {exc}"})
            continue

        removed_ids.append(candidate.tweet_id)
        archived += 1

    return RemovalStats(
        eligible=len(candidates),
        attempted=0 if dry_run else len(selected),
        removed=len(removed_ids),
        archived=archived,
        skipped=max(0, len(candidates) - len(selected)),
        failed=len(failed),
        removed_tweet_ids=tuple(removed_ids),
        failed_tweet_ids=tuple(failed),
        warnings=tuple(warnings),
    )


def max_live_removals() -> int:
    return _MAX_LIVE_REMOVALS
