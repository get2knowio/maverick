"""Human-mode CLI tests for ``maverick notify`` (T013) per
specs/054-assumption-batch-scheduler/contracts/cli-notify-json.md's
"Human-mode output (no --json)" section.

Same mocking style as ``tests/unit/cli/commands/test_notify_json.py`` — see
that file's module docstring for the rationale (``evaluate()``/
``NtfyDeliverer`` stubbed; ``BeadClient``/``report_entries`` run for real
against a mocked ``bd``).
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest
from click.testing import CliRunner, Result

from maverick.assumptions.models import Severity
from maverick.assumptions.schedule.deliver import DeliveryFailedError
from maverick.assumptions.schedule.models import (
    BatchSummary,
    DecisionKind,
    DeliveryDecision,
    EvaluationOutcome,
    SkipDecision,
    SkipReason,
    WindowOccurrence,
)
from maverick.assumptions.schedule.state import DeliveryRecord, DeliveryState, WindowDecisionRecord
from maverick.cli.context import ExitCode
from maverick.main import cli

_CONFIGURED_YAML = """
assumptions:
  schedule:
    windows: ["09:00"]

notifications:
  enabled: true
  topic: test-topic
"""

_UNCONFIGURED_YAML = """
notifications:
  enabled: true
  topic: test-topic
"""


def _setup(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch, *, yaml_text: str = _CONFIGURED_YAML
) -> None:
    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)
    (temp_dir / "maverick.yaml").write_text(yaml_text)


def _stub_preconditions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("maverick.cli.commands.notify.bd_ready_reason", lambda cwd: None)
    monkeypatch.setattr(
        "maverick.beads.client.BeadClient.verify_available",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "maverick.beads.client.BeadClient.query",
        AsyncMock(return_value=[]),
    )


def _stub_evaluate(
    monkeypatch: pytest.MonkeyPatch,
    outcome: EvaluationOutcome,
    *,
    captured: list[datetime] | None = None,
) -> None:
    def _fake_evaluate(
        entries: object, schedule: object, state: object, now: datetime
    ) -> EvaluationOutcome:
        if captured is not None:
            captured.append(now)
        return outcome

    monkeypatch.setattr("maverick.cli.commands.notify.evaluate", _fake_evaluate)


class _FakeDeliverer:
    calls: list[tuple[DecisionKind, BatchSummary]] = []
    fail: bool = False

    def __init__(self, *, server: str, topic: str) -> None:
        self.server = server
        self.topic = topic

    async def __aenter__(self) -> _FakeDeliverer:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def deliver(self, kind: DecisionKind, summary: BatchSummary) -> None:
        type(self).calls.append((kind, summary))
        if type(self).fail:
            raise DeliveryFailedError(
                "ntfy delivery failed after 3 attempts", kind=kind, status_code=503
            )


def _stub_deliverer(monkeypatch: pytest.MonkeyPatch, *, fail: bool) -> None:
    _FakeDeliverer.calls = []
    _FakeDeliverer.fail = fail
    monkeypatch.setattr("maverick.cli.commands.notify.NtfyDeliverer", _FakeDeliverer)


def _summary() -> BatchSummary:
    return BatchSummary(
        counts={Severity.HIGH: 0, Severity.MEDIUM: 2, Severity.LOW: 3},
        owner_specs=("054-assumption-batch-scheduler",),
        oldest_age_hours=11.5,
        review_invocation="maverick review --list --status open",
    )


def _occurrence() -> WindowOccurrence:
    return WindowOccurrence(
        date=date(2026, 8, 5), window="09:00", due_at=datetime(2026, 8, 5, 9, 0, tzinfo=UTC)
    )


def _delivery_decision() -> DeliveryDecision:
    return DeliveryDecision(
        kind=DecisionKind.WINDOW_BATCH,
        entry_ids=("mav-abc", "mav-def"),
        summary=_summary(),
        occurrence=_occurrence(),
        rule="window 09:00 due",
    )


def _outcome_one_delivery() -> EvaluationOutcome:
    prior_state = DeliveryState(updated_at="2026-08-05T08:00:00Z")
    decision = _delivery_decision()
    window_decisions = {
        "2026-08-05/09:00": WindowDecisionRecord(
            outcome="delivered",
            decided_at="2026-08-05T09:00:05Z",
            entry_ids=list(decision.entry_ids),
            rule=decision.rule,
        )
    }
    deliveries = [
        DeliveryRecord(
            kind="window-batch",
            delivered_at="2026-08-05T09:00:05Z",
            trigger="2026-08-05/09:00",
            entry_ids=list(decision.entry_ids),
            summary={
                "counts": {"high": 0, "medium": 2, "low": 3},
                "owner_specs": ["054-assumption-batch-scheduler"],
                "oldest_age_hours": 11.5,
                "review_invocation": "maverick review --list --status open",
            },
        )
    ]
    state_after = prior_state.model_copy(
        update={
            "updated_at": "2026-08-05T09:00:05Z",
            "window_decisions": window_decisions,
            "deliveries": deliveries,
        }
    )
    return EvaluationOutcome(
        deliveries=(decision,), skips=(), auto_waives=(), state_after=state_after
    )


def _outcome_nothing_due() -> EvaluationOutcome:
    prior_state = DeliveryState(updated_at="2026-08-05T08:00:00Z")
    skip = SkipDecision(
        reason=SkipReason.NOT_YET_DUE,
        occurrence=_occurrence(),
        entry_ids=(),
        rule="window 09:00 not yet due (due 2026-08-05T09:00:00+00:00)",
    )
    return EvaluationOutcome(deliveries=(), skips=(skip,), auto_waives=(), state_after=prior_state)


def _invoke(cli_runner: CliRunner) -> Result:
    return cli_runner.invoke(cli, ["notify"])


class TestUnconfiguredNoOp:
    def test_single_line_no_op_exit_zero(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch, yaml_text=_UNCONFIGURED_YAML)

        result = _invoke(cli_runner)

        assert result.exit_code == ExitCode.SUCCESS
        assert "not configured" in result.output
        assert "assumptions.schedule" in result.output
        assert not (temp_dir / ".maverick" / "notify").exists()


class TestNothingDue:
    def test_prints_nothing_due(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        _stub_preconditions(monkeypatch)
        _stub_evaluate(monkeypatch, _outcome_nothing_due())
        _stub_deliverer(monkeypatch, fail=False)

        result = _invoke(cli_runner)

        assert result.exit_code == ExitCode.SUCCESS
        assert "Nothing due." in result.output


class TestDeliveryCompletionLine:
    def test_prints_delivered_completion_line(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        _stub_preconditions(monkeypatch)
        _stub_evaluate(monkeypatch, _outcome_one_delivery())
        _stub_deliverer(monkeypatch, fail=False)

        result = _invoke(cli_runner)

        assert result.exit_code == ExitCode.SUCCESS
        assert "✓" in result.output  # ✓
        assert "Delivered window batch" in result.output
        assert "2 medium" in result.output
        assert "3 low" in result.output
        assert "11.5h" in result.output
        assert "09:00 window" in result.output


def _tzdata_available() -> bool:
    """Whether this machine's tz database can resolve a DST-observing zone."""
    try:
        ZoneInfo("America/New_York")
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False
    return True


