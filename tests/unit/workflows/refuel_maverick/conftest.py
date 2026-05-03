"""Shared test fixtures for RefuelMaverickWorkflow tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from maverick.executor.result import ExecutorResult
from maverick.library.actions.types import BeadCreationResult, DependencyWiringResult
from maverick.workflows.refuel_maverick.constants import DETAIL_BATCH_SIZE
from maverick.workflows.refuel_maverick.models import (
    AcceptanceCriterionSpec,
    DecompositionOutline,
    DecompositionOutput,
    DetailBatchOutput,
    FileScopeSpec,
    WorkUnitDetail,
    WorkUnitOutline,
    WorkUnitSpec,
)
from maverick.workflows.refuel_maverick.workflow import RefuelMaverickWorkflow

# ---------------------------------------------------------------------------
# Sample flight plan helper
# ---------------------------------------------------------------------------


def make_simple_flight_plan(tmp_path: Path) -> Path:
    """Create a sample simple flight plan with 3 success criteria, 5 in-scope files.

    Returns the Path to the written flight plan file.
    """
    content = """\
---
name: add-user-auth
version: "1.0"
created: 2026-02-27
tags: [auth, security]
---

## Objective
Add user authentication to the application.

## Success Criteria
- [ ] Users can register with email and password
- [ ] Users can log in and receive a session token
- [ ] Protected routes reject unauthenticated requests

## Scope

### In
- src/auth/models.py
- src/auth/views.py
- src/auth/urls.py
- tests/test_auth.py
- src/config.py

### Out
- src/admin/

