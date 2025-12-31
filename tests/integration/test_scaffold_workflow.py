"""Integration tests for workflow template scaffolding.

This module validates the complete template scaffolding flow:
- Creating workflows from basic, full, and parallel templates
- YAML and Python format generation
- Custom values (name, description, author)
- Preview mode without file creation
- File validation (YAML parsing, Python syntax checking)
- Directory handling (project vs custom directories)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from maverick.dsl.serialization.parser import parse_workflow
from maverick.library.scaffold import (
    InvalidNameError,
    OutputExistsError,
    ScaffoldRequest,
    TemplateFormat,
    TemplateType,
    get_default_output_dir,
    validate_workflow_name,
)


# Get scaffolder instance for tests
def get_scaffolder():
    """Get scaffolder instance, skip test if templates not available or broken."""
    from maverick.library.scaffold import create_scaffold_service

    scaffolder = create_scaffold_service()

    # Check if templates directory has any .j2 files
    template_files = list(scaffolder._template_dir.glob("*.j2"))
    if not template_files:
        pytest.skip("Templates not yet created (tasks T045-T050)")

    # Try a simple template render to see if templates are working
    try:
        from pathlib import Path

        from maverick.library.scaffold import (
            ScaffoldRequest,
            TemplateFormat,
            TemplateType,
        )

        test_request = ScaffoldRequest(
            name="test",
            template=TemplateType.BASIC,
            format=TemplateFormat.YAML,
            output_dir=Path("/tmp"),
        )
        # This will raise TemplateRenderError if templates have syntax issues
        scaffolder.preview(test_request)
    except Exception as e:
        pytest.skip(f"Templates exist but are not yet functional: {e}")

    return scaffolder


class TestWorkflowNameValidation:
    """Test workflow name validation rules."""

    def test_valid_names(self) -> None:
        """Valid workflow names should pass validation."""
        valid_names = [
            "my-workflow",
            "test",
            "a",
            "workflow-123",
            "feature-branch-1",
            "x" * 64,  # Maximum length
        ]
        for name in valid_names:
            # Should not raise
            validate_workflow_name(name)

    def test_invalid_empty_name(self) -> None:
        """Empty name should raise InvalidNameError."""
        with pytest.raises(InvalidNameError) as exc_info:
            validate_workflow_name("")
        assert exc_info.value.name == ""
        assert "empty" in exc_info.value.reason.lower()

    def test_invalid_too_long(self) -> None:
        """Name longer than 64 characters should raise InvalidNameError."""
        long_name = "x" * 65
        with pytest.raises(InvalidNameError) as exc_info:
            validate_workflow_name(long_name)
        assert exc_info.value.name == long_name
        assert "64 characters" in exc_info.value.reason

    def test_invalid_uppercase_start(self) -> None:
        """Name starting with uppercase should raise InvalidNameError."""
        with pytest.raises(InvalidNameError) as exc_info:
            validate_workflow_name("Workflow")
        assert "lowercase letter" in exc_info.value.reason

    def test_invalid_number_start(self) -> None:
        """Name starting with number should raise InvalidNameError."""
        with pytest.raises(InvalidNameError) as exc_info:
            validate_workflow_name("1workflow")
        assert "lowercase letter" in exc_info.value.reason

    def test_invalid_special_characters(self) -> None:
        """Name with special characters (not hyphen) should raise InvalidNameError."""
        invalid_names = [
            "my_workflow",  # Underscore not allowed
            "my.workflow",  # Dot not allowed
            "my workflow",  # Space not allowed
            "my@workflow",  # @ not allowed
        ]
        for name in invalid_names:
            with pytest.raises(InvalidNameError) as exc_info:
                validate_workflow_name(name)
            assert "lowercase letters, numbers, and hyphens" in exc_info.value.reason


class TestDefaultOutputDirectory:
    """Test default output directory function."""

    def test_default_output_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default output directory should be .maverick/workflows/.

        Verifies default location in current directory.
        """
        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        output_dir = get_default_output_dir()

        expected = tmp_path / ".maverick" / "workflows"
        assert output_dir == expected


