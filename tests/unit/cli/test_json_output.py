"""Unit tests for the JSON envelope machinery (feature 053).

Covers `ErrorKind`, `JsonEnvelope`/`JsonError`, `emit_json`, and
`json_error_handler` per `specs/053-assumption-review-console/contracts/
error-envelope.md`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maverick.assumptions.errors import AssumptionLedgerError
from maverick.cli.context import ExitCode
from maverick.cli.json_output import (
    ErrorKind,
    JsonEnvelope,
    JsonError,
    emit_json,
    json_error_handler,
)
from maverick.exceptions import (
    REASON_CONCURRENT_RUN,
    REASON_DIRTY_WORKING_COPY,
    REASON_LOCKED,
    JjConflictError,
    JjError,
    MaverickError,
    WorkflowError,
)
from maverick.exceptions.beads import BeadQueryError

# =============================================================================
# ErrorKind registry
# =============================================================================


class TestErrorKind:
    """The 12-value ErrorKind registry is frozen per the contract."""

    def test_exact_registry_values(self) -> None:
        expected = {
            "validation",
            "not-found",
            "already-resolved",
            "bd-unavailable",
            "dirty-working-copy",
            "concurrent-run",
            "locked",
            "frontier-blocked",
            "confirmation-required",
            "curation-failed",
            "vcs",
            "internal",
        }
        actual = {member.value for member in ErrorKind}
        assert actual == expected

    def test_is_str_enum(self) -> None:
        assert ErrorKind.VALIDATION == "validation"
        assert isinstance(ErrorKind.VALIDATION, str)


# =============================================================================
# JsonEnvelope / JsonError shape
# =============================================================================


class TestJsonEnvelope:
    def test_success_shape(self) -> None:
        envelope = JsonEnvelope.success("review.list", {"entries": []})
        data = envelope.to_dict()

        assert data == {
            "schema_version": 1,
            "verb": "review.list",
            "ok": True,
            "result": {"entries": []},
        }

    def test_success_omits_error_key(self) -> None:
        envelope = JsonEnvelope.success("review.list", {"entries": []})
        data = envelope.to_dict()

        assert "error" not in data

    def test_failure_shape(self) -> None:
        envelope = JsonEnvelope.failure(
            "review.answer",
            ErrorKind.NOT_FOUND,
            "no such entry",
            details={"bead_id": "bd-1"},
        )
        data = envelope.to_dict()

        assert data == {
            "schema_version": 1,
            "verb": "review.answer",
            "ok": False,
            "error": {
                "kind": "not-found",
                "message": "no such entry",
                "details": {"bead_id": "bd-1"},
            },
        }

    def test_failure_omits_result_key(self) -> None:
        envelope = JsonEnvelope.failure("review.answer", ErrorKind.NOT_FOUND, "no such entry")
        data = envelope.to_dict()

        assert "result" not in data

    def test_failure_default_details_empty_dict(self) -> None:
        envelope = JsonEnvelope.failure("review.answer", ErrorKind.INTERNAL, "boom")
        data = envelope.to_dict()

        assert data["error"]["details"] == {}

    def test_schema_version_is_one(self) -> None:
        success = JsonEnvelope.success("review.list", {})
        failure = JsonEnvelope.failure("review.list", ErrorKind.INTERNAL, "x")

        assert success.schema_version == 1
        assert failure.schema_version == 1

    def test_json_error_dataclass_fields(self) -> None:
        err = JsonError(kind=ErrorKind.VCS, message="jj failed")
        assert err.kind == ErrorKind.VCS
        assert err.message == "jj failed"
        assert err.details == {}

    def test_result_and_error_mutually_exclusive_in_dict(self) -> None:
        success = JsonEnvelope.success("review.list", {"a": 1})
        failure = JsonEnvelope.failure("review.list", ErrorKind.INTERNAL, "x")

        success_dict = success.to_dict()
        failure_dict = failure.to_dict()

        assert ("result" in success_dict) and ("error" not in success_dict)
        assert ("error" in failure_dict) and ("result" not in failure_dict)


# =============================================================================
# emit_json — stdout stream discipline
# =============================================================================


class TestEmitJson:
    def test_writes_single_parseable_document(self, capsys: pytest.CaptureFixture[str]) -> None:
        envelope = JsonEnvelope.success("review.list", {"entries": [1, 2, 3]})
        emit_json(envelope)

        captured = capsys.readouterr()
        assert captured.err == ""
        parsed = json.loads(captured.out)
        assert parsed == envelope.to_dict()

    def test_no_ansi_or_markup_leaks(self, capsys: pytest.CaptureFixture[str]) -> None:
        envelope = JsonEnvelope.failure("review.list", ErrorKind.INTERNAL, "boom")
        emit_json(envelope)

        captured = capsys.readouterr()
        assert "\x1b[" not in captured.out
        assert "[red]" not in captured.out

    def test_emoji_shortcodes_survive_verbatim(self, capsys: pytest.CaptureFixture[str]) -> None:
        """`:name:` runs in free text must not be rewritten to unicode emoji.

        Rich substitutes emoji shortcodes by default. Assumption questions,
        adopted answers and waive reasons are agent- and human-authored and
        routinely contain `:key:`-shaped runs; silently rewriting them
        corrupts the ledger round-trip (`review --answer "<adopted_answer>"`
        writes the mutated text straight back).
        """
        question = "Should we key off the :key: field or :id: for lookup?"
        emit_json(JsonEnvelope.success("review.list", {"question": question}))

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["result"]["question"] == question

    def test_free_text_round_trips_unchanged(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Nothing in the transport may mutate a string value."""
        payload = {
            "markup": "[red]not a style tag[/red]",
            "emoji": ":rocket: :100: :-)",
            "unicode": "café — naïve … ✓",
            "control": "tab\there\nnewline",
            "long": "x" * 500,  # must not be wrapped
        }
        emit_json(JsonEnvelope.success("review.list", payload))

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["result"] == payload

    def test_exactly_one_trailing_newline(self, capsys: pytest.CaptureFixture[str]) -> None:
        envelope = JsonEnvelope.success("review.list", {"x": 1})
        emit_json(envelope)

        captured = capsys.readouterr()
        # Exactly one document: stripping one trailing newline gives valid JSON
        # with no further newlines embedded (single-line-safe JSON output).
        assert captured.out.count("\n") == 1
        assert captured.out.endswith("\n")
        json.loads(captured.out.strip())


