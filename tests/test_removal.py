import json

import pytest

from src.api_client import DeleteBookmarkResult
from src.markdown_writer import read_existing_ids
from src.removal import (
    backfill_synthesized_false,
    remove_candidates,
    scan_synthesized_bookmark_notes,
    validate_synthesized_backfill,
)


def _note(tweet_id: str = "100", synthesized: str | None = "false", extra: str = "") -> str:
    lines = [
        "---",
        'title: "Test"',
        'author: "@alice"',
        'category: "AI Coding"',
        'subCategory: "Coding Workflows"',
        "date: 2026-05-13",
        "read: false",
    ]
    if synthesized is not None:
        lines.append(f"synthesized: {synthesized}")
    lines.extend([
        'type: "post"',
        f'tweet_url: "https://x.com/alice/status/{tweet_id}"',
    ])
    if extra:
        lines.append(extra)
    lines.extend(["---", "## Test", ""])
    return "\n".join(lines)


class TestSynthesizedScan:
    def test_strict_true_is_eligible(self, tmp_path):
        (tmp_path / "yes.md").write_text(_note("1", "true"))

        result = scan_synthesized_bookmark_notes(tmp_path)

        assert len(result.eligible) == 1
        assert result.eligible[0].tweet_id == "1"

    @pytest.mark.parametrize("value", ["false", None])
    def test_false_and_missing_are_skipped(self, tmp_path, value):
        (tmp_path / "note.md").write_text(_note("1", value))

        result = scan_synthesized_bookmark_notes(tmp_path)

        assert result.eligible == ()
        assert result.skipped == 1
        assert result.warnings == ()

    @pytest.mark.parametrize("value", ["True", '"true"', "", "null"])
    def test_non_strict_values_warn_and_skip(self, tmp_path, value):
        (tmp_path / "note.md").write_text(_note("1", value))

        result = scan_synthesized_bookmark_notes(tmp_path)

        assert result.eligible == ()
        assert result.skipped == 1
        assert result.warnings

    def test_malformed_yaml_warns_and_skips(self, tmp_path):
        (tmp_path / "bad.md").write_text('---\ntitle: "bad: "yaml"\nsynthesized: true\n---\n')

        result = scan_synthesized_bookmark_notes(tmp_path)

        assert result.eligible == ()
        assert result.skipped == 1
        assert "malformed" in result.warnings[0]


class TestBackfill:
    def test_missing_field_becomes_false_after_read(self, tmp_path):
        path = tmp_path / "note.md"
        path.write_text(_note("1", None))

        result = backfill_synthesized_false(tmp_path)
        content = path.read_text()

        assert result.updated == 1
        assert "read: false\nsynthesized: false\n" in content
        assert validate_synthesized_backfill(tmp_path) == {"missing": 0, "true": 0}

    def test_existing_true_is_preserved(self, tmp_path):
        path = tmp_path / "note.md"
        path.write_text(_note("1", "true"))

        result = backfill_synthesized_false(tmp_path)

        assert result.updated == 0
        assert "synthesized: true" in path.read_text()
        assert validate_synthesized_backfill(tmp_path) == {"missing": 0, "true": 1}

    def test_archive_is_not_backfilled(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "old.md").write_text(_note("1", None))

        result = backfill_synthesized_false(tmp_path)

        assert result.scanned == 0
        assert "synthesized:" not in (archive / "old.md").read_text()


class TestArchiveRemoval:
    def test_successful_delete_annotates_and_archives(self, tmp_path):
        path = tmp_path / "note.md"
        path.write_text(_note("1", "true"))
        candidates = scan_synthesized_bookmark_notes(tmp_path).eligible

        result = remove_candidates(
            candidates,
            output_dir=tmp_path,
            dry_run=False,
            max_removals=None,
            delete_bookmark=lambda tweet_id: DeleteBookmarkResult(tweet_id=tweet_id),
        )

        archived = tmp_path / "archive" / "note.md"
        assert not path.exists()
        assert archived.exists()
        content = archived.read_text()
        assert "bookmark_removed: true" in content
        assert "bookmark_removed_at:" in content
        assert result.removed == 1
        assert result.archived == 1

    def test_404_style_result_is_idempotent_success(self, tmp_path):
        path = tmp_path / "note.md"
        path.write_text(_note("1", "true"))
        candidates = scan_synthesized_bookmark_notes(tmp_path).eligible

        result = remove_candidates(
            candidates,
            output_dir=tmp_path,
            dry_run=False,
            max_removals=None,
            delete_bookmark=lambda tweet_id: DeleteBookmarkResult(tweet_id=tweet_id, already_absent=True),
        )

        assert (tmp_path / "archive" / "note.md").exists()
        assert result.removed == 1
        assert result.warnings

    def test_archive_collision_appends_tweet_id(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "note.md").write_text(_note("999", "true"))
        (tmp_path / "note.md").write_text(_note("1", "true"))
        candidates = scan_synthesized_bookmark_notes(tmp_path).eligible

        remove_candidates(
            candidates,
            output_dir=tmp_path,
            dry_run=False,
            max_removals=None,
            delete_bookmark=lambda tweet_id: DeleteBookmarkResult(tweet_id=tweet_id),
        )

        assert (archive / "note-1.md").exists()

    def test_archive_notes_do_not_block_normal_dedup(self, tmp_path):
        archive = tmp_path / "archive"
        archive.mkdir()
        (archive / "old.md").write_text(_note("1", "true"))

        assert read_existing_ids(tmp_path) == set()


class TestRemovalHistoryShape:
    def test_removal_record_can_be_jsonl_serialized(self, tmp_path):
        from src.main import _append_history, _build_removal_record, _HISTORY_FILENAME

        record = _build_removal_record(
            run_id="abc",
            status="success",
            started_at="2026-05-13T00:00:00Z",
            duration_ms=1,
            output_dir=tmp_path,
            archive_dir=tmp_path / "archive",
            dry_run=False,
            confirmed=True,
            eligible=1,
            attempted=1,
            removed=1,
            archived=1,
            removed_tweet_ids=("1",),
        )

        _append_history(tmp_path, record)
        parsed = json.loads((tmp_path / _HISTORY_FILENAME).read_text())

        assert parsed["mode"] == "remove_synthesized_bookmarks"
        assert parsed["removal"]["removed_tweet_ids"] == ["1"]
