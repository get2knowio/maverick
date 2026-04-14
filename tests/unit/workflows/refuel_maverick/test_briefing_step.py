"""Unit tests for the briefing step in RefuelMaverickWorkflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.briefing.models import (
    ContrarianBrief,
    NavigatorBrief,
    ReconBrief,
    StructuralistBrief,
)
from maverick.executor.result import ExecutorResult

from .conftest import (
    collect_events,
    make_bead_result,
    make_simple_flight_plan,
    make_wire_result,
    make_workflow,
    patch_cwd,
    patch_decompose_supervisor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_navigator_brief() -> NavigatorBrief:
    return NavigatorBrief(
        architecture_decisions=(),
        module_structure="src/",
        integration_points=(),
        summary="Nav summary",
    )


def _make_structuralist_brief() -> StructuralistBrief:
    return StructuralistBrief(entities=(), interfaces=(), summary="Struct summary")


def _make_recon_brief() -> ReconBrief:
    return ReconBrief(
        risks=(),
        ambiguities=(),
        testing_strategy="Unit tests",
        summary="Recon summary",
    )


def _make_contrarian_brief() -> ContrarianBrief:
    return ContrarianBrief(
        challenges=(),
        simplifications=(),
        consensus_points=(),
        summary="Contrarian summary",
    )


def _make_executor_with_briefing() -> AsyncMock:
    """Create a mock step executor that returns briefing agent outputs.

    Decomposition is now handled by _decompose_with_supervisor (Thespian),
    so this executor only needs to service the briefing agents.
    """
    from maverick.executor.protocol import StepExecutor

    executor = AsyncMock(spec=StepExecutor)

    # Map agent names to their outputs (briefing agents return single outputs)
    briefing_map: dict[str, Any] = {
        "navigator": _make_navigator_brief(),
        "structuralist": _make_structuralist_brief(),
        "recon": _make_recon_brief(),
        "contrarian": _make_contrarian_brief(),
    }

    async def _execute(
        step_name: str,
        agent_name: str,
        prompt: str,
        output_schema: Any,
        event_callback: Any = None,
        config: Any = None,
        **kwargs: Any,
    ) -> ExecutorResult:
        output = briefing_map.get(agent_name)
        return ExecutorResult(
            output=output,
            success=True,
            events=(),
            usage=None,
        )

    executor.execute.side_effect = _execute
    return executor


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBriefingStep:
    """Tests for the briefing step integration in the workflow."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        from maverick.config import ModelConfig

        cfg = MagicMock()
        cfg.steps = {}
        cfg.agents = {}
        cfg.model = ModelConfig()
        return cfg

    @pytest.fixture
    def mock_registry(self) -> MagicMock:
        return MagicMock()

    @pytest.mark.asyncio
    async def test_briefing_step_runs_when_not_skipped(
        self, tmp_path: Path, mock_config: MagicMock, mock_registry: MagicMock
    ) -> None:
        """Briefing step executes when skip_briefing=False."""
        fp_path = make_simple_flight_plan(tmp_path)
        executor = _make_executor_with_briefing()
        workflow = make_workflow(mock_config, mock_registry, step_executor=executor)

        with (
            patch_cwd(tmp_path),
            patch(
                "maverick.workflows.refuel_maverick.workflow.create_beads",
                return_value=make_bead_result(),
            ),
            patch(
                "maverick.workflows.refuel_maverick.workflow.wire_dependencies",
                return_value=make_wire_result(),
            ),
            patch_decompose_supervisor(),
        ):
            events, _ = await collect_events(
                workflow,
                {
                    "flight_plan_path": str(fp_path),
                    "dry_run": True,
                    "skip_briefing": False,
                },
            )

        # Should have called execute for briefing agents
        call_agent_names = [
            call.kwargs.get("agent_name", call.args[1] if len(call.args) > 1 else None)
            for call in executor.execute.call_args_list
        ]
        assert "navigator" in call_agent_names
        assert "structuralist" in call_agent_names
        assert "recon" in call_agent_names
        assert "contrarian" in call_agent_names

    @pytest.mark.asyncio
    async def test_briefing_step_skipped(
        self, tmp_path: Path, mock_config: MagicMock, mock_registry: MagicMock
    ) -> None:
        """Briefing step is skipped when skip_briefing=True."""
        fp_path = make_simple_flight_plan(tmp_path)
        executor = _make_executor_with_briefing()
        workflow = make_workflow(mock_config, mock_registry, step_executor=executor)

        with (
            patch_cwd(tmp_path),
            patch(
                "maverick.workflows.refuel_maverick.workflow.create_beads",
                return_value=make_bead_result(),
            ),
            patch(
                "maverick.workflows.refuel_maverick.workflow.wire_dependencies",
                return_value=make_wire_result(),
            ),
            patch_decompose_supervisor(),
        ):
            events, _ = await collect_events(
                workflow,
                {
                    "flight_plan_path": str(fp_path),
                    "dry_run": True,
                    "skip_briefing": True,
                },
            )

        # Should NOT have called execute for briefing agents
        call_agent_names = [
            call.kwargs.get("agent_name", call.args[1] if len(call.args) > 1 else None)
            for call in executor.execute.call_args_list
        ]
        assert "navigator" not in call_agent_names
        assert "contrarian" not in call_agent_names

    @pytest.mark.asyncio
    async def test_briefing_writes_artifact(
        self, tmp_path: Path, mock_config: MagicMock, mock_registry: MagicMock
    ) -> None:
        """Briefing step writes refuel-briefing.md artifact to disk."""
        fp_path = make_simple_flight_plan(tmp_path)
        executor = _make_executor_with_briefing()
        workflow = make_workflow(mock_config, mock_registry, step_executor=executor)

        with (
            patch_cwd(tmp_path),
            patch(
                "maverick.workflows.refuel_maverick.workflow.create_beads",
                return_value=make_bead_result(),
            ),
            patch(
                "maverick.workflows.refuel_maverick.workflow.wire_dependencies",
                return_value=make_wire_result(),
            ),
            patch_decompose_supervisor(),
        ):
            await collect_events(
                workflow,
                {
                    "flight_plan_path": str(fp_path),
                    "dry_run": True,
                    "skip_briefing": False,
                },
            )

        briefing_dir = tmp_path / ".maverick" / "plans" / "add-user-auth"
        briefing_path = briefing_dir / "refuel-briefing.md"
        assert briefing_path.exists()
        content = briefing_path.read_text()
        assert "flight-plan: add-user-auth" in content
        assert "## Summary" in content

    @pytest.mark.asyncio
    async def test_briefing_result_has_briefing_path(
        self, tmp_path: Path, mock_config: MagicMock, mock_registry: MagicMock
    ) -> None:
        """Workflow result includes briefing_path when briefing runs."""
        fp_path = make_simple_flight_plan(tmp_path)
        executor = _make_executor_with_briefing()
        workflow = make_workflow(mock_config, mock_registry, step_executor=executor)

        with (
            patch_cwd(tmp_path),
            patch(
                "maverick.workflows.refuel_maverick.workflow.create_beads",
                return_value=make_bead_result(),
            ),
            patch(
                "maverick.workflows.refuel_maverick.workflow.wire_dependencies",
                return_value=make_wire_result(),
            ),
            patch_decompose_supervisor(),
        ):
            _, result = await collect_events(
                workflow,
                {
                    "flight_plan_path": str(fp_path),
                    "dry_run": True,
                    "skip_briefing": False,
                },
            )

        assert result is not None
        assert result.final_output["briefing_path"] is not None
        assert "refuel-briefing.md" in result.final_output["briefing_path"]

    @pytest.mark.asyncio
    async def test_briefing_path_none_when_skipped(
        self, tmp_path: Path, mock_config: MagicMock, mock_registry: MagicMock
    ) -> None:
        """Workflow result has briefing_path=None when briefing is skipped."""
        fp_path = make_simple_flight_plan(tmp_path)
        executor = _make_executor_with_briefing()
        workflow = make_workflow(mock_config, mock_registry, step_executor=executor)

        with (
            patch_cwd(tmp_path),
            patch(
                "maverick.workflows.refuel_maverick.workflow.create_beads",
                return_value=make_bead_result(),
            ),
            patch(
                "maverick.workflows.refuel_maverick.workflow.wire_dependencies",
                return_value=make_wire_result(),
            ),
            patch_decompose_supervisor(),
        ):
            _, result = await collect_events(
                workflow,
                {
                    "flight_plan_path": str(fp_path),
                    "dry_run": True,
                    "skip_briefing": True,
                },
            )

        assert result is not None
        assert result.final_output["briefing_path"] is None

    @pytest.mark.asyncio
    async def test_parallel_execution_of_three_agents(
        self, tmp_path: Path, mock_config: MagicMock, mock_registry: MagicMock
    ) -> None:
        """Navigator, Structuralist, and Recon run in parallel (gather verifies)."""
        fp_path = make_simple_flight_plan(tmp_path)
        executor = _make_executor_with_briefing()
        workflow = make_workflow(mock_config, mock_registry, step_executor=executor)

        with (
            patch_cwd(tmp_path),
            patch(
                "maverick.workflows.refuel_maverick.workflow.create_beads",
                return_value=make_bead_result(),
            ),
            patch(
                "maverick.workflows.refuel_maverick.workflow.wire_dependencies",
                return_value=make_wire_result(),
            ),
            patch_decompose_supervisor(),
        ):
            await collect_events(
                workflow,
                {
                    "flight_plan_path": str(fp_path),
                    "dry_run": True,
                    "skip_briefing": False,
                },
            )

        # Contrarian should be called after the first 3
        call_agent_names = [
            call.kwargs.get("agent_name", call.args[1] if len(call.args) > 1 else None)
            for call in executor.execute.call_args_list
        ]
        contrarian_idx = call_agent_names.index("contrarian")
        # Navigator, structuralist, recon should all be before contrarian
        for agent in ("navigator", "structuralist", "recon"):
            assert call_agent_names.index(agent) < contrarian_idx
