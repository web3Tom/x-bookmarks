import pytest
from pathlib import Path

from src.config import Config, load_config


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

    def test_output_dir_is_correct(self, minimal_env):
        config = load_config(env_path=minimal_env)
        expected = Path.home() / "Documents/notes/obsidianVaults/dev-notes/03_AI/x"
        assert config.output_dir == expected

    def test_missing_client_id_raises(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("")
        monkeypatch.setenv("ACCESS_TOKEN", "t")
        monkeypatch.setenv("REFRESH_TOKEN", "r")
        monkeypatch.setenv("USER_ID", "u")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
        monkeypatch.delenv("CLIENT_ID", raising=False)
        with pytest.raises(ValueError, match="CLIENT_ID"):
            load_config(env_path=env_file)

    def test_missing_access_token_raises(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("")
        monkeypatch.setenv("CLIENT_ID", "c")
        monkeypatch.setenv("REFRESH_TOKEN", "r")
        monkeypatch.setenv("USER_ID", "u")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
        monkeypatch.delenv("ACCESS_TOKEN", raising=False)
        with pytest.raises(ValueError, match="ACCESS_TOKEN"):
            load_config(env_path=env_file)

    def test_missing_anthropic_key_raises(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("")
        monkeypatch.setenv("CLIENT_ID", "c")
        monkeypatch.setenv("ACCESS_TOKEN", "t")
        monkeypatch.setenv("REFRESH_TOKEN", "r")
        monkeypatch.setenv("USER_ID", "u")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
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

