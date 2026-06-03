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
    _existing_mechanics,
    _existing_entity_tags,
    _parse_migration_response,
    _replace_body_heading,
    _resolve_pillar,
    _resolve_mechanics,
    _resolve_tags,
    _split_frontmatter_body,
    _parse_frontmatter,
    generate_titles_batch,
    migrate_directory,
    migrate_single_file,
    parse_existing_bookmark,
)
from src.markdown_writer import _slugify_title
from src.taxonomy import ENTITY_PREFIXES


# --- Fixtures ---

SAMPLE_FACETED_FRONTMATTER = """\
title: "How to master prompt engineering"
author: "@EXM7777"
pillar: "Applied Practice"
mechanics:
  - prompt-engineering
  - context-management
entity_tags:
  framework: [langchain]
date: 2026-01-15
read: false
synthesized: false
type: "article"
tweet_url: "https://x.com/EXM7777/status/2011800604709175808"
article_url: "http://x.com/i/article/2011690517210546176\""""

SAMPLE_FACETED_FILE = f"---\n{SAMPLE_FACETED_FRONTMATTER}\n---\n\n## How to master prompt engineering\n\nSome body text here.\n"

SAMPLE_WITH_BOOKMARK_REMOVED = """\
title: "Old Article"
author: "@bob"
pillar: "Theory & Concepts"
mechanics:
  - research
date: 2026-01-16
read: true
synthesized: false
type: "post"
tweet_url: "https://x.com/bob/status/222"
bookmark_removed: true
bookmark_removed_at: 2026-02-01"""


@pytest.fixture
def faceted_bookmark_file(tmp_path: Path) -> Path:
    """Create a sample faceted-schema bookmark file."""
    filepath = tmp_path / "mastering-prompt-engineering.md"
    filepath.write_text(SAMPLE_FACETED_FILE)
    return filepath


@pytest.fixture
def faceted_bookmark_dir(tmp_path: Path) -> Path:
    """Create a directory with multiple faceted-schema bookmark files."""
    d = tmp_path / "bookmarks"
    d.mkdir()

    (d / "alice-post.md").write_text(
        '---\ntitle: "Alice\'s Great Post"\nauthor: "@alice"\n'
        'pillar: "Applied Practice"\nmechanics:\n  - rag\n  - evaluation\n'
        'entity_tags:\n  tool: [langchain]\n'
        'date: 2026-01-15\nread: false\nsynthesized: false\ntype: "post"\n'
        'tweet_url: "https://x.com/alice/status/111"\n---\n\n'
        '## Alice\'s Great Post\n\nFirst post body.\n'
    )
    (d / "bob-research.md").write_text(
        '---\ntitle: "Bob\'s Research Note"\nauthor: "@bob"\n'
        'pillar: "Theory & Concepts"\nmechanics:\n  - research\n  - papers\n'
        'entity_tags:\n  model: [llama3]\n'
        'date: 2026-01-16\nread: true\nsynthesized: false\ntype: "post"\n'
        'tweet_url: "https://x.com/bob/status/222"\n---\n\n'
        '## Bob\'s Research Note\n\nSecond post body.\n'
    )
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
    def test_full_parse(self, faceted_bookmark_file: Path):
        result = parse_existing_bookmark(faceted_bookmark_file)
        assert result is not None
        assert result.filepath == faceted_bookmark_file
        assert result.frontmatter["title"] == "How to master prompt engineering"
        assert result.frontmatter["pillar"] == "Applied Practice"
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


# --- TestExistingMechanics ---

class TestExistingMechanics:
    def test_reads_mechanics_list(self):
        fm = {"mechanics": ["rag", "evaluation"]}
        result = _existing_mechanics(fm)
        assert result == ["rag", "evaluation"]

    def test_tolerates_missing_mechanics(self):
        fm = {"title": "Test"}
        result = _existing_mechanics(fm)
        assert result == []

    def test_tolerates_non_list_mechanics(self):
        fm = {"mechanics": "single-string"}
        result = _existing_mechanics(fm)
        assert result == []

    def test_coerces_to_strings(self):
        fm = {"mechanics": [1, 2, "three"]}
        result = _existing_mechanics(fm)
        assert result == ["1", "2", "three"]


