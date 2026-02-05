"""Unit tests for workflow writer (serialization to YAML/JSON/dict).

This module contains TDD tests for workflow serialization:
- WorkflowWriter.to_dict(): Convert WorkflowFile to dict
- WorkflowWriter.to_yaml(): Convert WorkflowFile to YAML string
- WorkflowWriter.to_json(): Convert WorkflowFile to JSON string

Tests are written before implementation following TDD principles.

Test scenarios:
1. to_dict produces valid dict
2. to_yaml produces valid YAML
3. to_json produces valid JSON
4. Expression values preserved correctly (${{ ... }})
5. All step types serialized correctly
6. Nested structures (parallel, branch, on_failure) serialized correctly
7. Field ordering is preserved for readability
"""

from __future__ import annotations

import json

import yaml

from maverick.dsl.serialization.schema import (
    AgentStepRecord,
    BranchOptionRecord,
    BranchStepRecord,
    GenerateStepRecord,
    InputDefinition,
    InputType,
    LoopStepRecord,
    PythonStepRecord,
    SubWorkflowStepRecord,
    ValidateStepRecord,
    WorkflowFile,
)
from maverick.dsl.serialization.writer import WorkflowWriter
from maverick.dsl.types import StepType

# =============================================================================
# Basic to_dict Tests
# =============================================================================


