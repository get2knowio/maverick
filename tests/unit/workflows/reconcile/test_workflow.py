"""Tests for `ReconcileWorkflow` orchestration (T017 + later tasks).

Covers the MVP happy-path sequence (clean-working-copy precondition, the
zero-changed-answers fast path, the full per-answer stage sequence on
success), rollback-on-failure, conflict resolution, the semantic-
dependents pass, interrupted-run recovery, and the two pre-mutation
"skipped" guards (T034): unlocatable target and the mutability guard
(``jj_check_mutability``), both of which run before any snapshot is ever
captured.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from maverick.assumptions.models import Severity
from maverick.config import AgentBindingConfig, AgentsConfig, MaverickConfig
from maverick.exceptions import WorkflowError
from maverick.runway.run_metadata import RunMetadata, write_metadata
from maverick.workflows.reconcile import workflow as workflow_module
from maverick.workflows.reconcile.conflicts import ConflictOutcome
from maverick.workflows.reconcile.correction import CorrectionResult
from maverick.workflows.reconcile.models import ChangedAnswer, ReconcileStage
from maverick.workflows.reconcile.semantic import SemanticOutcome
from maverick.workflows.reconcile.state import (
    AnswerState,
    ReconcileRunState,
    acquire_lock,
    load_run_state,
    save_run_state,
)
from maverick.workflows.reconcile.workflow import ReconcileWorkflow


def _config() -> MaverickConfig:
    return MaverickConfig(
        agents=AgentsConfig(
            implement=AgentBindingConfig(provider="claude", model_id="stub-model"),
            review=AgentBindingConfig(provider="claude", model_id="stub-model"),
        )
    )


def _workflow() -> ReconcileWorkflow:
    return ReconcileWorkflow(config=_config())


async def _run_workflow(workflow: ReconcileWorkflow, inputs: dict[str, Any]) -> dict[str, Any]:
    """Drive the workflow through its public `execute()` template method.

    Calling `_run` directly would skip `PythonWorkflow.execute()`'s setup
    of `_step_start_times`/`_event_queue`/etc., so tests go through the
    same path production does (CLI -> `execute_python_workflow` ->
    `workflow.execute(inputs)`), draining every `ProgressEvent` and then
    reading the aggregated `WorkflowResult.final_output`.
    """
    async for _event in workflow.execute(inputs):
        pass
    assert workflow.result is not None
    return workflow.result.final_output


def _changed_answer(
    *,
    entry_id: str = "bd-1",
    target_change_id: str | None = "target-1",
    stack_index: int = 0,
    human_answer: str = "new answer",
) -> ChangedAnswer:
    return ChangedAnswer(
        entry_id=entry_id,
        question="Which auth provider?",
        adopted_answer="OAuth",
        human_answer=human_answer,
        severity=Severity.MEDIUM,
        owner_spec="051-reconcile-changed-answers",
        stamped_change_ids=(target_change_id,) if target_change_id else (),
        target_change_id=target_change_id,
        stack_index=stack_index,
    )


def _correction_result(
    *, applied: bool = True, no_change_required: bool = False, error: str | None = None
) -> CorrectionResult:
    return CorrectionResult(
        applied=applied,
        no_change_required=no_change_required,
        correction_diff="diff --git a/x b/x" if applied else "",
        payload=None,
        error=error,
    )


def _conflict_outcome(
    *,
    resolved: bool = True,
    rounds_used: int = 0,
    unresolvable: tuple[str, ...] = (),
    error: str | None = None,
) -> ConflictOutcome:
    return ConflictOutcome(
        resolved=resolved, rounds_used=rounds_used, unresolvable=unresolvable, error=error
    )


def _semantic_outcome(
    *,
    completed: bool = True,
    rounds_used: int = 0,
    fixed_descendants: tuple[str, ...] = (),
    error: str | None = None,
) -> SemanticOutcome:
    return SemanticOutcome(
        completed=completed,
        rounds_used=rounds_used,
        fixed_descendants=fixed_descendants,
        error=error,
    )


class _FakeSquadron:
    """Stub `ReconcileSquadron` — no real airframe runtime touched."""

    #: Set True by a test to assert the squadron is never constructed
    #: (the zero-changed-answers fast path).
    fail_on_construct: bool = False

    def __init__(self, *, cwd: Path, config: MaverickConfig, cost_sink: Any = None) -> None:
        if _FakeSquadron.fail_on_construct:
            raise AssertionError("ReconcileSquadron must not be constructed on this path")
        self.cwd = cwd
        self.config = config
        self.reconciler = MagicMock(name="reconciler")
        self.semantic = MagicMock(name="semantic")
        self.rotate_for_new_bead = AsyncMock()
        self.opened = False

    async def __aenter__(self) -> _FakeSquadron:
        self.opened = True
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self.opened = False


@pytest.fixture(autouse=True)
def _reset_fake_squadron_guard() -> None:
    _FakeSquadron.fail_on_construct = False


def _patch_jj_client(monkeypatch: pytest.MonkeyPatch, *, files_changed: int = 0) -> None:
    """Patch `JjClient` with a stub whose `diff_stat`/`log` are controllable.

    `log(revset="@-")` and the later re-resolve-by-change-id call both
    resolve to a single change; the re-resolve call passes the original
    parent's own change id as the revset, so echoing it back models jj's
    "change ids are stable across rebase" behaviour well enough for this
    task's happy-path tests (no actual rebase happens in these fakes).
    """

    class _FakeJjClient:
        def __init__(self, *, cwd: Path) -> None:
            self.cwd = cwd

        async def diff_stat(self, revision: str = "@") -> SimpleNamespace:
            return SimpleNamespace(files_changed=files_changed)

        async def log(self, revset: str = "@", limit: int = 10) -> SimpleNamespace:
            change_id = "orig-parent" if revset == "@-" else revset
            return SimpleNamespace(changes=[SimpleNamespace(change_id=change_id)])

    monkeypatch.setattr(workflow_module, "JjClient", _FakeJjClient)


def _patch_common(
    monkeypatch: pytest.MonkeyPatch,
    *,
    changed_answers: tuple[ChangedAnswer, ...] = (),
    apply_correction_result: CorrectionResult | None = None,
    conflict_outcome: ConflictOutcome | None = None,
    semantic_outcome: SemanticOutcome | None = None,
    gate_result: dict[str, Any] | None = None,
    escalation_bead_id: str | None = "bd-escalation",
    mutability_result: dict[str, Any] | None = None,
) -> dict[str, AsyncMock]:
    """Patch every collaborator `ReconcileWorkflow._run` calls by name.

    Returns the mocks so individual tests can assert call args/counts.
    """
    # Default re-resolution (T032/T033): echo back each answer's own
    # already-computed (target_change_id, stack_index), keyed by its
    # stamped_change_ids, so tests that don't care about post-repair
    # re-resolution see zero drift from it — only tests that override
    # this mock's side_effect exercise a genuine mid-run change.
    by_stamped_ids = {
        answer.stamped_change_ids: (answer.target_change_id, answer.stack_index)
        for answer in changed_answers
    }

    async def _default_resolve_target(
        stamped_change_ids: tuple[str, ...], *, cwd: Path
    ) -> tuple[str | None, int]:
        return by_stamped_ids.get(stamped_change_ids, (None, 1_000_000))

    mocks: dict[str, AsyncMock] = {
        "build_changed_answers": AsyncMock(return_value=changed_answers),
        "apply_correction": AsyncMock(
            return_value=apply_correction_result or _correction_result()
        ),
        "resolve_conflicts": AsyncMock(return_value=conflict_outcome or _conflict_outcome()),
        "run_semantic_pass": AsyncMock(return_value=semantic_outcome or _semantic_outcome()),
        "create_reconcile_escalation": AsyncMock(return_value=escalation_bead_id),
        "run_independent_gate": AsyncMock(
            return_value=gate_result or {"passed": True, "stage_results": {}, "summary": "ok"}
        ),
        "mark_reconciled": AsyncMock(return_value=True),
        "mark_needs_interactive_review": AsyncMock(return_value=True),
        "jj_snapshot_operation": AsyncMock(
            return_value={"success": True, "operation_id": "op-1", "error": None}
        ),
        "jj_check_mutability": AsyncMock(
            return_value=mutability_result
            or {
                "success": True,
                "mutable": True,
                "immutable_change_ids": (),
                "error": None,
            }
        ),
        "jj_new_child": AsyncMock(
            return_value={"success": True, "change_id": "new-empty", "error": None}
        ),
        "jj_restore_operation": AsyncMock(return_value={"success": True, "error": None}),
        "resolve_target_against_current_stack": AsyncMock(side_effect=_default_resolve_target),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(workflow_module, name, mock)
    monkeypatch.setattr(workflow_module, "ReconcileSquadron", _FakeSquadron)
    return mocks


class TestWorkingCopyPrecondition:
    async def test_dirty_working_copy_raises_workflow_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=3)
        mocks = _patch_common(monkeypatch)

        with pytest.raises(WorkflowError, match="working copy is not clean"):
            await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["build_changed_answers"].assert_not_called()


class TestZeroChangedAnswersFastPath:
    async def test_returns_empty_report_without_constructing_squadron(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        _patch_common(monkeypatch, changed_answers=())
        _FakeSquadron.fail_on_construct = True

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert result["outcomes"] == []
        assert result["exit_success"] is True
        assert result["run_id"] == "run-1"
        assert result["dry_run"] is False


class TestHappyPathSingleAnswer:
    async def test_all_stages_succeed_produces_reconciled_outcome(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer(entry_id="bd-1", target_change_id="target-1", human_answer="SAML")
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            apply_correction_result=_correction_result(applied=True, no_change_required=False),
            gate_result={"passed": True, "stage_results": {}, "summary": "ok"},
        )

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert len(result["outcomes"]) == 1
        outcome = result["outcomes"][0]
        assert outcome["entry_id"] == "bd-1"
        assert outcome["status"] == "reconciled"
        assert outcome["stage_reached"] == ReconcileStage.TERMINAL.value
        assert outcome["target_change_id"] == "target-1"
        assert outcome["gate_passed"] is True
        assert result["exit_success"] is True

        mocks["mark_reconciled"].assert_awaited_once()
        assert mocks["mark_reconciled"].await_args is not None
        _, kwargs = mocks["mark_reconciled"].await_args
        assert kwargs["entry_id"] == "bd-1"
        assert kwargs["applied_answer"] == "SAML"
        assert kwargs["change_id"] == "target-1"
        mocks["mark_needs_interactive_review"].assert_not_called()

    async def test_rotate_for_new_bead_called_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        _patch_common(monkeypatch, changed_answers=(answer,))

        squadrons: list[_FakeSquadron] = []
        orig_init = _FakeSquadron.__init__

        def _tracking_init(self: _FakeSquadron, **kwargs: Any) -> None:
            orig_init(self, **kwargs)
            squadrons.append(self)

        monkeypatch.setattr(_FakeSquadron, "__init__", _tracking_init)

        await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert len(squadrons) == 1
        squadrons[0].rotate_for_new_bead.assert_awaited_once()

    async def test_final_landing_happens_after_all_answers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        call_order: list[str] = []

        mocks = _patch_common(monkeypatch, changed_answers=(answer,))

        async def _tracking_mark_reconciled(*args: Any, **kwargs: Any) -> bool:
            call_order.append("mark_reconciled")
            return True

        async def _tracking_jj_new_child(*args: Any, **kwargs: Any) -> dict[str, Any]:
            call_order.append("jj_new_child")
            return {"success": True, "change_id": "new-empty", "error": None}

        mocks["mark_reconciled"].side_effect = _tracking_mark_reconciled
        mocks["jj_new_child"].side_effect = _tracking_jj_new_child

        await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert call_order == ["mark_reconciled", "jj_new_child"]
        mocks["jj_new_child"].assert_awaited_once()


class TestUnlocatableTarget:
    async def test_skipped_without_calling_apply_correction_or_any_jj_mutation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """data-model.md §2: an unlocatable target (``target_change_id is
        None``) is ``"skipped"`` (no mutation ever attempted) — NOT
        ``needs_interactive_review``, which is reserved for exits where a
        mutation was attempted and rolled back. Zero jj calls of any kind,
        including the mutability check (target is unresolved, so there is
        nothing to check).
        """
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer(target_change_id=None, stack_index=1_000_000)
        mocks = _patch_common(monkeypatch, changed_answers=(answer,))

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        outcome = result["outcomes"][0]
        assert outcome["status"] == "skipped"
        assert outcome["reason"] == "unresolvable correction target"
        assert outcome["stage_reached"] == ReconcileStage.PENDING.value
        mocks["apply_correction"].assert_not_called()
        mocks["jj_check_mutability"].assert_not_called()
        mocks["jj_snapshot_operation"].assert_not_called()
        # No snapshot was ever captured for this answer, so there is nothing
        # to restore (research R8's one documented exception).
        mocks["jj_restore_operation"].assert_not_called()
        # The bd ledger state is still written (FR-019's uniform re-arm
        # rule) even though the Python status differs.
        assert mocks["mark_needs_interactive_review"].await_args is not None
        _, kwargs = mocks["mark_needs_interactive_review"].await_args
        assert kwargs["entry_id"] == answer.entry_id
        assert kwargs["reason"] == "unresolvable correction target"


class TestMutabilityGuard:
    """T034 (research R4/FR-011/FR-012): once a target IS resolved, one

    read-only ``jj_check_mutability`` call runs before
    ``jj_snapshot_operation`` — an immutable target (or descendant it would
    rebase) or a failed check both produce ``"skipped"`` with zero mutation
    calls, never ``needs_interactive_review``.
    """

    async def test_mutable_target_proceeds_into_snapshot_and_correction(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression check: the new guard must not block the happy path."""
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer(target_change_id="target-1")
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            mutability_result={
                "success": True,
                "mutable": True,
                "immutable_change_ids": (),
                "error": None,
            },
        )

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["jj_check_mutability"].assert_awaited_once()
        _, kwargs = mocks["jj_check_mutability"].await_args
        assert kwargs["target"] == "target-1"
        mocks["jj_snapshot_operation"].assert_awaited_once()
        mocks["apply_correction"].assert_awaited_once()
        assert result["outcomes"][0]["status"] == "reconciled"

    async def test_immutable_target_is_skipped_with_zero_mutation_calls(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer(target_change_id="target-1")
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            mutability_result={
                "success": True,
                "mutable": False,
                "immutable_change_ids": ("target-1", "child-1"),
                "error": None,
            },
        )

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["jj_check_mutability"].assert_awaited_once()
        _, kwargs = mocks["jj_check_mutability"].await_args
        assert kwargs["target"] == "target-1"
        mocks["jj_snapshot_operation"].assert_not_called()
        mocks["apply_correction"].assert_not_called()
        mocks["jj_restore_operation"].assert_not_called()

        outcome = result["outcomes"][0]
        assert outcome["status"] == "skipped"
        assert outcome["stage_reached"] == ReconcileStage.PENDING.value
        assert "target-1" in outcome["reason"]
        assert "child-1" in outcome["reason"]

        assert mocks["mark_needs_interactive_review"].await_args is not None
        _, review_kwargs = mocks["mark_needs_interactive_review"].await_args
        assert review_kwargs["entry_id"] == answer.entry_id
        assert "target-1" in review_kwargs["reason"]

    async def test_mutability_check_failure_fails_safe_and_is_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A transient jj error from the check itself must not be treated

        as "mutable" — fail safe rather than risk touching something
        immutable.
        """
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer(target_change_id="target-1")
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            mutability_result={
                "success": False,
                "mutable": False,
                "immutable_change_ids": (),
                "error": "jj log timed out",
            },
        )

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["jj_snapshot_operation"].assert_not_called()
        mocks["apply_correction"].assert_not_called()
        mocks["jj_restore_operation"].assert_not_called()

        outcome = result["outcomes"][0]
        assert outcome["status"] == "skipped"
        assert outcome["stage_reached"] == ReconcileStage.PENDING.value
        assert "jj log timed out" in outcome["reason"]
        mocks["mark_needs_interactive_review"].assert_awaited_once()


class TestCorrectionFailure:
    async def test_needs_interactive_review_with_corrections_error_as_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            apply_correction_result=_correction_result(applied=False, error="agent blew up"),
        )

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        outcome = result["outcomes"][0]
        assert outcome["status"] == "needs_interactive_review"
        assert outcome["reason"] == "agent blew up"
        assert outcome["stage_reached"] == ReconcileStage.SNAPSHOTTED.value
        mocks["run_independent_gate"].assert_not_called()
        assert mocks["mark_needs_interactive_review"].await_args is not None
        _, kwargs = mocks["mark_needs_interactive_review"].await_args
        assert kwargs["reason"] == "agent blew up"


class TestGateFailure:
    async def test_needs_interactive_review_with_gate_passed_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            gate_result={
                "passed": False,
                "stage_results": {},
                "summary": "1 stage(s) failed: lint",
            },
        )

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        outcome = result["outcomes"][0]
        assert outcome["status"] == "needs_interactive_review"
        assert outcome["gate_passed"] is False
        assert outcome["reason"] == "1 stage(s) failed: lint"
        # The semantic-dependents pass (T030) now runs between
        # CONFLICTS_RESOLVED and the gate, and completes by default in
        # this fixture — so the furthest stage reached before the gate
        # fails is SEMANTIC_DONE, not CONFLICTS_RESOLVED.
        assert outcome["stage_reached"] == ReconcileStage.SEMANTIC_DONE.value
        mocks["mark_reconciled"].assert_not_called()


class TestConflictResolution:
    """T026 (research R5/R8): the conflict-resolution stage sits between

    CORRECTED and the gate. A resolved outcome advances the stage and lets
    the gate run unchanged; a non-resolved outcome (agent-declared
    unresolvable, budget exhaustion, or an internal action error) rolls
    back, creates an escalation bead, and terminal-marks
    needs-interactive-review — mirroring correction/gate failure handling
    but with an escalation bead in the mix.
    """

    async def test_conflicts_resolved_advances_stage_and_gate_still_runs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            conflict_outcome=_conflict_outcome(resolved=True, rounds_used=2),
        )

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["resolve_conflicts"].assert_awaited_once()
        _, kwargs = mocks["resolve_conflicts"].await_args
        assert kwargs["max_rounds"] == 3  # ReconcileConfig.resolution_rounds default
        mocks["run_independent_gate"].assert_awaited_once()
        mocks["create_reconcile_escalation"].assert_not_called()
        outcome = result["outcomes"][0]
        assert outcome["status"] == "reconciled"
        assert outcome["escalation_bead_id"] is None

    async def test_conflicts_unresolvable_rolls_back_and_escalates_in_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            conflict_outcome=_conflict_outcome(
                resolved=False, rounds_used=1, unresolvable=("f.txt", "g.py")
            ),
            escalation_bead_id="bd-escalation-1",
        )
        call_order: list[str] = []

        async def _tracking_restore(*args: Any, **kwargs: Any) -> dict[str, Any]:
            call_order.append("jj_restore_operation")
            return {"success": True, "error": None}

        async def _tracking_escalation(*args: Any, **kwargs: Any) -> str | None:
            call_order.append("create_reconcile_escalation")
            return "bd-escalation-1"

        async def _tracking_mark_needs_review(*args: Any, **kwargs: Any) -> bool:
            call_order.append("mark_needs_interactive_review")
            return True

        mocks["jj_restore_operation"].side_effect = _tracking_restore
        mocks["create_reconcile_escalation"].side_effect = _tracking_escalation
        mocks["mark_needs_interactive_review"].side_effect = _tracking_mark_needs_review

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert call_order == [
            "jj_restore_operation",
            "create_reconcile_escalation",
            "mark_needs_interactive_review",
        ]
        mocks["run_independent_gate"].assert_not_called()

        assert mocks["jj_restore_operation"].await_args is not None
        args, kwargs = mocks["jj_restore_operation"].await_args
        restore_op_id = args[0] if args else kwargs.get("operation_id")
        assert restore_op_id == "op-1"

        assert mocks["create_reconcile_escalation"].await_args is not None
        _, escalation_kwargs = mocks["create_reconcile_escalation"].await_args
        assert escalation_kwargs["entry"].bead_id == answer.entry_id
        assert escalation_kwargs["entry"].question == answer.question
        assert escalation_kwargs["entry"].adopted_answer == answer.adopted_answer
        assert escalation_kwargs["remaining"] == ("f.txt", "g.py")
        assert escalation_kwargs["kind"] == "conflicts"

        outcome = result["outcomes"][0]
        assert outcome["status"] == "needs_interactive_review"
        assert outcome["escalation_bead_id"] == "bd-escalation-1"
        assert outcome["stage_reached"] == ReconcileStage.CORRECTED.value
        mocks["mark_reconciled"].assert_not_called()

    async def test_conflicts_budget_exhaustion_escalates_with_sensible_remaining(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            conflict_outcome=_conflict_outcome(resolved=False, rounds_used=3, unresolvable=()),
            escalation_bead_id="bd-escalation-2",
        )

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert mocks["create_reconcile_escalation"].await_args is not None
        _, escalation_kwargs = mocks["create_reconcile_escalation"].await_args
        assert escalation_kwargs["kind"] == "conflicts"
        remaining = escalation_kwargs["remaining"]
        assert len(remaining) == 1
        assert "3" in remaining[0]  # rounds_used surfaced in the description

        outcome = result["outcomes"][0]
        assert outcome["status"] == "needs_interactive_review"
        assert outcome["escalation_bead_id"] == "bd-escalation-2"
        assert "budget exhausted" in outcome["reason"]
        mocks["run_independent_gate"].assert_not_called()

    async def test_escalation_creation_failure_still_marks_needs_review_with_no_bead_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            conflict_outcome=_conflict_outcome(
                resolved=False, rounds_used=1, unresolvable=("f.txt",)
            ),
            escalation_bead_id=None,
        )

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["create_reconcile_escalation"].assert_awaited_once()
        outcome = result["outcomes"][0]
        assert outcome["status"] == "needs_interactive_review"
        assert outcome["escalation_bead_id"] is None
        # Never raises, never crashes the run.
        mocks["mark_needs_interactive_review"].assert_awaited_once()

    async def test_conflict_free_answer_still_invokes_resolve_conflicts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_conflicts is always called (it internally short-circuits

        on zero conflicts) — the workflow wiring must not skip calling it.
        """
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            conflict_outcome=_conflict_outcome(resolved=True, rounds_used=0),
        )

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["resolve_conflicts"].assert_awaited_once()
        assert result["outcomes"][0]["status"] == "reconciled"


