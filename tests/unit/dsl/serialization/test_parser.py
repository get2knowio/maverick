"""Tests for workflow parser (T032a-d, T032-T039).

This module tests the workflow YAML/JSON parser, including:
- YAML parsing with error handling
- Schema validation against WorkflowFile Pydantic model
- Version validation
- Expression extraction and validation
- Reference resolution (actions, agents, generators, workflows)
- Lenient mode and validate_only mode
"""

from __future__ import annotations

from typing import Any

import pytest

from maverick.dsl.errors import (
    ReferenceResolutionError,
    UnsupportedVersionError,
    WorkflowParseError,
)
from maverick.dsl.expressions.errors import ExpressionSyntaxError
from maverick.dsl.serialization.parser import (
    extract_expressions,
    parse_workflow,
    parse_yaml,
    resolve_references,
    validate_schema,
    validate_version,
)
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import WorkflowFile

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def valid_workflow_yaml() -> str:
    """Valid workflow YAML for testing."""
    return """
version: "1.0"
name: test-workflow
description: A test workflow
inputs:
  dry_run:
    type: boolean
    required: false
    default: false
steps:
  - name: setup
    type: python
    action: validate_files
    kwargs:
      path: /tmp/test
  - name: review
    type: agent
    agent: code_reviewer
    context:
      files: ${{ inputs.files }}
"""


@pytest.fixture
def component_reg() -> ComponentRegistry:
    """Create a ComponentRegistry with test components."""
    registry = ComponentRegistry(strict=True)

    # Register test action
    def validate_files(path: str) -> bool:
        return True

    registry.actions.register("validate_files", validate_files)

    # Register test agent (mock class)
    class MockAgent:
        pass

    # Register as both agent and generator to support different step types
    registry.agents.register("code_reviewer", MockAgent, validate=False)  # type: ignore
    registry.generators.register("code_reviewer", MockAgent, validate=False)  # type: ignore

    return registry


# =============================================================================
# T032a: parse_yaml Tests
# =============================================================================


def test_parse_yaml_valid() -> None:
    """Test parsing valid YAML content."""
    yaml_content = """
version: "1.0"
name: test-workflow
steps:
  - name: step1
    type: python
    action: my_action
"""
    result = parse_yaml(yaml_content)
    assert isinstance(result, dict)
    assert result["version"] == "1.0"
    assert result["name"] == "test-workflow"
    assert len(result["steps"]) == 1


def test_parse_yaml_empty_content() -> None:
    """Test parsing empty YAML content raises error."""
    with pytest.raises(WorkflowParseError) as exc_info:
        parse_yaml("")
    assert "Empty workflow" in str(exc_info.value)


