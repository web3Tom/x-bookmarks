from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


_REQUIRED = ("CLIENT_ID", "ACCESS_TOKEN", "REFRESH_TOKEN", "USER_ID", "ANTHROPIC_API_KEY")


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
    else:
        load_dotenv(override=True)

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
        output_dir=Path(
            os.environ.get(
                "KNOWLEDGE_BASE_DIR",
                str(Path.home() / "x-bookmarks-data"),
            )
        ).expanduser().resolve()
        / "bookmarks/posts",
    )
