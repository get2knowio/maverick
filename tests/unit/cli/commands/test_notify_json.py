"""CLI contract tests for ``maverick notify --json`` (T013, T022) per
specs/054-assumption-batch-scheduler/contracts/cli-notify-json.md.

House pattern (mirrors ``test_reconcile_json.py`` / ``test_review_json.py``):
mock ``BeadClient.verify_available``/``.query`` so no real ``bd`` invocation
occurs, invoke via ``cli_runner``. ``report_entries`` runs for real against
the mocked ``BeadClient`` (returns an empty ledger sweep in every test here);
the decision engine itself (``evaluate()``) is stubbed with a canned
``EvaluationOutcome`` — window/quiet-hours/DST evaluation logic is already
covered by ``tests/unit/assumptions/schedule/test_evaluate_*.py`` (T010/T011),
so these tests only need to prove the CLI's effects layer (delivery,
write-after-success state persistence, envelope shape, error mapping).
``acquire_lock``/``load_state``/``save_state``/``release_lock`` run for real
against a temp cwd so the persisted-state assertions are genuine.

T022 (US3, cron-hardening) adds one exception to the "``evaluate()`` is
stubbed" rule: ``TestRealEvaluateIdempotence`` lets it run for real across
two actual CLI invocations against the same persisted state, because
idempotence across process restarts can't be proven against a canned
outcome — see that class's docstring.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner, Result

from maverick.assumptions.errors import AssumptionLedgerError
from maverick.assumptions.schedule.deliver import DeliveryFailedError
from maverick.assumptions.schedule.models import (
    AutoWaiveDecision,
    BatchSummary,
    DecisionKind,
    DeliveryDecision,
    EvaluationOutcome,
    SkipDecision,
    SkipReason,
    WindowOccurrence,
)
from maverick.assumptions.schedule.state import (
    DeliveryRecord,
    DeliveryState,
    EntryTrackingRecord,
    WindowDecisionRecord,
)
from maverick.beads.models import BeadDetails, BeadSummary
from maverick.cli.common import BD_MISSING
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

_NOTIFICATIONS_DISABLED_YAML = """
assumptions:
  schedule:
    windows: ["09:00"]

notifications:
  enabled: false
  topic: test-topic
"""

_NOTIFICATIONS_NO_TOPIC_YAML = """
assumptions:
  schedule:
    windows: ["09:00"]

notifications:
  enabled: true
"""

_UNCONFIGURED_YAML = """
notifications:
  enabled: true
  topic: test-topic
"""


def _write_config(temp_dir: Path, yaml_text: str) -> None:
    (temp_dir / "maverick.yaml").write_text(yaml_text)


def _stub_preconditions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass real bd/ledger I/O: bd is ready, the ledger sweep is empty."""
    monkeypatch.setattr("maverick.cli.commands.notify.bd_ready_reason", lambda cwd: None)
    monkeypatch.setattr(
        "maverick.beads.client.BeadClient.verify_available",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "maverick.beads.client.BeadClient.query",
        AsyncMock(return_value=[]),
    )


def _stub_evaluate(monkeypatch: pytest.MonkeyPatch, outcome: EvaluationOutcome) -> None:
    def _fake_evaluate(
        entries: object, schedule: object, state: object, now: object
    ) -> EvaluationOutcome:
        return outcome

    monkeypatch.setattr("maverick.cli.commands.notify.evaluate", _fake_evaluate)


class _FakeDeliverer:
    """Fake ``NtfyDeliverer`` replacement: records calls, optionally raises."""

    #: Class-level call log so the factory function signature matches
    #: ``NtfyDeliverer.__init__`` while still being inspectable by tests.
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


def _stub_deliverer(monkeypatch: pytest.MonkeyPatch, *, fail: bool) -> type[_FakeDeliverer]:
    _FakeDeliverer.calls = []
    _FakeDeliverer.fail = fail
    monkeypatch.setattr("maverick.cli.commands.notify.NtfyDeliverer", _FakeDeliverer)
    return _FakeDeliverer


