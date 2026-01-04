from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.common import (
    cli_error_handler,
    create_registered_registry,
    get_discovery_result,
)
from maverick.cli.context import ExitCode, async_command
from maverick.cli.output import format_error, format_json, format_table
from maverick.dsl.serialization.parser import parse_workflow
from maverick.dsl.visualization import to_ascii, to_mermaid
from maverick.logging import get_logger


@click.group()
@click.option(
    "--registry",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to custom registry file.",
)
@click.option(
    "--lenient/--no-lenient",
    default=False,
    help="Lenient mode for unknown references.",
)
@click.pass_context
def workflow(
    ctx: click.Context,
    registry: Path | None,
    lenient: bool,
) -> None:
    """Manage DSL workflows."""
    # Store workflow-specific options in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["workflow_registry"] = registry
    ctx.obj["workflow_lenient"] = lenient


@workflow.command("list")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    help="Output format.",
)
@click.option(
    "--source",
    type=click.Choice(["all", "builtin", "user", "project"]),
    default="all",
    help="Filter by source location.",
)
@click.pass_context
def workflow_list(ctx: click.Context, fmt: str, source: str) -> None:
    """List all discovered workflows.

    Discovers workflows from builtin, user, and project locations with
    override precedence (project > user > builtin).

    Examples:
        maverick workflow list
        maverick workflow list --format json
        maverick workflow list --source builtin
    """
    import yaml

    logger = get_logger(__name__)

    try:
        # Run discovery (FR-014: call discover() when CLI initializes)
        discovery_result = get_discovery_result(ctx)

        # Filter workflows by source if specified
        if source == "all":
            discovered_workflows = discovery_result.workflows
        else:
            source_filter = source
            discovered_workflows = tuple(
                w for w in discovery_result.workflows if w.source == source_filter
            )

        if not discovered_workflows:
            if source != "all":
                click.echo(f"No workflows found from source '{source}'")
            else:
                click.echo("No workflows discovered")
            raise SystemExit(ExitCode.SUCCESS)

        # Build output data with source information
        workflows = []
        for dw in discovered_workflows:
            wf = dw.workflow
            workflows.append(
                {
                    "name": wf.name,
                    "description": wf.description or "(no description)",
                    "version": wf.version,
                    "source": dw.source,
                    "file": str(dw.file_path),
                    "overrides": [str(p) for p in dw.overrides] if dw.overrides else [],
                }
            )

        # Sort by name
        workflows.sort(key=lambda w: str(w["name"]))

        # Format output
        if fmt == "json":
            click.echo(format_json(workflows))
        elif fmt == "yaml":
            click.echo(yaml.dump(workflows, default_flow_style=False, sort_keys=False))
        else:
            # Table format with source column
            headers = ["Name", "Version", "Source", "Description"]
            rows = [
                [
                    str(wf["name"]),
                    str(wf["version"]),
                    str(wf["source"]),
                    str(wf["description"])[:40],
                ]
                for wf in workflows
            ]
            click.echo(format_table(headers, rows))

            # Show discovery stats
            click.echo()
            time_ms = discovery_result.discovery_time_ms
            click.echo(f"Discovered {len(workflows)} workflow(s) in {time_ms:.0f}ms")
            if discovery_result.skipped:
                skipped_count = len(discovery_result.skipped)
                click.echo(f"Skipped {skipped_count} file(s) with errors")

    except SystemExit:
        raise
    except Exception as e:
        logger.exception("Unexpected error in workflow list command")
        error_msg = format_error(f"Failed to list workflows: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e


@workflow.command("search")
@click.argument("query")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format.",
)
@click.pass_context
def workflow_search(ctx: click.Context, query: str, fmt: str) -> None:
    """Search workflows by name or description.

    QUERY is the search string (case-insensitive substring match).

    Examples:
        maverick workflow search validate
        maverick workflow search "code review"
        maverick workflow search fix --format json
    """
    logger = get_logger(__name__)

    try:
        # Run discovery
        discovery_result = get_discovery_result(ctx)

        # Search workflows
        matches = discovery_result.search_workflows(query)

        if not matches:
            click.echo(f"No workflows found matching '{query}'")
            raise SystemExit(ExitCode.SUCCESS)

        # Build output data
        workflows = []
        for dw in matches:
            wf = dw.workflow
            workflows.append(
                {
                    "name": wf.name,
                    "description": wf.description or "(no description)",
                    "version": wf.version,
                    "source": dw.source,
                    "file": str(dw.file_path),
                }
            )

        # Format output
        if fmt == "json":
            click.echo(format_json(workflows))
        else:
            # Table format
            headers = ["Name", "Version", "Source", "Description"]
            rows = [
                [
                    str(wf["name"]),
                    str(wf["version"]),
                    str(wf["source"]),
                    str(wf["description"])[:50],
                ]
                for wf in workflows
            ]
            click.echo(format_table(headers, rows))

            # Show summary
            click.echo()
            click.echo(f"Found {len(matches)} workflow(s) matching '{query}'")

    except SystemExit:
        raise
    except Exception as e:
        logger.exception("Unexpected error in workflow search command")
        error_msg = format_error(f"Failed to search workflows: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e


@workflow.command("info")
@click.argument("name")
@click.pass_context
def workflow_info(ctx: click.Context, name: str) -> None:
    """Display detailed workflow information including all versions.

    NAME is the workflow name to look up.

    Shows the active workflow (highest precedence) and any overridden versions.

    Examples:
        maverick workflow info fly
        maverick workflow info validate
    """
    logger = get_logger(__name__)

    try:
        # Run discovery
        discovery_result = get_discovery_result(ctx)

        # Get the active workflow
        discovered = discovery_result.get_workflow(name)

        if discovered is None:
            # Show available workflows in error message
            available = discovery_result.workflow_names
            if available:
                available_str = ", ".join(available[:5])
                if len(available) > 5:
                    available_str += f", ... ({len(available)} total)"
                suggestion = f"Available workflows: {available_str}"
            else:
                suggestion = "No workflows discovered. Check your workflow directories."

            error_msg = format_error(
                f"Workflow '{name}' not found",
                suggestion=suggestion,
            )
            click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE)

        # Get all versions of the workflow
        all_versions = discovery_result.get_all_with_name(name)

        # Display active workflow (first in precedence order)
        wf = discovered.workflow

        click.echo(click.style(f"Workflow: {wf.name}", bold=True))
        click.echo(f"Version: {wf.version}")
        click.echo(f"Description: {wf.description or '(no description)'}")
        click.echo()

        # Display source information
        click.echo(click.style("Active Version:", bold=True))
        source_label = {
            "builtin": "Built-in (packaged with Maverick)",
            "user": "User (~/.config/maverick/workflows/)",
            "project": "Project (.maverick/workflows/)",
        }.get(discovered.source, discovered.source)
        click.echo(f"  Source: {source_label}")
        click.echo(f"  File: {discovered.file_path}")
        click.echo()

        # Display all versions if there are overrides
        if len(all_versions) > 1:
            click.echo(click.style("All Versions:", bold=True))
            for i, (source, path) in enumerate(all_versions, 1):
                status = "ACTIVE" if i == 1 else "overridden"
                click.echo(f"  {i}. [{status}] {source}: {path}")
            click.echo()

        # Display inputs
        if wf.inputs:
            click.echo(click.style("Inputs:", bold=True))
            for input_name, input_def in wf.inputs.items():
                required_str = "required" if input_def.required else "optional"
                default_str = (
                    f", default: {input_def.default}"
                    if input_def.default is not None
                    else ""
                )
                desc_str = (
                    f" - {input_def.description}" if input_def.description else ""
                )
                click.echo(
                    f"  {input_name} ({input_def.type.value}, "
                    f"{required_str}{default_str}){desc_str}"
                )
            click.echo()

        # Display step summary
        click.echo(click.style(f"Steps ({len(wf.steps)}):", bold=True))
        for i, step in enumerate(wf.steps, 1):
            click.echo(f"  {i}. {step.name} ({step.type.value})")
            if step.when:
                click.echo(f"     when: {step.when}")

    except SystemExit:
        raise
    except Exception as e:
        logger.exception("Unexpected error in workflow info command")
        error_msg = format_error(f"Failed to show workflow info: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e


@workflow.command("show")
@click.argument("name")
@click.pass_context
def workflow_show(ctx: click.Context, name: str) -> None:
    """Display workflow metadata, inputs, and steps.

    NAME can be either a workflow name (from discovery) or a file path.
    Shows source information and any overrides.

    Examples:
        maverick workflow show fly
        maverick workflow show my-workflow
        maverick workflow show ./workflows/my-workflow.yaml
    """
    logger = get_logger(__name__)

    try:
        # Determine if name is a file path or workflow name
        name_path = Path(name)
        discovered_workflow = None
        workflow_obj = None
        source_info = None
        file_path = None
        overrides = []

        if name_path.exists():
            # It's a file path - parse directly
            file_path = name_path
            content = file_path.read_text(encoding="utf-8")
            workflow_obj = parse_workflow(content, validate_only=True)
            source_info = "file"
        else:
            # Look up in discovery (FR-014: use DiscoveryResult for workflow show)
            discovery_result = get_discovery_result(ctx)
            discovered_workflow = discovery_result.get_workflow(name)

            if discovered_workflow is None:
                # Show available workflows in error message
                available = discovery_result.workflow_names
                if available:
                    available_str = ", ".join(available[:5])
                    if len(available) > 5:
                        available_str += f", ... ({len(available)} total)"
                    suggestion = f"Available workflows: {available_str}"
                else:
                    suggestion = (
                        "No workflows discovered. Check your workflow directories."
                    )

                error_msg = format_error(
                    f"Workflow '{name}' not found",
                    suggestion=suggestion,
                )
                click.echo(error_msg, err=True)
                raise SystemExit(ExitCode.FAILURE)

            workflow_obj = discovered_workflow.workflow
            source_info = discovered_workflow.source
            file_path = discovered_workflow.file_path
            overrides = list(discovered_workflow.overrides)

        # Display workflow information with source (T063)
        click.echo(f"Workflow: {workflow_obj.name}")
        click.echo(f"Version: {workflow_obj.version}")

        # T063: Add source information display
        if source_info:
            source_label = {
                "builtin": "Built-in (packaged with Maverick)",
                "user": "User (~/.config/maverick/workflows/)",
                "project": "Project (.maverick/workflows/)",
                "file": "Direct file path",
            }.get(source_info, source_info)
            click.echo(f"Source: {source_label}")

        if file_path:
            click.echo(f"File: {file_path}")

        if overrides:
            click.echo(f"Overrides: {len(overrides)} workflow(s)")
            for override_path in overrides:
                click.echo(f"  - {override_path}")

        if workflow_obj.description:
            click.echo(f"Description: {workflow_obj.description}")
        click.echo()

        # Display inputs
        if workflow_obj.inputs:
            click.echo("Inputs:")
            for input_name, input_def in workflow_obj.inputs.items():
                required_str = "required" if input_def.required else "optional"
                default_str = (
                    f", default: {input_def.default}"
                    if input_def.default is not None
                    else ""
                )
                desc_str = (
                    f" - {input_def.description}" if input_def.description else ""
                )
                click.echo(
                    f"  {input_name} ({input_def.type.value}, "
                    f"{required_str}{default_str}){desc_str}"
                )
            click.echo()

        # Display steps
        click.echo(f"Steps ({len(workflow_obj.steps)}):")
        for i, step in enumerate(workflow_obj.steps, 1):
            click.echo(f"  {i}. {step.name} ({step.type.value})")
            if step.when:
                click.echo(f"     when: {step.when}")

    except SystemExit:
        raise
    except Exception as e:
        logger.exception("Unexpected error in workflow show command")
        error_msg = format_error(f"Failed to show workflow: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e


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
        errors = []

        click.echo(f"Validating {len(workflows_to_validate)} workflow(s)...")
        click.echo()

        for dw in workflows_to_validate:
            wf = dw.workflow
            try:
                # Re-parse to validate (discovery uses validate_only=True)
                from maverick.dsl.serialization.parser import parse_workflow

                content = dw.file_path.read_text(encoding="utf-8")
                parse_workflow(content, registry=registry, validate_only=not strict)

                # Success
                valid_count += 1
                status = click.style("✓", fg="green", bold=True)
                click.echo(f"{status} {wf.name} ({dw.source})")

            except (
                WorkflowParseError,
                UnsupportedVersionError,
                ReferenceResolutionError,
            ) as e:
                # Validation failed
                invalid_count += 1
                status = click.style("✗", fg="red", bold=True)
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


@workflow.command("viz")
@click.argument("name_or_file")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["ascii", "mermaid"]),
    default="ascii",
    help="Diagram format.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file (stdout if not specified).",
)
@click.option(
    "--direction",
    type=click.Choice(["TD", "LR"]),
    default="TD",
    help="Mermaid diagram direction (TD=top-down, LR=left-right).",
)
@click.pass_context
def workflow_viz(
    ctx: click.Context,
    name_or_file: str,
    fmt: str,
    output: Path | None,
    direction: str,
) -> None:
    """Generate ASCII or Mermaid diagram of workflow.

    NAME_OR_FILE can be either a workflow name (from discovery) or a file path.

    Examples:
        maverick workflow viz fly
        maverick workflow viz my-workflow.yaml --format mermaid
        maverick workflow viz my-workflow --output diagram.md
        maverick workflow viz my-workflow --format mermaid --direction LR
    """
    logger = get_logger(__name__)

    try:
        # Determine if name_or_file is a file path or workflow name
        name_path = Path(name_or_file)
        workflow_obj = None

        if name_path.exists():
            # It's a file path - parse directly
            content = name_path.read_text(encoding="utf-8")
            workflow_obj = parse_workflow(content, validate_only=True)
        else:
            # Look up in discovery (FR-014: use DiscoveryResult for workflow viz)
            discovery_result = get_discovery_result(ctx)
            discovered_workflow = discovery_result.get_workflow(name_or_file)

            if discovered_workflow is not None:
                workflow_obj = discovered_workflow.workflow
            else:
                # Show available workflows in error message
                available = discovery_result.workflow_names
                if available:
                    available_str = ", ".join(available[:5])
                    if len(available) > 5:
                        available_str += f", ... ({len(available)} total)"
                    suggestion = f"Available workflows: {available_str}"
                else:
                    suggestion = (
                        "No workflows discovered. Check your workflow directories."
                    )

                error_msg = format_error(
                    f"Workflow '{name_or_file}' not found",
                    suggestion=suggestion,
                )
                click.echo(error_msg, err=True)
                raise SystemExit(ExitCode.FAILURE)

        # Generate diagram
        if fmt == "mermaid":
            diagram = to_mermaid(workflow_obj, direction=direction)
        else:
            # ASCII format
            diagram = to_ascii(workflow_obj, width=80)

        # Output diagram
        if output:
            output.write_text(diagram, encoding="utf-8")
            click.echo(f"Diagram written to {output}")
        else:
            click.echo(diagram)

    except SystemExit:
        raise
    except Exception as e:
        logger.exception("Unexpected error in workflow viz command")
        error_msg = format_error(f"Failed to generate diagram: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e


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


@workflow.command("run")
@click.argument("name_or_file")
@click.option(
    "-i",
    "--input",
    "inputs",
    multiple=True,
    help="Input parameter (KEY=VALUE format).",
)
@click.option(
    "--input-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Load inputs from JSON/YAML file.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show execution plan without running.",
)
@click.option(
    "--resume",
    is_flag=True,
    default=False,
    help="Resume workflow from latest checkpoint.",
)
@click.option(
    "--no-validate",
    is_flag=True,
    default=False,
    help="Skip semantic validation before execution (not recommended).",
)
@click.pass_context
@async_command
async def workflow_run(
    ctx: click.Context,
    name_or_file: str,
    inputs: tuple[str, ...],
    input_file: Path | None,
    dry_run: bool,
    resume: bool,
    no_validate: bool,
) -> None:
    """Execute workflow from file or discovered workflow.

    NAME_OR_FILE can be either a workflow name (from discovery) or a file path.
    Uses discovery to find workflows from builtin, user, or project locations.

    Inputs can be provided via -i flags (KEY=VALUE) or --input-file.

    The --resume flag attempts to resume from the latest checkpoint, validating
    that inputs match the saved checkpoint state. If no checkpoint exists,
    the workflow executes normally from the start.

    By default, workflows are validated before execution. Use --no-validate
    to skip semantic validation (not recommended).

    Examples:
        maverick workflow run fly
        maverick workflow run my-workflow -i branch=main -i dry_run=true
        maverick workflow run my-workflow.yaml --input-file inputs.json
        maverick workflow run my-workflow --dry-run
        maverick workflow run fly --resume  # Resume from checkpoint
        maverick workflow run my-workflow --no-validate  # Skip validation
    """
    # Delegate to helper function
    await _execute_workflow_run(
        ctx, name_or_file, inputs, input_file, dry_run, resume, no_validate
    )


async def _execute_workflow_run(
    ctx: click.Context,
    name_or_file: str,
    inputs: tuple[str, ...],
    input_file: Path | None,
    dry_run: bool,
    resume: bool,
    no_validate: bool = False,
    list_steps: bool = False,
    only_step: str | None = None,
) -> None:
    """Core workflow execution logic (shared by fly and workflow run commands).

    Args:
        ctx: Click context.
        name_or_file: Workflow name or file path.
        inputs: Tuple of KEY=VALUE input strings.
        input_file: Optional path to JSON/YAML input file.
        dry_run: If True, show execution plan without running.
        resume: If True, resume from latest checkpoint.
        no_validate: If True, skip semantic validation before execution.
        list_steps: If True, list workflow steps and exit.
        only_step: If provided, run only this step (name or number).
    """
    import json

    import yaml

    with cli_error_handler():
        # Determine if name_or_file is a file path or workflow name
        name_path = Path(name_or_file)
        workflow_file = None
        workflow_obj = None

        if name_path.exists():
            # It's a file path - parse directly
            workflow_file = name_path
            content = workflow_file.read_text(encoding="utf-8")
            workflow_obj = parse_workflow(content, validate_only=True)
        else:
            # Look up in discovery (FR-014: use DiscoveryResult for workflow run)
            discovery_result = get_discovery_result(ctx)
            discovered_workflow = discovery_result.get_workflow(name_or_file)

            if discovered_workflow is not None:
                workflow_obj = discovered_workflow.workflow
                workflow_file = discovered_workflow.file_path
            else:
                # Show available workflows in error message
                available = discovery_result.workflow_names
                if available:
                    available_str = ", ".join(available[:5])
                    if len(available) > 5:
                        available_str += f", ... ({len(available)} total)"
                    suggestion = f"Available workflows: {available_str}"
                else:
                    suggestion = (
                        "No workflows discovered. Check your workflow directories."
                    )

                error_msg = format_error(
                    f"Workflow '{name_or_file}' not found",
                    suggestion=suggestion,
                )
                click.echo(error_msg, err=True)
                raise SystemExit(ExitCode.FAILURE)

        # Parse inputs
        input_dict = {}

        # Load from file first
        if input_file:
            input_content = input_file.read_text(encoding="utf-8")
            if input_file.suffix == ".json":
                input_dict = json.loads(input_content)
            else:
                # Assume YAML
                input_dict = yaml.safe_load(input_content)

        # Parse KEY=VALUE inputs (override file inputs)
        for input_str in inputs:
            if "=" not in input_str:
                error_msg = format_error(
                    f"Invalid input format: {input_str}",
                    suggestion="Use KEY=VALUE format (e.g., -i branch=main)",
                )
                click.echo(error_msg, err=True)
                raise SystemExit(ExitCode.FAILURE)

            key, value = input_str.split("=", 1)

            # Try to parse value as JSON for proper type handling
            try:
                parsed_value = json.loads(value)
            except json.JSONDecodeError:
                # Keep as string
                parsed_value = value

            input_dict[key] = parsed_value

        # List steps and exit if requested
        if list_steps:
            click.echo(click.style(f"Workflow: {workflow_obj.name}", bold=True))
            click.echo(f"Version: {workflow_obj.version}")
            if workflow_obj.description:
                click.echo(f"Description: {workflow_obj.description}")
            click.echo()
            click.echo(click.style("Steps:", bold=True))
            for i, step in enumerate(workflow_obj.steps, 1):
                step_type = click.style(f"({step.type.value})", dim=True)
                click.echo(f"  {i}. {step.name} {step_type}")
                if step.when:
                    when_str = click.style(f"when: {step.when}", dim=True)
                    click.echo(f"     {when_str}")
            click.echo()
            click.echo("Use --step <name|number> to run only a specific step.")
            raise SystemExit(ExitCode.SUCCESS)

        # Resolve only_step to step index if provided
        only_step_index: int | None = None
        if only_step:
            # Try to parse as number first
            try:
                step_num = int(only_step)
                if 1 <= step_num <= len(workflow_obj.steps):
                    only_step_index = step_num - 1  # Convert to 0-based
                else:
                    error_msg = format_error(
                        f"Step number {step_num} out of range",
                        suggestion=f"Valid range: 1-{len(workflow_obj.steps)}",
                    )
                    click.echo(error_msg, err=True)
                    raise SystemExit(ExitCode.FAILURE)
            except ValueError:
                # Try to find step by name
                step_names = [s.name for s in workflow_obj.steps]
                if only_step in step_names:
                    only_step_index = step_names.index(only_step)
                else:
                    # Show available steps
                    error_msg = format_error(
                        f"Step '{only_step}' not found",
                        suggestion="Use --list-steps to see available steps",
                    )
                    click.echo(error_msg, err=True)
                    raise SystemExit(ExitCode.FAILURE) from None

        # Show execution plan for dry run
        if dry_run:
            click.echo(f"Dry run: Would execute workflow '{workflow_obj.name}'")
            click.echo(f"  Version: {workflow_obj.version}")
            click.echo(f"  Steps: {len(workflow_obj.steps)}")
            if input_dict:
                click.echo("  Inputs:")
                for key, value in input_dict.items():
                    click.echo(f"    {key} = {value}")
            click.echo("\nExecution plan:")
            for i, step in enumerate(workflow_obj.steps, 1):
                click.echo(f"  {i}. {step.name} ({step.type.value})")
                if step.when:
                    click.echo(f"     when: {step.when}")
            click.echo("\nNo actions performed (dry run mode).")
            raise SystemExit(ExitCode.SUCCESS)

        # Execute workflow using WorkflowFileExecutor
        from maverick.dsl.events import (
            StepCompleted,
            StepStarted,
            WorkflowCompleted,
            WorkflowStarted,
        )
        from maverick.dsl.serialization import WorkflowFileExecutor

        # Display workflow header
        wf_name = workflow_obj.name
        click.echo(click.style(f"Executing workflow: {wf_name}", fg="cyan", bold=True))
        click.echo(f"Version: {click.style(workflow_obj.version, fg='white')}")

        # Display input summary
        if input_dict:
            input_summary = ", ".join(
                f"{k}={click.style(str(v), fg='yellow')}" for k, v in input_dict.items()
            )
            click.echo(f"Inputs: {input_summary}")
        else:
            click.echo("Inputs: (none)")
        click.echo()

        # Create registry with all built-in components registered and executor
        registry = create_registered_registry()
        executor = WorkflowFileExecutor(
            registry=registry,
            validate_semantic=not no_validate,
        )

        # Track step progress
        step_index = 0
        total_steps = len(workflow_obj.steps)

        # Show limited execution message if --step was used
        if only_step_index is not None:
            only_step_name = workflow_obj.steps[only_step_index].name
            limit_msg = click.style(
                f"Will run only step: {only_step_name} "
                f"({only_step_index + 1}/{total_steps})",
                fg="yellow",
            )
            click.echo(limit_msg)
            click.echo()

        # Execute workflow and display progress
        from maverick.dsl.events import (
            ValidationCompleted,
            ValidationFailed,
            ValidationStarted,
        )

        async for event in executor.execute(
            workflow_obj,
            inputs=input_dict,
            resume_from_checkpoint=resume,
            only_step=only_step_index,
        ):
            if isinstance(event, ValidationStarted):
                # Show validation start
                msg = click.style("Validating workflow...", fg="cyan")
                click.echo(msg, nl=False)

            elif isinstance(event, ValidationCompleted):
                # Show validation success
                check_mark = click.style("✓", fg="green", bold=True)
                click.echo(f" {check_mark}")
                if event.warnings_count > 0:
                    warning_msg = click.style(
                        f"  ({event.warnings_count} warning(s))",
                        fg="yellow",
                    )
                    click.echo(warning_msg)
                click.echo()

            elif isinstance(event, ValidationFailed):
                # Show validation failure
                x_mark = click.style("✗", fg="red", bold=True)
                click.echo(f" {x_mark}")
                click.echo()

                # Display error details
                error_msg = format_error(
                    "Workflow validation failed",
                    details=list(event.errors),
                    suggestion="Fix validation errors and try again",
                )
                click.echo(error_msg, err=True)
                raise SystemExit(ExitCode.FAILURE)

            elif isinstance(event, WorkflowStarted):
                # Already displayed header above
                pass

            elif isinstance(event, StepStarted):
                step_index += 1

                # Step type icon mapping
                type_icons = {
                    "python": "⚙",
                    "agent": "🤖",
                    "generate": "✍",
                    "validate": "✓",
                    "checkpoint": "💾",
                }
                icon = type_icons.get(event.step_type.value, "●")

                # Display step start with progress counter
                step_name = event.step_name
                step_header = f"[{step_index}/{total_steps}] {icon} {step_name}"
                styled = click.style(step_header, fg="blue")
                click.echo(f"{styled} ({event.step_type.value})... ", nl=False)

            elif isinstance(event, StepCompleted):
                # Calculate duration
                duration_sec = event.duration_ms / 1000

                if event.success:
                    # Success indicator
                    status_msg = click.style("✓", fg="green", bold=True)
                    duration_msg = click.style(f"({duration_sec:.2f}s)", dim=True)
                    click.echo(f"{status_msg} {duration_msg}")
                else:
                    # Failure indicator
                    status_msg = click.style("✗", fg="red", bold=True)
                    duration_msg = click.style(f"({duration_sec:.2f}s)", dim=True)
                    click.echo(f"{status_msg} {duration_msg}")

            elif isinstance(event, WorkflowCompleted):
                # Workflow summary
                click.echo()
                total_sec = event.total_duration_ms / 1000

                if event.success:
                    summary_header = click.style(
                        "Workflow completed successfully", fg="green", bold=True
                    )
                    click.echo(f"{summary_header} in {total_sec:.2f}s")
                else:
                    summary_header = click.style("Workflow failed", fg="red", bold=True)
                    click.echo(f"{summary_header} after {total_sec:.2f}s")

        # Get final result
        result = executor.get_result()

        # Display summary
        click.echo()
        completed_steps = sum(1 for step in result.step_results if step.success)

        styled_completed = click.style(str(completed_steps), fg="green")
        click.echo(f"Steps: {styled_completed}/{total_steps} completed")

        if result.success:
            # Display final output (truncated if too long)
            if result.final_output is not None:
                output_str = str(result.final_output)
                if len(output_str) > 200:
                    output_str = output_str[:197] + "..."
                click.echo(f"Final output: {click.style(output_str, fg='white')}")
            raise SystemExit(ExitCode.SUCCESS)
        else:
            # Find and display the failed step
            failed_step = result.failed_step
            if failed_step:
                click.echo()
                error_msg = format_error(
                    f"Step '{failed_step.name}' failed",
                    details=[failed_step.error] if failed_step.error else None,
                    suggestion="Check the step configuration and try again.",
                )
                click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE)
