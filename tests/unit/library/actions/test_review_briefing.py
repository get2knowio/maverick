"""Tests for briefing context threading through the review pipeline."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from maverick.library.actions.review import run_review_fix_loop


@pytest.mark.asyncio
async def test_briefing_context_reaches_reviewer() -> None:
    """Briefing context is threaded into the review_context dict for the reviewer."""
    captured_context: dict[str, Any] = {}

    async def _fake_execute(
        step_name: str,
        agent_name: str,
        prompt: Any,
        output_schema: Any,
        **kwargs: Any,
    ) -> Any:
        from maverick.executor.result import ExecutorResult
        from maverick.models.review_models import GroupedReviewResult

        # Capture the prompt (review_context dict) passed to the reviewer
        captured_context.update(prompt if isinstance(prompt, dict) else {})
        return ExecutorResult(
            output=GroupedReviewResult(groups=[]),
            success=True,
            events=(),
            usage=None,
        )

    mock_executor = AsyncMock()
    mock_executor.execute.side_effect = _fake_execute
    mock_executor.cleanup = AsyncMock()

    review_input = {
        "review_metadata": {"title": "Test PR"},
        "changed_files": ["src/foo.py"],
        "diff": "some diff",
    }

    with (
        patch(
            "maverick.executor.create_default_executor",
            return_value=mock_executor,
        ),
        patch(
            "maverick.agents.reviewers.UnifiedReviewerAgent",
        ),
    ):
        await run_review_fix_loop(
            review_input=review_input,
            base_branch="main",
            max_attempts=1,
            briefing_context="## Key Decisions\n- Use Pydantic",
        )

    expected = "## Key Decisions\n- Use Pydantic"
    assert captured_context.get("briefing_context") == expected


@pytest.mark.asyncio
async def test_no_briefing_context_omitted() -> None:
    """When briefing_context is None, it is not added to review_context."""
    captured_context: dict[str, Any] = {}

    async def _fake_execute(
        step_name: str,
        agent_name: str,
        prompt: Any,
        output_schema: Any,
        **kwargs: Any,
    ) -> Any:
        from maverick.executor.result import ExecutorResult
        from maverick.models.review_models import GroupedReviewResult

        captured_context.update(prompt if isinstance(prompt, dict) else {})
        return ExecutorResult(
            output=GroupedReviewResult(groups=[]),
            success=True,
            events=(),
            usage=None,
        )

    mock_executor = AsyncMock()
    mock_executor.execute.side_effect = _fake_execute
    mock_executor.cleanup = AsyncMock()

    review_input = {
        "review_metadata": {"title": "Test PR"},
        "changed_files": ["src/foo.py"],
        "diff": "some diff",
    }

    with (
        patch(
            "maverick.executor.create_default_executor",
            return_value=mock_executor,
        ),
        patch(
            "maverick.agents.reviewers.UnifiedReviewerAgent",
        ),
    ):
        await run_review_fix_loop(
            review_input=review_input,
            base_branch="main",
            max_attempts=1,
            briefing_context=None,
        )

    assert "briefing_context" not in captured_context
