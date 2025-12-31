"""Tests for DefaultWorkflowDiscovery (T025-001 through T025-012).

This module tests the workflow discovery registry implementation, including:
- Path resolution methods (builtin, user, project)
- Workflow discovery from multiple locations
- Precedence and override behavior
- Conflict detection
- Discovery result structure and properties
- Factory function
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.dsl.discovery import (
    DefaultWorkflowDiscovery,
    DiscoveryResult,
    WorkflowConflictError,
    WorkflowSource,
    create_discovery,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_workflow_yaml() -> str:
    """Create a minimal valid workflow YAML."""
    return """version: "1.0"
name: test-workflow
description: A test workflow
inputs:
  test_input:
    type: string
    required: false
steps:
  - name: step1
    type: python
    action: log_message
    kwargs:
      message: "test"
"""


@pytest.fixture
def sample_fragment_yaml() -> str:
    """Create a minimal valid fragment YAML."""
    return """version: "1.0"
name: test-fragment
description: A test fragment
inputs:
  test_input:
    type: string
    required: false
steps:
  - name: step1
    type: python
    action: log_message
    kwargs:
      message: "test"
"""


@pytest.fixture
def builtin_workflow_names() -> set[str]:
    """Expected builtin workflow names that currently parse successfully.

    Note: Some builtin workflows may be skipped if they use features not yet
    implemented in the parser (e.g., format() function, advanced expressions).
    """
    return {"review", "validate"}


@pytest.fixture
def builtin_fragment_names() -> set[str]:
    """Expected builtin fragment names that currently parse successfully.

    Note: Some builtin fragments may be skipped if they use features not yet
    implemented in the parser.
    """
    return {"commit-and-push", "create-pr-with-summary"}


# =============================================================================
# T025-001: Test get_builtin_path()
# =============================================================================


def test_get_builtin_path_returns_library_path() -> None:
    """Test get_builtin_path() returns path to maverick.library directory."""
    discovery = DefaultWorkflowDiscovery()
    builtin_path = discovery.get_builtin_path()

    # Should be an absolute path
    assert builtin_path.is_absolute()

    # Should contain "maverick" in the path
    assert "maverick" in str(builtin_path)

    # Should exist
    assert builtin_path.exists()
    assert builtin_path.is_dir()

    # Should contain workflows subdirectory
    workflows_dir = builtin_path / "workflows"
    assert workflows_dir.exists()


def test_get_builtin_path_contains_expected_workflows() -> None:
    """Test builtin path contains expected workflow files."""
    discovery = DefaultWorkflowDiscovery()
    builtin_path = discovery.get_builtin_path()

    # Check for expected workflow files
    review_workflow = builtin_path / "workflows" / "review.yaml"
    assert review_workflow.exists()

    # Check for expected fragment files (note: file uses underscores)
    validate_fragment = builtin_path / "fragments" / "validate_and_fix.yaml"
    assert validate_fragment.exists()


# =============================================================================
# T025-002: Test get_user_path()
# =============================================================================


def test_get_user_path_returns_config_directory() -> None:
    """Test get_user_path() returns ~/.config/maverick/workflows/."""
    discovery = DefaultWorkflowDiscovery()
    user_path = discovery.get_user_path()

    # Should be an absolute path
    assert user_path.is_absolute()

    # Should be in home directory
    assert user_path.is_relative_to(Path.home())

    # Should match expected path
    expected = Path.home() / ".config" / "maverick" / "workflows"
    assert user_path == expected


# =============================================================================
# T025-003: Test get_project_path()
# =============================================================================


def test_get_project_path_returns_maverick_workflows() -> None:
    """Test get_project_path() returns .maverick/workflows/ relative to cwd."""
    discovery = DefaultWorkflowDiscovery()
    project_path = discovery.get_project_path()

    # Should be an absolute path
    assert project_path.is_absolute()

    # Should end with .maverick/workflows
    assert project_path.name == "workflows"
    assert project_path.parent.name == ".maverick"

    # Should be relative to current working directory
    assert project_path == Path.cwd() / ".maverick" / "workflows"


def test_get_project_path_with_custom_root(tmp_path: Path) -> None:
    """Test get_project_path() with custom project_root parameter."""
    discovery = DefaultWorkflowDiscovery()
    custom_root = tmp_path / "custom_project"
    custom_root.mkdir()

    project_path = discovery.get_project_path(project_root=custom_root)

    # Should be relative to custom root
    assert project_path == custom_root / ".maverick" / "workflows"


# =============================================================================
# T025-004: Test discover() - Basic Discovery
# =============================================================================


def test_discover_finds_builtin_workflows(
    builtin_workflow_names: set[str],
) -> None:
    """Test discover() finds builtin workflows."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Should find workflows
    assert len(result.workflows) > 0

    # Extract workflow names
    discovered_names = {w.workflow.name for w in result.workflows}

    # Should contain expected builtin workflows
    assert builtin_workflow_names.issubset(discovered_names)


