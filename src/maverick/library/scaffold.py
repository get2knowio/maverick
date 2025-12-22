"""Workflow Scaffolding Models and Exceptions.

This module provides the data models, exceptions, and helper functions for
template-based workflow scaffolding. It defines the public API for creating
new workflow files from templates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

# =============================================================================
# Enums
# =============================================================================


class TemplateType(str, Enum):
    """Scaffolding template categories.

    Values:
        BASIC: Linear workflow with few steps (FR-019).
        FULL: Complete workflow with validation/review/PR (FR-020).
        PARALLEL: Demonstrates parallel step interface (FR-021).
    """

    BASIC = "basic"
    FULL = "full"
    PARALLEL = "parallel"


class TemplateFormat(str, Enum):
    """Output format for scaffolded workflows.

    Values:
        YAML: YAML workflow file (default per FR-022).
        PYTHON: Python workflow function.
    """

    YAML = "yaml"
    PYTHON = "python"


# =============================================================================
# Data Transfer Objects
# =============================================================================


@dataclass(frozen=True, slots=True)
class TemplateInfo:
    """Information about an available template.

    Attributes:
        template_type: Template category.
        format: Output format.
        description: Human-readable template description.
        example_steps: List of example step names included.
    """

    template_type: TemplateType
    format: TemplateFormat
    description: str
    example_steps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScaffoldRequest:
    """Request to scaffold a new workflow.

    Attributes:
        name: Workflow name (must match naming convention).
        template: Template to use.
        format: Output format (YAML default).
        output_dir: Target directory for output file.
        description: Optional workflow description.
        author: Optional author name.
        overwrite: Allow overwriting existing file.
    """

    name: str
    template: TemplateType
    format: TemplateFormat
    output_dir: Path
    description: str = ""
    author: str = ""
    overwrite: bool = False

    @property
    def output_path(self) -> Path:
        """Compute output file path based on format.

        Returns:
            Path to output file with appropriate extension (.yaml or .py).
        """
        ext = ".yaml" if self.format == TemplateFormat.YAML else ".py"
        return self.output_dir / f"{self.name}{ext}"


@dataclass(frozen=True, slots=True)
class ScaffoldResult:
    """Result of scaffolding operation.

    Attributes:
        success: Whether scaffolding succeeded.
        output_path: Path to generated file (if success).
        content: Generated content (for preview mode).
        error: Error message (if not success).
    """

    success: bool
    output_path: Path | None = None
    content: str | None = None
    error: str | None = None


# =============================================================================
# Exceptions
# =============================================================================


class ScaffoldError(Exception):
    """Base exception for scaffolding errors."""

    pass


class InvalidNameError(ScaffoldError):
    """Raised when workflow name is invalid.

    Attributes:
        name: The invalid name.
        reason: Why the name is invalid.
    """

    def __init__(self, name: str, reason: str) -> None:
        """Initialize invalid name error.

        Args:
            name: The invalid workflow name.
            reason: Why the name is invalid.
        """
        self.name = name
        self.reason = reason
        super().__init__(f"Invalid workflow name '{name}': {reason}")


class OutputExistsError(ScaffoldError):
    """Raised when output path already exists.

    Attributes:
        path: The existing path.
    """

    def __init__(self, path: Path) -> None:
        """Initialize output exists error.

        Args:
            path: The path that already exists.
        """
        self.path = path
        super().__init__(f"Output path already exists: {path}")


class TemplateRenderError(ScaffoldError):
    """Raised when template rendering fails.

    Attributes:
        template: Template that failed.
        cause: Underlying error.
    """

    def __init__(self, template: TemplateType, cause: str) -> None:
        """Initialize template render error.

        Args:
            template: The template type that failed to render.
            cause: The underlying error message.
        """
        self.template = template
        self.cause = cause
        super().__init__(f"Failed to render {template.value} template: {cause}")


# =============================================================================
# Helper Functions
# =============================================================================


def validate_workflow_name(name: str) -> None:
    """Validate workflow name against naming convention.

    Names must:
    - Start with a lowercase letter
    - Contain only lowercase letters, numbers, and hyphens
    - Be between 1 and 64 characters

    Pattern: ^[a-z][a-z0-9-]{0,63}$

    Args:
        name: Workflow name to validate.

    Raises:
        InvalidNameError: If name is invalid with specific reason.
    """
    pattern = r"^[a-z][a-z0-9-]{0,63}$"

    if not name:
        raise InvalidNameError(name, "name cannot be empty")

    if len(name) > 64:
        raise InvalidNameError(name, "must be 64 characters or less")

    if not name[0].islower() or not name[0].isalpha():
        raise InvalidNameError(name, "must start with lowercase letter")

    if not re.match(pattern, name):
        raise InvalidNameError(
            name, "must contain only lowercase letters, numbers, and hyphens"
        )


def get_default_output_dir() -> Path:
    """Get default output directory for scaffolded workflows.

    Returns:
        Path to .maverick/workflows/ in current working directory.
    """
    return Path.cwd() / ".maverick" / "workflows"


# =============================================================================
# Service Implementation
# =============================================================================


class ScaffoldService:
    """Template-based workflow scaffolding service.

    This service renders Jinja2 templates to create new workflow files.
    """

    def __init__(self, template_dir: Path | None = None) -> None:
        """Initialize scaffold service.

        Args:
            template_dir: Directory containing Jinja2 templates.
                         If None, uses package templates directory.

        Raises:
            ValueError: If template directory does not exist.
        """
        if template_dir is None:
            # Use package templates directory
            template_dir = Path(__file__).parent / "templates"

        # Validate template directory exists early
        if not template_dir.exists():
            raise ValueError(f"Template directory not found: {template_dir}")

        self._template_dir = template_dir

        # Template metadata
        self._templates = {
            (TemplateType.BASIC, TemplateFormat.YAML): TemplateInfo(
                template_type=TemplateType.BASIC,
                format=TemplateFormat.YAML,
                description="Linear workflow with few steps",
                example_steps=("init", "main", "cleanup"),
            ),
            (TemplateType.BASIC, TemplateFormat.PYTHON): TemplateInfo(
                template_type=TemplateType.BASIC,
                format=TemplateFormat.PYTHON,
                description="Linear workflow with few steps (Python)",
                example_steps=("init", "main", "cleanup"),
            ),
            (TemplateType.FULL, TemplateFormat.YAML): TemplateInfo(
                template_type=TemplateType.FULL,
                format=TemplateFormat.YAML,
                description="Complete workflow with validation/review/PR",
                example_steps=("setup", "implement", "validate", "review", "create_pr"),
            ),
            (TemplateType.FULL, TemplateFormat.PYTHON): TemplateInfo(
                template_type=TemplateType.FULL,
                format=TemplateFormat.PYTHON,
                description="Complete workflow with validation/review/PR (Python)",
                example_steps=("setup", "implement", "validate", "review", "create_pr"),
            ),
            (TemplateType.PARALLEL, TemplateFormat.YAML): TemplateInfo(
                template_type=TemplateType.PARALLEL,
                format=TemplateFormat.YAML,
                description="Demonstrates parallel step interface",
                example_steps=("parallel_processing", "combine_results"),
            ),
            (TemplateType.PARALLEL, TemplateFormat.PYTHON): TemplateInfo(
                template_type=TemplateType.PARALLEL,
                format=TemplateFormat.PYTHON,
                description="Demonstrates parallel step interface (Python)",
                example_steps=("parallel_processing", "combine_results"),
            ),
        }

    def list_templates(self) -> list[TemplateInfo]:
        """List all available templates.

        Returns:
            List of template information objects.
        """
        return list(self._templates.values())

    def preview(self, request: ScaffoldRequest) -> ScaffoldResult:
        """Preview generated content without writing.

        Args:
            request: Scaffold request parameters.

        Returns:
            ScaffoldResult with content field set.

        Raises:
            InvalidNameError: If workflow name is invalid.
            TemplateRenderError: If template rendering fails.
        """
        # Validate workflow name
        validate_workflow_name(request.name)

        # Render template
        try:
            content = self._render_template(request)
            return ScaffoldResult(success=True, content=content)
        except Exception as e:
            raise TemplateRenderError(request.template, str(e)) from e

    def scaffold(self, request: ScaffoldRequest) -> ScaffoldResult:
        """Generate a new workflow from template.

        Args:
            request: Scaffold request parameters.

        Returns:
            ScaffoldResult with success/failure information.

        Raises:
            InvalidNameError: If workflow name is invalid.
            OutputExistsError: If output exists and overwrite=False.
            TemplateRenderError: If template rendering fails.
        """
        # Validate workflow name
        validate_workflow_name(request.name)

        # Check if output exists
        if request.output_path.exists() and not request.overwrite:
            raise OutputExistsError(request.output_path)

        # Render template
        try:
            content = self._render_template(request)
        except Exception as e:
            raise TemplateRenderError(request.template, str(e)) from e

        # Create parent directories
        request.output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        try:
            request.output_path.write_text(content)
            return ScaffoldResult(success=True, output_path=request.output_path)
        except Exception as e:
            return ScaffoldResult(
                success=False,
                error=f"Failed to write file: {e}",
            )

    def _render_template(self, request: ScaffoldRequest) -> str:
        """Render template with request parameters.

        Args:
            request: Scaffold request parameters.

        Returns:
            Rendered template content.

        Raises:
            TemplateRenderError: If template file not found or rendering fails.
        """
        import jinja2

        # Get template path
        template_path = self.get_template_path(request.template, request.format)

        if not template_path.exists():
            raise TemplateRenderError(
                request.template,
                f"Template file not found: {template_path}",
            )

        # Load and render template
        try:
            template_content = template_path.read_text()

            # Use standard Jinja2 Template
            template = jinja2.Template(template_content)

            # Prepare template variables
            variables = {
                "name": request.name,
                "description": request.description,
                "author": request.author,
                "date": datetime.now().strftime("%Y-%m-%d"),
            }

            return template.render(**variables)
        except jinja2.TemplateError as e:
            raise TemplateRenderError(request.template, str(e)) from e

    def get_template_path(self, template: TemplateType, format: TemplateFormat) -> Path:
        """Get path to template file.

        Args:
            template: Template type.
            format: Output format.

        Returns:
            Path to Jinja2 template file.
        """
        ext = "yaml.j2" if format == TemplateFormat.YAML else "py.j2"
        return self._template_dir / f"{template.value}.{ext}"


def create_scaffold_service(template_dir: Path | None = None) -> ScaffoldService:
    """Create a scaffold service instance.

    Args:
        template_dir: Directory containing Jinja2 templates.
                     If None, uses package templates directory.

    Returns:
        Configured ScaffoldService instance.
    """
    return ScaffoldService(template_dir=template_dir)