# --- TestExistingEntityTags ---

class TestExistingEntityTags:
    def test_flattens_nested_entity_tags(self):
        fm = {"entity_tags": {"framework": ["langchain", "langgraph"], "model": ["llama3"]}}
        result = _existing_entity_tags(fm)
        assert set(result) == {"framework/langchain", "framework/langgraph", "model/llama3"}

    def test_tolerates_missing_entity_tags(self):
        fm = {"title": "Test"}
        result = _existing_entity_tags(fm)
        assert result == []

    def test_tolerates_non_dict_entity_tags(self):
        fm = {"entity_tags": ["not", "a", "dict"]}
        result = _existing_entity_tags(fm)
        assert result == []

    def test_skips_non_list_entity_values(self):
        fm = {"entity_tags": {"framework": "langchain", "model": ["llama3"]}}
        result = _existing_entity_tags(fm)
        assert result == ["model/llama3"]


# --- TestBuildMigrationPayload ---

class TestBuildMigrationPayload:
    def test_json_structure_faceted(self, faceted_bookmark_file: Path):
        bm = parse_existing_bookmark(faceted_bookmark_file)
        payload = _build_migration_payload([bm])
        data = json.loads(payload)
        assert len(data) == 1
        assert data[0]["filename"] == faceted_bookmark_file.name
        assert data[0]["title"] == "How to master prompt engineering"
        assert data[0]["pillar"] == "Applied Practice"
        assert data[0]["mechanics"] == ["prompt-engineering", "context-management"]
        assert data[0]["type"] == "article"

    def test_json_sends_pillar_and_mechanics(self, faceted_bookmark_file: Path):
        bm = parse_existing_bookmark(faceted_bookmark_file)
        payload = _build_migration_payload([bm])
        data = json.loads(payload)
        assert "pillar" in data[0]
        assert "mechanics" in data[0]
        assert "category" not in data[0]
        assert "subCategory" not in data[0]
        assert "tags" not in data[0]

    def test_body_truncation(self, tmp_path: Path):
        long_body = "x" * 5000
        filepath = tmp_path / "long.md"
        filepath.write_text(
            f'---\ntitle: "Long Post"\nauthor: "@alice"\n'
            f'pillar: "Applied Practice"\nmechanics:\n  - test\n'
            f'type: "post"\ndate: 2026-01-01\ntweet_url: "https://x.com/alice/status/1"\n---\n\n{long_body}\n'
        )
        bm = parse_existing_bookmark(filepath)
        payload = _build_migration_payload([bm])
        data = json.loads(payload)
        assert len(data[0]["body"]) == 2000


# --- TestResolvePillar ---

class TestResolvePillar:
    def test_uses_llm_pillar_if_valid(self):
        title_data = {"pillar": "Applied Practice"}
        fm = {"pillar": "Theory & Concepts"}
        pillars = ["Applied Practice", "Theory & Concepts", "Operations"]
        result = _resolve_pillar(title_data, fm, pillars, "Operations")
        assert result == "Applied Practice"

    def test_uses_existing_pillar_if_llm_absent(self):
        """When LLM pillar is absent/None/empty, falls back to existing."""
        title_data = {}  # No pillar from LLM
        fm = {"pillar": "Applied Practice"}
        pillars = ["Applied Practice", "Theory & Concepts"]
        result = _resolve_pillar(title_data, fm, pillars, "Theory & Concepts")
        assert result == "Applied Practice"

    def test_uses_fallback_if_both_invalid(self):
        """When LLM pillar invalid and existing missing, uses fallback."""
        title_data = {"pillar": "BadPillar"}
        fm = {}  # No existing pillar
        pillars = ["Applied Practice", "Theory & Concepts"]
        result = _resolve_pillar(title_data, fm, pillars, "Applied Practice")
        assert result == "Applied Practice"

    def test_prefers_llm_even_if_invalid_logs_warning(self):
        """LLM pillar is checked first; if invalid, falls through to fallback."""
        title_data = {"pillar": "InvalidPillar"}
        fm = {"pillar": "Applied Practice"}
        pillars = ["Applied Practice", "Theory & Concepts"]
        # When title_data has pillar (even invalid), it uses that path first
        result = _resolve_pillar(title_data, fm, pillars, "Theory & Concepts")
        # Invalid pillar causes fallback to fallback_pillar
        assert result == "Theory & Concepts"