def test_discover_finds_builtin_fragments(
    builtin_fragment_names: set[str],
) -> None:
    """Test discover() finds builtin fragments."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Should find fragments
    assert len(result.fragments) > 0

    # Extract fragment names
    discovered_names = {f.workflow.name for f in result.fragments}

    # Should contain expected builtin fragments
    assert builtin_fragment_names.issubset(discovered_names)


def test_discover_returns_correct_structure() -> None:
    """Test discover() returns DiscoveryResult with correct structure."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Should be a DiscoveryResult instance
    assert isinstance(result, DiscoveryResult)

    # Should have all required fields
    assert isinstance(result.workflows, tuple)
    assert isinstance(result.fragments, tuple)
    assert isinstance(result.skipped, tuple)
    assert isinstance(result.locations_scanned, tuple)
    assert isinstance(result.discovery_time_ms, float)


def test_discover_workflow_names_property() -> None:
    """Test DiscoveryResult.workflow_names property returns sorted names."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Get workflow names
    names = result.workflow_names

    # Should be a tuple
    assert isinstance(names, tuple)

    # Should contain strings
    assert all(isinstance(name, str) for name in names)

    # Should be sorted
    assert names == tuple(sorted(names))

    # Should contain expected workflows (that parse successfully)
    assert "review" in names
    assert "validate" in names


def test_discover_fragment_names_property() -> None:
    """Test DiscoveryResult.fragment_names property returns sorted names."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Get fragment names
    names = result.fragment_names

    # Should be a tuple
    assert isinstance(names, tuple)

    # Should contain strings
    assert all(isinstance(name, str) for name in names)

    # Should be sorted
    assert names == tuple(sorted(names))

    # Should contain expected fragments (that parse successfully)
    assert "commit-and-push" in names
    assert "create-pr-with-summary" in names


def test_discover_get_workflow_lookup() -> None:
    """Test DiscoveryResult.get_workflow() lookup by name."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Lookup existing workflow
    review_workflow = result.get_workflow("review")
    assert review_workflow is not None
    assert review_workflow.workflow.name == "review"
    assert review_workflow.source == WorkflowSource.BUILTIN.value

    # Lookup non-existent workflow
    missing = result.get_workflow("nonexistent-workflow")
    assert missing is None


def test_discover_get_fragment_lookup() -> None:
    """Test DiscoveryResult.get_fragment() lookup by name."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Lookup existing fragment
    commit_fragment = result.get_fragment("commit-and-push")
    assert commit_fragment is not None
    assert commit_fragment.workflow.name == "commit-and-push"
    assert commit_fragment.source == WorkflowSource.BUILTIN.value

    # Lookup non-existent fragment
    missing = result.get_fragment("nonexistent-fragment")
    assert missing is None


def test_discover_locations_scanned() -> None:
    """Test DiscoveryResult.locations_scanned contains correct paths."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Should have at least builtin path
    assert len(result.locations_scanned) >= 1

    # All should be Path instances
    assert all(isinstance(path, Path) for path in result.locations_scanned)

    # Should include builtin path
    builtin_path = discovery.get_builtin_path()
    assert builtin_path in result.locations_scanned


def test_discover_time_is_positive() -> None:
    """Test DiscoveryResult.discovery_time_ms is positive number."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Discovery time should be positive
    assert result.discovery_time_ms > 0

    # Should be a reasonable value (less than 10 seconds)
    assert result.discovery_time_ms < 10_000


