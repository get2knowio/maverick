"""Unit tests for RefuelMaverickWorkflow."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from maverick.dsl.events import (
    StepCompleted,
    StepStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.library.actions.decompose import CodebaseContext
from maverick.workflows.refuel_maverick.constants import (
    CREATE_BEADS,
    DECOMPOSE,
    GATHER_CONTEXT,
    PARSE_FLIGHT_PLAN,
    VALIDATE,
    WIRE_DEPS,
    WORKFLOW_NAME,
    WRITE_WORK_UNITS,
)
from tests.unit.workflows.refuel_maverick.conftest import (
    collect_events,
    make_bead_result,
    make_simple_flight_plan,
    make_wire_result,
    make_workflow,
    patch_cwd,
)

_MODULE = "maverick.workflows.refuel_maverick.workflow"

# Step order constants
_ALL_STEPS = [
    PARSE_FLIGHT_PLAN,
    GATHER_CONTEXT,
    DECOMPOSE,
    VALIDATE,
    WRITE_WORK_UNITS,
    CREATE_BEADS,
    WIRE_DEPS,
]
_DRY_RUN_STEPS = [
    PARSE_FLIGHT_PLAN,
    GATHER_CONTEXT,
    DECOMPOSE,
    VALIDATE,
    WRITE_WORK_UNITS,
]

_EMPTY_CONTEXT = CodebaseContext(files=(), missing_files=(), total_size=0)


# ---------------------------------------------------------------------------
# Happy path tests
# ---------------------------------------------------------------------------


class TestRefuelMaverickWorkflowHappyPath:
    """Tests for the full (non-dry-run) workflow happy path."""

    async def test_all_7_steps_execute(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """All 7 steps produce StepCompleted events in the non-dry-run path."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry, mock_step_executor)
        bead_result = make_bead_result()
        wire_result = make_wire_result()

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=bead_result)),
            patch(
                f"{_MODULE}.wire_dependencies", new=AsyncMock(return_value=wire_result)
            ),
        ):
            events, result = await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": False},
            )

        # StepStarted events for all 7 steps
        started_names = [e.step_name for e in events if isinstance(e, StepStarted)]
        for step in _ALL_STEPS:
            assert step in started_names, f"Expected StepStarted for {step}"

        # StepCompleted events for all 7 steps
        completed_names = [e.step_name for e in events if isinstance(e, StepCompleted)]
        for step in _ALL_STEPS:
            assert step in completed_names, f"Expected StepCompleted for {step}"

    async def test_result_fields_populated_correctly(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """RefuelMaverickResult fields are populated correctly after a full run."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry, mock_step_executor)
        bead_result = make_bead_result()
        wire_result = make_wire_result()

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=bead_result)),
            patch(
                f"{_MODULE}.wire_dependencies", new=AsyncMock(return_value=wire_result)
            ),
        ):
            _events, workflow_result = await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": False},
            )

        assert workflow_result is not None
        assert workflow_result.success is True
        final = workflow_result.final_output
        assert final["work_units_written"] == 4
        assert ".maverick/work-units/add-user-auth" in final["work_units_dir"]
        assert final["epic"] == {"bd_id": "epic-1", "title": "add-user-auth"}
        assert len(final["work_beads"]) == 4
        assert final["dry_run"] is False
        assert isinstance(final["errors"], list)

    async def test_step_executor_called_with_decomposition_schema(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """StepExecutor.execute() is called with DecompositionOutput as output_schema."""  # noqa: E501
        from maverick.workflows.refuel_maverick.models import DecompositionOutput

        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry, mock_step_executor)
        bead_result = make_bead_result()
        wire_result = make_wire_result()

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=bead_result)),
            patch(
                f"{_MODULE}.wire_dependencies", new=AsyncMock(return_value=wire_result)
            ),
        ):
            await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": False},
            )

        mock_step_executor.execute.assert_called_once()
        call_kwargs = mock_step_executor.execute.call_args.kwargs
        assert call_kwargs["output_schema"] is DecompositionOutput
        assert call_kwargs["step_name"] == DECOMPOSE

    async def test_work_unit_files_written_with_correct_naming(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Work unit files use {seq:03d}-{id}.md naming inside .maverick/work-units/."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry, mock_step_executor)
        bead_result = make_bead_result()
        wire_result = make_wire_result()

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=bead_result)),
            patch(
                f"{_MODULE}.wire_dependencies", new=AsyncMock(return_value=wire_result)
            ),
        ):
            await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": False},
            )

        work_units_dir = tmp_path / ".maverick" / "work-units" / "add-user-auth"
        assert work_units_dir.exists(), f"Expected {work_units_dir} to exist"
        files = sorted(work_units_dir.glob("[0-9][0-9][0-9]-*.md"))
        assert len(files) == 4
        assert files[0].name == "001-add-user-model.md"
        assert files[1].name == "002-add-registration-endpoint.md"
        assert files[2].name == "003-add-login-endpoint.md"
        assert files[3].name == "004-add-auth-middleware.md"

    async def test_workflow_name(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """Workflow has the correct _workflow_name constant."""
        workflow = make_workflow(mock_config, mock_registry)
        assert workflow._workflow_name == WORKFLOW_NAME

    async def test_workflow_started_and_completed_events(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """WorkflowStarted is the first event and WorkflowCompleted is the last."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry, mock_step_executor)
        bead_result = make_bead_result()
        wire_result = make_wire_result()

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=bead_result)),
            patch(
                f"{_MODULE}.wire_dependencies", new=AsyncMock(return_value=wire_result)
            ),
        ):
            events, result = await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": False},
            )

        assert isinstance(events[0], WorkflowStarted)
        assert events[0].workflow_name == WORKFLOW_NAME
        assert isinstance(events[-1], WorkflowCompleted)
        assert events[-1].success is True

    async def test_wire_dependencies_receives_extracted_deps_from_work_units(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """wire_dependencies is called with extracted_deps built from depends_on."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry, mock_step_executor)
        bead_result = make_bead_result()
        wire_result = make_wire_result()

        mock_wire = AsyncMock(return_value=wire_result)
        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=bead_result)),
            patch(f"{_MODULE}.wire_dependencies", new=mock_wire),
        ):
            await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": False},
            )

        mock_wire.assert_called_once()
        call_kwargs = mock_wire.call_args.kwargs
        extracted = call_kwargs["extracted_deps"]
        assert extracted, "extracted_deps should not be empty"

        dep_pairs = json.loads(extracted)
        # The conftest fixture has 3 dependency relationships:
        # add-registration-endpoint -> add-user-model
        # add-login-endpoint -> add-user-model
        # add-auth-middleware -> add-login-endpoint
        assert len(dep_pairs) == 3
        assert ["add-registration-endpoint", "add-user-model"] in dep_pairs
        assert ["add-login-endpoint", "add-user-model"] in dep_pairs
        assert ["add-auth-middleware", "add-login-endpoint"] in dep_pairs


# ---------------------------------------------------------------------------
# Dry-run mode tests
# ---------------------------------------------------------------------------


class TestDryRunMode:
    """Tests for dry-run mode (steps 1-5 only; steps 6-7 skipped)."""

    async def test_dry_run_skips_create_beads_and_wire_deps(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """create_beads and wire_dependencies are NOT called in dry-run mode."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry, mock_step_executor)

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads") as mock_create,
            patch(f"{_MODULE}.wire_dependencies") as mock_wire,
        ):
            await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": True},
            )

        mock_create.assert_not_called()
        mock_wire.assert_not_called()

    async def test_dry_run_work_unit_files_still_written(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Work unit files ARE written in dry-run mode (steps 1-5 execute normally)."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry, mock_step_executor)

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads"),
            patch(f"{_MODULE}.wire_dependencies"),
        ):
            await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": True},
            )

        work_units_dir = tmp_path / ".maverick" / "work-units" / "add-user-auth"
        assert work_units_dir.exists(), f"Expected {work_units_dir} to exist"
        files = list(work_units_dir.glob("[0-9][0-9][0-9]-*.md"))
        assert len(files) == 4

    async def test_dry_run_result_fields(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """RefuelMaverickResult has correct field values in dry-run mode."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry, mock_step_executor)

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads"),
            patch(f"{_MODULE}.wire_dependencies"),
        ):
            _events, workflow_result = await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": True},
            )

        assert workflow_result is not None
        assert workflow_result.success is True
        final = workflow_result.final_output
        assert final["dry_run"] is True
        assert final["epic"] is None
        assert final["work_beads"] == []
        assert final["dependencies"] == []
        assert final["work_units_written"] == 4

    async def test_dry_run_steps_1_to_5_in_completed_events(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Steps 1-5 have StepCompleted events; steps 6-7 do not appear."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry, mock_step_executor)

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads"),
            patch(f"{_MODULE}.wire_dependencies"),
        ):
            events, _ = await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": True},
            )

        completed_names = {e.step_name for e in events if isinstance(e, StepCompleted)}
        for step in _DRY_RUN_STEPS:
            assert step in completed_names, f"Expected StepCompleted for {step}"
        assert CREATE_BEADS not in completed_names
        assert WIRE_DEPS not in completed_names

    async def test_dry_run_workflow_succeeds(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Workflow result is success=True in dry-run mode."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry, mock_step_executor)

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads"),
            patch(f"{_MODULE}.wire_dependencies"),
        ):
            events, result = await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": True},
            )

        assert result is not None
        assert result.success is True
        workflow_completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert workflow_completed.success is True


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error cases and edge conditions."""

    async def test_missing_flight_plan_path_fails_workflow(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """Omitting flight_plan_path results in a failed workflow."""
        workflow = make_workflow(mock_config, mock_registry)
        events, result = await collect_events(workflow, {}, ignore_exception=True)

        assert result is not None
        assert result.success is False
        workflow_completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert workflow_completed.success is False

    async def test_nonexistent_flight_plan_fails_workflow(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A non-existent flight plan path results in a failed parse_flight_plan step."""  # noqa: E501
        workflow = make_workflow(mock_config, mock_registry)
        missing_path = tmp_path / ".maverick" / "flight-plans" / "does-not-exist.md"

        events, result = await collect_events(
            workflow,
            {"flight_plan_path": str(missing_path)},
            ignore_exception=True,
        )

        assert result is not None
        assert result.success is False
        # parse_flight_plan step should have failed
        failed_steps = [s for s in result.step_results if not s.success]
        assert len(failed_steps) >= 1
        assert failed_steps[0].name == PARSE_FLIGHT_PLAN

    async def test_no_step_executor_fails_decompose(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Without a step_executor, the decompose step fails."""
        fp = make_simple_flight_plan(tmp_path)
        # No step_executor provided
        workflow = make_workflow(mock_config, mock_registry, step_executor=None)

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
        ):
            events, result = await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "dry_run": False},
                ignore_exception=True,
            )

        assert result is not None
        assert result.success is False
        failed_names = [s.name for s in result.step_results if not s.success]
        assert DECOMPOSE in failed_names