def _summary(**overrides: object) -> BatchSummary:
    from maverick.assumptions.models import Severity

    defaults: dict[str, object] = {
        "counts": {Severity.HIGH: 0, Severity.MEDIUM: 2, Severity.LOW: 3},
        "owner_specs": ("054-assumption-batch-scheduler",),
        "oldest_age_hours": 11.5,
        "review_invocation": "maverick review --list --status open",
    }
    defaults.update(overrides)
    return BatchSummary(**defaults)  # type: ignore[arg-type]


def _occurrence() -> WindowOccurrence:
    return WindowOccurrence(
        date=date(2026, 8, 5), window="09:00", due_at=datetime(2026, 8, 5, 9, 0, tzinfo=UTC)
    )


def _delivery_decision(*, entry_ids: tuple[str, ...] = ("mav-abc", "mav-def")) -> DeliveryDecision:
    return DeliveryDecision(
        kind=DecisionKind.WINDOW_BATCH,
        entry_ids=entry_ids,
        summary=_summary(),
        occurrence=_occurrence(),
        rule="window 09:00 due",
    )


def _state_after_one_delivery(
    prior_state: DeliveryState, decision: DeliveryDecision
) -> DeliveryState:
    window_decisions = dict(prior_state.window_decisions)
    window_decisions["2026-08-05/09:00"] = WindowDecisionRecord(
        outcome="delivered",
        decided_at="2026-08-05T09:00:05Z",
        entry_ids=list(decision.entry_ids),
        rule=decision.rule,
    )
    deliveries = [
        *prior_state.deliveries,
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
        ),
    ]
    return prior_state.model_copy(
        update={
            "updated_at": "2026-08-05T09:00:05Z",
            "window_decisions": window_decisions,
            "deliveries": deliveries,
        }
    )


def _outcome_one_delivery() -> EvaluationOutcome:
    prior_state = DeliveryState(updated_at="2026-08-05T08:00:00Z")
    decision = _delivery_decision()
    return EvaluationOutcome(
        deliveries=(decision,),
        skips=(),
        auto_waives=(),
        state_after=_state_after_one_delivery(prior_state, decision),
    )


def _summary_high_only() -> BatchSummary:
    from maverick.assumptions.models import Severity

    return _summary(counts={Severity.HIGH: 1, Severity.MEDIUM: 0, Severity.LOW: 0})


