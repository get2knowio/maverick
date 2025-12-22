"""Tests for generator registration.

This module tests the register_all_generators function to ensure all generators
referenced in workflow YAML files are properly registered.
"""

from __future__ import annotations

import pytest

from maverick.agents.generators import (
    CommitMessageGenerator,
    PRDescriptionGenerator,
    PRTitleGenerator,
)
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.library.generators import register_all_generators


class TestRegisterAllGenerators:
    """Test suite for register_all_generators function."""

    @pytest.fixture
    def registry(self) -> ComponentRegistry:
        """Create a fresh ComponentRegistry for testing."""
        return ComponentRegistry()

    def test_registers_commit_message_generator(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that commit_message_generator is registered."""
        register_all_generators(registry)

        assert registry.generators.has("commit_message_generator")
        generator_class = registry.generators.get("commit_message_generator")
        assert generator_class is CommitMessageGenerator

    def test_registers_pr_body_generator(self, registry: ComponentRegistry) -> None:
        """Test that pr_body_generator is registered."""
        register_all_generators(registry)

        assert registry.generators.has("pr_body_generator")
        generator_class = registry.generators.get("pr_body_generator")
        assert generator_class is PRDescriptionGenerator

    def test_registers_pr_title_generator(self, registry: ComponentRegistry) -> None:
        """Test that pr_title_generator is registered."""
        register_all_generators(registry)

        assert registry.generators.has("pr_title_generator")
        generator_class = registry.generators.get("pr_title_generator")
        assert generator_class is PRTitleGenerator

    def test_registers_all_expected_generators(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that all expected generators are registered."""
        register_all_generators(registry)

        expected_generators = {
            "commit_message_generator",
            "pr_body_generator",
            "pr_title_generator",
        }

        registered_generators = set(registry.generators.list_names())
        assert expected_generators.issubset(registered_generators)

    def test_registration_is_idempotent(self, registry: ComponentRegistry) -> None:
        """Test that calling register_all_generators multiple times doesn't fail.

        Note: This will raise DuplicateComponentError because the registry
        doesn't allow duplicate registrations. This is expected behavior.
        """
        register_all_generators(registry)

        # Second call should raise DuplicateComponentError
        with pytest.raises(Exception):  # DuplicateComponentError
            register_all_generators(registry)

    def test_registered_generators_can_be_instantiated(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that registered generators can be instantiated."""
        register_all_generators(registry)

        # Get each generator class and verify it can be instantiated
        commit_gen_class = registry.generators.get("commit_message_generator")
        commit_gen = commit_gen_class()
        assert commit_gen is not None

        pr_body_class = registry.generators.get("pr_body_generator")
        pr_body = pr_body_class()
        assert pr_body is not None

        pr_title_class = registry.generators.get("pr_title_generator")
        pr_title = pr_title_class()
        assert pr_title is not None

    def test_registered_generators_have_correct_names(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that registered generators have the expected class names."""
        register_all_generators(registry)

        # Verify class names match expected values
        assert (
            registry.generators.get("commit_message_generator").__name__
            == "CommitMessageGenerator"
        )
        assert (
            registry.generators.get("pr_body_generator").__name__
            == "PRDescriptionGenerator"
        )
        assert (
            registry.generators.get("pr_title_generator").__name__ == "PRTitleGenerator"
        )

    def test_generators_have_correct_instance_attributes(
        self, registry: ComponentRegistry
    ) -> None:
        """Test that instantiated generators have expected attributes."""
        register_all_generators(registry)

        # Commit message generator
        commit_gen = registry.generators.get("commit_message_generator")()
        assert commit_gen.name == "commit-message-generator"
        assert commit_gen.model is not None

        # PR body generator
        pr_body = registry.generators.get("pr_body_generator")()
        assert pr_body.name == "pr-description-generator"
        assert pr_body.model is not None

        # PR title generator
        pr_title = registry.generators.get("pr_title_generator")()
        assert pr_title.name == "pr-title-generator"
        assert pr_title.model is not None
