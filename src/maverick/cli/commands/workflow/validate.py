"""Workflow validate and validate-all subcommands.

Provides validation of individual workflow files and batch validation
of all discovered workflows.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.common import (
    create_registered_registry,
    get_discovery_result,
)
from maverick.cli.context import ExitCode
from maverick.cli.output import format_error
from maverick.dsl.serialization.parser import parse_workflow
from maverick.logging import get_logger

from ._group import workflow


@workflow.command("validate-all")
@click.option(
    "--source",
    type=click.Choice(["all", "builtin", "user", "project"]),
    default="all",
    help="Filter by source location.",
)
@click.option(
    "--strict/--no-strict",
    default=False,
    help="Strict mode checks all references exist.",
)
@click.pass_context
def workflow_validate_all(ctx: click.Context, source: str, strict: bool) -> None:
    """Validate all discovered workflows.

    Checks all workflows for syntax errors, schema violations, and optionally
    validates that all component references exist.

    Examples:
        maverick workflow validate-all
        maverick workflow validate-all --source builtin
        maverick workflow validate-all --strict
    """
    logger = get_logger(__name__)

    try:
        from maverick.dsl.errors import (
            ReferenceResolutionError,
            UnsupportedVersionError,
            WorkflowParseError,
        )

        # Run discovery
        discovery_result = get_discovery_result(ctx)

        # Filter workflows by source if specified
        if source == "all":
            workflows_to_validate = discovery_result.workflows
        else:
            workflows_to_validate = discovery_result.filter_by_source(source)

        if not workflows_to_validate:
            click.echo(f"No workflows found to validate from source '{source}'")
            raise SystemExit(ExitCode.SUCCESS)

        # Create registry if strict mode
        registry = None
        if strict:
            registry = create_registered_registry(strict=True)

        # Validate each workflow
        valid_count = 0
        invalid_count = 0
        errors: list[dict[str, str]] = []

        click.echo(f"Validating {len(workflows_to_validate)} workflow(s)...")
        click.echo()

        for dw in workflows_to_validate:
            wf = dw.workflow
            try:
                # Re-parse to validate (discovery uses validate_only=True)
                content = dw.file_path.read_text(encoding="utf-8")
                parse_workflow(content, registry=registry, validate_only=not strict)

                # Success
                valid_count += 1
                status = click.style("\u2713", fg="green", bold=True)
                click.echo(f"{status} {wf.name} ({dw.source})")

            except (
                WorkflowParseError,
                UnsupportedVersionError,
                ReferenceResolutionError,
            ) as e:
                # Validation failed
                invalid_count += 1
                status = click.style("\u2717", fg="red", bold=True)
                click.echo(f"{status} {wf.name} ({dw.source})")

                # Record error details
                error_details = {
                    "name": wf.name,
                    "source": dw.source,
                    "file": str(dw.file_path),
                    "error": str(e),
                }
                errors.append(error_details)

        # Show summary
        click.echo()
        click.echo(click.style("Validation Summary:", bold=True))
        click.echo(f"  Valid: {click.style(str(valid_count), fg='green')}")
        click.echo(f"  Invalid: {click.style(str(invalid_count), fg='red')}")

        # Show details for invalid workflows
        if errors:
            click.echo()
            click.echo(click.style("Validation Errors:", bold=True, fg="red"))
            for error in errors:
                click.echo(f"\n  {error['name']} ({error['source']}):")
                click.echo(f"    File: {error['file']}")
                click.echo(f"    Error: {error['error']}")

        # Exit with failure if any validation errors
        if invalid_count > 0:
            raise SystemExit(ExitCode.FAILURE)
        else:
            raise SystemExit(ExitCode.SUCCESS)

    except SystemExit:
        raise
    except Exception as e:
        logger.exception("Unexpected error in workflow validate-all command")
        error_msg = format_error(f"Failed to validate workflows: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e


@workflow.command("validate")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--strict/--no-strict",
    default=True,
    help="Strict mode checks all references exist.",
)
@click.option(
    "--no-semantic",
    is_flag=True,
    default=False,
    help="Skip semantic validation (syntax-only).",
)
@click.pass_context
def workflow_validate(
    ctx: click.Context, file: Path, strict: bool, no_semantic: bool
) -> None:
    """Validate workflow YAML syntax, schema, and semantics.

    By default, performs full validation including:
    - YAML syntax checking
    - Schema validation (Pydantic model)
    - Expression syntax validation
    - Semantic validation (component references, step dependencies, etc.)

    Use --no-strict to skip reference resolution.
    Use --no-semantic to skip semantic validation entirely (not recommended).

    Examples:
        maverick workflow validate my-workflow.yaml
        maverick workflow validate my-workflow.yaml --no-strict
        maverick workflow validate my-workflow.yaml --no-semantic
    """
    logger = get_logger(__name__)

    try:
        from maverick.dsl.errors import (
            ReferenceResolutionError,
            UnsupportedVersionError,
            WorkflowParseError,
        )

        # Read workflow file
        content = file.read_text(encoding="utf-8")

        # Parse workflow
        registry = None
        if strict:
            # Create a registry with all built-in components registered
            # In strict mode, we want to catch reference errors
            registry = create_registered_registry(strict=True)

        # Parse with optional semantic validation
        validate_semantic = not no_semantic and registry is not None

        workflow_obj = parse_workflow(
            content,
            registry=registry,
            validate_only=not strict,
            validate_semantic=validate_semantic,
        )

        # If we get here, validation succeeded
        click.echo(f"Workflow '{workflow_obj.name}' is valid.")
        click.echo(f"  Version: {workflow_obj.version}")
        click.echo(f"  Steps: {len(workflow_obj.steps)}")
        click.echo(f"  Inputs: {len(workflow_obj.inputs)}")

        # Show validation mode
        validation_modes = []
        if not strict:
            validation_modes.append("Reference resolution skipped (use --strict)")
        if no_semantic:
            validation_modes.append(
                "Semantic validation skipped (use without --no-semantic)"
            )

        if validation_modes:
            click.echo("\nNote: " + "; ".join(validation_modes))

    except WorkflowParseError as e:
        error_details = []
        if e.line_number:
            error_details.append(f"Line: {e.line_number}")

        error_msg = format_error(
            f"Workflow parsing failed: {e.message}",
            details=error_details,
        )
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e

    except UnsupportedVersionError as e:
        error_msg = format_error(
            f"Unsupported workflow version: {e.requested_version}",
            suggestion=f"Use one of: {', '.join(e.supported_versions)}",
        )
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e

    except ReferenceResolutionError as e:
        error_details = [
            f"Reference type: {e.reference_type}",
            f"Reference name: {e.reference_name}",
        ]
        if e.available_names:
            error_details.append(f"Available: {', '.join(e.available_names[:5])}")

        error_msg = format_error(
            "Unresolved component reference",
            details=error_details,
            suggestion="Register the component or use --no-strict to skip validation",
        )
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e

    except SystemExit:
        raise
    except Exception as e:
        logger.exception("Unexpected error in workflow validate command")
        error_msg = format_error(f"Failed to validate workflow: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e
