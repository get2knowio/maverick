"""Unit tests for RefuelMaverickWorkflow."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from maverick.events import (
    StepCompleted,
    StepStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.library.actions.decompose import CodebaseContext
from maverick.workflows.refuel_maverick.constants import (
    CREATE_BEADS,
    DETAIL_SESSION_MAX_TURNS,
    FIX_SESSION_MAX_TURNS,
    GATHER_CONTEXT,
    PARSE_FLIGHT_PLAN,
    WIRE_DEPS,
    WORKFLOW_NAME,
    WRITE_WORK_UNITS,
)
from tests.unit.workflows.refuel_maverick.conftest import (
    collect_events,
    make_bead_result,
    make_simple_decomposition_output,
    make_simple_flight_plan,
    make_wire_result,
    make_workflow,
    patch_cwd,
    patch_decompose_supervisor,
)

_MODULE = "maverick.workflows.refuel_maverick.workflow"

# Step order constants — decompose + validate now run inside the Thespian
# supervisor (_run_with_thespian) so their events are not visible
# when that method is mocked.
_OUTER_STEPS = [
    PARSE_FLIGHT_PLAN,
    GATHER_CONTEXT,
    WRITE_WORK_UNITS,
    CREATE_BEADS,
    WIRE_DEPS,
]
_EMPTY_CONTEXT = CodebaseContext(files=(), missing_files=(), total_size=0)


# ---------------------------------------------------------------------------
# Happy path tests
# ---------------------------------------------------------------------------


class TestRefuelMaverickWorkflowHappyPath:
    """Tests for the full workflow happy path."""

    async def test_all_7_steps_execute(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """All 7 steps produce StepCompleted events."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry)
        bead_result = make_bead_result()
        wire_result = make_wire_result()

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=bead_result)),
            patch(f"{_MODULE}.wire_dependencies", new=AsyncMock(return_value=wire_result)),
            patch_decompose_supervisor(),
        ):
            events, result = await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "skip_briefing": True},
            )

        # StepStarted events for outer steps (decompose/validate run inside Thespian)
        started_names = [e.step_name for e in events if isinstance(e, StepStarted)]
        for step in _OUTER_STEPS:
            assert step in started_names, f"Expected StepStarted for {step}"

        # StepCompleted events for outer steps
        completed_names = [e.step_name for e in events if isinstance(e, StepCompleted)]
        for step in _OUTER_STEPS:
            assert step in completed_names, f"Expected StepCompleted for {step}"

    async def test_result_fields_populated_correctly(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """RefuelMaverickResult fields are populated correctly after a full run."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry)
        bead_result = make_bead_result()
        wire_result = make_wire_result()

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=bead_result)),
            patch(f"{_MODULE}.wire_dependencies", new=AsyncMock(return_value=wire_result)),
            patch_decompose_supervisor(),
        ):
            _events, workflow_result = await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "skip_briefing": True},
            )

        assert workflow_result is not None
        assert workflow_result.success is True
        final = workflow_result.final_output
        assert final["work_units_written"] == 4
        assert ".maverick/plans/add-user-auth" in final["work_units_dir"]
        assert final["epic"] == {"bd_id": "epic-1", "title": "add-user-auth"}
        assert len(final["work_beads"]) == 4
        assert isinstance(final["errors"], list)

    async def test_decompose_supervisor_called(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """_run_with_thespian is called during the workflow."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry)
        bead_result = make_bead_result()
        wire_result = make_wire_result()

        mock_decompose = AsyncMock(
            return_value=__import__(
                "tests.unit.workflows.refuel_maverick.conftest", fromlist=["x"]
            ).make_simple_decomposition_output()
        )

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=bead_result)),
            patch(f"{_MODULE}.wire_dependencies", new=AsyncMock(return_value=wire_result)),
            patch.object(workflow, "_run_with_thespian", new=mock_decompose),
        ):
            await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "skip_briefing": True},
            )

        mock_decompose.assert_called_once()

    async def test_run_with_thespian_passes_internal_session_thresholds(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Decomposer actor init receives the internal detail/fix thresholds."""

        class _FakeActorSystem:
            def __init__(self) -> None:
                self.asks: list[tuple[object, dict, int]] = []
                self.tell_calls: list[tuple[object, object]] = []
                self._counter = 0

            def createActor(self, _cls, globalName=None):  # noqa: N802
                self._counter += 1
                return globalName or f"actor-{self._counter}"

            def ask(self, addr, message, timeout):
                self.asks.append((addr, message, timeout))
                return {"type": "init_ok"}

            def tell(self, addr, message):
                self.tell_calls.append((addr, message))

            def shutdown(self):
                return None

        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry)
        fake_asys = _FakeActorSystem()
        flight_plan = await __import__(
            "maverick.flight.loader",
            fromlist=["FlightPlanFile"],
        ).FlightPlanFile.aload(fp)

        with (
            patch_cwd(tmp_path),
            patch(
                "maverick.agents.briefing.prompts.build_briefing_prompt",
                return_value="briefing prompt",
            ),
            patch("maverick.actors.create_actor_system", return_value=fake_asys),
            patch.object(workflow, "emit_output", new=AsyncMock()),
            patch.object(workflow, "emit_step_completed", new=AsyncMock()),
            patch.object(
                workflow,
                "_drain_supervisor_events",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "specs": make_simple_decomposition_output().work_units,
                    }
                ),
            ),
        ):
            await workflow._run_with_thespian(
                flight_plan=flight_plan,
                raw_content=fp.read_text(encoding="utf-8"),
                codebase_context=_EMPTY_CONTEXT,
                open_bead_result=None,
                runway_context_text=None,
                run_dir=None,
                skip_briefing=True,
            )

        decomposer_inits = [
            message
            for _addr, message, _timeout in fake_asys.asks
            if message.get("type") == "init" and message.get("role") in {"primary", "pool"}
        ]
        assert decomposer_inits
        assert all(
            msg["detail_session_max_turns"] == DETAIL_SESSION_MAX_TURNS
            for msg in decomposer_inits
        )
        assert all(
            msg["fix_session_max_turns"] == FIX_SESSION_MAX_TURNS
            for msg in decomposer_inits
        )

    async def test_work_unit_files_written_with_correct_naming(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Work unit files use {seq:03d}-{id}.md naming inside .maverick/plans/."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry)
        bead_result = make_bead_result()
        wire_result = make_wire_result()

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=bead_result)),
            patch(f"{_MODULE}.wire_dependencies", new=AsyncMock(return_value=wire_result)),
            patch_decompose_supervisor(),
        ):
            await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "skip_briefing": True},
            )

        work_units_dir = tmp_path / ".maverick" / "plans" / "add-user-auth"
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
        tmp_path: Path,
    ) -> None:
        """WorkflowStarted is the first event and WorkflowCompleted is the last."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry)
        bead_result = make_bead_result()
        wire_result = make_wire_result()

        with (
            patch_cwd(tmp_path),
            patch(
                f"{_MODULE}.gather_codebase_context",
                new=AsyncMock(return_value=_EMPTY_CONTEXT),
            ),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=bead_result)),
            patch(f"{_MODULE}.wire_dependencies", new=AsyncMock(return_value=wire_result)),
            patch_decompose_supervisor(),
        ):
            events, result = await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "skip_briefing": True},
            )

        assert isinstance(events[0], WorkflowStarted)
        assert events[0].workflow_name == WORKFLOW_NAME
        assert isinstance(events[-1], WorkflowCompleted)
        assert events[-1].success is True

    async def test_wire_dependencies_receives_extracted_deps_from_work_units(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """wire_dependencies is called with extracted_deps built from depends_on."""
        fp = make_simple_flight_plan(tmp_path)
        workflow = make_workflow(mock_config, mock_registry)
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
            patch_decompose_supervisor(),
        ):
            await collect_events(
                workflow,
                {"flight_plan_path": str(fp), "skip_briefing": True},
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
        missing_path = tmp_path / ".maverick" / "plans" / "does-not-exist" / "flight-plan.md"

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