class TestWorkflowWriterToDict:
    """Test suite for WorkflowWriter.to_dict()."""

    def test_minimal_workflow_to_dict(self) -> None:
        """Test converting minimal workflow to dict."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        assert isinstance(result, dict)
        assert result["version"] == "1.0"
        assert result["name"] == "test-workflow"
        assert "steps" in result
        assert len(result["steps"]) == 1
        assert result["steps"][0]["name"] == "step1"
        assert result["steps"][0]["type"] == "python"
        assert result["steps"][0]["action"] == "my_func"

    def test_workflow_with_description_to_dict(self) -> None:
        """Test converting workflow with description to dict."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            description="Test workflow description",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        assert result["description"] == "Test workflow description"

    def test_workflow_with_inputs_to_dict(self) -> None:
        """Test converting workflow with inputs to dict."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            inputs={
                "repo_name": InputDefinition(
                    type=InputType.STRING,
                    required=True,
                    description="Repository name",
                ),
                "dry_run": InputDefinition(
                    type=InputType.BOOLEAN,
                    required=False,
                    default=False,
                    description="Dry run mode",
                ),
            },
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        assert "inputs" in result
        assert "repo_name" in result["inputs"]
        assert result["inputs"]["repo_name"]["type"] == "string"
        assert result["inputs"]["repo_name"]["required"] is True
        assert result["inputs"]["repo_name"]["description"] == "Repository name"

        assert "dry_run" in result["inputs"]
        assert result["inputs"]["dry_run"]["type"] == "boolean"
        assert result["inputs"]["dry_run"]["required"] is False
        assert result["inputs"]["dry_run"]["default"] is False


# =============================================================================
# Step Type Serialization Tests
# =============================================================================


class TestWorkflowWriterStepTypes:
    """Test suite for serializing different step types."""

    def test_python_step_to_dict(self) -> None:
        """Test serializing PythonStepRecord."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_module.my_func",
                    args=["arg1", 42],
                    kwargs={"key": "value"},
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        step = result["steps"][0]
        assert step["type"] == "python"
        assert step["action"] == "my_module.my_func"
        assert step["args"] == ["arg1", 42]
        assert step["kwargs"] == {"key": "value"}

    def test_agent_step_to_dict(self) -> None:
        """Test serializing AgentStepRecord."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                AgentStepRecord(
                    name="review",
                    type=StepType.AGENT,
                    agent="code_reviewer",
                    context={"files": ["main.py"]},
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        step = result["steps"][0]
        assert step["type"] == "agent"
        assert step["agent"] == "code_reviewer"
        assert step["context"] == {"files": ["main.py"]}

    def test_generate_step_to_dict(self) -> None:
        """Test serializing GenerateStepRecord."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                GenerateStepRecord(
                    name="describe",
                    type=StepType.GENERATE,
                    generator="pr_description",
                    context={"changes": "..."},
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        step = result["steps"][0]
        assert step["type"] == "generate"
        assert step["generator"] == "pr_description"
        assert step["context"] == {"changes": "..."}

    def test_validate_step_to_dict(self) -> None:
        """Test serializing ValidateStepRecord."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                ValidateStepRecord(
                    name="validate",
                    type=StepType.VALIDATE,
                    stages=["format", "lint", "test"],
                    retry=3,
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        step = result["steps"][0]
        assert step["type"] == "validate"
        assert step["stages"] == ["format", "lint", "test"]
        assert step["retry"] == 3

    def test_validate_step_with_on_failure_to_dict(self) -> None:
        """Test serializing ValidateStepRecord with on_failure."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                ValidateStepRecord(
                    name="validate",
                    type=StepType.VALIDATE,
                    stages=["lint"],
                    retry=2,
                    on_failure=PythonStepRecord(
                        name="fix",
                        type=StepType.PYTHON,
                        action="auto_fix",
                    ),
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        step = result["steps"][0]
        assert step["type"] == "validate"
        assert "on_failure" in step
        assert step["on_failure"]["name"] == "fix"
        assert step["on_failure"]["type"] == "python"
        assert step["on_failure"]["action"] == "auto_fix"

    def test_subworkflow_step_to_dict(self) -> None:
        """Test serializing SubWorkflowStepRecord."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                SubWorkflowStepRecord(
                    name="nested",
                    type=StepType.SUBWORKFLOW,
                    workflow="other_workflow",
                    inputs={"data": "value"},
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        step = result["steps"][0]
        assert step["type"] == "subworkflow"
        assert step["workflow"] == "other_workflow"
        assert step["inputs"] == {"data": "value"}

    def test_branch_step_to_dict(self) -> None:
        """Test serializing BranchStepRecord."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                BranchStepRecord(
                    name="route",
                    type=StepType.BRANCH,
                    options=[
                        BranchOptionRecord(
                            when="${{ inputs.type == 'a' }}",
                            step=PythonStepRecord(
                                name="handle_a",
                                type=StepType.PYTHON,
                                action="handle_a",
                            ),
                        ),
                        BranchOptionRecord(
                            when="${{ inputs.type == 'b' }}",
                            step=PythonStepRecord(
                                name="handle_b",
                                type=StepType.PYTHON,
                                action="handle_b",
                            ),
                        ),
                    ],
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        step = result["steps"][0]
        assert step["type"] == "branch"
        assert len(step["options"]) == 2
        assert step["options"][0]["when"] == "${{ inputs.type == 'a' }}"
        assert step["options"][0]["step"]["name"] == "handle_a"
        assert step["options"][1]["when"] == "${{ inputs.type == 'b' }}"
        assert step["options"][1]["step"]["name"] == "handle_b"

    def test_loop_step_to_dict(self) -> None:
        """Test serializing LoopStepRecord."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                LoopStepRecord(
                    name="parallel_tasks",
                    type=StepType.LOOP,
                    steps=[
                        PythonStepRecord(
                            name="task1",
                            type=StepType.PYTHON,
                            action="task1",
                        ),
                        PythonStepRecord(
                            name="task2",
                            type=StepType.PYTHON,
                            action="task2",
                        ),
                    ],
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        step = result["steps"][0]
        assert step["type"] == "loop"
        assert len(step["steps"]) == 2
        assert step["steps"][0]["name"] == "task1"
        assert step["steps"][1]["name"] == "task2"

    def test_loop_step_with_parallel_true_to_dict(self) -> None:
        """Test serializing LoopStepRecord with parallel: true."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                LoopStepRecord(
                    name="parallel_tasks",
                    type=StepType.LOOP,
                    parallel=True,
                    steps=[
                        PythonStepRecord(
                            name="task1",
                            type=StepType.PYTHON,
                            action="task1",
                        ),
                    ],
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        step = result["steps"][0]
        assert step["type"] == "loop"
        assert step["parallel"] is True
        assert "max_concurrency" not in step

    def test_loop_step_with_parallel_false_to_dict(self) -> None:
        """Test serializing LoopStepRecord with parallel: false."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                LoopStepRecord(
                    name="parallel_tasks",
                    type=StepType.LOOP,
                    parallel=False,
                    steps=[
                        PythonStepRecord(
                            name="task1",
                            type=StepType.PYTHON,
                            action="task1",
                        ),
                    ],
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        step = result["steps"][0]
        assert step["type"] == "loop"
        assert step["parallel"] is False
        assert "max_concurrency" not in step

    def test_loop_step_with_max_concurrency_to_dict(self) -> None:
        """Test serializing LoopStepRecord with max_concurrency."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                LoopStepRecord(
                    name="parallel_tasks",
                    type=StepType.LOOP,
                    max_concurrency=3,
                    steps=[
                        PythonStepRecord(
                            name="task1",
                            type=StepType.PYTHON,
                            action="task1",
                        ),
                    ],
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        step = result["steps"][0]
        assert step["type"] == "loop"
        assert step["max_concurrency"] == 3
        assert "parallel" not in step

    def test_loop_step_with_for_each_to_dict(self) -> None:
        """Test serializing LoopStepRecord with for_each."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                LoopStepRecord(
                    name="process_items",
                    type=StepType.LOOP,
                    for_each="${{ inputs.items }}",
                    parallel=True,
                    steps=[
                        PythonStepRecord(
                            name="process",
                            type=StepType.PYTHON,
                            action="process",
                        ),
                    ],
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        step = result["steps"][0]
        assert step["type"] == "loop"
        assert step["for_each"] == "${{ inputs.items }}"
        assert step["parallel"] is True

    def test_loop_step_default_values_not_serialized(self) -> None:
        """Test that default values (sequential) are not serialized."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                LoopStepRecord(
                    name="parallel_tasks",
                    type=StepType.LOOP,
                    steps=[
                        PythonStepRecord(
                            name="task1",
                            type=StepType.PYTHON,
                            action="task1",
                        ),
                    ],
                    # parallel=None (default)
                    # max_concurrency=1 (default)
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        step = result["steps"][0]
        assert step["type"] == "loop"
        # Neither parallel nor max_concurrency should be in output when using defaults
        assert "parallel" not in step
        assert "max_concurrency" not in step


