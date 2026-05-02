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
