import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.migrate import (
    MigrationResult,
    ParsedBookmark,
    _build_migrated_frontmatter,
    _build_migration_payload,
    _build_rename_filename,
    _parse_migration_response,
    _replace_body_heading,
    _split_frontmatter_body,
    _parse_frontmatter,
    generate_titles_batch,
    migrate_directory,
    migrate_single_file,
    parse_existing_bookmark,
)
from src.markdown_writer import _slugify_title


# --- Fixtures ---

SAMPLE_OLD_FRONTMATTER = """\
title: "How to master prompt engineering"
author: "@EXM7777"
author_name: "Machina"
category: "AI Coding"
subCategory: "Prompt & Context Engineering"
date: 2026-01-15
read: false
type: "article"
tweet_id: "2011800604709175808"
tweet_url: "https://x.com/EXM7777/status/2011800604709175808"
article_url: "http://x.com/i/article/2011690517210546176"
likes: 2435
retweets: 279
replies: 57
bookmarks: 6832
has_media: false
has_links: false"""

SAMPLE_OLD_FILE = f"---\n{SAMPLE_OLD_FRONTMATTER}\n---\n\n## Notes\n\nSome body text here.\n"

SAMPLE_UNQUOTED_FRONTMATTER = """\
title: How to use AI Coding
author: "@alice"
author_name: Alice
category: AI Coding
subCategory: Coding Workflows
date: 2026-01-10
read: false
type: post
tweet_id: "12345"
tweet_url: "https://x.com/alice/status/12345"
likes: 100
retweets: 10
replies: 5
bookmarks: 50
has_media: false
has_links: false"""


@pytest.fixture
def old_bookmark_file(tmp_path: Path) -> Path:
    """Create a sample old-format bookmark file."""
    filepath = tmp_path / "2026-01-15-EXM7777.md"
    filepath.write_text(SAMPLE_OLD_FILE)
    return filepath


@pytest.fixture
def old_bookmark_dir(tmp_path: Path) -> Path:
    """Create a directory with multiple old-format bookmark files."""
    d = tmp_path / "bookmarks"
    d.mkdir()

    (d / "2026-01-15-alice.md").write_text(
        '---\ntitle: "Some dumb title"\nauthor: "@alice"\n'
        'author_name: "Alice"\ncategory: "AI Coding"\n'
        'subCategory: "Coding Workflows"\ndate: 2026-01-15\n'
        'read: false\ntype: "post"\ntweet_id: "111"\n'
        'tweet_url: "https://x.com/alice/status/111"\n'
        'likes: 10\nretweets: 1\nreplies: 0\nbookmarks: 5\n'
        'has_media: false\nhas_links: false\n---\n\n'
        '## Notes\n\nFirst post body.\n'
    )
    (d / "2026-01-16-bob.md").write_text(
        '---\ntitle: "Another dumb title"\nauthor: "@bob"\n'
        'author_name: "Bob"\ncategory: "Agent Architectures"\n'
        'subCategory: "Applied Agents"\ndate: 2026-01-16\n'
        'read: true\ntype: "post"\ntweet_id: "222"\n'
        'tweet_url: "https://x.com/bob/status/222"\n'
        'likes: 20\nretweets: 2\nreplies: 1\nbookmarks: 8\n'
        'has_media: true\nhas_links: false\n---\n\n'
        '## Notes\n\nSecond post body.\n'
    )
    (d / "index.md").write_text("---\ntitle: X Bookmarks\n---\n\nDataview query\n")

    return d


# --- TestSplitFrontmatterBody ---

class TestSplitFrontmatterBody:
    def test_valid_split(self):
        content = '---\ntitle: "Hello"\nauthor: "@alice"\n---\n\nBody text here.\n'
        yaml_block, body = _split_frontmatter_body(content)
        assert 'title: "Hello"' in yaml_block
        assert "Body text here." in body

    def test_missing_frontmatter_raises(self):
        content = "No frontmatter here, just text."
        with pytest.raises(ValueError, match="No frontmatter found"):
            _split_frontmatter_body(content)

    def test_missing_closing_delimiter_raises(self):
        content = "---\ntitle: hello\nno closing delimiter"
        with pytest.raises(ValueError, match="No closing ---"):
            _split_frontmatter_body(content)

    def test_empty_body(self):
        content = '---\ntitle: "Hello"\n---\n'
        yaml_block, body = _split_frontmatter_body(content)
        assert 'title: "Hello"' in yaml_block
        assert body == ""


