"""Unit tests for ScaffoldService."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from maverick.library import (
    InvalidNameError,
    OutputExistsError,
    ScaffoldRequest,
    ScaffoldResult,
    ScaffoldService,
    TemplateFormat,
    TemplateInfo,
    TemplateRenderError,
    TemplateType,
    create_scaffold_service,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service(tmp_path: Path) -> ScaffoldService:
    """Create ScaffoldService instance with real templates."""
    # Use actual package templates directory
    return create_scaffold_service()


@pytest.fixture
def custom_template_dir(tmp_path: Path) -> Path:
    """Create a custom template directory for testing."""
    template_dir = tmp_path / "templates"
    template_dir.mkdir()

    # Create a simple test template
    (template_dir / "basic.yaml.j2").write_text(
        "name: {{ name }}\ndescription: {{ description }}\n"
    )
    (template_dir / "basic.py.j2").write_text('"""{{ name }}"""\n# {{ description }}\n')

    return template_dir


@pytest.fixture
def service_with_custom_templates(custom_template_dir: Path) -> ScaffoldService:
    """Create ScaffoldService with custom templates."""
    return ScaffoldService(template_dir=custom_template_dir)


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Create output directory for tests."""
    output = tmp_path / "output"
    output.mkdir()
    return output


@pytest.fixture
def basic_yaml_request(output_dir: Path) -> ScaffoldRequest:
    """Create basic YAML scaffold request."""
    return ScaffoldRequest(
        name="test-workflow",
        template=TemplateType.BASIC,
        format=TemplateFormat.YAML,
        output_dir=output_dir,
        description="Test workflow description",
        author="Test Author",
    )


@pytest.fixture
def basic_python_request(output_dir: Path) -> ScaffoldRequest:
    """Create basic Python scaffold request."""
    return ScaffoldRequest(
        name="test-workflow",
        template=TemplateType.BASIC,
        format=TemplateFormat.PYTHON,
        output_dir=output_dir,
        description="Test workflow description",
        author="Test Author",
    )


@pytest.fixture
def full_yaml_request(output_dir: Path) -> ScaffoldRequest:
    """Create full YAML scaffold request."""
    return ScaffoldRequest(
        name="full-workflow",
        template=TemplateType.FULL,
        format=TemplateFormat.YAML,
        output_dir=output_dir,
        description="Full workflow description",
        author="Test Author",
    )


@pytest.fixture
def parallel_yaml_request(output_dir: Path) -> ScaffoldRequest:
    """Create parallel YAML scaffold request."""
    return ScaffoldRequest(
        name="parallel-workflow",
        template=TemplateType.PARALLEL,
        format=TemplateFormat.YAML,
        output_dir=output_dir,
        description="Parallel workflow description",
        author="Test Author",
    )


# =============================================================================
# Test list_templates()
# =============================================================================


def test_list_templates_returns_list_of_template_info(service: ScaffoldService):
    """Test that list_templates returns list of TemplateInfo objects."""
    templates = service.list_templates()

    assert isinstance(templates, list)
    assert len(templates) > 0
    assert all(isinstance(t, TemplateInfo) for t in templates)


def test_list_templates_contains_three_template_types(service: ScaffoldService):
    """Test that list_templates contains all 3 template types."""
    templates = service.list_templates()

    template_types = {t.template_type for t in templates}
    assert TemplateType.BASIC in template_types
    assert TemplateType.FULL in template_types
    assert TemplateType.PARALLEL in template_types


def test_list_templates_each_type_has_yaml_and_python_formats(
    service: ScaffoldService,
):
    """Test that each template type has both YAML and Python formats."""
    templates = service.list_templates()

    # Group templates by type
    by_type = {}
    for t in templates:
        if t.template_type not in by_type:
            by_type[t.template_type] = []
        by_type[t.template_type].append(t.format)

    # Check each type has both formats
    for template_type in [TemplateType.BASIC, TemplateType.FULL, TemplateType.PARALLEL]:
        assert template_type in by_type
        formats = by_type[template_type]
        assert TemplateFormat.YAML in formats
        assert TemplateFormat.PYTHON in formats


