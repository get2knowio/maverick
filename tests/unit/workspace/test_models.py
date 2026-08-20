"""Unit tests for `maverick.workspace.models`.

Covers `to_dict()` round-trips and `IsolationPolicy`'s three validation
rules (data-model.md "Validation").
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from maverick.workspace.models import (
    CheckoutPath,
    FoldBackOutcome,
    FoldBackResult,
    IsolationLease,
    IsolationPolicy,
    UnitOfWork,
)


class TestUnitOfWork:
    def test_to_dict_round_trips(self) -> None:
        unit = UnitOfWork(key="bd-1", label="Implement auth", seed_inputs=(Path("/tmp/prd.md"),))
        d = unit.to_dict()
        assert d == {
            "key": "bd-1",
            "label": "Implement auth",
            "seed_inputs": ("/tmp/prd.md",),
        }

    def test_defaults(self) -> None:
        unit = UnitOfWork(key="bd-1", label="Implement auth")
        assert unit.seed_inputs == ()


class TestIsolationPolicy:
    def test_to_dict_round_trips(self) -> None:
        policy = IsolationPolicy(
            workflow="fly",
            root=Path("/home/user/.maverick/workspaces"),
            reuse=False,
            retain_on_failure=False,
            fold_scope=("specs/057-foo",),
            fold_exclusions=("~.maverick",),
        )
        d = policy.to_dict()
        assert d == {
            "workflow": "fly",
            "root": "/home/user/.maverick/workspaces",
            "reuse": False,
            "retain_on_failure": False,
            "fold_scope": ("specs/057-foo",),
            "fold_exclusions": ("~.maverick",),
        }

    def test_rejects_non_slug_workflow(self) -> None:
        with pytest.raises(ValueError, match="path-safe slug"):
            IsolationPolicy(workflow="../etc", root=Path("/tmp"))

    def test_rejects_empty_workflow(self) -> None:
        with pytest.raises(ValueError, match="path-safe slug"):
            IsolationPolicy(workflow="", root=Path("/tmp"))

    def test_rejects_relative_root(self) -> None:
        with pytest.raises(ValueError, match="must be absolute"):
            IsolationPolicy(workflow="fly", root=Path("relative/path"))

    def test_rejects_fold_scope_traversal(self) -> None:
        with pytest.raises(ValueError, match="escape the workspace root"):
            IsolationPolicy(workflow="fly", root=Path("/tmp"), fold_scope=("../outside",))

    def test_rejects_fold_exclusions_traversal(self) -> None:
        with pytest.raises(ValueError, match="escape the workspace root"):
            IsolationPolicy(workflow="fly", root=Path("/tmp"), fold_exclusions=("~../outside",))

    def test_rejects_absolute_fold_scope(self) -> None:
        with pytest.raises(ValueError, match="escape the workspace root"):
            IsolationPolicy(workflow="fly", root=Path("/tmp"), fold_scope=("/etc/passwd",))

    def test_accepts_negated_maverick_exclusion(self) -> None:
        policy = IsolationPolicy(
            workflow="fly", root=Path("/tmp"), fold_exclusions=("~.maverick",)
        )
        assert policy.fold_exclusions == ("~.maverick",)

    def test_defaults(self) -> None:
        policy = IsolationPolicy(workflow="spec-chain", root=Path("/tmp"))
        assert policy.reuse is True
        assert policy.retain_on_failure is False
        assert policy.fold_scope == ()
        assert policy.fold_exclusions == ()


class TestIsolationLease:
    def test_to_dict_round_trips(self) -> None:
        created_at = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)
        lease = IsolationLease(
            unit=UnitOfWork(key="bd-1", label="Implement auth"),
            workspace_path=Path("/home/user/.maverick/workspaces/proj/fly/bd-1"),
            workspace_name="bd-1",
            checkout=CheckoutPath(Path("/home/user/proj")),
            created_at=created_at,
        )
        d = lease.to_dict()
        assert d["workspace_path"] == "/home/user/.maverick/workspaces/proj/fly/bd-1"
        assert d["workspace_name"] == "bd-1"
        assert d["checkout"] == "/home/user/proj"
        assert d["created_at"] == created_at.isoformat()
        assert d["unit"] == {"key": "bd-1", "label": "Implement auth", "seed_inputs": ()}


class TestFoldBackResult:
    def test_to_dict_round_trips(self) -> None:
        result = FoldBackResult(
            outcome=FoldBackOutcome.APPLIED,
            applied_paths=("a.py", "b.py"),
            restore_operation_id="op-abc",
            diagnostic="",
            duration_seconds=1.23,
        )
        d = result.to_dict()
        assert d == {
            "outcome": "applied",
            "applied_paths": ("a.py", "b.py"),
            "conflicting_paths": (),
            "restore_operation_id": "op-abc",
            "diagnostic": "",
            "duration_seconds": 1.23,
        }

    def test_conflict_outcome_carries_conflicting_paths(self) -> None:
        result = FoldBackResult(
            outcome=FoldBackOutcome.CONFLICT,
            conflicting_paths=("a.py",),
            diagnostic="conflict in a.py",
        )
        assert result.to_dict()["outcome"] == "conflict"
        assert result.conflicting_paths == ("a.py",)

    def test_rejected_is_distinguishable_from_conflict_and_discarded_in_projection(self) -> None:
        """FR-019: a naive implementation would collapse REJECTED (an
        environment-level check failed after a successful fold-back),
        CONFLICT (fold-back mechanics), and DISCARDED (agent failure) into
        one "the unit failed" bucket. The `to_dict()` projection — what
        every consumer actually inspects — must keep them apart."""
        rejected = FoldBackResult(outcome=FoldBackOutcome.REJECTED, diagnostic="gate failed")
        conflict = FoldBackResult(outcome=FoldBackOutcome.CONFLICT, conflicting_paths=("a.py",))
        discarded = FoldBackResult(outcome=FoldBackOutcome.DISCARDED)

        projections = {r.to_dict()["outcome"] for r in (rejected, conflict, discarded)}
        assert projections == {"rejected", "conflict", "discarded"}

    def test_outcomes_are_distinguishable(self) -> None:
        outcomes = {o.value for o in FoldBackOutcome}
        assert outcomes == {"applied", "empty", "conflict", "discarded", "rejected"}
