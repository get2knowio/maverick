"""Tests for semantic workflow validation (FR-017 enhancement).

This module tests the WorkflowSemanticValidator class, which provides
comprehensive semantic validation beyond syntactic schema validation.

Test coverage:
- Component reference validation (actions, agents, generators, context builders,
  workflows)
- Expression syntax validation in all step types
- Step name reference validation in expressions
- Circular dependency detection
- Input usage analysis (unused inputs, missing required inputs)
"""

from __future__ import annotations

from typing import Any

import pytest

from maverick.agents.base import MaverickAgent
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import WorkflowFile
from maverick.dsl.serialization.validation import (
    WorkflowSemanticValidator,
    validate_workflow_semantics,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def registry() -> ComponentRegistry:
    """Create a ComponentRegistry with test components."""
    reg = ComponentRegistry(strict=True)

    # Register test action
    def test_action(arg: str) -> str:
        return arg

    reg.actions.register("test_action", test_action)

    # Register test agent (valid MaverickAgent subclass)
    class TestAgent(MaverickAgent[dict[str, Any], str]):
        """A valid agent for testing."""

        def __init__(self) -> None:
            super().__init__(
                name="test_agent",
                system_prompt="Test agent",
                allowed_tools=[],
            )

        async def execute(self, context: dict[str, Any]) -> str:
            return "test result"

    # Register test generator (same class, different name)
    class TestGenerator(MaverickAgent[dict[str, Any], str]):
        """A valid generator for testing."""

        def __init__(self) -> None:
            super().__init__(
                name="test_generator",
                system_prompt="Test generator",
                allowed_tools=[],
            )

        async def execute(self, context: dict[str, Any]) -> str:
            return "generated content"

    # Register in appropriate registries (validate=False for test mocks)
    reg.agents.register("test_agent", TestAgent, validate=False)
    reg.generators.register("test_generator", TestGenerator, validate=False)

    # Register test context builder (requires 2 params: inputs, step_results)
    def test_context(
        inputs: dict[str, Any], step_results: dict[str, Any]
    ) -> dict[str, Any]:
        return {"key": "value", "inputs": inputs}

    reg.context_builders.register("test_context", test_context)

    return reg


# =============================================================================
# Component Reference Validation Tests
# =============================================================================


def test_validate_component_references_valid(registry: ComponentRegistry) -> None:
    """Test validation passes for valid component references."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "test_action",
            },
            {
                "name": "step2",
                "type": "agent",
                "agent": "test_agent",
            },
            {
                "name": "step3",
                "type": "generate",
                "generator": "test_generator",
            },
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert result.valid
    assert len(result.errors) == 0


def test_validate_component_references_invalid_action(
    registry: ComponentRegistry,
) -> None:
    """Test validation fails for invalid action reference."""
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

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid
    assert len(result.errors) == 1
    assert result.errors[0].code == "E001"
    assert "unknown_action" in result.errors[0].message
    assert result.errors[0].path == "steps[0].action"
    assert "test_action" in result.errors[0].suggestion


def test_validate_component_references_invalid_agent(
    registry: ComponentRegistry,
) -> None:
    """Test validation fails for invalid agent reference."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "agent",
                "agent": "unknown_agent",
            }
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid
    assert len(result.errors) == 1
    assert result.errors[0].code == "E002"
    assert "unknown_agent" in result.errors[0].message


def test_validate_component_references_invalid_generator(
    registry: ComponentRegistry,
) -> None:
    """Test validation fails for invalid generator reference."""
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

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid
    assert len(result.errors) == 1
    assert result.errors[0].code == "E004"
    assert "unknown_generator" in result.errors[0].message


def test_validate_component_references_invalid_context_builder(
    registry: ComponentRegistry,
) -> None:
    """Test validation fails for invalid context builder reference."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "agent",
                "agent": "test_agent",
                "context": "unknown_context",  # String reference
            }
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid
    assert len(result.errors) == 1
    assert result.errors[0].code == "E003"
    assert "unknown_context" in result.errors[0].message


def test_validate_component_references_invalid_subworkflow(
    registry: ComponentRegistry,
) -> None:
    """Test validation fails for invalid subworkflow reference."""
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

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid
    assert len(result.errors) == 1
    assert result.errors[0].code == "E005"
    assert "unknown-workflow" in result.errors[0].message


def test_validate_component_references_nested_steps(
    registry: ComponentRegistry,
) -> None:
    """Test validation checks nested steps (branch, parallel, validate)."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "parallel_step",
                "type": "parallel",
                "steps": [
                    {
                        "name": "sub1",
                        "type": "python",
                        "action": "unknown_action",  # Invalid
                    },
                    {
                        "name": "sub2",
                        "type": "python",
                        "action": "test_action",  # Valid
                    },
                ],
            }
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid
    assert len(result.errors) == 1
    assert result.errors[0].code == "E001"
    assert "steps[0].steps[0].action" in result.errors[0].path