# --- TestResolveMechanics ---

class TestResolveMechanics:
    def test_uses_llm_mechanics_if_present(self):
        title_data = {"mechanics": ["rag", "evaluation"]}
        fm = {"mechanics": ["old", "mechanics"]}
        result = _resolve_mechanics(title_data, fm)
        assert result == ("rag", "evaluation")

    def test_uses_existing_mechanics_if_llm_absent(self):
        title_data = {"mechanics": None}
        fm = {"mechanics": ["rag", "evaluation"]}
        result = _resolve_mechanics(title_data, fm)
        assert result == ("rag", "evaluation")

    def test_returns_empty_if_neither_present(self):
        title_data = {}
        fm = {}
        result = _resolve_mechanics(title_data, fm)
        assert result == ()


# --- TestResolveTags ---

class TestResolveTags:
    def test_uses_llm_tags_if_present(self):
        title_data = {"tags": ["framework/langchain", "model/llama3"]}
        fm = {"entity_tags": {"framework": ["langgraph"]}}
        allowed = set(ENTITY_PREFIXES)
        result = _resolve_tags(title_data, fm, allowed)
        assert result == ("framework/langchain", "model/llama3")

    def test_uses_existing_tags_if_llm_absent(self):
        title_data = {"tags": None}
        fm = {"entity_tags": {"framework": ["langchain", "langgraph"]}}
        allowed = set(ENTITY_PREFIXES)
        result = _resolve_tags(title_data, fm, allowed)
        assert set(result) == {"framework/langchain", "framework/langgraph"}

    def test_drops_invalid_prefixes(self):
        title_data = {"tags": ["framework/langchain", "invalid/tag"]}
        fm = {}
        allowed = set(ENTITY_PREFIXES)
        result = _resolve_tags(title_data, fm, allowed)
        assert result == ("framework/langchain",)


# --- TestBuildMigratedFrontmatter ---

