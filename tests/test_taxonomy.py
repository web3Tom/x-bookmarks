from __future__ import annotations

import pytest
from pathlib import Path

from src.taxonomy import (
    DEFAULT_PILLARS,
    DEFAULT_PILLAR_NAMES,
    DEFAULT_MECHANICS,
    ENTITY_PREFIXES,
    TaxonomyOverride,
    build_entity_tags_section,
    build_mechanics_section,
    build_pillars_section,
    group_entity_tags,
    load_taxonomy_override,
    normalize_mechanics,
    normalize_tag,
    normalize_tags,
    parse_deprecations,
    parse_entity_tags,
    parse_override_guidance,
    slugify_mechanic,
    validate_pillar,
    _split_frontmatter_body,
)


class TestDefaultConstants:
    """Test the DEFAULT_PILLARS, DEFAULT_PILLAR_NAMES, DEFAULT_MECHANICS, ENTITY_PREFIXES."""

    def test_default_pillars_is_tuple_of_tuples(self):
        assert isinstance(DEFAULT_PILLARS, tuple)
        assert len(DEFAULT_PILLARS) == 4
        for item in DEFAULT_PILLARS:
            assert isinstance(item, tuple)
            assert len(item) == 2
            name, focus = item
            assert isinstance(name, str)
            assert isinstance(focus, str)

    def test_default_pillar_names_matches_pillars(self):
        names_from_pillars = tuple(name for name, _ in DEFAULT_PILLARS)
        assert DEFAULT_PILLAR_NAMES == names_from_pillars
        assert DEFAULT_PILLAR_NAMES == ("Theory & Concepts", "Applied Practice", "Operations", "Strategy")

    def test_default_mechanics_is_empty_tuple(self):
        assert DEFAULT_MECHANICS == ()

    def test_entity_prefixes_is_correct(self):
        assert ENTITY_PREFIXES == ("framework", "harness", "model", "tool")


class TestSlugifyMechanic:
    """Test single mechanic slugification."""

    def test_basic_lowercase(self):
        assert slugify_mechanic("RAG") == "rag"

    def test_spaces_to_dashes(self):
        assert slugify_mechanic("persistent memory") == "persistent-memory"

    def test_underscores_to_dashes(self):
        assert slugify_mechanic("persistent_memory") == "persistent-memory"

    def test_mixed_spaces_and_underscores(self):
        assert slugify_mechanic("persistent__ memory  test") == "persistent-memory-test"

    def test_invalid_chars_dropped(self):
        assert slugify_mechanic("rag@advanced!") == "ragadvanced"

    def test_collapse_repeated_dashes(self):
        assert slugify_mechanic("rag---advanced") == "rag-advanced"

    def test_strip_leading_trailing_dashes(self):
        assert slugify_mechanic("--rag--") == "rag"

    def test_empty_string_returns_none(self):
        assert slugify_mechanic("") is None

    def test_whitespace_only_returns_none(self):
        assert slugify_mechanic("   ") is None

    def test_invalid_chars_only_returns_none(self):
        assert slugify_mechanic("@#$%^&*") is None


class TestNormalizeMechanics:
    """Test mechanics list normalization."""

    def test_empty_list_returns_empty_tuple(self):
        assert normalize_mechanics([]) == ()

    def test_none_returns_empty_tuple(self):
        assert normalize_mechanics(None) == ()

    def test_single_mechanic(self):
        assert normalize_mechanics(["RAG"]) == ("rag",)

    def test_multiple_mechanics(self):
        result = normalize_mechanics(["RAG", "Persistent Memory", "fine_tuning"])
        assert result == ("rag", "persistent-memory", "fine-tuning")

    def test_deduplication_preserves_first_seen(self):
        result = normalize_mechanics(["RAG", "rag", "RAG"])
        assert result == ("rag",)

    def test_whitespace_only_entries_dropped(self):
        result = normalize_mechanics(["RAG", "   ", "agentic"])
        assert result == ("rag", "agentic")

    def test_invalid_chars_only_entries_dropped(self):
        result = normalize_mechanics(["RAG", "@#$", "agentic"])
        assert result == ("rag", "agentic")

    def test_converts_strings(self):
        result = normalize_mechanics([1, 2.5, "RAG"])
        # Dot is not a valid char, gets dropped; only alphanumeric and dashes survive
        assert result == ("1", "25", "rag")


