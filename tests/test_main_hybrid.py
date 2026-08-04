"""CLI-level tests for the hybrid backfill and enrichment flags.

The invariant these protect: the unofficial path is read-only and opt-in.
Deletion must never travel over the cookie/GraphQL mechanism, because the
official DELETE has documented idempotency and error semantics that the
private endpoint does not, and a bad delete is unrecoverable.
"""

from __future__ import annotations

import pytest

from src.main import _parse_args


class TestDefaults:
    def test_hybrid_features_are_off_by_default(self):
        """A bare `x-bookmarks` run must behave exactly as before this feature."""
        args = _parse_args([])
        assert args.backfill_unofficial is False
        assert args.enrich_titles is False
        assert args.backfill_max is None


class TestUnofficialFlagGuards:
    def test_unofficial_cannot_be_combined_with_removal(self, capsys):
        """Deletes stay on OAuth. Permanently.

        Reproducing safe deletes over a private GraphQL surface is far
        higher-stakes than read-only fetching, so the combination is refused at
        parse time rather than guarded deeper in the call stack.
        """
        with pytest.raises(SystemExit):
            _parse_args([
                "--backfill-unofficial",
                "--remove-synthesized-bookmarks",
            ])
        assert "remove" in capsys.readouterr().err.lower()

    def test_backfill_max_requires_unofficial(self, capsys):
        with pytest.raises(SystemExit):
            _parse_args(["--backfill-max", "500"])
        assert "--backfill-unofficial" in capsys.readouterr().err

    def test_backfill_max_rejects_non_positive(self, capsys):
        with pytest.raises(SystemExit):
            _parse_args(["--backfill-unofficial", "--backfill-max", "0"])
        assert "greater than zero" in capsys.readouterr().err

    def test_valid_unofficial_invocation_parses(self):
        args = _parse_args(["--backfill-unofficial", "--backfill-max", "2000"])
        assert args.backfill_unofficial is True
        assert args.backfill_max == 2000


class TestEnrichFlag:
    def test_enrich_titles_is_independent_of_unofficial(self):
        """Enrichment carries no account risk, so it must be usable on the
        default OAuth path without opting into anything unsanctioned."""
        args = _parse_args(["--enrich-titles"])
        assert args.enrich_titles is True
        assert args.backfill_unofficial is False

    def test_enrich_titles_combines_with_removal_is_rejected(self, capsys):
        """Removal mode never fetches or categorizes, so enrichment is a no-op
        there; accepting it silently would imply work that never happens."""
        with pytest.raises(SystemExit):
            _parse_args(["--enrich-titles", "--remove-synthesized-bookmarks"])
        assert "enrich" in capsys.readouterr().err.lower()