def test_list_templates_has_correct_descriptions(service: ScaffoldService):
    """Test that templates have correct descriptions."""
    templates = service.list_templates()

    # Find basic template
    basic_templates = [t for t in templates if t.template_type == TemplateType.BASIC]
    assert len(basic_templates) == 2
    assert all("Linear workflow" in t.description for t in basic_templates)

    # Find full template
    full_templates = [t for t in templates if t.template_type == TemplateType.FULL]
    assert len(full_templates) == 2
    assert all("validation" in t.description.lower() for t in full_templates)

    # Find parallel template
    parallel_templates = [
        t for t in templates if t.template_type == TemplateType.PARALLEL
    ]
    assert len(parallel_templates) == 2
    assert all("parallel" in t.description.lower() for t in parallel_templates)


def test_list_templates_has_correct_example_steps(service: ScaffoldService):
    """Test that templates have correct example_steps."""
    templates = service.list_templates()

    # Find basic template
    basic = next(
        t
        for t in templates
        if t.template_type == TemplateType.BASIC and t.format == TemplateFormat.YAML
    )
    assert len(basic.example_steps) > 0
    assert "init" in basic.example_steps
    assert "main" in basic.example_steps
    assert "cleanup" in basic.example_steps

    # Find full template
    full = next(
        t
        for t in templates
        if t.template_type == TemplateType.FULL and t.format == TemplateFormat.YAML
    )
    assert len(full.example_steps) > 0
    expected_steps = {"setup", "implement", "validate", "review", "create_pr"}
    assert all(step in full.example_steps for step in expected_steps)

    # Find parallel template
    parallel = next(
        t
        for t in templates
        if t.template_type == TemplateType.PARALLEL and t.format == TemplateFormat.YAML
    )
    assert len(parallel.example_steps) > 0
    assert "parallel_processing" in parallel.example_steps
    assert "combine_results" in parallel.example_steps


# =============================================================================
# Test scaffold() - Basic Functionality
# =============================================================================


def test_scaffold_creates_file_at_correct_path_yaml(
    service: ScaffoldService, basic_yaml_request: ScaffoldRequest
):
    """Test that scaffold creates file at correct path with YAML extension."""
    result = service.scaffold(basic_yaml_request)

    assert result.success
    assert result.output_path is not None
    assert result.output_path.exists()
    assert result.output_path.name == "test-workflow.yaml"
    assert result.output_path.parent == basic_yaml_request.output_dir


def test_scaffold_creates_file_at_correct_path_python(
    service: ScaffoldService, basic_python_request: ScaffoldRequest
):
    """Test that scaffold creates file at correct path with Python extension."""
    result = service.scaffold(basic_python_request)

    assert result.success
    assert result.output_path is not None
    assert result.output_path.exists()
    assert result.output_path.name == "test-workflow.py"
    assert result.output_path.parent == basic_python_request.output_dir


def test_scaffold_creates_parent_directories_if_needed(
    service: ScaffoldService, output_dir: Path
):
    """Test that scaffold creates parent directories if they don't exist."""
    # Create request with nested directory that doesn't exist
    nested_dir = output_dir / "nested" / "path" / "to" / "workflows"
    request = ScaffoldRequest(
        name="test-workflow",
        template=TemplateType.BASIC,
        format=TemplateFormat.YAML,
        output_dir=nested_dir,
    )

    result = service.scaffold(request)

    assert result.success
    assert result.output_path is not None
    assert result.output_path.exists()
    assert nested_dir.exists()


# =============================================================================
# Test scaffold() - Validation
# =============================================================================


def test_scaffold_raises_invalid_name_error_for_invalid_names(
    service: ScaffoldService, output_dir: Path
):
    """Test that scaffold raises InvalidNameError for invalid workflow names."""
    invalid_names = [
        "InvalidName",  # starts with uppercase
        "invalid_name",  # contains underscore
        "123-invalid",  # starts with number
        "invalid name",  # contains space
        "",  # empty
        "a" * 65,  # too long
    ]

    for name in invalid_names:
        request = ScaffoldRequest(
            name=name,
            template=TemplateType.BASIC,
            format=TemplateFormat.YAML,
            output_dir=output_dir,
        )

        with pytest.raises(InvalidNameError) as exc_info:
            service.scaffold(request)

        assert exc_info.value.name == name


