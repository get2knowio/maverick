"""Unit tests for the refuel DecomposerActor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from maverick.actors.decomposer import DecomposerActor


def _make_actor() -> DecomposerActor:
    actor = object.__new__(DecomposerActor)
    actor._handle_actor_exit = MagicMock(return_value=False)
    actor._run_async = MagicMock()
    actor.send = MagicMock()
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
