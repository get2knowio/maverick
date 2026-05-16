"""Tests for the bundled persona system-prompt loader + plumbing.

Two surfaces are covered:

1. ``load_persona_system_prompt`` — file lookup, missing-file fallback,
   the 18 expected personas are all loadable.
2. :meth:`Agent._execute_via_runtime` forwards the loaded prompt as
   ``system=`` on every adapter call.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from airframe.cost import CostRecord
from airframe.protocol import RuntimeResult

from maverick.agents.coding import CodingAgent
from maverick.agents.system_prompts import (
    available_personas,
    load_persona_system_prompt,
)

# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def test_load_returns_none_for_missing_persona() -> None:
    assert load_persona_system_prompt("maverick.does-not-exist") is None


def test_load_returns_none_for_empty_name() -> None:
    assert load_persona_system_prompt("") is None
    assert load_persona_system_prompt(None) is None


def test_load_returns_body_for_known_persona() -> None:
    prompt = load_persona_system_prompt("maverick.consolidator")
    assert prompt is not None
    # No leftover YAML frontmatter (would start with --- if it leaked).
    assert not prompt.startswith("---")
    # Anchored by a recognizable phrase from the persona body.
    assert "knowledge consolidator" in prompt


def test_available_personas_lists_all_eighteen() -> None:
    """The 18 personas we shipped under runtime/opencode/profile/agents/."""
    expected = {
        "maverick.codebase-analyst",
        "maverick.completeness-reviewer",
        "maverick.consolidator",
        "maverick.contrarian",
        "maverick.correctness-reviewer",
        "maverick.criteria-writer",
        "maverick.curator",
        "maverick.decomposer",
        "maverick.flight-plan-generator",
        "maverick.generator",
        "maverick.implementer",
        "maverick.navigator",
        "maverick.preflight-contrarian",
        "maverick.recon",
        "maverick.runway-seed",
        "maverick.scopist",
        "maverick.structuralist",
        "maverick.validation-fixer",
    }
    assert set(available_personas()) == expected


# ---------------------------------------------------------------------------
# Plumbing: Agent._execute_via_runtime forwards system=
# ---------------------------------------------------------------------------


def _impl_payload() -> dict[str, Any]:
    return {
        "kind": "submit_implementation",
        "summary": "done",
        "files_changed": [],
        "commands_run": [],
        "verification": "",
        "next_step": "",
    }


def _cost() -> CostRecord:
    return CostRecord(
        provider_id="anthropic",
        model_id="claude-haiku-4-5",
        cost_usd=0.0,
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish="end_turn",
    )


def _make_runtime() -> Any:
    runtime = MagicMock()
    runtime.label = "stub"
    runtime.execute = AsyncMock(
        return_value=RuntimeResult(
            text="", structured=_impl_payload(), cost=_cost(), finish="end_turn"
        )
    )
    runtime.reset = AsyncMock()
    runtime.close = AsyncMock()
    return runtime


async def test_execute_forwards_persona_system_prompt() -> None:
    """A real persona name reaches the runtime as ``system=``."""
    runtime = _make_runtime()
    agent = CodingAgent(runtime=runtime, cwd="/tmp")
    async with agent:
        await agent.implement("do the work")
    call = runtime.execute.await_args
    assert call.kwargs["persona"] == "maverick.implementer"
    system = call.kwargs.get("system")
    assert system is not None
    # Anchor on a load-bearing phrase from the implementer persona body.
    assert "expert software engineer" in system.lower()


async def test_execute_passes_system_none_for_unknown_persona() -> None:
    """An unknown persona name → ``system=None`` (no crash)."""
    runtime = _make_runtime()
    agent = CodingAgent(runtime=runtime, cwd="/tmp")
    # Override the class-var to something unmapped.
    agent._opencode_agent_instance = "maverick.does-not-exist"  # noqa: SLF001
    async with agent:
        await agent.implement("x")
    assert runtime.execute.await_args.kwargs.get("system") is None
