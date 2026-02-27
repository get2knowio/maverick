"""Immutable prompt registry mapping (step_name, provider) to PromptEntry."""

from __future__ import annotations

from types import MappingProxyType

from maverick.prompts.models import (
    GENERIC_PROVIDER,
    OverridePolicy,
    PromptConfigError,
    PromptEntry,
)


class PromptRegistry:
    """Immutable registry of default prompts keyed by (step_name, provider).

    Created once at application startup. Read-only after construction.

    Args:
        entries: Mapping of (step_name, provider) tuples to PromptEntry objects.

    Raises:
        PromptConfigError: If entries is empty.
    """

    __slots__ = ("_entries",)

    def __init__(self, entries: dict[tuple[str, str], PromptEntry]) -> None:
        if not entries:
            raise PromptConfigError("Cannot create PromptRegistry with empty entries")
        self._entries: MappingProxyType[tuple[str, str], PromptEntry] = (
            MappingProxyType(dict(entries))
        )

    def get(self, step_name: str, provider: str = GENERIC_PROVIDER) -> PromptEntry:
        """Look up with fallback to generic provider.

        Resolution: (step_name, provider) -> (step_name, GENERIC_PROVIDER) -> error
        """
        key = (step_name, provider)
        if key in self._entries:
            return self._entries[key]
        generic_key = (step_name, GENERIC_PROVIDER)
        if generic_key in self._entries:
            return self._entries[generic_key]
        raise PromptConfigError(f"No default prompt registered for step '{step_name}'")

    def get_policy(self, step_name: str) -> OverridePolicy:
        """Shortcut to get the override policy for a step (generic provider)."""
        return self.get(step_name, GENERIC_PROVIDER).policy

    def has(self, step_name: str, provider: str = GENERIC_PROVIDER) -> bool:
        """Check if a step+provider combination is registered."""
        return (step_name, provider) in self._entries

    def step_names(self) -> frozenset[str]:
        """Return all registered step names (deduplicated across providers)."""
        return frozenset(name for name, _ in self._entries)

    def validate_override(self, step_name: str, override: object) -> None:
        """Validate a user override against the step's policy.

        The override object must have prompt_file attribute.
        Raises PromptConfigError if prompt_file is set on an augment_only step.
        """
        entry = self.get(step_name, GENERIC_PROVIDER)
        prompt_file = getattr(override, "prompt_file", None)
        if prompt_file is not None and entry.policy == OverridePolicy.AUGMENT_ONLY:
            raise PromptConfigError(
                f"Step '{step_name}' does not allow full prompt replacement "
                f"(policy: augment_only)"
            )
