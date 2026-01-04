"""Integration tests for workflow serialization round-trip.

This module tests that workflows can be parsed from YAML, serialized back
to YAML/JSON, and re-parsed with semantic equivalence.

Round-trip scenarios:
1. Parse YAML -> Write YAML -> Parse YAML (should be equivalent)
2. Parse YAML -> Write JSON -> Parse JSON (should be equivalent)
3. Complex workflows with nested structures
4. Workflows with expressions
5. All step types

The goal is to ensure that:
- No data is lost during serialization
- Expressions are preserved correctly
- Nested structures maintain their integrity
- Field ordering is consistent and readable
"""

from __future__ import annotations

import json

import yaml

from maverick.dsl.serialization.parser import parse_workflow
from maverick.dsl.serialization.schema import WorkflowFile
from maverick.dsl.serialization.writer import WorkflowWriter


class TestWorkflowRoundtripBasic:
    """Test basic round-trip serialization scenarios."""

    def test_minimal_workflow_yaml_roundtrip(self) -> None:
        """Test round-trip for minimal workflow through YAML."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: step1
    type: python
    action: my_func
"""
        # Parse original
        workflow = parse_workflow(original_yaml)

        # Write to YAML
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)

        # Re-parse
        reparsed = parse_workflow(written_yaml)

        # Verify semantic equivalence
        assert reparsed.version == workflow.version
        assert reparsed.name == workflow.name
        assert len(reparsed.steps) == len(workflow.steps)
        assert reparsed.steps[0].name == workflow.steps[0].name
        assert reparsed.steps[0].type == workflow.steps[0].type

    def test_workflow_with_description_roundtrip(self) -> None:
        """Test round-trip for workflow with description."""
        original_yaml = """
version: "1.0"
name: test-workflow
description: This is a test workflow
steps:
  - name: step1
    type: python
    action: my_func
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)
        reparsed = parse_workflow(written_yaml)

        assert reparsed.description == workflow.description

    def test_workflow_with_inputs_roundtrip(self) -> None:
        """Test round-trip for workflow with input definitions."""
        original_yaml = """
version: "1.0"
name: test-workflow
inputs:
  repo_name:
    type: string
    required: true
    description: Repository name
  dry_run:
    type: boolean
    required: false
    default: false
steps:
  - name: step1
    type: python
    action: my_func
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)
        reparsed = parse_workflow(written_yaml)

        assert "repo_name" in reparsed.inputs
        assert reparsed.inputs["repo_name"].type == workflow.inputs["repo_name"].type
        assert (
            reparsed.inputs["repo_name"].required
            == workflow.inputs["repo_name"].required
        )
        assert reparsed.inputs["dry_run"].default == workflow.inputs["dry_run"].default