def test_parse_yaml_invalid_syntax() -> None:
    """Test parsing YAML with syntax errors."""
    invalid_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: step1
    type: python
    action: [unclosed list
"""
    with pytest.raises(WorkflowParseError) as exc_info:
        parse_yaml(invalid_yaml)
    assert exc_info.value.parse_error is not None


def test_parse_yaml_not_dict() -> None:
    """Test parsing YAML that doesn't result in a dict."""
    list_yaml = """
- item1
- item2
"""
    with pytest.raises(WorkflowParseError) as exc_info:
        parse_yaml(list_yaml)
    assert "must be an object" in str(exc_info.value).lower()


def test_parse_yaml_preserves_line_numbers() -> None:
    """Test that parse errors include line number context when available."""
    invalid_yaml = """
version: "1.0"
name: test-workflow
steps: [unclosed
"""
    with pytest.raises(WorkflowParseError) as exc_info:
        parse_yaml(invalid_yaml)
    # PyYAML typically includes line/column info
    assert exc_info.value.parse_error is not None


# =============================================================================
# T033: validate_schema Tests
# =============================================================================


def test_validate_schema_valid() -> None:
    """Test validating a valid workflow dict."""
    workflow_dict = {
        "version": "1.0",
        "name": "test-workflow",
        "steps": [
            {
                "name": "step1",
                "type": "python",
                "action": "my_action",
            }
        ],
    }
    workflow = validate_schema(workflow_dict)
    assert isinstance(workflow, WorkflowFile)
    assert workflow.name == "test-workflow"
    assert len(workflow.steps) == 1


def test_validate_schema_missing_required_field() -> None:
    """Test validation fails for missing required fields."""
    workflow_dict = {
        "version": "1.0",
        # Missing 'name'
        "steps": [
            {
                "name": "step1",
                "type": "python",
                "action": "my_action",
            }
        ],
    }
    with pytest.raises(WorkflowParseError) as exc_info:
        validate_schema(workflow_dict)
    assert "name" in str(exc_info.value).lower()


def test_validate_schema_invalid_type() -> None:
    """Test validation fails for invalid field types."""
    workflow_dict = {
        "version": "1.0",
        "name": "test-workflow",
        "steps": "not-a-list",  # Should be a list
    }
    with pytest.raises(WorkflowParseError) as exc_info:
        validate_schema(workflow_dict)
    assert "steps" in str(exc_info.value).lower()


def test_validate_schema_invalid_version_format() -> None:
    """Test validation fails for invalid version format."""
    workflow_dict = {
        "version": "1",  # Should be "1.0" format
        "name": "test-workflow",
        "steps": [
            {
                "name": "step1",
                "type": "python",
                "action": "my_action",
            }
        ],
    }
    with pytest.raises(WorkflowParseError) as exc_info:
        validate_schema(workflow_dict)
    assert "version" in str(exc_info.value).lower()


def test_validate_schema_invalid_workflow_name() -> None:
    """Test validation fails for invalid workflow name format."""
    workflow_dict = {
        "version": "1.0",
        "name": "Invalid_Name",  # Uppercase not allowed
        "steps": [
            {
                "name": "step1",
                "type": "python",
                "action": "my_action",
            }
        ],
    }
    with pytest.raises(WorkflowParseError) as exc_info:
        validate_schema(workflow_dict)
    assert "name" in str(exc_info.value).lower()


def test_validate_schema_duplicate_step_names() -> None:
    """Test validation fails for duplicate step names."""
    workflow_dict = {
        "version": "1.0",
        "name": "test-workflow",
        "steps": [
            {
                "name": "step1",
                "type": "python",
                "action": "action1",
            },
            {
                "name": "step1",  # Duplicate
                "type": "python",
                "action": "action2",
            },
        ],
    }
    with pytest.raises(WorkflowParseError) as exc_info:
        validate_schema(workflow_dict)
    assert "duplicate" in str(exc_info.value).lower()
    assert "step1" in str(exc_info.value)


def test_validate_schema_empty_steps() -> None:
    """Test validation fails when steps list is empty."""
    workflow_dict = {
        "version": "1.0",
        "name": "test-workflow",
        "steps": [],
    }
    with pytest.raises(WorkflowParseError) as exc_info:
        validate_schema(workflow_dict)
    assert "steps" in str(exc_info.value).lower()


# =============================================================================
# T034: validate_version Tests
# =============================================================================


def test_validate_version_supported() -> None:
    """Test validating a supported version."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "my_action",
            }
        ],
    )
    # Should not raise
    validate_version(workflow)


def test_validate_version_unsupported_future() -> None:
    """Test validation fails for future unsupported version."""
    workflow = WorkflowFile(
        version="2.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "my_action",
            }
        ],
    )
    with pytest.raises(UnsupportedVersionError) as exc_info:
        validate_version(workflow)
    assert exc_info.value.requested_version == "2.0"
    assert "1.0" in exc_info.value.supported_versions


def test_validate_version_unsupported_legacy() -> None:
    """Test validation fails for legacy unsupported version."""
    workflow = WorkflowFile(
        version="0.9",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "my_action",
            }
        ],
    )
    with pytest.raises(UnsupportedVersionError) as exc_info:
        validate_version(workflow)
    assert exc_info.value.requested_version == "0.9"
    assert "1.0" in exc_info.value.supported_versions


# =============================================================================
# T035-T036: extract_expressions Tests
# =============================================================================


def test_extract_expressions_from_workflow() -> None:
    """Test extracting all expressions from a workflow."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        inputs={
            "dry_run": {
                "type": "boolean",
                "required": False,
                "default": False,
            }
        },
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "my_action",
                "kwargs": {
                    "flag": "${{ inputs.dry_run }}",
                    "data": "${{ steps.previous.output }}",
                },
            },
            {
                "name": "step2",
                "type": "agent",
                "agent": "my_agent",
                "context": {
                    "value": "${{ inputs.value }}",
                },
                "when": "${{ not inputs.skip }}",
            },
        ],
    )

    expressions = extract_expressions(workflow)
    assert len(expressions) >= 4

    # Verify expression content
    raw_exprs = [e.raw for e in expressions]
    assert "${{ inputs.dry_run }}" in raw_exprs
    assert "${{ steps.previous.output }}" in raw_exprs
    assert "${{ inputs.value }}" in raw_exprs
    assert "${{ not inputs.skip }}" in raw_exprs