# =============================================================================
# json_error_handler — exception → envelope mapping
# =============================================================================


class TestJsonErrorHandler:
    def test_keyboard_interrupt_emits_no_document(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc_info, json_error_handler("review.list"):
            raise KeyboardInterrupt()

        assert exc_info.value.code == ExitCode.INTERRUPTED
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_workflow_error_dirty_working_copy(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info, json_error_handler("reconcile.run"):
            raise WorkflowError(
                "working copy is not clean — commit or discard changes before running reconcile"
            )

        assert exc_info.value.code == ExitCode.FAILURE
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["ok"] is False
        assert data["error"]["kind"] == "dirty-working-copy"

    def test_workflow_error_concurrent_run(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit), json_error_handler("reconcile.run"):
            raise WorkflowError("cannot run reconcile while a fly run is in progress")

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["error"]["kind"] == "concurrent-run"

    def test_workflow_error_locked(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit), json_error_handler("reconcile.run"):
            raise WorkflowError(
                "another reconcile run is already in progress (lockfile held by a live process)"
            )

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["error"]["kind"] == "locked"

    def test_workflow_error_other_message_falls_back(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit), json_error_handler("reconcile.run"):
            raise WorkflowError("something else entirely broke")

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["error"]["kind"] == "internal"

    @pytest.mark.parametrize(
        ("reason", "expected_kind"),
        [
            (REASON_DIRTY_WORKING_COPY, "dirty-working-copy"),
            (REASON_CONCURRENT_RUN, "concurrent-run"),
            (REASON_LOCKED, "locked"),
        ],
    )
    def test_typed_reason_wins_over_prose(
        self,
        reason: str,
        expected_kind: str,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Reworded messages must keep classifying — that's the point of `reason_code`.

        The message below matches none of the legacy prose markers, so a
        substring-only implementation would classify all three as
        ``internal``.
        """
        with pytest.raises(SystemExit), json_error_handler("reconcile.run"):
            raise WorkflowError("a completely reworded precondition message", reason_code=reason)

        data = json.loads(capsys.readouterr().out)
        assert data["error"]["kind"] == expected_kind

    def test_unknown_reason_falls_back_to_prose_markers(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit), json_error_handler("reconcile.run"):
            raise WorkflowError("working copy is not clean", reason_code="not-a-known-reason")

        data = json.loads(capsys.readouterr().out)
        assert data["error"]["kind"] == "dirty-working-copy"

    def test_reconcile_workflow_raises_carry_typed_reasons(self) -> None:
        """The workflow's own raises set `reason_code`, not just prose (regression).

        Without this, rewording ``workflow.py``'s precondition messages
        would silently break the skill's remediation branches with no test
        failure — the exact fragility the typed reason removes.
        """
        source = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "maverick"
            / "workflows"
            / "reconcile"
            / "workflow.py"
        ).read_text(encoding="utf-8")
        for constant in (
            "REASON_DIRTY_WORKING_COPY",
            "REASON_CONCURRENT_RUN",
            "REASON_LOCKED",
        ):
            assert f"reason_code={constant}" in source

    def test_jj_error_maps_to_vcs_with_operation_detail(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit), json_error_handler("reconcile.run"):
            raise JjError("jj describe failed", command="describe")

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["error"]["kind"] == "vcs"
        assert data["error"]["details"] == {"operation": "describe"}

    def test_jj_conflict_error_subclass_maps_to_vcs(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit), json_error_handler("reconcile.run"):
            raise JjConflictError("conflicts detected", command="rebase")

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["error"]["kind"] == "vcs"
        assert data["error"]["details"] == {"operation": "rebase"}

    def test_jj_error_without_command_has_no_operation_detail(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit), json_error_handler("reconcile.run"):
            raise JjError("something failed")

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["error"]["kind"] == "vcs"
        assert data["error"]["details"] == {}

    def test_bead_query_error_maps_to_bd_unavailable(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit), json_error_handler("review.list"):
            raise BeadQueryError("bd query failed", query="ready")

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["error"]["kind"] == "bd-unavailable"

    def test_assumption_ledger_error_maps_to_validation(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit), json_error_handler("review.answer"):
            raise AssumptionLedgerError("answer text must not be empty")

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["error"]["kind"] == "validation"

    def test_maverick_error_catch_all_maps_to_internal(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit), json_error_handler("review.list"):
            raise MaverickError("something maverick-specific broke")

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["error"]["kind"] == "internal"

    def test_bare_exception_maps_to_internal(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info, json_error_handler("review.list"):
            raise ValueError("unexpected")

        assert exc_info.value.code == ExitCode.FAILURE
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["ok"] is False
        assert data["error"]["kind"] == "internal"

    def test_failure_envelope_carries_verb(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit), json_error_handler("land.run"):
            raise MaverickError("boom")

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["verb"] == "land.run"

    def test_raises_system_exit_with_failure_code(self) -> None:
        with pytest.raises(SystemExit) as exc_info, json_error_handler("review.list"):
            raise MaverickError("boom")

        assert exc_info.value.code == ExitCode.FAILURE

    def test_success_case_no_exception(self) -> None:
        result = None
        with json_error_handler("review.list"):
            result = "success"

        assert result == "success"
