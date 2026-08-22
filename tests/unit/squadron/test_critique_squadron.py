"""Tests for :class:`maverick.squadron.critique.CritiqueSquadron`.

The squadron behind the standalone ``maverick critique`` command: one
reviewer pair, no coder, no tiers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from maverick.config import AgentBindingConfig, AgentsConfig, MaverickConfig
from maverick.squadron.critique import CritiqueSquadron


@pytest.fixture
def review_only_config() -> MaverickConfig:
    """An ``agents:`` block with **only** ``review`` bound.

    Deliberately missing ``implement`` — see
    :func:`test_opens_with_only_a_review_binding`.
    """
    return MaverickConfig(
        agents=AgentsConfig(
            review=AgentBindingConfig(provider="claude", model_id="claude-haiku-4-5"),
        )
    )


async def test_opens_with_only_a_review_binding(
    stub_airframe_runtime: dict[str, Any],
    review_only_config: MaverickConfig,
    tmp_path: Path,
) -> None:
    """Opens on a repository configured only for review — no ``agents.implement``.

    This is the assertion that makes research R1's rejection of
    ``FlySquadron`` load-bearing: ``FlySquadron`` also builds a
    ``CodingAgent``, which requires an ``agents.implement`` binding, so
    reusing it here would make a read-only review command fail to start
    on exactly this config (``test_squadron_requires_agents_config`` in
    ``test_fly_squadron.py`` pins that failure). ``CritiqueSquadron``'s
    dependency footprint is exactly ``agents.review``.
    """
    assert review_only_config.agents.implement is None

    async with CritiqueSquadron(cwd=tmp_path, config=review_only_config) as squadron:
        assert squadron.correctness_reviewer.review_kind == "correctness"
        assert squadron.completeness_reviewer.review_kind == "completeness"

    # Exactly two runtimes: one per lens, no coder.
    assert len(stub_airframe_runtime["constructed"]) == 2


async def test_builds_exactly_one_pair_with_distinct_runtimes(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    """One pair at DEFAULT_TIER, each lens on its own runtime."""
    async with CritiqueSquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        correctness = squadron.correctness_reviewer
        completeness = squadron.completeness_reviewer
        assert correctness is not completeness
        assert correctness._runtime is not completeness._runtime
        # No tier suffix — critique has no complexity to route on.
        assert correctness.tag == "correctness-reviewer"
        assert completeness.tag == "completeness-reviewer"
        assert list(squadron._all_agents()) == [correctness, completeness]

    assert len(stub_airframe_runtime["constructed"]) == 2


async def test_workflow_name_is_critique(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    """``WORKFLOW_NAME`` rides onto every agent's protection block records."""
    assert CritiqueSquadron.WORKFLOW_NAME == "critique"

    async with CritiqueSquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        for agent in squadron._all_agents():
            assert agent._workflow == "critique"
            # 056: the squadron builds one real policy + collector and
            # threads it into both lenses.
            assert agent._protection_policy is squadron.protection_policy
            assert agent._block_collector is squadron.block_collector


async def test_close_tears_down_both_agents(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    """``close()`` closes both reviewers' runtimes."""
    squadron = CritiqueSquadron(cwd=tmp_path, config=config_with_agents)
    await squadron.open()
    assert len(stub_airframe_runtime["constructed"]) == 2

    await squadron.close()

    assert all(r.close_calls >= 1 for r in stub_airframe_runtime["constructed"])


async def test_async_with_opens_and_closes(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    """``async with`` is the supported lifecycle: open on entry, close on exit."""
    async with CritiqueSquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        assert squadron.correctness_reviewer is not None
        assert all(r.close_calls == 0 for r in stub_airframe_runtime["constructed"])

    assert all(r.close_calls >= 1 for r in stub_airframe_runtime["constructed"])


async def test_missing_review_binding_fails_at_open(tmp_path: Path) -> None:
    """An empty ``agents:`` block surfaces as a clear ValueError naming the role."""
    with pytest.raises(ValueError, match="agents.review"):
        async with CritiqueSquadron(cwd=tmp_path, config=MaverickConfig()):
            pass


async def test_reviewer_config_threads_into_both_lenses(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    """An explicit reviewer ``StepConfig`` reaches both agents."""
    from maverick.executor.config import StepConfig

    step_config = StepConfig(timeout=321)

    async with CritiqueSquadron(
        cwd=tmp_path,
        config=config_with_agents,
        reviewer_config=step_config,
    ) as squadron:
        for agent in squadron._all_agents():
            assert agent._step_config is step_config