def _outcome_one_interrupt() -> EvaluationOutcome:
    """A single high-severity interrupt decision (T021), analogous to
    :func:`_outcome_one_delivery` for window batches — ``occurrence`` is
    ``None`` (interrupts aren't window-scoped) and the state mutation lands
    on ``entry_tracking``, not ``window_decisions``."""
    prior_state = DeliveryState(updated_at="2026-08-05T08:00:00Z")
    decision = DeliveryDecision(
        kind=DecisionKind.INTERRUPT,
        entry_ids=("mav-hi",),
        summary=_summary_high_only(),
        occurrence=None,
        rule="high-severity interrupt due",
    )
    state_after = prior_state.model_copy(
        update={
            "updated_at": "2026-08-05T09:00:05Z",
            "entry_tracking": {
                "mav-hi": EntryTrackingRecord(
                    first_seen="2026-08-05T08:00:00Z",
                    severity="high",
                    interrupt_delivered_at="2026-08-05T09:00:05Z",
                )
            },
            "deliveries": [
                DeliveryRecord(
                    kind="interrupt",
                    delivered_at="2026-08-05T09:00:05Z",
                    trigger="high-severity interrupt due",
                    entry_ids=["mav-hi"],
                    summary={
                        "counts": {"high": 1, "medium": 0, "low": 0},
                        "owner_specs": ["054-assumption-batch-scheduler"],
                        "oldest_age_hours": 11.5,
                        "review_invocation": "maverick review --list --status open",
                    },
                )
            ],
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


def _setup(
    temp_dir: Path, monkeypatch: pytest.MonkeyPatch, *, yaml_text: str = _CONFIGURED_YAML
) -> None:
    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)
    _write_config(temp_dir, yaml_text)


def _invoke(cli_runner: CliRunner, *args: str) -> Result:
    return cli_runner.invoke(cli, ["notify", *args])


class TestUnconfiguredNoOp:
    def test_run_exits_success_ok_true(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch, yaml_text=_UNCONFIGURED_YAML)

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["verb"] == "notify.run"
        assert data["result"]["configured"] is False
        assert data["result"]["skipped"] == "not-configured"
        assert data["result"]["deliveries"] == []
        assert data["result"]["skips"] == []
        assert not (temp_dir / ".maverick" / "notify").exists()

    def test_dry_run_uses_dry_run_verb(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch, yaml_text=_UNCONFIGURED_YAML)

        result = _invoke(cli_runner, "--dry-run", "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["verb"] == "notify.dry-run"
        assert data["result"]["dry_run"] is True


class TestNotificationsUnusableValidation:
    def test_notifications_disabled_names_the_key(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch, yaml_text=_NOTIFICATIONS_DISABLED_YAML)

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["error"]["kind"] == "validation"
        assert "notifications.enabled" in data["error"]["message"]

    def test_missing_topic_names_the_key(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch, yaml_text=_NOTIFICATIONS_NO_TOPIC_YAML)

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["error"]["kind"] == "validation"
        assert "notifications.topic" in data["error"]["message"]
        assert not (temp_dir / ".maverick" / "notify").exists()


class TestBdUnavailable:
    def test_bd_ready_reason_missing(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        monkeypatch.setattr("maverick.cli.commands.notify.bd_ready_reason", lambda cwd: BD_MISSING)

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["error"]["kind"] == "bd-unavailable"
        assert data["verb"] == "notify.run"
        assert not (temp_dir / ".maverick" / "notify").exists()

    def test_verify_available_false(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        monkeypatch.setattr("maverick.cli.commands.notify.bd_ready_reason", lambda cwd: None)
        monkeypatch.setattr(
            "maverick.beads.client.BeadClient.verify_available",
            AsyncMock(return_value=False),
        )

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["error"]["kind"] == "bd-unavailable"


class TestSuccessfulDelivery:
    def test_single_window_batch_delivers_and_persists_state(
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

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["result"]["configured"] is True
        assert data["result"]["skipped"] is None
        assert len(data["result"]["deliveries"]) == 1
        delivery = data["result"]["deliveries"][0]
        assert delivery["kind"] == "window-batch"
        assert delivery["trigger"] == "2026-08-05/09:00"
        assert delivery["entry_ids"] == ["mav-abc", "mav-def"]
        assert delivery["summary"]["counts"] == {"high": 0, "medium": 2, "low": 3}
        assert delivery["rule"] == "window 09:00 due"
        assert _FakeDeliverer.calls  # ntfy was actually invoked

        state_path = temp_dir / ".maverick" / "notify" / "state.json"
        assert state_path.is_file()
        persisted = json.loads(state_path.read_text())
        assert persisted["window_decisions"]["2026-08-05/09:00"]["outcome"] == "delivered"
        assert len(persisted["deliveries"]) == 1

    def test_nothing_due_reports_skips_and_persists_state(
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

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["result"]["deliveries"] == []
        assert len(data["result"]["skips"]) == 1
        assert data["result"]["skips"][0]["reason"] == "not-yet-due"
        assert not _FakeDeliverer.calls


class TestInterruptDelivery:
    """T021: interrupt decisions flow through the same generic delivery
    loop as window batches, but priority/title (urgent, per
    contracts/ntfy-payload.md) are deliver.py's concern — proven directly
    in ``test_deliver.py``. This class proves the CLI wires the interrupt
    ``kind`` through to ``NtfyDeliverer.deliver`` unchanged and persists
    ``interrupt_delivered_at`` correctly (success and failure)."""

    def test_interrupt_delivers_and_persists_interrupt_delivered_at(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        _stub_preconditions(monkeypatch)
        outcome = _outcome_one_interrupt()
        _stub_evaluate(monkeypatch, outcome)
        deliverer_cls = _stub_deliverer(monkeypatch, fail=False)

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["ok"] is True
        deliveries = data["result"]["deliveries"]
        assert len(deliveries) == 1
        assert deliveries[0]["kind"] == "interrupt"
        assert deliveries[0]["entry_ids"] == ["mav-hi"]
        assert deliveries[0]["trigger"] == "high-severity interrupt due"

        # The kind reached NtfyDeliverer.deliver unchanged.
        assert deliverer_cls.calls == [(DecisionKind.INTERRUPT, outcome.deliveries[0].summary)]

        state_path = temp_dir / ".maverick" / "notify" / "state.json"
        persisted = json.loads(state_path.read_text())
        assert persisted["entry_tracking"]["mav-hi"]["interrupt_delivered_at"] is not None

    def test_failed_interrupt_reverts_interrupt_delivered_at(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """FR-012: a failed interrupt push must not persist
        ``interrupt_delivered_at`` — the entry stays due at the next
        evaluation, mirroring the window-batch failure invariant in
        ``TestDeliveryFailedExhausted`` below."""
        _setup(temp_dir, monkeypatch)
        _stub_preconditions(monkeypatch)
        _stub_evaluate(monkeypatch, _outcome_one_interrupt())
        _stub_deliverer(monkeypatch, fail=True)

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["error"]["kind"] == "delivery-failed"
        assert data["error"]["details"]["failed_deliveries"][0]["kind"] == "interrupt"

        state_path = temp_dir / ".maverick" / "notify" / "state.json"
        assert state_path.is_file()
        persisted = json.loads(state_path.read_text())
        assert persisted["entry_tracking"]["mav-hi"]["interrupt_delivered_at"] is None
        assert persisted["deliveries"] == []


class TestDeliveryFailedExhausted:
    def test_exit_1_delivery_failed_kind_and_state_excludes_failure(
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

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["error"]["kind"] == "delivery-failed"
        assert len(data["error"]["details"]["failed_deliveries"]) == 1
        assert data["error"]["details"]["failed_deliveries"][0]["kind"] == "window-batch"

        # FR-012: a failed decision's mutations must not be persisted — the
        # occurrence stays undecided (and therefore due again next time).
        state_path = temp_dir / ".maverick" / "notify" / "state.json"
        assert state_path.is_file()
        persisted = json.loads(state_path.read_text())
        assert "2026-08-05/09:00" not in persisted["window_decisions"]
        assert persisted["deliveries"] == []


class TestPartialSuccessAcrossDecisions:
    """T022/T024: a run with more than one due decision (e.g. a mixed
    ledger's window batch *and* interrupt) must record each independently
    — one failure must not roll back an unrelated decision's success."""

    def test_one_of_two_due_decisions_fails_persists_the_success_independently(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        _stub_preconditions(monkeypatch)

        batch_decision = _delivery_decision(entry_ids=("mav-med",))
        interrupt_decision = DeliveryDecision(
            kind=DecisionKind.INTERRUPT,
            entry_ids=("mav-hi",),
            summary=_summary_high_only(),
            occurrence=None,
            rule="high-severity interrupt due",
        )
        prior_state = DeliveryState(updated_at="2026-08-05T08:00:00Z")
        state_after = prior_state.model_copy(
            update={
                "updated_at": "2026-08-05T09:00:05Z",
                "window_decisions": {
                    "2026-08-05/09:00": WindowDecisionRecord(
                        outcome="delivered",
                        decided_at="2026-08-05T09:00:05Z",
                        entry_ids=list(batch_decision.entry_ids),
                        rule=batch_decision.rule,
                    )
                },
                "entry_tracking": {
                    "mav-hi": EntryTrackingRecord(
                        first_seen="2026-08-05T08:00:00Z",
                        severity="high",
                        interrupt_delivered_at="2026-08-05T09:00:05Z",
                    )
                },
                "deliveries": [
                    DeliveryRecord(
                        kind="window-batch",
                        delivered_at="2026-08-05T09:00:05Z",
                        trigger="2026-08-05/09:00",
                        entry_ids=list(batch_decision.entry_ids),
                        summary={
                            "counts": {"high": 0, "medium": 2, "low": 3},
                            "owner_specs": ["054-assumption-batch-scheduler"],
                            "oldest_age_hours": 11.5,
                            "review_invocation": "maverick review --list --status open",
                        },
                    ),
                    DeliveryRecord(
                        kind="interrupt",
                        delivered_at="2026-08-05T09:00:05Z",
                        trigger="high-severity interrupt due",
                        entry_ids=["mav-hi"],
                        summary={
                            "counts": {"high": 1, "medium": 0, "low": 0},
                            "owner_specs": ["054-assumption-batch-scheduler"],
                            "oldest_age_hours": 11.5,
                            "review_invocation": "maverick review --list --status open",
                        },
                    ),
                ],
            }
        )
        outcome = EvaluationOutcome(
            deliveries=(batch_decision, interrupt_decision),
            skips=(),
            auto_waives=(),
            state_after=state_after,
        )
        _stub_evaluate(monkeypatch, outcome)

        class _SelectivelyFailingDeliverer:
            """Fails only the interrupt; the window batch always succeeds."""

            calls: list[DecisionKind] = []

            def __init__(self, *, server: str, topic: str) -> None:
                pass

            async def __aenter__(self) -> _SelectivelyFailingDeliverer:
                return self

            async def __aexit__(self, *exc_info: object) -> None:
                return None

            async def deliver(self, kind: DecisionKind, summary: BatchSummary) -> None:
                type(self).calls.append(kind)
                if kind == DecisionKind.INTERRUPT:
                    raise DeliveryFailedError(
                        "ntfy delivery failed after 3 attempts", kind=kind, status_code=503
                    )

        _SelectivelyFailingDeliverer.calls = []
        monkeypatch.setattr(
            "maverick.cli.commands.notify.NtfyDeliverer", _SelectivelyFailingDeliverer
        )

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["error"]["kind"] == "delivery-failed"
        assert len(data["error"]["details"]["failed_deliveries"]) == 1
        assert data["error"]["details"]["failed_deliveries"][0]["kind"] == "interrupt"
        # Both decisions were attempted independently — the loop never
        # short-circuits on the first failure.
        assert _SelectivelyFailingDeliverer.calls == [
            DecisionKind.WINDOW_BATCH,
            DecisionKind.INTERRUPT,
        ]

        state_path = temp_dir / ".maverick" / "notify" / "state.json"
        persisted = json.loads(state_path.read_text())
        # The succeeded window batch is fully, individually persisted...
        assert persisted["window_decisions"]["2026-08-05/09:00"]["outcome"] == "delivered"
        assert len(persisted["deliveries"]) == 1
        assert persisted["deliveries"][0]["kind"] == "window-batch"
        # ...while the failed interrupt's marker is reverted, exactly as in
        # the single-decision-failure case.
        assert persisted["entry_tracking"]["mav-hi"]["interrupt_delivered_at"] is None


class TestAutoWaiveEffects:
    """T026/T028: ``AutoWaiveDecision``s execute via
    ``assumptions.ledger.waive`` (research R10), recording a
    :class:`~maverick.assumptions.schedule.state.TerminalOutcome` in
    persisted state; ``--dry-run`` never touches bd (contract: zero bd
    calls)."""

    def _outcome_one_auto_waive(self) -> EvaluationOutcome:
        prior_state = DeliveryState(updated_at="2026-08-05T08:00:00Z")
        state_after = prior_state.model_copy(
            update={
                "updated_at": "2026-08-05T09:00:05Z",
                "entry_tracking": {
                    "mav-lo": EntryTrackingRecord(
                        first_seen="2026-08-01T00:00:00Z",
                        severity="low",
                    )
                },
            }
        )
        decision = AutoWaiveDecision(
            entry_id="mav-lo",
            reason_text="auto-waived by schedule policy after 168h: stale, accepted risk",
        )
        return EvaluationOutcome(
            deliveries=(), skips=(), auto_waives=(decision,), state_after=state_after
        )

    def test_real_run_calls_ledger_waive_and_records_terminal_outcome(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        _stub_preconditions(monkeypatch)
        _stub_evaluate(monkeypatch, self._outcome_one_auto_waive())
        _stub_deliverer(monkeypatch, fail=False)

        waive_calls: list[dict[str, object]] = []

        async def _fake_waive(
            client: object, *, bead_id: str, reason: str, waived_by: str
        ) -> None:
            waive_calls.append({"bead_id": bead_id, "reason": reason, "waived_by": waived_by})

        monkeypatch.setattr("maverick.cli.commands.notify.ledger_waive", _fake_waive)

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["ok"] is True

        assert len(waive_calls) == 1
        assert waive_calls[0]["bead_id"] == "mav-lo"
        assert waive_calls[0]["waived_by"] == "maverick-scheduler"
        assert "168h" in str(waive_calls[0]["reason"])
        assert "stale, accepted risk" in str(waive_calls[0]["reason"])

        assert len(data["result"]["auto_waives"]) == 1
        assert data["result"]["auto_waives"][0]["entry_id"] == "mav-lo"

        state_path = temp_dir / ".maverick" / "notify" / "state.json"
        persisted = json.loads(state_path.read_text())
        terminal = persisted["entry_tracking"]["mav-lo"]["terminal"]
        assert terminal["kind"] == "auto-waived"
        assert (
            terminal["detail"] == "auto-waived by schedule policy after 168h: stale, accepted risk"
        )

    def test_waive_failure_does_not_abort_the_run_or_record_terminal(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A bd failure waiving one entry must not crash the run
        (Principle III) and must not fabricate a terminal outcome for an
        entry that was never actually waived (FR-016)."""
        _setup(temp_dir, monkeypatch)
        _stub_preconditions(monkeypatch)
        _stub_evaluate(monkeypatch, self._outcome_one_auto_waive())
        _stub_deliverer(monkeypatch, fail=False)

        async def _failing_waive(
            client: object, *, bead_id: str, reason: str, waived_by: str
        ) -> None:
            raise AssumptionLedgerError(f"Failed to waive {bead_id}: bd exploded")

        monkeypatch.setattr("maverick.cli.commands.notify.ledger_waive", _failing_waive)

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["result"]["auto_waives"] == []

        state_path = temp_dir / ".maverick" / "notify" / "state.json"
        persisted = json.loads(state_path.read_text())
        assert persisted["entry_tracking"]["mav-lo"].get("terminal") is None

    def test_dry_run_reports_would_waive_with_zero_bd_calls(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        _stub_preconditions(monkeypatch)
        _stub_evaluate(monkeypatch, self._outcome_one_auto_waive())
        _stub_deliverer(monkeypatch, fail=False)

        waive_calls: list[object] = []

        async def _fake_waive(*args: object, **kwargs: object) -> None:
            waive_calls.append((args, kwargs))

        monkeypatch.setattr("maverick.cli.commands.notify.ledger_waive", _fake_waive)

        result = _invoke(cli_runner, "--dry-run", "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["verb"] == "notify.dry-run"
        assert data["result"]["dry_run"] is True
        assert len(data["result"]["auto_waives"]) == 1
        assert data["result"]["auto_waives"][0]["entry_id"] == "mav-lo"

        assert not waive_calls
        assert not (temp_dir / ".maverick" / "notify").exists()


class TestDryRunZeroSideEffects:
    def test_dry_run_reports_would_deliver_with_zero_side_effects(
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

        result = _invoke(cli_runner, "--dry-run", "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["verb"] == "notify.dry-run"
        assert data["result"]["dry_run"] is True
        assert len(data["result"]["deliveries"]) == 1

        # Zero ntfy calls, zero state writes (contract).
        assert not _FakeDeliverer.calls
        assert not (temp_dir / ".maverick" / "notify").exists()


class TestConcurrentEvaluationBenignSkip:
    def test_held_lock_is_ok_true_skipped_exit_zero(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        _stub_preconditions(monkeypatch)
        monkeypatch.setattr(
            "maverick.cli.commands.notify.acquire_lock", AsyncMock(return_value=False)
        )
        # `evaluate`/deliverer must never be reached — no evaluation is
        # performed at all on a benign lock skip (research R7).
        _stub_evaluate(monkeypatch, _outcome_one_delivery())
        _stub_deliverer(monkeypatch, fail=False)

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["result"]["skipped"] == "concurrent-evaluation"
        assert data["result"]["deliveries"] == []
        assert not _FakeDeliverer.calls

    def test_held_lock_from_real_live_pid_leaves_lockfile_untouched(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Same contract as above, but against a genuine lockfile carrying
        this test process's own (guaranteed-live) pid, rather than a
        mocked ``acquire_lock`` — proves the real pid-liveness check, not
        just the CLI's handling of a canned ``False`` return."""
        _setup(temp_dir, monkeypatch)
        _stub_preconditions(monkeypatch)
        _stub_evaluate(monkeypatch, _outcome_one_delivery())
        _stub_deliverer(monkeypatch, fail=False)

        lock_path = temp_dir / ".maverick" / "notify" / "lock"
        lock_path.parent.mkdir(parents=True)
        lock_path.write_text(str(os.getpid()), encoding="utf-8")

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["result"]["skipped"] == "concurrent-evaluation"
        assert data["result"]["deliveries"] == []
        assert not _FakeDeliverer.calls
        # A benign skip never touches the lock it lost the race for.
        assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())
        assert not (temp_dir / ".maverick" / "notify" / "state.json").exists()

    def test_stale_lock_from_dead_pid_is_reclaimed_and_evaluation_proceeds(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """research R7 is about *live*-pid contention specifically; a lock
        naming a dead pid (crashed prior run, machine reboot) must not
        wedge the command forever — ``acquire_lock`` reclaims it and this
        run evaluates and delivers normally."""
        _setup(temp_dir, monkeypatch)
        _stub_preconditions(monkeypatch)
        _stub_evaluate(monkeypatch, _outcome_one_delivery())
        _stub_deliverer(monkeypatch, fail=False)

        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        dead_pid = proc.pid
        proc.wait()  # reap the child; dead_pid is now guaranteed not alive

        lock_path = temp_dir / ".maverick" / "notify" / "lock"
        lock_path.parent.mkdir(parents=True)
        lock_path.write_text(str(dead_pid), encoding="utf-8")

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["result"]["skipped"] is None
        assert len(data["result"]["deliveries"]) == 1
        assert _FakeDeliverer.calls  # evaluation proceeded for real
        # Released cleanly after this run completed.
        assert not lock_path.exists()


# --- T022 (US3): ledger-read failure -----------------------------------------


class TestLedgerReadFailure:
    """spec.md edge case: "Ledger unreadable at evaluation time: the run
    fails with a clear diagnostic; it must not record deliveries or mutate
    state based on a partial read." Mirrors research R11's mapping
    (``AssumptionLedgerError`` -> ``validation``, via the existing
    ``json_error_handler`` dispatch)."""

    def test_ledger_read_failure_maps_to_validation_with_zero_state_mutation(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        monkeypatch.setattr("maverick.cli.commands.notify.bd_ready_reason", lambda cwd: None)
        monkeypatch.setattr(
            "maverick.beads.client.BeadClient.verify_available",
            AsyncMock(return_value=True),
        )
        monkeypatch.setattr(
            "maverick.cli.commands.notify.report_entries",
            AsyncMock(side_effect=AssumptionLedgerError("Failed to query task beads: boom")),
        )
        _stub_deliverer(monkeypatch, fail=False)

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["error"]["kind"] == "validation"
        assert not _FakeDeliverer.calls
        # No state file was ever created: the failure happens before
        # `load_state`/`save_state` are reached (the ledger sweep is the
        # very first thing the evaluate-deliver-save sequence does).
        assert not (temp_dir / ".maverick" / "notify" / "state.json").exists()
        # The lock is released on the way out, not left held.
        assert not (temp_dir / ".maverick" / "notify" / "lock").exists()


# --- T022 (US3): real evaluate() idempotence across process restarts --------


def _open_medium_bead_details(
    bead_id: str, *, owner_spec: str = "054-assumption-batch-scheduler"
) -> BeadDetails:
    """A minimal, valid ``assumption``-labeled bead: real enough for
    ``ledger.report_entries()``/``evaluate()`` to process, deliberately
    inert on everything ``evaluate()`` doesn't look at (question/answer
    text)."""
    return BeadDetails(
        id=bead_id,
        title=f"Assumption: {bead_id}",
        description=(
            "## Question\n\nQ?\n\n"
            "## Adopted Answer\n\nA.\n\n"
            "## Alternatives Considered\n\n(none)\n\n"
            "## Context\n\nSource bead: mav-source — Source\n"
        ),
        bead_type="task",
        status="open",
        labels=["assumption"],
        state={
            "assumption_severity": "medium",
            "assumption_status": "open",
            "assumption_owner_spec": owner_spec,
            "source_bead": "mav-source",
        },
    )


def _stub_real_ledger_sweep(monkeypatch: pytest.MonkeyPatch, bead_ids: list[str]) -> None:
    """Wire ``BeadClient.query``/``.show`` so ``report_entries()`` — and
    therefore ``evaluate()`` — runs for real, unlike :func:`_stub_preconditions`
    (which returns an empty ledger sweep, requiring ``evaluate()`` itself to
    be stubbed via :func:`_stub_evaluate` in every other test in this file)."""
    monkeypatch.setattr("maverick.cli.commands.notify.bd_ready_reason", lambda cwd: None)
    monkeypatch.setattr(
        "maverick.beads.client.BeadClient.verify_available",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "maverick.beads.client.BeadClient.query",
        AsyncMock(
            return_value=[BeadSummary(id=bid, title=bid, status="open") for bid in bead_ids]
        ),
    )
    details_by_id = {bid: _open_medium_bead_details(bid) for bid in bead_ids}

    async def _fake_show(self: object, bead_id: str) -> BeadDetails:
        return details_by_id[bead_id]

    monkeypatch.setattr("maverick.beads.client.BeadClient.show", _fake_show)


#: ``"00:00"`` is always due for *any* wall-clock ``now`` on the day the
#: test runs (no quiet hours configured) — this is how these tests avoid
#: needing a clock-injection seam in the CLI boundary itself (research R6
#: keeps that seam confined to ``evaluate()``'s own `now` parameter).
_REAL_EVAL_YAML = """
assumptions:
  schedule:
    windows: ["00:00"]

notifications:
  enabled: true
  topic: test-topic
"""


class TestRealEvaluateIdempotence:
    """T022 (US3): the rest of this file stubs ``evaluate()`` with a canned
    ``EvaluationOutcome`` — sufficient to prove the CLI's effects layer, but
    not idempotence *across two real process-boundary invocations* sharing
    persisted state, which is exactly what a cron-driven re-run is. These
    tests let ``report_entries()`` and ``evaluate()`` run for real against a
    real ``.maverick/notify/state.json`` in ``temp_dir``, invoking the CLI
    twice in sequence."""

    def test_second_run_same_window_skips_with_zero_transport_calls(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch, yaml_text=_REAL_EVAL_YAML)
        _stub_real_ledger_sweep(monkeypatch, ["mav-1"])
        _stub_deliverer(monkeypatch, fail=False)

        first = _invoke(cli_runner, "--json")
        assert first.exit_code == ExitCode.SUCCESS
        first_data = json.loads(first.stdout)
        assert len(first_data["result"]["deliveries"]) == 1
        assert first_data["result"]["deliveries"][0]["kind"] == "window-batch"
        assert len(_FakeDeliverer.calls) == 1

        second = _invoke(cli_runner, "--json")

        assert second.exit_code == ExitCode.SUCCESS
        second_data = json.loads(second.stdout)
        assert second_data["result"]["deliveries"] == []
        assert any(
            skip["reason"] == "already-delivered" for skip in second_data["result"]["skips"]
        )
        # No second ntfy push for the already-decided occurrence.
        assert len(_FakeDeliverer.calls) == 1

    def test_new_entry_after_delivery_waits_for_next_window(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """spec.md US3 acceptance scenario 2: a batch already delivered at
        one window must not re-fire just because a new entry showed up —
        the new entry waits for the next occurrence, not an immediate
        second delivery of the same one."""
        _setup(temp_dir, monkeypatch, yaml_text=_REAL_EVAL_YAML)
        _stub_real_ledger_sweep(monkeypatch, ["mav-1"])
        _stub_deliverer(monkeypatch, fail=False)

        first = _invoke(cli_runner, "--json")
        assert len(json.loads(first.stdout)["result"]["deliveries"]) == 1

        # A second entry shows up after the window already delivered.
        _stub_real_ledger_sweep(monkeypatch, ["mav-1", "mav-2"])
        second = _invoke(cli_runner, "--json")

        assert second.exit_code == ExitCode.SUCCESS
        second_data = json.loads(second.stdout)
        assert second_data["result"]["deliveries"] == []
        assert any(
            skip["reason"] == "already-delivered" for skip in second_data["result"]["skips"]
        )
        assert len(_FakeDeliverer.calls) == 1