class TestValidatePillar:
    """Test pillar validation with fallback."""

    def test_valid_pillar_passes_through(self):
        allowed = ["Theory & Concepts", "Applied Practice"]
        result = validate_pillar("Theory & Concepts", allowed, "Applied Practice")
        assert result == "Theory & Concepts"

    def test_invalid_pillar_returns_fallback(self):
        allowed = ["Theory & Concepts", "Applied Practice"]
        result = validate_pillar("Invalid Pillar", allowed, "Applied Practice")
        assert result == "Applied Practice"

    def test_fallback_used_for_missing_pillar(self):
        allowed = DEFAULT_PILLAR_NAMES
        result = validate_pillar("Unknown", allowed, "Operations")
        assert result == "Operations"


class TestGroupEntityTags:
    """Test splitting flat entity tags into nested dict by prefix."""

    def test_empty_list_returns_empty_dict(self):
        assert group_entity_tags([]) == {}

    def test_single_tag_single_prefix(self):
        result = group_entity_tags(["model/deepseek"])
        assert result == {"model": ["deepseek"]}

    def test_multiple_tags_same_prefix(self):
        result = group_entity_tags(["model/deepseek", "model/llama3"])
        assert result == {"model": ["deepseek", "llama3"]}

    def test_multiple_tags_multiple_prefixes(self):
        result = group_entity_tags(["model/deepseek", "tool/docker", "model/llama3"])
        assert result == {"model": ["deepseek", "llama3"], "tool": ["docker"]}

    def test_respects_entity_prefixes_fixed_order(self):
        """Test that results are returned in ENTITY_PREFIXES order, not input order."""
        tags = ["tool/docker", "model/deepseek", "harness/langchain", "framework/react"]
        result = group_entity_tags(tags)
        keys = list(result.keys())
        # Should be in fixed order: framework, harness, model, tool
        assert keys == ["framework", "harness", "model", "tool"]

    def test_drops_provider_prefix(self):
        """provider/ is no longer allowed; should be dropped."""
        result = group_entity_tags(["model/deepseek", "provider/openrouter"])
        assert result == {"model": ["deepseek"]}
        assert "provider" not in result

    def test_drops_concept_prefix(self):
        """concept/ moved to mechanics; should be dropped."""
        result = group_entity_tags(["model/deepseek", "concept/rag"])
        assert result == {"model": ["deepseek"]}
        assert "concept" not in result

    def test_drops_unknown_prefix(self):
        result = group_entity_tags(["model/deepseek", "unknown/thing"])
        assert result == {"model": ["deepseek"]}

    def test_deduplicates_entities_first_seen(self):
        result = group_entity_tags(["model/deepseek", "model/deepseek"])
        assert result == {"model": ["deepseek"]}

    def test_drops_malformed_tags_without_slash(self):
        result = group_entity_tags(["model/deepseek", "invalid-tag"])
        assert result == {"model": ["deepseek"]}

    def test_drops_empty_entity(self):
        result = group_entity_tags(["model/", "model/deepseek"])
        assert result == {"model": ["deepseek"]}

    def test_whitespace_stripped_in_tag(self):
        result = group_entity_tags(["model / deepseek"])
        assert result == {"model": ["deepseek"]}