# =============================================================================
# Expression Syntax Validation Tests
# =============================================================================


def test_validate_expressions_valid(registry: ComponentRegistry) -> None:
    """Test validation passes for valid expressions."""
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
                "action": "test_action",
                "args": ["${{ inputs.dry_run }}"],
            }
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert result.valid
    assert len(result.errors) == 0


def test_validate_expressions_invalid_syntax(registry: ComponentRegistry) -> None:
    """Test validation fails for invalid expression syntax."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "test_action",
                "kwargs": {
                    "bad": "${{ invalid.reference }}",  # Not inputs/steps
                },
            }
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid
    assert len(result.errors) >= 1
    assert result.errors[0].code == "E006"
    assert "expression syntax" in result.errors[0].message.lower()


def test_validate_expressions_empty_expression(registry: ComponentRegistry) -> None:
    """Test validation fails for empty expressions."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "test_action",
                "kwargs": {
                    "bad": "${{ }}",  # Empty expression
                },
            }
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid
    assert len(result.errors) >= 1
    assert result.errors[0].code == "E006"


def test_validate_expressions_in_nested_steps(registry: ComponentRegistry) -> None:
    """Test expression validation in nested step structures."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "branch_step",
                "type": "branch",
                "options": [
                    {
                        "when": "${{ invalid.expr }}",  # Invalid
                        "step": {
                            "name": "option1",
                            "type": "python",
                            "action": "test_action",
                        },
                    }
                ],
            }
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid
    assert any(err.code == "E006" for err in result.errors)


# =============================================================================
# Step Reference Validation Tests
# =============================================================================


def test_validate_step_references_valid(registry: ComponentRegistry) -> None:
    """Test validation passes for valid step references."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "test_action",
            },
            {
                "name": "step2",
                "type": "python",
                "action": "test_action",
                "args": ["${{ steps.step1.output }}"],  # Valid reference
            },
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert result.valid
    assert len(result.errors) == 0


def test_validate_step_references_invalid(registry: ComponentRegistry) -> None:
    """Test validation fails for invalid step references."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "test_action",
                "args": ["${{ steps.nonexistent.output }}"],  # Invalid
            }
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid
    assert len(result.errors) >= 1
    assert any(err.code == "E007" for err in result.errors)
    assert any("nonexistent" in err.message for err in result.errors)


def test_validate_step_references_nested_output(registry: ComponentRegistry) -> None:
    """Test validation passes for nested output references."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "test_action",
            },
            {
                "name": "step2",
                "type": "python",
                "action": "test_action",
                "args": ["${{ steps.step1.output.field }}"],  # Nested field
            },
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    # Should pass - we validate step name exists, not nested fields
    assert result.valid


def test_validate_step_references_in_conditionals(
    registry: ComponentRegistry,
) -> None:
    """Test validation checks step references in when conditions."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "test_action",
            },
            {
                "name": "step2",
                "type": "python",
                "action": "test_action",
                "when": "${{ steps.nonexistent.output }}",  # Invalid
            },
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid
    assert any(err.code == "E007" for err in result.errors)


# =============================================================================
# Circular Dependency Detection Tests
# =============================================================================


def test_validate_no_cycles_valid(registry: ComponentRegistry) -> None:
    """Test validation passes for workflows without circular dependencies."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "test_action",
            },
            {
                "name": "step2",
                "type": "python",
                "action": "test_action",
                "args": ["${{ steps.step1.output }}"],  # step2 -> step1 (valid)
            },
            {
                "name": "step3",
                "type": "python",
                "action": "test_action",
                "args": ["${{ steps.step2.output }}"],  # step3 -> step2 (valid)
            },
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert result.valid
    assert len(result.errors) == 0


def test_validate_no_cycles_detects_direct_cycle(
    registry: ComponentRegistry,
) -> None:
    """Test validation detects direct circular dependency (A -> A)."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "test_action",
                "args": ["${{ steps.step1.output }}"],  # Self-reference
            }
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid
    assert any(err.code == "E008" for err in result.errors)
    assert any("circular" in err.message.lower() for err in result.errors)


def test_validate_no_cycles_detects_indirect_cycle(
    registry: ComponentRegistry,
) -> None:
    """Test validation detects indirect circular dependency (A -> B -> A)."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "test_action",
                "args": ["${{ steps.step2.output }}"],  # step1 -> step2
            },
            {
                "name": "step2",
                "type": "python",
                "action": "test_action",
                "args": ["${{ steps.step1.output }}"],  # step2 -> step1 (cycle!)
            },
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid
    assert any(err.code == "E008" for err in result.errors)
    assert any("circular" in err.message.lower() for err in result.errors)