# --- TestParseFrontmatter ---

class TestParseFrontmatter:
    def test_valid_yaml(self):
        block = 'title: "Hello"\nauthor: "@alice"\ndate: 2026-01-15'
        result = _parse_frontmatter(block)
        assert result is not None
        assert result["title"] == "Hello"
        assert result["author"] == "@alice"

    def test_broken_yaml_returns_none(self):
        block = "title: [invalid: yaml: {{"
        result = _parse_frontmatter(block)
        assert result is None

    def test_non_dict_returns_none(self):
        block = "- item1\n- item2"
        result = _parse_frontmatter(block)
        assert result is None


# --- TestParseExistingBookmark ---

class TestParseExistingBookmark:
    def test_full_parse(self, old_bookmark_file: Path):
        result = parse_existing_bookmark(old_bookmark_file)
        assert result is not None
        assert result.filepath == old_bookmark_file
        assert result.frontmatter["title"] == "How to master prompt engineering"
        assert result.frontmatter["author_name"] == "Machina"
        assert "Some body text here." in result.body

    def test_bad_file_handled_gracefully(self, tmp_path: Path):
        bad_file = tmp_path / "bad.md"
        bad_file.write_text("No frontmatter here")
        result = parse_existing_bookmark(bad_file)
        assert result is None

    def test_nonexistent_file_handled_gracefully(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.md"
        result = parse_existing_bookmark(missing)
        assert result is None


# --- TestBuildMigrationPayload ---

class TestBuildMigrationPayload:
    def test_json_structure(self, old_bookmark_file: Path):
        bm = parse_existing_bookmark(old_bookmark_file)
        payload = _build_migration_payload([bm])
        data = json.loads(payload)
        assert len(data) == 1
        assert data[0]["filename"] == old_bookmark_file.name
        assert data[0]["title"] == "How to master prompt engineering"
        assert data[0]["category"] == "AI Coding"
        assert data[0]["type"] == "article"

    def test_body_truncation_for_posts(self, tmp_path: Path):
        long_body = "x" * 5000
        filepath = tmp_path / "long.md"
        filepath.write_text(
            f'---\ntitle: "Long Post"\nauthor: "@alice"\n'
            f'type: "post"\ndate: 2026-01-01\n---\n\n{long_body}\n'
        )
        bm = parse_existing_bookmark(filepath)
        payload = _build_migration_payload([bm])
        data = json.loads(payload)
        assert len(data[0]["body"]) <= 2001  # 2000 chars + possible newline

    def test_articles_also_truncated(self, tmp_path: Path):
        long_body = "x" * 5000
        filepath = tmp_path / "article.md"
        filepath.write_text(
            f'---\ntitle: "Long Article"\nauthor: "@alice"\n'
            f'type: "article"\ndate: 2026-01-01\n---\n\n{long_body}\n'
        )
        bm = parse_existing_bookmark(filepath)
        payload = _build_migration_payload([bm])
        data = json.loads(payload)
        assert len(data[0]["body"]) == 2000


# --- TestBuildMigratedFrontmatter ---

class TestBuildMigratedFrontmatter:
    def test_only_allowed_fields(self):
        parsed = {
            "title": "Old Title",
            "author": "@alice",
            "author_name": "Alice",
            "category": "AI Coding",
            "subCategory": "Coding Workflows",
            "date": "2026-01-15",
            "read": False,
            "type": "post",
            "tweet_id": "12345",
            "tweet_url": "https://x.com/alice/status/12345",
            "likes": 100,
            "retweets": 10,
            "replies": 5,
            "bookmarks": 50,
            "has_media": False,
            "has_links": False,
        }
        result = _build_migrated_frontmatter(parsed, "New Title", "AI Coding", "Coding Workflows")
        assert "author_name" not in result
        assert "tweet_id:" not in result
        assert "likes:" not in result
        assert "retweets:" not in result
        assert "replies:" not in result
        assert "bookmarks:" not in result
        assert "has_media:" not in result
        assert "has_links:" not in result

    def test_deprecated_fields_removed(self):
        parsed = {
            "title": "Old",
            "author": "@alice",
            "author_name": "Alice",
            "tweet_id": "123",
            "likes": 10,
            "retweets": 5,
            "replies": 1,
            "bookmarks": 20,
            "has_media": True,
            "has_links": True,
            "date": "2026-01-10",
            "type": "post",
            "tweet_url": "https://x.com/alice/status/123",
        }
        result = _build_migrated_frontmatter(parsed, "New Title", "AI Coding", "Coding Workflows")
        for field in ["author_name", "tweet_id", "likes", "retweets", "replies", "bookmarks", "has_media", "has_links"]:
            assert f"{field}:" not in result

    def test_read_true_preserved(self):
        parsed = {
            "author": "@bob",
            "date": "2026-01-16",
            "read": True,
            "type": "post",
            "tweet_url": "https://x.com/bob/status/222",
        }
        result = _build_migrated_frontmatter(parsed, "Title", "General", "Uncategorized")
        assert "read: true" in result

    def test_all_strings_quoted(self):
        parsed = {
            "author": "@alice",
            "date": "2026-01-15",
            "read": False,
            "type": "post",
            "tweet_url": "https://x.com/alice/status/123",
        }
        result = _build_migrated_frontmatter(parsed, "Test Title", "AI Coding", "Prompt & Context Engineering")
        assert 'title: "Test Title"' in result
        assert 'author: "@alice"' in result
        assert 'category: "AI Coding"' in result
        assert 'subCategory: "Prompt & Context Engineering"' in result
        assert 'type: "post"' in result

    def test_yaml_validates(self):
        parsed = {
            "author": "@alice",
            "date": "2026-01-15",
            "read": False,
            "type": "post",
            "tweet_url": "https://x.com/alice/status/123",
        }
        result = _build_migrated_frontmatter(
            parsed, "Inference & Serving Guide", "Model Systems", "Inference & Serving",
        )
        lines = result.strip().split("\n")
        yaml_body = "\n".join(lines[1:-1])
        data = yaml.safe_load(yaml_body)
        assert data["title"] == "Inference & Serving Guide"
        assert data["subCategory"] == "Inference & Serving"
        assert data["category"] == "Model Systems"

    def test_article_url_included(self):
        parsed = {
            "author": "@alice",
            "date": "2026-01-15",
            "read": False,
            "type": "article",
            "tweet_url": "https://x.com/alice/status/123",
            "article_url": "http://x.com/i/article/456",
        }
        result = _build_migrated_frontmatter(parsed, "Article Title", "AI Coding", "Coding Workflows")
        assert 'article_url: "http://x.com/i/article/456"' in result

    def test_author_without_at_prefix(self):
        parsed = {
            "author": "alice",
            "date": "2026-01-15",
            "type": "post",
            "tweet_url": "https://x.com/alice/status/123",
        }
        result = _build_migrated_frontmatter(parsed, "Title", "General", "Uncategorized")
        assert 'author: "@alice"' in result


# --- TestReplaceBodyHeading ---

class TestReplaceBodyHeading:
    def test_notes_heading_replaced(self):
        body = "\n## Notes\n\nSome content.\n"
        result = _replace_body_heading(body, "New Title")
        assert "## New Title" in result
        assert "## Notes" not in result

    def test_other_h2_replaced(self):
        body = "\n## Old Heading\n\nSome content.\n"
        result = _replace_body_heading(body, "New Title")
        assert "## New Title" in result
        assert "## Old Heading" not in result

    def test_no_h2_body_unchanged(self):
        body = "\nSome content with no heading.\n"
        result = _replace_body_heading(body, "New Title")
        assert result == body

    def test_only_first_h2_replaced(self):
        body = "\n## First Heading\n\nContent.\n\n## References\n\nLinks.\n"
        result = _replace_body_heading(body, "New Title")
        assert "## New Title" in result
        assert "## References" in result
        assert "## First Heading" not in result


# --- TestMigrateSingleFile ---

class TestMigrateSingleFile:
    def test_file_rewritten_and_renamed(self, old_bookmark_file: Path):
        bm = parse_existing_bookmark(old_bookmark_file)
        title_data = {
            "title": "Mastering Prompt Engineering Fundamentals",
            "category": "AI Coding",
            "sub_category": "Prompt & Context Engineering",
        }
        result = migrate_single_file(bm, title_data)

        assert not result.skipped
        assert result.old_title == "How to master prompt engineering"
        assert result.new_title == "Mastering Prompt Engineering Fundamentals"
        assert result.old_filename == "2026-01-15-EXM7777.md"
        assert result.new_filename == "mastering-prompt-engineering-fundamentals.md"
        assert "author_name" in result.fields_removed
        assert "tweet_id" in result.fields_removed
        assert "likes" in result.fields_removed
        assert result.heading_changed

        # Old file should be gone, new file should exist
        assert not old_bookmark_file.exists()
        new_path = old_bookmark_file.parent / "mastering-prompt-engineering-fundamentals.md"
        assert new_path.exists()

        content = new_path.read_text()
        assert 'title: "Mastering Prompt Engineering Fundamentals"' in content
        assert "author_name" not in content
        assert "tweet_id:" not in content
        assert "likes:" not in content
        assert "## Mastering Prompt Engineering Fundamentals" in content
        assert "## Notes" not in content

        # Verify YAML is valid
        parts = content.split("---")
        data = yaml.safe_load(parts[1])
        assert data["title"] == "Mastering Prompt Engineering Fundamentals"

    def test_result_fields_populated(self, old_bookmark_file: Path):
        bm = parse_existing_bookmark(old_bookmark_file)
        title_data = {"title": "New Title", "category": "AI Coding", "sub_category": "Coding Workflows"}
        result = migrate_single_file(bm, title_data)

        assert isinstance(result, MigrationResult)
        assert result.new_filename == "new-title.md"
        assert isinstance(result.fields_removed, tuple)
        assert isinstance(result.heading_changed, bool)
        assert not result.skipped

    def test_fallback_title_on_empty(self, old_bookmark_file: Path):
        bm = parse_existing_bookmark(old_bookmark_file)
        title_data = {"title": "", "category": "AI Coding", "sub_category": "Coding Workflows"}
        result = migrate_single_file(bm, title_data)
        assert result.new_title != ""

    def test_collision_suffix(self, tmp_path: Path):
        """Two files with same title get -2 suffix."""
        for name in ("a.md", "b.md"):
            (tmp_path / name).write_text(
                '---\ntitle: "Same Title"\nauthor: "@user"\n'
                'date: 2026-01-01\ntype: "post"\n'
                'tweet_url: "https://x.com/user/status/1"\n---\n\n## Notes\n\nBody.\n'
            )
        bm_a = parse_existing_bookmark(tmp_path / "a.md")
        bm_b = parse_existing_bookmark(tmp_path / "b.md")
        existing: set[str] = {"index.md"}

        r1 = migrate_single_file(bm_a, {"title": "Same Title", "category": "AI", "sub_category": "X"}, existing)
        existing.add(r1.new_filename)

        r2 = migrate_single_file(bm_b, {"title": "Same Title", "category": "AI", "sub_category": "X"}, existing)

        assert r1.new_filename == "same-title.md"
        assert r2.new_filename == "same-title-2.md"


# --- TestMigrateDirectory ---

class TestMigrateDirectory:
    @patch("src.migrate.generate_titles_batch")
    def test_skips_index_md(self, mock_gen: MagicMock, old_bookmark_dir: Path):
        mock_gen.return_value = {
            "2026-01-15-alice.md": {"title": "Alice Title", "category": "AI Coding", "sub_category": "Coding Workflows"},
            "2026-01-16-bob.md": {"title": "Bob Title", "category": "Agent Architectures", "sub_category": "Applied Agents"},
        }
        results = migrate_directory(old_bookmark_dir, api_key="test-key")
        filenames = [r.old_filename for r in results]
        assert "index.md" not in filenames

    @patch("src.migrate.generate_titles_batch")
    def test_processes_all_md_files(self, mock_gen: MagicMock, old_bookmark_dir: Path):
        mock_gen.return_value = {
            "2026-01-15-alice.md": {"title": "Alice Title", "category": "AI Coding", "sub_category": "Coding Workflows"},
            "2026-01-16-bob.md": {"title": "Bob Title", "category": "Agent Architectures", "sub_category": "Applied Agents"},
        }
        results = migrate_directory(old_bookmark_dir, api_key="test-key")
        migrated = [r for r in results if not r.skipped]
        assert len(migrated) == 2

    @patch("src.migrate.generate_titles_batch")
    def test_files_renamed_to_title_slug(self, mock_gen: MagicMock, old_bookmark_dir: Path):
        mock_gen.return_value = {
            "2026-01-15-alice.md": {"title": "Alice Title", "category": "AI Coding", "sub_category": "Coding Workflows"},
            "2026-01-16-bob.md": {"title": "Bob Title", "category": "Agent Architectures", "sub_category": "Applied Agents"},
        }
        results = migrate_directory(old_bookmark_dir, api_key="test-key")

        new_filenames = {r.new_filename for r in results if not r.skipped}
        assert new_filenames == {"alice-title.md", "bob-title.md"}
        assert (old_bookmark_dir / "alice-title.md").exists()
        assert (old_bookmark_dir / "bob-title.md").exists()
        assert not (old_bookmark_dir / "2026-01-15-alice.md").exists()
        assert not (old_bookmark_dir / "2026-01-16-bob.md").exists()

    @patch("src.migrate.generate_titles_batch")
    def test_dry_run_doesnt_write(self, mock_gen: MagicMock, old_bookmark_dir: Path):
        original_alice = (old_bookmark_dir / "2026-01-15-alice.md").read_text()
        original_bob = (old_bookmark_dir / "2026-01-16-bob.md").read_text()

        mock_gen.return_value = {
            "2026-01-15-alice.md": {"title": "Alice Title", "category": "AI Coding", "sub_category": "Coding Workflows"},
            "2026-01-16-bob.md": {"title": "Bob Title", "category": "Agent Architectures", "sub_category": "Applied Agents"},
        }
        results = migrate_directory(old_bookmark_dir, api_key="test-key", dry_run=True)
        assert len(results) == 2
        assert results[0].new_filename == "alice-title.md"
        assert results[1].new_filename == "bob-title.md"

        # Files should be unchanged (not renamed or rewritten)
        assert (old_bookmark_dir / "2026-01-15-alice.md").read_text() == original_alice
        assert (old_bookmark_dir / "2026-01-16-bob.md").read_text() == original_bob

    @patch("src.migrate.generate_titles_batch")
    def test_read_true_preserved_after_migration(self, mock_gen: MagicMock, old_bookmark_dir: Path):
        mock_gen.return_value = {
            "2026-01-15-alice.md": {"title": "Alice Title", "category": "AI Coding", "sub_category": "Coding Workflows"},
            "2026-01-16-bob.md": {"title": "Bob Title", "category": "Agent Architectures", "sub_category": "Applied Agents"},
        }
        migrate_directory(old_bookmark_dir, api_key="test-key")

        content = (old_bookmark_dir / "bob-title.md").read_text()
        assert "read: true" in content

    def test_empty_directory(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        results = migrate_directory(empty_dir, api_key="test-key")
        assert results == []


# --- TestGenerateTitlesBatch ---

class TestGenerateTitlesBatch:
    @patch("src.migrate.anthropic.Anthropic")
    def test_mock_claude_response_parsed(self, mock_cls: MagicMock, old_bookmark_file: Path):
        bm = parse_existing_bookmark(old_bookmark_file)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {
                "filename": old_bookmark_file.name,
                "title": "Mastering Prompt Engineering",
                "category": "AI Coding",
                "sub_category": "Prompt & Context Engineering",
            }
        ]))]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_cls.return_value = mock_client

        result = generate_titles_batch([bm], api_key="test-key")
        assert old_bookmark_file.name in result
        assert result[old_bookmark_file.name]["title"] == "Mastering Prompt Engineering"
        assert result[old_bookmark_file.name]["category"] == "AI Coding"

    @patch("src.migrate.anthropic.Anthropic")
    def test_fallback_on_missing_filename(self, mock_cls: MagicMock, old_bookmark_file: Path):
        bm = parse_existing_bookmark(old_bookmark_file)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {
                "filename": "wrong-file.md",
                "title": "Wrong File Title",
                "category": "General",
                "sub_category": "Uncategorized",
            }
        ]))]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_cls.return_value = mock_client

        result = generate_titles_batch([bm], api_key="test-key")
        # The actual file name should not be in the results
        assert old_bookmark_file.name not in result

    @patch("src.migrate.anthropic.Anthropic")
    def test_batching(self, mock_cls: MagicMock, tmp_path: Path):
        """Verify multiple API calls happen for large batches."""
        files = []
        for i in range(5):
            fp = tmp_path / f"file-{i}.md"
            fp.write_text(
                f'---\ntitle: "Title {i}"\nauthor: "@user"\n'
                f'date: 2026-01-01\ntype: "post"\n'
                f'tweet_url: "https://x.com/user/status/{i}"\n---\n\n## Notes\n\nBody {i}\n'
            )
            files.append(fp)

        bookmarks = [parse_existing_bookmark(f) for f in files]

        mock_response = MagicMock()
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        def make_response(batch_files):
            entries = [
                {"filename": f.name, "title": f"New {f.stem}", "category": "General", "sub_category": "Uncategorized"}
                for f in batch_files
            ]
            resp = MagicMock()
            resp.content = [MagicMock(text=json.dumps(entries))]
            return resp

        # batch_size=2 should produce 3 calls for 5 files
        call_count = 0
        def side_effect(**kwargs):
            nonlocal call_count
            payload = json.loads(kwargs["messages"][0]["content"])
            batch_names = [e["filename"] for e in payload]
            batch_files = [f for f in files if f.name in batch_names]
            call_count += 1
            return make_response(batch_files)

        mock_client.messages.create.side_effect = side_effect

        result = generate_titles_batch(bookmarks, api_key="test-key", batch_size=2)
        assert call_count == 3
        assert len(result) == 5


