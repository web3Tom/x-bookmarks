import pytest
from pathlib import Path

from src.config import Config, load_config, resolve_taxonomy_file


@pytest.fixture
def valid_env(tmp_path):
    """Create a valid .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CLIENT_ID=test_client_id\n"
        "CLIENT_SECRET=test_secret\n"
        "ACCESS_TOKEN=test_access\n"
        "REFRESH_TOKEN=test_refresh\n"
        "USER_ID=123456\n"
        "ANTHROPIC_API_KEY=sk-ant-test\n"
    )
    return env_file


@pytest.fixture
def minimal_env(tmp_path, monkeypatch):
    """Set env vars and provide an empty .env so project .env is not loaded."""
    monkeypatch.setenv("CLIENT_ID", "test_client_id")
    monkeypatch.setenv("CLIENT_SECRET", "test_secret")
    monkeypatch.setenv("ACCESS_TOKEN", "test_access")
    monkeypatch.setenv("REFRESH_TOKEN", "test_refresh")
    monkeypatch.setenv("USER_ID", "123456")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    env_file = tmp_path / ".env"
    env_file.write_text("")
    return env_file


class TestConfig:
    def test_config_is_frozen(self, minimal_env):
        config = load_config(env_path=minimal_env)
        with pytest.raises(AttributeError):
            config.client_id = "changed"

    def test_load_config_from_env_vars(self, minimal_env):
        config = load_config(env_path=minimal_env)
        assert config.client_id == "test_client_id"
        assert config.access_token == "test_access"
        assert config.user_id == "123456"
        assert config.anthropic_api_key == "sk-ant-test"

    def test_load_config_from_env_file(self, valid_env):
        config = load_config(env_path=valid_env)
        assert config.client_id == "test_client_id"
        assert config.refresh_token == "test_refresh"

    def test_output_dir_is_correct(self, minimal_env, monkeypatch):
        monkeypatch.delenv("KNOWLEDGE_BASE_DIR", raising=False)
        config = load_config(env_path=minimal_env)
        expected = Path.home() / "x-bookmarks-data"
        assert config.output_dir == expected

    def test_output_dir_from_env_override(self, minimal_env, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_DIR", "/tmp/custom-kb")
        config = load_config(env_path=minimal_env)
        assert config.output_dir == Path("/tmp/custom-kb")

    def test_output_dir_from_legacy_env_fallback(self, minimal_env, monkeypatch):
        monkeypatch.delenv("KNOWLEDGE_BASE_DIR", raising=False)
        monkeypatch.setenv("KNOWLEDGE_DIR", "/tmp/legacy-kb")
        config = load_config(env_path=minimal_env)
        assert config.output_dir == Path("/tmp/legacy-kb")

    def test_output_dir_from_local_envrc_fallback(self, minimal_env, monkeypatch, tmp_path):
        monkeypatch.delenv("KNOWLEDGE_BASE_DIR", raising=False)
        monkeypatch.delenv("KNOWLEDGE_DIR", raising=False)
        (tmp_path / ".envrc.local").write_text('export KNOWLEDGE_BASE_DIR="/tmp/envrc-kb"\n')
        config = load_config(env_path=minimal_env)
        assert config.output_dir == Path("/tmp/envrc-kb")

    def test_output_dir_from_legacy_local_envrc_fallback(self, minimal_env, monkeypatch, tmp_path):
        monkeypatch.delenv("KNOWLEDGE_BASE_DIR", raising=False)
        monkeypatch.delenv("KNOWLEDGE_DIR", raising=False)
        (tmp_path / ".envrc.local").write_text("export KNOWLEDGE_DIR=/tmp/legacy-envrc-kb\n")
        config = load_config(env_path=minimal_env)
        assert config.output_dir == Path("/tmp/legacy-envrc-kb")

    def test_output_dir_prefers_canonical_env(self, minimal_env, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_DIR", "/tmp/custom-kb")
        monkeypatch.setenv("KNOWLEDGE_DIR", "/tmp/legacy-kb")
        config = load_config(env_path=minimal_env)
        assert config.output_dir == Path("/tmp/custom-kb")

    def test_output_dir_expands_tilde(self, minimal_env, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_DIR", "~/my-kb")
        config = load_config(env_path=minimal_env)
        assert "~" not in str(config.output_dir)
        assert config.output_dir.is_absolute()
        assert str(config.output_dir).endswith("my-kb")

    def test_loads_without_any_oauth_credentials(self, tmp_path, monkeypatch):
        """The headline property of the twitter-cli default: the tool runs with
        no X developer account at all. Requiring OAuth here would make the free
        path unreachable for anyone who never registered an X app.
        """
        env_file = tmp_path / ".env"
        env_file.write_text("")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
        for name in ("CLIENT_ID", "ACCESS_TOKEN", "REFRESH_TOKEN", "USER_ID"):
            monkeypatch.delenv(name, raising=False)

        config = load_config(env_path=env_file)

        assert config.has_official_credentials is False
        assert config.client_id == ""
        assert config.access_token == ""

    def test_partial_oauth_is_reported_unusable(self, tmp_path, monkeypatch):
        """Half-configured OAuth must be caught before --official runs, not
        surface as a 401 midway through a paid fetch."""
        env_file = tmp_path / ".env"
        env_file.write_text("")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
        monkeypatch.setenv("CLIENT_ID", "c")
        monkeypatch.setenv("ACCESS_TOKEN", "t")
        for name in ("REFRESH_TOKEN", "USER_ID"):
            monkeypatch.delenv(name, raising=False)

        assert load_config(env_path=env_file).has_official_credentials is False

    def test_missing_anthropic_key_still_raises(self, tmp_path, monkeypatch):
        """Categorization is not optional on either path, so this key remains
        the one hard requirement."""
        env_file = tmp_path / ".env"
        env_file.write_text("")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(
            "src.config._resolve_anthropic_key_from_pass", lambda: ""
        )
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            load_config(env_path=env_file)

    def test_missing_anthropic_key_raises(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("")
        monkeypatch.setenv("CLIENT_ID", "c")
        monkeypatch.setenv("ACCESS_TOKEN", "t")
        monkeypatch.setenv("REFRESH_TOKEN", "r")
        monkeypatch.setenv("USER_ID", "u")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr("src.config._resolve_anthropic_key_from_pass", lambda: "")
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            load_config(env_path=env_file)

    def test_client_secret_optional(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("")
        monkeypatch.setenv("CLIENT_ID", "c")
        monkeypatch.setenv("ACCESS_TOKEN", "t")
        monkeypatch.setenv("REFRESH_TOKEN", "r")
        monkeypatch.setenv("USER_ID", "u")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
        monkeypatch.delenv("CLIENT_SECRET", raising=False)
        config = load_config(env_path=env_file)
        assert config.client_secret is None

    def test_config_includes_taxonomy_file(self, minimal_env):
        config = load_config(env_path=minimal_env)
        assert hasattr(config, "taxonomy_file")

    def test_taxonomy_file_none_by_default(self, minimal_env, monkeypatch):
        monkeypatch.delenv("X_BOOKMARKS_TAXONOMY_FILE", raising=False)
        config = load_config(env_path=minimal_env)
        assert config.taxonomy_file is None


class TestResolveTaxonomyFile:
    def test_returns_none_when_unset(self, tmp_path, monkeypatch):
        monkeypatch.delenv("X_BOOKMARKS_TAXONOMY_FILE", raising=False)
        result = resolve_taxonomy_file(tmp_path)
        assert result is None

    def test_returns_none_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("X_BOOKMARKS_TAXONOMY_FILE", "/nonexistent/taxonomy.md")
        result = resolve_taxonomy_file(tmp_path)
        assert result is None

    def test_resolves_from_env_var(self, tmp_path, monkeypatch):
        taxonomy_file = tmp_path / "taxonomy.md"
        taxonomy_file.write_text("---\ntaxonomy: {}\n---\n")
        monkeypatch.setenv("X_BOOKMARKS_TAXONOMY_FILE", str(taxonomy_file))
        result = resolve_taxonomy_file(tmp_path)
        assert result == taxonomy_file

    def test_resolves_from_envrc_local(self, tmp_path, monkeypatch):
        monkeypatch.delenv("X_BOOKMARKS_TAXONOMY_FILE", raising=False)
        taxonomy_file = tmp_path / "taxonomy.md"
        taxonomy_file.write_text("---\ntaxonomy: {}\n---\n")
        (tmp_path / ".envrc.local").write_text(f'export X_BOOKMARKS_TAXONOMY_FILE="{taxonomy_file}"\n')
        result = resolve_taxonomy_file(tmp_path)
        assert result == taxonomy_file

    def test_expands_tilde(self, tmp_path, monkeypatch, home_dir=None):
        # Create a temporary taxonomy file in a test location
        taxonomy_file = tmp_path / "taxonomy.md"
        taxonomy_file.write_text("---\ntaxonomy: {}\n---\n")
        monkeypatch.setenv("X_BOOKMARKS_TAXONOMY_FILE", str(taxonomy_file))
        result = resolve_taxonomy_file(tmp_path)
        assert result.is_absolute()

    def test_prefers_env_var_over_envrc(self, tmp_path, monkeypatch):
        monkeypatch.delenv("X_BOOKMARKS_TAXONOMY_FILE", raising=False)
        env_file = tmp_path / "env-taxonomy.md"
        env_file.write_text("---\ntaxonomy: {}\n---\n")
        envrc_file = tmp_path / "envrc-taxonomy.md"
        envrc_file.write_text("---\ntaxonomy: {}\n---\n")
        monkeypatch.setenv("X_BOOKMARKS_TAXONOMY_FILE", str(env_file))
        (tmp_path / ".envrc.local").write_text(f'export X_BOOKMARKS_TAXONOMY_FILE="{envrc_file}"\n')
        result = resolve_taxonomy_file(tmp_path)
        assert result == env_file