class TestBuildPillarsSection:
    """Test formatting pillars for markdown display."""

    def test_empty_list_returns_empty_string(self):
        assert build_pillars_section([]) == ""

    def test_single_pillar_no_description(self):
        result = build_pillars_section(["Theory & Concepts"])
        assert result == "- Theory & Concepts"

    def test_multiple_pillars_no_descriptions(self):
        result = build_pillars_section(["Theory & Concepts", "Applied Practice"])
        expected = "- Theory & Concepts\n- Applied Practice"
        assert result == expected

    def test_single_pillar_with_description(self):
        descriptions = {"Theory & Concepts": "Foundational ideas and research."}
        result = build_pillars_section(["Theory & Concepts"], descriptions)
        assert result == "- Theory & Concepts: Foundational ideas and research."

    def test_multiple_pillars_with_descriptions(self):
        descriptions = {
            "Theory & Concepts": "Foundational ideas and research.",
            "Applied Practice": "Building and implementing.",
        }
        result = build_pillars_section(["Theory & Concepts", "Applied Practice"], descriptions)
        lines = result.split("\n")
        assert lines[0] == "- Theory & Concepts: Foundational ideas and research."
        assert lines[1] == "- Applied Practice: Building and implementing."

    def test_partial_descriptions(self):
        """Only some pillars have descriptions."""
        descriptions = {"Applied Practice": "Building and implementing."}
        result = build_pillars_section(["Theory & Concepts", "Applied Practice"], descriptions)
        lines = result.split("\n")
        assert lines[0] == "- Theory & Concepts"
        assert lines[1] == "- Applied Practice: Building and implementing."

    def test_none_descriptions_treated_as_no_descriptions(self):
        result = build_pillars_section(["Theory & Concepts"], None)
        assert result == "- Theory & Concepts"


class TestBuildMechanicsSection:
    """Test formatting mechanics for markdown display."""

    def test_empty_list_returns_empty_string(self):
        assert build_mechanics_section([]) == ""

    def test_single_mechanic(self):
        result = build_mechanics_section(["rag"])
        assert result == "rag"

    def test_multiple_mechanics_sorted(self):
        result = build_mechanics_section(["rag", "agentic", "persistent-memory"])
        assert result == "agentic, persistent-memory, rag"

    def test_deduplicates_repeated_mechanics(self):
        result = build_mechanics_section(["rag", "agentic", "rag"])
        assert result == "agentic, rag"

    def test_comma_space_separated(self):
        result = build_mechanics_section(["a", "b", "c"])
        assert result == "a, b, c"


class TestNormalizeTag:
    """Test single tag normalization."""

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
        assert result == "a/bc"

    def test_empty_prefix(self):
        result = normalize_tag("/entity")
        assert result is None

    def test_empty_entity(self):
        result = normalize_tag("prefix/")
        assert result is None

    def test_invalid_characters_dropped(self):
        result = normalize_tag("prefix/ent@ity#123")
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
    """Test tag list normalization."""

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
        result = normalize_tags(["model/deepseek", "tool/docker"])
        assert result == ("model/deepseek", "tool/docker")

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
    """Test entity tags section formatting."""

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
        assert lines[0].startswith("- framework:")
        assert lines[1].startswith("- model:")
        assert lines[2].startswith("- tool:")

    def test_entities_sorted_within_prefix(self):
        entity_tags = {"model": ["zephyr", "llama3", "deepseek"]}
        result = build_entity_tags_section(entity_tags)
        assert "deepseek, llama3, zephyr" in result


class TestSplitFrontmatterBody:
    """Test frontmatter/body splitting."""

    def test_valid_split(self):
        content = "---\nkey: value\n---\n\nBody text here"
        yaml_block, body = _split_frontmatter_body(content)
        assert yaml_block == "key: value"
        # Body includes the leading newline after closing ---
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
        content = "---\nmechanics:\n  - rag\n  - agentic\ndeprecate:\n  - Old\n---\n\nBody"
        yaml_block, body = _split_frontmatter_body(content)
        assert "mechanics:" in yaml_block
        assert "deprecate:" in yaml_block
        assert body == "\nBody"