class TestBuildMigratedFrontmatter:
    def test_faceted_schema_only(self):
        parsed = {
            "title": "Old Title",
            "author": "@alice",
            "date": "2026-01-15",
            "read": False,
            "type": "post",
            "tweet_url": "https://x.com/alice/status/12345",
        }
        result = _build_migrated_frontmatter(parsed, "New Title", "Applied Practice", ("rag",))
        # Should NOT contain old schema fields
        assert "category:" not in result
        assert "subCategory:" not in result
        assert "tags:" not in result or "entity_tags:" in result
        # Should contain faceted fields
        assert 'title: "New Title"' in result
        assert 'pillar: "Applied Practice"' in result
        assert "mechanics:" in result
        assert "- rag" in result

    def test_deprecated_fields_never_emitted(self):
        parsed = {
            "title": "Old",
            "author": "@alice",
            "author_name": "Alice",
            "tweet_id": "123",
            "likes": 10,
            "retweets": 5,
            "date": "2026-01-10",
            "type": "post",
            "tweet_url": "https://x.com/alice/status/123",
        }
        result = _build_migrated_frontmatter(parsed, "New Title", "Applied Practice", ("test",))
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
        result = _build_migrated_frontmatter(parsed, "Title", "Applied Practice", ("test",))
        assert "read: true" in result

    def test_entity_tags_nested_format(self):
        parsed = {
            "author": "@alice",
            "date": "2026-01-15",
            "read": False,
            "type": "post",
            "tweet_url": "https://x.com/alice/status/123",
        }
        result = _build_migrated_frontmatter(
            parsed, "Test", "Applied Practice", ("rag",), ("framework/langchain", "model/llama3"),
        )
        assert "entity_tags:" in result
        assert "framework:" in result
        assert "langchain" in result
        assert "model:" in result
        assert "llama3" in result

    def test_article_url_included(self):
        parsed = {
            "author": "@alice",
            "date": "2026-01-15",
            "read": False,
            "type": "article",
            "tweet_url": "https://x.com/alice/status/123",
            "article_url": "http://example.com/article",
        }
        result = _build_migrated_frontmatter(parsed, "Article", "Applied Practice", ("test",))
        assert 'article_url: "http://example.com/article"' in result

    def test_bookmark_removed_tail_lines(self):
        parsed = {
            "author": "@alice",
            "date": "2026-01-15",
            "read": False,
            "type": "post",
            "tweet_url": "https://x.com/alice/status/123",
            "bookmark_removed": True,
            "bookmark_removed_at": "2026-02-01",
        }
        result = _build_migrated_frontmatter(parsed, "Title", "Applied Practice", ("test",))
        assert "bookmark_removed: true" in result
        assert "bookmark_removed_at: 2026-02-01" in result

    def test_mechanics_defaults_to_uncategorized(self):
        parsed = {
            "author": "@alice",
            "date": "2026-01-15",
            "read": False,
            "type": "post",
            "tweet_url": "https://x.com/alice/status/123",
        }
        result = _build_migrated_frontmatter(parsed, "Title", "Applied Practice")
        assert "- uncategorized" in result

    def test_author_without_at_prefix(self):
        parsed = {
            "author": "alice",
            "date": "2026-01-15",
            "type": "post",
            "tweet_url": "https://x.com/alice/status/123",
        }
        result = _build_migrated_frontmatter(parsed, "Title", "Applied Practice", ("test",))
        assert 'author: "@alice"' in result

    def test_yaml_validates_faceted(self):
        parsed = {
            "author": "@alice",
            "date": "2026-01-15",
            "read": False,
            "type": "post",
            "tweet_url": "https://x.com/alice/status/123",
        }
        result = _build_migrated_frontmatter(
            parsed, "Test Title", "Applied Practice", ("rag", "evaluation"),
        )
        lines = result.strip().split("\n")
        yaml_body = "\n".join(lines[1:-1])
        data = yaml.safe_load(yaml_body)
        assert data["title"] == "Test Title"
        assert data["pillar"] == "Applied Practice"
        assert data["mechanics"] == ["rag", "evaluation"]


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
    def test_file_rewritten_and_renamed(self, faceted_bookmark_file: Path):
        bm = parse_existing_bookmark(faceted_bookmark_file)
        title_data = {
            "title": "Advanced Prompt Engineering",
            "pillar": "Applied Practice",
            "mechanics": ["prompt-engineering", "advanced-techniques"],
        }
        result = migrate_single_file(bm, title_data, pillars=["Applied Practice", "Theory & Concepts"])

        assert not result.skipped
        assert result.old_title == "How to master prompt engineering"
        assert result.new_title == "Advanced Prompt Engineering"
        assert result.old_filename == "mastering-prompt-engineering.md"
        assert result.new_filename == "advanced-prompt-engineering.md"
        assert result.heading_changed
        assert result.old_pillar == "Applied Practice"
        assert result.new_pillar == "Applied Practice"
        assert result.mechanics == ("prompt-engineering", "advanced-techniques")

        # Old file should be gone, new file should exist
        assert not faceted_bookmark_file.exists()
        new_path = faceted_bookmark_file.parent / "advanced-prompt-engineering.md"
        assert new_path.exists()

        content = new_path.read_text()
        assert 'title: "Advanced Prompt Engineering"' in content
        assert "pillar: \"Applied Practice\"" in content
        assert "mechanics:" in content
        assert "## Advanced Prompt Engineering" in content
        # Ensure no old schema fields
        assert "category:" not in content
        assert "subCategory:" not in content

        # Verify YAML is valid and faceted
        parts = content.split("---")
        data = yaml.safe_load(parts[1])
        assert data["title"] == "Advanced Prompt Engineering"
        assert data["pillar"] == "Applied Practice"
        assert "mechanics" in data

    def test_result_fields_populated_faceted(self, faceted_bookmark_file: Path):
        bm = parse_existing_bookmark(faceted_bookmark_file)
        title_data = {"title": "New Title", "pillar": "Theory & Concepts", "mechanics": ["research"]}
        result = migrate_single_file(bm, title_data, pillars=["Applied Practice", "Theory & Concepts"])

        assert isinstance(result, MigrationResult)
        assert result.new_filename == "new-title.md"
        assert isinstance(result.fields_removed, tuple)
        assert isinstance(result.heading_changed, bool)
        assert not result.skipped
        assert result.old_pillar == "Applied Practice"
        assert result.new_pillar == "Theory & Concepts"
        assert result.mechanics == ("research",)

    def test_fallback_title_on_empty(self, faceted_bookmark_file: Path):
        bm = parse_existing_bookmark(faceted_bookmark_file)
        title_data = {"title": ""}
        result = migrate_single_file(bm, title_data, pillars=["Applied Practice"])
        assert result.new_title != ""

    def test_collision_suffix(self, tmp_path: Path):
        """Two files with same title get -2 suffix."""
        for name in ("a.md", "b.md"):
            (tmp_path / name).write_text(
                '---\ntitle: "Same Title"\nauthor: "@user"\n'
                'pillar: "Applied Practice"\nmechanics:\n  - test\n'
                'date: 2026-01-01\ntype: "post"\n'
                'tweet_url: "https://x.com/user/status/1"\n---\n\n## Same Title\n\nBody.\n'
            )
        bm_a = parse_existing_bookmark(tmp_path / "a.md")
        bm_b = parse_existing_bookmark(tmp_path / "b.md")
        existing: set[str] = set()

        r1 = migrate_single_file(bm_a, {"title": "Same Title", "pillar": "Applied Practice"}, existing, pillars=["Applied Practice"])
        existing.add(r1.new_filename)

        r2 = migrate_single_file(bm_b, {"title": "Same Title", "pillar": "Applied Practice"}, existing, pillars=["Applied Practice"])

        assert r1.new_filename == "same-title.md"
        assert r2.new_filename == "same-title-2.md"

    def test_migration_result_includes_faceted_fields(self, faceted_bookmark_file: Path):
        """Verify MigrationResult captures pillar, mechanics, tags (not old_category/new_category)."""
        bm = parse_existing_bookmark(faceted_bookmark_file)
        title_data = {"title": "New", "pillar": "Theory & Concepts", "mechanics": ["research"]}
        result = migrate_single_file(bm, title_data, pillars=["Applied Practice", "Theory & Concepts"])

        assert hasattr(result, "old_pillar")
        assert hasattr(result, "new_pillar")
        assert hasattr(result, "mechanics")
        assert hasattr(result, "tags")
        assert not hasattr(result, "old_category")
        assert not hasattr(result, "new_category")


