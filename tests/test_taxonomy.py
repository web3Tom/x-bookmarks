from __future__ import annotations

import pytest
from pathlib import Path

from src.taxonomy import (
    DEFAULT_TAXONOMY,
    TaxonomyOverride,
    build_entity_tags_section,
    build_taxonomy_section,
    load_override_file,
    load_taxonomy_override,
    merge_taxonomies,
    normalize_tag,
    normalize_tags,
    parse_deprecations,
    parse_entity_tags,
    parse_override_guidance,
    _split_frontmatter_body,
)


class TestDefaultTaxonomy:
    """Test the DEFAULT_TAXONOMY constant."""

    def test_default_taxonomy_is_non_empty(self):
        assert DEFAULT_TAXONOMY
        assert len(DEFAULT_TAXONOMY) > 0

    def test_default_taxonomy_has_no_empty_subcategory_lists(self):
        for category, subs in DEFAULT_TAXONOMY.items():
            assert isinstance(subs, list)
            assert len(subs) > 0

    def test_default_taxonomy_has_no_catch_all_bucket(self):
        """Verify no 'General', 'Miscellaneous', or 'Other' top-level categories."""
        excluded = {"General", "Miscellaneous", "Other", "Uncategorized"}
        for category in DEFAULT_TAXONOMY.keys():
            assert category not in excluded


class TestBuildTaxonomySection:
    def test_builds_from_set(self):
        taxonomy = {
            "Category A": {"Sub 1", "Sub 2"},
            "Category B": {"Sub 3"},
        }
        result = build_taxonomy_section(taxonomy)
        assert "- Category A" in result
        assert "  - Sub 1" in result
        assert "  - Sub 2" in result
        assert "- Category B" in result
        assert "  - Sub 3" in result

    def test_builds_from_list(self):
        taxonomy = {
            "Technology": ["Software Development", "Hardware"],
        }
        result = build_taxonomy_section(taxonomy)
        assert "- Technology" in result
        assert "  - Hardware" in result
        assert "  - Software Development" in result

    def test_sorts_categories_and_subcategories(self):
        taxonomy = {
            "Zebra": ["Gamma", "Alpha", "Beta"],
            "Apple": ["Charlie", "Bravo"],
        }
        result = build_taxonomy_section(taxonomy)
        lines = result.split("\n")
        # Find indices of top-level categories
        apple_idx = next(i for i, line in enumerate(lines) if line == "- Apple")
        zebra_idx = next(i for i, line in enumerate(lines) if line == "- Zebra")
        assert apple_idx < zebra_idx  # Apple before Zebra

        # Check subcategories are sorted
        apple_subs = [lines[i] for i in range(apple_idx + 1, zebra_idx) if lines[i].startswith("  -")]
        assert apple_subs == ["  - Bravo", "  - Charlie"]

    def test_empty_dict(self):
        result = build_taxonomy_section({})
        assert result == ""


class TestSplitFrontmatterBody:
    def test_valid_split(self):
        content = "---\nkey: value\n---\n\nBody text here"
        yaml_block, body = _split_frontmatter_body(content)
        assert yaml_block == "key: value"
        assert body == "\nBody text here"

    def test_no_leading_delimiter(self):
        content = "key: value\n---\n\nBody"
        with pytest.raises(ValueError, match="No frontmatter found"):
            _split_frontmatter_body(content)

    def test_no_closing_delimiter(self):
        content = "---\nkey: value\n\nNo closing delimiter"
        with pytest.raises(ValueError, match="No closing --- delimiter"):
            _split_frontmatter_body(content)

    def test_multiline_yaml(self):
        content = "---\ntaxonomy:\n  Category: [Sub1, Sub2]\ndeprecate:\n  - Old\n---\n\nBody"
        yaml_block, body = _split_frontmatter_body(content)
        assert "taxonomy:" in yaml_block
        assert "deprecate:" in yaml_block
        assert body == "\nBody"