# =============================================================================
# Expression Preservation Tests
# =============================================================================


class TestWorkflowWriterExpressions:
    """Test suite for preserving expression syntax."""

    def test_expression_in_when_field(self) -> None:
        """Test that expression syntax is preserved in when field."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                    when="${{ inputs.enabled }}",
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        assert result["steps"][0]["when"] == "${{ inputs.enabled }}"

    def test_expression_in_args(self) -> None:
        """Test that expressions in args are preserved."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                    args=["${{ inputs.name }}", "${{ steps.prev.output }}"],
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        assert result["steps"][0]["args"] == [
            "${{ inputs.name }}",
            "${{ steps.prev.output }}",
        ]

    def test_expression_in_kwargs(self) -> None:
        """Test that expressions in kwargs are preserved."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                    kwargs={
                        "repo": "${{ inputs.repo_name }}",
                        "data": "${{ steps.fetch.output.data }}",
                    },
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        assert result["steps"][0]["kwargs"]["repo"] == "${{ inputs.repo_name }}"
        assert result["steps"][0]["kwargs"]["data"] == "${{ steps.fetch.output.data }}"

    def test_expression_in_context(self) -> None:
        """Test that expressions in context dict are preserved."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                AgentStepRecord(
                    name="review",
                    type=StepType.AGENT,
                    agent="reviewer",
                    context={
                        "files": "${{ steps.list_files.output }}",
                        "enabled": "${{ not inputs.skip }}",
                    },
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        step_context = result["steps"][0]["context"]
        assert step_context["files"] == "${{ steps.list_files.output }}"
        assert step_context["enabled"] == "${{ not inputs.skip }}"


# =============================================================================
# YAML Output Tests
# =============================================================================