class TestWorkflowRoundtripStepTypes:
    """Test round-trip for different step types."""

    def test_python_step_roundtrip(self) -> None:
        """Test round-trip for Python step with args/kwargs."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: process
    type: python
    action: my_module.process
    args: [arg1, 42, true]
    kwargs:
      key: value
      number: 123
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)
        reparsed = parse_workflow(written_yaml)

        step = reparsed.steps[0]
        assert step.action == "my_module.process"
        assert step.args == ["arg1", 42, True]
        assert step.kwargs == {"key": "value", "number": 123}

    def test_agent_step_roundtrip(self) -> None:
        """Test round-trip for agent step."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: review
    type: agent
    agent: code_reviewer
    context:
      files: [main.py, utils.py]
      strict: true
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)
        reparsed = parse_workflow(written_yaml)

        step = reparsed.steps[0]
        assert step.agent == "code_reviewer"
        assert isinstance(step.context, dict)
        assert step.context["files"] == ["main.py", "utils.py"]

    def test_generate_step_roundtrip(self) -> None:
        """Test round-trip for generate step."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: describe
    type: generate
    generator: pr_description
    context: default_context_builder
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)
        reparsed = parse_workflow(written_yaml)

        step = reparsed.steps[0]
        assert step.generator == "pr_description"
        assert step.context == "default_context_builder"

    def test_validate_step_roundtrip(self) -> None:
        """Test round-trip for validate step."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: validate
    type: validate
    stages: [format, lint, test]
    retry: 3
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)
        reparsed = parse_workflow(written_yaml)

        step = reparsed.steps[0]
        assert step.stages == ["format", "lint", "test"]
        assert step.retry == 3

    def test_validate_with_on_failure_roundtrip(self) -> None:
        """Test round-trip for validate step with on_failure."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: validate
    type: validate
    stages: [lint]
    retry: 2
    on_failure:
      name: fix
      type: python
      action: auto_fix
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)
        reparsed = parse_workflow(written_yaml)

        step = reparsed.steps[0]
        assert step.on_failure is not None
        assert step.on_failure.name == "fix"
        assert step.on_failure.action == "auto_fix"

    def test_subworkflow_step_roundtrip(self) -> None:
        """Test round-trip for subworkflow step."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: nested
    type: subworkflow
    workflow: other_workflow
    inputs:
      data: value
      count: 42
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)
        reparsed = parse_workflow(written_yaml)

        step = reparsed.steps[0]
        assert step.workflow == "other_workflow"
        assert step.inputs == {"data": "value", "count": 42}

    def test_branch_step_roundtrip(self) -> None:
        """Test round-trip for branch step."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: route
    type: branch
    options:
      - when: "${{ inputs.type_a }}"
        step:
          name: handle_a
          type: python
          action: handle_a
      - when: "${{ inputs.type_b }}"
        step:
          name: handle_b
          type: python
          action: handle_b
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)
        reparsed = parse_workflow(written_yaml)

        step = reparsed.steps[0]
        assert len(step.options) == 2
        assert step.options[0].when == "${{ inputs.type_a }}"
        assert step.options[0].step.name == "handle_a"

    def test_loop_step_roundtrip(self) -> None:
        """Test round-trip for parallel step."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: loop_tasks
    type: loop
    steps:
      - name: task1
        type: python
        action: task1
      - name: task2
        type: python
        action: task2
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)
        reparsed = parse_workflow(written_yaml)

        step = reparsed.steps[0]
        assert len(step.steps) == 2
        assert step.steps[0].name == "task1"
        assert step.steps[1].name == "task2"


class TestWorkflowRoundtripExpressions:
    """Test round-trip for workflows with expressions."""

    def test_expression_in_when_field(self) -> None:
        """Test round-trip preserves when expressions."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: step1
    type: python
    action: my_func
    when: "${{ inputs.enabled }}"
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)
        reparsed = parse_workflow(written_yaml)

        assert reparsed.steps[0].when == "${{ inputs.enabled }}"

    def test_expressions_in_args_kwargs(self) -> None:
        """Test round-trip preserves expressions in args/kwargs."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: step1
    type: python
    action: my_func
    args:
      - "${{ inputs.name }}"
      - "${{ steps.prev.output }}"
    kwargs:
      repo: "${{ inputs.repo_name }}"
      data: "${{ steps.fetch.output.data }}"
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)
        reparsed = parse_workflow(written_yaml)

        step = reparsed.steps[0]
        assert step.args[0] == "${{ inputs.name }}"
        assert step.args[1] == "${{ steps.prev.output }}"
        assert step.kwargs["repo"] == "${{ inputs.repo_name }}"
        assert step.kwargs["data"] == "${{ steps.fetch.output.data }}"

    def test_expressions_in_context(self) -> None:
        """Test round-trip preserves expressions in context."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: review
    type: agent
    agent: reviewer
    context:
      files: "${{ steps.list_files.output }}"
      enabled: "${{ not inputs.skip }}"
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)
        reparsed = parse_workflow(written_yaml)

        step = reparsed.steps[0]
        assert step.context["files"] == "${{ steps.list_files.output }}"
        assert step.context["enabled"] == "${{ not inputs.skip }}"


class TestWorkflowRoundtripNestedStructures:
    """Test round-trip for complex nested structures."""

    def test_deeply_nested_branch_in_loop(self) -> None:
        """Test round-trip for branch inside loop."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: outer_loop
    type: loop
    steps:
      - name: branch1
        type: branch
        options:
          - when: "${{ inputs.enabled }}"
            step:
              name: task1
              type: python
              action: task1
      - name: task2
        type: python
        action: task2
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)
        reparsed = parse_workflow(written_yaml)

        outer = reparsed.steps[0]
        assert outer.type.value == "loop"
        assert len(outer.steps) == 2
        branch = outer.steps[0]
        assert branch.type.value == "branch"
        assert len(branch.options) == 1

    def test_validate_with_nested_on_failure_branch(self) -> None:
        """Test round-trip for validate with branch in on_failure."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: validate
    type: validate
    stages: [lint]
    retry: 2
    on_failure:
      name: fix_route
      type: branch
      options:
        - when: "${{ inputs.auto_fix }}"
          step:
            name: auto_fix
            type: python
            action: fix
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        written_yaml = writer.to_yaml(workflow)
        reparsed = parse_workflow(written_yaml)

        validate = reparsed.steps[0]
        assert validate.on_failure is not None
        assert validate.on_failure.type.value == "branch"
        assert len(validate.on_failure.options) == 1


class TestWorkflowRoundtripJSON:
    """Test round-trip through JSON format."""

    def test_minimal_workflow_json_roundtrip(self) -> None:
        """Test round-trip for minimal workflow through JSON."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: step1
    type: python
    action: my_func