# --- TestMigrateDirectory ---

class TestMigrateDirectory:
    @patch("src.migrate.generate_titles_batch")
    def test_processes_all_md_files(self, mock_gen: MagicMock, faceted_bookmark_dir: Path):
        mock_gen.return_value = {
            "alice-post.md": {"title": "Alice Title", "pillar": "Applied Practice", "mechanics": ["rag"]},
            "bob-research.md": {"title": "Bob Title", "pillar": "Theory & Concepts", "mechanics": ["research"]},
        }
        results = migrate_directory(faceted_bookmark_dir, api_key="test-key")
        migrated = [r for r in results if not r.skipped]
        assert len(migrated) == 2

    @patch("src.migrate.generate_titles_batch")
    def test_files_renamed_to_title_slug(self, mock_gen: MagicMock, faceted_bookmark_dir: Path):
        mock_gen.return_value = {
            "alice-post.md": {"title": "Alice Title", "pillar": "Applied Practice", "mechanics": ["rag"]},
            "bob-research.md": {"title": "Bob Title", "pillar": "Theory & Concepts", "mechanics": ["research"]},
        }
        results = migrate_directory(faceted_bookmark_dir, api_key="test-key")

        new_filenames = {r.new_filename for r in results if not r.skipped}
        assert new_filenames == {"alice-title.md", "bob-title.md"}
        assert (faceted_bookmark_dir / "alice-title.md").exists()
        assert (faceted_bookmark_dir / "bob-title.md").exists()
        assert not (faceted_bookmark_dir / "alice-post.md").exists()
        assert not (faceted_bookmark_dir / "bob-research.md").exists()

    @patch("src.migrate.generate_titles_batch")
    def test_dry_run_doesnt_write(self, mock_gen: MagicMock, faceted_bookmark_dir: Path):
        original_alice = (faceted_bookmark_dir / "alice-post.md").read_text()
        original_bob = (faceted_bookmark_dir / "bob-research.md").read_text()

        mock_gen.return_value = {
            "alice-post.md": {"title": "Alice Title", "pillar": "Applied Practice", "mechanics": ["rag"]},
            "bob-research.md": {"title": "Bob Title", "pillar": "Theory & Concepts", "mechanics": ["research"]},
        }
        results = migrate_directory(faceted_bookmark_dir, api_key="test-key", dry_run=True)
        assert len(results) == 2
        assert results[0].new_filename == "alice-title.md"
        assert results[1].new_filename == "bob-title.md"

        # Files should be unchanged (not renamed or rewritten)
        assert (faceted_bookmark_dir / "alice-post.md").read_text() == original_alice
        assert (faceted_bookmark_dir / "bob-research.md").read_text() == original_bob

    @patch("src.migrate.generate_titles_batch")
    def test_read_true_preserved_after_migration(self, mock_gen: MagicMock, faceted_bookmark_dir: Path):
        mock_gen.return_value = {
            "alice-post.md": {"title": "Alice Title", "pillar": "Applied Practice", "mechanics": ["rag"]},
            "bob-research.md": {"title": "Bob Title", "pillar": "Theory & Concepts", "mechanics": ["research"]},
        }
        migrate_directory(faceted_bookmark_dir, api_key="test-key")

        content = (faceted_bookmark_dir / "bob-title.md").read_text()
        assert "read: true" in content

    def test_empty_directory(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        results = migrate_directory(empty_dir, api_key="test-key")
        assert results == []

    @patch("src.migrate.generate_titles_batch")
    def test_limit_caps_files_processed(self, mock_gen: MagicMock, tmp_path: Path):
        for i in range(3):
            (tmp_path / f"note-{i}.md").write_text(
                f'---\ntitle: "Note {i}"\nauthor: "@x"\n'
                f'pillar: "Applied Practice"\nmechanics:\n  - test\n'
                f'date: 2026-01-0{i + 1}\nread: false\n'
                f'synthesized: false\ntype: "post"\n'
                f'tweet_url: "https://x.com/x/status/{i}"\n---\n\n## Note {i}\n\n> body\n'
            )
        mock_gen.return_value = {
            "note-0.md": {"title": "First", "pillar": "Theory & Concepts", "mechanics": ["research"]},
            "note-1.md": {"title": "Second", "pillar": "Theory & Concepts", "mechanics": ["research"]},
        }
        results = migrate_directory(tmp_path, api_key="test-key", dry_run=True, limit=2)

        migrated = [r for r in results if not r.skipped]
        assert len(migrated) == 2  # third file never parsed
        # Only the first 2 files were sent to Claude (token-bounded)
        assert len(mock_gen.call_args.args[0]) == 2
        # Dry-run captures the pillar change
        assert migrated[0].old_pillar == "Applied Practice"
        assert migrated[0].new_pillar == "Theory & Concepts"

    @patch("src.migrate.generate_titles_batch")
    def test_dry_run_populates_faceted_fields(self, mock_gen: MagicMock, faceted_bookmark_dir: Path):
        mock_gen.return_value = {
            "alice-post.md": {"title": "Alice Title", "pillar": "Theory & Concepts", "mechanics": ["rag", "research"]},
            "bob-research.md": {"title": "Bob Title", "pillar": "Applied Practice", "mechanics": ["implementation"]},
        }
        results = migrate_directory(faceted_bookmark_dir, api_key="test-key", dry_run=True)

        migrated = [r for r in results if not r.skipped]
        assert len(migrated) == 2
        # Check faceted fields are populated
        assert migrated[0].old_pillar == "Applied Practice"
        assert migrated[0].new_pillar == "Theory & Concepts"
        assert migrated[0].mechanics == ("rag", "research")
        assert migrated[1].new_pillar == "Applied Practice"


# --- TestGenerateTitlesBatch ---

class TestGenerateTitlesBatch:
    @patch("src.migrate.anthropic.Anthropic")
    def test_mock_claude_response_parsed_faceted(self, mock_cls: MagicMock, faceted_bookmark_file: Path):
        bm = parse_existing_bookmark(faceted_bookmark_file)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {
                "filename": faceted_bookmark_file.name,
                "title": "Advanced Prompt Engineering",
                "pillar": "Applied Practice",
                "mechanics": ["prompt-engineering", "advanced"],
            }
        ]))]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_cls.return_value = mock_client

        result = generate_titles_batch([bm], api_key="test-key")
        assert faceted_bookmark_file.name in result
        assert result[faceted_bookmark_file.name]["title"] == "Advanced Prompt Engineering"
        assert result[faceted_bookmark_file.name]["pillar"] == "Applied Practice"
        assert result[faceted_bookmark_file.name]["mechanics"] == ["prompt-engineering", "advanced"]
        # Should NOT have old schema fields
        assert "category" not in result[faceted_bookmark_file.name]

    @patch("src.migrate.anthropic.Anthropic")
    def test_response_includes_tags_when_present(self, mock_cls: MagicMock, faceted_bookmark_file: Path):
        bm = parse_existing_bookmark(faceted_bookmark_file)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {
                "filename": faceted_bookmark_file.name,
                "title": "Title",
                "pillar": "Applied Practice",
                "mechanics": ["rag"],
                "tags": ["framework/langchain", "model/gpt4"],
            }
        ]))]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_cls.return_value = mock_client

        result = generate_titles_batch([bm], api_key="test-key")
        assert result[faceted_bookmark_file.name]["tags"] == ["framework/langchain", "model/gpt4"]

    @patch("src.migrate.anthropic.Anthropic")
    def test_fallback_on_missing_filename(self, mock_cls: MagicMock, faceted_bookmark_file: Path):
        bm = parse_existing_bookmark(faceted_bookmark_file)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {
                "filename": "wrong-file.md",
                "title": "Wrong File Title",
                "pillar": "Applied Practice",
                "mechanics": ["test"],
            }
        ]))]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_cls.return_value = mock_client

        result = generate_titles_batch([bm], api_key="test-key")
        # The actual file name should not be in the results
        assert faceted_bookmark_file.name not in result

    @patch("src.migrate.anthropic.Anthropic")
    def test_batching(self, mock_cls: MagicMock, tmp_path: Path):
        """Verify multiple API calls happen for large batches."""
        files = []
        for i in range(5):
            fp = tmp_path / f"file-{i}.md"
            fp.write_text(
                f'---\ntitle: "Title {i}"\nauthor: "@user"\n'
                f'pillar: "Applied Practice"\nmechanics:\n  - test\n'
                f'date: 2026-01-01\ntype: "post"\n'
                f'tweet_url: "https://x.com/user/status/{i}"\n---\n\n## Title {i}\n\nBody {i}\n'
            )
            files.append(fp)

        bookmarks = [parse_existing_bookmark(f) for f in files]

        mock_response = MagicMock()
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        def make_response(batch_files):
            entries = [
                {
                    "filename": f.name,
                    "title": f"New {f.stem}",
                    "pillar": "Theory & Concepts",
                    "mechanics": ["research"],
                }
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
        # Verify faceted fields are in response
        for entry in result.values():
            assert "pillar" in entry
            assert "mechanics" in entry


# --- TestParseResponse ---

class TestParseResponse:
    def test_plain_json_faceted(self):
        text = json.dumps([
            {
                "filename": "a.md",
                "title": "Title A",
                "pillar": "Applied Practice",
                "mechanics": ["rag"],
            },
        ])
        result = _parse_migration_response(text)
        assert "a.md" in result
        assert result["a.md"]["title"] == "Title A"
        assert result["a.md"]["pillar"] == "Applied Practice"
        assert result["a.md"]["mechanics"] == ["rag"]

    def test_fenced_json_faceted(self):
        text = '```json\n[{"filename": "b.md", "title": "Title B", "pillar": "Theory & Concepts", "mechanics": ["research"], "tags": ["framework/langchain"]}]\n```'
        result = _parse_migration_response(text)
        assert "b.md" in result
        assert result["b.md"]["title"] == "Title B"
        assert result["b.md"]["pillar"] == "Theory & Concepts"
        assert result["b.md"]["tags"] == ["framework/langchain"]

    def test_missing_mechanics_defaults_to_empty_list(self):
        text = json.dumps([
            {"filename": "c.md", "title": "Title C", "pillar": "Applied Practice"},
        ])
        result = _parse_migration_response(text)
        assert result["c.md"]["mechanics"] == []

    def test_missing_tags_defaults_to_empty_list(self):
        text = json.dumps([
            {
                "filename": "d.md",
                "title": "Title D",
                "pillar": "Applied Practice",
                "mechanics": ["test"],
            },
        ])
        result = _parse_migration_response(text)
        assert result["d.md"]["tags"] == []


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


class TestMigrationWithOverride:
    """Test migration with taxonomy override file."""

    @patch("src.migrate.anthropic.Anthropic")
    def test_generate_titles_batch_accepts_override_file(self, mock_cls, valid_override_file, faceted_bookmark_dir):
        """Test that generate_titles_batch accepts and uses override_file parameter."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {"filename": "alice-post.md", "title": "New Title", "pillar": "Applied Practice", "mechanics": ["rag"]},
        ]))]
        mock_client.messages.create.return_value = mock_response

        bookmarks = [parse_existing_bookmark(faceted_bookmark_dir / "alice-post.md")]
        bookmarks = [b for b in bookmarks if b is not None]

        result = generate_titles_batch(
            bookmarks,
            api_key="sk-test",
            override_file=valid_override_file,
        )

        assert "alice-post.md" in result
        assert result["alice-post.md"]["title"] == "New Title"
        assert result["alice-post.md"]["pillar"] == "Applied Practice"

    @patch("src.migrate.anthropic.Anthropic")
    def test_migrate_directory_accepts_override_file(self, mock_cls, valid_override_file, faceted_bookmark_dir):
        """Test that migrate_directory accepts and uses override_file parameter."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {"filename": "alice-post.md", "title": "Alice's Great Post", "pillar": "Applied Practice", "mechanics": ["rag"]},
            {"filename": "bob-research.md", "title": "Bob's Research", "pillar": "Theory & Concepts", "mechanics": ["research"]},
        ]))]
        mock_client.messages.create.return_value = mock_response

        results = migrate_directory(
            faceted_bookmark_dir,
            api_key="sk-test",
            dry_run=True,
            override_file=valid_override_file,
        )

        assert len(results) >= 2
        # Both files should be processed (dry_run doesn't affect processing)
        assert any(r.old_filename == "alice-post.md" for r in results if not r.skipped)

    @patch("src.migrate.anthropic.Anthropic")
    def test_override_file_none_is_allowed(self, mock_cls, faceted_bookmark_dir):
        """Test that passing override_file=None is handled gracefully."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {"filename": "alice-post.md", "title": "Title", "pillar": "Applied Practice", "mechanics": ["test"]},
        ]))]
        mock_client.messages.create.return_value = mock_response

        results = migrate_directory(
            faceted_bookmark_dir,
            api_key="sk-test",
            dry_run=True,
            override_file=None,
        )

        assert len(results) >= 2