@pytest.mark.skipif(not _tzdata_available(), reason="tz database unavailable on this machine")
class TestInjectedClock:
    """The evaluation clock handed to ``evaluate()`` must carry a real IANA
    zone when the machine has one — ``datetime.now().astimezone()`` yields a
    fixed offset, which silently defeats ``evaluate()``'s DST handling for any
    occurrence on the far side of a transition."""

    def test_injected_now_carries_resolvable_zone(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TZ", "America/New_York")
        _setup(temp_dir, monkeypatch)
        _stub_preconditions(monkeypatch)
        captured: list[datetime] = []
        _stub_evaluate(monkeypatch, _outcome_nothing_due(), captured=captured)
        _stub_deliverer(monkeypatch, fail=False)

        result = _invoke(cli_runner)

        assert result.exit_code == ExitCode.SUCCESS
        assert len(captured) == 1
        now = captured[0]
        assert isinstance(now.tzinfo, ZoneInfo)
        assert now.tzinfo.key == "America/New_York"
        # The regression proper: the bound zone's offset varies across DST.
        assert (
            datetime(2026, 3, 7, 10, tzinfo=now.tzinfo).utcoffset()
            != datetime(2026, 3, 9, 10, tzinfo=now.tzinfo).utcoffset()
        )


class TestDeliveryFailure:
    def test_prints_failure_mark_and_warning_exit_one(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        _stub_preconditions(monkeypatch)
        _stub_evaluate(monkeypatch, _outcome_one_delivery())
        _stub_deliverer(monkeypatch, fail=True)

        result = _invoke(cli_runner)

        assert result.exit_code == ExitCode.FAILURE
        assert "✗" in result.output  # ✗
        assert "Delivery failed" in result.output
        assert "Warning:" in result.output
