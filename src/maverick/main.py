"""CLI entry point for Maverick.

This module defines the Click-based command-line interface for Maverick.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import click

from maverick import __version__
from maverick.agents.code_reviewer import CodeReviewerAgent
from maverick.cli.context import CLIContext, ExitCode, async_command
from maverick.cli.helpers import (
    count_tasks,
    detect_task_file,
    format_review_markdown,
    format_review_text,
    format_status_json,
    format_status_text,
    get_git_branch,
    get_workflow_history,
    validate_branch,
    validate_pr,
)
from maverick.cli.output import OutputFormat, format_error, format_json, format_table
from maverick.cli.validators import check_dependencies, check_git_auth
from maverick.config import load_config
from maverick.dsl.context_builders import register_all_context_builders
from maverick.dsl.discovery import DiscoveryResult, create_discovery
from maverick.dsl.serialization.parser import parse_workflow
from maverick.dsl.visualization import to_ascii, to_mermaid
from maverick.exceptions import AgentError, ConfigError, GitError, MaverickError
from maverick.library.actions import register_all_actions
from maverick.library.agents import register_all_agents
from maverick.library.generators import register_all_generators
from maverick.models.review import ReviewContext
from maverick.workflows.fly import FlyInputs, FlyWorkflow, FlyWorkflowCompleted
from maverick.workflows.refuel import (
    RefuelInputs,
    RefuelWorkflow,
)

if TYPE_CHECKING:
    from maverick.dsl.serialization.registry import ComponentRegistry


@contextlib.contextmanager
def cli_error_handler() -> Generator[None, None, None]:
    """Context manager for common CLI error handling.

    Handles common error patterns across CLI commands:
    - KeyboardInterrupt: Exit with code 130
    - GitError: Format error with operation details
    - AgentError: Format error with agent context
    - MaverickError: Format error with message
    - Generic exceptions: Log and format error

    Example:
        >>> with cli_error_handler():
        >>>     # Command logic here
        >>>     workflow.execute()
    """
    logger = logging.getLogger(__name__)

    try:
        yield
    except KeyboardInterrupt:
        click.echo("\n\nInterrupted by user.", err=True)
        raise SystemExit(ExitCode.INTERRUPTED) from None
    except GitError as e:
        error_msg = format_error(
            e.message,
            details=[f"Operation: {e.operation}"] if e.operation else None,
        )
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e
    except AgentError as e:
        error_msg = format_error(e.message)
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e
    except MaverickError as e:
        error_msg = format_error(e.message)
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e
    except Exception as e:
        logger.exception("Unexpected error in command")
        click.echo(f"Error: {e!s}", err=True)
        raise SystemExit(ExitCode.FAILURE) from e


def create_registered_registry(strict: bool = False) -> ComponentRegistry:
    """Create a ComponentRegistry with all built-in components registered.

    This function creates a new ComponentRegistry and registers all built-in
    actions, agents, generators, context builders, and discovered workflows
    so they can be resolved by workflows.

    Args:
        strict: If True, create registry in strict mode (reference resolution
            errors will be raised immediately).

    Returns:
        ComponentRegistry with all built-in components and discovered
        workflows registered.
    """
    from maverick.dsl.discovery import load_workflows_into_registry
    from maverick.dsl.serialization.registry import ComponentRegistry

    registry = ComponentRegistry(strict=strict)

    # Register all built-in components
    register_all_actions(registry)
    register_all_agents(registry)
    register_all_generators(registry)
    register_all_context_builders(registry)

    # Register all discovered workflows and fragments
    load_workflows_into_registry(registry)

    return registry


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="maverick")
@click.option(
    "-c",
    "--config",
    "config_file",
    type=click.Path(exists=False, path_type=str),
    default=None,
    help="Path to config file (overrides project/user config).",
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Increase verbosity (-v for INFO, -vv for DEBUG, -vvv for DEBUG+trace).",
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    default=False,
    help="Suppress non-essential output (ERROR level only).",
)
@click.option(
    "--no-tui",
    is_flag=True,
    default=False,
    help="Disable TUI mode (headless operation).",
)
@click.pass_context
def cli(
    ctx: click.Context,
    config_file: str | None,
    verbose: int,
    quiet: bool,
    no_tui: bool,
) -> None:
    """Maverick - AI-powered development workflow orchestration."""
    # Ensure ctx.obj exists for subcommands
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet
    ctx.obj["no_tui"] = no_tui

    # Load configuration first (before logging setup)
    try:
        # If --config specified, load from that path
        config_path = Path(config_file) if config_file else None
        config = load_config(config_path)
        ctx.obj["config"] = config
    except ConfigError as e:
        # Can't use logging yet, just output error
        error_parts = [f"Error: {e.message}"]
        if e.field:
            error_parts.append(f"  Field: {e.field}")
        if e.value is not None:
            error_parts.append(f"  Value: {e.value}")
        error_msg = "\n".join(error_parts)
        click.echo(error_msg, err=True)
        ctx.exit(1)

    # Create CLIContext and store in Click context
    cli_ctx = CLIContext(
        config=config,
        config_path=Path(config_file) if config_file else None,
        verbosity=verbose,
        quiet=quiet,
        no_tui=no_tui,
    )
    ctx.obj["cli_ctx"] = cli_ctx

    # Determine logging level with precedence rules
    # Priority: quiet > verbose > config
    verbosity_map = {
        "error": logging.ERROR,
        "warning": logging.WARNING,
        "info": logging.INFO,
        "debug": logging.DEBUG,
    }

    if quiet:
        # Quiet takes precedence - ERROR level only (40)
        level = logging.ERROR
    elif verbose > 0:
        # CLI verbose flag takes precedence over config
        # 0: WARNING (30) - default
        # 1 (-v): INFO (20)
        # 2+ (-vv, -vvv): DEBUG (10)
        level = logging.INFO if verbose == 1 else logging.DEBUG
    else:
        # Use config file setting
        level = verbosity_map.get(config.verbosity, logging.WARNING)

    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        force=True,  # Reconfigure if already configured
    )

    # FR-013: Validate required dependencies at startup
    # Only validate when a command is being invoked (not for --help/--version)
    if ctx.invoked_subcommand is not None:
        # Define which commands need which dependencies
        commands_needing_git_gh = {"fly", "refuel", "review", "status"}

        if ctx.invoked_subcommand in commands_needing_git_gh:
            # Check for git and gh CLI tools
            dep_statuses = check_dependencies(["git", "gh"])

            # Report any missing dependencies
            missing_deps = [dep for dep in dep_statuses if not dep.available]
            if missing_deps:
                for dep in missing_deps:
                    suggestion = (
                        f"Install from {dep.install_url}" if dep.install_url else None
                    )
                    error_msg = format_error(
                        dep.error or f"{dep.name} is not available",
                        suggestion=suggestion,
                    )
                    click.echo(error_msg, err=True)
                ctx.exit(ExitCode.FAILURE)

    # If no command is given, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.argument("branch_name")
@click.option(
    "-t",
    "--task-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to task file (auto-detect if not specified).",
)
@click.option(
    "--skip-review",
    is_flag=True,
    default=False,
    help="Skip code review stage.",
)
@click.option(
    "--skip-pr",
    is_flag=True,
    default=False,
    help="Skip PR creation stage.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show planned actions without executing.",
)
@click.pass_context
@async_command
async def fly(
    ctx: click.Context,
    branch_name: str,
    task_file: Path | None,
    skip_review: bool,
    skip_pr: bool,
    dry_run: bool,
) -> None:
    """Execute FlyWorkflow for a feature branch.

    Orchestrates the complete spec-based development workflow including setup,
    implementation, code review, validation, convention updates, and PR management.

    Examples:
        maverick fly feature-123
        maverick fly feature-123 --task-file ./tasks.md
        maverick fly feature-123 --skip-review --skip-pr
        maverick fly feature-123 --dry-run
    """
    logger = logging.getLogger(__name__)

    with cli_error_handler():
        # T039: Validate branch exists
        logger.info(f"Validating branch '{branch_name}'...")
        is_valid, error_msg = validate_branch(branch_name)
        if not is_valid:
            click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE)

        # T040: Detect/validate task file
        if task_file is None:
            task_file = detect_task_file(branch_name)
            if task_file:
                logger.info(f"Auto-detected task file: {task_file}")

        # T042: If dry_run, just show planned actions
        if dry_run:
            click.echo(f"Dry run: Would execute FlyWorkflow for branch '{branch_name}'")
            click.echo(f"  Task file: {task_file or '(auto-detect)'}")
            click.echo(f"  Skip review: {skip_review}")
            click.echo(f"  Skip PR: {skip_pr}")
            click.echo("\nNo actions performed (dry run mode).")
            raise SystemExit(ExitCode.SUCCESS)

        # Create FlyInputs from CLI options
        inputs = FlyInputs(
            branch_name=branch_name,
            task_file=task_file,
            skip_review=skip_review,
            skip_pr=skip_pr,
        )

        # T041: Run workflow (TUI or headless based on cli_ctx.use_tui)
        logger.info(
            f"Starting fly workflow (branch={branch_name}, "
            f"task_file={task_file}, skip_review={skip_review}, skip_pr={skip_pr})"
        )

        workflow = FlyWorkflow()

        # Execute workflow and consume events
        result = None
        async for event in workflow.execute(inputs):
            if isinstance(event, FlyWorkflowCompleted):
                result = event.result
            # Optionally log progress events here

        # Show summary
        if result:
            click.echo(f"\n{result.summary}")
            if result.success:
                raise SystemExit(ExitCode.SUCCESS)
            else:
                raise SystemExit(ExitCode.FAILURE)
        else:
            click.echo("Workflow did not complete")
            raise SystemExit(ExitCode.FAILURE)


@cli.command()
@click.option(
    "-l",
    "--label",
    default="tech-debt",
    help="Issue label to filter by.",
)
@click.option(
    "-n",
    "--limit",
    default=5,
    type=int,
    help="Maximum issues to process.",
)
@click.option(
    "--parallel/--sequential",
    default=True,
    help="Processing mode (parallel or sequential).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="List matching issues without processing.",
)
@click.pass_context
@async_command
async def refuel(
    ctx: click.Context,
    label: str,
    limit: int,
    parallel: bool,
    dry_run: bool,
) -> None:
    """Execute RefuelWorkflow for tech debt resolution.

    Discovers GitHub issues by label and processes them using IssueFixerAgent.
    Creates branches, fixes issues, and generates pull requests.

    Examples:
        maverick refuel
        maverick refuel --label bug --limit 3
        maverick refuel --sequential
        maverick refuel --dry-run
    """
    logger = logging.getLogger(__name__)

    with cli_error_handler():
        # T053: Check GitHub CLI authentication
        logger.info("Checking GitHub CLI authentication...")
        auth_status = check_git_auth()

        if not auth_status.available:
            error_msg = f"Error: {auth_status.error}"
            if auth_status.install_url:
                error_msg += f"\n\nSuggestion: Visit {auth_status.install_url}"
            click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE)

        # Create RefuelInputs from CLI options
        inputs = RefuelInputs(
            label=label,
            limit=limit,
            parallel=parallel,
            dry_run=dry_run,
        )

        # T054: Run workflow (TUI or headless based on cli_ctx.use_tui)
        logger.info(
            f"Starting refuel workflow (label={label}, limit={limit}, "
            f"parallel={parallel}, dry_run={dry_run})"
        )

        workflow = RefuelWorkflow()

        # T055: If dry_run, just list matching issues
        if dry_run:
            click.echo(f"Dry run: Finding issues with label '{label}'...")

        # Execute workflow and consume events
        async for event in workflow.execute(inputs):
            # For now, just log events (TUI integration will handle this later)
            from maverick.workflows.refuel import (
                IssueProcessingCompleted,
                IssueProcessingStarted,
                RefuelCompleted,
                RefuelStarted,
            )

            if isinstance(event, RefuelStarted):
                click.echo(f"Found {event.issues_found} issue(s) with label '{label}'")
                if dry_run and event.issues_found == 0:
                    click.echo("No issues found.")

            elif isinstance(event, IssueProcessingStarted):
                msg = (
                    f"[{event.index}/{event.total}] Processing issue "
                    f"#{event.issue.number}: {event.issue.title}"
                )
                click.echo(msg)

            elif isinstance(event, IssueProcessingCompleted):
                issue_result = event.result
                if issue_result.status.value == "fixed":
                    click.echo(f"  ✓ Fixed: {issue_result.pr_url}")
                elif issue_result.status.value == "failed":
                    click.echo(f"  ✗ Failed: {issue_result.error}")
                elif issue_result.status.value == "skipped":
                    click.echo("  ⊘ Skipped")

            elif isinstance(event, RefuelCompleted):
                refuel_result = event.result
                click.echo("\nSummary:")
                click.echo(f"  Total issues: {refuel_result.issues_found}")
                click.echo(f"  Fixed: {refuel_result.issues_fixed}")
                click.echo(f"  Failed: {refuel_result.issues_failed}")
                click.echo(f"  Skipped: {refuel_result.issues_skipped}")

                if refuel_result.total_cost_usd > 0:
                    click.echo(f"  Cost: ${refuel_result.total_cost_usd:.4f}")

                # Determine exit code
                # Success: no failures (dry-run or all skipped)
                if refuel_result.issues_failed == 0:
                    raise SystemExit(ExitCode.SUCCESS)
                # Partial: some fixed, some failed
                elif refuel_result.issues_failed > 0 and refuel_result.issues_fixed > 0:
                    raise SystemExit(ExitCode.PARTIAL)
                # Failure: only failures, no fixes
                else:
                    raise SystemExit(ExitCode.FAILURE)


@cli.command()
@click.argument("pr_number", type=int)
@click.option(
    "--fix/--no-fix",
    default=False,
    help="Automatically apply suggested fixes.",
)
@click.option(
    "-o",
    "--output",
    type=click.Choice(["tui", "json", "markdown", "text"]),
    default="tui",
    help="Output format.",
)
@click.pass_context
@async_command
async def review(
    ctx: click.Context,
    pr_number: int,
    fix: bool,
    output: str,
) -> None:
    """Review a pull request using AI-powered analysis.

    Analyzes a GitHub pull request for correctness, security, style, performance,
    and testability issues using the CodeReviewerAgent.

    Examples:
        maverick review 123
        maverick review 123 --fix
        maverick review 123 --output json
        maverick review 123 --output markdown
        maverick review 123 --output text
    """
    _cli_ctx: CLIContext = ctx.obj["cli_ctx"]  # Reserved for future use
    logger = logging.getLogger(__name__)

    with cli_error_handler():
        # T064: Validate PR exists using gh pr view
        logger.info(f"Validating PR #{pr_number}...")
        is_valid, error_msg, pr_data = validate_pr(pr_number)
        if not is_valid:
            click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE)

        # Extract branch info from pr_data
        branch = pr_data.get("headRefName", "HEAD") if pr_data else "HEAD"
        base_branch = pr_data.get("baseRefName", "main") if pr_data else "main"

        # T065: Create and execute CodeReviewerAgent
        logger.info(f"Starting code review for PR #{pr_number}...")

        agent = CodeReviewerAgent()

        # Create ReviewContext for the review
        context = ReviewContext(
            branch=branch,
            base_branch=base_branch,
            cwd=Path.cwd(),
        )

        # Execute the review
        result = await agent.execute(context)

        # T066-T067: Format output based on --output option
        output_format = OutputFormat(output)

        if output_format == OutputFormat.JSON:
            click.echo(format_json(result.model_dump()))
        elif output_format == OutputFormat.MARKDOWN:
            click.echo(format_review_markdown(result, pr_number))
        else:
            click.echo(format_review_text(result))

        if result.success:
            raise SystemExit(ExitCode.SUCCESS)
        else:
            raise SystemExit(ExitCode.FAILURE)




@cli.group()
def config() -> None:
    """Manage Maverick configuration."""
    pass


@config.command("init")
@click.option("--force", is_flag=True, help="Overwrite existing config file.")
@click.pass_context
def config_init(ctx: click.Context, force: bool) -> None:
    """Initialize a new configuration file.

    Creates a default maverick.yaml configuration file in the current directory.

    Examples:
        maverick config init
        maverick config init --force
    """
    import yaml

    logger = logging.getLogger(__name__)
    config_file = Path.cwd() / "maverick.yaml"

    # Check if file exists and --force not specified
    if config_file.exists() and not force:
        error_msg = format_error(
            f"Config file already exists: {config_file}",
            suggestion="Use --force to overwrite existing file",
        )
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE)

    # Create default config template
    default_config = {
        "github": {
            "owner": None,
            "repo": None,
            "default_branch": "main",
        },
        "notifications": {
            "enabled": False,
            "server": "https://ntfy.sh",
            "topic": None,
        },
        "validation": {
            "format_cmd": ["ruff", "format", "."],
            "lint_cmd": ["ruff", "check", "--fix", "."],
            "typecheck_cmd": ["mypy", "."],
            "test_cmd": ["pytest", "-x", "--tb=short"],
            "timeout_seconds": 300,
            "max_errors": 50,
        },
        "model": {
            "model_id": "claude-sonnet-4-20250514",
            "max_tokens": 8192,
            "temperature": 0.0,
        },
        "parallel": {
            "max_agents": 3,
            "max_tasks": 5,
        },
        "verbosity": "warning",
    }

    try:
        # Write config file
        yaml_content = yaml.dump(
            default_config, default_flow_style=False, sort_keys=False
        )
        config_file.write_text(yaml_content, encoding="utf-8")

        logger.info(f"Config file created: {config_file}")
        click.echo(f"Configuration file created: {config_file}")

    except Exception as e:
        error_msg = format_error(f"Failed to create config file: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e


@config.command("show")
@click.option(
    "-f",
    "--format",
    "fmt",
    type=click.Choice(["yaml", "json"]),
    default="yaml",
    help="Output format (yaml or json).",
)
@click.pass_context
def config_show(ctx: click.Context, fmt: str) -> None:
    """Display current configuration.

    Shows the merged configuration from all sources (defaults, user config,
    project config, environment variables).

    Examples:
        maverick config show
        maverick config show --format json
    """
    import yaml

    from maverick.cli.output import format_json

    cli_ctx: CLIContext = ctx.obj["cli_ctx"]
    config = cli_ctx.config

    # Convert config to dict for output
    config_dict = config.model_dump(mode="python")

    if fmt == "json":
        # Output as JSON
        click.echo(format_json(config_dict))
    else:
        # Output as YAML
        yaml_output = yaml.dump(config_dict, default_flow_style=False, sort_keys=False)
        click.echo(yaml_output)


@config.command("edit")
@click.option(
    "--user",
    is_flag=True,
    help="Edit user config (~/.config/maverick/config.yaml).",
)
@click.option(
    "--project",
    is_flag=True,
    default=True,
    help="Edit project config (./maverick.yaml).",
)
@click.pass_context
def config_edit(ctx: click.Context, user: bool, project: bool) -> None:
    """Open configuration file in default editor.

    Opens the specified config file in $EDITOR or the default system editor.

    Examples:
        maverick config edit
        maverick config edit --user
    """
    logger = logging.getLogger(__name__)

    # Determine which config to edit
    if user:
        from maverick.config import get_user_config_path

        config_file = get_user_config_path()
        # Ensure user config directory exists
        config_file.parent.mkdir(parents=True, exist_ok=True)
    else:
        config_file = Path.cwd() / "maverick.yaml"

    # Read existing content if file exists
    content = config_file.read_text(encoding="utf-8") if config_file.exists() else ""

    try:
        # Open editor
        result = click.edit(content)

        # If result is None, user cancelled
        if result is None:
            logger.info("Edit cancelled by user")
            click.echo("Edit cancelled.")
            return

        # Write back if changed
        if result != content:
            config_file.write_text(result, encoding="utf-8")
            logger.info(f"Config file updated: {config_file}")
            click.echo(f"Configuration file updated: {config_file}")
        else:
            click.echo("No changes made.")

    except Exception as e:
        error_msg = format_error(f"Failed to edit config file: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e


@config.command("validate")
@click.option(
    "-f",
    "--file",
    "config_file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Config file to validate (auto-detect if not specified).",
)
@click.pass_context
def config_validate(ctx: click.Context, config_file: Path | None) -> None:
    """Validate configuration file.

    Checks configuration file for syntax errors and validation issues.

    Examples:
        maverick config validate
        maverick config validate --file custom.yaml
    """
    logger = logging.getLogger(__name__)

    try:
        # Load and validate config
        load_config(config_file)

        # If we get here, validation succeeded
        logger.info("Configuration is valid")
        click.echo("Configuration is valid.")

    except ConfigError as e:
        # Validation failed
        error_parts = [f"Error: Invalid configuration - {e.message}"]
        if e.field:
            error_parts.append(f"  Field: {e.field}")
        if e.value is not None:
            error_parts.append(f"  Value: {e.value}")
        error_msg = "\n".join(error_parts)
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e

    except Exception as e:
        error_msg = format_error(f"Error validating config: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e


def _get_discovery_result(ctx: click.Context) -> DiscoveryResult:
    """Get or create workflow discovery result.

    Runs discovery on first call and caches result in CLI context.

    Args:
        ctx: Click context.

    Returns:
        DiscoveryResult from workflow discovery.
    """
    if "discovery_result" not in ctx.obj:
        discovery = create_discovery()
        ctx.obj["discovery_result"] = discovery.discover()
    result: DiscoveryResult = ctx.obj["discovery_result"]
    return result


@cli.group()
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

    logger = logging.getLogger(__name__)

    try:
        # Run discovery (FR-014: call discover() when CLI initializes)
        discovery_result = _get_discovery_result(ctx)

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
    logger = logging.getLogger(__name__)

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
            discovery_result = _get_discovery_result(ctx)
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


@workflow.command("validate")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--strict/--no-strict",
    default=True,
    help="Strict mode checks all references exist.",
)
@click.pass_context
def workflow_validate(ctx: click.Context, file: Path, strict: bool) -> None:
    """Validate workflow YAML syntax and schema.

    Checks workflow file for syntax errors, schema violations, and optionally
    validates that all component references exist.

    Examples:
        maverick workflow validate my-workflow.yaml
        maverick workflow validate my-workflow.yaml --no-strict
    """
    logger = logging.getLogger(__name__)

    try:
        from maverick.dsl.serialization.errors import (
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

        workflow_obj = parse_workflow(
            content, registry=registry, validate_only=not strict
        )

        # If we get here, validation succeeded
        click.echo(f"Workflow '{workflow_obj.name}' is valid.")
        click.echo(f"  Version: {workflow_obj.version}")
        click.echo(f"  Steps: {len(workflow_obj.steps)}")
        click.echo(f"  Inputs: {len(workflow_obj.inputs)}")

        if not strict:
            click.echo("\nNote: Reference resolution skipped (use --strict to enable)")

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
    logger = logging.getLogger(__name__)

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
            discovery_result = _get_discovery_result(ctx)
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
    help="Output format (default: yaml).",
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
        Default format is YAML.
        Default output directory is .maverick/workflows/.

    Examples:
        maverick workflow new my-workflow
        maverick workflow new my-workflow --template full
        maverick workflow new my-workflow --format python
        maverick workflow new my-workflow --output-dir ./workflows
        maverick workflow new my-workflow --preview
    """
    logger = logging.getLogger(__name__)

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
@click.pass_context
@async_command
async def workflow_run(
    ctx: click.Context,
    name_or_file: str,
    inputs: tuple[str, ...],
    input_file: Path | None,
    dry_run: bool,
    resume: bool,
) -> None:
    """Execute workflow from file or discovered workflow.

    NAME_OR_FILE can be either a workflow name (from discovery) or a file path.
    Uses discovery to find workflows from builtin, user, or project locations.

    Inputs can be provided via -i flags (KEY=VALUE) or --input-file.

    The --resume flag attempts to resume from the latest checkpoint, validating
    that inputs match the saved checkpoint state. If no checkpoint exists,
    the workflow executes normally from the start.

    Examples:
        maverick workflow run fly
        maverick workflow run my-workflow -i branch=main -i dry_run=true
        maverick workflow run my-workflow.yaml --input-file inputs.json
        maverick workflow run my-workflow --dry-run
        maverick workflow run fly --resume  # Resume from checkpoint
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
            discovery_result = _get_discovery_result(ctx)
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
        executor = WorkflowFileExecutor(registry=registry)

        # Track step progress
        step_index = 0
        total_steps = len(workflow_obj.steps)

        # Execute workflow and display progress
        async for event in executor.execute(
            workflow_obj,
            inputs=input_dict,
            resume_from_checkpoint=resume,
        ):
            if isinstance(event, WorkflowStarted):
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
                    summary_header = click.style(
                        "Workflow failed", fg="red", bold=True
                    )
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


@cli.command()
@click.option(
    "-f",
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format.",
)
@click.pass_context
def status(ctx: click.Context, fmt: str) -> None:
    """Display project status information.

    Shows current git branch, pending tasks, recent workflow runs, and
    configuration status.

    Examples:
        maverick status
        maverick status --format json
    """
    logger = logging.getLogger(__name__)

    try:
        # Get git branch
        branch, error_msg = get_git_branch()
        if error_msg:
            click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE)

        # Ensure we have a valid branch name
        if not branch:
            branch = "(unknown)"

        # Detect pending tasks from tasks.md
        task_file_found = False
        pending_tasks = 0
        completed_tasks = 0

        task_file_path = detect_task_file(
            branch
            if branch and branch not in ("(unknown)", "(detached HEAD)")
            else None
        )

        if task_file_path:
            task_file_found = True
            pending_tasks, completed_tasks = count_tasks(task_file_path)

        # Get recent workflow history
        recent_workflows = get_workflow_history(count=5)

        # Format output
        if fmt == "json":
            output = format_status_json(
                branch,
                task_file_found,
                pending_tasks,
                completed_tasks,
                recent_workflows,
            )
        else:
            output = format_status_text(
                branch,
                task_file_found,
                pending_tasks,
                completed_tasks,
                recent_workflows,
            )

        click.echo(output)

    except SystemExit:
        raise
    except Exception as e:
        # Unexpected error
        logger.exception("Unexpected error in status command")
        click.echo(f"Error: {e!s}", err=True)
        raise SystemExit(ExitCode.FAILURE) from e


if __name__ == "__main__":
    cli()