def test_extract_expressions_nested_structures() -> None:
    """Test extracting expressions from nested dicts and lists."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "my_action",
                "args": [
                    "${{ inputs.arg1 }}",
                    {
                        "nested": "${{ inputs.arg2 }}",
                    },
                ],
            }
        ],
    )

    expressions = extract_expressions(workflow)
    raw_exprs = [e.raw for e in expressions]
    assert "${{ inputs.arg1 }}" in raw_exprs
    assert "${{ inputs.arg2 }}" in raw_exprs


def test_extract_expressions_none_found() -> None:
    """Test extracting expressions when there are none."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "my_action",
                "kwargs": {"static": "value"},
            }
        ],
    )

    expressions = extract_expressions(workflow)
    assert expressions == []


def test_extract_expressions_validates_syntax() -> None:
    """Test that invalid expressions raise ExpressionSyntaxError."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "my_action",
                "kwargs": {
                    "bad": "${{ invalid.reference }}",  # Not inputs/steps
                },
            }
        ],
    )

    with pytest.raises(ExpressionSyntaxError):
        extract_expressions(workflow)


# =============================================================================
# T037-T039: resolve_references Tests
# =============================================================================


def test_resolve_references_valid_action(component_reg: ComponentRegistry) -> None:
    """Test resolving valid action references."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "validate_files",
            }
        ],
    )

    # Should not raise
    resolve_references(workflow, component_reg)


def test_resolve_references_invalid_action(component_reg: ComponentRegistry) -> None:
    """Test resolving invalid action reference raises error."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "unknown_action",
            }
        ],
    )

    with pytest.raises(ReferenceResolutionError) as exc_info:
        resolve_references(workflow, component_reg)
    assert exc_info.value.reference_type == "action"
    assert exc_info.value.reference_name == "unknown_action"


def test_resolve_references_valid_generator(component_reg: ComponentRegistry) -> None:
    """Test resolving valid generator references."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "generate",
                "generator": "code_reviewer",
            }
        ],
    )

    # Should not raise
    resolve_references(workflow, component_reg)