class TestLoadOverrideFile:
    def test_returns_none_for_none_filepath(self):
        assert load_override_file(None) is None

    def test_returns_none_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.md"
        assert load_override_file(missing) is None

    def test_loads_valid_taxonomy_from_file(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text(
            "---\ntaxonomy:\n  AI: [Coding, Reasoning]\n---\n\nGuidance"
        )
        result = load_override_file(override_file)
        assert result == {"AI": ["Coding", "Reasoning"]}

    def test_returns_none_when_no_taxonomy_key(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\ndeprecate: [Old]\n---\n\nGuidance")
        result = load_override_file(override_file)
        assert result is None

    def test_returns_none_when_taxonomy_not_dict(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\ntaxonomy: [A, B, C]\n---\n")
        result = load_override_file(override_file)
        assert result is None

    def test_returns_none_on_malformed_yaml(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\ninvalid: [unmatched\n---\n")
        result = load_override_file(override_file)
        assert result is None


class TestParseDeprecations:
    def test_returns_none_for_none_filepath(self):
        assert parse_deprecations(None) is None

    def test_returns_none_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.md"
        assert parse_deprecations(missing) is None

    def test_parses_deprecate_list(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text(
            "---\ndeprecate:\n  - General\n  - \"Uncategorized/Other\"\n---\n"
        )
        result = parse_deprecations(override_file)
        assert result == ["General", "Uncategorized/Other"]

    def test_returns_none_when_no_deprecate_key(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\ntaxonomy: {}\n---\n")
        result = parse_deprecations(override_file)
        assert result is None

    def test_returns_none_when_deprecate_not_list(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\ndeprecate: {a: b}\n---\n")
        result = parse_deprecations(override_file)
        assert result is None


class TestParseOverrideGuidance:
    def test_returns_none_for_none_filepath(self):
        assert parse_override_guidance(None) is None

    def test_returns_none_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.md"
        assert parse_override_guidance(missing) is None

    def test_parses_markdown_body(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        content = "---\ntaxonomy: {}\n---\n\n## Guidance\n\nSome rules here."
        override_file.write_text(content)
        result = parse_override_guidance(override_file)
        assert "## Guidance" in result
        assert "Some rules here." in result

    def test_returns_empty_string_when_no_body(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\ntaxonomy: {}\n---\n")
        result = parse_override_guidance(override_file)
        assert result == ""

    def test_strips_whitespace(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\ntaxonomy: {}\n---\n\n\n  Guidance text  \n\n")
        result = parse_override_guidance(override_file)
        assert result == "Guidance text"


class TestMergeTaxonomies:
    def test_merge_with_none_override(self):
        vault = {"AI": {"Coding"}, "Research": {"Papers"}}
        result = merge_taxonomies(vault, None)
        assert result == vault

    def test_merge_empty_vault_with_override(self):
        override = {"Technology": ["Hardware"], "Business": ["Finance"]}
        result = merge_taxonomies({}, override)
        assert result == {"Technology": {"Hardware"}, "Business": {"Finance"}}

    def test_union_merge(self):
        vault = {"AI": {"Coding", "Reasoning"}}
        override = {"AI": ["Memory"], "Business": ["Startups"]}
        result = merge_taxonomies(vault, override)
        assert result["AI"] == {"Coding", "Reasoning", "Memory"}
        assert result["Business"] == {"Startups"}

    def test_empty_vault_and_override(self):
        result = merge_taxonomies({}, None)
        assert result == {}

    def test_new_category_from_override(self):
        vault = {"AI": {"Coding"}}
        override = {"NewCat": ["NewSub"]}
        result = merge_taxonomies(vault, override)
        assert "NewCat" in result
        assert result["NewCat"] == {"NewSub"}

    def test_existing_category_extended(self):
        vault = {"Technology": {"Software"}}
        override = {"Technology": ["Hardware", "Software"]}
        result = merge_taxonomies(vault, override)
        # Both should be present (union)
        assert "Software" in result["Technology"]
        assert "Hardware" in result["Technology"]


class TestNormalizeTag:
    def test_valid_tag_basic(self):
        result = normalize_tag("model/llama3")
        assert result == "model/llama3"

    def test_valid_tag_with_spaces(self):
        result = normalize_tag("framework / lang graph")
        assert result == "framework/lang-graph"

    def test_valid_tag_with_underscores(self):
        result = normalize_tag("tool/docker_compose")
        assert result == "tool/docker-compose"

    def test_valid_tag_case_insensitive(self):
        result = normalize_tag("Model/DeepSeek")
        assert result == "model/deepseek"

    def test_missing_slash(self):
        result = normalize_tag("invalid-tag")
        assert result is None

    def test_multiple_slashes(self):
        result = normalize_tag("a/b/c")
        # Should use first slash, then slugify remaining (slash becomes nothing)
        assert result == "a/bc"

    def test_empty_prefix(self):
        result = normalize_tag("/entity")
        assert result is None

    def test_empty_entity(self):
        result = normalize_tag("prefix/")
        assert result is None

    def test_invalid_characters_dropped(self):
        result = normalize_tag("prefix/ent@ity#123")
        # Invalid chars (@, #) are dropped, not replaced
        assert result == "prefix/entity123"

    def test_unknown_prefix_with_allowed_set(self):
        allowed = {"model", "tool"}
        result = normalize_tag("framework/langgraph", allowed)
        assert result is None

    def test_known_prefix_with_allowed_set(self):
        allowed = {"model", "tool"}
        result = normalize_tag("tool/docker", allowed)
        assert result == "tool/docker"

    def test_collapse_repeated_dashes(self):
        result = normalize_tag("prefix/entity---name")
        assert result == "prefix/entity-name"

    def test_strip_leading_trailing_dashes(self):
        result = normalize_tag("prefix/-entity-")
        assert result == "prefix/entity"

    def test_whitespace_stripping(self):
        result = normalize_tag("  model / deepseek  ")
        assert result == "model/deepseek"


class TestNormalizeTags:
    def test_empty_list(self):
        result = normalize_tags([])
        assert result == ()

    def test_none_input(self):
        result = normalize_tags(None)
        assert result == ()

    def test_single_tag(self):
        result = normalize_tags(["model/deepseek"])
        assert result == ("model/deepseek",)

    def test_multiple_valid_tags(self):
        result = normalize_tags(["model/deepseek", "provider/openrouter", "tool/docker"])
        assert result == ("model/deepseek", "provider/openrouter", "tool/docker")

    def test_deduplication_preserves_order(self):
        result = normalize_tags(["model/deepseek", "tool/docker", "model/deepseek"])
        assert result == ("model/deepseek", "tool/docker")

    def test_invalid_tags_dropped(self):
        result = normalize_tags(["model/deepseek", "invalid", "tool/docker"])
        assert result == ("model/deepseek", "tool/docker")

    def test_with_allowed_prefixes(self):
        allowed = {"model", "tool"}
        result = normalize_tags(["model/deepseek", "framework/langgraph", "tool/docker"], allowed)
        assert result == ("model/deepseek", "tool/docker")

    def test_case_normalization(self):
        result = normalize_tags(["Model/DeepSeek", "Tool/Docker"])
        assert result == ("model/deepseek", "tool/docker")

    def test_whitespace_handling(self):
        result = normalize_tags(["model / deepseek", "tool / docker"])
        assert result == ("model/deepseek", "tool/docker")


class TestBuildEntityTagsSection:
    def test_empty_dict(self):
        result = build_entity_tags_section({})
        assert result == ""

    def test_single_prefix_single_entity(self):
        entity_tags = {"model": ["deepseek"]}
        result = build_entity_tags_section(entity_tags)
        assert result == "- model: deepseek"

    def test_single_prefix_multiple_entities(self):
        entity_tags = {"model": ["deepseek", "llama3", "claude"]}
        result = build_entity_tags_section(entity_tags)
        assert "- model: claude, deepseek, llama3" in result

    def test_multiple_prefixes_sorted(self):
        entity_tags = {
            "tool": ["docker"],
            "model": ["deepseek"],
            "framework": ["langgraph"],
        }
        result = build_entity_tags_section(entity_tags)
        lines = result.split("\n")
        # Check order: framework, model, tool (alphabetically)
        assert lines[0].startswith("- framework:")
        assert lines[1].startswith("- model:")
        assert lines[2].startswith("- tool:")

    def test_entities_sorted_within_prefix(self):
        entity_tags = {"model": ["zephyr", "llama3", "deepseek"]}
        result = build_entity_tags_section(entity_tags)
        assert "deepseek, llama3, zephyr" in result


class TestLoadTaxonomyOverride:
    def test_returns_none_for_none_filepath(self):
        result = load_taxonomy_override(None)
        assert result is None

    def test_returns_none_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.md"
        result = load_taxonomy_override(missing)
        assert result is None

    def test_loads_all_fields(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text(
            "---\n"
            "taxonomy:\n"
            "  AI: [Coding, Reasoning]\n"
            "entity_tags:\n"
            "  model: [deepseek, llama3]\n"
            "  tool: [docker]\n"
            "deprecate:\n"
            "  - General\n"
            "  - Uncategorized\n"
            "---\n\n"
            "## Guidance\n"
            "Use AI categories for ML posts."
        )
        result = load_taxonomy_override(override_file)
        assert result is not None
        assert result.taxonomy == {"AI": ["Coding", "Reasoning"]}
        assert result.entity_tags == {"model": ["deepseek", "llama3"], "tool": ["docker"]}
        assert result.deprecations == ["General", "Uncategorized"]
        assert "## Guidance" in result.guidance

    def test_none_values_become_safe_defaults(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\nkey: value\n---\n")
        result = load_taxonomy_override(override_file)
        assert result is not None
        assert result.taxonomy is None
        assert result.entity_tags == {}
        assert result.deprecations is None

    def test_type_guards_entity_tags(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\nentity_tags: [not, a, dict]\n---\n")
        result = load_taxonomy_override(override_file)
        assert result is not None
        assert result.entity_tags == {}

    def test_type_guards_deprecations(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\ndeprecate: {not: a, list}\n---\n")
        result = load_taxonomy_override(override_file)
        assert result is not None
        assert result.deprecations is None

    def test_malformed_yaml_returns_safe_default(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\nkey: [unmatched\n---\n")
        result = load_taxonomy_override(override_file)
        assert result is not None
        assert result.taxonomy is None
        assert result.entity_tags == {}


class TestParseEntityTags:
    def test_returns_empty_dict_for_none_filepath(self):
        result = parse_entity_tags(None)
        assert result == {}

    def test_returns_empty_dict_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.md"
        result = parse_entity_tags(missing)
        assert result == {}

    def test_parses_entity_tags_from_file(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text(
            "---\n"
            "entity_tags:\n"
            "  model: [deepseek]\n"
            "  tool: [docker]\n"
            "---\n"
        )
        result = parse_entity_tags(override_file)
        assert result == {"model": ["deepseek"], "tool": ["docker"]}

    def test_returns_empty_dict_when_no_entity_tags_key(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\ntaxonomy: {}\n---\n")
        result = parse_entity_tags(override_file)
        assert result == {}
