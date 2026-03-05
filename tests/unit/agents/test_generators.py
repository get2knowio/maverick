"""Unit tests for GeneratorAgent base class.

Tests the generator agent base class functionality including:
- Initialization and configuration
- Tool permissions (should be empty)
- Abstract interface requirements
"""

from __future__ import annotations

import pytest

from maverick.agents.generators.base import GeneratorAgent

# =============================================================================
# Test Implementation of GeneratorAgent
# =============================================================================


class ConcreteGenerator(GeneratorAgent):
    """Concrete implementation of GeneratorAgent for testing."""

    def __init__(self):
        super().__init__(
            name="test-generator",
            system_prompt="You generate test content.",
        )

    def build_prompt(self, context: dict) -> str:
        """Build prompt from context."""
        return f"Generate: {context.get('input', '')}"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def generator() -> ConcreteGenerator:
    """Create a ConcreteGenerator instance for testing."""
    return ConcreteGenerator()


# =============================================================================
# Initialization Tests
# =============================================================================


class TestGeneratorAgentInitialization:
    """Tests for GeneratorAgent initialization."""

    def test_default_initialization(self, generator: ConcreteGenerator) -> None:
        """Test generator initializes with correct defaults."""
        assert generator.name == "test-generator"
        assert "generate test content" in generator.system_prompt.lower()

    def test_allowed_tools_is_empty(self, generator: ConcreteGenerator) -> None:
        """Test generators have no tools by default.

        Generators are text-only and should not have access to any tools.
        All context is provided in prompts.
        """
        assert generator.allowed_tools == []

    def test_allowed_tools_uses_centralized_constants(
        self, generator: ConcreteGenerator
    ) -> None:
        """Test allowed tools uses GENERATOR_TOOLS from maverick.agents.tools.

        T013: Verify that GeneratorAgent uses the centralized GENERATOR_TOOLS
        constant from tools.py (which should be empty). This enforces the
        orchestration pattern where tool permissions are centrally managed.
        """
        from maverick.agents.tools import GENERATOR_TOOLS as CENTRALIZED_TOOLS

        # Generator's allowed_tools should match the centralized constant (empty)
        expected_tools = set(CENTRALIZED_TOOLS)
        actual_tools = set(generator.allowed_tools)

        assert actual_tools == expected_tools, (
            f"GeneratorAgent must use centralized GENERATOR_TOOLS. "
            f"Expected: {expected_tools}, Got: {actual_tools}"
        )

        # Ensure GENERATOR_TOOLS is empty (per US1 contract)
        assert len(CENTRALIZED_TOOLS) == 0, (
            "GENERATOR_TOOLS should be empty - generators don't use tools"
        )

    def test_raises_on_empty_name(self) -> None:
        """Test generator raises ValueError with empty name."""
        with pytest.raises(ValueError, match="name must be non-empty"):

            class BadGenerator(GeneratorAgent):
                def __init__(self):
                    super().__init__(name="", system_prompt="test")

                def build_prompt(self, context: dict) -> str:
                    return "test"

                async def generate(self, context: dict) -> str:
                    return "test"

            BadGenerator()

    def test_raises_on_empty_system_prompt(self) -> None:
        """Test generator raises ValueError with empty system_prompt."""
        with pytest.raises(ValueError, match="system_prompt must be non-empty"):

            class BadGenerator(GeneratorAgent):
                def __init__(self):
                    super().__init__(name="test", system_prompt="")

                def build_prompt(self, context: dict) -> str:
                    return "test"

                async def generate(self, context: dict) -> str:
                    return "test"

            BadGenerator()


# =============================================================================
# Build Prompt Tests
# =============================================================================


class TestQueryMethod:
    """Tests for the build_prompt method (ACP-compatible interface)."""

    def test_build_prompt_returns_string(self, generator: ConcreteGenerator) -> None:
        """Test build_prompt returns a string."""
        result = generator.build_prompt({"input": "hello"})

        assert isinstance(result, str)
        assert "hello" in result

    def test_build_prompt_with_empty_context(
        self, generator: ConcreteGenerator
    ) -> None:
        """Test build_prompt handles empty context gracefully."""
        result = generator.build_prompt({})

        assert isinstance(result, str)


# =============================================================================
# Abstract Method Tests
# =============================================================================


class TestAbstractInterface:
    """Tests for abstract interface requirements."""

    def test_must_implement_build_prompt(self) -> None:
        """Test subclass must implement build_prompt method."""

        class IncompleteGenerator(GeneratorAgent):
            def __init__(self):
                super().__init__(name="incomplete", system_prompt="test")

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteGenerator()