class TestLoadTaxonomyOverride:
    """Test full taxonomy override file parsing (NEW contract)."""

    def test_returns_none_for_none_filepath(self):
        result = load_taxonomy_override(None)
        assert result is None

    def test_returns_none_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.md"
        result = load_taxonomy_override(missing)
        assert result is None

    def test_loads_all_fields_from_valid_file(self, valid_override_file):
        """Test against conftest's valid_override_file fixture."""
        result = load_taxonomy_override(valid_override_file)
        assert result is not None
        assert result.pillars == ("Theory & Concepts", "Applied Practice")
        assert result.mechanics == ("rag", "persistent-memory")
        assert result.entity_tags == {"model": ["deepseek", "llama3"]}
        assert result.deprecations == ["General", "Uncategorized"]
        assert result.guidance is not None
        assert "Prefer Applied Practice" in result.guidance

    def test_loads_with_no_optional_fields(self, tmp_path):
        """Minimal file: only frontmatter, no keys."""
        override_file = tmp_path / "minimal.md"
        override_file.write_text("---\nkey: value\n---\n")
        result = load_taxonomy_override(override_file)
        assert result is not None
        assert result.pillars is None
        assert result.mechanics is None
        assert result.entity_tags == {}
        assert result.deprecations is None
        # No body text, so guidance is None
        assert result.guidance is None

    def test_pillars_as_list_of_strings(self, tmp_path):
        override_file = tmp_path / "pillars.md"
        override_file.write_text(
            "---\npillars:\n  - Theory & Concepts\n  - Operations\n---\n"
        )
        result = load_taxonomy_override(override_file)
        assert result.pillars == ("Theory & Concepts", "Operations")

    def test_mechanics_as_list_of_strings(self, tmp_path):
        override_file = tmp_path / "mechanics.md"
        override_file.write_text(
            "---\nmechanics:\n  - rag\n  - fine-tuning\n---\n"
        )
        result = load_taxonomy_override(override_file)
        assert result.mechanics == ("rag", "fine-tuning")

    def test_entity_tags_as_dict(self, tmp_path):
        override_file = tmp_path / "entity_tags.md"
        override_file.write_text(
            "---\nentity_tags:\n  model: [deepseek, llama3]\n  tool: [docker]\n---\n"
        )
        result = load_taxonomy_override(override_file)
        assert result.entity_tags == {"model": ["deepseek", "llama3"], "tool": ["docker"]}

    def test_deprecations_as_list(self, tmp_path):
        override_file = tmp_path / "deprecations.md"
        override_file.write_text(
            "---\ndeprecate:\n  - General\n  - Uncategorized\n---\n"
        )
        result = load_taxonomy_override(override_file)
        assert result.deprecations == ["General", "Uncategorized"]

    def test_guidance_from_body(self, tmp_path):
        override_file = tmp_path / "guidance.md"
        override_file.write_text(
            "---\nkey: value\n---\n\n## Domain Rules\n\nPrefer Theory & Concepts.\n"
        )
        result = load_taxonomy_override(override_file)
        assert result.guidance is not None
        assert "## Domain Rules" in result.guidance
        assert "Prefer Theory & Concepts" in result.guidance

    def test_guidance_empty_string_when_no_body(self, tmp_path):
        override_file = tmp_path / "no_body.md"
        override_file.write_text("---\nkey: value\n---\n")
        result = load_taxonomy_override(override_file)
        # No body text means guidance is None, not empty string
        assert result.guidance is None

    def test_type_guards_pillars_not_list(self, tmp_path):
        """pillars: must be a list; if not, set to None with warning."""
        override_file = tmp_path / "bad_pillars.md"
        override_file.write_text("---\npillars: not-a-list\n---\n")
        result = load_taxonomy_override(override_file)
        assert result.pillars is None
        assert result.entity_tags == {}

    def test_type_guards_mechanics_not_list(self, tmp_path):
        """mechanics: must be a list; if not, set to None with warning."""
        override_file = tmp_path / "bad_mechanics.md"
        override_file.write_text("---\nmechanics: {not: list}\n---\n")
        result = load_taxonomy_override(override_file)
        assert result.mechanics is None

    def test_type_guards_entity_tags_not_dict(self, tmp_path):
        """entity_tags: must be a dict; if not, set to {} with warning."""
        override_file = tmp_path / "bad_entity_tags.md"
        override_file.write_text("---\nentity_tags: [not, a, dict]\n---\n")
        result = load_taxonomy_override(override_file)
        assert result.entity_tags == {}

    def test_type_guards_deprecate_not_list(self, tmp_path):
        """deprecate: must be a list; if not, set to None with warning."""
        override_file = tmp_path / "bad_deprecate.md"
        override_file.write_text("---\ndeprecate: {not: list}\n---\n")
        result = load_taxonomy_override(override_file)
        assert result.deprecations is None

    def test_malformed_yaml_returns_safe_default_with_guidance(self, malformed_override_file):
        """Malformed YAML: return safe defaults + body text as guidance."""
        result = load_taxonomy_override(malformed_override_file)
        assert result is not None
        assert result.pillars is None
        assert result.mechanics is None
        assert result.entity_tags == {}
        assert result.deprecations is None

    def test_non_dict_frontmatter_returns_safe_default(self, tmp_path):
        """Frontmatter is not a dict (e.g., YAML scalar): return safe defaults."""
        override_file = tmp_path / "scalar_frontmatter.md"
        override_file.write_text("---\njust a string\n---\n\nBody")
        result = load_taxonomy_override(override_file)
        assert result is not None
        assert result.pillars is None
        assert result.entity_tags == {}
        assert result.guidance == "Body"