class TestSemanticDependentsPass:
    """T030 (research R6/R8): the semantic-dependents pass sits between

    CONFLICTS_RESOLVED and the gate. A completed outcome advances the
    stage to SEMANTIC_DONE and lets the gate run unchanged; a
    non-completed outcome (budget exhaustion or an internal action error)
    rolls back, creates an escalation bead (``kind="semantic"``), and
    terminal-marks needs-interactive-review — mirroring the conflicts
    stage's handling but for the semantic pass.
    """

    async def test_semantic_completes_advances_stage_and_gate_still_runs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            semantic_outcome=_semantic_outcome(completed=True, rounds_used=1),
        )

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["run_semantic_pass"].assert_awaited_once()
        mocks["run_independent_gate"].assert_awaited_once()
        mocks["create_reconcile_escalation"].assert_not_called()
        outcome = result["outcomes"][0]
        assert outcome["status"] == "reconciled"
        assert outcome["escalation_bead_id"] is None

    async def test_run_semantic_pass_receives_the_captured_correction_diff(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The diff captured by the correction stage (pre-fold) must flow

        through unchanged into ``run_semantic_pass`` — it's the ONLY
        source of "what changed" for the semantic reviewer, since the
        target's post-fold diff is much larger (research R6).
        """
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        distinctive_diff = "diff --git a/reconciled_file.py b/reconciled_file.py\n+fixed"
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            apply_correction_result=CorrectionResult(
                applied=True,
                no_change_required=False,
                correction_diff=distinctive_diff,
                payload=None,
                error=None,
            ),
        )

        await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["run_semantic_pass"].assert_awaited_once()
        args, _kwargs = mocks["run_semantic_pass"].await_args
        # Positional signature: (reconciler, semantic, answer, correction_diff)
        assert args[3] == distinctive_diff

    async def test_semantic_budget_exhaustion_rolls_back_and_escalates_in_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            semantic_outcome=_semantic_outcome(completed=False, rounds_used=3, error=None),
            escalation_bead_id="bd-semantic-escalation",
        )
        call_order: list[str] = []

        async def _tracking_restore(*args: Any, **kwargs: Any) -> dict[str, Any]:
            call_order.append("jj_restore_operation")
            return {"success": True, "error": None}

        async def _tracking_escalation(*args: Any, **kwargs: Any) -> str | None:
            call_order.append("create_reconcile_escalation")
            return "bd-semantic-escalation"

        async def _tracking_mark_needs_review(*args: Any, **kwargs: Any) -> bool:
            call_order.append("mark_needs_interactive_review")
            return True

        mocks["jj_restore_operation"].side_effect = _tracking_restore
        mocks["create_reconcile_escalation"].side_effect = _tracking_escalation
        mocks["mark_needs_interactive_review"].side_effect = _tracking_mark_needs_review

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert call_order == [
            "jj_restore_operation",
            "create_reconcile_escalation",
            "mark_needs_interactive_review",
        ]
        mocks["run_independent_gate"].assert_not_called()

        assert mocks["jj_restore_operation"].await_args is not None
        args, kwargs = mocks["jj_restore_operation"].await_args
        restore_op_id = args[0] if args else kwargs.get("operation_id")
        assert restore_op_id == "op-1"

        assert mocks["create_reconcile_escalation"].await_args is not None
        _, escalation_kwargs = mocks["create_reconcile_escalation"].await_args
        assert escalation_kwargs["entry"].bead_id == answer.entry_id
        assert escalation_kwargs["entry"].question == answer.question
        assert escalation_kwargs["entry"].adopted_answer == answer.adopted_answer
        assert escalation_kwargs["kind"] == "semantic"
        remaining = escalation_kwargs["remaining"]
        assert len(remaining) == 1
        assert "3" in remaining[0]  # rounds_used surfaced in the description

        outcome = result["outcomes"][0]
        assert outcome["status"] == "needs_interactive_review"
        assert outcome["escalation_bead_id"] == "bd-semantic-escalation"
        assert outcome["stage_reached"] == ReconcileStage.CONFLICTS_RESOLVED.value
        assert "budget exhausted" in outcome["reason"]
        mocks["mark_reconciled"].assert_not_called()

    async def test_semantic_internal_error_rolls_back_and_escalates_with_error_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            semantic_outcome=_semantic_outcome(
                completed=False, rounds_used=1, error="apply_correction fold failed"
            ),
            escalation_bead_id="bd-semantic-escalation-2",
        )

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["run_independent_gate"].assert_not_called()
        assert mocks["create_reconcile_escalation"].await_args is not None
        _, escalation_kwargs = mocks["create_reconcile_escalation"].await_args
        assert escalation_kwargs["kind"] == "semantic"
        assert escalation_kwargs["remaining"] == ("apply_correction fold failed",)

        outcome = result["outcomes"][0]
        assert outcome["status"] == "needs_interactive_review"
        assert outcome["escalation_bead_id"] == "bd-semantic-escalation-2"
        assert "apply_correction fold failed" in outcome["reason"]
        mocks["mark_reconciled"].assert_not_called()

    async def test_gate_not_called_when_semantic_pass_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            semantic_outcome=_semantic_outcome(completed=False, rounds_used=3),
        )

        await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["run_independent_gate"].assert_not_called()

    async def test_escalation_creation_failure_still_marks_needs_review_with_no_bead_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            semantic_outcome=_semantic_outcome(completed=False, rounds_used=3),
            escalation_bead_id=None,
        )

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["create_reconcile_escalation"].assert_awaited_once()
        outcome = result["outcomes"][0]
        assert outcome["status"] == "needs_interactive_review"
        assert outcome["escalation_bead_id"] is None
        # Never raises, never crashes the run.
        mocks["mark_needs_interactive_review"].assert_awaited_once()


class TestMultipleAnswersOrdering:
    async def test_processed_in_stack_index_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        later = _changed_answer(entry_id="bd-later", target_change_id="t-later", stack_index=5)
        earlier = _changed_answer(
            entry_id="bd-earlier", target_change_id="t-earlier", stack_index=1
        )
        # Deliberately returned out of order — the workflow must sort.
        mocks = _patch_common(monkeypatch, changed_answers=(later, earlier))

        processed_order: list[str] = []

        async def _tracking_apply_correction(
            reconciler: Any, ans: ChangedAnswer, *, cwd: Any
        ) -> CorrectionResult:
            processed_order.append(ans.entry_id)
            return _correction_result()

        mocks["apply_correction"].side_effect = _tracking_apply_correction

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert processed_order == ["bd-earlier", "bd-later"]
        assert [o["entry_id"] for o in result["outcomes"]] == ["bd-earlier", "bd-later"]
        assert all(o["status"] == "reconciled" for o in result["outcomes"])


class TestRollbackOrdering:
    """T020/T021 (US2, research R8): every post-snapshot failure exit must

    call ``jj_restore_operation(restore_op_id)`` *before*
    ``mark_needs_interactive_review`` — never the reverse, and never with a
    bd write squeezed in between. Each test tracks call order via a shared
    list appended to by both mocks' ``side_effect``.
    """

    async def test_correction_failure_restores_before_marking_needs_review(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            apply_correction_result=_correction_result(applied=False, error="agent blew up"),
        )
        call_order: list[str] = []

        async def _tracking_restore(*args: Any, **kwargs: Any) -> dict[str, Any]:
            call_order.append("jj_restore_operation")
            return {"success": True, "error": None}

        async def _tracking_mark_needs_review(*args: Any, **kwargs: Any) -> bool:
            call_order.append("mark_needs_interactive_review")
            return True

        mocks["jj_restore_operation"].side_effect = _tracking_restore
        mocks["mark_needs_interactive_review"].side_effect = _tracking_mark_needs_review

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert call_order == ["jj_restore_operation", "mark_needs_interactive_review"]
        assert mocks["jj_restore_operation"].await_args is not None
        args, kwargs = mocks["jj_restore_operation"].await_args
        restore_op_id = args[0] if args else kwargs.get("operation_id")
        assert restore_op_id == "op-1"
        assert result["outcomes"][0]["status"] == "needs_interactive_review"

    async def test_gate_failure_restores_before_marking_needs_review(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            gate_result={
                "passed": False,
                "stage_results": {},
                "summary": "1 stage(s) failed: lint",
            },
        )
        call_order: list[str] = []

        async def _tracking_restore(*args: Any, **kwargs: Any) -> dict[str, Any]:
            call_order.append("jj_restore_operation")
            return {"success": True, "error": None}

        async def _tracking_mark_needs_review(*args: Any, **kwargs: Any) -> bool:
            call_order.append("mark_needs_interactive_review")
            return True

        mocks["jj_restore_operation"].side_effect = _tracking_restore
        mocks["mark_needs_interactive_review"].side_effect = _tracking_mark_needs_review

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert call_order == ["jj_restore_operation", "mark_needs_interactive_review"]
        assert result["outcomes"][0]["status"] == "needs_interactive_review"
        assert result["outcomes"][0]["gate_passed"] is False

    async def test_broad_exception_restores_before_marking_needs_review(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(monkeypatch, changed_answers=(answer,))
        # Force the broad-exception path: gate stage raises unexpectedly
        # rather than returning a `passed: False` result.
        mocks["run_independent_gate"].side_effect = RuntimeError("gate crashed")
        call_order: list[str] = []

        async def _tracking_restore(*args: Any, **kwargs: Any) -> dict[str, Any]:
            call_order.append("jj_restore_operation")
            return {"success": True, "error": None}

        async def _tracking_mark_needs_review(*args: Any, **kwargs: Any) -> bool:
            call_order.append("mark_needs_interactive_review")
            return True

        mocks["jj_restore_operation"].side_effect = _tracking_restore
        mocks["mark_needs_interactive_review"].side_effect = _tracking_mark_needs_review

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert call_order == ["jj_restore_operation", "mark_needs_interactive_review"]
        outcome = result["outcomes"][0]
        assert outcome["status"] == "needs_interactive_review"
        assert "gate crashed" in outcome["reason"]

    async def test_third_answer_processed_after_second_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        first = _changed_answer(entry_id="bd-1", target_change_id="t-1", stack_index=0)
        second = _changed_answer(entry_id="bd-2", target_change_id="t-2", stack_index=1)
        third = _changed_answer(entry_id="bd-3", target_change_id="t-3", stack_index=2)
        mocks = _patch_common(monkeypatch, changed_answers=(first, second, third))

        processed: list[str] = []

        async def _tracking_apply_correction(
            reconciler: Any, ans: ChangedAnswer, *, cwd: Any
        ) -> CorrectionResult:
            processed.append(ans.entry_id)
            if ans.entry_id == "bd-2":
                return _correction_result(applied=False, error="second answer failed")
            return _correction_result()

        mocks["apply_correction"].side_effect = _tracking_apply_correction

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        # All three answers were attempted — the second's failure did not
        # stop the run from reaching the third.
        assert processed == ["bd-1", "bd-2", "bd-3"]
        assert [o["entry_id"] for o in result["outcomes"]] == ["bd-1", "bd-2", "bd-3"]
        statuses = {o["entry_id"]: o["status"] for o in result["outcomes"]}
        assert statuses["bd-1"] == "reconciled"
        assert statuses["bd-2"] == "needs_interactive_review"
        assert statuses["bd-3"] == "reconciled"
        # The second answer's rollback must have run (it had a restore
        # point captured); it must not have poisoned the third answer's run.
        mocks["jj_restore_operation"].assert_awaited_once()

    async def test_one_terminal_status_per_answer_invariant(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        reconciled = _changed_answer(entry_id="bd-ok", target_change_id="t-ok", stack_index=0)
        failed = _changed_answer(entry_id="bd-fail", target_change_id="t-fail", stack_index=1)
        unlocatable = _changed_answer(
            entry_id="bd-unlocatable", target_change_id=None, stack_index=2
        )
        mocks = _patch_common(monkeypatch, changed_answers=(reconciled, failed, unlocatable))

        async def _tracking_apply_correction(
            reconciler: Any, ans: ChangedAnswer, *, cwd: Any
        ) -> CorrectionResult:
            if ans.entry_id == "bd-fail":
                return _correction_result(applied=False, error="boom")
            return _correction_result()

        mocks["apply_correction"].side_effect = _tracking_apply_correction

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        allowed = {"reconciled", "skipped", "needs_interactive_review"}
        assert len(result["outcomes"]) == 3
        for outcome in result["outcomes"]:
            assert outcome["status"] in allowed
            # Exactly one status — never left null/intermediate.
            assert outcome["status"] is not None

    async def test_restore_operation_failure_still_marks_needs_review(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed rollback must not crash the run — the answer still

        lands on `needs_interactive_review`, with the reason augmented to
        note the rollback also failed, and the failure logged at error
        level (a failed rollback is more serious than an ordinary
        needs-review exit).
        """
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            apply_correction_result=_correction_result(applied=False, error="agent blew up"),
        )
        mocks["jj_restore_operation"].return_value = {
            "success": False,
            "error": "op log corrupted",
        }

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        outcome = result["outcomes"][0]
        assert outcome["status"] == "needs_interactive_review"
        mocks["jj_restore_operation"].assert_awaited_once()
        mocks["mark_needs_interactive_review"].assert_awaited_once()
        assert mocks["mark_needs_interactive_review"].await_args is not None
        _, kwargs = mocks["mark_needs_interactive_review"].await_args
        # Original failure reason preserved plus an indication the rollback
        # itself failed.
        assert "agent blew up" in kwargs["reason"]
        assert "op log corrupted" in kwargs["reason"] or "rollback" in kwargs["reason"].lower()


