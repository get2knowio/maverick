"""Integration tests for branch step execution with YAML workflows.

This test module verifies that BranchStepRecord execution works correctly
when loaded from YAML workflow files and executed through WorkflowFileExecutor.
"""

from __future__ import annotations

import pytest

from maverick.dsl.events import (
    StepStarted,
)
from maverick.dsl.serialization import (
    ComponentRegistry,
    WorkflowFileExecutor,
    parse_workflow,
)


@pytest.fixture
def registry():
    """Create a component registry with test actions."""
    reg = ComponentRegistry()

    @reg.actions.register("action_a")
    def action_a():
        return "Result A"

    @reg.actions.register("action_b")
    def action_b():
        return "Result B"

    @reg.actions.register("action_default")
    def action_default():
        return "Default Result"

    @reg.actions.register("log_message")
    def log_message(message: str):
        return f"Logged: {message}"

    return reg


class TestBranchWorkflowYAML:
    """Integration tests for branch steps in YAML workflows."""

    @pytest.mark.asyncio
    async def test_simple_branch_workflow(self, registry):
        """Test a simple YAML workflow with branch step."""
        yaml_content = """
version: "1.0"
name: simple-branch-test
description: Test branch step with simple conditions

inputs:
  choose_a:
    type: boolean
    required: true
    description: Whether to choose path A
  choose_b:
    type: boolean
    required: true
    description: Whether to choose path B

steps:
  - name: choose_action
    type: branch
    options:
      - when: ${{ inputs.choose_a }}
        step:
          name: path_a
          type: python
          action: action_a

      - when: ${{ inputs.choose_b }}
        step:
          name: path_b
          type: python
          action: action_b
"""

        # Parse workflow
        workflow = parse_workflow(yaml_content)

        # Execute with path A
        executor = WorkflowFileExecutor(registry=registry)
        events = []

        async for event in executor.execute(
            workflow, inputs={"choose_a": True, "choose_b": False}
        ):
            events.append(event)

        # Verify execution took path A
        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "Result A"

        # Verify events
        step_names = [e.step_name for e in events if isinstance(e, StepStarted)]
        assert "choose_action" in step_names
        # Note: path_a is executed as part of the branch step

    @pytest.mark.asyncio
    async def test_branch_with_negation(self, registry):
        """Test branch step with negation operator."""
        yaml_content = """
version: "1.0"
name: negation-branch-test
description: Test branch with NOT operator

inputs:
  is_enabled:
    type: boolean
    required: true

steps:
  - name: conditional_branch
    type: branch
    options:
      - when: ${{ inputs.is_enabled }}
        step:
          name: enabled_path
          type: python
          action: action_a

      - when: ${{ not inputs.is_enabled }}
        step:
          name: disabled_path
          type: python
          action: action_b
"""

        workflow = parse_workflow(yaml_content)

        # Test with is_enabled=False (should take disabled_path)
        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"is_enabled": False}):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "Result B"

    @pytest.mark.asyncio
    async def test_branch_with_fallback(self, registry):
        """Test branch step with catch-all fallback option."""
        yaml_content = """
version: "1.0"
name: fallback-branch-test
description: Test branch with catch-all default

inputs:
  is_special:
    type: boolean
    required: false
    default: false

steps:
  - name: choice_branch
    type: branch
    options:
      - when: ${{ inputs.is_special }}
        step:
          name: special_path
          type: python
          action: action_a

      # Catch-all for any other value
      - when: ${{ not inputs.is_special }}
        step:
          name: default_path
          type: python
          action: action_default
"""

        workflow = parse_workflow(yaml_content)

        # Test with is_special=False (should take default path)
        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"is_special": False}):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "Default Result"

    @pytest.mark.asyncio
    async def test_branch_no_match_returns_none(self, registry):
        """Test that branch returns None when no option matches."""
        yaml_content = """
version: "1.0"
name: no-match-branch-test
description: Test branch with no matching option

inputs:
  flag:
    type: boolean
    required: true

steps:
  - name: strict_branch
    type: branch
    options:
      - when: ${{ inputs.flag }}
        step:
          name: true_path
          type: python
          action: action_a
"""

        workflow = parse_workflow(yaml_content)

        # Execute with flag=False (no matching option)
        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"flag": False}):
            pass

        result = executor.get_result()
        assert result.success is True
        # When no branch matches, the step returns None
        assert result.final_output is None

    @pytest.mark.asyncio
    async def test_branch_evaluates_in_order(self, registry):
        """Test that branch options are evaluated in order (first match wins)."""
        yaml_content = """
version: "1.0"
name: ordered-branch-test
description: Test that first matching branch is selected

inputs:
  both_true:
    type: boolean
    required: true

steps:
  - name: ordered_branch
    type: branch
    options:
      # Both conditions will be true
      - when: ${{ inputs.both_true }}
        step:
          name: first_match
          type: python
          action: action_a

      # This would also match, but should not execute
      - when: ${{ inputs.both_true }}
        step:
          name: second_match
          type: python
          action: action_b
"""

        workflow = parse_workflow(yaml_content)

        # Execute with both_true=True (both conditions match, but first wins)
        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"both_true": True}):
            pass

        result = executor.get_result()
        assert result.success is True
        # Should execute action_a (first match), not action_b
        assert result.final_output == "Result A"

    @pytest.mark.asyncio
    async def test_branch_with_step_output_reference(self, registry):
        """Test branch condition referencing previous step output."""
        yaml_content = """
version: "1.0"
name: step-ref-branch-test
description: Test branch using step output in condition

steps:
  - name: setup
    type: python
    action: action_a

  - name: conditional_branch
    type: branch
    options:
      # Check if previous step output contains "A"
      - when: ${{ steps.setup.output }}
        step:
          name: has_output
          type: python
          action: action_b
"""

        workflow = parse_workflow(yaml_content)

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        # setup returns "Result A", which is truthy, so branch executes action_b
        assert result.final_output == "Result B"

    @pytest.mark.asyncio
    async def test_branch_in_multi_step_workflow(self, registry):
        """Test branch step as part of a larger workflow."""
        yaml_content = """
version: "1.0"
name: multi-step-branch-test
description: Test branch step integrated in workflow

inputs:
  use_fast_mode:
    type: boolean
    required: true

steps:
  - name: setup
    type: python
    action: log_message
    kwargs:
      message: "Starting workflow"

  - name: mode_selection
    type: branch
    options:
      - when: ${{ inputs.use_fast_mode }}
        step:
          name: fast_mode
          type: python
          action: action_a

      - when: ${{ not inputs.use_fast_mode }}
        step:
          name: slow_mode
          type: python
          action: action_b

  - name: finalize
    type: python
    action: log_message
    kwargs:
      message: "Workflow complete"
"""

        workflow = parse_workflow(yaml_content)

        # Execute with use_fast_mode=True
        executor = WorkflowFileExecutor(registry=registry)
        events = []

        async for event in executor.execute(workflow, inputs={"use_fast_mode": True}):
            events.append(event)

        # Verify all steps executed
        result = executor.get_result()
        assert result.success is True
        assert len(result.step_results) == 3

        # Verify the branch step executed action_a
        assert result.step_results[1].name == "mode_selection"
        assert result.step_results[1].output == "Result A"

        # Verify final step executed
        assert result.final_output == "Logged: Workflow complete"
