from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

logger = logging.getLogger(__name__)

# Only the categorization key is universally required. The X OAuth variables
# were dropped from this list when `twitter-cli` became the default retrieval
# mechanism: the tool now runs with no X developer account at all. They are
# still read when present, because `--official` remains available.
_REQUIRED = ("ANTHROPIC_API_KEY",)
_OFFICIAL_REQUIRED = ("CLIENT_ID", "ACCESS_TOKEN", "REFRESH_TOKEN", "USER_ID")
_OUTPUT_DIR_ENV = "KNOWLEDGE_BASE_DIR"
_LEGACY_OUTPUT_DIR_ENV = "KNOWLEDGE_DIR"
_TAXONOMY_FILE_ENV = "X_BOOKMARKS_TAXONOMY_FILE"
_LOCAL_ENVRC_FILENAME = ".envrc.local"

# Secrets this tool will look up in the user's `pass` vault, in the order they
# are tried. The twitter-cli cookies belong here for the same reason the API key
# does: `.envrc.local` documents them as `$(pass ...)` substitutions, and only
# direnv can evaluate those. Without a fallback, the default retrieval path has
# no credential route at all on a machine without direnv.
_PASS_ENTRIES = {
    "ANTHROPIC_API_KEY": "ai/anthropic/api-key",
    "TWITTER_AUTH_TOKEN": "x/auth-token",
    "TWITTER_CT0": "x/ct0",
}
_PASS_TIMEOUT_S = 10


class PassLookupError(RuntimeError):
    """`pass` was reachable but the secret could not be read.

    Distinct from "not configured": a locked GPG agent is an operator error with
    a concrete fix, and reporting it as an absent variable sends the operator to
    `.env`, which is not where the failure is.
    """


def _apply_dotenv(env_path: Path | None) -> None:
    """Apply `.env` entries to the environment, ignoring blank values.

    `load_dotenv(override=True)` treats `KEY=` as an instruction to unset, so the
    placeholder line shipped in `.env` silently erased a key exported into the
    shell. A blank entry means "not configured in this file", never "clear it".
    Populated entries keep their previous precedence over the environment.
    """
    values = dotenv_values() if env_path is None else dotenv_values(env_path)
    for key, value in values.items():
        if value and value.strip():
            os.environ[key] = value


def _resolve_from_pass(entry: str) -> str:
    """Fetch one secret from the user's `pass` vault.

    Returns "" when `pass` is absent or the entry does not exist, both of which
    mean "not configured here" and must stay quiet so other sources can be tried.

    Raises:
        PassLookupError: the lookup started but could not complete, which in
            practice means the GPG agent holds no cached passphrase and pinentry
            cannot prompt on a non-interactive shell.
    """
    if shutil.which("pass") is None:
        return ""
    try:
        result = subprocess.run(
            ["pass", entry],
            capture_output=True,
            text=True,
            timeout=_PASS_TIMEOUT_S,
            check=True,
        )
    except subprocess.CalledProcessError:
        return ""
    except subprocess.TimeoutExpired as exc:
        raise PassLookupError(
            f"`pass {entry}` timed out after {_PASS_TIMEOUT_S}s. The GPG agent "
            "has no cached passphrase and pinentry cannot prompt here. Run "
            f"`pass {entry}` once in an interactive terminal to unlock the "
            "agent, or export the variable directly."
        ) from exc
    return result.stdout.strip()


def _fill_from_pass() -> dict[str, str]:
    """Populate absent credentials from `pass`; return per-variable failures.

    Failures are returned rather than raised so a locked `x/ct0` cannot abort an
    `--official` run that never touches the twitter-cli path. The caller decides
    which failures are fatal.
    """
    failures: dict[str, str] = {}
    for name, entry in _PASS_ENTRIES.items():
        if os.environ.get(name):
            continue
        if failures:
            # One timeout proves the agent cannot unlock right now. Retrying the
            # remaining entries would multiply the stall by the secret count.
            continue
        try:
            value = _resolve_from_pass(entry)
        except PassLookupError as exc:
            logger.warning("%s", exc)
            failures[name] = str(exc)
            continue
        if value:
            os.environ[name] = value
    return failures


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


def resolve_taxonomy_file(env_dir: Path) -> Path | None:
    """Resolve the taxonomy override file from env var or .envrc.local.

    Mirrors the pattern for _resolve_output_dir but returns None if unset.
    Returns None if the resolved path does not exist.
    Logs a warning and returns None on resolution failure.
    Expands ~ and resolves to absolute path.
    """
    taxonomy_path = (
        os.environ.get(_TAXONOMY_FILE_ENV)
        or _read_local_envrc_value(_TAXONOMY_FILE_ENV, env_dir / _LOCAL_ENVRC_FILENAME)
    )

    if not taxonomy_path:
        return None

    resolved = Path(taxonomy_path).expanduser().resolve()
    if not resolved.exists():
        logger.warning("Taxonomy override file does not exist: %s", resolved)
        return None

    return resolved


@dataclass(frozen=True)
class Config:
    client_id: str
    client_secret: str | None
    access_token: str
    refresh_token: str
    user_id: str
    anthropic_api_key: str
    output_dir: Path
    taxonomy_file: Path | None

    @property
    def has_official_credentials(self) -> bool:
        """Whether the OAuth path is usable.

        Empty rather than absent: these fields are always present on the
        dataclass, but carry "" when no X developer account is configured.
        """
        return all(
            (self.client_id, self.access_token, self.refresh_token, self.user_id)
        )


def load_config(env_path: Path | None = None) -> Config:
    """Load configuration from environment variables (and optional .env file)."""
    _apply_dotenv(env_path)
    env_dir = env_path.parent if env_path is not None else Path.cwd()

    pass_failures = _fill_from_pass()

    missing = [key for key in _REQUIRED if not os.environ.get(key)]
    if missing:
        detail = "".join(
            f"\n  {name}: {pass_failures[name]}"
            for name in missing
            if name in pass_failures
        )
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}{detail}"
        )

    return Config(
        client_id=os.environ.get("CLIENT_ID") or "",
        client_secret=os.environ.get("CLIENT_SECRET") or None,
        access_token=os.environ.get("ACCESS_TOKEN") or "",
        refresh_token=os.environ.get("REFRESH_TOKEN") or "",
        user_id=os.environ.get("USER_ID") or "",
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        output_dir=_resolve_output_dir(env_dir),
        taxonomy_file=resolve_taxonomy_file(env_dir),
    )