def test_discover_without_builtin() -> None:
    """Test discover() with include_builtin=False."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=False)

    # Should not include builtin workflows
    builtin_path = discovery.get_builtin_path()
    assert builtin_path not in result.locations_scanned

    # May have no workflows if user/project dirs don't exist
    # Just verify the structure is valid
    assert isinstance(result.workflows, tuple)
    assert isinstance(result.fragments, tuple)


# =============================================================================
# T025-005: Test discover() - Skipped Files
# =============================================================================


def test_discover_skipped_list_contains_invalid_files(tmp_path: Path) -> None:
    """Test discover() skips invalid files and reports them."""
    # Create project workflows directory
    project_dir = tmp_path / ".maverick" / "workflows"
    project_dir.mkdir(parents=True)

    # Create an invalid YAML file
    invalid_file = project_dir / "invalid.yaml"
    invalid_file.write_text("this is not valid: yaml: syntax: ][")

    # Discover from project directory
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(project_dir=project_dir, include_builtin=False)

    # Should have skipped the invalid file
    assert len(result.skipped) > 0

    # Check that the invalid file is in the skipped list
    skipped_paths = {s.file_path for s in result.skipped}
    assert invalid_file in skipped_paths

    # Skipped entry should have error info
    skipped_entry = next(s for s in result.skipped if s.file_path == invalid_file)
    assert skipped_entry.error_message
    assert skipped_entry.error_type


def test_discover_skipped_with_missing_required_fields(tmp_path: Path) -> None:
    """Test discover() skips workflows missing required fields."""
    # Create project workflows directory
    project_dir = tmp_path / ".maverick" / "workflows"
    project_dir.mkdir(parents=True)

    # Create workflow missing required fields
    incomplete_file = project_dir / "incomplete.yaml"
    incomplete_file.write_text("""