### Boundaries
- src/config.py (protect - read only)
"""
    flight_plans_dir = tmp_path / ".maverick" / "plans" / "add-user-auth"
    flight_plans_dir.mkdir(parents=True)
    fp = flight_plans_dir / "flight-plan.md"
    fp.write_text(content, encoding="utf-8")
    return fp


def make_simple_decomposition_output() -> DecompositionOutput:
    """Return a sample DecompositionOutput with 4 work units (sequential deps)."""
    return DecompositionOutput(
        work_units=[
            WorkUnitSpec(
                id="add-user-model",
                sequence=1,
                task="Add User model with email/password fields",
                acceptance_criteria=[
                    AcceptanceCriterionSpec(text="User model created", trace_ref="SC-001")
                ],
                file_scope=FileScopeSpec(
                    create=["src/auth/models.py"],
                    modify=[],
                    protect=["src/config.py"],
                ),
                instructions="Create the User model in src/auth/models.py",
                verification=["python -m pytest tests/test_auth.py::test_user_model"],
            ),
            WorkUnitSpec(
                id="add-registration-endpoint",
                sequence=2,
                depends_on=["add-user-model"],
                task="Add registration endpoint",
                acceptance_criteria=[
                    AcceptanceCriterionSpec(text="Registration works", trace_ref="SC-001")
                ],
                file_scope=FileScopeSpec(
                    create=[],
                    modify=["src/auth/views.py"],
                    protect=["src/config.py"],
                ),
                instructions="Add POST /register endpoint",
                verification=["python -m pytest tests/test_auth.py::test_register"],
            ),
            WorkUnitSpec(
                id="add-login-endpoint",
                sequence=3,
                depends_on=["add-user-model"],
                task="Add login endpoint returning session token",
                acceptance_criteria=[
                    AcceptanceCriterionSpec(text="Login returns token", trace_ref="SC-002")
                ],
                file_scope=FileScopeSpec(
                    create=[],
                    modify=["src/auth/views.py"],
                    protect=["src/config.py"],
                ),
                instructions="Add POST /login endpoint",
                verification=["python -m pytest tests/test_auth.py::test_login"],
            ),
            WorkUnitSpec(
                id="add-auth-middleware",
                sequence=4,
                depends_on=["add-login-endpoint"],
                task="Add authentication middleware",
                acceptance_criteria=[
                    AcceptanceCriterionSpec(
                        text="Middleware rejects unauthorized", trace_ref="SC-003"
                    )
                ],
                file_scope=FileScopeSpec(
                    create=[],
                    modify=["src/auth/urls.py"],
                    protect=["src/config.py"],
                ),
                instructions="Add auth middleware",
                verification=["python -m pytest tests/test_auth.py::test_middleware"],
            ),
        ],
        rationale="Sequential decomposition of auth feature",
    )


def decomposition_to_two_pass_results(
    decomp: DecompositionOutput,
) -> list[ExecutorResult]:
    """Convert a DecompositionOutput into the sequence of ExecutorResults
    expected by the two-pass (outline → detail batches) decomposition flow.

    Returns a list of ExecutorResult objects: first the outline result,
    then one detail batch result per DETAIL_BATCH_SIZE chunk of work units.
    """
    # Build outline
    outlines = [
        WorkUnitOutline(
            id=wu.id,
            sequence=wu.sequence,
            parallel_group=wu.parallel_group,
            depends_on=wu.depends_on,
            task=wu.task,
            file_scope=wu.file_scope,
        )
        for wu in decomp.work_units
    ]
    outline = DecompositionOutline(
        work_units=outlines,
        rationale=decomp.rationale,
    )

    # Build detail batches
    all_units = list(decomp.work_units)
    detail_batches: list[DetailBatchOutput] = []
    for i in range(0, len(all_units), DETAIL_BATCH_SIZE):
        batch = all_units[i : i + DETAIL_BATCH_SIZE]
        detail_batches.append(
            DetailBatchOutput(
                details=[
                    WorkUnitDetail(
                        id=wu.id,
                        instructions=wu.instructions,
                        acceptance_criteria=wu.acceptance_criteria,
                        verification=wu.verification,
                    )
                    for wu in batch
                ]
            )
        )

    results: list[ExecutorResult] = [
        ExecutorResult(output=outline, success=True, events=(), usage=None),
    ]
    for batch in detail_batches:
        results.append(
            ExecutorResult(output=batch, success=True, events=(), usage=None),
        )
    return results


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------


def make_bead_result() -> BeadCreationResult:
    """Return a sample BeadCreationResult for 4 work units."""
    return BeadCreationResult(
        epic={"bd_id": "epic-1", "title": "add-user-auth"},
        work_beads=(
            {"bd_id": "bead-1", "title": "Add User model with email/password fields"},
            {"bd_id": "bead-2", "title": "Add registration endpoint"},
            {"bd_id": "bead-3", "title": "Add login endpoint returning session token"},
            {"bd_id": "bead-4", "title": "Add authentication middleware"},
        ),
        created_map={
            "Add User model with email/password fields": "bead-1",
            "Add registration endpoint": "bead-2",
            "Add login endpoint returning session token": "bead-3",
            "Add authentication middleware": "bead-4",
        },
        errors=(),
    )


def make_wire_result() -> DependencyWiringResult:
    """Return a sample DependencyWiringResult."""
    return DependencyWiringResult(
        dependencies=(
            {"from": "bead-2", "to": "bead-1"},
            {"from": "bead-3", "to": "bead-1"},
            {"from": "bead-4", "to": "bead-3"},
        ),
        errors=(),
        success=True,
    )


# ---------------------------------------------------------------------------
# Shared helpers (used by test_workflow.py and test_workflow_edge_cases.py)
# ---------------------------------------------------------------------------


async def collect_events(
    workflow: RefuelMaverickWorkflow,
    inputs: dict[str, Any],
    *,
    ignore_exception: bool = False,
) -> tuple[list[Any], Any]:
    """Drain the execute() generator and return (events, workflow.result)."""
    events: list[Any] = []
    try:
        async for event in workflow.execute(inputs):
            events.append(event)
    except Exception:
        if not ignore_exception:
            raise
    return events, workflow.result


def make_workflow(
    mock_config: MagicMock,
    **_kwargs: Any,
) -> RefuelMaverickWorkflow:
    """Create a RefuelMaverickWorkflow with the given mocks."""
    return RefuelMaverickWorkflow(
        config=mock_config,
    )


def patch_cwd(tmp_path: Path) -> Any:
    """Return a context manager that patches Path.cwd() to return tmp_path."""
    return patch("pathlib.Path.cwd", return_value=tmp_path)


def patch_decompose_supervisor(
    decomp: DecompositionOutput | None = None,
    *,
    bead_result: BeadCreationResult | None = None,
    dep_result: DependencyWiringResult | None = None,
) -> Any:
    """Return a context manager that patches _run_with_xoscar.

    The xoscar actor path is now the only decomposition path AND the
    only bead-creation path. The real ``_run_with_xoscar`` populates
    ``ctx`` with the supervisor's bead-creation outputs (epic, work
    beads, created_map, dependencies) so the workflow's downstream
    steps can adopt them instead of re-running ``create_beads``. The
    mock here mirrors that contract: it stashes ``bead_result`` and
    ``dep_result`` into the ``ctx`` keys the workflow reads.
    """
    if decomp is None:
        decomp = make_simple_decomposition_output()
    if bead_result is None:
        bead_result = make_bead_result()
    if dep_result is None:
        dep_result = make_wire_result()

    async def _fake_run_with_xoscar(
        self: Any,
        *args: Any,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> DecompositionOutput:
        if ctx is not None:
            epic = bead_result.epic
            ctx["fix_rounds"] = 0
            ctx["supervisor_epic"] = epic
            ctx["supervisor_epic_id"] = epic["bd_id"] if epic else ""
            ctx["supervisor_work_beads"] = list(bead_result.work_beads)
            ctx["supervisor_created_map"] = dict(bead_result.created_map)
            ctx["supervisor_dependencies"] = list(dep_result.dependencies)
            ctx["supervisor_deps_wired"] = len(dep_result.dependencies)
        return decomp

    return patch(
        "maverick.workflows.refuel_maverick.workflow.RefuelMaverickWorkflow._run_with_xoscar",
        new=_fake_run_with_xoscar,
    )


# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------
