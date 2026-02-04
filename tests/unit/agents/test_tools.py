"""Unit tests for agent tool permission constants."""

from __future__ import annotations

import pytest

from maverick.agents.base import BUILTIN_TOOLS
from maverick.agents.tools import (
    FIXER_TOOLS,
    GENERATOR_TOOLS,
    IMPLEMENTER_TOOLS,
    ISSUE_FIXER_TOOLS,
    REVIEWER_TOOLS,
)

# =============================================================================
# Type and Immutability Tests
# =============================================================================


class TestToolSetTypes:
    """Tests for tool set type correctness and immutability."""

    def test_reviewer_tools_is_frozenset(self) -> None:
        """Test REVIEWER_TOOLS is a frozenset instance."""
        assert isinstance(REVIEWER_TOOLS, frozenset)

    def test_implementer_tools_is_frozenset(self) -> None:
        """Test IMPLEMENTER_TOOLS is a frozenset instance."""
        assert isinstance(IMPLEMENTER_TOOLS, frozenset)

    def test_fixer_tools_is_frozenset(self) -> None:
        """Test FIXER_TOOLS is a frozenset instance."""
        assert isinstance(FIXER_TOOLS, frozenset)

    def test_issue_fixer_tools_is_frozenset(self) -> None:
        """Test ISSUE_FIXER_TOOLS is a frozenset instance."""
        assert isinstance(ISSUE_FIXER_TOOLS, frozenset)

    def test_generator_tools_is_frozenset(self) -> None:
        """Test GENERATOR_TOOLS is a frozenset instance."""
        assert isinstance(GENERATOR_TOOLS, frozenset)

    def test_frozensets_are_immutable(self) -> None:
        """Test that frozensets cannot be modified at runtime."""
        # Attempting to modify any of these should raise AttributeError
        with pytest.raises(AttributeError):
            REVIEWER_TOOLS.add("Bash")  # type: ignore[attr-defined]

        with pytest.raises(AttributeError):
            IMPLEMENTER_TOOLS.remove("Read")  # type: ignore[attr-defined]

        with pytest.raises(AttributeError):
            FIXER_TOOLS.clear()  # type: ignore[attr-defined]


# =============================================================================
# Tool Set Validity Tests
# =============================================================================


class TestToolSetValidity:
    """Tests that all tool sets contain only valid built-in tools."""

    def test_reviewer_tools_are_valid(self) -> None:
        """Test all REVIEWER_TOOLS exist in BUILTIN_TOOLS."""
        assert REVIEWER_TOOLS.issubset(BUILTIN_TOOLS), (
            f"Invalid tools in REVIEWER_TOOLS: {REVIEWER_TOOLS - BUILTIN_TOOLS}"
        )

    def test_implementer_tools_are_valid(self) -> None:
        """Test all IMPLEMENTER_TOOLS exist in BUILTIN_TOOLS."""
        assert IMPLEMENTER_TOOLS.issubset(BUILTIN_TOOLS), (
            f"Invalid tools in IMPLEMENTER_TOOLS: {IMPLEMENTER_TOOLS - BUILTIN_TOOLS}"
        )

    def test_fixer_tools_are_valid(self) -> None:
        """Test all FIXER_TOOLS exist in BUILTIN_TOOLS."""
        assert FIXER_TOOLS.issubset(BUILTIN_TOOLS), (
            f"Invalid tools in FIXER_TOOLS: {FIXER_TOOLS - BUILTIN_TOOLS}"
        )

    def test_issue_fixer_tools_are_valid(self) -> None:
        """Test all ISSUE_FIXER_TOOLS exist in BUILTIN_TOOLS."""
        assert ISSUE_FIXER_TOOLS.issubset(BUILTIN_TOOLS), (
            f"Invalid tools in ISSUE_FIXER_TOOLS: {ISSUE_FIXER_TOOLS - BUILTIN_TOOLS}"
        )

    def test_generator_tools_are_valid(self) -> None:
        """Test GENERATOR_TOOLS (empty set) is valid."""
        # Empty set is always a subset
        assert GENERATOR_TOOLS.issubset(BUILTIN_TOOLS)