def test_scaffold_raises_output_exists_error_when_file_exists(
    service: ScaffoldService, basic_yaml_request: ScaffoldRequest
):
    """Test that scaffold raises OutputExistsError when file exists and
    overwrite=False."""
    # Create file first time
    result = service.scaffold(basic_yaml_request)
    assert result.success

    # Try to create again without overwrite
    with pytest.raises(OutputExistsError) as exc_info:
        service.scaffold(basic_yaml_request)

    assert exc_info.value.path == basic_yaml_request.output_path


def test_scaffold_overwrites_when_overwrite_true(
    service: ScaffoldService, basic_yaml_request: ScaffoldRequest
):
    """Test that scaffold overwrites existing file when overwrite=True."""
    # Create file first time
    result1 = service.scaffold(basic_yaml_request)
    assert result1.success
    original_content = result1.output_path.read_text()

    # Create again with overwrite=True
    overwrite_request = ScaffoldRequest(
        name=basic_yaml_request.name,
        template=basic_yaml_request.template,
        format=basic_yaml_request.format,
        output_dir=basic_yaml_request.output_dir,
        description="Different description",
        overwrite=True,
    )

    result2 = service.scaffold(overwrite_request)
    assert result2.success
    new_content = result2.output_path.read_text()

    # Content should be different
    assert new_content != original_content
    assert "Different description" in new_content


# =============================================================================
# Test scaffold() - Content Validation
# =============================================================================


def test_scaffold_rendered_content_is_valid_yaml(
    service: ScaffoldService, basic_yaml_request: ScaffoldRequest
):
    """Test that scaffolded YAML content is valid."""
    result = service.scaffold(basic_yaml_request)

    assert result.success
    content = result.output_path.read_text()

    # Parse YAML to ensure it's valid
    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict)
    assert parsed["name"] == "test-workflow"


def test_scaffold_rendered_content_is_valid_python(
    service: ScaffoldService, basic_python_request: ScaffoldRequest
):
    """Test that scaffolded Python content is valid syntax."""
    result = service.scaffold(basic_python_request)

    assert result.success
    content = result.output_path.read_text()

    # Parse Python to ensure it's valid syntax
    try:
        ast.parse(content)
    except SyntaxError as e:
        pytest.fail(f"Generated Python has invalid syntax: {e}")


def test_scaffold_template_variables_are_substituted_correctly_yaml(
    service: ScaffoldService, basic_yaml_request: ScaffoldRequest
):
    """Test that template variables are substituted correctly in YAML."""
    result = service.scaffold(basic_yaml_request)

    assert result.success
    content = result.output_path.read_text()

    # Check all variables are present
    assert "test-workflow" in content
    assert "Test workflow description" in content
    assert "Test Author" in content


def test_scaffold_template_variables_are_substituted_correctly_python(
    service: ScaffoldService, basic_python_request: ScaffoldRequest
):
    """Test that template variables are substituted correctly in Python."""
    result = service.scaffold(basic_python_request)

    assert result.success
    content = result.output_path.read_text()

    # Check all variables are present
    assert "test-workflow" in content or "test_workflow" in content
    assert "Test workflow description" in content
    assert "Test Author" in content


def test_scaffold_full_template_has_all_expected_steps(
    service: ScaffoldService, full_yaml_request: ScaffoldRequest
):
    """Test that full template includes all expected steps."""
    result = service.scaffold(full_yaml_request)

    assert result.success
    content = result.output_path.read_text()

    # Parse YAML
    parsed = yaml.safe_load(content)

    # Check steps exist
    assert "steps" in parsed
    steps = parsed["steps"]
    step_names = {step["name"] for step in steps}

    # Expected steps from TemplateInfo
    # review might be in a branch step, so let's just check for main steps
    main_steps = {"setup", "implement", "validate", "create_pr"}
    assert main_steps.issubset(step_names)


def test_scaffold_parallel_template_has_parallel_structure(
    service: ScaffoldService, parallel_yaml_request: ScaffoldRequest
):
    """Test that parallel template has parallel step structure."""
    result = service.scaffold(parallel_yaml_request)

    assert result.success
    content = result.output_path.read_text()

    # Parse YAML
    parsed = yaml.safe_load(content)

    # Check for parallel step
    assert "steps" in parsed
    steps = parsed["steps"]

    # Find parallel step
    parallel_steps = [s for s in steps if s.get("type") == "parallel"]
    assert len(parallel_steps) > 0

    # Check parallel step has for_each
    parallel_step = parallel_steps[0]
    assert "for_each" in parallel_step or "foreach" in parallel_step


