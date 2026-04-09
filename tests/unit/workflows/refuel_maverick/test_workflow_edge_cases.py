"""Edge case tests for RefuelMaverickWorkflow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.exceptions import WorkflowError
from maverick.executor.protocol import StepExecutor
from maverick.library.actions.decompose import CodebaseContext
from maverick.library.actions.types import BeadCreationResult, DependencyWiringResult
from maverick.workflows.refuel_maverick.constants import (
    VALIDATE,
)
from maverick.workflows.refuel_maverick.models import (
    AcceptanceCriterionSpec,
    DecompositionOutput,
    FileScopeSpec,
    WorkUnitSpec,
)
from tests.unit.workflows.refuel_maverick.conftest import (
    collect_events,
    decomposition_to_two_pass_results,
    make_workflow,
    patch_cwd,
)

_MODULE = "maverick.workflows.refuel_maverick.workflow"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_flight_plan_file(tmp_path: Path, name: str = "test-plan") -> Path:
    """Create a minimal valid flight plan file."""
    content = f"""\
---
name: {name}
version: "1.0"
created: 2026-02-27
tags: []
---

## Objective
Test objective.

## Success Criteria
- [ ] Test criterion 1
- [ ] Test criterion 2

## Scope

### In
- src/test.py

### Out
- src/excluded.py