def test_validate_no_cycles_detects_complex_cycle(
    registry: ComponentRegistry,
) -> None:
    """Test validation detects complex circular dependency (A -> B -> C -> A)."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "test_action",
                "args": ["${{ steps.step2.output }}"],  # step1 -> step2
            },
            {
                "name": "step2",
                "type": "python",
                "action": "test_action",
                "args": ["${{ steps.step3.output }}"],  # step2 -> step3
            },
            {
                "name": "step3",
                "type": "python",
                "action": "test_action",
                "args": ["${{ steps.step1.output }}"],  # step3 -> step1 (cycle!)
            },
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid
    assert any(err.code == "E008" for err in result.errors)
    # Verify cycle path is in error message
    assert any("step1" in err.message for err in result.errors if err.code == "E008")


# =============================================================================
# Input Usage Validation Tests
# =============================================================================


def test_validate_input_usage_all_used(registry: ComponentRegistry) -> None:
    """Test validation passes when all inputs are used."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        inputs={
            "dry_run": {
                "type": "boolean",
                "required": False,
                "default": False,
            },
            "branch": {
                "type": "string",
                "required": True,
            },
        },
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "test_action",
                "args": ["${{ inputs.dry_run }}"],
            },
            {
                "name": "step2",
                "type": "python",
                "action": "test_action",
                "when": "${{ inputs.branch }}",
            },
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert result.valid
    assert len(result.warnings) == 0


def test_validate_input_usage_unused_input_warning(
    registry: ComponentRegistry,
) -> None:
    """Test validation warns about unused inputs."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        inputs={
            "dry_run": {
                "type": "boolean",
                "required": False,
                "default": False,
            },
            "unused_input": {
                "type": "string",
                "required": False,
                "default": "unused",
            },
        },
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "test_action",
                "args": ["${{ inputs.dry_run }}"],  # Only use dry_run
            }
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    # Valid but with warning
    assert result.valid
    assert len(result.warnings) == 1
    assert result.warnings[0].code == "W001"
    assert "unused_input" in result.warnings[0].message


def test_validate_input_usage_in_nested_steps(registry: ComponentRegistry) -> None:
    """Test validation tracks input usage in nested steps."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        inputs={
            "flag": {
                "type": "boolean",
                "required": False,
                "default": False,
            }
        },
        steps=[
            {
                "name": "parallel_step",
                "type": "parallel",
                "steps": [
                    {
                        "name": "sub1",
                        "type": "python",
                        "action": "test_action",
                        "when": "${{ inputs.flag }}",  # Used in nested step
                    }
                ],
            }
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    # Should not warn - input is used in nested step
    assert result.valid
    assert len(result.warnings) == 0


# =============================================================================
# Integration Tests
# =============================================================================


def test_validate_workflow_semantics_convenience_function(
    registry: ComponentRegistry,
) -> None:
    """Test the convenience function validate_workflow_semantics."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "unknown_action",  # Invalid
            }
        ],
    )

    result = validate_workflow_semantics(workflow, registry)

    assert not result.valid
    assert len(result.errors) >= 1
    assert result.errors[0].code == "E001"


def test_validate_multiple_errors(registry: ComponentRegistry) -> None:
    """Test validation reports multiple errors."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "unknown_action",  # Error 1: invalid action
                "kwargs": {
                    "bad": "${{ invalid.ref }}",  # Error 2: invalid expression
                },
            },
            {
                "name": "step2",
                "type": "agent",
                "agent": "unknown_agent",  # Error 3: invalid agent
            },
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid
    assert len(result.errors) >= 3

    # Check we have errors for each issue
    error_codes = {err.code for err in result.errors}
    assert "E001" in error_codes  # Invalid action
    assert "E002" in error_codes  # Invalid agent
    assert "E006" in error_codes  # Invalid expression


def test_validate_errors_and_warnings(registry: ComponentRegistry) -> None:
    """Test validation can return both errors and warnings."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        inputs={
            "unused": {
                "type": "string",
                "required": False,
                "default": "value",
            }
        },
        steps=[
            {
                "name": "step1",
                "type": "python",
                "action": "unknown_action",  # Error
            }
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert not result.valid  # Errors make it invalid
    assert len(result.errors) >= 1
    assert len(result.warnings) >= 1  # Unused input warning


def test_validate_valid_workflow_complex(registry: ComponentRegistry) -> None:
    """Test validation passes for a complex valid workflow."""
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
                "action": "test_action",
                "args": ["${{ inputs.dry_run }}"],
            },
            {
                "name": "step2",
                "type": "agent",
                "agent": "test_agent",
                "context": "test_context",
                "when": "${{ steps.step1.output }}",
            },
            {
                "name": "step3",
                "type": "parallel",
                "steps": [
                    {
                        "name": "sub1",
                        "type": "python",
                        "action": "test_action",
                    },
                    {
                        "name": "sub2",
                        "type": "generate",
                        "generator": "test_generator",
                    },
                ],
            },
        ],
    )

    validator = WorkflowSemanticValidator(registry)
    result = validator.validate(workflow)

    assert result.valid
    assert len(result.errors) == 0
    assert len(result.warnings) == 0
