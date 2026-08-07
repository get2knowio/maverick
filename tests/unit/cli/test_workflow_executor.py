"""Unit tests for shared Python workflow execution helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import click

from maverick.cli.workflow_executor import (
    PythonWorkflowRunConfig,
    execute_python_workflow,
)
from maverick.workflows.base import PythonWorkflow

WORKFLOW_NAME = "recording-workflow"


class RecordingWorkflow(PythonWorkflow):
    """Minimal workflow used to assert constructor wiring."""

    STEPS: ClassVar[dict[str, Any]] = {}
    last_workflow_name: ClassVar[str | None] = None

    def __init__(
        self,
        *,
        config: Any,
        checkpoint_store: Any = None,
        workflow_name: str,
    ) -> None:
        type(self).last_workflow_name = workflow_name
        super().__init__(
            config=config,
            checkpoint_store=checkpoint_store,
            workflow_name=workflow_name,
        )

    def execute(self, inputs: dict[str, Any]) -> AsyncIterator[Any]:
        async def _events() -> AsyncIterator[Any]:
            if False:
                yield None

        return _events()

    async def _run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {}


class TestExecutePythonWorkflow:
    """Tests for execute_python_workflow."""

    async def test_passes_workflow_name_to_constructor(self) -> None:
        """The shared CLI runner passes the resolved workflow name explicitly."""
        RecordingWorkflow.last_workflow_name = None
        ctx = click.Context(click.Command("test"))
        ctx.obj = {"verbosity": 0}
        checkpoint_store = AsyncMock()
        checkpoint_store.load_latest.return_value = None

        with (
            patch(
                "maverick.checkpoint.store.FileCheckpointStore",
                return_value=checkpoint_store,
            ),
            patch("maverick.config.load_config", return_value=MagicMock()),
            patch(
                "maverick.cli.workflow_executor.render_workflow_events",
                new_callable=AsyncMock,
            ) as mock_render,
        ):
            await execute_python_workflow(
                ctx,
                PythonWorkflowRunConfig(
                    workflow_class=RecordingWorkflow,
                    inputs={"value": "x"},
                ),
            )

        assert RecordingWorkflow.last_workflow_name == WORKFLOW_NAME
        mock_render.assert_awaited_once()


class TestStepOutputMarkupSafety:
    """Workflow text is data, not Rich markup.

    Regression for the first live Spec Kit walkthrough: a Spec Kit task
    description mentioning ``[project.scripts]`` and ``[tool.mypy]`` had
    those tokens silently eaten by Rich's markup parser on the way to the
    terminal, and a description containing ``[/]`` raises ``MarkupError``
    outright. Neither is markup the workflow authored -- both come from a
    file Maverick parsed.
    """

    @staticmethod
    async def _render(messages: list[str]) -> str:
        import io

        from rich.console import Console

        from maverick.cli.workflow_executor import render_workflow_events
        from maverick.events import StepOutput

        async def _events() -> AsyncIterator[Any]:
            for msg in messages:
                yield StepOutput(step_name="create_beads", message=msg)

        buf = io.StringIO()
        await render_workflow_events(_events(), Console(file=buf, width=200, no_color=True))
        return buf.getvalue()

    async def test_bracketed_tokens_survive_rendering(self) -> None:
        out = await self._render(
            [
                "first interim",
                "T001: create `[project.scripts]` and `[tool.mypy]`/`[tool.ruff]` sections",
            ]
        )
        assert "[project.scripts]" in out
        assert "[tool.mypy]" in out
        assert "[tool.ruff]" in out

    async def test_closing_tag_in_message_does_not_raise(self) -> None:
        out = await self._render(["first interim", "T002: handle the `[/]` route"])
        assert "[/]" in out


class TestContextFileWriteBlockedRendering:
    """056-context-file-protection T022: block events render as yellow
    warnings; agent-authored ``detail``/paths are escaped."""

    @staticmethod
    async def _render(events: list[Any]) -> str:
        import io

        from rich.console import Console

        from maverick.cli.workflow_executor import render_workflow_events

        async def _events() -> AsyncIterator[Any]:
            for event in events:
                yield event

        buf = io.StringIO()
        await render_workflow_events(_events(), Console(file=buf, width=200, no_color=True))
        return buf.getvalue()

    async def test_renders_path_and_layer(self) -> None:
        from maverick.events import ContextFileWriteBlocked

        out = await self._render(
            [
                ContextFileWriteBlocked(
                    agent_role="implement",
                    workflow="fly-beads",
                    operation="edit",
                    path="CLAUDE.md",
                    layer="pre-write",
                    detail="matched default rule",
                )
            ]
        )
        assert "CLAUDE.md" in out
        assert "pre-write" in out
        assert "matched default rule" in out

    async def test_restore_operation_says_restored(self) -> None:
        from maverick.events import ContextFileWriteBlocked

        out = await self._render(
            [
                ContextFileWriteBlocked(
                    agent_role="implement",
                    workflow="fly-beads",
                    operation="restore",
                    path="AGENTS.md",
                    layer="backstop",
                )
            ]
        )
        assert "Restored" in out

    async def test_agent_authored_detail_with_markup_tokens_does_not_raise(self) -> None:
        from maverick.events import ContextFileWriteBlocked

        out = await self._render(
            [
                ContextFileWriteBlocked(
                    agent_role="implement",
                    workflow="fly-beads",
                    operation="edit",
                    path="CLAUDE.md",
                    layer="pre-write",
                    detail="agent said `[/]` and `[bold]` in its reasoning",
                )
            ]
        )
        assert "[/]" in out
        assert "[bold]" in out

    async def test_rename_shows_destination_arrow(self) -> None:
        from maverick.events import ContextFileWriteBlocked

        out = await self._render(
            [
                ContextFileWriteBlocked(
                    agent_role="implement",
                    workflow="fly-beads",
                    operation="rename",
                    path="notes.txt",
                    destination_path="AGENTS.md",
                    layer="pre-write",
                )
            ]
        )
        assert "notes.txt" in out
        assert "AGENTS.md" in out
