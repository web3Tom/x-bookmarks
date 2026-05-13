from src.auth_helper import _write_env


class TestWriteEnv:
    def test_preserves_existing_output_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            "CLIENT_ID=old\n"
            "ANTHROPIC_API_KEY=\n"
            "KNOWLEDGE_BASE_DIR=/tmp/bookmark-notes\n"
        )

        _write_env("client", "access", "refresh", "user")

        content = (tmp_path / ".env").read_text()
        assert "CLIENT_ID=client\n" in content
        assert "ACCESS_TOKEN=access\n" in content
        assert "REFRESH_TOKEN=refresh\n" in content
        assert "USER_ID=user\n" in content
        assert "KNOWLEDGE_BASE_DIR=/tmp/bookmark-notes\n" in content

    def test_persists_output_dir_from_environment(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KNOWLEDGE_BASE_DIR", "/tmp/from-env")
        (tmp_path / ".env").write_text("CLIENT_ID=old\nANTHROPIC_API_KEY=\n")

        _write_env("client", "access", "refresh", "user")

        content = (tmp_path / ".env").read_text()
        assert "KNOWLEDGE_BASE_DIR=/tmp/from-env\n" in content

    def test_persists_legacy_output_dir_as_canonical(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KNOWLEDGE_BASE_DIR", raising=False)
        monkeypatch.setenv("KNOWLEDGE_DIR", "/tmp/from-legacy-env")
        (tmp_path / ".env").write_text("CLIENT_ID=old\nANTHROPIC_API_KEY=\n")

        _write_env("client", "access", "refresh", "user")

        content = (tmp_path / ".env").read_text()
        assert "KNOWLEDGE_BASE_DIR=/tmp/from-legacy-env\n" in content
        assert "KNOWLEDGE_DIR=" not in content

    def test_persists_output_dir_from_local_envrc(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", "/tmp")
        monkeypatch.delenv("KNOWLEDGE_BASE_DIR", raising=False)
        monkeypatch.delenv("KNOWLEDGE_DIR", raising=False)
        (tmp_path / ".env").write_text("CLIENT_ID=old\nANTHROPIC_API_KEY=\n")
        (tmp_path / ".envrc.local").write_text('export KNOWLEDGE_BASE_DIR="$HOME/from-envrc"\n')

        _write_env("client", "access", "refresh", "user")

        content = (tmp_path / ".env").read_text()
        assert "KNOWLEDGE_BASE_DIR=/tmp/from-envrc\n" in content

    def test_keeps_output_dir_commented_when_unconfigured(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KNOWLEDGE_BASE_DIR", raising=False)
        monkeypatch.delenv("KNOWLEDGE_DIR", raising=False)

        _write_env("client", "access", "refresh", "user")

        content = (tmp_path / ".env").read_text()
        assert "# KNOWLEDGE_BASE_DIR=\n" in content