def test_resolve_references_invalid_generator(component_reg: ComponentRegistry) -> None:
    """Test resolving invalid generator reference raises error."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "generate",
                "generator": "unknown_generator",
            }
        ],
    )

    with pytest.raises(ReferenceResolutionError) as exc_info:
        resolve_references(workflow, component_reg)
    assert exc_info.value.reference_type == "generator"
    assert exc_info.value.reference_name == "unknown_generator"


def test_resolve_references_context_builder(component_reg: ComponentRegistry) -> None:
    """Test resolving context builder references."""

    # Register a context builder (with validation disabled for test fixture)
    def build_context() -> dict[str, Any]:
        return {"key": "value"}

    component_reg.context_builders.register("my_context", build_context, validate=False)

    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "agent",
                "agent": "code_reviewer",
                "context": "my_context",  # String reference to context builder
            }
        ],
    )

    # Should not raise
    resolve_references(workflow, component_reg)


def test_resolve_references_invalid_context_builder(
    component_reg: ComponentRegistry,
) -> None:
    """Test resolving invalid context builder reference raises error."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "agent",
                "agent": "code_reviewer",
                "context": "unknown_context",
            }
        ],
    )

    with pytest.raises(ReferenceResolutionError) as exc_info:
        resolve_references(workflow, component_reg)
    assert exc_info.value.reference_type == "context_builder"
    assert exc_info.value.reference_name == "unknown_context"


def test_resolve_references_subworkflow(component_reg: ComponentRegistry) -> None:
    """Test resolving sub-workflow references."""
    # Register a workflow
    sub_workflow = WorkflowFile(
        version="1.0",
        name="sub-workflow",
        steps=[
            {
                "name": "substep1",
                "type": "python",
                "action": "validate_files",
            }
        ],
    )
    component_reg.workflows.register("sub-workflow", sub_workflow)

    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "subworkflow",
                "workflow": "sub-workflow",
            }
        ],
    )

    # Should not raise
    resolve_references(workflow, component_reg)


def test_resolve_references_invalid_subworkflow(
    component_reg: ComponentRegistry,
) -> None:
    """Test resolving invalid sub-workflow reference raises error."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "subworkflow",
                "workflow": "unknown-workflow",
            }
        ],
    )

    with pytest.raises(ReferenceResolutionError) as exc_info:
        resolve_references(workflow, component_reg)
    assert exc_info.value.reference_type == "workflow"
    assert exc_info.value.reference_name == "unknown-workflow"


def test_resolve_references_nested_steps(component_reg: ComponentRegistry) -> None:
    """Test resolving references in nested step structures (branch, loop)."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "loop_step",
                "type": "loop",
                "steps": [
                    {
                        "name": "sub1",
                        "type": "python",
                        "action": "validate_files",
                    },
                    {
                        "name": "sub2",
                        "type": "generate",
                        "generator": "code_reviewer",
                    },
                ],
            }
        ],
    )

    # Should not raise
    resolve_references(workflow, component_reg)


def test_resolve_references_branch_steps(component_reg: ComponentRegistry) -> None:
    """Test resolving references in branch step options."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "branch_step",
                "type": "branch",
                "options": [
                    {
                        "when": "${{ inputs.use_action }}",
                        "step": {
                            "name": "option1",
                            "type": "python",
                            "action": "validate_files",
                        },
                    },
                    {
                        "when": "${{ not inputs.use_action }}",
                        "step": {
                            "name": "option2",
                            "type": "generate",
                            "generator": "code_reviewer",
                        },
                    },
                ],
            }
        ],
    )

    # Should not raise
    resolve_references(workflow, component_reg)


def test_resolve_references_lenient_mode() -> None:
    """Test that lenient mode defers resolution errors."""
    lenient_registry = ComponentRegistry(strict=False)

    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "unknown_action",  # Not registered
            }
        ],
    )

    # In lenient mode, should not raise
    resolve_references(workflow, lenient_registry)


# =============================================================================
# T032-T039: parse_workflow Integration Tests
# =============================================================================


def test_parse_workflow_valid(
    valid_workflow_yaml: str, component_reg: ComponentRegistry
) -> None:
    """Test parsing a complete valid workflow."""
    workflow = parse_workflow(valid_workflow_yaml, component_reg)
    assert isinstance(workflow, WorkflowFile)
    assert workflow.name == "test-workflow"
    assert workflow.version == "1.0"
    assert len(workflow.steps) == 2


def test_parse_workflow_yaml_error() -> None:
    """Test parse_workflow with invalid YAML."""
    invalid_yaml = """
