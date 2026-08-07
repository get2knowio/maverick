"""Tests for ``ProtectionPolicy.decide`` (protection/policy.py).

See specs/056-context-file-protection/data-model.md's "ProtectionPolicy"
section for the normative decision algorithm this exercises.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.protection.config import ProtectionConfig
from maverick.protection.policy import PolicyDecision, ProtectionPolicy


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


class TestDefaultRulesCreateEditDelete:
    def test_agents_md_at_root_blocked(self, root: Path) -> None:
        policy = ProtectionPolicy.build(root)
        for op in ("create", "edit", "delete"):
            decision = policy.decide("AGENTS.md", op)
            assert decision.blocked is True
            assert decision.rule

    def test_claude_md_nested_case_insensitive_blocked(self, root: Path) -> None:
        policy = ProtectionPolicy.build(root)
        decision = policy.decide("sub/dir/claude.MD".replace("MD", "md"), "edit")
        assert decision.blocked is True

    def test_specify_memory_tree_blocked_any_depth(self, root: Path) -> None:
        policy = ProtectionPolicy.build(root)
        assert policy.decide(".specify/memory/constitution.md", "delete").blocked is True
        assert policy.decide(".specify/memory/nested/x.md", "edit").blocked is True

    def test_unprotected_path_allowed(self, root: Path) -> None:
        policy = ProtectionPolicy.build(root)
        decision = policy.decide("src/real_work.py", "edit")
        assert decision.blocked is False
        assert decision.rule == ""
        assert decision.reason == ""

    def test_readme_not_protected(self, root: Path) -> None:
        policy = ProtectionPolicy.build(root)
        assert policy.decide("README.md", "edit").blocked is False


class TestRenameBlockedOnEitherSide:
    def test_rename_source_protected_blocks(self, root: Path) -> None:
        policy = ProtectionPolicy.build(root)
        decision = policy.decide("CLAUDE.md", "rename", destination="CLAUDE.old.txt")
        assert decision.blocked is True

    def test_rename_destination_protected_blocks(self, root: Path) -> None:
        policy = ProtectionPolicy.build(root)
        decision = policy.decide("notes.txt", "rename", destination="AGENTS.md")
        assert decision.blocked is True

    def test_rename_neither_side_protected_allowed(self, root: Path) -> None:
        policy = ProtectionPolicy.build(root)
        decision = policy.decide("notes.txt", "rename", destination="notes2.txt")
        assert decision.blocked is False


class TestPolicyDecisionShape:
    def test_decision_is_frozen_dataclass_with_fields(self, root: Path) -> None:
        policy = ProtectionPolicy.build(root)
        decision = policy.decide("AGENTS.md", "edit")
        assert isinstance(decision, PolicyDecision)
        assert decision.blocked is True
        assert isinstance(decision.rule, str) and decision.rule
        assert isinstance(decision.reason, str) and decision.reason
        with pytest.raises(Exception):  # noqa: B017, PT011 — frozen dataclass mutation
            decision.blocked = False  # type: ignore[misc]


class TestSymlinkDualMatching:
    def test_symlink_planted_at_protected_literal_path_blocked(self, root: Path) -> None:
        # A symlink literally named CLAUDE.md pointing elsewhere: the
        # literal side alone must catch it (FR-014), regardless of target.
        target = root / "real_target.txt"
        target.write_text("hello")
        link = root / "CLAUDE.md"
        link.symlink_to(target)
        policy = ProtectionPolicy.build(root)
        decision = policy.decide("CLAUDE.md", "edit")
        assert decision.blocked is True

    def test_symlink_resolving_to_protected_target_blocked(self, root: Path) -> None:
        # A symlink at an unprotected literal path whose resolved target
        # is protected must also be caught (the resolved side).
        real_protected = root / "AGENTS.md"
        real_protected.write_text("hi")
        link = root / "sub"
        link.mkdir()
        alias = link / "not_protected_name.md"
        alias.symlink_to(real_protected)
        policy = ProtectionPolicy.build(root)
        decision = policy.decide("sub/not_protected_name.md", "edit")
        assert decision.blocked is True


class TestOutsideRootNotProtected:
    def test_escaping_path_not_protected(self, root: Path) -> None:
        policy = ProtectionPolicy.build(root)
        decision = policy.decide("../../etc/CLAUDE.md", "edit")
        # Escapes root entirely -> normalize_relpath returns None for both
        # sides -> never matched -> allowed.
        assert decision.blocked is False


class TestConfigDrivenRulesAllowlistAndAdditionalGlobs:
    def test_allowlist_exempts_default_protected_name(self, root: Path) -> None:
        config = ProtectionConfig(allowlist=["AGENTS.md"])
        policy = ProtectionPolicy.build(root, config)
        assert policy.decide("AGENTS.md", "edit").blocked is False
        # Unrelated default-protected file still blocked.
        assert policy.decide("CLAUDE.md", "edit").blocked is True

    def test_additional_globs_extends_protected_set(self, root: Path) -> None:
        config = ProtectionConfig(additional_globs=["docs/agent-rules/**"])
        policy = ProtectionPolicy.build(root, config)
        assert policy.decide("docs/agent-rules/style.md", "edit").blocked is True
        assert policy.decide("docs/other/style.md", "edit").blocked is False

    def test_allowlist_wildcard_full_opt_out(self, root: Path) -> None:
        config = ProtectionConfig(allowlist=["**"])
        policy = ProtectionPolicy.build(root, config)
        assert policy.decide("AGENTS.md", "edit").blocked is False
        assert policy.decide(".specify/memory/x.md", "edit").blocked is False

    def test_invalid_pattern_dropped_rest_still_applies(self, root: Path) -> None:
        config = ProtectionConfig(additional_globs=["a\\", "docs/**"])
        policy = ProtectionPolicy.build(root, config)
        assert "a\\" in policy.dropped_patterns
        assert policy.decide("docs/x.md", "edit").blocked is True


class TestFailClosedOnInternalError:
    def test_decide_swallows_normalize_errors_and_denies_default_names(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        policy = ProtectionPolicy.build(root)

        def _boom(*args: object, **kwargs: object) -> str:
            raise RuntimeError("boom")

        monkeypatch.setattr("maverick.protection.policy.normalize_relpath", _boom)
        decision = policy.decide("CLAUDE.md", "edit")
        assert decision.blocked is True
        assert "fail-closed" in decision.rule

    def test_decide_swallows_normalize_errors_and_allows_non_default_names(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        policy = ProtectionPolicy.build(root)

        def _boom(*args: object, **kwargs: object) -> str:
            raise RuntimeError("boom")

        monkeypatch.setattr("maverick.protection.policy.normalize_relpath", _boom)
        decision = policy.decide("src/real_work.py", "edit")
        assert decision.blocked is False
