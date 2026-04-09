"""Unit tests for action intent registry.

Tests the intents.py module including:
- T030: All registered actions have intent descriptions
- T031: No orphan keys in ACTION_INTENTS
- T032: get_intent() returns correct values
"""

from __future__ import annotations

from maverick.library.actions import register_all_actions
from maverick.library.actions.intents import ACTION_INTENTS, get_intent
from maverick.registry import ComponentRegistry


class TestActionIntentCoverage:
    """T030: Every registered action must have a non-empty intent description."""

    def test_all_registered_actions_have_intents(self) -> None:
        """Every action in ComponentRegistry.actions has a non-empty entry."""
        registry = ComponentRegistry()
        register_all_actions(registry)
        registered = set(registry.actions.list_names())
        intents = set(ACTION_INTENTS.keys())

        missing = registered - intents
        assert not missing, f"Actions missing intent descriptions: {missing}"

    def test_all_intent_values_are_non_empty_strings(self) -> None:
        """Every value in ACTION_INTENTS must be a non-empty string."""
        for action_name, description in ACTION_INTENTS.items():
            assert isinstance(description, str), (
                f"Intent for '{action_name}' is not a string: {type(description)}"
            )
            assert description.strip(), f"Intent for '{action_name}' is empty or whitespace-only"


class TestNoOrphanIntentKeys:
    """T031: No orphan keys exist in ACTION_INTENTS."""

    def test_no_orphan_intent_keys(self) -> None:
        """Every key in ACTION_INTENTS must correspond to a registered action."""
        registry = ComponentRegistry()
        register_all_actions(registry)
        registered = set(registry.actions.list_names())
        intents = set(ACTION_INTENTS.keys())

        orphans = intents - registered
        assert not orphans, f"Orphan intent keys (no registered action): {orphans}"


class TestGetIntent:
    """T032: get_intent() returns correct description for known actions."""

    def test_returns_description_for_known_action(self) -> None:
        """get_intent() returns the intent string for a registered action."""
        result = get_intent("run_preflight_checks")
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_none_for_unknown_action(self) -> None:
        """get_intent() returns None for an action name not in the registry."""
        result = get_intent("nonexistent_action_xyz")
        assert result is None

    def test_returns_correct_value_for_each_action(self) -> None:
        """get_intent() returns the exact value from ACTION_INTENTS for each key."""
        for action_name, expected in ACTION_INTENTS.items():
            actual = get_intent(action_name)
            assert actual == expected, (
                f"get_intent('{action_name}') returned {actual!r}, expected {expected!r}"
            )

    def test_returns_none_for_empty_string(self) -> None:
        """get_intent() returns None for empty string input."""
        assert get_intent("") is None