"""
        # Parse from YAML
        workflow = parse_workflow(original_yaml)

        # Write to JSON
        writer = WorkflowWriter()
        json_str = writer.to_json(workflow)

        # Parse JSON and create WorkflowFile from dict
        json_data = json.loads(json_str)

        reparsed = WorkflowFile(**json_data)

        # Verify semantic equivalence
        assert reparsed.version == workflow.version
        assert reparsed.name == workflow.name
        assert len(reparsed.steps) == len(workflow.steps)

    def test_complex_workflow_json_roundtrip(self) -> None:
        """Test round-trip for complex workflow through JSON."""
        original_yaml = """
version: "1.0"
name: complex-workflow
description: Complex workflow with multiple step types
inputs:
  repo:
    type: string
    required: true
steps:
  - name: step1
    type: python
    action: func1
    when: "${{ inputs.repo }}"
  - name: step2
    type: agent
    agent: reviewer
    context:
      data: "${{ steps.step1.output }}"
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        json_str = writer.to_json(workflow)

        # Parse JSON
        json_data = json.loads(json_str)

        reparsed = WorkflowFile(**json_data)

        assert reparsed.description == workflow.description
        assert "repo" in reparsed.inputs
        assert len(reparsed.steps) == 2
        assert reparsed.steps[0].when == "${{ inputs.repo }}"


class TestWorkflowRoundtripEquivalence:
    """Test that round-trip maintains Pydantic model equivalence."""

    def test_model_equality_after_roundtrip(self) -> None:
        """Test that WorkflowFile models are equal after round-trip."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: step1
    type: python
    action: my_func
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()

        # YAML round-trip
        yaml_str = writer.to_yaml(workflow)
        yaml_reparsed = parse_workflow(yaml_str)

        # Models should be equivalent (Pydantic equality)
        assert workflow == yaml_reparsed

    def test_multiple_roundtrips_stable(self) -> None:
        """Test that multiple round-trips produce stable output."""
        original_yaml = """
version: "1.0"
name: test-workflow
steps:
  - name: step1
    type: python
    action: my_func
"""
        workflow1 = parse_workflow(original_yaml)
        writer = WorkflowWriter()

        # First round-trip
        yaml1 = writer.to_yaml(workflow1)
        workflow2 = parse_workflow(yaml1)

        # Second round-trip
        yaml2 = writer.to_yaml(workflow2)
        workflow3 = parse_workflow(yaml2)

        # All should be equal
        assert workflow1 == workflow2 == workflow3
        # YAML strings should be identical after first round-trip
        assert yaml1 == yaml2

    def test_field_ordering_preserved(self) -> None:
        """Test that field ordering is consistent across round-trips."""
        original_yaml = """
version: "1.0"
name: test-workflow
description: Test
inputs:
  repo:
    type: string
    required: true
steps:
  - name: step1
    type: python
    action: func
"""
        workflow = parse_workflow(original_yaml)
        writer = WorkflowWriter()
        yaml_str = writer.to_yaml(workflow)

        # Parse the YAML to check field order
        data = yaml.safe_load(yaml_str)
        keys = list(data.keys())

        # Verify logical ordering
        assert keys[0] == "version"
        assert keys[1] == "name"
        assert "description" in keys
        assert "inputs" in keys
        assert "steps" in keys
        # description should come before inputs
        assert keys.index("description") < keys.index("inputs")