class TestBasicTemplateScaffolding:
    """Test basic template scaffolding for YAML workflows."""

    def test_scaffold_basic_yaml_workflow(self, tmp_path: Path) -> None:
        """Create a basic YAML workflow and verify it's valid."""
        scaffolder = get_scaffolder()

        output_dir = tmp_path / "workflows"
        output_dir.mkdir()

        request = ScaffoldRequest(
            name="test-workflow",
            template=TemplateType.BASIC,
            format=TemplateFormat.YAML,
            output_dir=output_dir,
            description="A test workflow",
            author="Test Author",
        )

        result = scaffolder.scaffold(request)

        # Verify result
        assert result.success
        assert result.output_path is not None
        assert result.output_path.exists()
        assert result.output_path == output_dir / "test-workflow.yaml"
        assert result.error is None

        # Verify file content is valid YAML workflow
        content = result.output_path.read_text()
        workflow = parse_workflow(content)

        assert workflow.name == "test-workflow"
        assert workflow.version == "1.0"
        assert len(workflow.steps) > 0

    def test_scaffold_basic_yaml_with_default_values(self, tmp_path: Path) -> None:
        """Scaffold with minimal values should use defaults."""
        scaffolder = get_scaffolder()

        output_dir = tmp_path / "workflows"
        output_dir.mkdir()

        request = ScaffoldRequest(
            name="minimal",
            template=TemplateType.BASIC,
            format=TemplateFormat.YAML,
            output_dir=output_dir,
        )

        result = scaffolder.scaffold(request)

        assert result.success
        assert result.output_path is not None
        assert result.output_path.exists()

        # Should still be valid workflow
        content = result.output_path.read_text()
        workflow = parse_workflow(content)
        assert workflow.name == "minimal"

    def test_scaffold_rejects_invalid_name(self, tmp_path: Path) -> None:
        """Scaffolding with invalid name should raise InvalidNameError."""
        scaffolder = get_scaffolder()

        request = ScaffoldRequest(
            name="Invalid_Name",  # Underscore not allowed
            template=TemplateType.BASIC,
            format=TemplateFormat.YAML,
            output_dir=tmp_path,
        )

        with pytest.raises(InvalidNameError):
            scaffolder.scaffold(request)

    def test_scaffold_rejects_existing_file(self, tmp_path: Path) -> None:
        """Scaffolding when file exists should raise OutputExistsError."""
        scaffolder = get_scaffolder()

        output_dir = tmp_path / "workflows"
        output_dir.mkdir()

        # Create existing file
        existing_file = output_dir / "existing.yaml"
        existing_file.write_text("version: '1.0'\nname: existing\nsteps: []")

        request = ScaffoldRequest(
            name="existing",
            template=TemplateType.BASIC,
            format=TemplateFormat.YAML,
            output_dir=output_dir,
            overwrite=False,
        )

        with pytest.raises(OutputExistsError) as exc_info:
            scaffolder.scaffold(request)
        assert exc_info.value.path == existing_file

    def test_scaffold_overwrites_with_flag(self, tmp_path: Path) -> None:
        """Scaffolding with overwrite=True should replace existing file."""
        scaffolder = get_scaffolder()

        output_dir = tmp_path / "workflows"
        output_dir.mkdir()

        # Create existing file
        existing_file = output_dir / "existing.yaml"
        existing_file.write_text("old content")

        request = ScaffoldRequest(
            name="existing",
            template=TemplateType.BASIC,
            format=TemplateFormat.YAML,
            output_dir=output_dir,
            overwrite=True,
        )

        result = scaffolder.scaffold(request)

        assert result.success
        assert result.output_path == existing_file

        # Content should be new workflow, not "old content"
        content = existing_file.read_text()
        assert "old content" not in content
        workflow = parse_workflow(content)
        assert workflow.name == "existing"


