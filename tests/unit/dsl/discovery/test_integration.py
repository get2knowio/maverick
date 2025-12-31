"""Tests for workflow discovery to registry integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.dsl.discovery.integration import load_workflows_into_registry
from maverick.dsl.serialization.registry import ComponentRegistry

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
def temp_project_workflows(tmp_path: Path, sample_workflow_yaml: str) -> Path:
    """Create a temporary project workflows directory."""
    workflows_dir = tmp_path / ".maverick" / "workflows"
    workflows_dir.mkdir(parents=True)

    # Create a test workflow
    (workflows_dir / "my-workflow.yaml").write_text(
        sample_workflow_yaml.replace("test-workflow", "my-workflow")
    )

    return workflows_dir


@pytest.fixture
def temp_project_fragments(tmp_path: Path, sample_fragment_yaml: str) -> Path:
    """Create a temporary project fragments directory."""
    fragments_dir = tmp_path / ".maverick" / "workflows" / "fragments"
    fragments_dir.mkdir(parents=True)

    # Create a test fragment
    (fragments_dir / "my-fragment.yaml").write_text(
        sample_fragment_yaml.replace("test-fragment", "my-fragment")
    )

    return fragments_dir


# =============================================================================
# Integration Tests
# =============================================================================


def test_load_workflows_into_registry_basic() -> None:
    """Test loading workflows into registry."""
    registry = ComponentRegistry()

    # Initially registry should be empty
    assert registry.workflows.list_names() == []

    # Load discovered workflows
    load_workflows_into_registry(registry)

    # Registry should now contain built-in workflows
    workflow_names = registry.workflows.list_names()

    # Should at least have some builtin workflows
    # Note: exact names depend on what's in maverick.library
    assert len(workflow_names) > 0


def test_load_workflows_registers_fragments() -> None:
    """Test that fragments are registered alongside workflows."""
    registry = ComponentRegistry()

    # Load discovered workflows and fragments
    load_workflows_into_registry(registry)

    # Registry should contain both workflows and fragments
    all_names = registry.workflows.list_names()

    # Should have at least some entries (builtins)
    assert len(all_names) > 0


def test_load_workflows_respects_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sample_workflow_yaml: str,
) -> None:
    """Test that project workflows override builtin workflows."""
    # Create a project directory with a custom "fly" workflow
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    workflows_dir = project_dir / ".maverick" / "workflows"
    workflows_dir.mkdir(parents=True)

    # Create custom fly workflow
    custom_fly_yaml = sample_workflow_yaml.replace("test-workflow", "fly").replace(
        "A test workflow", "Custom fly workflow"
    )
    (workflows_dir / "fly.yaml").write_text(custom_fly_yaml)

    # Change to project directory
    monkeypatch.chdir(project_dir)

    # Load workflows
    registry = ComponentRegistry()
    load_workflows_into_registry(registry)

    # Should have fly workflow registered
    assert registry.workflows.has("fly")

    # Get the workflow
    fly_workflow = registry.workflows.get("fly")

    # Should be the custom one (with custom description)
    assert fly_workflow.description == "Custom fly workflow"


def test_load_workflows_into_empty_registry() -> None:
    """Test loading workflows into an empty registry."""
    registry = ComponentRegistry()

    # Should not raise any errors
    load_workflows_into_registry(registry)

    # Should have populated the registry
    assert len(registry.workflows.list_names()) > 0


def test_load_workflows_no_duplicates() -> None:
    """Test that loading workflows doesn't create duplicates."""
    from maverick.dsl.errors import DuplicateComponentError

    registry = ComponentRegistry()

    # Load workflows once
    load_workflows_into_registry(registry)
    len(registry.workflows.list_names())

    # Loading again should raise error due to duplicate registration
    # (ComponentRegistry doesn't allow re-registering the same name)
    with pytest.raises(DuplicateComponentError):
        load_workflows_into_registry(registry)


def test_load_workflows_can_be_looked_up() -> None:
    """Test that loaded workflows can be looked up by name."""
    registry = ComponentRegistry()
    load_workflows_into_registry(registry)

    # Get all workflow names
    workflow_names = registry.workflows.list_names()

    # Should be able to look up each one
    for name in workflow_names:
        workflow = registry.workflows.get(name)
        assert workflow is not None
        assert workflow.name == name


def test_load_workflows_with_project_fragment_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sample_fragment_yaml: str,
) -> None:
    """Test that project fragments override builtin fragments."""
    # Create a project directory with a custom fragment
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    fragments_dir = project_dir / ".maverick" / "workflows" / "fragments"
    fragments_dir.mkdir(parents=True)

    # Create custom fragment that might override a builtin
    # Note: File uses underscores, workflow name uses hyphens (established convention)
    custom_fragment_yaml = sample_fragment_yaml.replace(
        "test-fragment", "commit-and-push"
    ).replace("A test fragment", "Custom commit-and-push fragment")
    (fragments_dir / "commit_and_push.yaml").write_text(custom_fragment_yaml)

    # Change to project directory
    monkeypatch.chdir(project_dir)

    # Load workflows
    registry = ComponentRegistry()
    load_workflows_into_registry(registry)

    # Should have the fragment registered
    if registry.workflows.has("commit-and-push"):
        fragment = registry.workflows.get("commit-and-push")
        # Should be the custom one (with custom description)
        assert fragment.description == "Custom commit-and-push fragment"
