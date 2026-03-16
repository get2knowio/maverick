"""Unit tests for fetch_runway_context step function."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from maverick.library.actions.types import RunwayRetrievalResult
from maverick.workflows.fly_beads.models import BeadContext
from maverick.workflows.fly_beads.steps import fetch_runway_context

_STEPS_MOD = "maverick.workflows.fly_beads.steps"


def _make_ctx(**overrides: Any) -> BeadContext:
    defaults: dict[str, Any] = {
        "bead_id": "b1",
        "title": "Test bead",
        "description": "Do work",
        "epic_id": "e1",
        "cwd": Path("/tmp/ws"),
    }
    defaults.update(overrides)
    return BeadContext(**defaults)


def _make_wf(*, runway_enabled: bool = True) -> MagicMock:
    """Build a mock workflow with runway config."""
    wf = MagicMock()

    runway_cfg = MagicMock()
    runway_cfg.enabled = runway_enabled

    retrieval_cfg = MagicMock()
    retrieval_cfg.max_passages = 10
    retrieval_cfg.bm25_top_k = 20
    retrieval_cfg.max_context_chars = 4000
    runway_cfg.retrieval = retrieval_cfg

    wf._config.runway = runway_cfg
    return wf


class TestFetchRunwayContext:
    async def test_populates_ctx(self) -> None:
        """Runway with data → ctx.runway_context set."""
        wf = _make_wf()
        ctx = _make_ctx()
        result = RunwayRetrievalResult(
            success=True,
            context_text="### Recent Outcomes\n- bead-1",
            passages_used=2,
            outcomes_used=1,
            error=None,
        )

        with patch(
            f"{_STEPS_MOD}.retrieve_runway_context",
            new_callable=AsyncMock,
            return_value=result,
        ):
            await fetch_runway_context(wf, ctx)

        assert ctx.runway_context == "### Recent Outcomes\n- bead-1"

    async def test_skips_when_disabled(self) -> None:
        """runway.enabled=False → ctx.runway_context stays None."""
        wf = _make_wf(runway_enabled=False)
        ctx = _make_ctx()

        await fetch_runway_context(wf, ctx)

        assert ctx.runway_context is None

    async def test_best_effort_on_exception(self) -> None:
        """Exception → no raise, ctx unchanged."""
        wf = _make_wf()
        ctx = _make_ctx()

        with patch(
            f"{_STEPS_MOD}.retrieve_runway_context",
            new_callable=AsyncMock,
            side_effect=RuntimeError("store crash"),
        ):
            await fetch_runway_context(wf, ctx)

        assert ctx.runway_context is None

    async def test_empty_result_leaves_ctx_none(self) -> None:
        """Empty context_text → ctx.runway_context stays None."""
        wf = _make_wf()
        ctx = _make_ctx()
        result = RunwayRetrievalResult(
            success=True,
            context_text="",
            passages_used=0,
            outcomes_used=0,
            error=None,
        )

        with patch(
            f"{_STEPS_MOD}.retrieve_runway_context",
            new_callable=AsyncMock,
            return_value=result,
        ):
            await fetch_runway_context(wf, ctx)

        assert ctx.runway_context is None

    async def test_no_runway_config(self) -> None:
        """No runway attribute on config → returns without error."""
        wf = MagicMock()
        wf._config = MagicMock(spec=[])  # no runway attribute
        ctx = _make_ctx()

        await fetch_runway_context(wf, ctx)

        assert ctx.runway_context is None
