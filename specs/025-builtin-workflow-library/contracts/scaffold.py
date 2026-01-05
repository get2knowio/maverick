"""Contract: Workflow Scaffolding API.

This module defines the public interface for template-based workflow scaffolding.
Implementation will be in maverick.library.scaffold.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
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
        """Compute output file path."""
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

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class InvalidNameError(ScaffoldError):
    """Raised when workflow name is invalid.

    Attributes:
        name: The invalid name.
        reason: Why the name is invalid.
    """

    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        self.reason = reason
        super().__init__(f"Invalid workflow name '{name}': {reason}")


class OutputExistsError(ScaffoldError):
    """Raised when output path already exists.

    Attributes:
        path: The existing path.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Output path already exists: {path}")


class TemplateRenderError(ScaffoldError):
    """Raised when template rendering fails.

    Attributes:
        template: Template that failed.
        cause: Underlying error.
    """

    def __init__(self, template: TemplateType, cause: str) -> None:
        self.template = template
        self.cause = cause
        super().__init__(f"Failed to render {template.value} template: {cause}")


# =============================================================================
# Service Protocol
# =============================================================================


class TemplateScaffolder(ABC):
    """Abstract base for workflow scaffolding service.

    Implementations render Jinja2 templates to create new workflows.
    """

    @abstractmethod
    def list_templates(self) -> list[TemplateInfo]:
        """List all available templates.

        Returns:
            List of template information objects.
        """
        ...

    @abstractmethod
    def preview(self, request: ScaffoldRequest) -> str:
        """Preview generated content without writing.

        Args:
            request: Scaffold request parameters.

        Returns:
            Generated content as string.

        Raises:
            InvalidNameError: If workflow name is invalid.
            TemplateRenderError: If template rendering fails.
        """
        ...

    @abstractmethod
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
        ...

    @abstractmethod
    def get_template_path(self, template: TemplateType, format: TemplateFormat) -> Path:
        """Get path to template file.

        Args:
            template: Template type.
            format: Output format.

        Returns:
            Path to Jinja2 template file.
        """
        ...


# =============================================================================
# Factory Functions
# =============================================================================


def create_scaffolder() -> TemplateScaffolder:
    """Create a template scaffolder instance.

    Returns:
        Configured TemplateScaffolder instance.
    """
    # Implementation will be in maverick.library.scaffold
    raise NotImplementedError("Implementation in maverick.library.scaffold")


def validate_workflow_name(name: str) -> None:
    """Validate workflow name against naming convention.

    Args:
        name: Workflow name to validate.

    Raises:
        InvalidNameError: If name is invalid.
    """
    import re

    pattern = r"^[a-z][a-z0-9-]{0,63}$"
    if not re.match(pattern, name):
        if not name:
            raise InvalidNameError(name, "name cannot be empty")
        if not name[0].islower():
            raise InvalidNameError(name, "must start with lowercase letter")
        if len(name) > 64:
            raise InvalidNameError(name, "must be 64 characters or less")
        raise InvalidNameError(
            name, "must contain only lowercase letters, numbers, and hyphens"
        )


def get_default_output_dir() -> Path:
    """Get default output directory for scaffolded workflows.

    Returns:
        Path to .maverick/workflows/ in current directory.
    """
    return Path.cwd() / ".maverick" / "workflows"
