"""Tests for build_default_registry() -- T009."""

from __future__ import annotations

from maverick.prompts.models import GENERIC_PROVIDER, OverridePolicy

EXPECTED_STEPS = {
    "implement": (OverridePolicy.AUGMENT_ONLY, True),
    "completeness_review": (OverridePolicy.AUGMENT_ONLY, False),
    "correctness_review": (OverridePolicy.AUGMENT_ONLY, False),
    "fix": (OverridePolicy.AUGMENT_ONLY, False),
    "curator": (OverridePolicy.AUGMENT_ONLY, False),
    "commit_message": (OverridePolicy.REPLACE, False),
    "pr_description": (OverridePolicy.REPLACE, False),
    "pr_title": (OverridePolicy.REPLACE, False),
}


class TestBuildDefaultRegistry:
    """Tests for build_default_registry()."""

    def test_returns_registry_with_all_steps(self) -> None:
        from maverick.prompts.defaults import build_default_registry

        registry = build_default_registry()
        assert registry.step_names() == frozenset(EXPECTED_STEPS.keys())

    def test_all_entries_have_correct_policies(self) -> None:
        from maverick.prompts.defaults import build_default_registry

        registry = build_default_registry()
        for step_name, (expected_policy, _) in EXPECTED_STEPS.items():
            entry = registry.get(step_name)
            assert entry.policy == expected_policy, (
                f"{step_name}: expected {expected_policy}, got {entry.policy}"
            )

    def test_all_entries_have_correct_is_template(self) -> None:
        from maverick.prompts.defaults import build_default_registry

        registry = build_default_registry()
        for step_name, (_, expected_template) in EXPECTED_STEPS.items():
            entry = registry.get(step_name)
            assert entry.is_template == expected_template, (
                f"{step_name}: expected is_template={expected_template}"
            )

    def test_no_empty_text(self) -> None:
        from maverick.prompts.defaults import build_default_registry

        registry = build_default_registry()
        for step_name in EXPECTED_STEPS:
            entry = registry.get(step_name)
            assert entry.text, f"{step_name} has empty text"
            assert len(entry.text.strip()) > 0, f"{step_name} has whitespace-only text"

    def test_all_entries_use_generic_provider(self) -> None:
        from maverick.prompts.defaults import build_default_registry

        registry = build_default_registry()
        for step_name in EXPECTED_STEPS:
            assert registry.has(step_name, GENERIC_PROVIDER), (
                f"{step_name} missing generic provider entry"
            )

    def test_exactly_twelve_step_names(self) -> None:
        from maverick.prompts.defaults import build_default_registry

        registry = build_default_registry()
        assert len(registry.step_names()) == 8