version: "1.0"
name: [unclosed
"""
    with pytest.raises(WorkflowParseError):
        parse_workflow(invalid_yaml)


def test_parse_workflow_schema_error() -> None:
    """Test parse_workflow with schema validation error."""
    yaml_content = """
version: "1.0"
# Missing required 'name' field
steps:
  - name: step1
    type: python
    action: my_action
"""
    with pytest.raises(WorkflowParseError):
        parse_workflow(yaml_content)


def test_parse_workflow_version_error() -> None:
    """Test parse_workflow with unsupported version."""
    yaml_content = """
version: "2.0"
name: test-workflow
steps:
  - name: step1
    type: python
    action: my_action
"""
    with pytest.raises(UnsupportedVersionError):
        parse_workflow(yaml_content)


def test_parse_workflow_expression_error() -> None:
    """Test parse_workflow with invalid expression syntax."""
    yaml_content = """
version: "1.0"
name: test-workflow
steps:
  - name: step1
    type: python
    action: my_action
    kwargs:
      bad: ${{ invalid.path }}
"""
    with pytest.raises(ExpressionSyntaxError):
        parse_workflow(yaml_content)


def test_parse_workflow_reference_error(component_reg: ComponentRegistry) -> None:
    """Test parse_workflow with unresolved reference (via semantic validation)."""
    yaml_content = """
version: "1.0"
name: test-workflow
steps:
  - name: step1
    type: python
    action: unknown_action
"""
    # Semantic validation catches the missing action as WorkflowParseError
    with pytest.raises(WorkflowParseError, match="unknown_action"):
        parse_workflow(yaml_content, component_reg)


def test_parse_workflow_without_registry() -> None:
    """Test parse_workflow without registry (no reference resolution)."""
    yaml_content = """
version: "1.0"
name: test-workflow
steps:
  - name: step1
    type: python
    action: my_action
"""
    workflow = parse_workflow(yaml_content, registry=None)
    assert isinstance(workflow, WorkflowFile)
    assert workflow.name == "test-workflow"


def test_parse_workflow_validate_only_mode(component_reg: ComponentRegistry) -> None:
    """Test parse_workflow in validate_only mode (skips reference resolution)."""
    yaml_content = """
version: "1.0"
name: test-workflow
steps:
  - name: step1
    type: python
    action: unknown_action
"""
    # With validate_semantic=False, should not raise for unknown refs
    workflow = parse_workflow(
        yaml_content, component_reg, validate_only=True, validate_semantic=False
    )
    assert isinstance(workflow, WorkflowFile)


def test_parse_workflow_lenient_mode() -> None:
    """Test parse_workflow with lenient registry mode."""
    lenient_registry = ComponentRegistry(strict=False)

    yaml_content = """
version: "1.0"
name: test-workflow
steps:
  - name: step1
    type: python
    action: unknown_action
"""
    # In lenient mode with validate_semantic=False, should not raise for unknown refs
    workflow = parse_workflow(yaml_content, lenient_registry, validate_semantic=False)
    assert isinstance(workflow, WorkflowFile)


def test_parse_workflow_complex_nested_structure(
    component_reg: ComponentRegistry,
) -> None:
    """Test parsing workflow with complex nested structures."""
    yaml_content = """
version: "1.0"
name: test-workflow
inputs:
  dry_run:
    type: boolean
    required: false
    default: false
steps:
  - name: loop_tasks
    type: loop
    steps:
      - name: task1
        type: python
        action: validate_files
      - name: task2
        type: generate
        generator: code_reviewer
  - name: conditional
    type: branch
    options:
      - when: ${{ inputs.dry_run }}
        step:
          name: dry_run_step
          type: python
          action: validate_files
      - when: ${{ not inputs.dry_run }}
        step:
          name: real_step
          type: python
          action: validate_files
"""
    workflow = parse_workflow(yaml_content, component_reg)
    assert isinstance(workflow, WorkflowFile)
    assert len(workflow.steps) == 2
