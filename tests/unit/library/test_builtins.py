"""Tests for built-in workflow library.

This module tests the BuiltinLibrary class and related data structures,
including workflow/fragment info objects, constants, and library operations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.dsl.serialization.schema import WorkflowFile
from maverick.library.builtins import (
    BUILTIN_FRAGMENTS,
    BUILTIN_WORKFLOWS,
    COMMIT_AND_PUSH_FRAGMENT_INFO,
    CREATE_PR_WITH_SUMMARY_FRAGMENT_INFO,
    FLY_BEADS_WORKFLOW_INFO,
    REFUEL_SPECKIT_WORKFLOW_INFO,
    VALIDATE_AND_FIX_FRAGMENT_INFO,
    BuiltinFragmentInfo,
    BuiltinLibrary,
    BuiltinWorkflowInfo,
    DefaultBuiltinLibrary,
    create_builtin_library,
)

# =============================================================================
# BuiltinWorkflowInfo Tests
# =============================================================================


class TestBuiltinWorkflowInfo:
    """Test suite for BuiltinWorkflowInfo dataclass."""

    def test_dataclass_is_frozen(self) -> None:
        """Test that BuiltinWorkflowInfo is immutable."""
        info = BuiltinWorkflowInfo(
            name="test",
            description="Test workflow",
            inputs=(("param", "string", True, "Test param"),),
            step_summary="step1 → step2",
        )

        with pytest.raises(AttributeError):
            info.name = "modified"  # type: ignore[misc]

    def test_dataclass_uses_slots(self) -> None:
        """Test that BuiltinWorkflowInfo uses __slots__ for memory efficiency."""
        info = BuiltinWorkflowInfo(
            name="test",
            description="Test workflow",
            inputs=(),
            step_summary="step1",
        )

        # Dataclass with slots=True doesn't have __dict__
        assert not hasattr(info, "__dict__")

    def test_all_workflow_info_constants_exist(self) -> None:
        """Test that all workflow info constants are defined."""
        assert FLY_BEADS_WORKFLOW_INFO is not None
        assert REFUEL_SPECKIT_WORKFLOW_INFO is not None

    def test_fly_beads_workflow_info_fields(self) -> None:
        """Test that FLY_BEADS_WORKFLOW_INFO has correct fields."""
        assert FLY_BEADS_WORKFLOW_INFO.name == "fly-beads"
        assert "bead-driven" in FLY_BEADS_WORKFLOW_INFO.description.lower()
        assert isinstance(FLY_BEADS_WORKFLOW_INFO.inputs, tuple)
        assert len(FLY_BEADS_WORKFLOW_INFO.inputs) >= 2

    def test_refuel_speckit_workflow_info_fields(self) -> None:
        """Test that REFUEL_SPECKIT_WORKFLOW_INFO has correct fields."""
        assert REFUEL_SPECKIT_WORKFLOW_INFO.name == "refuel-speckit"
        assert isinstance(REFUEL_SPECKIT_WORKFLOW_INFO.inputs, tuple)


# =============================================================================
# BuiltinFragmentInfo Tests
# =============================================================================


class TestBuiltinFragmentInfo:
    """Test suite for BuiltinFragmentInfo dataclass."""

    def test_dataclass_is_frozen(self) -> None:
        """Test that BuiltinFragmentInfo is immutable."""
        info = BuiltinFragmentInfo(
            name="test",
            description="Test fragment",
            inputs=(("param", "string", True, "Test param"),),
            used_by=("workflow1",),
        )

        with pytest.raises(AttributeError):
            info.name = "modified"  # type: ignore[misc]

    def test_dataclass_uses_slots(self) -> None:
        """Test that BuiltinFragmentInfo uses __slots__ for memory efficiency."""
        info = BuiltinFragmentInfo(
            name="test",
            description="Test fragment",
            inputs=(),
            used_by=(),
        )

        # Dataclass with slots=True doesn't have __dict__
        assert not hasattr(info, "__dict__")

    def test_all_fragment_info_constants_exist(self) -> None:
        """Test that all fragment info constants are defined."""
        assert VALIDATE_AND_FIX_FRAGMENT_INFO is not None
        assert COMMIT_AND_PUSH_FRAGMENT_INFO is not None
        assert CREATE_PR_WITH_SUMMARY_FRAGMENT_INFO is not None

    def test_fragment_info_fields_are_correct(self) -> None:
        """Test that VALIDATE_AND_FIX_FRAGMENT_INFO has correct fields."""
        assert VALIDATE_AND_FIX_FRAGMENT_INFO.name == "validate-and-fix"
        assert (
            VALIDATE_AND_FIX_FRAGMENT_INFO.description == "Validation-with-retry loop"
        )
        assert isinstance(VALIDATE_AND_FIX_FRAGMENT_INFO.inputs, tuple)
        assert isinstance(VALIDATE_AND_FIX_FRAGMENT_INFO.used_by, tuple)

    def test_fragment_info_used_by_structure(self) -> None:
        """Test that fragment info used_by has correct structure."""
        assert isinstance(COMMIT_AND_PUSH_FRAGMENT_INFO.used_by, tuple)
        assert all(isinstance(wf, str) for wf in COMMIT_AND_PUSH_FRAGMENT_INFO.used_by)


# =============================================================================
# Constants Tests
# =============================================================================


class TestBuiltinConstants:
    """Test suite for BUILTIN_WORKFLOWS and BUILTIN_FRAGMENTS constants."""

    def test_builtin_workflows_is_frozenset(self) -> None:
        """Test that BUILTIN_WORKFLOWS is a frozenset."""
        assert isinstance(BUILTIN_WORKFLOWS, frozenset)

    def test_builtin_workflows_contains_expected_workflows(self) -> None:
        """Test that BUILTIN_WORKFLOWS contains all expected workflow names."""
        expected = {
            "fly-beads",
            "refuel-speckit",
        }
        assert expected == BUILTIN_WORKFLOWS

    def test_builtin_workflows_is_immutable(self) -> None:
        """Test that BUILTIN_WORKFLOWS cannot be modified."""
        with pytest.raises(AttributeError):
            BUILTIN_WORKFLOWS.add("new_workflow")  # type: ignore[attr-defined]

    def test_builtin_fragments_is_frozenset(self) -> None:
        """Test that BUILTIN_FRAGMENTS is a frozenset."""
        assert isinstance(BUILTIN_FRAGMENTS, frozenset)

    def test_builtin_fragments_contains_expected_fragments(self) -> None:
        """Test that BUILTIN_FRAGMENTS contains all expected fragment names."""
        expected = {"validate-and-fix", "commit-and-push", "create-pr-with-summary"}
        assert expected == BUILTIN_FRAGMENTS

    def test_builtin_fragments_is_immutable(self) -> None:
        """Test that BUILTIN_FRAGMENTS cannot be modified."""
        with pytest.raises(AttributeError):
            BUILTIN_FRAGMENTS.add("new_fragment")  # type: ignore[attr-defined]

    def test_frozenset_membership_checks(self) -> None:
        """Test that membership checks work correctly on frozensets."""
        assert "fly-beads" in BUILTIN_WORKFLOWS
        assert "unknown" not in BUILTIN_WORKFLOWS
        assert "validate-and-fix" in BUILTIN_FRAGMENTS
        assert "unknown" not in BUILTIN_FRAGMENTS


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateBuiltinLibrary:
    """Test suite for create_builtin_library() factory function."""

    def test_returns_builtin_library_instance(self) -> None:
        """Test that factory returns a BuiltinLibrary instance."""
        library = create_builtin_library()
        assert isinstance(library, BuiltinLibrary)

    def test_returns_default_implementation(self) -> None:
        """Test that factory returns DefaultBuiltinLibrary by default."""
        library = create_builtin_library()
        assert isinstance(library, DefaultBuiltinLibrary)

    def test_creates_new_instance_each_time(self) -> None:
        """Test that factory creates a new instance on each call."""
        library1 = create_builtin_library()
        library2 = create_builtin_library()
        assert library1 is not library2


# =============================================================================
# BuiltinLibrary.list_workflows() Tests
# =============================================================================


class TestListWorkflows:
    """Test suite for BuiltinLibrary.list_workflows()."""

    @pytest.fixture
    def library(self) -> BuiltinLibrary:
        """Create a BuiltinLibrary instance for testing."""
        return create_builtin_library()

    def test_returns_list(self, library: BuiltinLibrary) -> None:
        """Test that list_workflows returns a list."""
        workflows = library.list_workflows()
        assert isinstance(workflows, list)

    def test_returns_builtin_workflow_info_objects(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that list_workflows returns BuiltinWorkflowInfo objects."""
        workflows = library.list_workflows()
        assert all(isinstance(wf, BuiltinWorkflowInfo) for wf in workflows)

    def test_returns_two_workflows(self, library: BuiltinLibrary) -> None:
        """Test that list_workflows returns exactly 2 workflows."""
        workflows = library.list_workflows()
        assert len(workflows) == 2

    def test_all_expected_workflows_present(self, library: BuiltinLibrary) -> None:
        """Test that all expected workflows are in the list."""
        workflows = library.list_workflows()
        workflow_names = {wf.name for wf in workflows}
        expected = {
            "fly-beads",
            "refuel-speckit",
        }
        assert workflow_names == expected

    def test_workflow_info_objects_match_constants(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that returned workflow info objects match constants."""
        workflows = library.list_workflows()
        workflow_dict = {wf.name: wf for wf in workflows}

        assert workflow_dict["fly-beads"] == FLY_BEADS_WORKFLOW_INFO
        assert workflow_dict["refuel-speckit"] == REFUEL_SPECKIT_WORKFLOW_INFO


# =============================================================================
# BuiltinLibrary.list_fragments() Tests
# =============================================================================


class TestListFragments:
    """Test suite for BuiltinLibrary.list_fragments()."""

    @pytest.fixture
    def library(self) -> BuiltinLibrary:
        """Create a BuiltinLibrary instance for testing."""
        return create_builtin_library()

    def test_returns_list(self, library: BuiltinLibrary) -> None:
        """Test that list_fragments returns a list."""
        fragments = library.list_fragments()
        assert isinstance(fragments, list)

    def test_returns_builtin_fragment_info_objects(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that list_fragments returns BuiltinFragmentInfo objects."""
        fragments = library.list_fragments()
        assert all(isinstance(frag, BuiltinFragmentInfo) for frag in fragments)

    def test_returns_three_fragments(self, library: BuiltinLibrary) -> None:
        """Test that list_fragments returns exactly 3 fragments."""
        fragments = library.list_fragments()
        assert len(fragments) == 3

    def test_all_expected_fragments_present(self, library: BuiltinLibrary) -> None:
        """Test that all expected fragments are in the list."""
        fragments = library.list_fragments()
        fragment_names = {frag.name for frag in fragments}
        expected = {"validate-and-fix", "commit-and-push", "create-pr-with-summary"}
        assert fragment_names == expected

    def test_fragment_info_objects_match_constants(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that returned fragment info objects match constants."""
        fragments = library.list_fragments()
        fragment_dict = {frag.name: frag for frag in fragments}

        assert fragment_dict["validate-and-fix"] == VALIDATE_AND_FIX_FRAGMENT_INFO
        assert fragment_dict["commit-and-push"] == COMMIT_AND_PUSH_FRAGMENT_INFO
        assert (
            fragment_dict["create-pr-with-summary"]
            == CREATE_PR_WITH_SUMMARY_FRAGMENT_INFO
        )


# =============================================================================
# BuiltinLibrary.has_workflow() Tests
# =============================================================================


class TestHasWorkflow:
    """Test suite for BuiltinLibrary.has_workflow()."""

    @pytest.fixture
    def library(self) -> BuiltinLibrary:
        """Create a BuiltinLibrary instance for testing."""
        return create_builtin_library()

    def test_returns_true_for_valid_workflow_names(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that has_workflow returns True for all valid workflow names."""
        assert library.has_workflow("fly-beads") is True
        assert library.has_workflow("refuel-speckit") is True

    def test_returns_false_for_invalid_workflow_names(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that has_workflow returns False for invalid workflow names."""
        assert library.has_workflow("unknown") is False
        assert library.has_workflow("feature") is False
        assert library.has_workflow("") is False

    def test_returns_false_for_fragment_names(self, library: BuiltinLibrary) -> None:
        """Test that has_workflow returns False for fragment names."""
        assert library.has_workflow("validate-and-fix") is False
        assert library.has_workflow("commit-and-push") is False


# =============================================================================
# BuiltinLibrary.has_fragment() Tests
# =============================================================================


class TestHasFragment:
    """Test suite for BuiltinLibrary.has_fragment()."""

    @pytest.fixture
    def library(self) -> BuiltinLibrary:
        """Create a BuiltinLibrary instance for testing."""
        return create_builtin_library()

    def test_returns_true_for_valid_fragment_names(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that has_fragment returns True for all valid fragment names."""
        assert library.has_fragment("validate-and-fix") is True
        assert library.has_fragment("commit-and-push") is True
        assert library.has_fragment("create-pr-with-summary") is True

    def test_returns_false_for_invalid_fragment_names(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that has_fragment returns False for invalid fragment names."""
        assert library.has_fragment("unknown") is False
        assert library.has_fragment("not_a_fragment") is False
        assert library.has_fragment("") is False

    def test_returns_false_for_workflow_names(self, library: BuiltinLibrary) -> None:
        """Test that has_fragment returns False for workflow names."""
        assert library.has_fragment("fly-beads") is False
        assert library.has_fragment("refuel-speckit") is False


# =============================================================================
# BuiltinLibrary.get_workflow_path() Tests
# =============================================================================


class TestGetWorkflowPath:
    """Test suite for BuiltinLibrary.get_workflow_path()."""

    @pytest.fixture
    def library(self) -> BuiltinLibrary:
        """Create a BuiltinLibrary instance for testing."""
        return create_builtin_library()

    def test_returns_path_object_for_valid_workflow(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that get_workflow_path returns a Path object."""
        path = library.get_workflow_path("fly-beads")
        assert isinstance(path, Path)

    def test_path_points_to_yaml_file(self, library: BuiltinLibrary) -> None:
        """Test that returned path points to a .yaml file."""
        path = library.get_workflow_path("fly-beads")
        assert path.suffix == ".yaml"
        assert path.name == "fly-beads.yaml"

    def test_all_workflow_paths_can_be_retrieved(self, library: BuiltinLibrary) -> None:
        """Test that paths can be retrieved for all workflows."""
        for workflow_name in BUILTIN_WORKFLOWS:
            path = library.get_workflow_path(workflow_name)
            assert isinstance(path, Path)
            assert path.suffix == ".yaml"

    def test_raises_key_error_for_invalid_workflow(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that get_workflow_path raises KeyError for invalid names."""
        with pytest.raises(KeyError, match="Unknown built-in workflow: unknown"):
            library.get_workflow_path("unknown")

    def test_raises_key_error_for_fragment_name(self, library: BuiltinLibrary) -> None:
        """Test that get_workflow_path raises KeyError for fragment names."""
        with pytest.raises(KeyError, match="Unknown built-in workflow"):
            library.get_workflow_path("validate-and-fix")


# =============================================================================
# BuiltinLibrary.get_fragment_path() Tests
# =============================================================================


class TestGetFragmentPath:
    """Test suite for BuiltinLibrary.get_fragment_path()."""

    @pytest.fixture
    def library(self) -> BuiltinLibrary:
        """Create a BuiltinLibrary instance for testing."""
        return create_builtin_library()

    def test_returns_path_object_for_valid_fragment(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that get_fragment_path returns a Path object."""
        path = library.get_fragment_path("validate-and-fix")
        assert isinstance(path, Path)

    def test_path_points_to_yaml_file(self, library: BuiltinLibrary) -> None:
        """Test that returned path points to a .yaml file."""
        path = library.get_fragment_path("validate-and-fix")
        assert path.suffix == ".yaml"
        assert path.name == "validate_and_fix.yaml"

    def test_all_fragment_paths_can_be_retrieved(self, library: BuiltinLibrary) -> None:
        """Test that paths can be retrieved for all fragments."""
        for fragment_name in BUILTIN_FRAGMENTS:
            path = library.get_fragment_path(fragment_name)
            assert isinstance(path, Path)
            assert path.suffix == ".yaml"

    def test_raises_key_error_for_invalid_fragment(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that get_fragment_path raises KeyError for invalid names."""
        with pytest.raises(KeyError, match="Unknown built-in fragment: unknown"):
            library.get_fragment_path("unknown")

    def test_raises_key_error_for_workflow_name(self, library: BuiltinLibrary) -> None:
        """Test that get_fragment_path raises KeyError for workflow names."""
        with pytest.raises(KeyError, match="Unknown built-in fragment"):
            library.get_fragment_path("fly-beads")


# =============================================================================
# BuiltinLibrary.get_workflow() Tests
# =============================================================================


class TestGetWorkflow:
    """Test suite for BuiltinLibrary.get_workflow()."""

    @pytest.fixture
    def library(self) -> BuiltinLibrary:
        """Create a BuiltinLibrary instance for testing."""
        return create_builtin_library()

    def test_returns_workflow_file_for_valid_workflow(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that get_workflow returns a WorkflowFile object."""
        workflow = library.get_workflow("fly-beads")
        assert isinstance(workflow, WorkflowFile)

    def test_workflow_file_has_correct_name(self, library: BuiltinLibrary) -> None:
        """Test that returned WorkflowFile has correct name attribute."""
        workflow = library.get_workflow("fly-beads")
        assert workflow.name == "fly-beads"

    def test_workflow_file_has_description(self, library: BuiltinLibrary) -> None:
        """Test that returned WorkflowFile has a description."""
        workflow = library.get_workflow("fly-beads")
        assert isinstance(workflow.description, str)
        assert len(workflow.description) > 0

    def test_workflow_file_has_version(self, library: BuiltinLibrary) -> None:
        """Test that returned WorkflowFile has a version."""
        workflow = library.get_workflow("fly-beads")
        assert isinstance(workflow.version, str)
        assert "." in workflow.version

    def test_workflow_file_has_steps(self, library: BuiltinLibrary) -> None:
        """Test that returned WorkflowFile has steps."""
        workflow = library.get_workflow("fly-beads")
        assert isinstance(workflow.steps, list)
        assert len(workflow.steps) > 0

    def test_all_workflows_can_be_loaded(self, library: BuiltinLibrary) -> None:
        """Test that all workflows load successfully."""
        loaded_count = 0
        for workflow_name in BUILTIN_WORKFLOWS:
            try:
                workflow = library.get_workflow(workflow_name)
                assert isinstance(workflow, WorkflowFile)
                assert isinstance(workflow.name, str)
                assert len(workflow.name) > 0
                loaded_count += 1
            except Exception:
                pass

        assert loaded_count >= 1, f"Only {loaded_count} workflows loaded successfully"

    def test_raises_key_error_for_invalid_workflow(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that get_workflow raises KeyError for invalid names."""
        with pytest.raises(KeyError, match="Unknown built-in workflow: unknown"):
            library.get_workflow("unknown")


# =============================================================================
# BuiltinLibrary.get_fragment() Tests
# =============================================================================


class TestGetFragment:
    """Test suite for BuiltinLibrary.get_fragment()."""

    @pytest.fixture
    def library(self) -> BuiltinLibrary:
        """Create a BuiltinLibrary instance for testing."""
        return create_builtin_library()

    def test_returns_workflow_file_for_valid_fragment(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that get_fragment returns a WorkflowFile object for valid fragments."""
        for fragment_name in ["commit-and-push", "create-pr-with-summary"]:
            try:
                fragment = library.get_fragment(fragment_name)
                assert isinstance(fragment, WorkflowFile)
                return
            except Exception:
                continue
        pytest.fail("No fragments could be loaded successfully")

    def test_all_fragments_can_be_loaded(self, library: BuiltinLibrary) -> None:
        """Test that fragments can be loaded successfully."""
        loaded_count = 0
        for fragment_name in BUILTIN_FRAGMENTS:
            try:
                fragment = library.get_fragment(fragment_name)
                assert isinstance(fragment, WorkflowFile)
                assert isinstance(fragment.name, str)
                assert len(fragment.name) > 0
                loaded_count += 1
            except Exception:
                pass

        assert loaded_count >= 1, "No fragments could be loaded successfully"

    def test_raises_key_error_for_invalid_fragment(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that get_fragment raises KeyError for invalid names."""
        with pytest.raises(KeyError, match="Unknown built-in fragment: unknown"):
            library.get_fragment("unknown")

    def test_raises_key_error_for_workflow_name(self, library: BuiltinLibrary) -> None:
        """Test that get_fragment raises KeyError for workflow names."""
        with pytest.raises(KeyError, match="Unknown built-in fragment"):
            library.get_fragment("fly-beads")


# =============================================================================
# Integration Tests
# =============================================================================


class TestBuiltinLibraryIntegration:
    """Integration tests for BuiltinLibrary combining multiple operations."""

    @pytest.fixture
    def library(self) -> BuiltinLibrary:
        """Create a BuiltinLibrary instance for testing."""
        return create_builtin_library()

    def test_has_workflow_matches_list_workflows(self, library: BuiltinLibrary) -> None:
        """Test that has_workflow is consistent with list_workflows."""
        workflows = library.list_workflows()
        workflow_names = {wf.name for wf in workflows}

        for name in workflow_names:
            assert library.has_workflow(name) is True

    def test_has_fragment_matches_list_fragments(self, library: BuiltinLibrary) -> None:
        """Test that has_fragment is consistent with list_fragments."""
        fragments = library.list_fragments()
        fragment_names = {frag.name for frag in fragments}

        for name in fragment_names:
            assert library.has_fragment(name) is True

    def test_get_workflow_path_and_get_workflow_are_consistent(
        self, library: BuiltinLibrary
    ) -> None:
        """Test that workflow path and loaded workflow are consistent."""
        path = library.get_workflow_path("fly-beads")
        workflow = library.get_workflow("fly-beads")

        assert "fly-beads" in str(path)
        assert workflow.name == "fly-beads"