version: "1.0"
# Missing name field
description: Incomplete workflow
steps: []
""")

    # Discover from project directory
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(project_dir=project_dir, include_builtin=False)

    # Should have skipped the incomplete file
    assert len(result.skipped) > 0
    skipped_paths = {s.file_path for s in result.skipped}
    assert incomplete_file in skipped_paths


# =============================================================================
# T025-006: Test Precedence - Project Overrides Builtin
# =============================================================================


def test_discover_project_overrides_builtin(
    tmp_path: Path,
    sample_workflow_yaml: str,
) -> None:
    """Test project workflow takes precedence over builtin."""
    # Create project workflows directory
    project_dir = tmp_path / ".maverick" / "workflows"
    project_dir.mkdir(parents=True)

    # Create a workflow with same name as builtin
    project_workflow = project_dir / "review.yaml"
    # Modify the YAML to use "review" name
    custom_yaml = sample_workflow_yaml.replace("test-workflow", "review")
    project_workflow.write_text(custom_yaml)

    # Discover workflows
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(project_dir=project_dir, include_builtin=True)

    # Should find the workflow
    review = result.get_workflow("review")
    assert review is not None

    # Should be from project source (highest precedence)
    assert review.source == WorkflowSource.PROJECT.value

    # File path should be the project file
    assert review.file_path == project_workflow

    # Should have overrides tuple containing the builtin path
    assert len(review.overrides) > 0
    # Check that one of the overridden paths is from builtin
    builtin_path = discovery.get_builtin_path()
    overridden_paths_str = [str(p) for p in review.overrides]
    assert any(str(builtin_path) in p for p in overridden_paths_str)


def test_discover_user_overrides_builtin(
    tmp_path: Path,
    sample_workflow_yaml: str,
) -> None:
    """Test user workflow takes precedence over builtin."""
    # Create user workflows directory
    user_dir = tmp_path / "user_workflows"
    user_dir.mkdir(parents=True)

    # Create a workflow with same name as builtin
    user_workflow = user_dir / "review.yaml"
    custom_yaml = sample_workflow_yaml.replace("test-workflow", "review")
    user_workflow.write_text(custom_yaml)

    # Discover workflows
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(user_dir=user_dir, include_builtin=True)

    # Should find the workflow
    review = result.get_workflow("review")
    assert review is not None

    # Should be from user source
    assert review.source == WorkflowSource.USER.value

    # File path should be the user file
    assert review.file_path == user_workflow

    # Should have overrides
    assert len(review.overrides) > 0


def test_discover_project_overrides_user(
    tmp_path: Path,
    sample_workflow_yaml: str,
) -> None:
    """Test project workflow takes precedence over user workflow."""
    # Create both user and project directories
    user_dir = tmp_path / "user_workflows"
    user_dir.mkdir(parents=True)
    project_dir = tmp_path / ".maverick" / "workflows"
    project_dir.mkdir(parents=True)

    # Create same workflow in both locations
    user_workflow = user_dir / "custom.yaml"
    project_workflow = project_dir / "custom.yaml"

    custom_yaml = sample_workflow_yaml.replace("test-workflow", "custom")
    user_workflow.write_text(custom_yaml)
    project_workflow.write_text(custom_yaml)

    # Discover workflows
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(
        user_dir=user_dir,
        project_dir=project_dir,
        include_builtin=False,
    )

    # Should find the workflow
    custom = result.get_workflow("custom")
    assert custom is not None

    # Should be from project source (highest precedence)
    assert custom.source == WorkflowSource.PROJECT.value

    # File path should be the project file
    assert custom.file_path == project_workflow

    # Should override the user workflow
    assert user_workflow in custom.overrides


# =============================================================================
# T025-007: Test Conflict Detection
# =============================================================================


def test_discover_raises_conflict_error_for_duplicate_in_same_location(
    tmp_path: Path,
    sample_workflow_yaml: str,
) -> None:
    """Test WorkflowConflictError raised when same name exists at same precedence."""
    # Create project workflows directory with subdirectories
    project_dir = tmp_path / ".maverick" / "workflows"
    subdir1 = project_dir / "features"
    subdir2 = project_dir / "common"
    subdir1.mkdir(parents=True)
    subdir2.mkdir(parents=True)

    # Create two workflows with same name in same source (project)
    workflow1 = subdir1 / "duplicate.yaml"
    workflow2 = subdir2 / "duplicate.yaml"

    custom_yaml = sample_workflow_yaml.replace("test-workflow", "duplicate")
    workflow1.write_text(custom_yaml)
    workflow2.write_text(custom_yaml)

    # Discover should raise conflict error
    discovery = DefaultWorkflowDiscovery()
    with pytest.raises(WorkflowConflictError) as exc_info:
        discovery.discover(project_dir=project_dir, include_builtin=False)

    # Check error details
    error = exc_info.value
    assert error.name == "duplicate"
    assert error.source == WorkflowSource.PROJECT.value
    assert len(error.conflicting_paths) == 2
    assert workflow1 in error.conflicting_paths
    assert workflow2 in error.conflicting_paths


def test_discover_raises_conflict_error_for_fragments(
    tmp_path: Path,
    sample_fragment_yaml: str,
) -> None:
    """Test conflict detection works for fragments too."""
    # Create project fragments directory with subdirectories
    fragments_dir = tmp_path / ".maverick" / "workflows" / "fragments"
    subdir1 = fragments_dir / "util"
    subdir2 = fragments_dir / "core"
    subdir1.mkdir(parents=True)
    subdir2.mkdir(parents=True)

    # Create two fragments with same name
    fragment1 = subdir1 / "duplicate-fragment.yaml"
    fragment2 = subdir2 / "duplicate-fragment.yaml"

    custom_yaml = sample_fragment_yaml.replace("test-fragment", "duplicate-fragment")
    fragment1.write_text(custom_yaml)
    fragment2.write_text(custom_yaml)

    # Discover should raise conflict error
    discovery = DefaultWorkflowDiscovery()
    with pytest.raises(WorkflowConflictError) as exc_info:
        discovery.discover(
            project_dir=tmp_path / ".maverick" / "workflows",
            include_builtin=False,
        )

    # Check error details
    error = exc_info.value
    assert error.name == "duplicate-fragment"
    assert len(error.conflicting_paths) == 2


# =============================================================================
# T025-008: Test Fragment Detection
# =============================================================================


def test_discover_distinguishes_workflows_from_fragments(
    tmp_path: Path,
    sample_workflow_yaml: str,
    sample_fragment_yaml: str,
) -> None:
    """Test workflows and fragments are correctly distinguished."""
    # Create both workflows and fragments directories
    workflows_dir = tmp_path / ".maverick" / "workflows"
    fragments_dir = workflows_dir / "fragments"
    workflows_dir.mkdir(parents=True)
    fragments_dir.mkdir(parents=True)

    # Create a workflow
    workflow_file = workflows_dir / "my-workflow.yaml"
    workflow_file.write_text(sample_workflow_yaml)

    # Create a fragment
    fragment_file = fragments_dir / "my-fragment.yaml"
    fragment_file.write_text(sample_fragment_yaml)

    # Discover
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(project_dir=workflows_dir, include_builtin=False)

    # Should have both workflows and fragments
    assert len(result.workflows) > 0
    assert len(result.fragments) > 0

    # Workflow should be in workflows list
    assert "test-workflow" in result.workflow_names

    # Fragment should be in fragments list
    assert "test-fragment" in result.fragment_names


# =============================================================================
# T025-009: Test create_discovery() Factory
# =============================================================================


def test_create_discovery_returns_instance() -> None:
    """Test create_discovery() returns DefaultWorkflowDiscovery instance."""
    discovery = create_discovery()

    assert isinstance(discovery, DefaultWorkflowDiscovery)


def test_create_discovery_with_custom_locator() -> None:
    """Test create_discovery() accepts custom locator."""
    from maverick.dsl.discovery.registry import WorkflowLocator

    custom_locator = WorkflowLocator()
    discovery = create_discovery(locator=custom_locator)

    assert isinstance(discovery, DefaultWorkflowDiscovery)
    # The locator should be the one we passed in
    assert discovery._locator is custom_locator


def test_create_discovery_with_custom_loader() -> None:
    """Test create_discovery() accepts custom loader."""
    from maverick.dsl.discovery.registry import WorkflowLoader

    custom_loader = WorkflowLoader()
    discovery = create_discovery(loader=custom_loader)

    assert isinstance(discovery, DefaultWorkflowDiscovery)
    # The loader should be the one we passed in
    assert discovery._loader is custom_loader


# =============================================================================
# T025-010: Test Edge Cases
# =============================================================================


def test_discover_empty_project_directory(tmp_path: Path) -> None:
    """Test discover() handles empty project directory gracefully."""
    # Create empty project directory
    project_dir = tmp_path / ".maverick" / "workflows"
    project_dir.mkdir(parents=True)

    # Discover should complete without error
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(project_dir=project_dir, include_builtin=False)

    # Should have no workflows from project
    assert len(result.workflows) == 0
    assert len(result.fragments) == 0
    assert len(result.skipped) == 0


def test_discover_nonexistent_project_directory(tmp_path: Path) -> None:
    """Test discover() handles nonexistent project directory gracefully."""
    # Use non-existent directory
    project_dir = tmp_path / "does-not-exist"

    # Discover should complete without error
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(project_dir=project_dir, include_builtin=False)

    # Should have no workflows
    assert len(result.workflows) == 0
    assert len(result.fragments) == 0

    # Should not have scanned the non-existent directory
    assert project_dir not in result.locations_scanned


def test_discover_yml_extension(tmp_path: Path, sample_workflow_yaml: str) -> None:
    """Test discover() finds .yml files (not just .yaml)."""
    # Create project directory
    project_dir = tmp_path / ".maverick" / "workflows"
    project_dir.mkdir(parents=True)

    # Create workflow with .yml extension
    workflow_file = project_dir / "test.yml"
    workflow_file.write_text(sample_workflow_yaml)

    # Discover
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(project_dir=project_dir, include_builtin=False)

    # Should find the workflow
    assert len(result.workflows) > 0
    assert "test-workflow" in result.workflow_names


def test_discover_nested_directories(
    tmp_path: Path,
    sample_workflow_yaml: str,
) -> None:
    """Test discover() scans nested directories recursively."""
    # Create nested directory structure
    project_dir = tmp_path / ".maverick" / "workflows"
    nested_dir = project_dir / "category" / "subcategory"
    nested_dir.mkdir(parents=True)

    # Create workflow in nested directory
    workflow_file = nested_dir / "nested.yaml"
    workflow_file.write_text(sample_workflow_yaml)

    # Discover
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(project_dir=project_dir, include_builtin=False)

    # Should find the nested workflow
    assert len(result.workflows) > 0
    assert "test-workflow" in result.workflow_names


# =============================================================================
# T025-011: Test Source Attribution
# =============================================================================


def test_discovered_workflow_has_correct_source_builtin() -> None:
    """Test discovered builtin workflows have correct source attribution."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Get a builtin workflow
    review = result.get_workflow("review")
    assert review is not None
    assert review.source == WorkflowSource.BUILTIN.value


