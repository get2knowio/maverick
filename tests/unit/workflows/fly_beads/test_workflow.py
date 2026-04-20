"""Unit tests for FlyBeadsWorkflow Thespian orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from maverick.config import AgentConfig, AgentProviderConfig, MaverickConfig, ModelConfig
from maverick.registry import ComponentRegistry
from maverick.workflows.fly_beads.constants import WORKFLOW_NAME
from maverick.workflows.fly_beads.workflow import FlyBeadsWorkflow


def _make_workflow() -> FlyBeadsWorkflow:
    config = MagicMock(spec=MaverickConfig)
    config.model = ModelConfig()
    config.steps = {}
    config.agents = {
        "implementer": AgentConfig(
            provider="gemini",
            model_id="gemini-3.1-pro-preview",
        ),
        "reviewer": AgentConfig(
            provider="claude",
            model_id="opus",
        ),
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
    config.project_type = "python"
    registry = MagicMock(spec=ComponentRegistry)
    return FlyBeadsWorkflow(
        config=config,
        registry=registry,
        workflow_name=WORKFLOW_NAME,
    )


class _FakeActorSystem:
    def __init__(self) -> None:
        self.asks: list[tuple[str, dict[str, Any], int]] = []
        self.tell_calls: list[tuple[str, str]] = []
        self._counter = 0

    def createActor(self, _cls, **kwargs):  # noqa: N802
        self._counter += 1
        return kwargs.get("globalName") or f"actor-{self._counter}"

    def ask(self, addr, message, timeout):
        self.asks.append((addr, message, timeout))
        return {"type": "init_ok"}

    def tell(self, addr, message):
        self.tell_calls.append((addr, message))

    def shutdown(self):
        return None


class TestFlyBeadsWorkflowThespianConfig:
    async def test_actor_inits_receive_resolved_step_config(self, tmp_path: Path) -> None:
        """Implementer and reviewer init messages carry provider/model overrides."""
        workflow = _make_workflow()
        fake_asys = _FakeActorSystem()

        with (
            patch("maverick.actors.create_actor_system", return_value=fake_asys),
            patch(
                "maverick.workflows.fly_beads.steps._build_validation_commands",
                return_value=[["make", "test"]],
            ),
            patch.object(workflow, "emit_output", new=AsyncMock()),
            patch.object(
                workflow,
                "_drain_supervisor_events",
                new=AsyncMock(
                    return_value={
                        "bead_events": [],
                        "aggregate_review": [],
                        "beads_completed": 0,
                        "beads_failed": 0,
                        "beads_skipped": 0,
                    }
                ),
            ),
        ):
            await workflow._run_fly_with_thespian(
                epic_id="",
                workspace_path=tmp_path,
            )

        actor_inits = [
            message
            for _addr, message, _timeout in fake_asys.asks
            if message.get("type") == "init" and message.get("config")
        ]
        assert len(actor_inits) == 2

        implementer_init = next(
            msg for msg in actor_inits if msg["config"].get("provider") == "gemini"
        )
        assert implementer_init["config"]["model_id"] == "gemini-3.1-pro-preview"

        reviewer_init = next(
            msg for msg in actor_inits if msg["config"].get("provider") == "claude"
        )
        assert reviewer_init["config"]["model_id"] == "opus"
