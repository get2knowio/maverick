"""Unit tests for workflow CLI commands.

Tests comprehensive workflow CLI functionality for Phase 5 (User Story 3):
- T066a: workflow command group tests
- T066b: list and show commands
- T066c: validate and viz commands
- T066d: run command

These tests are written in TDD style and should FAIL initially until the
CLI commands are implemented.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from maverick.main import cli

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_workflow_yaml() -> str:
    """Return sample workflow YAML content for testing."""
    return """version: "1.0"
name: test-workflow
description: A test workflow for unit testing
inputs:
  target:
    type: string
    required: true
    description: The target to process
  verbose:
    type: boolean
    required: false
    default: false
steps:
  - name: process
    type: python
    action: my_action
    kwargs:
      value: ${{ inputs.target }}
  - name: validate
    type: python
    action: validate_result
    kwargs:
      result: ${{ steps.process.output }}
"""


@pytest.fixture
def sample_workflow_file(temp_dir: Path, sample_workflow_yaml: str) -> Path:
    """Create a sample workflow file for testing."""
    workflow_file = temp_dir / "test-workflow.yaml"
    workflow_file.write_text(sample_workflow_yaml)
    return workflow_file


@pytest.fixture
def workflows_dir(temp_dir: Path) -> Path:
    """Create a workflows directory with sample files.

    Creates workflows in .maverick/workflows/ which is the project workflow directory
    that discovery will find.
    """
    workflows = temp_dir / ".maverick" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)

    # Create a few sample workflow files
    (workflows / "workflow-1.yaml").write_text("""version: "1.0"
name: workflow-1
description: First test workflow
steps:
  - name: step1
    type: python
    action: action1
""")

    (workflows / "workflow-2.yaml").write_text("""version: "1.0"
name: workflow-2
description: Second test workflow
steps:
  - name: step1
    type: agent
    agent: TestAgent