class TestParseDeprecations:
    """Test deprecations delegation to load_taxonomy_override."""

    def test_returns_none_for_none_filepath(self):
        assert parse_deprecations(None) is None

    def test_returns_none_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.md"
        assert parse_deprecations(missing) is None

    def test_parses_deprecate_list(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text(
            "---\ndeprecate:\n  - General\n  - Uncategorized\n---\n"
        )
        result = parse_deprecations(override_file)
        assert result == ["General", "Uncategorized"]

    def test_returns_none_when_no_deprecate_key(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\nmechanics: [rag]\n---\n")
        result = parse_deprecations(override_file)
        assert result is None

    def test_returns_none_when_deprecate_not_list(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\ndeprecate: {a: b}\n---\n")
        result = parse_deprecations(override_file)
        assert result is None


class TestParseOverrideGuidance:
    """Test guidance delegation to load_taxonomy_override."""

    def test_returns_none_for_none_filepath(self):
        assert parse_override_guidance(None) is None

    def test_returns_none_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.md"
        assert parse_override_guidance(missing) is None

    def test_parses_markdown_body(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        content = "---\nmechanics: [rag]\n---\n\n## Guidance\n\nSome rules here."
        override_file.write_text(content)
        result = parse_override_guidance(override_file)
        assert "## Guidance" in result
        assert "Some rules here." in result

    def test_returns_empty_string_when_no_body(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\nmechanics: [rag]\n---\n")
        result = parse_override_guidance(override_file)
        assert result == ""

    def test_strips_whitespace_from_body(self, tmp_path):
        override_file = tmp_path / "taxonomy.md"
        override_file.write_text("---\nkey: value\n---\n\n\n  Guidance text  \n\n")
        result = parse_override_guidance(override_file)
        assert result == "Guidance text"


class TestParseEntityTags:
    """Test entity_tags delegation to load_taxonomy_override."""

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
        override_file.write_text("---\nmechanics: [rag]\n---\n")
        result = parse_entity_tags(override_file)
        assert result == {}
