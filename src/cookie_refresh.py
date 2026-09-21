"""Refresh the twitter-cli session cookies from the browser you already use.

The manual alternative is a DevTools export on every session rotation. This
module exists to delete that step: Firefox already holds a live, logged-in
`auth_token`/`ct0` pair and keeps it alive for months, so copying that pair into
`pass` on demand costs nothing and adds no second browser session to maintain.

Scope is the load-bearing safety property, not the mechanism. `unofficial_client`
refuses to run without explicit credentials precisely to stop upstream
`twitter-cli` from scanning every browser cookie jar it can find. This module is
the consented inverse of that scan: one named profile, two named cookies, on an
explicit user action or a failed fetch, never as a silent ambient fallback.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from src.config import _PASS_ENTRIES

_PROFILE_ENV = "X_BOOKMARKS_FIREFOX_PROFILE"
_FIREFOX_ROOT = Path.home() / ".mozilla" / "firefox"
_COOKIE_DB = "cookies.sqlite"
# Firefox writes through a WAL. Copying the journal alongside the database is
# what makes a cookie rotated moments ago visible; the main file alone can lag.
_DB_SIDECARS = ("-wal", "-shm")
_HOSTS = (".x.com", "x.com", ".twitter.com", "twitter.com")

# Cookie name -> `pass` entry, sourced from the config map so the vault paths
# have exactly one definition.
_COOKIE_TO_PASS = {
    "auth_token": _PASS_ENTRIES["TWITTER_AUTH_TOKEN"],
    "ct0": _PASS_ENTRIES["TWITTER_CT0"],
}
_COOKIE_TO_ENV = {
    "auth_token": "TWITTER_AUTH_TOKEN",
    "ct0": "TWITTER_CT0",
}


class CookieRefreshError(RuntimeError):
    """The cookie pair could not be read or stored."""


def find_firefox_profile(env: dict[str, str] | None = None) -> Path:
    """Locate the Firefox profile holding the cookie store.

    Prefers an explicit override so a non-default profile, or a Snap/Flatpak
    install, does not require code changes.

    Raises:
        CookieRefreshError: no profile with a cookie database was found.
    """
    env = os.environ if env is None else env
    override = (env.get(_PROFILE_ENV) or "").strip()
    if override:
        candidate = Path(override).expanduser()
        if not (candidate / _COOKIE_DB).exists():
            raise CookieRefreshError(
                f"{_PROFILE_ENV} points at {candidate}, which has no {_COOKIE_DB}."
            )
        return candidate

    # `default-release` is the profile a normal desktop Firefox actually browses
    # with; a bare `default` is usually the vestigial one and has no session.
    for pattern in ("*.default-release", "*.default*", "*"):
        for candidate in sorted(_FIREFOX_ROOT.glob(pattern)):
            if (candidate / _COOKIE_DB).exists():
                return candidate

    raise CookieRefreshError(
        f"No Firefox profile with a {_COOKIE_DB} under {_FIREFOX_ROOT}. "
        f"Set {_PROFILE_ENV} to the profile directory."
    )


def read_cookies(profile_dir: Path) -> dict[str, str]:
    """Read `auth_token` and `ct0` out of a Firefox cookie store.

    The database is copied before reading because Firefox holds it open; querying
    the live file risks `database is locked` against a running browser.

    Raises:
        CookieRefreshError: the store is unreadable, or either cookie is absent,
            which in practice means the profile is logged out of X.
    """
    source = profile_dir / _COOKIE_DB
    if not source.exists():
        raise CookieRefreshError(f"No cookie database at {source}.")

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / _COOKIE_DB
        shutil.copy2(source, target)
        for suffix in _DB_SIDECARS:
            sidecar = source.with_name(_COOKIE_DB + suffix)
            if sidecar.exists():
                shutil.copy2(sidecar, target.with_name(_COOKIE_DB + suffix))

        placeholders = ",".join("?" * len(_HOSTS))
        names = tuple(_COOKIE_TO_PASS)
        try:
            connection = sqlite3.connect(target)
            try:
                rows = connection.execute(
                    "SELECT name, value FROM moz_cookies "
                    f"WHERE host IN ({placeholders}) "
                    f"AND name IN ({','.join('?' * len(names))})",
                    (*_HOSTS, *names),
                ).fetchall()
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise CookieRefreshError(f"Could not read {source}: {exc}") from exc

    cookies = {name: value for name, value in rows if value}
    missing = [name for name in names if not cookies.get(name)]
    if missing:
        raise CookieRefreshError(
            f"{', '.join(missing)} not found in {profile_dir.name}. "
            "Log into x.com in that Firefox profile and try again."
        )
    return cookies


def store_in_pass(cookies: dict[str, str]) -> None:
    """Write the cookie pair into the `pass` vault.

    Values are piped on stdin rather than passed as arguments so they never
    appear in a process listing or a shell history file.

    Raises:
        CookieRefreshError: `pass` is unavailable or an insert failed.
    """
    if shutil.which("pass") is None:
        raise CookieRefreshError("`pass` is not installed, so there is nowhere to store the cookies.")

    for name, entry in _COOKIE_TO_PASS.items():
        result = subprocess.run(
            ["pass", "insert", "-m", "-f", entry],
            input=cookies[name] + "\n",
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise CookieRefreshError(
                f"`pass insert {entry}` exited {result.returncode}: "
                f"{(result.stderr or '').strip()}"
            )


def refresh_cookies(env: dict[str, str] | None = None) -> dict[str, str]:
    """Copy the live cookie pair from Firefox into `pass` and the environment.

    The environment is updated too so the caller that triggered the refresh can
    retry in-process without paying another vault decryption.
    """
    env = os.environ if env is None else env
    profile = find_firefox_profile(env)
    cookies = read_cookies(profile)
    store_in_pass(cookies)
    for name, variable in _COOKIE_TO_ENV.items():
        env[variable] = cookies[name]
    return cookies


def main() -> None:
    """Console entry point: `x-bookmarks-refresh-cookies`."""
    try:
        profile = find_firefox_profile()
        cookies = read_cookies(profile)
        store_in_pass(cookies)
    except CookieRefreshError as exc:
        print(f"Cookie refresh failed: {exc}")
        sys.exit(1)

    print(f"Read x.com session from Firefox profile {profile.name}")
    for name, entry in _COOKIE_TO_PASS.items():
        print(f"  {name} ({len(cookies[name])} chars) -> pass {entry}")


if __name__ == "__main__":
    main()
