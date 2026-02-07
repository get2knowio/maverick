"""Workflow new subcommand.

Scaffolds new workflow files from built-in templates with support
for YAML and (deprecated) Python output formats.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.context import ExitCode
from maverick.cli.output import format_error
from maverick.logging import get_logger

from ._group import workflow


@workflow.command("new")
@click.argument("name")
@click.option(
    "-t",
    "--template",
    type=click.Choice(["basic", "full", "parallel"]),
    default="basic",
    help="Template type.",
)
@click.option(
    "-f",
    "--format",
    "fmt",
    type=click.Choice(["yaml", "python"]),
    default="yaml",
    help="Output format (default: yaml). Note: Python format is deprecated.",
)
@click.option(
    "-o",
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: .maverick/workflows/).",
)
@click.option(
    "-d",
    "--description",
    default="",
    help="Workflow description.",
)
@click.option(
    "-a",
    "--author",
    default="",
    help="Workflow author.",
)
@click.option(
    "--overwrite",
    is_flag=True,
    default=False,
    help="Overwrite existing file.",
)
@click.option(
    "--preview",
    is_flag=True,
    default=False,
    help="Preview generated content without writing.",
)
@click.pass_context
def workflow_new(
    ctx: click.Context,
    name: str,
    template: str,
    fmt: str,
    output_dir: Path | None,
    description: str,
    author: str,
    overwrite: bool,
    preview: bool,
) -> None:
    """Create a new workflow from a template.

    NAME is the workflow name (must be lowercase with hyphens).

    Templates:
        basic    - Simple linear workflow with few steps
        full     - Complete workflow with validation/review/PR
        parallel - Demonstrates parallel step interface

    Notes:
        Workflows are generated in YAML format by default.
        Default output directory is .maverick/workflows/.
        Python format (--format python) is deprecated and may be removed in a
        future version.

    Examples:
        maverick workflow new my-workflow
        maverick workflow new my-workflow --template full
        maverick workflow new my-workflow --template parallel
        maverick workflow new my-workflow --output-dir ./workflows
        maverick workflow new my-workflow --preview
    """
    logger = get_logger(__name__)

    try:
        from maverick.library import (
            InvalidNameError,
            OutputExistsError,
            ScaffoldRequest,
            TemplateFormat,
            TemplateRenderError,
            TemplateType,
            create_scaffold_service,
            get_default_output_dir,
        )

        # Warn if Python format is used (deprecated)
        if fmt == "python":
            warning_msg = click.style(
                "Warning: Python format is deprecated and may be removed in a "
                "future version. Please use YAML format (default).",
                fg="yellow",
            )
            click.echo(warning_msg, err=True)
            click.echo()

        # Create scaffold service
        service = create_scaffold_service()

        # Determine output directory
        if output_dir is None:
            output_dir = get_default_output_dir()

        # Create request
        request = ScaffoldRequest(
            name=name,
            template=TemplateType(template),
            format=TemplateFormat(fmt),
            output_dir=output_dir,
            description=description,
            author=author,
            overwrite=overwrite,
        )

        # Preview or scaffold
        if preview:
            result = service.preview(request)
            if result.success and result.content:
                click.echo(f"# Preview: {request.output_path}")
                click.echo()
                click.echo(result.content)
            else:
                error_msg = format_error(result.error or "Preview failed")
                click.echo(error_msg, err=True)
                raise SystemExit(ExitCode.FAILURE)
        else:
            result = service.scaffold(request)
            if result.success and result.output_path:
                click.echo(f"Created workflow: {result.output_path}")
                click.echo()
                click.echo("Next steps:")
                click.echo("  1. Edit the workflow file to add your steps")
                out_path = result.output_path
                click.echo(f"  2. Validate: maverick workflow validate {out_path}")
                click.echo(f"  3. Run: maverick workflow run {out_path}")
            else:
                error_msg = format_error(result.error or "Scaffold failed")
                click.echo(error_msg, err=True)
                raise SystemExit(ExitCode.FAILURE)

    except InvalidNameError as e:
        error_msg = format_error(
            f"Invalid workflow name: {e.name}",
            suggestion=e.reason,
        )
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e

    except OutputExistsError as e:
        error_msg = format_error(
            f"Output file already exists: {e.path}",
            suggestion="Use --overwrite to replace existing file",
        )
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e

    except TemplateRenderError as e:
        error_msg = format_error(
            f"Failed to render template: {e.cause}",
        )
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e

    except Exception as e:
        logger.exception("Unexpected error in workflow new command")
        error_msg = format_error(f"Failed to create workflow: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e
