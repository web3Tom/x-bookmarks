import sqlite3
import subprocess

import pytest

from src.cookie_refresh import (
    CookieRefreshError,
    find_firefox_profile,
    read_cookies,
    refresh_cookies,
    store_in_pass,
)


def _make_cookie_db(profile_dir, rows):
    """Build a minimal Firefox cookie store with the columns we query."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(profile_dir / "cookies.sqlite")
    connection.execute(
        "CREATE TABLE moz_cookies (id INTEGER PRIMARY KEY, name TEXT, value TEXT, host TEXT)"
    )
    connection.executemany(
        "INSERT INTO moz_cookies (name, value, host) VALUES (?, ?, ?)", rows
    )
    connection.commit()
    connection.close()
    return profile_dir


@pytest.fixture
def logged_in_profile(tmp_path):
    return _make_cookie_db(
        tmp_path / "abc.default-release",
        [
            ("auth_token", "a" * 40, ".x.com"),
            ("ct0", "c" * 160, ".x.com"),
            ("guest_id", "irrelevant", ".x.com"),
            ("sessionid", "someone-elses", ".example.com"),
        ],
    )


class TestFindFirefoxProfile:
    def test_env_override_wins(self, logged_in_profile):
        found = find_firefox_profile({"X_BOOKMARKS_FIREFOX_PROFILE": str(logged_in_profile)})
        assert found == logged_in_profile

    def test_env_override_without_cookie_db_is_rejected(self, tmp_path):
        """A pointed-at profile that cannot work must say so, rather than
        silently falling back to a different account's session."""
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(CookieRefreshError, match="no cookies.sqlite"):
            find_firefox_profile({"X_BOOKMARKS_FIREFOX_PROFILE": str(empty)})

    def test_missing_root_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.cookie_refresh._FIREFOX_ROOT", tmp_path / "nope")
        with pytest.raises(CookieRefreshError, match="No Firefox profile"):
            find_firefox_profile({})

    def test_prefers_default_release_over_bare_default(self, tmp_path, monkeypatch):
        """A bare `default` profile is usually the vestigial one Firefox never
        browses with, so picking it would read a logged-out cookie store."""
        _make_cookie_db(tmp_path / "zzz.default", [("auth_token", "stale", ".x.com")])
        release = _make_cookie_db(
            tmp_path / "aaa.default-release", [("auth_token", "live", ".x.com")]
        )
        monkeypatch.setattr("src.cookie_refresh._FIREFOX_ROOT", tmp_path)

        assert find_firefox_profile({}) == release


class TestReadCookies:
    def test_reads_the_pair(self, logged_in_profile):
        cookies = read_cookies(logged_in_profile)
        assert cookies == {"auth_token": "a" * 40, "ct0": "c" * 160}

    def test_ignores_other_hosts(self, tmp_path):
        """Scope is the safety property: a cookie of the same name on another
        site must never be harvested."""
        profile = _make_cookie_db(
            tmp_path / "p.default-release",
            [
                ("auth_token", "wrong-site", ".example.com"),
                ("ct0", "wrong-site", ".example.com"),
            ],
        )
        with pytest.raises(CookieRefreshError, match="auth_token, ct0"):
            read_cookies(profile)

    def test_logged_out_profile_names_the_fix(self, tmp_path):
        profile = _make_cookie_db(
            tmp_path / "p.default-release", [("guest_id", "v", ".x.com")]
        )
        with pytest.raises(CookieRefreshError, match="Log into x.com"):
            read_cookies(profile)

    def test_blank_value_counts_as_missing(self, tmp_path):
        """Firefox leaves an emptied cookie row behind on logout; treating it as
        present would store a blank token and fail far from the cause."""
        profile = _make_cookie_db(
            tmp_path / "p.default-release",
            [("auth_token", "", ".x.com"), ("ct0", "c" * 160, ".x.com")],
        )
        with pytest.raises(CookieRefreshError, match="auth_token"):
            read_cookies(profile)

    def test_does_not_read_the_live_database(self, logged_in_profile, monkeypatch):
        """Firefox holds cookies.sqlite open. Querying it in place risks
        `database is locked` against a running browser, so a copy is required."""
        opened = []
        real_connect = sqlite3.connect

        def _record(path, *args, **kwargs):
            opened.append(str(path))
            return real_connect(path, *args, **kwargs)

        monkeypatch.setattr("src.cookie_refresh.sqlite3.connect", _record)
        read_cookies(logged_in_profile)

        assert opened
        assert not any(str(logged_in_profile) in path for path in opened)

    def test_missing_database_raises(self, tmp_path):
        with pytest.raises(CookieRefreshError, match="No cookie database"):
            read_cookies(tmp_path / "absent")


class TestStoreInPass:
    def test_values_go_through_stdin_not_argv(self, monkeypatch):
        """A secret in argv is visible in `ps` output to every user on the box."""
        calls = []

        def _run(cmd, **kwargs):
            calls.append((cmd, kwargs.get("input")))
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr("src.cookie_refresh.shutil.which", lambda n: "/usr/bin/pass")
        monkeypatch.setattr("src.cookie_refresh.subprocess.run", _run)

        # Values deliberately share no substring with the vault entry paths, so
        # the argv check below cannot pass by accident.
        store_in_pass({"auth_token": "SEKRIT9", "ct0": "SEKRIT4"})

        entries = [cmd[-1] for cmd, _ in calls]
        assert entries == ["x/auth-token", "x/ct0"]
        assert [payload.strip() for _, payload in calls] == ["SEKRIT9", "SEKRIT4"]
        assert not any("SEKRIT" in " ".join(cmd) for cmd, _ in calls)

    def test_missing_pass_binary_raises(self, monkeypatch):
        monkeypatch.setattr("src.cookie_refresh.shutil.which", lambda n: None)
        with pytest.raises(CookieRefreshError, match="not installed"):
            store_in_pass({"auth_token": "t", "ct0": "c"})

    def test_failed_insert_raises(self, monkeypatch):
        monkeypatch.setattr("src.cookie_refresh.shutil.which", lambda n: "/usr/bin/pass")
        monkeypatch.setattr(
            "src.cookie_refresh.subprocess.run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "gpg: no secret key"),
        )
        with pytest.raises(CookieRefreshError, match="no secret key"):
            store_in_pass({"auth_token": "t", "ct0": "c"})


class TestRefreshCookies:
    def test_updates_environment_for_an_in_process_retry(
        self, logged_in_profile, monkeypatch
    ):
        """The caller that triggered the refresh retries immediately, so the new
        pair has to be visible without a second vault decryption."""
        monkeypatch.setattr("src.cookie_refresh.store_in_pass", lambda cookies: None)
        env = {"X_BOOKMARKS_FIREFOX_PROFILE": str(logged_in_profile)}

        refresh_cookies(env)

        assert env["TWITTER_AUTH_TOKEN"] == "a" * 40
        assert env["TWITTER_CT0"] == "c" * 160