class TestInterruptedRunRecovery:
    """T022 (US2, research R9, FR-016): a discovered ``status="running"``

    prior run state is the crash signal — recovered (restore + mark
    needs-interactive-review) before this invocation's own detection pass,
    never treated as a blocking concurrent run.
    """

    async def test_no_prior_interrupted_state_proceeds_normally(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No regression: a fresh run with nothing on disk behaves exactly
        like the pre-T022 happy path — no restore call, normal outcome.
        """
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(monkeypatch, changed_answers=(answer,))

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert result["outcomes"][0]["status"] == "reconciled"
        mocks["jj_restore_operation"].assert_not_called()

    async def test_recovers_interrupted_answer_then_processes_new_answers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        mocks = _patch_common(monkeypatch, changed_answers=())
        _FakeSquadron.fail_on_construct = True

        prior_state = ReconcileRunState(
            run_id="run-old",
            status="running",
            updated_at="2026-07-20T00:00:00Z",
            answers=[
                AnswerState(
                    entry_id="bd-old",
                    target_change_id="t-old",
                    restore_op_id="op-old",
                    stage=ReconcileStage.CORRECTED,
                ),
            ],
        )
        await save_run_state(prior_state, tmp_path)

        result = await _run_workflow(_workflow(), {"run_id": "run-new", "cwd": str(tmp_path)})

        mocks["jj_restore_operation"].assert_awaited_once()
        args, kwargs = mocks["jj_restore_operation"].await_args
        restore_op_id = args[0] if args else kwargs.get("operation_id")
        assert restore_op_id == "op-old"

        assert mocks["mark_needs_interactive_review"].await_args is not None
        _, review_kwargs = mocks["mark_needs_interactive_review"].await_args
        assert review_kwargs["entry_id"] == "bd-old"
        assert review_kwargs["reason"] == "interrupted"

        # The old run's state is retired so discover_resumable won't find
        # it again on a subsequent invocation.
        retired = await load_run_state("run-old", tmp_path)
        assert retired is not None
        assert retired.status == "failed"

        # This invocation proceeded as a fresh run — zero changed answers
        # detected (its own build_changed_answers mock returns ()).
        assert result["outcomes"] == []
        assert result["run_id"] == "run-new"

    async def test_terminal_prior_answer_is_not_restored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A prior run in status="running" whose answer already reached
        TERMINAL (e.g. crash happened just after the last save, between
        marking terminal and flipping run status to "completed") must not
        trigger a spurious restore for that already-finished answer.
        """
        _patch_jj_client(monkeypatch, files_changed=0)
        mocks = _patch_common(monkeypatch, changed_answers=())
        _FakeSquadron.fail_on_construct = True

        prior_state = ReconcileRunState(
            run_id="run-old",
            status="running",
            updated_at="2026-07-20T00:00:00Z",
            answers=[
                AnswerState(
                    entry_id="bd-old",
                    target_change_id="t-old",
                    restore_op_id="op-old",
                    stage=ReconcileStage.TERMINAL,
                    terminal_status="reconciled",
                ),
            ],
        )
        await save_run_state(prior_state, tmp_path)

        await _run_workflow(_workflow(), {"run_id": "run-new", "cwd": str(tmp_path)})

        mocks["jj_restore_operation"].assert_not_called()
        mocks["mark_needs_interactive_review"].assert_not_called()
        retired = await load_run_state("run-old", tmp_path)
        assert retired is not None
        assert retired.status == "failed"


class TestConcurrencyGuards:
    """T022 (US2, research R9/R14): reconcile lockfile + fly-run-flying

    guard implementing contract precondition 4 ("no concurrent run").
    """

    async def test_lock_held_by_live_process_raises_workflow_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        mocks = _patch_common(monkeypatch, changed_answers=(_changed_answer(),))
        _FakeSquadron.fail_on_construct = True

        lock_dir = tmp_path / ".maverick" / "runs"
        lock_dir.mkdir(parents=True)
        lock_path = lock_dir / "reconcile.lock"
        # This test process's own pid is guaranteed alive.
        lock_path.write_text(str(os.getpid()), encoding="utf-8")

        with pytest.raises(WorkflowError, match="already in progress"):
            await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["build_changed_answers"].assert_not_called()
        # Never acquired -> must never release someone else's lock.
        assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())

    async def test_stale_lock_reclaimed_run_proceeds_normally(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Integration point over the already-unit-tested acquire_lock
        stale-pid reclaim (T008/test_state.py): a dead pid on disk must not
        block a real workflow run.
        """
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        _patch_common(monkeypatch, changed_answers=(answer,))

        lock_dir = tmp_path / ".maverick" / "runs"
        lock_dir.mkdir(parents=True)
        lock_path = lock_dir / "reconcile.lock"
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        dead_pid = proc.pid
        proc.wait(timeout=5)
        lock_path.write_text(str(dead_pid), encoding="utf-8")

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert result["outcomes"][0]["status"] == "reconciled"
        # Reclaimed by this run, then released on completion.
        assert not lock_path.is_file()

    async def test_fly_run_flying_raises_workflow_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        mocks = _patch_common(monkeypatch, changed_answers=(_changed_answer(),))
        _FakeSquadron.fail_on_construct = True

        run_dir = tmp_path / ".maverick" / "runs" / "fly-run-1"
        write_metadata(
            run_dir,
            RunMetadata(
                run_id="fly-run-1",
                plan_name="some-plan",
                epic_id="epic-1",
                status="flying",
            ),
        )

        with pytest.raises(WorkflowError, match="fly run is in progress"):
            await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["build_changed_answers"].assert_not_called()
        # No lockfile should have been created — the fly-flying guard
        # short-circuits before lock acquisition.
        assert not (tmp_path / ".maverick" / "runs" / "reconcile.lock").is_file()

    async def test_fly_run_not_flying_does_not_block(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A fly run recorded in a terminal status (e.g. "completed") must
        not trip the guard — only "flying" blocks.
        """
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        _patch_common(monkeypatch, changed_answers=(answer,))

        run_dir = tmp_path / ".maverick" / "runs" / "fly-run-1"
        write_metadata(
            run_dir,
            RunMetadata(
                run_id="fly-run-1",
                plan_name="some-plan",
                epic_id="epic-1",
                status="completed",
            ),
        )

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert result["outcomes"][0]["status"] == "reconciled"

    async def test_lock_released_after_successful_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        _patch_common(monkeypatch, changed_answers=(answer,))

        await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        lock_path = tmp_path / ".maverick" / "runs" / "reconcile.lock"
        assert not lock_path.is_file()
        # Re-acquiring immediately after must succeed.
        assert await acquire_lock(tmp_path) is True

    async def test_lock_released_when_run_raises_partway_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        mocks = _patch_common(monkeypatch, changed_answers=(answer,))
        mocks["build_changed_answers"].side_effect = RuntimeError("boom - unexpected failure")

        with pytest.raises(RuntimeError, match="boom"):
            await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        lock_path = tmp_path / ".maverick" / "runs" / "reconcile.lock"
        assert not lock_path.is_file()


class TestPostRepairReResolution:
    """T032/T033 (US5, research R2/R13): the batch-wide ``stack_index`` sort
    (T017) runs once, before any repair. By the time the SECOND (or later)
    answer in ``ordered_answers`` reaches processing, an earlier answer's
    correction may have already folded (squash/absorb auto-rebases
    descendants in the same jj operation) — so this answer's target/
    position could be stale. The workflow must re-verify (and, if needed,
    recompute) each subsequent answer's resolution against a FRESH ``::@``
    snapshot immediately before dispatching it — never for the first
    answer, since nothing has been rebased yet when it is processed.
    """

    async def test_first_answer_is_never_reresolved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer(entry_id="bd-1", target_change_id="t-1", stack_index=0)
        mocks = _patch_common(monkeypatch, changed_answers=(answer,))

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["resolve_target_against_current_stack"].assert_not_called()
        assert result["outcomes"][0]["status"] == "reconciled"

    async def test_second_answer_reresolved_between_the_two_answers_processing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        first = _changed_answer(entry_id="bd-1", target_change_id="t-1", stack_index=0)
        second = _changed_answer(entry_id="bd-2", target_change_id="t-2", stack_index=1)
        mocks = _patch_common(monkeypatch, changed_answers=(first, second))

        call_order: list[str] = []

        async def _tracking_apply_correction(
            reconciler: Any, ans: ChangedAnswer, *, cwd: Any
        ) -> CorrectionResult:
            call_order.append(f"apply_correction:{ans.entry_id}")
            return _correction_result()

        async def _tracking_resolve(
            stamped_change_ids: tuple[str, ...], *, cwd: Path
        ) -> tuple[str | None, int]:
            call_order.append(f"resolve:{stamped_change_ids}")
            # Simulate the first answer's fold having rebased the stack:
            # the second answer's target now resolves to a NEW id/position.
            if stamped_change_ids == second.stamped_change_ids:
                return "t-2-rebased", 0
            return (stamped_change_ids[0], 0) if stamped_change_ids else (None, 1_000_000)

        mocks["apply_correction"].side_effect = _tracking_apply_correction
        mocks["resolve_target_against_current_stack"].side_effect = _tracking_resolve

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        # Exactly one re-resolution call, sequenced strictly between the
        # first answer's correction and the second's — never before the
        # first, never skipped for the second.
        assert call_order == [
            "apply_correction:bd-1",
            f"resolve:{second.stamped_change_ids}",
            "apply_correction:bd-2",
        ]
        mocks["resolve_target_against_current_stack"].assert_awaited_once()

        outcomes = {o["entry_id"]: o for o in result["outcomes"]}
        assert outcomes["bd-1"]["status"] == "reconciled"
        assert outcomes["bd-2"]["status"] == "reconciled"
        # The second answer was processed and reconciled against the NEW,
        # re-resolved target — not the stale pre-run one.
        assert outcomes["bd-2"]["target_change_id"] == "t-2-rebased"

    async def test_reresolution_returning_same_values_does_not_alter_processing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When re-resolution echoes back the same (target, stack_index),
        the answer must be processed exactly as it would without any
        re-resolution at all — i.e. this is a genuine no-op in the common
        case where nothing shifted.
        """
        _patch_jj_client(monkeypatch, files_changed=0)
        first = _changed_answer(entry_id="bd-1", target_change_id="t-1", stack_index=0)
        second = _changed_answer(entry_id="bd-2", target_change_id="t-2", stack_index=1)
        mocks = _patch_common(monkeypatch, changed_answers=(first, second))

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        mocks["resolve_target_against_current_stack"].assert_awaited_once()
        outcomes = {o["entry_id"]: o for o in result["outcomes"]}
        assert outcomes["bd-2"]["target_change_id"] == "t-2"
        assert outcomes["bd-2"]["status"] == "reconciled"

    async def test_third_answer_also_reresolved_using_its_own_stamped_ids(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        first = _changed_answer(entry_id="bd-1", target_change_id="t-1", stack_index=0)
        second = _changed_answer(entry_id="bd-2", target_change_id="t-2", stack_index=1)
        third = _changed_answer(entry_id="bd-3", target_change_id="t-3", stack_index=2)
        mocks = _patch_common(monkeypatch, changed_answers=(first, second, third))

        resolved_for: list[tuple[str, ...]] = []

        async def _tracking_resolve(
            stamped_change_ids: tuple[str, ...], *, cwd: Path
        ) -> tuple[str | None, int]:
            resolved_for.append(stamped_change_ids)
            return (stamped_change_ids[0], 0) if stamped_change_ids else (None, 1_000_000)

        mocks["resolve_target_against_current_stack"].side_effect = _tracking_resolve

        await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        # Called once per answer after the first, each with that answer's
        # own stamped_change_ids — never the first's.
        assert resolved_for == [second.stamped_change_ids, third.stamped_change_ids]


class TestSameTargetSequentialHandling:
    """T033 second half (US5): two different ledger entries whose stamped
    ids happen to resolve to the SAME ``target_change_id`` must be
    processed strictly sequentially. No special-casing is added for this —
    it is an emergent property of the existing simple ``for`` loop, since
    each answer's correction always operates against whatever the shared
    target's CURRENT state is at the time it is that answer's turn. This
    test proves the second entry's correction never starts until the
    first's entire snapshot->correct->gate->mark_reconciled cycle for that
    same target has completed — i.e. the second's fix is built on top of
    the first's already-folded correction, not interleaved with it.
    """

    async def test_second_entrys_correction_starts_only_after_first_fully_completes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        shared_target = "shared-target"
        first = _changed_answer(entry_id="bd-1", target_change_id=shared_target, stack_index=0)
        second = _changed_answer(entry_id="bd-2", target_change_id=shared_target, stack_index=0)
        mocks = _patch_common(monkeypatch, changed_answers=(first, second))

        call_order: list[str] = []

        async def _tracking_apply_correction(
            reconciler: Any, ans: ChangedAnswer, *, cwd: Any
        ) -> CorrectionResult:
            call_order.append(f"correction_start:{ans.entry_id}")
            return _correction_result()

        async def _tracking_mark_reconciled(*args: Any, **kwargs: Any) -> bool:
            call_order.append(f"reconciled:{kwargs['entry_id']}")
            return True

        mocks["apply_correction"].side_effect = _tracking_apply_correction
        mocks["mark_reconciled"].side_effect = _tracking_mark_reconciled

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert call_order == [
            "correction_start:bd-1",
            "reconciled:bd-1",
            "correction_start:bd-2",
            "reconciled:bd-2",
        ]
        assert all(o["status"] == "reconciled" for o in result["outcomes"])


class TestDryRun:
    """T035: ``--dry-run`` predicts a terminal status per answer using only

    the same two pre-mutation guards ``_process_one_answer`` runs before
    ``jj_snapshot_operation`` (unlocatable target, then
    ``jj_check_mutability``) — zero jj mutations, zero agent calls (no
    ``ReconcileSquadron``), zero ledger writes, zero run-state persistence
    (contract: "Detection, stack ordering, target resolution, and
    mutability checks only. Zero jj/bd/filesystem mutations.").
    """

    async def test_mutable_resolvable_target_predicts_reconciled_with_zero_mutations(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer(entry_id="bd-1", target_change_id="target-1")
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            mutability_result={
                "success": True,
                "mutable": True,
                "immutable_change_ids": (),
                "error": None,
            },
        )
        _FakeSquadron.fail_on_construct = True
        # `save_run_state` isn't part of `_patch_common` (other tests depend
        # on its real disk-persisting behaviour), so spy on it locally —
        # scoped to this test only via `monkeypatch`.
        save_run_state_mock = AsyncMock()
        monkeypatch.setattr(workflow_module, "save_run_state", save_run_state_mock)

        result = await _run_workflow(
            _workflow(),
            {"run_id": "run-1", "cwd": str(tmp_path), "dry_run": True},
        )

        assert result["dry_run"] is True
        assert len(result["outcomes"]) == 1
        outcome = result["outcomes"][0]
        assert outcome["entry_id"] == "bd-1"
        assert outcome["status"] == "reconciled"
        assert outcome["target_change_id"] == "target-1"
        assert outcome["stage_reached"] == ReconcileStage.PENDING.value

        mocks["jj_check_mutability"].assert_awaited_once()
        _, kwargs = mocks["jj_check_mutability"].await_args
        assert kwargs["target"] == "target-1"

        mocks["jj_snapshot_operation"].assert_not_called()
        mocks["apply_correction"].assert_not_called()
        mocks["resolve_conflicts"].assert_not_called()
        mocks["run_semantic_pass"].assert_not_called()
        mocks["run_independent_gate"].assert_not_called()
        mocks["mark_reconciled"].assert_not_called()
        mocks["mark_needs_interactive_review"].assert_not_called()
        mocks["jj_restore_operation"].assert_not_called()
        save_run_state_mock.assert_not_called()

    async def test_immutable_target_predicts_skipped_with_zero_mutations(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer(entry_id="bd-1", target_change_id="target-1")
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(answer,),
            mutability_result={
                "success": True,
                "mutable": False,
                "immutable_change_ids": ("target-1", "child-1"),
                "error": None,
            },
        )
        _FakeSquadron.fail_on_construct = True
        save_run_state_mock = AsyncMock()
        monkeypatch.setattr(workflow_module, "save_run_state", save_run_state_mock)

        result = await _run_workflow(
            _workflow(),
            {"run_id": "run-1", "cwd": str(tmp_path), "dry_run": True},
        )

        assert result["dry_run"] is True
        outcome = result["outcomes"][0]
        assert outcome["status"] == "skipped"
        assert outcome["stage_reached"] == ReconcileStage.PENDING.value
        assert "target-1" in outcome["reason"]
        assert "child-1" in outcome["reason"]

        mocks["jj_check_mutability"].assert_awaited_once()
        mocks["jj_snapshot_operation"].assert_not_called()
        mocks["apply_correction"].assert_not_called()
        mocks["mark_reconciled"].assert_not_called()
        mocks["mark_needs_interactive_review"].assert_not_called()
        mocks["jj_restore_operation"].assert_not_called()
        save_run_state_mock.assert_not_called()

    async def test_unlocatable_target_predicts_skipped_with_zero_jj_calls(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer(target_change_id=None, stack_index=1_000_000)
        mocks = _patch_common(monkeypatch, changed_answers=(answer,))
        _FakeSquadron.fail_on_construct = True
        save_run_state_mock = AsyncMock()
        monkeypatch.setattr(workflow_module, "save_run_state", save_run_state_mock)

        result = await _run_workflow(
            _workflow(),
            {"run_id": "run-1", "cwd": str(tmp_path), "dry_run": True},
        )

        assert result["dry_run"] is True
        outcome = result["outcomes"][0]
        assert outcome["status"] == "skipped"
        assert outcome["reason"] == "unresolvable correction target"
        assert outcome["stage_reached"] == ReconcileStage.PENDING.value
        assert outcome["target_change_id"] is None

        # No jj call of any kind for this answer — target never resolved.
        mocks["jj_check_mutability"].assert_not_called()
        mocks["jj_snapshot_operation"].assert_not_called()
        mocks["apply_correction"].assert_not_called()
        mocks["mark_reconciled"].assert_not_called()
        mocks["mark_needs_interactive_review"].assert_not_called()
        mocks["jj_restore_operation"].assert_not_called()
        save_run_state_mock.assert_not_called()

    async def test_multiple_answers_each_predicted_independently(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        mutable_answer = _changed_answer(
            entry_id="bd-mutable", target_change_id="t-mutable", stack_index=0
        )
        unlocatable_answer = _changed_answer(
            entry_id="bd-unlocatable", target_change_id=None, stack_index=1_000_000
        )
        mocks = _patch_common(
            monkeypatch,
            changed_answers=(mutable_answer, unlocatable_answer),
            mutability_result={
                "success": True,
                "mutable": True,
                "immutable_change_ids": (),
                "error": None,
            },
        )
        _FakeSquadron.fail_on_construct = True
        save_run_state_mock = AsyncMock()
        monkeypatch.setattr(workflow_module, "save_run_state", save_run_state_mock)

        result = await _run_workflow(
            _workflow(),
            {"run_id": "run-1", "cwd": str(tmp_path), "dry_run": True},
        )

        statuses = {o["entry_id"]: o["status"] for o in result["outcomes"]}
        assert statuses == {"bd-mutable": "reconciled", "bd-unlocatable": "skipped"}
        # Only one mutability check — the unlocatable answer never resolves
        # a target to check.
        mocks["jj_check_mutability"].assert_awaited_once()
        save_run_state_mock.assert_not_called()

    async def test_zero_changed_answers_dry_run_has_dry_run_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_jj_client(monkeypatch, files_changed=0)
        _patch_common(monkeypatch, changed_answers=())
        _FakeSquadron.fail_on_construct = True

        result = await _run_workflow(
            _workflow(),
            {"run_id": "run-1", "cwd": str(tmp_path), "dry_run": True},
        )

        assert result["outcomes"] == []
        assert result["dry_run"] is True
        assert result["exit_success"] is True

    async def test_real_run_still_sets_dry_run_false_regression(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression check: a real (non-dry-run) invocation that actually

        processes an answer must still report ``dry_run=False`` on the
        final report — not just on the zero-changed-answers fast path
        (already covered by ``TestZeroChangedAnswersFastPath``).
        """
        _patch_jj_client(monkeypatch, files_changed=0)
        answer = _changed_answer()
        _patch_common(monkeypatch, changed_answers=(answer,))

        result = await _run_workflow(_workflow(), {"run_id": "run-1", "cwd": str(tmp_path)})

        assert result["dry_run"] is False
        assert result["outcomes"][0]["status"] == "reconciled"