# =============================================================================
# Tool Set Composition Tests
# =============================================================================


class TestReviewerTools:
    """Tests for REVIEWER_TOOLS composition and constraints."""

    def test_reviewer_tools_exact_composition(self) -> None:
        """Test REVIEWER_TOOLS contains exactly the expected tools."""
        expected = {"Read", "Glob", "Grep"}
        assert expected == REVIEWER_TOOLS

    def test_reviewer_tools_is_read_only(self) -> None:
        """Test REVIEWER_TOOLS contains no write tools."""
        write_tools = {"Write", "Edit", "NotebookEdit"}
        assert not REVIEWER_TOOLS.intersection(write_tools), (
            f"REVIEWER_TOOLS should be read-only but contains: "
            f"{REVIEWER_TOOLS.intersection(write_tools)}"
        )

    def test_reviewer_tools_has_no_bash(self) -> None:
        """Test REVIEWER_TOOLS does not include Bash."""
        assert "Bash" not in REVIEWER_TOOLS

    def test_reviewer_tools_has_search_capabilities(self) -> None:
        """Test REVIEWER_TOOLS includes search tools."""
        assert "Glob" in REVIEWER_TOOLS
        assert "Grep" in REVIEWER_TOOLS


class TestImplementerTools:
    """Tests for IMPLEMENTER_TOOLS composition and constraints."""

    def test_implementer_tools_exact_composition(self) -> None:
        """Test IMPLEMENTER_TOOLS contains exactly the expected tools."""
        expected = {"Read", "Write", "Edit", "Glob", "Grep", "Task"}
        assert expected == IMPLEMENTER_TOOLS

    def test_implementer_tools_has_no_bash(self) -> None:
        """Test IMPLEMENTER_TOOLS does not include Bash."""
        assert "Bash" not in IMPLEMENTER_TOOLS

    def test_implementer_tools_has_read_capability(self) -> None:
        """Test IMPLEMENTER_TOOLS includes Read."""
        assert "Read" in IMPLEMENTER_TOOLS

    def test_implementer_tools_has_write_capability(self) -> None:
        """Test IMPLEMENTER_TOOLS includes Write and Edit."""
        assert "Write" in IMPLEMENTER_TOOLS
        assert "Edit" in IMPLEMENTER_TOOLS

    def test_implementer_tools_has_search_capability(self) -> None:
        """Test IMPLEMENTER_TOOLS includes search tools."""
        assert "Glob" in IMPLEMENTER_TOOLS
        assert "Grep" in IMPLEMENTER_TOOLS

    def test_implementer_tools_is_superset_of_reviewer_tools(self) -> None:
        """Test IMPLEMENTER_TOOLS includes all REVIEWER_TOOLS."""
        assert IMPLEMENTER_TOOLS.issuperset(REVIEWER_TOOLS)


class TestFixerTools:
    """Tests for FIXER_TOOLS composition and constraints."""

    def test_fixer_tools_exact_composition(self) -> None:
        """Test FIXER_TOOLS contains exactly the expected tools."""
        expected = {"Read", "Write", "Edit"}
        assert expected == FIXER_TOOLS

    def test_fixer_tools_is_minimal(self) -> None:
        """Test FIXER_TOOLS is the minimal set for code modification."""
        # Should have exactly 3 tools: Read, Write, Edit
        assert len(FIXER_TOOLS) == 3

    def test_fixer_tools_has_no_search(self) -> None:
        """Test FIXER_TOOLS does not include search tools."""
        search_tools = {"Glob", "Grep"}
        assert not FIXER_TOOLS.intersection(search_tools), (
            f"FIXER_TOOLS should not have search but contains: "
            f"{FIXER_TOOLS.intersection(search_tools)}"
        )

    def test_fixer_tools_has_no_bash(self) -> None:
        """Test FIXER_TOOLS does not include Bash."""
        assert "Bash" not in FIXER_TOOLS

    def test_fixer_tools_is_subset_of_implementer_tools(self) -> None:
        """Test FIXER_TOOLS is a subset of IMPLEMENTER_TOOLS."""
        assert FIXER_TOOLS.issubset(IMPLEMENTER_TOOLS)


