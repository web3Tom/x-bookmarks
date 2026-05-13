# PRD: X Bookmark Removal From Synthesized Notes

## Summary

Add a destructive, opt-in removal mode that removes X bookmarks only for active notes explicitly marked with strict `synthesized: true`. The mode is independent from normal sync: it does not fetch bookmarks, call Claude, or write new notes. After X confirms deletion, or reports the bookmark is already absent, the CLI annotates the note and archives it under `output_dir / "archive"`.

## Commands

```bash
uv run x-bookmarks --remove-synthesized-bookmarks --dry-run
uv run x-bookmarks --remove-synthesized-bookmarks --confirm
```

Live deletion requires `--confirm` or an interactive `Proceed? [y/N]` confirmation. `--max N` limits a live run and is capped at 50 deletions.

## Auth Requirements

OAuth scopes now include `bookmark.write` in addition to `bookmark.read`. Users must re-run:

```bash
uv run x-bookmarks-auth
```

Existing refresh tokens cannot upgrade scope in place. A `403` from deletion is reported as:

```text
403 likely means missing bookmark.write scope. Re-run 'uv run x-bookmarks-auth' to re-authorize.
```

## Eligibility

Removal scans only active `output_dir/*.md` notes. It skips `output_dir/archive/`.

`synthesized` parsing is strict:

- `synthesized: true` is eligible.
- `synthesized: false` is skipped.
- missing `synthesized` is skipped before backfill and should disappear after migration.
- null, empty, quoted strings, uppercase booleans, case-mismatched fields, and malformed YAML are skipped with warnings.

Backfill adds `synthesized: false` to active notes that do not already have a `synthesized` field, preserving existing `synthesized: true` values.

## Deletion And Archival

For each eligible note:

1. Parse and validate frontmatter.
2. Call `DELETE /2/users/{id}/bookmarks/{tweet_id}`.
3. Treat `200`/`204` as success.
4. Treat `404` as success with warning because the bookmark is already absent.
5. Only after remote success, add:

```yaml
bookmark_removed: true
bookmark_removed_at: 2026-05-13T18:22:10Z
```

6. Move the note to `output_dir / "archive"`.

Archive filename collisions append `-{tweet_id}` before `.md`. Archived notes do not block future normal sync deduplication, so re-bookmarking the same tweet can create a fresh active note.

## Rate Limits

The prototype processes at most 50 live deletions per run, matching the documented per-user DELETE bookmark limit. On `429`, it parses `x-rate-limit-reset`, prints the reset time, logs the failed run, and exits non-zero instead of sleeping through the window.

## History Logging

`.x-bookmarks-history.jsonl` removal records include:

- `mode: "remove_synthesized_bookmarks"`
- eligible, attempted, removed, archived, skipped, and failed counts
- removed tweet IDs
- failed tweet IDs and reasons
- dry-run and confirmed flags
- output and archive paths

## Sources

- X Delete Bookmark endpoint: `https://docs.x.com/x-api/users/delete-bookmark`
- X Manage Bookmarks guide: `https://docs.x.com/x-api/posts/bookmarks/quickstart/manage-bookmarks`
- X Rate Limits: `https://docs.x.com/x-api/fundamentals/rate-limits`
