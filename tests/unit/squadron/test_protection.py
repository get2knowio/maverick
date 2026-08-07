"""Tests for ``Squadron._build_protection`` (056-context-file-protection T030).

The base ``Squadron.open()`` builds one ``ProtectionPolicy`` +
``BlockCollector`` from ``lookup_protection_config(self._config)`` before
any agent is constructed, then threads them into every agent via
``_agent_protection_kwargs()``. Uses ``FlySquadron`` as the concrete
subclass under test — the mechanism lives entirely in the base class, so
any subclass would do; fly's is the most exercised.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maverick.config import MaverickConfig
from maverick.protection.policy import ProtectionPolicy
from maverick.protection.records import BlockCollector
from maverick.squadron.fly import DEFAULT_TIER, FlySquadron


class TestDefaultsOnlyWhenNoProtectionBlock:
    async def test_policy_built_with_defaults(
        self,
        stub_airframe_runtime: dict[str, Any],
        config_with_agents: MaverickConfig,
        tmp_path: Path,
    ) -> None:
        async with FlySquadron(cwd=tmp_path, config=config_with_agents) as squadron:
            assert isinstance(squadron.protection_policy, ProtectionPolicy)
            assert isinstance(squadron.block_collector, BlockCollector)
            # Default protected set active even with no protection: block.
            assert squadron.protection_policy.decide("CLAUDE.md", "edit").blocked is True
            assert squadron.protection_policy.decide("src/x.py", "edit").blocked is False

    async def test_policy_none_until_open(
        self, config_with_agents: MaverickConfig, tmp_path: Path
    ) -> None:
        squadron = FlySquadron(cwd=tmp_path, config=config_with_agents)
        assert squadron.protection_policy is None
        assert squadron.block_collector is None


class TestConfiguredRunReflectsMaverickYaml:
    async def test_allowlist_from_config_exempts_default_name(
        self,
        stub_airframe_runtime: dict[str, Any],
        config_with_agents: MaverickConfig,
        tmp_path: Path,
    ) -> None:
        configured = config_with_agents.model_copy(
            update={"protection": {"allowlist": ["AGENTS.md"]}}
        )
        async with FlySquadron(cwd=tmp_path, config=configured) as squadron:
            assert squadron.protection_policy is not None
            assert squadron.protection_policy.decide("AGENTS.md", "edit").blocked is False
            # Unrelated default-protected name still blocked.
            assert squadron.protection_policy.decide("CLAUDE.md", "edit").blocked is True

    async def test_additional_globs_from_config_extends_protected_set(
        self,
        stub_airframe_runtime: dict[str, Any],
        config_with_agents: MaverickConfig,
        tmp_path: Path,
    ) -> None:
        configured = config_with_agents.model_copy(
            update={"protection": {"additional_globs": ["docs/agent-rules/**"]}}
        )
        async with FlySquadron(cwd=tmp_path, config=configured) as squadron:
            assert squadron.protection_policy is not None
            decision = squadron.protection_policy.decide("docs/agent-rules/x.md", "edit")
            assert decision.blocked is True
            assert squadron.protection_policy.decide("docs/other/x.md", "edit").blocked is False

    async def test_malformed_protection_block_degrades_to_defaults(
        self,
        stub_airframe_runtime: dict[str, Any],
        config_with_agents: MaverickConfig,
        tmp_path: Path,
    ) -> None:
        configured = config_with_agents.model_copy(update={"protection": "not-a-dict"})
        async with FlySquadron(cwd=tmp_path, config=configured) as squadron:
            assert squadron.protection_policy is not None
            # Degraded to defaults — no crash, default set still active.
            assert squadron.protection_policy.decide("CLAUDE.md", "edit").blocked is True


class TestSameInstancesThreadedIntoEveryAgent:
    async def test_all_agents_share_the_same_policy_and_collector(
        self,
        stub_airframe_runtime: dict[str, Any],
        config_with_agents: MaverickConfig,
        tmp_path: Path,
    ) -> None:
        async with FlySquadron(cwd=tmp_path, config=config_with_agents) as squadron:
            policy = squadron.protection_policy
            collector = squadron.block_collector
            coder = squadron.coder_for(DEFAULT_TIER)
            correctness = squadron.correctness_reviewer_for(DEFAULT_TIER)
            completeness = squadron.completeness_reviewer_for(DEFAULT_TIER)
            for agent in (coder, correctness, completeness):
                assert agent._protection_policy is policy  # noqa: SLF001
                assert agent._block_collector is collector  # noqa: SLF001
                assert agent._workflow == FlySquadron.WORKFLOW_NAME  # noqa: SLF001


class TestProtectionSetupFailureDegradesGracefully:
    async def test_capture_failure_disables_protection_for_the_run(
        self,
        stub_airframe_runtime: dict[str, Any],
        config_with_agents: MaverickConfig,
        tmp_path: Path,
        monkeypatch: Any,
    ) -> None:
        """A squadron-open-time baseline-capture failure must not take
        down the whole run — every agent falls back to the
        zero-behavior-change (``protection_policy=None``) path."""

        async def _boom(*args: object, **kwargs: object) -> None:
            raise OSError("simulated capture failure")

        monkeypatch.setattr("maverick.protection.snapshot.SnapshotManifest.capture", _boom)
        async with FlySquadron(cwd=tmp_path, config=config_with_agents) as squadron:
            assert squadron.protection_policy is None
            assert squadron.block_collector is None
            coder = squadron.coder_for(DEFAULT_TIER)
            assert coder._protection_policy is None  # noqa: SLF001