class TestIssueFixerTools:
    """Tests for ISSUE_FIXER_TOOLS composition and constraints."""

    def test_issue_fixer_tools_exact_composition(self) -> None:
        """Test ISSUE_FIXER_TOOLS contains exactly the expected tools."""
        expected = {"Read", "Write", "Edit", "Glob", "Grep"}
        assert expected == ISSUE_FIXER_TOOLS

    def test_issue_fixer_tools_identical_to_implementer_tools(self) -> None:
        """Test ISSUE_FIXER_TOOLS is a subset of IMPLEMENTER_TOOLS."""
        assert ISSUE_FIXER_TOOLS.issubset(IMPLEMENTER_TOOLS)

    def test_issue_fixer_tools_has_no_bash(self) -> None:
        """Test ISSUE_FIXER_TOOLS does not include Bash."""
        assert "Bash" not in ISSUE_FIXER_TOOLS

    def test_issue_fixer_tools_has_search_capability(self) -> None:
        """Test ISSUE_FIXER_TOOLS includes search tools for finding issues."""
        assert "Glob" in ISSUE_FIXER_TOOLS
        assert "Grep" in ISSUE_FIXER_TOOLS


class TestGeneratorTools:
    """Tests for GENERATOR_TOOLS composition and constraints."""

    def test_generator_tools_is_empty(self) -> None:
        """Test GENERATOR_TOOLS is an empty frozenset."""
        assert frozenset() == GENERATOR_TOOLS
        assert len(GENERATOR_TOOLS) == 0

    def test_generator_tools_has_no_file_access(self) -> None:
        """Test GENERATOR_TOOLS includes no file access tools."""
        file_tools = {"Read", "Write", "Edit", "NotebookEdit"}
        assert not GENERATOR_TOOLS.intersection(file_tools)

    def test_generator_tools_has_no_search(self) -> None:
        """Test GENERATOR_TOOLS includes no search tools."""
        search_tools = {"Glob", "Grep"}
        assert not GENERATOR_TOOLS.intersection(search_tools)

    def test_generator_tools_has_no_bash(self) -> None:
        """Test GENERATOR_TOOLS does not include Bash."""
        assert "Bash" not in GENERATOR_TOOLS


# =============================================================================
# Cross-Set Relationship Tests
# =============================================================================


class TestToolSetRelationships:
    """Tests for relationships between different tool sets."""

    def test_all_non_empty_sets_contain_read(self) -> None:
        """Test all non-empty tool sets include Read capability."""
        assert "Read" in REVIEWER_TOOLS
        assert "Read" in IMPLEMENTER_TOOLS
        assert "Read" in FIXER_TOOLS
        assert "Read" in ISSUE_FIXER_TOOLS
        # GENERATOR_TOOLS is empty, so it doesn't have Read

    def test_no_tool_set_contains_bash(self) -> None:
        """Test no tool set includes Bash (removed per FR-006)."""
        assert "Bash" not in REVIEWER_TOOLS
        assert "Bash" not in IMPLEMENTER_TOOLS
        assert "Bash" not in FIXER_TOOLS
        assert "Bash" not in ISSUE_FIXER_TOOLS
        assert "Bash" not in GENERATOR_TOOLS

    def test_only_write_tools_contain_edit(self) -> None:
        """Test only tool sets with write permission include Edit."""
        # Sets with Edit
        assert "Edit" in IMPLEMENTER_TOOLS
        assert "Edit" in FIXER_TOOLS
        assert "Edit" in ISSUE_FIXER_TOOLS

        # Sets without Edit
        assert "Edit" not in REVIEWER_TOOLS
        assert "Edit" not in GENERATOR_TOOLS

    def test_reviewer_tools_is_smallest_non_empty_read_set(self) -> None:
        """Test REVIEWER_TOOLS is the smallest non-empty read-only set."""
        non_empty_sets = [
            REVIEWER_TOOLS,
            IMPLEMENTER_TOOLS,
            FIXER_TOOLS,
            ISSUE_FIXER_TOOLS,
        ]

        # Filter to read-only (no Write, no Edit)
        read_only_sets = [
            s for s in non_empty_sets if "Write" not in s and "Edit" not in s
        ]

        # REVIEWER_TOOLS should be the only read-only set
        assert read_only_sets == [REVIEWER_TOOLS]

    def test_fixer_tools_is_smallest_write_set(self) -> None:
        """Test FIXER_TOOLS is the smallest tool set with write capability."""
        write_sets = [
            IMPLEMENTER_TOOLS,
            FIXER_TOOLS,
            ISSUE_FIXER_TOOLS,
        ]

        # FIXER_TOOLS should be the smallest
        assert all(len(FIXER_TOOLS) <= len(s) for s in write_sets)