def test_discovered_workflow_has_correct_source_project(
    tmp_path: Path,
    sample_workflow_yaml: str,
) -> None:
    """Test discovered project workflows have correct source attribution."""
    # Create project directory
    project_dir = tmp_path / ".maverick" / "workflows"
    project_dir.mkdir(parents=True)

    # Create workflow
    workflow_file = project_dir / "project-workflow.yaml"
    workflow_file.write_text(sample_workflow_yaml)

    # Discover
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(project_dir=project_dir, include_builtin=False)

    # Get the workflow
    workflow = result.get_workflow("test-workflow")
    assert workflow is not None
    assert workflow.source == WorkflowSource.PROJECT.value


def test_discovered_workflow_has_correct_source_user(
    tmp_path: Path,
    sample_workflow_yaml: str,
) -> None:
    """Test discovered user workflows have correct source attribution."""
    # Create user directory
    user_dir = tmp_path / "user_workflows"
    user_dir.mkdir(parents=True)

    # Create workflow
    workflow_file = user_dir / "user-workflow.yaml"
    workflow_file.write_text(sample_workflow_yaml)

    # Discover
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(user_dir=user_dir, include_builtin=False)

    # Get the workflow
    workflow = result.get_workflow("test-workflow")
    assert workflow is not None
    assert workflow.source == WorkflowSource.USER.value