# --- TestParseResponse ---

class TestParseResponse:
    def test_plain_json(self):
        text = json.dumps([
            {"filename": "a.md", "title": "Title A", "category": "AI Coding", "sub_category": "Coding Workflows"},
        ])
        result = _parse_migration_response(text)
        assert "a.md" in result
        assert result["a.md"]["title"] == "Title A"

    def test_fenced_json(self):
        text = '```json\n[{"filename": "b.md", "title": "Title B", "category": "General", "sub_category": "Uncategorized"}]\n```'
        result = _parse_migration_response(text)
        assert "b.md" in result
        assert result["b.md"]["title"] == "Title B"


# --- TestSlugifyTitle ---

class TestSlugifyTitle:
    def test_basic_title(self):
        assert _slugify_title("Mastering Prompt Engineering") == "mastering-prompt-engineering"

    def test_special_characters_removed(self):
        assert _slugify_title("What's Next: AI & ML?") == "whats-next-ai-ml"

    def test_multiple_spaces_collapsed(self):
        assert _slugify_title("Too   Many    Spaces") == "too-many-spaces"

    def test_long_title_truncated(self):
        long_title = "A " * 100
        result = _slugify_title(long_title)
        assert len(result) <= 80

    def test_empty_title_fallback(self):
        assert _slugify_title("") == "untitled"
        assert _slugify_title("!!!") == "untitled"

    def test_preserves_hyphens(self):
        assert _slugify_title("AI-Powered Tools") == "ai-powered-tools"


# --- TestBuildRenameFilename ---

class TestBuildRenameFilename:
    def test_no_collision(self):
        assert _build_rename_filename("My Title", set()) == "my-title.md"

    def test_collision_suffix(self):
        existing = {"my-title.md"}
        assert _build_rename_filename("My Title", existing) == "my-title-2.md"

    def test_multiple_collisions(self):
        existing = {"my-title.md", "my-title-2.md"}
        assert _build_rename_filename("My Title", existing) == "my-title-3.md"
