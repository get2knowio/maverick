"""Unit tests for RefuelSpeckitWorkflow."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from maverick.events import (
    StepCompleted,
    StepStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.library.actions.types import (
    BeadCreationResult,
    DependencyWiringResult,
    SpecKitParseResult,
)
from maverick.workflows.refuel_speckit.constants import (
    CHECKOUT,
    CHECKOUT_MAIN,
    COMMIT,
    CREATE_BEADS,
    ENRICH_BEADS,
    EXTRACT_DEPS,
    MERGE,
    PARSE_SPEC,
    WIRE_DEPS,
    WORKFLOW_NAME,
)
from maverick.workflows.refuel_speckit.workflow import RefuelSpeckitWorkflow

# ---------------------------------------------------------------------------
# Helpers / constants
# ---------------------------------------------------------------------------

_SPEC = "001-test-spec"

_PARSE_RESULT = SpecKitParseResult(
    epic_definition={"title": "Epic", "bead_type": "EPIC"},
    work_definitions=({"title": "Work1", "bead_type": "TASK"},),
    tasks_content="# Tasks\n## Phase 1\n",
    dependency_section="",
)

_ENRICHED_DEFINITIONS = [{"title": "Work1 (enriched)", "description": "enriched desc"}]

_BEAD_RESULT = BeadCreationResult(
    epic={"id": "e1", "title": "Epic"},
    work_beads=({"id": "w1", "title": "Work1"},),
    created_map={"Work1": "w1"},
    errors=(),
)

_WIRE_RESULT = DependencyWiringResult(
    dependencies=(),
    errors=(),
    success=True,
)

_CHECKOUT_RESULT = {
    "success": True,
    "branch_name": _SPEC,
    "base_branch": "main",
    "created": True,
    "error": None,
}

_COMMIT_RESULT = {
    "success": True,
    "commit_sha": "abc123",
    "message": f"refuel(speckit): create beads for {_SPEC}",
    "files_committed": [".beads/issues.jsonl"],
    "error": None,
}

_MERGE_RESULT = {
    "success": True,
    "branch": _SPEC,
    "merge_commit": "def456",
    "error": None,
}


def _make_workflow(
    mock_config: MagicMock,
    mock_registry: MagicMock,
    step_executor: Any = None,
) -> RefuelSpeckitWorkflow:
    return RefuelSpeckitWorkflow(
        config=mock_config,
        registry=mock_registry,
        step_executor=step_executor,
    )


async def _collect_events(
    workflow: RefuelSpeckitWorkflow,
    inputs: dict[str, Any],
    *,
    ignore_exception: bool = False,
) -> tuple[list[Any], Any]:
    """Drain the execute() generator and return (events, workflow.result).

    When ignore_exception=True, swallows any exception re-raised by execute()
    after WorkflowCompleted (R-012 behaviour). Use this in tests that only need
    to verify the event stream and result, not the re-raise itself.
    """
    events = []
    try:
        async for event in workflow.execute(inputs):
            events.append(event)
    except Exception:
        if not ignore_exception:
            raise
    return events, workflow.result


# ---------------------------------------------------------------------------
# Patches helper
# ---------------------------------------------------------------------------

_MODULE = "maverick.workflows.refuel_speckit.workflow"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRefuelSpeckitWorkflow:
    """Tests for RefuelSpeckitWorkflow._run()."""

    async def test_happy_path(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """Full linear flow: checkout -> parse -> extract_deps -> enrich
        -> create_beads -> wire_deps -> commit -> checkout_main -> merge."""
        workflow = _make_workflow(mock_config, mock_registry)

        with (
            patch(
                f"{_MODULE}.create_git_branch",
                new=AsyncMock(return_value=_CHECKOUT_RESULT),
            ) as mock_branch,
            patch(
                f"{_MODULE}.parse_speckit", new=AsyncMock(return_value=_PARSE_RESULT)
            ) as mock_parse,
            patch(
                f"{_MODULE}.enrich_bead_descriptions",
                new=AsyncMock(return_value=_ENRICHED_DEFINITIONS),
            ) as mock_enrich,
            patch(
                f"{_MODULE}.create_beads", new=AsyncMock(return_value=_BEAD_RESULT)
            ) as mock_create,
            patch(
                f"{_MODULE}.wire_dependencies", new=AsyncMock(return_value=_WIRE_RESULT)
            ) as mock_wire,
            patch(
                f"{_MODULE}.git_commit", new=AsyncMock(return_value=_COMMIT_RESULT)
            ) as mock_commit,
            patch(f"{_MODULE}.git_merge", new=AsyncMock(return_value=_MERGE_RESULT)) as mock_merge,
        ):
            events, result = await _collect_events(workflow, {"spec": _SPEC})

        # Workflow succeeded
        assert result is not None
        assert result.success is True

        # All actions were called
        mock_branch.assert_called()
        mock_parse.assert_called_once_with(spec_dir=f"specs/{_SPEC}")
        mock_enrich.assert_called_once()
        mock_create.assert_called_once()
        mock_wire.assert_called_once()
        mock_commit.assert_called_once()
        mock_merge.assert_called_once_with(branch=_SPEC)

        # Output has expected keys — commit and merge are SHA strings, not full dicts
        output = result.final_output
        assert output["epic"] == _BEAD_RESULT.epic
        assert output["work_beads"] == list(_BEAD_RESULT.work_beads)
        assert output["commit"] == _COMMIT_RESULT["commit_sha"]
        assert output["merge"] == _MERGE_RESULT["merge_commit"]

    async def test_dry_run_skips_commit_and_merge(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """When dry_run=True, git_commit and git_merge must NOT be called."""
        workflow = _make_workflow(mock_config, mock_registry)

        with (
            patch(
                f"{_MODULE}.create_git_branch",
                new=AsyncMock(return_value=_CHECKOUT_RESULT),
            ),
            patch(f"{_MODULE}.parse_speckit", new=AsyncMock(return_value=_PARSE_RESULT)),
            patch(
                f"{_MODULE}.enrich_bead_descriptions",
                new=AsyncMock(return_value=_ENRICHED_DEFINITIONS),
            ),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=_BEAD_RESULT)),
            patch(f"{_MODULE}.wire_dependencies", new=AsyncMock(return_value=_WIRE_RESULT)),
            patch(
                f"{_MODULE}.git_commit", new=AsyncMock(return_value=_COMMIT_RESULT)
            ) as mock_commit,
            patch(f"{_MODULE}.git_merge", new=AsyncMock(return_value=_MERGE_RESULT)) as mock_merge,
        ):
            events, result = await _collect_events(workflow, {"spec": _SPEC, "dry_run": True})

        assert result is not None
        assert result.success is True

        # Commit and merge must NOT be called
        mock_commit.assert_not_called()
        mock_merge.assert_not_called()

        # Output reflects dry-run
        output = result.final_output
        assert output["commit"] is None
        assert output["merge"] is None

    async def test_parse_error_handling(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """If parse_speckit raises, the workflow fails and reports the error."""
        workflow = _make_workflow(mock_config, mock_registry)

        with (
            patch(
                f"{_MODULE}.create_git_branch",
                new=AsyncMock(return_value=_CHECKOUT_RESULT),
            ),
            patch(
                f"{_MODULE}.parse_speckit",
                new=AsyncMock(side_effect=RuntimeError("tasks.md not found")),
            ),
            patch(
                f"{_MODULE}.enrich_bead_descriptions",
                new=AsyncMock(return_value=_ENRICHED_DEFINITIONS),
            ),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=_BEAD_RESULT)),
            patch(f"{_MODULE}.wire_dependencies", new=AsyncMock(return_value=_WIRE_RESULT)),
            patch(f"{_MODULE}.git_commit", new=AsyncMock(return_value=_COMMIT_RESULT)),
            patch(f"{_MODULE}.git_merge", new=AsyncMock(return_value=_MERGE_RESULT)),
        ):
            events, result = await _collect_events(
                workflow, {"spec": _SPEC}, ignore_exception=True
            )

        assert result is not None
        assert result.success is False

        # At least one step should show failure
        failed_steps = [s for s in result.step_results if not s.success]
        assert len(failed_steps) >= 1

        # Final WorkflowCompleted event should be False
        workflow_completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert workflow_completed.success is False

    async def test_empty_spec_handling(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """Graceful handling when work_definitions is empty."""
        empty_parse_result = SpecKitParseResult(
            epic_definition={"title": "Epic", "bead_type": "EPIC"},
            work_definitions=(),  # empty
            tasks_content="# Tasks\n",
            dependency_section="",
        )
        empty_bead_result = BeadCreationResult(
            epic={"id": "e1", "title": "Epic"},
            work_beads=(),
            created_map={},
            errors=(),
        )
        empty_wire_result = DependencyWiringResult(
            dependencies=(),
            errors=(),
            success=True,
        )

        workflow = _make_workflow(mock_config, mock_registry)

        with (
            patch(
                f"{_MODULE}.create_git_branch",
                new=AsyncMock(return_value=_CHECKOUT_RESULT),
            ),
            patch(
                f"{_MODULE}.parse_speckit",
                new=AsyncMock(return_value=empty_parse_result),
            ),
            patch(f"{_MODULE}.enrich_bead_descriptions", new=AsyncMock(return_value=[])),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=empty_bead_result)),
            patch(
                f"{_MODULE}.wire_dependencies",
                new=AsyncMock(return_value=empty_wire_result),
            ),
            patch(f"{_MODULE}.git_commit", new=AsyncMock(return_value=_COMMIT_RESULT)),
            patch(f"{_MODULE}.git_merge", new=AsyncMock(return_value=_MERGE_RESULT)),
        ):
            events, result = await _collect_events(workflow, {"spec": _SPEC})

        assert result is not None
        assert result.success is True
        output = result.final_output
        assert output["work_beads"] == []
        assert output["dependencies"] == []
        assert output["errors"] == []

    async def test_events_emitted(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """WorkflowStarted, StepStarted/StepCompleted, WorkflowCompleted are emitted."""
        workflow = _make_workflow(mock_config, mock_registry)

        with (
            patch(
                f"{_MODULE}.create_git_branch",
                new=AsyncMock(return_value=_CHECKOUT_RESULT),
            ),
            patch(f"{_MODULE}.parse_speckit", new=AsyncMock(return_value=_PARSE_RESULT)),
            patch(
                f"{_MODULE}.enrich_bead_descriptions",
                new=AsyncMock(return_value=_ENRICHED_DEFINITIONS),
            ),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=_BEAD_RESULT)),
            patch(f"{_MODULE}.wire_dependencies", new=AsyncMock(return_value=_WIRE_RESULT)),
            patch(f"{_MODULE}.git_commit", new=AsyncMock(return_value=_COMMIT_RESULT)),
            patch(f"{_MODULE}.git_merge", new=AsyncMock(return_value=_MERGE_RESULT)),
        ):
            events, result = await _collect_events(workflow, {"spec": _SPEC})

        event_types = [type(e) for e in events]

        # Required events
        assert WorkflowStarted in event_types
        assert StepStarted in event_types
        assert StepCompleted in event_types
        assert WorkflowCompleted in event_types

        # First event is WorkflowStarted
        assert isinstance(events[0], WorkflowStarted)
        assert events[0].workflow_name == WORKFLOW_NAME

        # Last event is WorkflowCompleted
        assert isinstance(events[-1], WorkflowCompleted)
        assert events[-1].success is True

        # At least one StepStarted/StepCompleted pair per core step
        step_started_names = {e.step_name for e in events if isinstance(e, StepStarted)}
        step_completed_names = {e.step_name for e in events if isinstance(e, StepCompleted)}

        for step_name in (
            CHECKOUT,
            PARSE_SPEC,
            EXTRACT_DEPS,
            ENRICH_BEADS,
            CREATE_BEADS,
            WIRE_DEPS,
            COMMIT,
            CHECKOUT_MAIN,
            MERGE,
        ):
            assert step_name in step_started_names, f"{step_name} not in StepStarted events"
            assert step_name in step_completed_names, f"{step_name} not in StepCompleted events"

    async def test_missing_spec_input_raises(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """Omitting 'spec' input results in a failed workflow."""
        workflow = _make_workflow(mock_config, mock_registry)

        events, result = await _collect_events(workflow, {}, ignore_exception=True)

        assert result is not None
        assert result.success is False
        workflow_completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert workflow_completed.success is False

    async def test_workflow_name_default(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """Default workflow_name equals WORKFLOW_NAME constant."""
        workflow = _make_workflow(mock_config, mock_registry)
        assert workflow._workflow_name == WORKFLOW_NAME

    async def test_wire_deps_skipped_when_no_epic(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """wire_dependencies is NOT called when epic creation fails (epic=None)."""
        no_epic_result = BeadCreationResult(
            epic=None,
            work_beads=(),
            created_map={},
            errors=("Epic creation failed: bd not found",),
        )

        workflow = _make_workflow(mock_config, mock_registry)

        with (
            patch(
                f"{_MODULE}.create_git_branch",
                new=AsyncMock(return_value=_CHECKOUT_RESULT),
            ),
            patch(f"{_MODULE}.parse_speckit", new=AsyncMock(return_value=_PARSE_RESULT)),
            patch(
                f"{_MODULE}.enrich_bead_descriptions",
                new=AsyncMock(return_value=_ENRICHED_DEFINITIONS),
            ),
            patch(f"{_MODULE}.create_beads", new=AsyncMock(return_value=no_epic_result)),
            patch(
                f"{_MODULE}.wire_dependencies", new=AsyncMock(return_value=_WIRE_RESULT)
            ) as mock_wire,
            patch(f"{_MODULE}.git_commit", new=AsyncMock(return_value=_COMMIT_RESULT)),
            patch(f"{_MODULE}.git_merge", new=AsyncMock(return_value=_MERGE_RESULT)),
        ):
            events, result = await _collect_events(workflow, {"spec": _SPEC})

        mock_wire.assert_not_called()
        assert result is not None
        assert result.success is True
        output = result.final_output
        assert output["dependencies"] == []
        assert output["errors"] == list(no_epic_result.errors)