# =============================================================================
# T025-012: Test DiscoveredWorkflow Structure
# =============================================================================


def test_discovered_workflow_structure() -> None:
    """Test DiscoveredWorkflow contains all expected fields."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Get a workflow
    review = result.get_workflow("review")
    assert review is not None

    # Check all fields are present and correct types
    assert hasattr(review, "workflow")
    assert hasattr(review, "file_path")
    assert hasattr(review, "source")
    assert hasattr(review, "overrides")

    # Check types
    assert isinstance(review.file_path, Path)
    assert isinstance(review.source, str)
    assert isinstance(review.overrides, tuple)

    # File path should exist
    assert review.file_path.exists()

    # Workflow should have name and description
    assert review.workflow.name == "review"
    assert review.workflow.description


def test_discovered_workflow_overrides_empty_when_no_conflicts() -> None:
    """Test overrides tuple is empty when no lower-precedence workflows exist."""
    discovery = DefaultWorkflowDiscovery()
    # Only discover builtin (no user/project to override)
    result = discovery.discover(include_builtin=True)

    # Get a builtin workflow
    review = result.get_workflow("review")
    assert review is not None

    # Should have empty overrides (nothing to override at builtin level)
    assert len(review.overrides) == 0


# =============================================================================
# T025-013: Test DiscoveryResult Search and Filter Methods
# =============================================================================


def test_search_workflows_by_name() -> None:
    """Test search_workflows() finds workflows by name."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Search for "review" (a workflow that actually exists in builtin)
    matches = result.search_workflows("review")

    # Should find at least the review workflow
    assert len(matches) > 0
    assert any(w.workflow.name == "review" for w in matches)


def test_search_workflows_case_insensitive() -> None:
    """Test search_workflows() is case-insensitive."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Search with different cases for "review"
    matches_lower = result.search_workflows("review")
    matches_upper = result.search_workflows("REVIEW")
    matches_mixed = result.search_workflows("Review")

    # All should return same results
    assert len(matches_lower) == len(matches_upper)
    assert len(matches_lower) == len(matches_mixed)


def test_search_workflows_by_description() -> None:
    """Test search_workflows() searches in descriptions."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Search for common words that might appear in descriptions
    matches = result.search_workflows("workflow")

    # Should find multiple workflows with "workflow" in description
    assert len(matches) > 0


