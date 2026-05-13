from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


_REQUIRED = ("CLIENT_ID", "ACCESS_TOKEN", "REFRESH_TOKEN", "USER_ID", "ANTHROPIC_API_KEY")
_OUTPUT_DIR_ENV = "KNOWLEDGE_BASE_DIR"
_LEGACY_OUTPUT_DIR_ENV = "KNOWLEDGE_DIR"
_PASS_KEY_PATH = "ai/anthropic/api-key"
_LOCAL_ENVRC_FILENAME = ".envrc.local"


def _resolve_anthropic_key_from_pass() -> str:
    """Fetch the Anthropic API key from the user's `pass` vault.

    Used when `.env` overrides the shell-exported key with an empty value.
    Returns "" if `pass` is unavailable or the entry is missing.
    """
    if shutil.which("pass") is None:
        return ""
    try:
        result = subprocess.run(
            ["pass", _PASS_KEY_PATH],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()


def _read_local_envrc_value(key: str, envrc_path: Path) -> str:
    """Read a simple export KEY=value entry from a local direnv override file."""
    if not envrc_path.exists():
        return ""

    for raw_line in envrc_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if not line.startswith(f"{key}="):
            continue

        value = line.split("=", 1)[1].strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {'"', "'"}
        ):
            value = value[1:-1]
        return os.path.expandvars(value)

    return ""


def _resolve_output_dir(env_dir: Path) -> Path:
    """Resolve the target notes directory from canonical or legacy env vars."""
    output_dir = (
        os.environ.get(_OUTPUT_DIR_ENV)
        or os.environ.get(_LEGACY_OUTPUT_DIR_ENV)
        or _read_local_envrc_value(_OUTPUT_DIR_ENV, env_dir / _LOCAL_ENVRC_FILENAME)
        or _read_local_envrc_value(_LEGACY_OUTPUT_DIR_ENV, env_dir / _LOCAL_ENVRC_FILENAME)
        or str(Path.home() / "x-bookmarks-data")
    )
    return Path(output_dir).expanduser().resolve()


@dataclass(frozen=True)
class Config:
    client_id: str
    client_secret: str | None
    access_token: str
    refresh_token: str
    user_id: str
    anthropic_api_key: str
    output_dir: Path


def load_config(env_path: Path | None = None) -> Config:
    """Load configuration from environment variables (and optional .env file)."""
    if env_path is not None:
        load_dotenv(env_path, override=True)
        env_dir = env_path.parent
    else:
        load_dotenv(override=True)
        env_dir = Path.cwd()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        key = _resolve_anthropic_key_from_pass()
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key

    missing = [key for key in _REQUIRED if not os.environ.get(key)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return Config(
        client_id=os.environ["CLIENT_ID"],
        client_secret=os.environ.get("CLIENT_SECRET") or None,
        access_token=os.environ["ACCESS_TOKEN"],
        refresh_token=os.environ["REFRESH_TOKEN"],
        user_id=os.environ["USER_ID"],
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        output_dir=_resolve_output_dir(env_dir),
    )