# =============================================================================
# Tool Set Union/Intersection Tests
# =============================================================================


class TestToolSetOperations:
    """Tests for set operations on tool sets."""

    def test_reviewer_plus_fixer_is_subset_of_implementer(self) -> None:
        """Test REVIEWER_TOOLS union FIXER_TOOLS is subset of IMPLEMENTER."""
        # REVIEWER has Read+Search, FIXER has Read+Write+Edit
        # Union gives Read+Write+Edit+Search, subset of IMPLEMENTER
        # (IMPLEMENTER also has Task for subagent support)
        union = REVIEWER_TOOLS | FIXER_TOOLS
        assert union.issubset(IMPLEMENTER_TOOLS)

    def test_common_tools_across_all_non_empty_sets(self) -> None:
        """Test the intersection of all non-empty tool sets."""
        # Only Read should be common to all non-empty sets
        common = REVIEWER_TOOLS & IMPLEMENTER_TOOLS & FIXER_TOOLS & ISSUE_FIXER_TOOLS
        assert common == {"Read"}

    def test_issue_fixer_is_subset_of_implementer(self) -> None:
        """Test ISSUE_FIXER_TOOLS is a subset of IMPLEMENTER_TOOLS.

        The implementer has Task for subagent-based parallelization;
        the issue fixer does not need it.
        """
        assert ISSUE_FIXER_TOOLS.issubset(IMPLEMENTER_TOOLS)
        # The extra tool is Task
        assert {"Task"} == IMPLEMENTER_TOOLS - ISSUE_FIXER_TOOLS


# =============================================================================
# Module Import Tests
# =============================================================================


class TestModuleImports:
    """Tests for module-level imports and __all__ exports."""

    def test_all_tools_importable_from_agents_module(self) -> None:
        """Test all tool constants can be imported from maverick.agents."""
        # This is an integration test - if imports fail, test will error
        # Verify they're the same objects (not copies)
        from maverick.agents import (
            FIXER_TOOLS,
            GENERATOR_TOOLS,
            IMPLEMENTER_TOOLS,
            ISSUE_FIXER_TOOLS,
            REVIEWER_TOOLS,
            tools,
        )

        assert REVIEWER_TOOLS is tools.REVIEWER_TOOLS
        assert IMPLEMENTER_TOOLS is tools.IMPLEMENTER_TOOLS
        assert FIXER_TOOLS is tools.FIXER_TOOLS
        assert ISSUE_FIXER_TOOLS is tools.ISSUE_FIXER_TOOLS
        assert GENERATOR_TOOLS is tools.GENERATOR_TOOLS

    def test_tools_module_has_correct_all_export(self) -> None:
        """Test tools module exports correct __all__ list."""
        from maverick.agents import tools

        expected_all = [
            "REVIEWER_TOOLS",
            "IMPLEMENTER_TOOLS",
            "FIXER_TOOLS",
            "ISSUE_FIXER_TOOLS",
            "GENERATOR_TOOLS",
        ]

        assert hasattr(tools, "__all__")
        assert sorted(tools.__all__) == sorted(expected_all)