def test_search_workflows_returns_sorted() -> None:
    """Test search_workflows() returns results sorted by name."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Search broadly to get multiple results
    matches = result.search_workflows("w")

    if len(matches) > 1:
        # Check sorting
        names = [w.workflow.name for w in matches]
        assert names == sorted(names)


def test_search_workflows_no_matches() -> None:
    """Test search_workflows() returns empty tuple when no matches."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Search for something that definitely doesn't exist
    matches = result.search_workflows("nonexistent-impossible-workflow-name-xyz")

    assert len(matches) == 0
    assert isinstance(matches, tuple)


def test_filter_by_source_builtin() -> None:
    """Test filter_by_source() filters by builtin source."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Filter to builtin only
    builtin = result.filter_by_source("builtin")

    # All should be from builtin source
    assert all(w.source == "builtin" for w in builtin)

    # Should find at least some builtin workflows
    assert len(builtin) > 0


def test_filter_by_source_project(tmp_path: Path, sample_workflow_yaml: str) -> None:
    """Test filter_by_source() filters by project source."""
    # Create project directory
    project_dir = tmp_path / ".maverick" / "workflows"
    project_dir.mkdir(parents=True)

    # Create workflow
    workflow_file = project_dir / "project-workflow.yaml"
    workflow_file.write_text(sample_workflow_yaml)

    # Discover
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(project_dir=project_dir, include_builtin=True)

    # Filter to project only
    project = result.filter_by_source("project")

    # All should be from project source
    assert all(w.source == "project" for w in project)

    # Should find the workflow we created
    assert len(project) == 1
    assert project[0].workflow.name == "test-workflow"


def test_filter_by_source_returns_sorted() -> None:
    """Test filter_by_source() returns results sorted by name."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Filter to builtin
    builtin = result.filter_by_source("builtin")

    if len(builtin) > 1:
        # Check sorting
        names = [w.workflow.name for w in builtin]
        assert names == sorted(names)


def test_filter_by_source_empty_result() -> None:
    """Test filter_by_source() returns empty tuple when no matches."""
    discovery = DefaultWorkflowDiscovery()
    # Only discover builtin, no user or project
    result = discovery.discover(include_builtin=True)

    # Filter to project (which doesn't exist)
    project = result.filter_by_source("project")

    assert len(project) == 0
    assert isinstance(project, tuple)


def test_get_all_with_name_single_version() -> None:
    """Test get_all_with_name() returns single version when no overrides."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Get all versions of "review" (should just be builtin)
    all_versions = result.get_all_with_name("review")

    # Should have exactly one version (no overrides)
    assert len(all_versions) == 1

    # Should be from builtin
    source, path = all_versions[0]
    assert source == "builtin"
    assert path.exists()


def test_get_all_with_name_multiple_versions(
    tmp_path: Path,
    sample_workflow_yaml: str,
) -> None:
    """Test get_all_with_name() returns all versions with proper precedence."""
    # Create user and project directories
    user_dir = tmp_path / "user_workflows"
    user_dir.mkdir(parents=True)
    project_dir = tmp_path / ".maverick" / "workflows"
    project_dir.mkdir(parents=True)

    # Create same workflow in both locations
    custom_yaml = sample_workflow_yaml.replace("test-workflow", "custom")
    user_workflow = user_dir / "custom.yaml"
    project_workflow = project_dir / "custom.yaml"
    user_workflow.write_text(custom_yaml)
    project_workflow.write_text(custom_yaml)

    # Discover
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(
        user_dir=user_dir,
        project_dir=project_dir,
        include_builtin=False,
    )

    # Get all versions
    all_versions = result.get_all_with_name("custom")

    # Should have 2 versions
    assert len(all_versions) == 2

    # First should be project (highest precedence)
    source1, path1 = all_versions[0]
    assert source1 == "project"
    assert path1 == project_workflow

    # Second should be user
    source2, path2 = all_versions[1]
    assert source2 == "user"
    assert path2 == user_workflow


def test_get_all_with_name_returns_empty_when_not_found() -> None:
    """Test get_all_with_name() returns empty tuple when workflow not found."""
    discovery = DefaultWorkflowDiscovery()
    result = discovery.discover(include_builtin=True)

    # Search for non-existent workflow
    all_versions = result.get_all_with_name("nonexistent-workflow")

    assert len(all_versions) == 0
    assert isinstance(all_versions, tuple)
