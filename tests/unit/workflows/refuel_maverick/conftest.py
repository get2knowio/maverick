"""Shared test fixtures for RefuelMaverickWorkflow tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.dsl.executor.protocol import StepExecutor
from maverick.dsl.executor.result import ExecutorResult
from maverick.library.actions.types import BeadCreationResult, DependencyWiringResult
from maverick.workflows.refuel_maverick.models import (
    AcceptanceCriterionSpec,
    DecompositionOutput,
    FileScopeSpec,
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
    flight_plans_dir = tmp_path / ".maverick" / "flight-plans"
    flight_plans_dir.mkdir(parents=True)
    fp = flight_plans_dir / "add-user-auth.md"
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
                    AcceptanceCriterionSpec(
                        text="User model created", trace_ref="SC-001"
                    )
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
                    AcceptanceCriterionSpec(
                        text="Registration works", trace_ref="SC-001"
                    )
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
                    AcceptanceCriterionSpec(
                        text="Login returns token", trace_ref="SC-002"
                    )
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
    mock_registry: MagicMock,
    step_executor: Any = None,
) -> RefuelMaverickWorkflow:
    """Create a RefuelMaverickWorkflow with the given mocks."""
    return RefuelMaverickWorkflow(
        config=mock_config,
        registry=mock_registry,
        step_executor=step_executor,
    )


def patch_cwd(tmp_path: Path) -> Any:
    """Return a context manager that patches Path.cwd() to return tmp_path."""
    return patch("pathlib.Path.cwd", return_value=tmp_path)


# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_step_executor() -> AsyncMock:
    """Return an AsyncMock StepExecutor pre-configured with DecompositionOutput."""
    executor = AsyncMock(spec=StepExecutor)
    decomp = make_simple_decomposition_output()
    executor.execute.return_value = ExecutorResult(
        output=decomp,
        success=True,
        events=(),
        usage=None,
    )
    return executor
