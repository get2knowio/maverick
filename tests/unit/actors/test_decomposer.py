"""Unit tests for the refuel DecomposerActor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import maverick.actors.decomposer as decomposer_module
from maverick.executor.config import StepConfig


def _make_actor() -> decomposer_module.DecomposerActor:
    actor = object.__new__(decomposer_module.DecomposerActor)
    actor._handle_actor_exit = MagicMock(return_value=False)
    actor._run_async = MagicMock()
    actor.send = MagicMock()
    actor._role = "primary"
    actor._actor_tag = "decomposer[primary:pid=test]"
    actor._step_config = None
    actor._detail_outline_json = "{}"
    actor._detail_flight_plan = ""
    actor._detail_verification = ""
    actor._detail_seed_stale = False
    actor._detail_session_max_turns = 5
    actor._fix_outline_json = '{"work_units": []}'
    actor._fix_details_json = '{"details": []}'
    actor._fix_verification = ""
    actor._fix_seed_stale = False
    actor._fix_session_max_turns = 1
    actor._session_id = None
    actor._session_mode = None
    actor._session_turns_in_mode = 0
    return actor


class TestDecomposerSessionRotation:
    """Tests for seeded-session rotation helpers."""

    def test_needs_new_mode_session_when_no_session_exists(self) -> None:
        actor = _make_actor()

        assert actor._needs_new_mode_session(
            "detail",
            max_turns=5,
            seed_stale=False,
        )

    def test_needs_new_mode_session_when_mode_changes(self) -> None:
        actor = _make_actor()
        actor._session_id = "sess-1"
        actor._session_mode = "outline"

        assert actor._needs_new_mode_session(
            "detail",
            max_turns=5,
            seed_stale=False,
        )

    def test_needs_new_mode_session_when_turn_budget_exhausted(self) -> None:
        actor = _make_actor()
        actor._session_id = "sess-1"
        actor._session_mode = "detail"
        actor._session_turns_in_mode = 5

        assert actor._needs_new_mode_session(
            "detail",
            max_turns=5,
            seed_stale=False,
        )

    def test_needs_new_mode_session_false_when_session_reusable(self) -> None:
        actor = _make_actor()
        actor._session_id = "sess-1"
        actor._session_mode = "detail"
        actor._session_turns_in_mode = 2

        assert not actor._needs_new_mode_session(
            "detail",
            max_turns=5,
            seed_stale=False,
        )

    def test_mark_turn_completed_increments_current_mode(self) -> None:
        actor = _make_actor()
        actor._session_mode = "detail"

        actor._mark_turn_completed("detail")

        assert actor._session_turns_in_mode == 1

    def test_receive_message_set_context_marks_detail_seed_stale(self) -> None:
        actor = _make_actor()

        actor.receiveMessage(
            {
                "type": "set_context",
                "outline_json": '{"work_units": [{"id": "unit-1"}]}',
                "flight_plan_content": "## Objective\nShip it.",
                "verification_properties": "def verify_sc001():\n    assert True",
            },
            sender="supervisor",
        )

        assert actor._detail_seed_stale is True
        assert actor._detail_flight_plan == "## Objective\nShip it."
        assert '"id": "unit-1"' in actor._detail_outline_json

    def test_receive_message_fix_request_marks_fix_seed_stale(self) -> None:
        actor = _make_actor()
        actor._send_fix_prompt = MagicMock(return_value="fix-coro")

        actor.receiveMessage(
            {
                "type": "fix_request",
                "outline_json": '{"work_units": [{"id": "unit-1"}]}',
                "details_json": '{"details": [{"id": "unit-1"}]}',
                "verification_properties": "def verify_sc001():\n    assert True",
                "coverage_gaps": ["SC-001 missing"],
            },
            sender="supervisor",
        )

        assert actor._fix_seed_stale is True
        assert '"id": "unit-1"' in actor._fix_outline_json
        assert '"id": "unit-1"' in actor._fix_details_json
        actor._run_async.assert_called_once()


class TestDecomposerPromptComposition:
    """Tests for fresh versus reused seeded-session prompts."""

    async def test_detail_prompt_includes_seed_on_fresh_session(self) -> None:
        actor = _make_actor()
        actor._detail_flight_plan = "## Objective\nShip it."
        actor._detail_outline_json = '{"work_units": [{"id": "unit-1"}]}'
        actor._detail_verification = "def verify_sc001():\n    assert True"
        actor._detail_seed_stale = True
        actor._session_mode = "detail"
        actor._ensure_mode_session = AsyncMock(return_value=True)
        actor._prompt = AsyncMock()

        await actor._send_detail_prompt({"unit_id": "unit-1"})

        prompt_text = actor._prompt.await_args.args[0]
        assert "## Flight Plan" in prompt_text
        assert "## Full Outline" in prompt_text
        assert "## Detail Request" in prompt_text
        assert actor._detail_seed_stale is False

    async def test_detail_prompt_omits_seed_on_reused_session(self) -> None:
        actor = _make_actor()
        actor._detail_seed_stale = False
        actor._session_mode = "detail"
        actor._ensure_mode_session = AsyncMock(return_value=False)
        actor._prompt = AsyncMock()

        await actor._send_detail_prompt({"unit_id": "unit-1"})

        prompt_text = actor._prompt.await_args.args[0]
        assert "## Detail Request" in prompt_text
        assert "## Flight Plan" not in prompt_text
        assert "## Full Outline" not in prompt_text

    async def test_fix_prompt_includes_seed_on_fresh_session(self) -> None:
        actor = _make_actor()
        actor._fix_outline_json = '{"work_units": [{"id": "unit-1"}]}'
        actor._fix_details_json = '{"details": [{"id": "unit-1"}]}'
        actor._fix_verification = "def verify_sc001():\n    assert True"
        actor._fix_seed_stale = True
        actor._session_mode = "fix"
        actor._ensure_mode_session = AsyncMock(return_value=True)
        actor._prompt = AsyncMock()

        await actor._send_fix_prompt(
            {
                "coverage_gaps": ["SC-001 missing from unit-1"],
                "overloaded": ["unit-2 covers too many criteria"],
            }
        )

        prompt_text = actor._prompt.await_args.args[0]
        assert "## Current Outline" in prompt_text
        assert "## Current Details" in prompt_text
        assert "## Fix Request" in prompt_text
        assert actor._fix_seed_stale is False


class TestDecomposerSessionPermissions:
    """Tests for ACP session tool restrictions."""

    async def test_primary_session_passes_read_only_and_mcp_tools(self) -> None:
        actor = _make_actor()
        actor._cwd = "/tmp"
        actor._role = "primary"
        actor._admin_port = 19500
        actor._mcp_tool_names = decomposer_module.PRIMARY_DECOMPOSER_MCP_TOOLS
        actor._mcp_tools = ",".join(decomposer_module.PRIMARY_DECOMPOSER_MCP_TOOLS)
        actor._ensure_executor = AsyncMock()
        actor._executor = MagicMock()
        actor._executor.create_session = AsyncMock(return_value="sess-1")

        await actor._create_session()

        create_kwargs = actor._executor.create_session.await_args.kwargs
        assert set(create_kwargs["allowed_tools"]) == set(
            decomposer_module.READ_ONLY_DECOMPOSER_TOOLS
        ) | set(decomposer_module.PRIMARY_DECOMPOSER_MCP_TOOLS)

    async def test_pool_session_limits_mcp_tools_to_details(self) -> None:
        actor = _make_actor()
        actor._cwd = "/tmp"
        actor._role = "pool"
        actor._admin_port = 19500
        actor._mcp_tool_names = decomposer_module.POOL_DECOMPOSER_MCP_TOOLS
        actor._mcp_tools = ",".join(decomposer_module.POOL_DECOMPOSER_MCP_TOOLS)
        actor._ensure_executor = AsyncMock()
        actor._executor = MagicMock()
        actor._executor.create_session = AsyncMock(return_value="sess-2")

        await actor._create_session()

        create_kwargs = actor._executor.create_session.await_args.kwargs
        assert set(create_kwargs["allowed_tools"]) == set(
            decomposer_module.READ_ONLY_DECOMPOSER_TOOLS
        ) | set(decomposer_module.POOL_DECOMPOSER_MCP_TOOLS)

    async def test_create_session_passes_provider_and_model_config(self) -> None:
        actor = _make_actor()
        actor._cwd = "/tmp"
        actor._role = "primary"
        actor._admin_port = 19500
        actor._mcp_tool_names = decomposer_module.PRIMARY_DECOMPOSER_MCP_TOOLS
        actor._mcp_tools = ",".join(decomposer_module.PRIMARY_DECOMPOSER_MCP_TOOLS)
        actor._step_config = StepConfig(
            provider="gemini",
            model_id="gemini-3.1-pro-preview",
        )
        actor._ensure_executor = AsyncMock()
        actor._executor = MagicMock()
        actor._executor.create_session = AsyncMock(return_value="sess-1")

        await actor._create_session()

        create_kwargs = actor._executor.create_session.await_args.kwargs
        assert create_kwargs["provider"] == "gemini"
        assert create_kwargs["config"].model_id == "gemini-3.1-pro-preview"

    async def test_prompt_preserves_provider_and_model_config(self) -> None:
        actor = _make_actor()
        actor._session_id = "sess-1"
        actor._step_config = StepConfig(
            provider="gemini",
            model_id="gemini-3.1-pro-preview",
        )
        actor._ensure_agent = AsyncMock()
        actor._executor = MagicMock()
        actor._executor.prompt_session = AsyncMock()

        await actor._prompt(
            "outline prompt",
            step_name="decompose_outline",
            timeout_seconds=900,
        )

        prompt_kwargs = actor._executor.prompt_session.await_args.kwargs
        assert prompt_kwargs["provider"] == "gemini"
        assert prompt_kwargs["config"].model_id == "gemini-3.1-pro-preview"
        assert prompt_kwargs["config"].timeout == 900

class TestDecomposerLifecycleLogging:
    """Verify the five ACP-session lifecycle events emit as distinct log lines.

    The decomposer's narrative should read cleanly as: new session
    (reason=initial) → prompt_seeded → prompt_reused × N → session_rotated
    (reason=turn_limit) → new session (reason=turn_limit) → prompt_seeded …
    These tests pin that narrative so a future refactor can't silently
    collapse it back into the old catch-all "session_ready" event.
    """

    async def test_first_detail_session_logs_as_initial_created(self, caplog) -> None:
        import logging

        caplog.set_level(logging.INFO)
        actor = _make_actor()
        actor._create_session = AsyncMock()

        async def _assign_session() -> None:
            actor._session_id = "sess-new"

        actor._create_session.side_effect = _assign_session

        result = await actor._ensure_mode_session(
            "detail", max_turns=5, seed_stale=True
        )

        assert result is True
        messages = [r.message for r in caplog.records]
        assert any("'event': 'decomposer.session_created'" in m for m in messages)
        assert any("'reason': 'initial'" in m for m in messages)
        assert not any("'event': 'decomposer.session_rotated'" in m for m in messages)

    async def test_turn_limit_logs_rotated_before_created(self, caplog) -> None:
        import logging

        caplog.set_level(logging.INFO)
        actor = _make_actor()
        actor._session_id = "sess-old"
        actor._session_mode = "detail"
        actor._session_turns_in_mode = 5  # hit max_turns
        actor._create_session = AsyncMock()

        async def _assign_session() -> None:
            actor._session_id = "sess-new"

        actor._create_session.side_effect = _assign_session

        await actor._ensure_mode_session(
            "detail", max_turns=5, seed_stale=False
        )

        messages = [r.message for r in caplog.records]
        rotated_idx = next(
            i
            for i, m in enumerate(messages)
            if "'event': 'decomposer.session_rotated'" in m
        )
        created_idx = next(
            i
            for i, m in enumerate(messages)
            if "'event': 'decomposer.session_created'" in m
        )
        # Rotated must fire BEFORE created — the narrative is
        # "discarding old then creating new," not both at once.
        assert rotated_idx < created_idx

        rotated_msg = messages[rotated_idx]
        assert "'reason': 'turn_limit'" in rotated_msg
        assert "'previous_session': 'sess-old'" in rotated_msg
        assert "'previous_turns': 5" in rotated_msg

    async def test_prompt_seeded_vs_reused_distinguished(self, caplog) -> None:
        import logging

        caplog.set_level(logging.INFO)
        actor = _make_actor()
        actor._prompt = AsyncMock()

        # Seeded path: fresh session returned
        actor._ensure_mode_session = AsyncMock(return_value=True)
        actor._session_id = "sess-1"
        actor._detail_seed_stale = True
        await actor._send_detail_prompt({"unit_id": "unit-1"})

        # Reused path: existing session, no seed
        actor._ensure_mode_session = AsyncMock(return_value=False)
        actor._detail_seed_stale = False
        actor._session_turns_in_mode = 2
        await actor._send_detail_prompt({"unit_id": "unit-2"})

        messages = [r.message for r in caplog.records]
        assert any("'event': 'decomposer.prompt_seeded'" in m for m in messages)
        reused_msg = next(
            m for m in messages if "'event': 'decomposer.prompt_reused'" in m
        )
        assert "'turn': 3" in reused_msg
        assert "'max_turns': 5" in reused_msg