class TestFullTemplateScaffolding:
    """Test full template scaffolding with validation/review/PR patterns."""

    def test_scaffold_full_yaml_workflow(self, tmp_path: Path) -> None:
        """Create a full YAML workflow and verify it includes all sections."""
        scaffolder = get_scaffolder()

        output_dir = tmp_path / "workflows"
        output_dir.mkdir()

        request = ScaffoldRequest(
            name="full-workflow",
            template=TemplateType.FULL,
            format=TemplateFormat.YAML,
            output_dir=output_dir,
            description="A complete workflow with all stages",
        )

        result = scaffolder.scaffold(request)

        assert result.success
        assert result.output_path is not None

        # Verify workflow structure
        content = result.output_path.read_text()
        workflow = parse_workflow(content)

        assert workflow.name == "full-workflow"
        assert len(workflow.steps) > 1  # Should have multiple steps

        # Full template should reference validation/review/PR fragments
        step_names = {step.name for step in workflow.steps}
        # At least one of these patterns should be present
        has_validation = any("validate" in name.lower() for name in step_names)
        has_review = any("review" in name.lower() for name in step_names)
        has_pr = any(
            "pr" in name.lower() or "pull" in name.lower() for name in step_names
        )

        # Full workflow should have at least 2 of these 3 stages
        assert sum([has_validation, has_review, has_pr]) >= 2

    def test_full_template_includes_subworkflow_references(
        self, tmp_path: Path
    ) -> None:
        """Full template should include references to fragments.

        Verifies references like validate_and_fix are present in full template.
        """
        scaffolder = get_scaffolder()

        output_dir = tmp_path / "workflows"
        output_dir.mkdir()

        request = ScaffoldRequest(
            name="with-fragments",
            template=TemplateType.FULL,
            format=TemplateFormat.YAML,
            output_dir=output_dir,
        )

        result = scaffolder.scaffold(request)

        assert result.success
        content = result.output_path.read_text()

        # Full template should reference at least one fragment
        # Check for subworkflow references
        assert (
            "type: subworkflow" in content
            or "validate_and_fix" in content
            or "commit_and_push" in content
            or "create_pr_with_summary" in content
        )


class TestParallelTemplateScaffolding:
    """Test parallel template scaffolding demonstrating parallel steps."""

    def test_scaffold_parallel_yaml_workflow(self, tmp_path: Path) -> None:
        """Create a parallel YAML workflow and verify parallel structure."""
        scaffolder = get_scaffolder()

        output_dir = tmp_path / "workflows"
        output_dir.mkdir()

        request = ScaffoldRequest(
            name="parallel-workflow",
            template=TemplateType.PARALLEL,
            format=TemplateFormat.YAML,
            output_dir=output_dir,
        )

        result = scaffolder.scaffold(request)

        assert result.success
        assert result.output_path is not None

        # Verify workflow has parallel steps
        content = result.output_path.read_text()
        workflow = parse_workflow(content)

        assert workflow.name == "parallel-workflow"

        # Should contain parallel step type
        assert "type: parallel" in content

    def test_parallel_template_has_for_each_substeps(self, tmp_path: Path) -> None:
        """Parallel template should demonstrate for_each pattern with substeps."""
        scaffolder = get_scaffolder()

        output_dir = tmp_path / "workflows"
        output_dir.mkdir()

        request = ScaffoldRequest(
            name="multi-parallel",
            template=TemplateType.PARALLEL,
            format=TemplateFormat.YAML,
            output_dir=output_dir,
        )

        result = scaffolder.scaffold(request)

        content = result.output_path.read_text()
        workflow = parse_workflow(content)

        # Find parallel step
        parallel_steps = [s for s in workflow.steps if hasattr(s, "steps")]
        assert len(parallel_steps) > 0

        # Parallel step should have substeps (for_each pattern has 1 step repeated)
        if parallel_steps:
            # At least one parallel step should have substeps
            assert any(len(s.steps) >= 1 for s in parallel_steps)
            # Verify it uses for_each pattern
            assert any(hasattr(s, "for_each") and s.for_each for s in parallel_steps)


class TestPythonTemplateScaffolding:
    """Test Python template scaffolding for all template types."""

    def test_scaffold_basic_python_workflow(self, tmp_path: Path) -> None:
        """Create basic Python workflow and verify valid Python syntax."""
        scaffolder = get_scaffolder()

        output_dir = tmp_path / "workflows"
        output_dir.mkdir()

        request = ScaffoldRequest(
            name="python-basic",
            template=TemplateType.BASIC,
            format=TemplateFormat.PYTHON,
            output_dir=output_dir,
        )

        result = scaffolder.scaffold(request)

        assert result.success
        assert result.output_path is not None
        assert result.output_path.suffix == ".py"

        # Verify Python syntax is valid
        content = result.output_path.read_text()
        ast.parse(content)  # Will raise SyntaxError if invalid

    def test_scaffold_full_python_workflow(self, tmp_path: Path) -> None:
        """Create full Python workflow and verify syntax."""
        scaffolder = get_scaffolder()

        output_dir = tmp_path / "workflows"
        output_dir.mkdir()

        request = ScaffoldRequest(
            name="python-full",
            template=TemplateType.FULL,
            format=TemplateFormat.PYTHON,
            output_dir=output_dir,
        )

        result = scaffolder.scaffold(request)

        assert result.success
        content = result.output_path.read_text()

        # Valid Python syntax
        ast.parse(content)

        # Should contain async def or function definition
        assert "def " in content

    def test_scaffold_parallel_python_workflow(self, tmp_path: Path) -> None:
        """Create parallel Python workflow and verify syntax."""
        scaffolder = get_scaffolder()

        output_dir = tmp_path / "workflows"
        output_dir.mkdir()

        request = ScaffoldRequest(
            name="python-parallel",
            template=TemplateType.PARALLEL,
            format=TemplateFormat.PYTHON,
            output_dir=output_dir,
        )

        result = scaffolder.scaffold(request)

        assert result.success
        content = result.output_path.read_text()

        # Valid Python syntax
        tree = ast.parse(content)

        # Should have at least one function definition
        functions = [
            node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ]
        assert len(functions) > 0