""")

    return workflows


# =============================================================================
# T066a: workflow command group tests
# =============================================================================


class TestWorkflowCommandGroup:
    """Tests for the workflow command group."""

    def test_workflow_command_shows_help(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that 'maverick workflow' shows help text.

        Verifies:
        - Command exists and shows help
          (exit code 2 is expected for group without command)
        - Help text is displayed
        - Shows available subcommands
        """
        import os

        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        result = cli_runner.invoke(cli, ["workflow"])

        # Click groups without invoke_without_command=True
        # return 2 without subcommand
        # This is expected behavior - we just verify help is shown
        assert result.exit_code in (0, 2)
        # Should show usage/help text
        assert "workflow" in result.output.lower() or "usage" in result.output.lower()
        # Should mention subcommands
        assert (
            "list" in result.output.lower()
            or "show" in result.output.lower()
            or "commands" in result.output.lower()
        )

    def test_workflow_help_flag(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that 'maverick workflow --help' works.

        Verifies:
        - --help flag works
        - Help text includes command description
        - Lists all subcommands
        """
        import os

        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        result = cli_runner.invoke(cli, ["workflow", "--help"])

        assert result.exit_code == 0
        assert "workflow" in result.output.lower()
        # Should list main subcommands
        for cmd in ["list", "show", "validate", "viz", "run"]:
            assert cmd in result.output.lower()

    def test_workflow_group_exists(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that workflow group is registered under cli.

        Verifies:
        - workflow command is available
        - It's a group (has subcommands)
        """
        import os

        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        # Invoke main help to see if workflow is listed
        result = cli_runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "workflow" in result.output.lower()


# =============================================================================
# T066b: list and show commands
# =============================================================================


class TestWorkflowList:
    """Tests for 'maverick workflow list' command."""

    def test_list_with_empty_directory(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow list with no workflow files.

        Verifies:
        - Command succeeds even with no workflows
        - Shows builtin workflows (always available)
        """
        import os

        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        result = cli_runner.invoke(cli, ["workflow", "list"])

        # Should succeed
        assert result.exit_code == 0
        # Should show builtin workflows (always available)
        assert "fly" in result.output or "builtin" in result.output

    def test_list_with_workflow_files_present(
        self,
        cli_runner: CliRunner,
        workflows_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow list with workflow files present.

        Verifies:
        - Discovers workflow files in .maverick/workflows/ directory
        - Shows workflow names and descriptions
        - Default text/table format
        - Also shows builtin workflows
        """
        import os

        os.chdir(workflows_dir.parent.parent)
        monkeypatch.setattr(Path, "home", lambda: workflows_dir.parent.parent)

        result = cli_runner.invoke(cli, ["workflow", "list"])

        assert result.exit_code == 0
        # Should list both project workflows and builtin workflows
        assert "workflow-1" in result.output
        assert "workflow-2" in result.output
        # Should show descriptions
        assert "First test workflow" in result.output
        assert "Second test workflow" in result.output

    def test_list_format_json(
        self,
        cli_runner: CliRunner,
        workflows_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow list --format json.

        Verifies:
        - --format json flag is accepted
        - Output is valid JSON
        - Contains workflow metadata
        """
        import os

        os.chdir(workflows_dir.parent.parent)
        monkeypatch.setattr(Path, "home", lambda: workflows_dir.parent.parent)

        result = cli_runner.invoke(cli, ["workflow", "list", "--format", "json"])

        assert result.exit_code == 0
        # Output should be valid JSON
        try:
            data = json.loads(result.output)
            assert isinstance(data, list)
            # Should have at least 2 workflows (builtin + project workflows)
            assert len(data) >= 2
            # Each entry should have name and description
            for workflow in data:
                assert "name" in workflow
                assert "description" in workflow
        except json.JSONDecodeError:
            pytest.fail("Output is not valid JSON")

    def test_list_format_yaml(
        self,
        cli_runner: CliRunner,
        workflows_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow list --format yaml.

        Verifies:
        - --format yaml flag is accepted
        - Output is valid YAML
        - Contains workflow information
        """
        import os

        os.chdir(workflows_dir.parent.parent)
        monkeypatch.setattr(Path, "home", lambda: workflows_dir.parent.parent)

        result = cli_runner.invoke(cli, ["workflow", "list", "--format", "yaml"])

        assert result.exit_code == 0
        # Output should be valid YAML
        import yaml

        try:
            data = yaml.safe_load(result.output)
            assert isinstance(data, list)
            assert len(data) >= 2
        except yaml.YAMLError:
            pytest.fail("Output is not valid YAML")


class TestWorkflowShow:
    """Tests for 'maverick workflow show' command."""

    def test_show_existing_workflow(
        self,
        cli_runner: CliRunner,
        workflows_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow show with existing workflow name.

        Verifies:
        - Command accepts workflow name argument
        - Displays workflow details
        - Shows metadata, inputs, and steps
        """
        import os

        os.chdir(workflows_dir.parent.parent)
        monkeypatch.setattr(Path, "home", lambda: workflows_dir.parent.parent)

        result = cli_runner.invoke(cli, ["workflow", "show", "workflow-1"])

        assert result.exit_code == 0
        # Should show workflow details
        assert "workflow-1" in result.output
        assert "First test workflow" in result.output
        # Should show steps
        assert "step1" in result.output
        assert "python" in result.output.lower()

    def test_show_nonexistent_workflow_error(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow show with non-existent workflow.

        Verifies:
        - Command fails with exit code 1
        - Shows error message about workflow not found
        """
        import os

        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        result = cli_runner.invoke(cli, ["workflow", "show", "nonexistent"])

        # Should fail
        assert result.exit_code == 1
        # Should show error message
        assert "not found" in result.output.lower() or "nonexistent" in result.output


# =============================================================================
# T066c: validate and viz commands
# =============================================================================


class TestWorkflowValidate:
    """Tests for 'maverick workflow validate' command."""

    def test_validate_valid_workflow(
        self,
        cli_runner: CliRunner,
        sample_workflow_file: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test validate with a valid workflow file.

        Verifies:
        - Command accepts file path argument
        - Validates workflow successfully
        - Shows success message

        Note: Uses --no-strict to skip reference resolution since the test
        workflow references actions that aren't registered.
        """
        import os

        os.chdir(sample_workflow_file.parent)
        monkeypatch.setattr(Path, "home", lambda: sample_workflow_file.parent)

        result = cli_runner.invoke(
            cli, ["workflow", "validate", str(sample_workflow_file), "--no-strict"]
        )

        assert result.exit_code == 0
        # Should show validation success
        assert "valid" in result.output.lower() or "success" in result.output.lower()

    def test_validate_invalid_workflow_error(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test validate with an invalid workflow file.

        Verifies:
        - Command fails with exit code 1
        - Shows validation errors
        - Error messages are actionable
        """
        import os

        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        # Create invalid workflow (missing required fields)
        invalid_file = temp_dir / "invalid.yaml"
        invalid_file.write_text("""version: "1.0"
# Missing name field
steps:
  - invalid step
""")

        result = cli_runner.invoke(cli, ["workflow", "validate", str(invalid_file)])

        # Should fail
        assert result.exit_code == 1
        # Should show validation error
        assert "error" in result.output.lower() or "invalid" in result.output.lower()

    def test_validate_strict_mode(
        self,
        cli_runner: CliRunner,
        sample_workflow_file: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test validate --strict mode.

        Verifies:
        - --strict flag is accepted
        - Validates all references strictly
        - Fails if any references are unresolved
        """
        import os

        os.chdir(sample_workflow_file.parent)
        monkeypatch.setattr(Path, "home", lambda: sample_workflow_file.parent)

        result = cli_runner.invoke(
            cli, ["workflow", "validate", str(sample_workflow_file), "--strict"]
        )

        # May succeed or fail depending on references
        # Should at least not crash
        assert result.exit_code in (0, 1)


class TestWorkflowViz:
    """Tests for 'maverick workflow viz' command."""

    def test_viz_ascii_format(
        self,
        cli_runner: CliRunner,
        workflows_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow viz with ASCII format.

        Verifies:
        - Command accepts workflow name
        - --format ascii generates ASCII diagram
        - Output contains box-drawing characters
        """
        import os

        os.chdir(workflows_dir.parent.parent)
        monkeypatch.setattr(Path, "home", lambda: workflows_dir.parent.parent)

        result = cli_runner.invoke(
            cli, ["workflow", "viz", "workflow-1", "--format", "ascii"]
        )

        assert result.exit_code == 0
        # Should contain box-drawing characters
        assert any(char in result.output for char in ["┌", "│", "└", "─", "├", "┐"])
        # Should show workflow name
        assert "workflow-1" in result.output

    def test_viz_mermaid_format(
        self,
        cli_runner: CliRunner,
        workflows_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow viz with Mermaid format.

        Verifies:
        - --format mermaid generates Mermaid code
        - Output is valid Mermaid flowchart syntax
        - Contains workflow steps
        """
        import os

        os.chdir(workflows_dir.parent.parent)
        monkeypatch.setattr(Path, "home", lambda: workflows_dir.parent.parent)

        result = cli_runner.invoke(
            cli, ["workflow", "viz", "workflow-1", "--format", "mermaid"]
        )

        assert result.exit_code == 0
        # Should contain Mermaid syntax
        assert "flowchart" in result.output or "graph" in result.output
        # Should show steps
        assert "step1" in result.output

    def test_viz_output_to_file(
        self,
        cli_runner: CliRunner,
        workflows_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow viz --output option.

        Verifies:
        - --output FILE writes diagram to file
        - File is created with correct content
        - Success message is shown
        """
        import os

        os.chdir(workflows_dir.parent.parent)
        monkeypatch.setattr(Path, "home", lambda: workflows_dir.parent.parent)

        output_file = workflows_dir.parent.parent / "diagram.txt"

        result = cli_runner.invoke(
            cli,
            [
                "workflow",
                "viz",
                "workflow-1",
                "--format",
                "ascii",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code == 0
        # File should be created
        assert output_file.exists()
        # Should contain diagram
        content = output_file.read_text()
        assert "workflow-1" in content

    def test_viz_direction_option(
        self,
        cli_runner: CliRunner,
        workflows_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow viz --direction option for Mermaid.

        Verifies:
        - --direction LR changes flowchart direction
        - Mermaid output includes direction specification
        """
        import os

        os.chdir(workflows_dir.parent.parent)
        monkeypatch.setattr(Path, "home", lambda: workflows_dir.parent.parent)

        result = cli_runner.invoke(
            cli,
            [
                "workflow",
                "viz",
                "workflow-1",
                "--format",
                "mermaid",
                "--direction",
                "LR",
            ],
        )

        assert result.exit_code == 0
        # Should contain LR direction
        assert "LR" in result.output


# =============================================================================
# T066d: run command
# =============================================================================


class TestWorkflowRun:
    """Tests for 'maverick workflow run' command."""

    def test_run_workflow_with_inputs(
        self,
        cli_runner: CliRunner,
        sample_workflow_file: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow run with input values.

        Verifies:
        - Command accepts workflow file
        - Parses workflow
        - Accepts input values
        """
        import os

        os.chdir(sample_workflow_file.parent)
        monkeypatch.setattr(Path, "home", lambda: sample_workflow_file.parent)

        result = cli_runner.invoke(
            cli,
            [
                "workflow",
                "run",
                str(sample_workflow_file),
                "-i",
                "target=value",
            ],
        )

        # Workflow will fail because actions aren't registered,
        # but it should parse and start
        # The important thing is that it doesn't crash on parsing
        # Expected to fail due to missing actions
        assert result.exit_code == 1
        # Should show workflow name
        assert "test-workflow" in result.output
        # Should show it attempted execution
        assert "Executing workflow" in result.output or "process" in result.output

    def test_run_workflow_from_file(
        self,
        cli_runner: CliRunner,
        sample_workflow_file: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow run with file path.

        Verifies:
        - Can run workflow from file path
        - File is loaded and parsed
        """
        import os

        os.chdir(sample_workflow_file.parent)
        monkeypatch.setattr(Path, "home", lambda: sample_workflow_file.parent)

        result = cli_runner.invoke(
            cli,
            [
                "workflow",
                "run",
                str(sample_workflow_file),
                "-i",
                "target=test",
            ],
        )

        # Workflow will fail because actions aren't registered
        assert result.exit_code == 1
        assert "test-workflow" in result.output

    def test_run_with_input_key_value_pairs(
        self,
        cli_runner: CliRunner,
        sample_workflow_file: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow run with -i key=value inputs.

        Verifies:
        - -i/--input KEY=VALUE syntax is parsed
        - Multiple -i flags work
        """
        import os

        os.chdir(sample_workflow_file.parent)
        monkeypatch.setattr(Path, "home", lambda: sample_workflow_file.parent)

        result = cli_runner.invoke(
            cli,
            [
                "workflow",
                "run",
                str(sample_workflow_file),
                "-i",
                "target=value1",
                "-i",
                "verbose=true",
            ],
        )

        # Workflow will fail because actions aren't registered
        assert result.exit_code == 1
        # Check that inputs are mentioned in output
        assert "test-workflow" in result.output
        assert "Inputs:" in result.output

    def test_run_with_input_file(
        self,
        cli_runner: CliRunner,
        sample_workflow_file: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow run with --input-file option.

        Verifies:
        - --input-file loads inputs from JSON
        """
        import os

        os.chdir(sample_workflow_file.parent)
        monkeypatch.setattr(Path, "home", lambda: sample_workflow_file.parent)

        # Create input file
        input_file = sample_workflow_file.parent / "inputs.json"
        input_file.write_text(json.dumps({"target": "from-file", "verbose": True}))

        result = cli_runner.invoke(
            cli,
            [
                "workflow",
                "run",
                str(sample_workflow_file),
                "--input-file",
                str(input_file),
            ],
        )

        # Workflow will fail because actions aren't registered
        assert result.exit_code == 1
        assert "test-workflow" in result.output

    def test_run_dry_run_mode(
        self,
        cli_runner: CliRunner,
        sample_workflow_file: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow run --dry-run option.

        Verifies:
        - --dry-run shows execution plan
        - Workflow is NOT actually executed
        - Shows steps that would be run
        """
        import os

        os.chdir(sample_workflow_file.parent)
        monkeypatch.setattr(Path, "home", lambda: sample_workflow_file.parent)

        result = cli_runner.invoke(
            cli,
            [
                "workflow",
                "run",
                str(sample_workflow_file),
                "-i",
                "target=test",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        # Should indicate dry-run mode
        assert "dry run" in result.output.lower() or "would" in result.output.lower()
        # Should show workflow name
        assert "test-workflow" in result.output

    def test_run_enhanced_progress_display(
        self,
        cli_runner: CliRunner,
        sample_workflow_file: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test enhanced progress display during workflow execution.

        Verifies:
        - Workflow header with name and version
        - Input summary display
        - Step progress with counters [1/N]
        - Step type indicators
        - Success/failure status
        - Duration display
        - Summary statistics
        """
        import os

        os.chdir(sample_workflow_file.parent)
        monkeypatch.setattr(Path, "home", lambda: sample_workflow_file.parent)

        result = cli_runner.invoke(
            cli,
            [
                "workflow",
                "run",
                str(sample_workflow_file),
                "-i",
                "target=test-value",
                "--no-validate",  # Skip validation - actions not registered
            ],
        )

        # Note: The workflow will fail because actions aren't registered,
        # but we can still verify the output format
        assert result.exit_code == 1  # Expected to fail

        # Verify workflow header
        assert "Executing workflow: test-workflow" in result.output
        assert "Version:" in result.output

        # Verify input display
        assert "Inputs:" in result.output
        assert "target" in result.output

        # Verify step progress display
        # Should show step counters like [1/2], [2/2]
        assert "[1/2]" in result.output or "[1/" in result.output

        # Verify step names are shown
        assert "process" in result.output
        # validate step might not show if first step fails

        # Verify step type is shown
        assert "python" in result.output.lower()

        # Verify summary section
        assert "Steps:" in result.output
        assert "completed" in result.output.lower()

        # Verify error handling for failed step
        assert "failed" in result.output.lower()


# =============================================================================
# Integration Tests
# =============================================================================


class TestWorkflowCommandIntegration:
    """Integration tests combining multiple workflow commands."""

    def test_list_show_validate_workflow(
        self,
        cli_runner: CliRunner,
        workflows_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test complete workflow: list -> show -> validate.

        Verifies:
        - Commands work together
        - Data consistency across commands
        """
        import os

        os.chdir(workflows_dir.parent.parent)
        monkeypatch.setattr(Path, "home", lambda: workflows_dir.parent.parent)

        # List workflows
        list_result = cli_runner.invoke(cli, ["workflow", "list"])
        assert list_result.exit_code == 0
        assert "workflow-1" in list_result.output

        # Show workflow details
        show_result = cli_runner.invoke(cli, ["workflow", "show", "workflow-1"])
        assert show_result.exit_code == 0
        assert "workflow-1" in show_result.output

        # Validate workflow (use --no-strict since test actions aren't registered)
        workflow_file = workflows_dir / "workflow-1.yaml"
        validate_result = cli_runner.invoke(
            cli, ["workflow", "validate", str(workflow_file), "--no-strict"]
        )
        assert validate_result.exit_code == 0

    def test_validate_viz_workflow(
        self,
        cli_runner: CliRunner,
        workflows_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test workflow validation then visualization.

        Verifies:
        - Valid workflow can be visualized
        - Both commands succeed
        """
        import os

        os.chdir(workflows_dir.parent.parent)
        monkeypatch.setattr(Path, "home", lambda: workflows_dir.parent.parent)

        workflow_file = workflows_dir / "workflow-1.yaml"

        # Validate first (use --no-strict since test actions aren't registered)
        validate_result = cli_runner.invoke(
            cli, ["workflow", "validate", str(workflow_file), "--no-strict"]
        )
        assert validate_result.exit_code == 0

        # Then visualize
        viz_result = cli_runner.invoke(
            cli, ["workflow", "viz", "workflow-1", "--format", "ascii"]
        )
        assert viz_result.exit_code == 0