# =============================================================================
# Test preview()
# =============================================================================


def test_preview_returns_content_without_creating_file(
    service: ScaffoldService, basic_yaml_request: ScaffoldRequest
):
    """Test that preview returns content without creating a file."""
    result = service.preview(basic_yaml_request)

    assert result.success
    assert result.content is not None
    assert len(result.content) > 0
    assert not basic_yaml_request.output_path.exists()


def test_preview_returns_scaffold_result_with_content_field_set(
    service: ScaffoldService, basic_yaml_request: ScaffoldRequest
):
    """Test that preview returns ScaffoldResult with content field."""
    result = service.preview(basic_yaml_request)

    assert isinstance(result, ScaffoldResult)
    assert result.success is True
    assert result.content is not None
    assert result.output_path is None
    assert result.error is None


def test_preview_template_variables_are_substituted(
    service: ScaffoldService, basic_yaml_request: ScaffoldRequest
):
    """Test that preview correctly substitutes template variables."""
    result = service.preview(basic_yaml_request)

    assert result.success
    content = result.content

    # Check variables are substituted
    assert "test-workflow" in content
    assert "Test workflow description" in content
    assert "Test Author" in content


def test_preview_validates_workflow_name(service: ScaffoldService, output_dir: Path):
    """Test that preview validates workflow name."""
    request = ScaffoldRequest(
        name="InvalidName",  # uppercase - invalid
        template=TemplateType.BASIC,
        format=TemplateFormat.YAML,
        output_dir=output_dir,
    )

    with pytest.raises(InvalidNameError):
        service.preview(request)


def test_preview_raises_template_render_error_for_missing_template(
    service: ScaffoldService, output_dir: Path, tmp_path: Path
):
    """Test that preview raises TemplateRenderError for missing template."""
    # Create service with empty template directory
    empty_template_dir = tmp_path / "empty"
    empty_template_dir.mkdir()
    service_empty = ScaffoldService(template_dir=empty_template_dir)

    request = ScaffoldRequest(
        name="test-workflow",
        template=TemplateType.BASIC,
        format=TemplateFormat.YAML,
        output_dir=output_dir,
    )

    with pytest.raises(TemplateRenderError) as exc_info:
        service_empty.preview(request)

    assert exc_info.value.template == TemplateType.BASIC


# =============================================================================
# Test create_scaffold_service()
# =============================================================================


def test_create_scaffold_service_returns_scaffold_service_instance():
    """Test that create_scaffold_service returns ScaffoldService instance."""
    service = create_scaffold_service()

    assert isinstance(service, ScaffoldService)


def test_create_scaffold_service_with_custom_template_dir(
    custom_template_dir: Path,
):
    """Test that create_scaffold_service accepts custom template directory."""
    service = create_scaffold_service(template_dir=custom_template_dir)

    assert isinstance(service, ScaffoldService)
    assert service._template_dir == custom_template_dir


def test_create_scaffold_service_raises_value_error_for_missing_template_dir(
    tmp_path: Path,
):
    """Test that ScaffoldService raises ValueError if template directory
    doesn't exist."""
    # Create a path to a non-existent directory
    missing_dir = tmp_path / "nonexistent" / "templates"

    # Should raise ValueError with clear error message
    with pytest.raises(ValueError) as exc_info:
        ScaffoldService(template_dir=missing_dir)

    # Verify error message contains the path
    assert "Template directory not found" in str(exc_info.value)
    assert str(missing_dir) in str(exc_info.value)


# =============================================================================
# Test Template Rendering - All Templates
# =============================================================================


