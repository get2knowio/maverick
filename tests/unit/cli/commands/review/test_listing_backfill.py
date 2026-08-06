"""Failing tests for the ``run_list`` suggestion back-fill wiring (T013,
User Story 2, 055-learned-assumption-resolution).

Contract:
``specs/055-learned-assumption-resolution/contracts/entry-row-suggestion.md``
("``maverick review --list [--json]``") — before building rows, ``run_list``
back-fills suggestions for entries that have none stored: load the runway
corpus once (not per-entry), evaluate, persist hits. Store unavailable
degrades to a silent skip (debug log only, no warning to the user). JSON
payload shape is unchanged otherwise (rows carry the new ``suggestion`` /
``auto_resolved`` keys). The human table marks suggestion-carrying entries
with a ``suggested`` marker; no new columns.

This module tests the CALL-SITE wiring in
``src/maverick/cli/commands/review/listing.py`` only — not
``backfill_suggestions``'s own internals (that's
``tests/unit/assumptions/test_suggestions.py``, a sibling T011 task), and not
``entry_to_dict``'s projection logic in isolation (that's
``tests/unit/assumptions/test_suggestion_projection.py``, T012).

**RED-STATE MARKER**: at the time this module was written,
``src/maverick/assumptions/suggestions.py`` has no ``backfill_suggestions``
function, and ``AssumptionReportEntry`` (``src/maverick/assumptions/
models.py``) has no ``suggestion`` field. Every test here is expected to FAIL
until:

* T016 (parallel task) wires a module-level
  ``from maverick.assumptions.suggestions import backfill_suggestions``
  import into ``listing.py`` and calls it from ``run_list`` before
  ``_filter_and_sort`` — assumed signature
  ``backfill_suggestions(client, store, entries) -> list[AssumptionReportEntry]``
  per research.md R5 (async; loads corpus once; persists hits; never
  replaces an existing stored suggestion; silently no-ops when the runway
  store is uninitialized).
* T015 adds ``AssumptionReportEntry.suggestion`` / ``.auto_resolved``.
* T017 extends ``entry_to_dict`` with the ``suggestion`` / ``auto_resolved``
  keys.
* A parallel listing change teaches ``_render_table`` to mark
  suggestion-carrying rows.

Do not "fix" these tests by loosening the assertions — later tasks close
the gaps these tests pin down.

Mirrors the mocking style of ``tests/unit/cli/commands/test_review_listing.py``
(053-assumption-review-console): patch ``BeadClient.verify_available`` and
``maverick.assumptions.ledger.report_entries``, drive everything through the
``review`` Click command via ``CliRunner`` (never real ``bd``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from maverick.assumptions.models import (
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    AssumptionRecord,
    AssumptionReportEntry,
    Severity,
)
from maverick.cli.commands.review import review

#: Import path the tests patch. ``listing.py`` imports
#: ``backfill_suggestions`` function-locally (every other maverick import in
#: that module is deferred too, to keep Click command registration cheap),
#: so the definition site is the only stable patch target — there is no
#: module-level name in ``listing`` to look up.
_BACKFILL_PATCH_TARGET = "maverick.assumptions.suggestions.backfill_suggestions"


@dataclass(frozen=True)
class _FakeSuggestion:
    """Stand-in for the not-yet-existing ``Suggestion`` dataclass (T015).

    Shape mirrors ``contracts/entry-row-suggestion.md``'s example object,
    but this module intentionally does NOT import the real ``Suggestion``
    class — that class doesn't exist yet, and importing it at module scope
    would turn every test here into a collection error instead of a clean
    per-test failure. Only truthiness / attribute presence matters for
    these call-site tests.
    """

    resolution: str = "Yes — AsyncRetrying, 3 attempts"
    resolution_type: str = "answered"
    source_entry_id: str = "dea-old"
    source_spec: str = "052-conditional-landing"
    resolved_at: str = "2026-08-06T14:03:22+00:00"
    confidence: float = 0.87
    computed_at: str = "2026-08-07T10:11:12+00:00"


def _entry(
    bead_id: str,
    *,
    owner_spec: str,
    severity: Severity,
    status: str = STATUS_OPEN,
    question: str = "Q?",
    suggestion: object | None = None,
) -> AssumptionReportEntry:
    record = AssumptionRecord(
        bead_id=bead_id,
        question=question,
        adopted_answer="A.",
        alternatives=(),
        severity=severity,
        severity_defaulted=False,
        status=status,
        owner_spec=owner_spec,
        source_bead="src-1",
        change_ids=(),
        is_legacy=False,
    )
    kwargs: dict[str, object] = {
        "record": record,
        "final_answer": "A." if status == STATUS_ANSWERED else None,
        "waived_by": "alice" if status == STATUS_WAIVED else None,
        "waived_at": "2026-01-01T00:00:00+00:00" if status == STATUS_WAIVED else None,
        "waive_reason": "n/a" if status == STATUS_WAIVED else None,
        "reconcile_status": None,
        "reconciled_answer": None,
        "reconcile_change_id": None,
        "reconcile_reason": None,
        "pending_reconcile": False,
    }
    if suggestion is not None:
        # `AssumptionReportEntry` has no `suggestion` field until T015 —
        # this is expected to raise `TypeError: unexpected keyword
        # argument 'suggestion'` until then. That's the intended red
        # state for tests that pass `suggestion=...`.
        kwargs["suggestion"] = suggestion
    return AssumptionReportEntry(**kwargs)  # type: ignore[arg-type]


def _patched(
    entries: tuple[AssumptionReportEntry, ...],
    *,
    available: bool = True,
    backfill_mock: AsyncMock | None = None,
):
    """Same trio of patches as ``test_review_listing.py``'s ``_patched``,
    plus a patch for the new ``backfill_suggestions`` call site.

    *backfill_mock*, when omitted, defaults to an identity no-op
    (``AsyncMock(return_value=entries)``) — the "store unavailable" /
    "nothing to back-fill" behavior, since this module tests wiring, not
    ``backfill_suggestions``'s own degradation logic.
    """
    mock = backfill_mock if backfill_mock is not None else AsyncMock(return_value=entries)
    return (
        patch(
            "maverick.beads.client.BeadClient.verify_available",
            new=AsyncMock(return_value=available),
        ),
        patch(
            "maverick.assumptions.ledger.report_entries",
            new=AsyncMock(return_value=entries),
        ),
        patch(_BACKFILL_PATCH_TARGET, new=mock),
        mock,
    )


class TestBackfillScopedToOpenSelection:
    def test_backfill_skips_entries_the_listing_dropped(self) -> None:
        """``run_list`` must back-fill only the OPEN entries it is about to
        render, never the whole ``report_entries`` sweep.

        Back-fill is a write path — it persists each hit with a
        ``bd set-state`` call. ``review --list`` is a read verb the
        ``maverick-review`` skill runs on every sweep, and an
        answered/waived entry will never be reviewed again, so evaluating
        rows the caller filtered out would write suggestions onto closed
        beads for no one's benefit.
        """
        entries = (
            _entry("dea-1", owner_spec="049-spec", severity=Severity.HIGH, status=STATUS_OPEN),
            _entry(
                "dea-2", owner_spec="049-spec", severity=Severity.MEDIUM, status=STATUS_ANSWERED
            ),
            _entry("dea-3", owner_spec="049-spec", severity=Severity.LOW, status=STATUS_WAIVED),
        )
        verify, sweep, backfill_patch, mock_backfill = _patched(entries)
        runner = CliRunner()
        with verify, sweep, backfill_patch:
            result = runner.invoke(review, ["--list", "--json"])

        assert result.exit_code == 0, result.output
        mock_backfill.assert_awaited_once()

        call_args, call_kwargs = mock_backfill.call_args
        candidates = list(call_args) + list(call_kwargs.values())
        entries_arg = next((c for c in candidates if isinstance(c, (list, tuple))), None)
        assert entries_arg is not None, (
            f"expected a list/tuple of entries among backfill_suggestions's call "
            f"args, got args={call_args!r} kwargs={call_kwargs!r}"
        )
        passed_ids = {e.record.bead_id for e in entries_arg}
        # Only the open entry — the answered/waived pair the default status
        # filter drops must never reach the write path.
        assert passed_ids == {"dea-1"}

        data = json.loads(result.output)
        ids = [row["bead_id"] for row in data["result"]["entries"]]
        assert ids == ["dea-1"]

    def test_backfill_not_called_when_selection_is_all_closed(self) -> None:
        """An explicitly answered/waived-only listing does zero writes."""
        entries = (
            _entry(
                "dea-2", owner_spec="049-spec", severity=Severity.MEDIUM, status=STATUS_ANSWERED
            ),
            _entry("dea-3", owner_spec="049-spec", severity=Severity.LOW, status=STATUS_WAIVED),
        )
        verify, sweep, backfill_patch, mock_backfill = _patched(entries)
        runner = CliRunner()
        with verify, sweep, backfill_patch:
            result = runner.invoke(
                review, ["--list", "--status", "answered", "--status", "waived", "--json"]
            )

        assert result.exit_code == 0, result.output
        mock_backfill.assert_not_awaited()

        data = json.loads(result.output)
        ids = sorted(row["bead_id"] for row in data["result"]["entries"])
        assert ids == ["dea-2", "dea-3"]


class TestBackfillLoadedOncePerListing:
    def test_backfill_invoked_exactly_once_regardless_of_entry_count(self) -> None:
        """Corpus load is a per-listing-call concern, not per-entry — the
        call-site contract is that ``run_list`` calls
        ``backfill_suggestions`` exactly once per invocation, however many
        entries ``report_entries`` returns."""
        entries = tuple(
            _entry(f"dea-{i}", owner_spec="049-spec", severity=Severity.MEDIUM) for i in range(5)
        )
        verify, sweep, backfill_patch, mock_backfill = _patched(entries)
        runner = CliRunner()
        with verify, sweep, backfill_patch:
            result = runner.invoke(review, ["--list", "--json"])

        assert result.exit_code == 0, result.output
        assert mock_backfill.await_count == 1


class TestStoreUnavailableSkipsSilently:
    """FR-021 / research R11: a missing/uninitialized runway store degrades
    to a debug-logged no-op — never a warning surfaced to the user, and
    never a failed command. Modeled here by a ``backfill_suggestions`` mock
    that behaves as the real function would when the store is unavailable:
    it returns the entries unchanged.
    """

    def test_json_mode_completes_normally(self) -> None:
        entries = (
            _entry("dea-1", owner_spec="049-spec", severity=Severity.HIGH, status=STATUS_OPEN),
        )
        verify, sweep, backfill_patch, mock_backfill = _patched(entries)
        runner = CliRunner()
        with verify, sweep, backfill_patch:
            result = runner.invoke(review, ["--list", "--json"])

        assert result.exit_code == 0, result.output
        mock_backfill.assert_awaited_once()
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "warning" not in result.output.lower()

    def test_human_mode_completes_normally_without_warning(self) -> None:
        entries = (
            _entry("dea-1", owner_spec="049-spec", severity=Severity.HIGH, status=STATUS_OPEN),
        )
        verify, sweep, backfill_patch, mock_backfill = _patched(entries)
        runner = CliRunner()
        with verify, sweep, backfill_patch:
            result = runner.invoke(review, ["--list"])

        assert result.exit_code == 0, result.output
        mock_backfill.assert_awaited_once()
        assert "dea-1" in result.output
        assert "warning" not in result.output.lower()


class TestHumanTableMarksSuggestedEntries:
    """Contract: "Human table: entries with a suggestion show a `suggested`
    marker; no new columns beyond that." Constructing an entry with a
    non-None ``suggestion`` requires the not-yet-existing field from T015
    — this is the documented red state (see module docstring).
    """

    def test_entry_with_suggestion_shows_marker(self) -> None:
        entries = (
            _entry(
                "dea-1",
                owner_spec="049-spec",
                severity=Severity.HIGH,
                status=STATUS_OPEN,
                suggestion=_FakeSuggestion(),
            ),
        )
        verify, sweep, backfill_patch, _mock_backfill = _patched(entries)
        runner = CliRunner()
        with verify, sweep, backfill_patch:
            result = runner.invoke(review, ["--list"])

        assert result.exit_code == 0, result.output
        assert "suggested" in result.output.lower()

    def test_entry_without_suggestion_has_no_marker(self) -> None:
        entries = (
            _entry("dea-1", owner_spec="049-spec", severity=Severity.HIGH, status=STATUS_OPEN),
        )
        verify, sweep, backfill_patch, _mock_backfill = _patched(entries)
        runner = CliRunner()
        with verify, sweep, backfill_patch:
            result = runner.invoke(review, ["--list"])

        assert result.exit_code == 0, result.output
        assert "suggested" not in result.output.lower()


class TestJsonRowsCarrySuggestionKeys:
    """End-to-end through ``run_list`` — the projection function itself is
    covered by ``tests/unit/assumptions/test_suggestion_projection.py``
    (T012); this pins down that the listing command surface actually
    delivers the new keys to the caller.
    """

    def test_rows_carry_suggestion_and_auto_resolved_keys(self) -> None:
        entries = (
            _entry("dea-1", owner_spec="049-spec", severity=Severity.HIGH, status=STATUS_OPEN),
            _entry("dea-2", owner_spec="049-spec", severity=Severity.MEDIUM, status=STATUS_OPEN),
        )
        verify, sweep, backfill_patch, _mock_backfill = _patched(entries)
        runner = CliRunner()
        with verify, sweep, backfill_patch:
            result = runner.invoke(review, ["--list", "--json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        rows = data["result"]["entries"]
        assert rows, "expected at least one row in the JSON envelope"
        for row in rows:
            assert "suggestion" in row, f"row missing 'suggestion' key: {row!r}"
            assert "auto_resolved" in row, f"row missing 'auto_resolved' key: {row!r}"
