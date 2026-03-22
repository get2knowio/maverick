"""Tests for agent registration.

This module tests the register_all_agents function to ensure all agents
referenced in workflow YAML files are properly registered.
"""

from __future__ import annotations

import pytest

from maverick.agents import (
    FixerAgent,
    ImplementerAgent,
)
from maverick.library.agents import register_all_agents
from maverick.registry import ComponentRegistry


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

    def test_registers_completeness_reviewer_agent(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that completeness_reviewer agent is registered."""
        register_all_agents(registry)

        assert registry.agents.has("completeness_reviewer")

    def test_registers_correctness_reviewer_agent(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that correctness_reviewer agent is registered."""
        register_all_agents(registry)

        assert registry.agents.has("correctness_reviewer")

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
            "completeness_reviewer",
            "correctness_reviewer",
            "review_fixer",
            "validation_fixer",
            "decomposer",
            "flight_plan_generator",
            "navigator",
            "structuralist",
            "recon",
            "contrarian",
            "scopist",
            "codebase_analyst",
            "criteria_writer",
            "preflight_contrarian",
        }

        registered_agents = set(registry.agents.list_names())
        assert expected_agents.issubset(registered_agents)

    def test_registration_is_idempotent(self, registry: ComponentRegistry) -> None:
        """Test that calling register_all_agents multiple times raises.

        The registry doesn't allow duplicate registrations.
        """
        register_all_agents(registry)

        with pytest.raises(Exception):  # DuplicateComponentError
            register_all_agents(registry)

    def test_registered_agents_can_be_instantiated(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that registered agents can be instantiated."""
        register_all_agents(registry)

        implementer_class = registry.agents.get("implementer")
        implementer = implementer_class()
        assert implementer is not None

        validation_fixer_class = registry.agents.get("validation_fixer")
        validation_fixer = validation_fixer_class()
        assert validation_fixer is not None

    def test_does_not_register_legacy_agents(self, registry: ComponentRegistry) -> None:
        """Test that removed legacy agents are not registered."""
        register_all_agents(registry)

        assert not registry.agents.has("code_reviewer")
        assert not registry.agents.has("issue_fixer")
        assert not registry.agents.has("unified_reviewer")

    def test_registered_agents_have_correct_names(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that registered agents have the expected class names."""
        register_all_agents(registry)

        assert registry.agents.get("implementer").__name__ == "ImplementerAgent"
        assert (
            registry.agents.get("completeness_reviewer").__name__
            == "CompletenessReviewerAgent"
        )
        assert (
            registry.agents.get("correctness_reviewer").__name__
            == "CorrectnessReviewerAgent"
        )
        assert registry.agents.get("validation_fixer").__name__ == "FixerAgent"