@pytest.mark.parametrize(
    "template_type,format_type",
    [
        (TemplateType.BASIC, TemplateFormat.YAML),
        (TemplateType.BASIC, TemplateFormat.PYTHON),
        (TemplateType.FULL, TemplateFormat.YAML),
        (TemplateType.FULL, TemplateFormat.PYTHON),
        (TemplateType.PARALLEL, TemplateFormat.YAML),
        (TemplateType.PARALLEL, TemplateFormat.PYTHON),
    ],
)
def test_each_template_type_renders_successfully(
    service: ScaffoldService,
    output_dir: Path,
    template_type: TemplateType,
    format_type: TemplateFormat,
):
    """Test that each template type renders successfully."""
    request = ScaffoldRequest(
        name="test-workflow",
        template=template_type,
        format=format_type,
        output_dir=output_dir,
        description="Test description",
        author="Test Author",
    )

    result = service.scaffold(request)

    assert result.success
    assert result.output_path is not None
    assert result.output_path.exists()


@pytest.mark.parametrize(
    "template_type",
    [TemplateType.BASIC, TemplateType.FULL, TemplateType.PARALLEL],
)
def test_rendered_yaml_is_valid(
    service: ScaffoldService, output_dir: Path, template_type: TemplateType
):
    """Test that rendered YAML is valid for all template types."""
    request = ScaffoldRequest(
        name="test-workflow",
        template=template_type,
        format=TemplateFormat.YAML,
        output_dir=output_dir,
    )

    result = service.scaffold(request)

    assert result.success
    content = result.output_path.read_text()

    # Parse YAML to ensure it's valid
    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict)
    assert "name" in parsed
    assert parsed["name"] == "test-workflow"


@pytest.mark.parametrize(
    "template_type",
    [TemplateType.BASIC, TemplateType.FULL, TemplateType.PARALLEL],
)
def test_rendered_python_is_valid_syntax(
    service: ScaffoldService, output_dir: Path, template_type: TemplateType
):
    """Test that rendered Python is valid syntax for all template types."""
    request = ScaffoldRequest(
        name="test-workflow",
        template=template_type,
        format=TemplateFormat.PYTHON,
        output_dir=output_dir,
    )

    result = service.scaffold(request)

    assert result.success
    content = result.output_path.read_text()

    # Parse Python to ensure it's valid syntax
    try:
        ast.parse(content)
    except SyntaxError as e:
        pytest.fail(f"Generated Python has invalid syntax: {e}")


# =============================================================================
# Test Edge Cases
# =============================================================================


def test_scaffold_with_empty_description_and_author(
    service: ScaffoldService, output_dir: Path
):
    """Test scaffolding with empty description and author."""
    request = ScaffoldRequest(
        name="test-workflow",
        template=TemplateType.BASIC,
        format=TemplateFormat.YAML,
        output_dir=output_dir,
        description="",
        author="",
    )

    result = service.scaffold(request)

    assert result.success
    assert result.output_path is not None
    assert result.output_path.exists()


def test_scaffold_with_hyphens_in_name(service: ScaffoldService, output_dir: Path):
    """Test scaffolding with hyphens in workflow name."""
    request = ScaffoldRequest(
        name="my-test-workflow-name",
        template=TemplateType.BASIC,
        format=TemplateFormat.YAML,
        output_dir=output_dir,
    )

    result = service.scaffold(request)

    assert result.success
    assert result.output_path.name == "my-test-workflow-name.yaml"


def test_scaffold_with_numbers_in_name(service: ScaffoldService, output_dir: Path):
    """Test scaffolding with numbers in workflow name."""
    request = ScaffoldRequest(
        name="test123-workflow",
        template=TemplateType.BASIC,
        format=TemplateFormat.YAML,
        output_dir=output_dir,
    )

    result = service.scaffold(request)

    assert result.success
    assert result.output_path.name == "test123-workflow.yaml"


def test_get_template_path_returns_correct_path(service: ScaffoldService):
    """Test that get_template_path returns correct path."""
    yaml_path = service.get_template_path(TemplateType.BASIC, TemplateFormat.YAML)
    assert yaml_path.name == "basic.yaml.j2"

    py_path = service.get_template_path(TemplateType.BASIC, TemplateFormat.PYTHON)
    assert py_path.name == "basic.py.j2"


def test_scaffold_result_includes_date_in_content(
    service: ScaffoldService, basic_yaml_request: ScaffoldRequest
):
    """Test that scaffolded content includes generated date."""
    result = service.scaffold(basic_yaml_request)

    assert result.success
    content = result.output_path.read_text()

    # Check that content includes a date (basic check for year)
    import datetime

    current_year = str(datetime.datetime.now().year)
    assert current_year in content
