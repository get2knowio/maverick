"""Tests for :func:`maverick.squadron.reviewers.build_reviewer_pair`.

The pair-construction sequence extracted from ``FlySquadron`` (058
research R1). These assert the details that make the extraction
behavior-preserving: two independent runtimes, per-instance personas,
tier-suffixed tags, and the 056 protection DI bundle threading through.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maverick.config import AgentsConfig
from maverick.squadron.reviewers import (
    COMPLETENESS_PERSONA,
    CORRECTNESS_PERSONA,
    build_reviewer_pair,
)
from maverick.squadron.tiers import DEFAULT_TIER


def test_pair_has_two_distinct_agents_and_runtimes(
    stub_airframe_runtime: dict[str, Any],
    full_agents_config: AgentsConfig,
    tmp_path: Path,
) -> None:
    """Each reviewer owns its own runtime — never a shared one.

    The two lenses run concurrently, so sharing a runtime would
    interleave two conversations into one scope.
    """
    correctness, completeness = build_reviewer_pair(
        cwd=tmp_path,
        agents_config=full_agents_config,
    )

    assert correctness is not completeness
    assert correctness._runtime is not completeness._runtime
    assert len(stub_airframe_runtime["constructed"]) == 2


def test_pair_carries_the_two_lenses_and_personas(
    stub_airframe_runtime: dict[str, Any],
    full_agents_config: AgentsConfig,
    tmp_path: Path,
) -> None:
    """(correctness, completeness) in that order, with the fixed personas."""
    correctness, completeness = build_reviewer_pair(
        cwd=tmp_path,
        agents_config=full_agents_config,
    )

    assert correctness.review_kind == "correctness"
    assert completeness.review_kind == "completeness"
    assert (
        correctness._persona_name_instance
        == CORRECTNESS_PERSONA
        == "maverick.correctness-reviewer"
    )
    assert (
        completeness._persona_name_instance
        == COMPLETENESS_PERSONA
        == "maverick.completeness-reviewer"
    )
    assert correctness._cwd == str(tmp_path)
    assert completeness._cwd == str(tmp_path)


def test_default_tier_tags_carry_no_suffix(
    stub_airframe_runtime: dict[str, Any],
    full_agents_config: AgentsConfig,
    tmp_path: Path,
) -> None:
    """``DEFAULT_TIER`` (the role's base binding) means unsuffixed tags."""
    correctness, completeness = build_reviewer_pair(
        cwd=tmp_path,
        agents_config=full_agents_config,
        tier_name=DEFAULT_TIER,
    )

    assert correctness.tag == "correctness-reviewer"
    assert completeness.tag == "completeness-reviewer"


def test_named_tier_suffixes_both_tags(
    stub_airframe_runtime: dict[str, Any],
    full_agents_config: AgentsConfig,
    tmp_path: Path,
) -> None:
    """A named tier suffixes both tags so cost telemetry stays separable."""
    correctness, completeness = build_reviewer_pair(
        cwd=tmp_path,
        agents_config=full_agents_config,
        tier_name="complex",
    )

    assert correctness.tag == "correctness-reviewer.complex"
    assert completeness.tag == "completeness-reviewer.complex"


def test_binding_override_pins_both_runtimes(
    stub_airframe_runtime: dict[str, Any],
    full_agents_config: AgentsConfig,
    tmp_path: Path,
) -> None:
    """An explicit binding override reaches both runtimes, not just one."""
    from maverick.config import AgentBindingConfig

    build_reviewer_pair(
        cwd=tmp_path,
        agents_config=full_agents_config,
        tier_name="complex",
        binding_override=AgentBindingConfig(provider="opencode", model_id="gpt-5-nano"),
    )

    constructed = stub_airframe_runtime["constructed"]
    assert len(constructed) == 2
    assert {r.model for r in constructed} == {"gpt-5-nano"}
    assert {r.provider_id for r in constructed} == {"opencode"}


def test_protection_kwargs_thread_into_both_agents(
    stub_airframe_runtime: dict[str, Any],
    full_agents_config: AgentsConfig,
    tmp_path: Path,
) -> None:
    """The 056 DI bundle is splatted into each agent, not dropped."""
    from maverick.protection.config import ProtectionConfig
    from maverick.protection.policy import ProtectionPolicy
    from maverick.protection.records import BlockCollector

    policy = ProtectionPolicy.build(tmp_path, ProtectionConfig())
    collector = BlockCollector()

    correctness, completeness = build_reviewer_pair(
        cwd=tmp_path,
        agents_config=full_agents_config,
        protection_kwargs={
            "protection_policy": policy,
            "block_collector": collector,
            "workflow": "critique",
            "baseline_manifest": None,
        },
    )

    for agent in (correctness, completeness):
        assert agent._protection_policy is policy
        assert agent._block_collector is collector
        assert agent._workflow == "critique"


def test_no_protection_kwargs_leaves_agents_unguarded(
    stub_airframe_runtime: dict[str, Any],
    full_agents_config: AgentsConfig,
    tmp_path: Path,
) -> None:
    """Omitting the bundle is the pre-056 zero-behavior-change path."""
    correctness, completeness = build_reviewer_pair(
        cwd=tmp_path,
        agents_config=full_agents_config,
    )

    for agent in (correctness, completeness):
        assert agent._protection_policy is None
        assert agent._block_collector is None


def test_step_config_reaches_both_agents(
    stub_airframe_runtime: dict[str, Any],
    full_agents_config: AgentsConfig,
    tmp_path: Path,
) -> None:
    """Per-step provider settings land on both lenses identically."""
    from maverick.executor.config import StepConfig

    step_config = StepConfig(timeout=123)

    correctness, completeness = build_reviewer_pair(
        cwd=tmp_path,
        agents_config=full_agents_config,
        step_config=step_config,
    )

    assert correctness._step_config is step_config
    assert completeness._step_config is step_config
