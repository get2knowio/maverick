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
    "feature.yaml",
    "cleanup.yaml",
    "review.yaml",
    "validate.yaml",
    "quick_fix.yaml",
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

    def test_feature_workflow_structure(self) -> None:
        """Test that feature workflow has expected structure."""
        # Arrange
        workflow_path = WORKFLOWS_DIR / "feature.yaml"
        yaml_content = workflow_path.read_text()
        workflow = parse_workflow(yaml_content, validate_only=True)

        # Assert
        assert workflow.name == "feature"
        assert "branch_name" in workflow.inputs
        assert workflow.inputs["branch_name"].required is True

        # Check for key steps (feature workflow uses phased implementation)
        step_names = [step.name for step in workflow.steps]
        assert "init" in step_names
        assert "implement_by_phase" in step_names  # Phased implementation step
        assert "validate_and_fix" in step_names

    def test_cleanup_workflow_structure(self) -> None:
        """Test that cleanup workflow has expected structure."""
        # Arrange
        workflow_path = WORKFLOWS_DIR / "cleanup.yaml"
        yaml_content = workflow_path.read_text()
        workflow = parse_workflow(yaml_content, validate_only=True)

        # Assert
        assert workflow.name == "cleanup"

        # Should have optional inputs with defaults
        assert "label" in workflow.inputs
        assert workflow.inputs["label"].required is False
        assert workflow.inputs["label"].default is not None

    def test_review_workflow_structure(self) -> None:
        """Test that review workflow has expected structure."""
        # Arrange
        workflow_path = WORKFLOWS_DIR / "review.yaml"
        yaml_content = workflow_path.read_text()
        workflow = parse_workflow(yaml_content, validate_only=True)

        # Assert
        assert workflow.name == "review"

        # Check for key steps (dual-agent review structure)
        step_names = [step.name for step in workflow.steps]
        assert "gather_context" in step_names
        assert "parallel_reviews" in step_names  # Loop step for spec + technical reviewers
        assert "combine_results" in step_names

    def test_validate_workflow_structure(self) -> None:
        """Test that validate workflow has expected structure."""
        # Arrange
        workflow_path = WORKFLOWS_DIR / "validate.yaml"
        yaml_content = workflow_path.read_text()
        workflow = parse_workflow(yaml_content, validate_only=True)

        # Assert
        assert workflow.name == "validate"

        # Should have fix and max_attempts inputs
        assert "fix" in workflow.inputs
        assert "max_attempts" in workflow.inputs

    def test_quick_fix_workflow_structure(self) -> None:
        """Test that quick_fix workflow has expected structure."""
        # Arrange
        workflow_path = WORKFLOWS_DIR / "quick_fix.yaml"
        yaml_content = workflow_path.read_text()
        workflow = parse_workflow(yaml_content, validate_only=True)

        # Assert
        assert workflow.name == "quick-fix"
        assert "issue_number" in workflow.inputs
        assert workflow.inputs["issue_number"].required is True

        # Check for key steps
        step_names = [step.name for step in workflow.steps]
        assert "fetch_issue" in step_names
        assert "fix_issue" in step_names


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
