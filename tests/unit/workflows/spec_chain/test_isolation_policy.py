"""Unit tests for `SpecChainWorkflow._isolation_policy` (057-isolated-bead-
workspaces, US6). Covers what `land_step_artifacts`/`_strip_protected_paths`
used to test directly (T103, research.md R10/R11) — protection is now
`fold_exclusions` on the run's `IsolationPolicy`, wired from the same
`protection:` config block.
"""

from __future__ import annotations

from pathlib import Path

from maverick.config import AgentBindingConfig, AgentsConfig, MaverickConfig
from maverick.workflows.spec_chain.workflow import SpecChainWorkflow


def _workflow(config: MaverickConfig | None = None) -> SpecChainWorkflow:
    cfg = config or MaverickConfig(
        agents=AgentsConfig(generate=AgentBindingConfig(provider="claude", model_id="stub-model"))
    )
    return SpecChainWorkflow(config=cfg)


class TestIsolationPolicyShape:
    def test_workflow_and_reuse_and_retain(self) -> None:
        policy = _workflow()._isolation_policy(home=None)
        assert policy.workflow == "spec-chain"
        assert policy.reuse is True
        assert policy.retain_on_failure is True

    def test_root_defaults_to_workspace_config_root(self) -> None:
        policy = _workflow()._isolation_policy(home=None)
        assert policy.root == Path.home() / ".maverick" / "workspaces"

    def test_home_override_wins_over_config(self, tmp_path: Path) -> None:
        policy = _workflow()._isolation_policy(home=tmp_path)
        assert policy.root == tmp_path / ".maverick" / "workspaces"


class TestFoldExclusions:
    def test_default_protected_paths_always_excluded(self) -> None:
        policy = _workflow()._isolation_policy(home=None)
        assert ".specify/memory" in policy.fold_exclusions
        assert "AGENTS.md" in policy.fold_exclusions
        assert "CLAUDE.md" in policy.fold_exclusions

    def test_additional_globs_from_config_are_appended(self) -> None:
        config = MaverickConfig(
            agents=AgentsConfig(
                generate=AgentBindingConfig(provider="claude", model_id="stub-model")
            ),
            protection={"additional_globs": ["specs/001-foo/secret-notes.md"]},
        )
        policy = _workflow(config)._isolation_policy(home=None)
        assert "specs/001-foo/secret-notes.md" in policy.fold_exclusions

    def test_no_protection_config_still_applies_defaults(self) -> None:
        """`config.protection=None` degrades to defaults-only, never 'no
        protection' -- the same contract `land_step_artifacts` used to
        guarantee for `config=None`."""
        policy = _workflow()._isolation_policy(home=None)
        assert set(policy.fold_exclusions) == {".specify/memory", "AGENTS.md", "CLAUDE.md"}

    def test_malformed_protection_config_degrades_to_defaults(self) -> None:
        config = MaverickConfig(
            agents=AgentsConfig(
                generate=AgentBindingConfig(provider="claude", model_id="stub-model")
            ),
            protection="not-a-dict",
        )
        policy = _workflow(config)._isolation_policy(home=None)
        assert ".specify/memory" in policy.fold_exclusions
        assert "AGENTS.md" in policy.fold_exclusions