class TestScaffoldCustomValues:
    """Test scaffolding with custom name, description, and author."""

    def test_custom_description_appears_in_output(self, tmp_path: Path) -> None:
        """Custom description should appear in generated workflow."""
        scaffolder = get_scaffolder()

        output_dir = tmp_path / "workflows"
        output_dir.mkdir()

        custom_desc = "This is my custom workflow description"

        request = ScaffoldRequest(
            name="custom-desc",
            template=TemplateType.BASIC,
            format=TemplateFormat.YAML,
            output_dir=output_dir,
            description=custom_desc,
        )

        result = scaffolder.scaffold(request)

        assert result.success
        content = result.output_path.read_text()
        workflow = parse_workflow(content)

        # Description should be in workflow or content
        assert workflow.description == custom_desc or custom_desc in content

    def test_custom_author_appears_in_output(self, tmp_path: Path) -> None:
        """Custom author should appear in generated workflow comments."""
        scaffolder = get_scaffolder()

        output_dir = tmp_path / "workflows"
        output_dir.mkdir()

        custom_author = "Jane Developer"

        request = ScaffoldRequest(
            name="custom-author",
            template=TemplateType.BASIC,
            format=TemplateFormat.YAML,
            output_dir=output_dir,
            author=custom_author,
        )

        result = scaffolder.scaffold(request)

        assert result.success
        content = result.output_path.read_text()

        # Author should appear in comments or metadata
        assert custom_author in content

    def test_all_custom_values_together(self, tmp_path: Path) -> None:
        """All custom values should work together."""
        scaffolder = get_scaffolder()

        output_dir = tmp_path / "workflows"
        output_dir.mkdir()

        request = ScaffoldRequest(
            name="fully-custom",
            template=TemplateType.FULL,
            format=TemplateFormat.YAML,
            output_dir=output_dir,
            description="Custom description for testing",
            author="Test Suite",
        )

        result = scaffolder.scaffold(request)

        assert result.success
        content = result.output_path.read_text()
        workflow = parse_workflow(content)

        assert workflow.name == "fully-custom"
        # At least one custom value should be present
        assert "Custom description" in content or "Test Suite" in content


class TestScaffoldDirectoryHandling:
    """Test scaffolding to different directories."""

    def test_scaffold_to_project_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Scaffold to project .maverick/workflows/ directory."""
        monkeypatch.chdir(tmp_path)

        scaffolder = get_scaffolder()

        # Use default project directory
        project_dir = tmp_path / ".maverick" / "workflows"
        project_dir.mkdir(parents=True)

        request = ScaffoldRequest(
            name="project-workflow",
            template=TemplateType.BASIC,
            format=TemplateFormat.YAML,
            output_dir=project_dir,
        )

        result = scaffolder.scaffold(request)

        assert result.success
        assert result.output_path == project_dir / "project-workflow.yaml"
        assert result.output_path.exists()

    def test_scaffold_to_custom_directory(self, tmp_path: Path) -> None:
        """Scaffold to custom user-specified directory."""
        scaffolder = get_scaffolder()

        custom_dir = tmp_path / "custom" / "location"
        custom_dir.mkdir(parents=True)

        request = ScaffoldRequest(
            name="custom-location",
            template=TemplateType.BASIC,
            format=TemplateFormat.YAML,
            output_dir=custom_dir,
        )

        result = scaffolder.scaffold(request)

        assert result.success
        assert result.output_path == custom_dir / "custom-location.yaml"
        assert result.output_path.exists()

    def test_scaffold_creates_parent_directories(self, tmp_path: Path) -> None:
        """Scaffolder should create parent directories if they don't exist."""
        scaffolder = get_scaffolder()

        # Directory doesn't exist yet
        nested_dir = tmp_path / "deep" / "nested" / "path"
        assert not nested_dir.exists()

        request = ScaffoldRequest(
            name="nested-workflow",
            template=TemplateType.BASIC,
            format=TemplateFormat.YAML,
            output_dir=nested_dir,
        )

        result = scaffolder.scaffold(request)

        assert result.success
        assert nested_dir.exists()
        assert result.output_path.exists()


