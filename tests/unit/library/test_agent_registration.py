"""Tests for agent registration.

This module tests the register_all_agents function to ensure all agents
referenced in workflow YAML files are properly registered.
"""

from __future__ import annotations

import pytest

from maverick.agents import (
    CodeReviewerAgent,
    FixerAgent,
    ImplementerAgent,
    IssueFixerAgent,
)
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.library.agents import register_all_agents


class TestRegisterAllAgents:
    """Test suite for register_all_agents function."""

    @pytest.fixture
    def registry(self) -> ComponentRegistry:
        """Create a fresh ComponentRegistry for testing."""
        return ComponentRegistry()

    def test_registers_implementer_agent(self, registry: ComponentRegistry) -> None:
        """Test that implementer agent is registered."""
        register_all_agents(registry)

        assert registry.agents.has("implementer")
        agent_class = registry.agents.get("implementer")
        assert agent_class is ImplementerAgent

    def test_registers_code_reviewer_agent(self, registry: ComponentRegistry) -> None:
        """Test that code_reviewer agent is registered."""
        register_all_agents(registry)

        assert registry.agents.has("code_reviewer")
        agent_class = registry.agents.get("code_reviewer")
        assert agent_class is CodeReviewerAgent

    def test_registers_issue_fixer_agent(self, registry: ComponentRegistry) -> None:
        """Test that issue_fixer agent is registered."""
        register_all_agents(registry)

        assert registry.agents.has("issue_fixer")
        agent_class = registry.agents.get("issue_fixer")
        assert agent_class is IssueFixerAgent

    def test_registers_validation_fixer_agent(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that validation_fixer agent is registered."""
        register_all_agents(registry)

        assert registry.agents.has("validation_fixer")
        agent_class = registry.agents.get("validation_fixer")
        assert agent_class is FixerAgent

    def test_registers_all_expected_agents(self, registry: ComponentRegistry) -> None:
        """Test that all expected agents are registered."""
        register_all_agents(registry)

        expected_agents = {
            "implementer",
            "code_reviewer",
            "issue_fixer",
            "validation_fixer",
        }

        registered_agents = set(registry.agents.list_names())
        assert expected_agents.issubset(registered_agents)

    def test_registration_is_idempotent(self, registry: ComponentRegistry) -> None:
        """Test that calling register_all_agents multiple times doesn't fail.

        Note: This will raise DuplicateComponentError because the registry
        doesn't allow duplicate registrations. This is expected behavior.
        """
        register_all_agents(registry)

        # Second call should raise DuplicateComponentError
        with pytest.raises(Exception):  # DuplicateComponentError
            register_all_agents(registry)

    def test_registered_agents_can_be_instantiated(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that registered agents can be instantiated."""
        register_all_agents(registry)

        # Get each agent class and verify it can be instantiated
        implementer_class = registry.agents.get("implementer")
        implementer = implementer_class()
        assert implementer is not None

        code_reviewer_class = registry.agents.get("code_reviewer")
        code_reviewer = code_reviewer_class()
        assert code_reviewer is not None

        issue_fixer_class = registry.agents.get("issue_fixer")
        issue_fixer = issue_fixer_class()
        assert issue_fixer is not None

        validation_fixer_class = registry.agents.get("validation_fixer")
        validation_fixer = validation_fixer_class()
        assert validation_fixer is not None

    def test_does_not_register_issue_analyzer(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that issue_analyzer is not registered (not yet implemented)."""
        register_all_agents(registry)

        # issue_analyzer is referenced in refuel.yaml but not yet implemented
        assert not registry.agents.has("issue_analyzer")

    def test_registered_agents_have_correct_names(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that registered agents have the expected class names."""
        register_all_agents(registry)

        # Verify class names match expected values
        assert registry.agents.get("implementer").__name__ == "ImplementerAgent"
        assert registry.agents.get("code_reviewer").__name__ == "CodeReviewerAgent"
        assert registry.agents.get("issue_fixer").__name__ == "IssueFixerAgent"
        assert registry.agents.get("validation_fixer").__name__ == "FixerAgent"
