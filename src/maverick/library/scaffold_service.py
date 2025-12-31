"""Workflow Scaffolding Service Implementation.

This module provides the concrete implementation of the template-based workflow
scaffolding service. It uses Jinja2 templates to generate new workflow files
from predefined templates.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader, TemplateError, TemplateNotFound

from maverick.library.scaffold import (
    OutputExistsError,
    ScaffoldRequest,
    ScaffoldResult,
    TemplateFormat,
    TemplateInfo,
    TemplateRenderError,
    TemplateType,
    validate_workflow_name,
)


class ScaffoldService:
    """Service for scaffolding new workflows from Jinja2 templates.

    This service uses Jinja2's PackageLoader to load templates from the
    maverick.library.templates package. It supports generating workflows
    in both YAML and Python formats from three template types: basic, full,
    and parallel.

    Attributes:
        env: Jinja2 environment configured with PackageLoader.
    """

    def __init__(self) -> None:
        """Initialize the scaffold service with Jinja2 environment.

        Raises:
            ValueError: If template directory does not exist.
        """
        template_dir = Path(__file__).parent / "templates"
        if not template_dir.exists():
            raise ValueError(f"Template directory not found: {template_dir}")

        self.env = Environment(
            loader=PackageLoader("maverick.library", "templates"),
            autoescape=False,  # Don't escape workflow code
            keep_trailing_newline=True,  # Preserve newlines at end of templates
            # Use {{ }} for template variables (Jinja2 default)
            # Workflow expressions use ${{ }} which won't conflict
        )

    def list_templates(self) -> list[TemplateInfo]:
        """List all available workflow templates.

        Returns:
            List of TemplateInfo objects describing each available template.
            Includes both YAML and Python formats for each template type.
        """
        templates = [
            # Basic templates
            TemplateInfo(
                template_type=TemplateType.BASIC,
                format=TemplateFormat.YAML,
                description="Linear workflow with few steps for simple tasks",
                example_steps=("setup", "execute", "validate", "finalize"),
            ),
            TemplateInfo(
                template_type=TemplateType.BASIC,
                format=TemplateFormat.PYTHON,
                description="Linear workflow with few steps for simple tasks (Python)",
                example_steps=("setup", "execute", "validate", "finalize"),
            ),
            # Full templates
            TemplateInfo(
                template_type=TemplateType.FULL,
                format=TemplateFormat.YAML,
                description="Complete workflow with validation, review, PR patterns",
                example_steps=(
                    "init",
                    "implement",
                    "validate",
                    "review",
                    "create_pr",
                ),
            ),
            TemplateInfo(
                template_type=TemplateType.FULL,
                format=TemplateFormat.PYTHON,
                description="Complete workflow with validation, review, PR (Python)",
                example_steps=(
                    "init",
                    "implement",
                    "validate",
                    "review",
                    "create_pr",
                ),
            ),
            # Parallel templates
            TemplateInfo(
                template_type=TemplateType.PARALLEL,
                format=TemplateFormat.YAML,
                description="Demonstrates parallel step execution interface",
                example_steps=("setup", "parallel_tasks", "aggregate", "finalize"),
            ),
            TemplateInfo(
                template_type=TemplateType.PARALLEL,
                format=TemplateFormat.PYTHON,
                description="Demonstrates parallel step execution interface (Python)",
                example_steps=("setup", "parallel_tasks", "aggregate", "finalize"),
            ),
        ]
        return templates

    def scaffold(self, request: ScaffoldRequest) -> ScaffoldResult:
        """Generate a new workflow from template and write to disk.

        Args:
            request: Scaffold request containing workflow name, template type,
                format, output directory, and optional metadata.

        Returns:
            ScaffoldResult with success=True and output_path on success.

        Raises:
            InvalidNameError: If workflow name is invalid.
            OutputExistsError: If output path exists and overwrite=False.
            TemplateRenderError: If template rendering fails.
        """
        # Validate workflow name
        validate_workflow_name(request.name)

        # Check if output exists
        if request.output_path.exists() and not request.overwrite:
            raise OutputExistsError(request.output_path)

        # Render template content
        content = self._render_template(request)

        # Create output directory if needed
        request.output_dir.mkdir(parents=True, exist_ok=True)

        # Write to disk
        try:
            request.output_path.write_text(content, encoding="utf-8")
        except OSError as e:
            raise TemplateRenderError(
                request.template, f"Failed to write output file: {e}"
            ) from e

        return ScaffoldResult(success=True, output_path=request.output_path)

    def preview(self, request: ScaffoldRequest) -> ScaffoldResult:
        """Preview generated content without writing to disk.

        Args:
            request: Scaffold request containing workflow name, template type,
                format, and optional metadata.

        Returns:
            ScaffoldResult with success=True and content on success.

        Raises:
            InvalidNameError: If workflow name is invalid.
            TemplateRenderError: If template rendering fails.
        """
        # Validate workflow name
        validate_workflow_name(request.name)

        # Render template content
        content = self._render_template(request)

        return ScaffoldResult(success=True, content=content)

    def get_template_path(self, template: TemplateType, format: TemplateFormat) -> Path:
        """Get path to template file.

        Args:
            template: Template type (basic, full, parallel).
            format: Output format (yaml, python).

        Returns:
            Path to Jinja2 template file relative to templates directory.
        """
        ext = "yaml" if format == TemplateFormat.YAML else "py"
        filename = f"{template.value}.{ext}.j2"
        return Path(filename)

    def _render_template(self, request: ScaffoldRequest) -> str:
        """Render a Jinja2 template with the provided request context.

        Args:
            request: Scaffold request containing template parameters.

        Returns:
            Rendered template content as string.

        Raises:
            TemplateRenderError: If template loading or rendering fails.
        """
        from datetime import datetime

        # Get template filename
        template_path = self.get_template_path(request.template, request.format)
        template_name = str(template_path)

        try:
            # Load template
            template = self.env.get_template(template_name)

            # Render with context
            content = template.render(
                name=request.name,
                description=request.description,
                author=request.author,
                version="1.0",
                date=datetime.now().strftime("%Y-%m-%d"),
            )

            return content

        except TemplateNotFound as e:
            raise TemplateRenderError(
                request.template,
                f"Template file not found: {template_name}",
            ) from e
        except TemplateError as e:
            raise TemplateRenderError(
                request.template,
                f"Template rendering failed: {e}",
            ) from e


def create_scaffold_service() -> ScaffoldService:
    """Create a scaffold service instance.

    Returns:
        Configured ScaffoldService instance.
    """
    return ScaffoldService()
