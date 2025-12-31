"""End-to-end test for YAML workflow invoking a fragment by name.

This test validates the complete integration:
1. Discovery finds workflows and fragments
2. Integration loads them into registry
3. WorkflowFileExecutor can execute a workflow that references a fragment
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.dsl.discovery import load_workflows_into_registry
from maverick.dsl.serialization.executor import WorkflowFileExecutor
from maverick.dsl.serialization.parser import parse_workflow
from maverick.dsl.serialization.registry import ComponentRegistry


@pytest.fixture
def fragment_workflow_yaml() -> str:
    """Create a simple fragment workflow."""
    return """version: "1.0"
name: simple-fragment
description: A simple fragment for testing
inputs:
  message:
    type: string
    required: true
steps:
  - name: log-message
    type: python
    action: log_message
    kwargs:
      message: "${{ inputs.message }}"
"""


@pytest.fixture
def parent_workflow_yaml() -> str:
    """Create a parent workflow that invokes a fragment."""
    return """version: "1.0"
name: parent-workflow
description: Parent workflow that invokes a fragment
inputs:
  test_message:
    type: string
    required: false
    default: "Hello from parent"
steps:
  - name: invoke-fragment
    type: subworkflow
    workflow: simple-fragment
    inputs:
      message: "${{ inputs.test_message }}"
"""


@pytest.fixture
def temp_workflows_with_fragment(
    tmp_path: Path,
    fragment_workflow_yaml: str,
    parent_workflow_yaml: str,
) -> tuple[Path, Path]:
    """Create temporary workflows directory with fragment and parent workflow."""
    # Create project structure
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    # Create workflows directory
    workflows_dir = project_dir / ".maverick" / "workflows"
    workflows_dir.mkdir(parents=True)

    # Create fragments directory
    fragments_dir = workflows_dir / "fragments"
    fragments_dir.mkdir()

    # Write fragment
    fragment_path = fragments_dir / "simple_fragment.yaml"
    fragment_path.write_text(fragment_workflow_yaml)

    # Write parent workflow
    parent_path = workflows_dir / "parent.yaml"
    parent_path.write_text(parent_workflow_yaml)

    return project_dir, parent_path


@pytest.mark.asyncio
async def test_workflow_invokes_fragment_by_name(
    temp_workflows_with_fragment: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a YAML workflow can invoke a fragment by name."""
    project_dir, parent_workflow_path = temp_workflows_with_fragment

    # Change to project directory so discovery finds the workflows
    monkeypatch.chdir(project_dir)

    # Create registry and load all discovered workflows
    registry = ComponentRegistry()

    # Register a dummy log_message action for testing
    def log_message(message: str) -> str:
        return f"Logged: {message}"

    registry.actions.register("log_message", log_message)

    # Load discovered workflows and fragments
    load_workflows_into_registry(registry)

    # Verify fragment was registered
    assert registry.workflows.has("simple-fragment")

    # Parse parent workflow
    parent_workflow = parse_workflow(
        parent_workflow_path.read_text(), validate_only=True
    )

    # Create executor with registry
    executor = WorkflowFileExecutor(registry=registry)

    # Execute parent workflow
    events = []
    async for event in executor.execute(
        parent_workflow, inputs={"test_message": "Test"}
    ):
        events.append(event)

    # Get result
    result = executor.get_result()

    # Workflow should succeed
    assert result.success
    assert result.workflow_name == "parent-workflow"

    # Should have executed the subworkflow step
    assert len(result.step_results) == 1
    assert result.step_results[0].name == "invoke-fragment"
    assert result.step_results[0].success


@pytest.mark.asyncio
async def test_workflow_fragment_not_found_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that missing fragment results in workflow failure."""
    # Create project directory
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    workflows_dir = project_dir / ".maverick" / "workflows"
    workflows_dir.mkdir(parents=True)

    # Create workflow that references non-existent fragment
    workflow_yaml = """version: "1.0"
name: broken-workflow
description: Workflow with missing fragment reference
steps:
  - name: invoke-missing
    type: subworkflow
    workflow: non-existent-fragment
    inputs: {}
"""
    workflow_path = workflows_dir / "broken.yaml"
    workflow_path.write_text(workflow_yaml)

    # Change to project directory
    monkeypatch.chdir(project_dir)

    # Create registry and load workflows
    registry = ComponentRegistry()
    load_workflows_into_registry(registry)

    # Parse workflow
    workflow = parse_workflow(workflow_yaml, validate_only=True)

    # Create executor with semantic validation disabled to test runtime error
    executor = WorkflowFileExecutor(registry=registry, validate_semantic=False)

    # Execute should complete but with failure
    async for _event in executor.execute(workflow, inputs={}):
        pass

    # Get result
    result = executor.get_result()

    # Workflow should fail
    assert not result.success
    assert len(result.step_results) == 1
    assert not result.step_results[0].success

    # Error should mention the missing workflow
    assert "non-existent-fragment" in result.step_results[0].error


@pytest.mark.asyncio
async def test_nested_fragment_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that a fragment can invoke another fragment."""
    # Create project directory
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    workflows_dir = project_dir / ".maverick" / "workflows"
    workflows_dir.mkdir(parents=True)
    fragments_dir = workflows_dir / "fragments"
    fragments_dir.mkdir()

    # Create leaf fragment
    leaf_yaml = """version: "1.0"
name: leaf-fragment
description: Leaf fragment
inputs:
  value:
    type: string
    required: true
steps:
  - name: log-leaf
    type: python
    action: log_message
    kwargs:
      message: "${{ inputs.value }}"
"""
    (fragments_dir / "leaf.yaml").write_text(leaf_yaml)

    # Create intermediate fragment that calls leaf
    intermediate_yaml = """version: "1.0"
name: intermediate-fragment
description: Intermediate fragment
inputs:
  msg:
    type: string
    required: true
steps:
  - name: call-leaf
    type: subworkflow
    workflow: leaf-fragment
    inputs:
      value: "${{ inputs.msg }}"
"""
    (fragments_dir / "intermediate.yaml").write_text(intermediate_yaml)

    # Create top-level workflow
    top_yaml = """version: "1.0"
name: top-workflow
description: Top workflow
steps:
  - name: call-intermediate
    type: subworkflow
    workflow: intermediate-fragment
    inputs:
      msg: "Hello from top"
"""
    (workflows_dir / "top.yaml").write_text(top_yaml)

    # Change to project directory
    monkeypatch.chdir(project_dir)

    # Create registry and load workflows
    registry = ComponentRegistry()

    # Register dummy action
    def log_message(message: str) -> str:
        return f"Logged: {message}"

    registry.actions.register("log_message", log_message)

    # Load discovered workflows
    load_workflows_into_registry(registry)

    # Verify all fragments are registered
    assert registry.workflows.has("leaf-fragment")
    assert registry.workflows.has("intermediate-fragment")
    assert registry.workflows.has("top-workflow")

    # Parse and execute top workflow
    top_workflow = parse_workflow(top_yaml, validate_only=True)
    executor = WorkflowFileExecutor(registry=registry)

    async for _event in executor.execute(top_workflow, inputs={}):
        pass

    result = executor.get_result()

    # Should succeed with nested fragment execution
    assert result.success
    assert result.workflow_name == "top-workflow"