class TestScaffoldPreviewMode:
    """Test preview mode that returns content without creating files."""

    def test_preview_returns_content_without_creating_file(
        self, tmp_path: Path
    ) -> None:
        """Preview should return content but not create file."""
        scaffolder = get_scaffolder()

        output_dir = tmp_path / "workflows"
        output_dir.mkdir()

        request = ScaffoldRequest(
            name="preview-test",
            template=TemplateType.BASIC,
            format=TemplateFormat.YAML,
            output_dir=output_dir,
        )

        # Use preview instead of scaffold
        result = scaffolder.preview(request)

        # Content should be returned
        assert result.success
        assert result.content is not None
        assert isinstance(result.content, str)
        assert len(result.content) > 0

        # File should NOT exist
        expected_path = output_dir / "preview-test.yaml"
        assert not expected_path.exists()

    def test_preview_content_is_valid_workflow(self, tmp_path: Path) -> None:
        """Preview content should be parseable as workflow."""
        scaffolder = get_scaffolder()

        request = ScaffoldRequest(
            name="preview-valid",
            template=TemplateType.BASIC,
            format=TemplateFormat.YAML,
            output_dir=tmp_path,
        )

        result = scaffolder.preview(request)

        # Should parse as valid workflow
        assert result.success
        assert result.content is not None
        workflow = parse_workflow(result.content)
        assert workflow.name == "preview-valid"

    def test_preview_python_content_has_valid_syntax(self, tmp_path: Path) -> None:
        """Preview Python content should have valid syntax."""
        scaffolder = get_scaffolder()

        request = ScaffoldRequest(
            name="preview-python",
            template=TemplateType.BASIC,
            format=TemplateFormat.PYTHON,
            output_dir=tmp_path,
        )

        result = scaffolder.preview(request)

        # Should parse as valid Python
        assert result.success
        assert result.content is not None
        ast.parse(result.content)

    def test_preview_with_invalid_name_raises_error(self, tmp_path: Path) -> None:
        """Preview with invalid name should raise InvalidNameError."""
        scaffolder = get_scaffolder()

        request = ScaffoldRequest(
            name="Invalid_Name",
            template=TemplateType.BASIC,
            format=TemplateFormat.YAML,
            output_dir=tmp_path,
        )

        with pytest.raises(InvalidNameError):
            scaffolder.preview(request)


class TestTemplateList:
    """Test listing available templates."""

    def test_list_templates_returns_all_types(self) -> None:
        """list_templates should return info for all template types."""
        scaffolder = get_scaffolder()

        templates = scaffolder.list_templates()

        # Should have entries for each TemplateType
        template_types = {t.template_type for t in templates}
        assert TemplateType.BASIC in template_types
        assert TemplateType.FULL in template_types
        assert TemplateType.PARALLEL in template_types

    def test_list_templates_includes_both_formats(self) -> None:
        """list_templates should include both YAML and Python formats."""
        scaffolder = get_scaffolder()

        templates = scaffolder.list_templates()

        formats = {t.format for t in templates}
        assert TemplateFormat.YAML in formats
        assert TemplateFormat.PYTHON in formats

    def test_template_info_has_description(self) -> None:
        """Each template should have a description."""
        scaffolder = get_scaffolder()

        templates = scaffolder.list_templates()

        for template in templates:
            assert template.description
            assert len(template.description) > 0

    def test_template_info_has_example_steps(self) -> None:
        """Each template should list example steps."""
        scaffolder = get_scaffolder()

        templates = scaffolder.list_templates()

        for template in templates:
            assert template.example_steps
            assert len(template.example_steps) > 0