class TestWorkflowWriterToYaml:
    """Test suite for WorkflowWriter.to_yaml()."""

    def test_minimal_workflow_to_yaml(self) -> None:
        """Test converting minimal workflow to YAML string."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_yaml(workflow)

        assert isinstance(result, str)
        # Verify it's valid YAML by parsing it
        parsed = yaml.safe_load(result)
        assert parsed["version"] == "1.0"
        assert parsed["name"] == "test-workflow"
        assert len(parsed["steps"]) == 1

    def test_yaml_output_is_valid(self) -> None:
        """Test that YAML output is valid and parseable."""
        workflow = WorkflowFile(
            version="1.0",
            name="complex-workflow",
            description="Test workflow",
            inputs={
                "repo": InputDefinition(
                    type=InputType.STRING,
                    required=True,
                )
            },
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="func",
                    args=["arg1"],
                )
            ],
        )

        writer = WorkflowWriter()
        yaml_str = writer.to_yaml(workflow)

        # Should be parseable
        parsed = yaml.safe_load(yaml_str)
        assert parsed is not None
        assert isinstance(parsed, dict)

    def test_yaml_preserves_expressions(self) -> None:
        """Test that YAML output preserves expression syntax."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                    when="${{ inputs.enabled }}",
                    args=["${{ inputs.name }}"],
                )
            ],
        )

        writer = WorkflowWriter()
        yaml_str = writer.to_yaml(workflow)

        # Parse and verify expressions are preserved
        parsed = yaml.safe_load(yaml_str)
        assert parsed["steps"][0]["when"] == "${{ inputs.enabled }}"
        assert parsed["steps"][0]["args"][0] == "${{ inputs.name }}"

    def test_yaml_output_human_readable(self) -> None:
        """Test that YAML output is human-readable (not inline)."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                )
            ],
        )

        writer = WorkflowWriter()
        yaml_str = writer.to_yaml(workflow)

        # Should contain newlines and proper indentation
        assert "\n" in yaml_str
        # Should not be inline JSON-like format
        assert yaml_str.count("\n") > 3  # Multiple lines for structure


# =============================================================================
# JSON Output Tests
# =============================================================================


class TestWorkflowWriterToJson:
    """Test suite for WorkflowWriter.to_json()."""

    def test_minimal_workflow_to_json(self) -> None:
        """Test converting minimal workflow to JSON string."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_json(workflow)

        assert isinstance(result, str)
        # Verify it's valid JSON by parsing it
        parsed = json.loads(result)
        assert parsed["version"] == "1.0"
        assert parsed["name"] == "test-workflow"
        assert len(parsed["steps"]) == 1

    def test_json_output_is_valid(self) -> None:
        """Test that JSON output is valid and parseable."""
        workflow = WorkflowFile(
            version="1.0",
            name="complex-workflow",
            description="Test workflow",
            inputs={
                "repo": InputDefinition(
                    type=InputType.STRING,
                    required=True,
                )
            },
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="func",
                    args=["arg1"],
                )
            ],
        )

        writer = WorkflowWriter()
        json_str = writer.to_json(workflow)

        # Should be parseable
        parsed = json.loads(json_str)
        assert parsed is not None
        assert isinstance(parsed, dict)

    def test_json_preserves_expressions(self) -> None:
        """Test that JSON output preserves expression syntax."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                    when="${{ inputs.enabled }}",
                    args=["${{ inputs.name }}"],
                )
            ],
        )

        writer = WorkflowWriter()
        json_str = writer.to_json(workflow)

        # Parse and verify expressions are preserved
        parsed = json.loads(json_str)
        assert parsed["steps"][0]["when"] == "${{ inputs.enabled }}"
        assert parsed["steps"][0]["args"][0] == "${{ inputs.name }}"

    def test_json_output_indented(self) -> None:
        """Test that JSON output is indented by default."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                )
            ],
        )

        writer = WorkflowWriter()
        json_str = writer.to_json(workflow)

        # Should contain newlines and indentation
        assert "\n" in json_str
        assert "  " in json_str  # Default 2-space indent

    def test_json_custom_indent(self) -> None:
        """Test that JSON output accepts custom indent."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                )
            ],
        )

        writer = WorkflowWriter()
        json_str = writer.to_json(workflow, indent=4)

        # Should use 4-space indent
        assert "    " in json_str

    def test_json_no_indent(self) -> None:
        """Test that JSON output can be compact (no indent)."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                )
            ],
        )

        writer = WorkflowWriter()
        json_str = writer.to_json(workflow, indent=None)

        # Should be compact (minimal whitespace)
        # Note: json.dumps with indent=None still adds some spaces
        lines = json_str.split("\n")
        assert len(lines) == 1  # Single line


# =============================================================================
# Edge Cases and Special Scenarios
# =============================================================================