### Boundaries
- src/config.py (protect)
"""
    fp_dir = tmp_path / ".maverick" / "plans" / name
    fp_dir.mkdir(parents=True, exist_ok=True)
    fp = fp_dir / "flight-plan.md"
    fp.write_text(content, encoding="utf-8")
    return fp


def _make_simple_decomp(num_units: int = 2) -> DecompositionOutput:
    """Make a simple linear decomposition with the given number of work units."""
    units = []
    for i in range(1, num_units + 1):
        wu_id = f"unit-{i:02d}"
        deps = [f"unit-{i - 1:02d}"] if i > 1 else []
        units.append(
            WorkUnitSpec(
                id=wu_id,
                sequence=i,
                depends_on=deps,
                task=f"Task {i}",
                acceptance_criteria=[
                    AcceptanceCriterionSpec(text=f"Criterion {i}", trace_ref=f"SC-{i:03d}")
                ],
                file_scope=FileScopeSpec(protect=["src/config.py"]),
                instructions=f"Do task {i}",
                verification=["make test"],
            )
        )
    return DecompositionOutput(work_units=units, rationale="Linear decomposition")


def _make_parallel_decomp() -> DecompositionOutput:
    """Make a complex decomposition with parallel groups."""
    return DecompositionOutput(
        work_units=[
            WorkUnitSpec(
                id="setup-models",
                sequence=1,
                parallel_group=None,
                depends_on=[],
                task="Setup base models",
                acceptance_criteria=[
                    AcceptanceCriterionSpec(text="Models created", trace_ref="SC-001")
                ],
                file_scope=FileScopeSpec(protect=["src/config.py"]),
                instructions="Create models",
                verification=["make test"],
            ),
            WorkUnitSpec(
                id="add-payments",
                sequence=2,
                parallel_group="group-a",
                depends_on=["setup-models"],
                task="Add payment processing",
                acceptance_criteria=[
                    AcceptanceCriterionSpec(text="Payments work", trace_ref="SC-001")
                ],
                file_scope=FileScopeSpec(protect=["src/config.py"]),
                instructions="Add payments",
                verification=["make test"],
            ),
            WorkUnitSpec(
                id="add-refunds",
                sequence=3,
                parallel_group="group-a",
                depends_on=["setup-models"],
                task="Add refund workflow",
                acceptance_criteria=[
                    AcceptanceCriterionSpec(text="Refunds work", trace_ref="SC-002")
                ],
                file_scope=FileScopeSpec(protect=["src/config.py"]),
                instructions="Add refunds",
                verification=["make test"],
            ),
            WorkUnitSpec(
                id="wire-together",
                sequence=4,
                parallel_group=None,
                depends_on=["add-payments", "add-refunds"],
                task="Wire everything together",
                acceptance_criteria=[
                    AcceptanceCriterionSpec(text="All connected", trace_ref="SC-001")
                ],
                file_scope=FileScopeSpec(protect=["src/config.py"]),
                instructions="Wire up",
                verification=["make test"],
            ),
        ],
        rationale="Parallel groups for independent components",
    )


def _make_bead_result(num_work_beads: int = 2) -> BeadCreationResult:
    work_beads = tuple(
        {"bd_id": f"bead-{i}", "title": f"Bead {i}"} for i in range(1, num_work_beads + 1)
    )
    created_map = {f"Bead {i}": f"bead-{i}" for i in range(1, num_work_beads + 1)}
    return BeadCreationResult(
        epic={"bd_id": "epic-1", "title": "test-plan"},
        work_beads=work_beads,
        created_map=created_map,
        errors=(),
    )


def _make_wire_result() -> DependencyWiringResult:
    return DependencyWiringResult(
        dependencies=(),
        errors=(),
        success=True,
    )


# ---------------------------------------------------------------------------
# Error handling tests (T019)
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Edge case and error path tests."""

    async def test_malformed_flight_plan_raises_clear_error(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Flight plan parse error surfaces as workflow failure."""
        fp = tmp_path / "bad-plan.md"
        fp.write_text("This is not a valid flight plan YAML frontmatter.", encoding="utf-8")

        workflow = make_workflow(mock_config, mock_registry, mock_step_executor)

        events, result = await collect_events(
            workflow,
            {"flight_plan_path": str(fp), "skip_briefing": True},
            ignore_exception=True,
        )

        assert result is not None
        assert result.success is False
        failed_steps = [s for s in result.step_results if not s.success]
        assert len(failed_steps) >= 1

    async def test_missing_flight_plan_path_raises_workflow_error(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """Missing flight_plan_path input raises WorkflowError."""
        workflow = make_workflow(mock_config, mock_registry)

        with pytest.raises(WorkflowError, match="flight_plan_path"):
            async for _ in workflow.execute({}):
                pass

    async def test_nonexistent_flight_plan_file_raises(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Non-existent flight plan file path results in a failed workflow."""
        workflow = make_workflow(mock_config, mock_registry, mock_step_executor)

        events, result = await collect_events(
            workflow,
            {"flight_plan_path": str(tmp_path / "nonexistent.md")},
            ignore_exception=True,
        )

        assert result is not None
        assert result.success is False
        failed_steps = [s for s in result.step_results if not s.success]
        assert len(failed_steps) >= 1

    async def test_circular_dependency_detected_before_bead_creation(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Circular dependency detected and reported before bead creation."""
        fp = _make_flight_plan_file(tmp_path)

        # Create decomposition with circular dependency
        circular_decomp = DecompositionOutput(
            work_units=[
                WorkUnitSpec(
                    id="unit-a",
                    sequence=1,
                    depends_on=["unit-b"],
                    task="Task A",
                    acceptance_criteria=[
                        AcceptanceCriterionSpec(text="A done", trace_ref="SC-001")
                    ],
                    file_scope=FileScopeSpec(),
                    instructions="Do A",
                    verification=["test"],
                ),
                WorkUnitSpec(
                    id="unit-b",
                    sequence=2,
                    depends_on=["unit-a"],
                    task="Task B",
                    acceptance_criteria=[
                        AcceptanceCriterionSpec(text="B done", trace_ref="SC-002")
                    ],
                    file_scope=FileScopeSpec(),
                    instructions="Do B",
                    verification=["test"],
                ),
            ],
            rationale="Circular",
        )

        executor = AsyncMock(spec=StepExecutor)
        executor.execute.side_effect = decomposition_to_two_pass_results(circular_decomp)
        workflow = make_workflow(mock_config, mock_registry, executor)

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(
                    return_value=CodebaseContext(files=(), missing_files=(), total_size=0)
                ),
            ),
            patch(f"{_MODULE}.create_beads") as mock_create,
        ):
            with pytest.raises(WorkflowError, match="[Cc]ircular|[Dd]ependency|cycle"):
                inputs = {"flight_plan_path": str(fp), "skip_briefing": True}
                async for _ in workflow.execute(inputs):
                    pass

            # create_beads should NOT have been called (error in validate step)
            mock_create.assert_not_called()

    async def test_output_directory_cleared_before_writing(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Pre-existing work unit files in output dir are cleared before new write."""
        fp = _make_flight_plan_file(tmp_path)

        # Create pre-existing files in the output directory (same as plan dir)
        work_units_dir = tmp_path / ".maverick" / "plans" / "test-plan"
        work_units_dir.mkdir(parents=True, exist_ok=True)
        (work_units_dir / "001-old-unit.md").write_text("old content", encoding="utf-8")
        (work_units_dir / "002-another-old.md").write_text("another old", encoding="utf-8")

        workflow = make_workflow(mock_config, mock_registry, mock_step_executor)

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(
                    return_value=CodebaseContext(files=(), missing_files=(), total_size=0)
                ),
            ),
            patch(
                f"{_MODULE}.create_beads",
                new=AsyncMock(return_value=_make_bead_result(2)),
            ),
            patch(
                f"{_MODULE}.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": False, "skip_briefing": True},
            )

        # Old work unit files should be gone
        files = list(work_units_dir.iterdir())
        assert not any(f.name == "001-old-unit.md" for f in files)
        assert not any(f.name == "002-another-old.md" for f in files)

    async def test_empty_in_scope_produces_empty_codebase_context(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Empty in_scope list produces empty CodebaseContext (no crash)."""
        # Create a flight plan with empty in_scope
        content = """\
---
name: empty-scope-plan
version: "1.0"
created: 2026-02-27
tags: []
---

## Objective
Test objective.

## Success Criteria
- [ ] Test criterion 1

## Scope

### In

### Out

### Boundaries
"""
        fp_dir = tmp_path / ".maverick" / "plans" / "empty-scope-plan"
        fp_dir.mkdir(parents=True, exist_ok=True)
        fp = fp_dir / "flight-plan.md"
        fp.write_text(content, encoding="utf-8")

        # Decomp output for this plan — covers SC-001
        decomp = DecompositionOutput(
            work_units=[
                WorkUnitSpec(
                    id="single-unit",
                    sequence=1,
                    task="Do something",
                    acceptance_criteria=[AcceptanceCriterionSpec(text="Done", trace_ref="SC-001")],
                    file_scope=FileScopeSpec(),
                    instructions="Do it",
                    verification=["test"],
                )
            ],
            rationale="Single unit",
        )
        executor = AsyncMock(spec=StepExecutor)
        executor.execute.side_effect = decomposition_to_two_pass_results(decomp)
        workflow = make_workflow(mock_config, mock_registry, executor)

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.create_beads",
                new=AsyncMock(return_value=_make_bead_result(1)),
            ),
            patch(
                f"{_MODULE}.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            events, result = await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": False, "skip_briefing": True},
            )

        # Should succeed without error
        assert result is not None
        assert result.success is True
        assert result.final_output["work_units_written"] == 1

    async def test_agent_failure_after_retry_exhaustion(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Agent failure after all retries are exhausted fails the workflow."""
        fp = _make_flight_plan_file(tmp_path)

        executor = AsyncMock(spec=StepExecutor)
        # Raise a transient error on every attempt
        executor.execute.side_effect = TimeoutError("API timeout")
        workflow = make_workflow(mock_config, mock_registry, executor)

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(
                    return_value=CodebaseContext(files=(), missing_files=(), total_size=0)
                ),
            ),
        ):
            events, result = await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "skip_briefing": True},
                ignore_exception=True,
            )

        assert result is not None
        assert result.success is False

    async def test_bd_unavailability_fails_create_beads_step(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """bd system unavailability fails the create_beads step."""
        fp = _make_flight_plan_file(tmp_path)
        workflow = make_workflow(mock_config, mock_registry, mock_step_executor)

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(
                    return_value=CodebaseContext(files=(), missing_files=(), total_size=0)
                ),
            ),
            patch(
                f"{_MODULE}.create_beads",
                new=AsyncMock(side_effect=RuntimeError("bd: command not found")),
            ),
        ):
            events, result = await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": False, "skip_briefing": True},
                ignore_exception=True,
            )

        assert result is not None
        assert result.success is False

    async def test_dangling_depends_on_detected_before_bead_creation(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Dangling depends_on reference detected and reported before bead creation."""
        fp = _make_flight_plan_file(tmp_path)

        dangling_decomp = DecompositionOutput(
            work_units=[
                WorkUnitSpec(
                    id="unit-a",
                    sequence=1,
                    depends_on=["nonexistent-unit"],
                    task="Task A",
                    acceptance_criteria=[
                        AcceptanceCriterionSpec(text="A done", trace_ref="SC-001")
                    ],
                    file_scope=FileScopeSpec(),
                    instructions="Do A",
                    verification=["test"],
                ),
            ],
            rationale="Dangling",
        )

        executor = AsyncMock(spec=StepExecutor)
        executor.execute.side_effect = decomposition_to_two_pass_results(dangling_decomp)
        workflow = make_workflow(mock_config, mock_registry, executor)

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(
                    return_value=CodebaseContext(files=(), missing_files=(), total_size=0)
                ),
            ),
            patch(f"{_MODULE}.create_beads") as mock_create,
        ):
            with pytest.raises(WorkflowError):
                inputs = {"flight_plan_path": str(fp), "skip_briefing": True}
                async for _ in workflow.execute(inputs):
                    pass
            mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# Parallel group tests (T016)
# ---------------------------------------------------------------------------


class TestParallelGroups:
    """Tests for parallel group handling in decomposition."""

    async def test_parallel_groups_in_decomposition_output(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Work units with parallel_group produce valid work unit files."""
        fp = _make_flight_plan_file(tmp_path)

        parallel_decomp = _make_parallel_decomp()
        executor = AsyncMock(spec=StepExecutor)
        executor.execute.side_effect = decomposition_to_two_pass_results(parallel_decomp)
        workflow = make_workflow(mock_config, mock_registry, executor)

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(
                    return_value=CodebaseContext(files=(), missing_files=(), total_size=0)
                ),
            ),
            patch(
                f"{_MODULE}.create_beads",
                new=AsyncMock(return_value=_make_bead_result(4)),
            ),
            patch(
                f"{_MODULE}.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            events, result = await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": False, "skip_briefing": True},
            )

        # 4 work units written
        assert result is not None
        assert result.final_output["work_units_written"] == 4

    async def test_parallel_groups_validation_passes(self) -> None:
        """Parallel groups with proper dependencies pass validation."""
        from maverick.library.actions.decompose import validate_decomposition

        parallel_decomp = _make_parallel_decomp()

        # Validate the parallel decomposition - should not raise
        warnings = validate_decomposition(
            parallel_decomp.work_units,
            success_criteria_count=2,
        )

        # SC-001 and SC-002 are covered
        assert len(warnings) == 0

    async def test_independent_parallel_units_same_group(self) -> None:
        """Independent units within same group have no inter-dependencies."""
        parallel_decomp = _make_parallel_decomp()

        # add-payments and add-refunds are in group-a; no inter-dependencies
        group_a_units = [wu for wu in parallel_decomp.work_units if wu.parallel_group == "group-a"]
        assert len(group_a_units) == 2

        add_payments = next(wu for wu in group_a_units if wu.id == "add-payments")
        add_refunds = next(wu for wu in group_a_units if wu.id == "add-refunds")

        # They should not depend on each other
        assert "add-refunds" not in add_payments.depends_on
        assert "add-payments" not in add_refunds.depends_on

    async def test_validate_step_result_contains_parallel_group_count(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """validate step StepResult output contains correct parallel_group_count."""
        fp = _make_flight_plan_file(tmp_path)

        parallel_decomp = _make_parallel_decomp()
        executor = AsyncMock(spec=StepExecutor)
        executor.execute.side_effect = decomposition_to_two_pass_results(parallel_decomp)
        workflow = make_workflow(mock_config, mock_registry, executor)

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(
                    return_value=CodebaseContext(files=(), missing_files=(), total_size=0)
                ),
            ),
            patch(
                f"{_MODULE}.create_beads",
                new=AsyncMock(return_value=_make_bead_result(4)),
            ),
            patch(
                f"{_MODULE}.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            events, result = await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": False, "skip_briefing": True},
            )

        # Parallel group count is in StepResult output, not StepCompleted event.
        # StepCompleted has no output field — use workflow.result.step_results.
        assert result is not None
        validate_step_result = next(sr for sr in result.step_results if sr.name == VALIDATE)
        assert validate_step_result.output is not None
        # group-a is the only named parallel group
        assert validate_step_result.output.get("parallel_group_count", 0) >= 1

    async def test_parallel_groups_file_naming_uses_sequence(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Work unit files in parallel groups use their sequence numbers for naming."""
        fp = _make_flight_plan_file(tmp_path)

        parallel_decomp = _make_parallel_decomp()
        executor = AsyncMock(spec=StepExecutor)
        executor.execute.side_effect = decomposition_to_two_pass_results(parallel_decomp)
        workflow = make_workflow(mock_config, mock_registry, executor)

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(
                    return_value=CodebaseContext(files=(), missing_files=(), total_size=0)
                ),
            ),
            patch(
                f"{_MODULE}.create_beads",
                new=AsyncMock(return_value=_make_bead_result(4)),
            ),
            patch(
                f"{_MODULE}.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": False, "skip_briefing": True},
            )

        work_units_dir = tmp_path / ".maverick" / "plans" / "test-plan"
        assert work_units_dir.exists()
        files = sorted(work_units_dir.glob("[0-9][0-9][0-9]-*.md"))
        assert len(files) == 4
        # Sequence numbers preserved in filenames
        assert files[0].name == "001-setup-models.md"
        assert files[1].name == "002-add-payments.md"
        assert files[2].name == "003-add-refunds.md"
        assert files[3].name == "004-wire-together.md"


# ---------------------------------------------------------------------------
# Protect boundary propagation tests (SC-005)
# ---------------------------------------------------------------------------


class TestProtectBoundaryPropagation:
    """Tests for SC-005: protect boundaries propagated to every work unit."""

    async def test_protect_boundaries_in_all_work_unit_specs(self) -> None:
        """Every work unit in sample decomposition includes protect boundary."""
        from tests.unit.workflows.refuel_maverick.conftest import (
            make_simple_decomposition_output,
        )

        decomp = make_simple_decomposition_output()
        for wu in decomp.work_units:
            assert "src/config.py" in wu.file_scope.protect, (
                f"Work unit {wu.id!r} missing protect boundary"
            )

    async def test_converted_work_units_preserve_protect(self) -> None:
        """protect list is preserved after conversion to WorkUnit models."""
        from maverick.library.actions.decompose import convert_specs_to_work_units
        from tests.unit.workflows.refuel_maverick.conftest import (
            make_simple_decomposition_output,
        )

        decomp = make_simple_decomposition_output()
        units = convert_specs_to_work_units(decomp.work_units, flight_plan_name="test")
        for unit in units:
            assert "src/config.py" in unit.file_scope.protect, (
                f"WorkUnit {unit.id!r} missing protect boundary after conversion"
            )
