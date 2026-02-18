"""Tests for built-in workflow YAML parsing (T061).

This module verifies that all built-in workflow YAML files parse correctly
with the WorkflowFile schema and contain all required fields.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.dsl.serialization.parser import parse_workflow
from maverick.dsl.serialization.schema import WorkflowFile

# Path to built-in workflows directory relative to this test file
# Use importlib.resources for more robust path resolution
try:
    from importlib.resources import files

    # Get the path to maverick.library.workflows package
    WORKFLOWS_DIR = files("maverick.library") / "workflows"
except (ImportError, TypeError):
    # Fallback for older Python versions or when running from source
    WORKFLOWS_DIR = (
        Path(__file__).parents[3] / "src" / "maverick" / "library" / "workflows"
    )


# List of all built-in workflow files to test
BUILTIN_WORKFLOWS = [
    "fly-beads.yaml",
    "refuel-speckit.yaml",
]


class TestWorkflowParsing:
    """Test suite for built-in workflow parsing."""

    @pytest.mark.parametrize("workflow_filename", BUILTIN_WORKFLOWS)
    def test_workflow_parses_successfully(self, workflow_filename: str) -> None:
        """Test that each workflow file parses without errors.

        Args:
            workflow_filename: Name of the workflow YAML file to test.
        """
        # Arrange
        workflow_path = WORKFLOWS_DIR / workflow_filename
        assert workflow_path.exists(), f"Workflow file not found: {workflow_path}"

        # Act
        yaml_content = workflow_path.read_text()
        workflow = parse_workflow(yaml_content, validate_only=True)

        # Assert
        assert isinstance(workflow, WorkflowFile)

    @pytest.mark.parametrize("workflow_filename", BUILTIN_WORKFLOWS)
    def test_workflow_has_required_fields(self, workflow_filename: str) -> None:
        """Test that each workflow has all required fields.

        Args:
            workflow_filename: Name of the workflow YAML file to test.
        """
        # Arrange
        workflow_path = WORKFLOWS_DIR / workflow_filename
        yaml_content = workflow_path.read_text()
        workflow = parse_workflow(yaml_content, validate_only=True)

        # Assert - Required fields
        assert workflow.version, "Workflow must have a version"
        assert workflow.name, "Workflow must have a name"
        assert workflow.steps, "Workflow must have at least one step"

        # Assert - Version format
        assert workflow.version == "1.0", "Only version 1.0 is currently supported"

        # Assert - Name format (lowercase, alphanumeric with hyphens)
        assert workflow.name.replace("-", "").replace("_", "").isalnum()
        assert workflow.name[0].isalpha() and workflow.name[0].islower()

    @pytest.mark.parametrize("workflow_filename", BUILTIN_WORKFLOWS)
    def test_workflow_has_unique_step_names(self, workflow_filename: str) -> None:
        """Test that all step names within a workflow are unique.

        Args:
            workflow_filename: Name of the workflow YAML file to test.
        """
        # Arrange
        workflow_path = WORKFLOWS_DIR / workflow_filename
        yaml_content = workflow_path.read_text()
        workflow = parse_workflow(yaml_content, validate_only=True)

        # Act
        step_names = [step.name for step in workflow.steps]

        # Assert
        assert len(step_names) == len(set(step_names)), (
            f"Workflow {workflow_filename} has duplicate step names: "
            f"{[name for name in step_names if step_names.count(name) > 1]}"
        )

    @pytest.mark.parametrize("workflow_filename", BUILTIN_WORKFLOWS)
    def test_workflow_steps_have_valid_types(self, workflow_filename: str) -> None:
        """Test that all steps have valid type fields.

        Args:
            workflow_filename: Name of the workflow YAML file to test.
        """
        # Arrange
        workflow_path = WORKFLOWS_DIR / workflow_filename
        yaml_content = workflow_path.read_text()
        workflow = parse_workflow(yaml_content, validate_only=True)

        # Assert
        valid_types = {
            "python",
            "agent",
            "generate",
            "validate",
            "subworkflow",
            "branch",
            "loop",
            "checkpoint",
        }

        for step in workflow.steps:
            assert step.type in valid_types, (
                f"Step {step.name} has invalid type: {step.type}"
            )

    @pytest.mark.parametrize("workflow_filename", BUILTIN_WORKFLOWS)
    def test_workflow_inputs_are_valid(self, workflow_filename: str) -> None:
        """Test that all workflow inputs are properly defined.

        Args:
            workflow_filename: Name of the workflow YAML file to test.
        """
        # Arrange
        workflow_path = WORKFLOWS_DIR / workflow_filename
        yaml_content = workflow_path.read_text()
        workflow = parse_workflow(yaml_content, validate_only=True)

        # Assert
        for input_name, input_def in workflow.inputs.items():
            # Input name should be valid identifier
            assert input_name.replace("_", "").isalnum(), (
                f"Input name {input_name} is not a valid identifier"
            )

            # Required inputs cannot have defaults
            if input_def.required:
                assert input_def.default is None, (
                    f"Required input {input_name} cannot have a default value"
                )

            # Input should have a description
            assert input_def.description, (
                f"Input {input_name} should have a description"
            )


class TestSpecificWorkflows:
    """Tests for specific workflow characteristics."""

    def test_fly_beads_workflow_structure(self) -> None:
        """Test that fly-beads workflow has expected structure."""
        # Arrange
        workflow_path = WORKFLOWS_DIR / "fly-beads.yaml"
        yaml_content = workflow_path.read_text()
        workflow = parse_workflow(yaml_content, validate_only=True)

        # Assert
        assert workflow.name == "fly-beads"
        assert "epic_id" in workflow.inputs
        assert workflow.inputs["epic_id"].required is False

        # Check for key steps (curate/push moved to 'maverick land')
        step_names = [step.name for step in workflow.steps]
        assert "preflight" in step_names
        assert "bead_loop" in step_names
        assert "final_push" not in step_names

    def test_refuel_speckit_workflow_structure(self) -> None:
        """Test that refuel-speckit workflow has expected structure."""
        # Arrange
        workflow_path = WORKFLOWS_DIR / "refuel-speckit.yaml"
        yaml_content = workflow_path.read_text()
        workflow = parse_workflow(yaml_content, validate_only=True)

        # Assert
        assert workflow.name == "refuel-speckit"
        assert "spec" in workflow.inputs
        assert workflow.inputs["spec"].required is True

        # Check for key steps including branch/merge lifecycle
        step_names = [step.name for step in workflow.steps]
        assert "checkout_branch" in step_names
        assert "parse_spec" in step_names
        assert "create_beads" in step_names
        assert "commit_beads" in step_names
        assert "checkout_main" in step_names
        assert "merge_spec" in step_names


class TestWorkflowConsistency:
    """Tests for consistency across all workflows."""

    def test_all_workflows_have_descriptions(self) -> None:
        """Test that all workflows have non-empty descriptions."""
        for workflow_filename in BUILTIN_WORKFLOWS:
            # Arrange
            workflow_path = WORKFLOWS_DIR / workflow_filename
            yaml_content = workflow_path.read_text()
            workflow = parse_workflow(yaml_content, validate_only=True)

            # Assert
            assert workflow.description, (
                f"Workflow {workflow_filename} should have a description"
            )

    def test_all_workflows_use_version_1_0(self) -> None:
        """Test that all workflows use version 1.0."""
        for workflow_filename in BUILTIN_WORKFLOWS:
            # Arrange
            workflow_path = WORKFLOWS_DIR / workflow_filename
            yaml_content = workflow_path.read_text()
            workflow = parse_workflow(yaml_content, validate_only=True)

            # Assert
            assert workflow.version == "1.0", (
                f"Workflow {workflow_filename} should use version 1.0"
            )