class TestWorkflowWriterEdgeCases:
    """Test suite for edge cases and special scenarios."""

    def test_empty_lists_omitted_or_included(self) -> None:
        """Test handling of empty lists in steps."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                    args=[],  # Empty list
                    kwargs={},  # Empty dict
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        # Empty collections should be included (they're explicit)
        step = result["steps"][0]
        assert "args" in step
        assert "kwargs" in step
        assert step["args"] == []
        assert step["kwargs"] == {}

    def test_none_values_omitted(self) -> None:
        """Test that None values are omitted from output."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                    when=None,  # Optional field with None
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        # None values should be omitted
        step = result["steps"][0]
        assert "when" not in step

    def test_nested_expressions(self) -> None:
        """Test nested data structures with expressions."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                    kwargs={
                        "nested": {
                            "value": "${{ inputs.name }}",
                            "list": ["${{ steps.x.output }}", "static"],
                        }
                    },
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        nested = result["steps"][0]["kwargs"]["nested"]
        assert nested["value"] == "${{ inputs.name }}"
        assert nested["list"][0] == "${{ steps.x.output }}"

    def test_multiple_steps(self) -> None:
        """Test workflow with multiple different step types."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="func1",
                ),
                AgentStepRecord(
                    name="step2",
                    type=StepType.AGENT,
                    agent="agent1",
                ),
                ValidateStepRecord(
                    name="step3",
                    type=StepType.VALIDATE,
                    stages=["lint"],
                ),
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        assert len(result["steps"]) == 3
        assert result["steps"][0]["type"] == "python"
        assert result["steps"][1]["type"] == "agent"
        assert result["steps"][2]["type"] == "validate"

    def test_special_characters_in_strings(self) -> None:
        """Test handling of special characters in strings."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            description="Test with 'quotes' and \"double quotes\"",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="my_func",
                    args=["value with\nnewline", "value with\ttab"],
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        # Should preserve special characters
        assert "quotes" in result["description"]
        assert "value with\nnewline" in result["steps"][0]["args"]

        # YAML output should be valid
        yaml_str = writer.to_yaml(workflow)
        parsed = yaml.safe_load(yaml_str)
        assert parsed["description"] == workflow.description

    def test_context_as_string(self) -> None:
        """Test agent/generate steps with context as string (builder name)."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                AgentStepRecord(
                    name="review",
                    type=StepType.AGENT,
                    agent="reviewer",
                    context="review_context_builder",
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        assert result["steps"][0]["context"] == "review_context_builder"


# =============================================================================
# Field Ordering Tests
# =============================================================================


class TestWorkflowWriterFieldOrdering:
    """Test suite for field ordering in output."""

    def test_workflow_field_order(self) -> None:
        """Test that workflow fields are in logical order."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            description="Test",
            inputs={"repo": InputDefinition(type=InputType.STRING, required=True)},
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="func",
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        # Check that keys are in expected order
        keys = list(result.keys())
        # version and name should come first
        assert keys[0] == "version"
        assert keys[1] == "name"
        # description before inputs and steps
        assert keys.index("description") < keys.index("inputs")
        assert keys.index("inputs") < keys.index("steps")

    def test_step_field_order(self) -> None:
        """Test that step fields are in logical order."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="func",
                    when="${{ inputs.enabled }}",
                    args=["arg1"],
                    kwargs={"key": "value"},
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        step = result["steps"][0]
        keys = list(step.keys())
        # name and type should come first
        assert keys[0] == "name"
        assert keys[1] == "type"
        # when (if present) should come before action-specific fields
        if "when" in keys:
            assert keys.index("when") < keys.index("action")


# =============================================================================
# Complex Nested Structure Tests
# =============================================================================


class TestWorkflowWriterNestedStructures:
    """Test suite for complex nested structures."""

    def test_deeply_nested_branch(self) -> None:
        """Test branch step with nested steps inside options."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                BranchStepRecord(
                    name="outer_branch",
                    type=StepType.BRANCH,
                    options=[
                        BranchOptionRecord(
                            when="${{ inputs.type == 'a' }}",
                            step=LoopStepRecord(
                                name="parallel_a",
                                type=StepType.LOOP,
                                steps=[
                                    PythonStepRecord(
                                        name="task1",
                                        type=StepType.PYTHON,
                                        action="task1",
                                    ),
                                    PythonStepRecord(
                                        name="task2",
                                        type=StepType.PYTHON,
                                        action="task2",
                                    ),
                                ],
                            ),
                        ),
                    ],
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        # Verify nested structure is preserved
        branch = result["steps"][0]
        assert branch["type"] == "branch"
        nested_parallel = branch["options"][0]["step"]
        assert nested_parallel["type"] == "loop"
        assert len(nested_parallel["steps"]) == 2

    def test_validate_with_nested_on_failure(self) -> None:
        """Test validate step with complex on_failure step."""
        workflow = WorkflowFile(
            version="1.0",
            name="test-workflow",
            steps=[
                ValidateStepRecord(
                    name="validate",
                    type=StepType.VALIDATE,
                    stages=["lint"],
                    retry=2,
                    on_failure=BranchStepRecord(
                        name="fix_branch",
                        type=StepType.BRANCH,
                        options=[
                            BranchOptionRecord(
                                when="${{ true }}",
                                step=PythonStepRecord(
                                    name="auto_fix",
                                    type=StepType.PYTHON,
                                    action="fix",
                                ),
                            )
                        ],
                    ),
                )
            ],
        )

        writer = WorkflowWriter()
        result = writer.to_dict(workflow)

        validate = result["steps"][0]
        assert validate["type"] == "validate"
        on_failure = validate["on_failure"]
        assert on_failure["type"] == "branch"
        assert len(on_failure["options"]) == 1
