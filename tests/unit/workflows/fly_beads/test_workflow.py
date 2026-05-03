"""Unit tests for ``FlyBeadsWorkflow`` xoscar orchestration."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.config import AgentProviderConfig, MaverickConfig, ModelConfig
from maverick.workflows.fly_beads.constants import WORKFLOW_NAME
from maverick.workflows.fly_beads.workflow import FlyBeadsWorkflow

_REQUIRES_OPENCODE = pytest.mark.skipif(
    shutil.which("opencode") is None,
    reason="opencode binary not on PATH (CI environment)",
)


def _make_workflow() -> FlyBeadsWorkflow:
    config = MagicMock(spec=MaverickConfig)
    config.model = ModelConfig()
    config.actors = {
        "fly": {
            "implementer": {
                "provider": "gemini",
                "model_id": "gemini-3.1-pro-preview",
            },
            "reviewer": {
                "provider": "claude",
                "model_id": "opus",
            },
        },
    }
    config.agent_providers = {
        "claude": AgentProviderConfig(
            command=["claude-agent"],
            default=True,
            default_model="sonnet",
        ),
        "gemini": AgentProviderConfig(
            command=["gemini-agent"],
            default_model="gemini-default",
        ),
    }
    config.validation = MagicMock(timeout_seconds=300)
    config.parallel = MagicMock(max_agents=3)
    config.project_type = "python"
    return FlyBeadsWorkflow(
        config=config,
        workflow_name=WORKFLOW_NAME,
    )


@_REQUIRES_OPENCODE
class TestFlyBeadsWorkflowXoscarConfig:
    async def test_xoscar_supervisor_receives_typed_inputs(self, tmp_path: Path) -> None:
        """The xoscar FlySupervisor gets ``FlyInputs`` carrying the resolved
        implementer ``StepConfig`` and the project type."""
        workflow = _make_workflow()

        captured_inputs: dict[str, Any] = {}

        async def _fake_create_actor(_cls, *args: Any, **kwargs: Any) -> AsyncMock:
            if args and not captured_inputs:
                captured_inputs["value"] = args[0]
            return AsyncMock()

        async def _fake_destroy_actor(_ref: Any) -> None:
            return None

        with (
            patch(
                "maverick.workflows.fly_beads.steps._build_validation_commands",
                return_value={"test": ("make", "test")},
            ),
            patch("xoscar.create_actor", new=_fake_create_actor),
            patch("xoscar.destroy_actor", new=_fake_destroy_actor),
            patch.object(workflow, "emit_output", new=AsyncMock()),
            patch.object(
                workflow,
                "_drain_xoscar_supervisor",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "beads_completed": 0,
                        "completed_bead_ids": [],
                    }
                ),
            ),
        ):
            await workflow._run_fly_with_xoscar(
                epic_id="",
                cwd=tmp_path,
            )

        inputs = captured_inputs.get("value")
        assert inputs is not None, "FlySupervisor was never created"
        assert inputs.cwd == str(tmp_path)
        assert inputs.project_type == "python"
        # Implementer config flows through to the supervisor inputs.
        assert inputs.config is not None
        assert inputs.config.provider == "gemini"
        assert inputs.config.model_id == "gemini-3.1-pro-preview"
        # Reviewer gets its own resolved StepConfig — without this it
        # would inherit the implementer's provider/model.
        assert inputs.reviewer_config is not None
        assert inputs.reviewer_config.provider == "claude"
        assert inputs.reviewer_config.model_id == "opus"

    async def test_reviewer_config_resolves_from_actors_block(
        self,
        tmp_path: Path,
    ) -> None:
        """When user writes ``actors.fly.reviewer`` the workflow plumbs that
        config to the supervisor instead of letting reviewer inherit the
        implementer's config."""
        from maverick.config import (
            AgentProviderConfig,
            MaverickConfig,
            ModelConfig,
        )

        config = MagicMock(spec=MaverickConfig)
        config.model = ModelConfig()
        config.actors = {
            "fly": {
                "implementer": {
                    "provider": "copilot",
                    "model_id": "gpt-5.3-codex",
                },
                "reviewer": {
                    "provider": "gemini",
                    "model_id": "gemini-3.1-pro-preview",
                },
            },
        }
        config.agent_providers = {
            "claude": AgentProviderConfig(
                command=["claude-agent"], default=True, default_model="sonnet"
            ),
            "copilot": AgentProviderConfig(command=["copilot-agent"], default_model="gpt-5-mini"),
            "gemini": AgentProviderConfig(
                command=["gemini-agent"], default_model="gemini-default"
            ),
        }
        config.validation = MagicMock(timeout_seconds=300)
        config.parallel = MagicMock(max_agents=3)
        config.project_type = "python"

        workflow = FlyBeadsWorkflow(
            config=config,
            workflow_name=WORKFLOW_NAME,
        )

        captured_inputs: dict[str, Any] = {}

        async def _fake_create_actor(_cls, *args: Any, **kwargs: Any) -> AsyncMock:
            if args and not captured_inputs:
                captured_inputs["value"] = args[0]
            return AsyncMock()

        async def _fake_destroy_actor(_ref: Any) -> None:
            return None

        with (
            patch(
                "maverick.workflows.fly_beads.steps._build_validation_commands",
                return_value={"test": ("make", "test")},
            ),
            patch("xoscar.create_actor", new=_fake_create_actor),
            patch("xoscar.destroy_actor", new=_fake_destroy_actor),
            patch.object(workflow, "emit_output", new=AsyncMock()),
            patch.object(
                workflow,
                "_drain_xoscar_supervisor",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "beads_completed": 0,
                        "completed_bead_ids": [],
                    }
                ),
            ),
        ):
            await workflow._run_fly_with_xoscar(
                epic_id="",
                cwd=tmp_path,
            )

        inputs = captured_inputs["value"]
        assert inputs.config.provider == "copilot"
        assert inputs.config.model_id == "gpt-5.3-codex"
        # actors.fly.reviewer wins over the global default.
        assert inputs.reviewer_config.provider == "gemini"
        assert inputs.reviewer_config.model_id == "gemini-3.1-pro-preview"
