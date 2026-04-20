"""Tests for runtime StepConfig propagation in top-level Thespian actors."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import maverick.actors.briefing as briefing_module
import maverick.actors.implementer as implementer_module
from maverick.executor.config import StepConfig

_STEP_CONFIG = StepConfig(
    provider="gemini",
    model_id="gemini-3.1-pro-preview",
)


class TestBriefingActorRuntimeConfig:
    async def test_new_session_passes_provider_and_model_config(self) -> None:
        actor = object.__new__(briefing_module.BriefingActor)
        actor._cwd = "/tmp"
        actor._admin_port = 19500
        actor._mcp_tool = "submit_scope"
        actor._agent_name = "navigator"
        actor._step_config = _STEP_CONFIG
        actor._ensure_executor = AsyncMock()
        actor._executor = MagicMock()
        actor._executor.create_session = AsyncMock(return_value="sess-1")

        await actor._new_session()

        create_kwargs = actor._executor.create_session.await_args.kwargs
        assert create_kwargs["provider"] == "gemini"
        assert create_kwargs["config"].model_id == "gemini-3.1-pro-preview"

    async def test_prompt_session_preserves_provider_and_model_config(self) -> None:
        actor = object.__new__(briefing_module.BriefingActor)
        actor._mcp_tool = "submit_scope"
        actor._agent_name = "navigator"
        actor._step_config = _STEP_CONFIG
        actor._session_id = "sess-1"
        actor._ensure_executor = AsyncMock()
        actor._executor = MagicMock()
        actor._executor.prompt_session = AsyncMock()

        await actor._send_prompt({"prompt": "brief it"})

        prompt_kwargs = actor._executor.prompt_session.await_args.kwargs
        assert prompt_kwargs["provider"] == "gemini"
        assert prompt_kwargs["config"].model_id == "gemini-3.1-pro-preview"
        assert prompt_kwargs["config"].timeout == 1200


class TestImplementerActorRuntimeConfig:
    async def test_new_session_passes_provider_and_model_config(self) -> None:
        actor = object.__new__(implementer_module.ImplementerActor)
        actor._cwd = "/tmp"
        actor._admin_port = 19500
        actor._mcp_tools = "submit_implementation,submit_fix_result"
        actor._step_config = _STEP_CONFIG
        actor._ensure_executor = AsyncMock()
        actor._executor = MagicMock()
        actor._executor.create_session = AsyncMock(return_value="sess-1")

        await actor._new_session()

        create_kwargs = actor._executor.create_session.await_args.kwargs
        assert create_kwargs["provider"] == "gemini"
        assert create_kwargs["config"].model_id == "gemini-3.1-pro-preview"

    async def test_prompt_session_preserves_provider_and_model_config(self) -> None:
        actor = object.__new__(implementer_module.ImplementerActor)
        actor._step_config = _STEP_CONFIG
        actor._session_id = "sess-1"
        actor._ensure_executor = AsyncMock()
        actor._executor = MagicMock()
        actor._executor.prompt_session = AsyncMock()

        await actor._send_prompt({"prompt": "implement this"}, "implement")

        prompt_kwargs = actor._executor.prompt_session.await_args.kwargs
        assert prompt_kwargs["provider"] == "gemini"
        assert prompt_kwargs["config"].model_id == "gemini-3.1-pro-preview"
        assert prompt_kwargs["config"].timeout == 1800
