"""CLI entry point for Maverick.

This module defines the Click-based command-line interface for Maverick.
"""

from __future__ import annotations

import logging
from pathlib import Path

import click

from maverick import __version__
from maverick.agents.code_reviewer import CodeReviewerAgent
from maverick.agents.context import AgentContext
from maverick.cli.context import CLIContext, ExitCode, async_command
from maverick.cli.output import OutputFormat, format_error, format_json
from maverick.cli.validators import check_dependencies, check_git_auth
from maverick.config import load_config
from maverick.exceptions import AgentError, ConfigError, GitError, MaverickError
from maverick.models.review import ReviewResult
from maverick.workflows.fly import FlyInputs, FlyWorkflow
from maverick.workflows.refuel import RefuelInputs, RefuelWorkflow


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

    try:
        # T039: Validate branch exists
        logger.info(f"Validating branch '{branch_name}'...")
        try:
            import subprocess

            # Check if branch exists using git show-ref
            # This works for branches that have commits
            result = subprocess.run(
                ["git", "show-ref", "--verify", f"refs/heads/{branch_name}"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                # Branch doesn't exist as a ref (no commits yet or doesn't exist at all)
                # Check if we're currently on this branch using symbolic-ref
                current_branch_result = subprocess.run(
                    ["git", "symbolic-ref", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if current_branch_result.returncode == 0:
                    # Extract branch name from refs/heads/branch-name
                    current_ref = current_branch_result.stdout.strip()
                    current_branch = current_ref.replace("refs/heads/", "")

                    if current_branch != branch_name:
                        # Branch doesn't exist and we're not on it
                        suggestion = (
                            f"Create branch with 'git checkout -b {branch_name}'"
                        )
                        error_msg = format_error(
                            f"Branch '{branch_name}' does not exist",
                            suggestion=suggestion,
                        )
                        click.echo(error_msg, err=True)
                        raise SystemExit(ExitCode.FAILURE)
                else:
                    # Can't determine current branch
                    suggestion = f"Create branch with 'git checkout -b {branch_name}'"
                    error_msg = format_error(
                        f"Branch '{branch_name}' does not exist",
                        suggestion=suggestion,
                    )
                    click.echo(error_msg, err=True)
                    raise SystemExit(ExitCode.FAILURE)

        except subprocess.TimeoutExpired:
            error_msg = format_error("Git command timed out")
            click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE) from None
        except FileNotFoundError:
            error_msg = format_error(
                "git is not installed",
                suggestion="Install from https://git-scm.com/downloads",
            )
            click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE) from None

        # T040: Detect/validate task file
        if task_file is None:
            # Auto-detect task file
            # Look for tasks.md in spec directories
            potential_paths = [
                Path(f".specify/{branch_name}/tasks.md"),
                Path("tasks.md"),
            ]

            for path in potential_paths:
                if path.exists():
                    task_file = path
                    logger.info(f"Auto-detected task file: {task_file}")
                    break

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

        # Execute workflow
        result = await workflow.execute(inputs)

        # Show summary
        click.echo(f"\n{result.summary}")

        if result.success:
            raise SystemExit(ExitCode.SUCCESS)
        else:
            raise SystemExit(ExitCode.FAILURE)

    except KeyboardInterrupt:
        # T043: Handle KeyboardInterrupt with exit code 130
        click.echo("\n\nInterrupted by user.", err=True)
        raise SystemExit(ExitCode.INTERRUPTED) from None

    except GitError as e:
        # T044: Handle GitError
        error_msg = format_error(
            e.message,
            details=[f"Operation: {e.operation}"] if e.operation else None,
        )
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e

    except MaverickError as e:
        # T044: Handle MaverickError hierarchy
        error_msg = format_error(e.message)
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e

    except Exception as e:
        # Unexpected error
        logger.exception("Unexpected error in fly command")
        click.echo(f"Error: {e!s}", err=True)
        raise SystemExit(ExitCode.FAILURE) from e


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

    try:
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
                result = event.result
                if result.status.value == "fixed":
                    click.echo(f"  ✓ Fixed: {result.pr_url}")
                elif result.status.value == "failed":
                    click.echo(f"  ✗ Failed: {result.error}")
                elif result.status.value == "skipped":
                    click.echo("  ⊘ Skipped")

            elif isinstance(event, RefuelCompleted):
                result = event.result
                click.echo("\nSummary:")
                click.echo(f"  Total issues: {result.issues_found}")
                click.echo(f"  Fixed: {result.issues_fixed}")
                click.echo(f"  Failed: {result.issues_failed}")
                click.echo(f"  Skipped: {result.issues_skipped}")

                if result.total_cost_usd > 0:
                    click.echo(f"  Cost: ${result.total_cost_usd:.4f}")

                # Determine exit code
                # Success: no failures (dry-run or all skipped)
                if result.issues_failed == 0:
                    raise SystemExit(ExitCode.SUCCESS)
                # Partial: some fixed, some failed
                elif result.issues_failed > 0 and result.issues_fixed > 0:
                    raise SystemExit(ExitCode.PARTIAL)
                # Failure: only failures, no fixes
                else:
                    raise SystemExit(ExitCode.FAILURE)

    except KeyboardInterrupt:
        # T056: Handle KeyboardInterrupt and exit with code 130
        click.echo("\n\nInterrupted by user.", err=True)
        raise SystemExit(ExitCode.INTERRUPTED) from None

    except MaverickError as e:
        # T056: Handle MaverickError and show formatted error message
        error_msg = f"Error: {e.message}"
        if hasattr(e, "details") and e.details:
            error_msg += f"\n  {e.details}"
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e

    except Exception as e:
        # Unexpected error
        logger.exception("Unexpected error in refuel command")
        click.echo(f"Error: {e!s}", err=True)
        raise SystemExit(ExitCode.FAILURE) from e


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
    cli_ctx: CLIContext = ctx.obj["cli_ctx"]
    logger = logging.getLogger(__name__)

    try:
        # T064: Validate PR exists using gh pr view
        logger.info(f"Validating PR #{pr_number}...")
        try:
            import subprocess

            result = subprocess.run(
                ["gh", "pr", "view", str(pr_number)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                suggestion = (
                    "Check the PR number and ensure you have access to the repository"
                )
                error_msg = format_error(
                    f"Pull request #{pr_number} not found",
                    suggestion=suggestion,
                )
                click.echo(error_msg, err=True)
                raise SystemExit(ExitCode.FAILURE)

        except subprocess.TimeoutExpired:
            error_msg = format_error("GitHub CLI command timed out")
            click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE) from None
        except FileNotFoundError:
            error_msg = format_error(
                "GitHub CLI (gh) is not installed",
                suggestion="Install from https://cli.github.com/",
            )
            click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE) from None

        # T064a: Get PR information (branch name for review)
        logger.info(f"Fetching PR #{pr_number} details...")
        try:
            # Get PR branch name
            pr_info_result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr_number),
                    "--json",
                    "headRefName,baseRefName",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if pr_info_result.returncode != 0:
                error_msg = format_error(
                    f"Failed to fetch PR #{pr_number} details",
                )
                click.echo(error_msg, err=True)
                raise SystemExit(ExitCode.FAILURE)

            import json

            pr_data = json.loads(pr_info_result.stdout)
            branch = pr_data.get("headRefName", "HEAD")
            base_branch = pr_data.get("baseRefName", "main")

        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Could not parse PR details: {e}, using defaults")
            branch = "HEAD"
            base_branch = "main"

        # T065: Create and execute CodeReviewerAgent
        logger.info(f"Starting code review for PR #{pr_number}...")

        agent = CodeReviewerAgent()

        # Create AgentContext for the review
        context = AgentContext(
            branch=branch,
            cwd=Path.cwd(),
            config=cli_ctx.config,
            extra={
                "base_branch": base_branch,
                "pr_number": pr_number,
                "fix": fix,
            },
        )

        # Execute the review
        result = await agent.execute(context)

        # T066-T067: Format output based on --output option
        output_format = OutputFormat(output)

        if output_format == OutputFormat.JSON:
            # T066: Format as JSON
            json_output = format_json(result.model_dump())
            click.echo(json_output)
        elif output_format == OutputFormat.MARKDOWN:
            # T067: Format as markdown
            markdown_output = _format_review_as_markdown(result, pr_number)
            click.echo(markdown_output)
        else:
            # TUI/text output
            click.echo(f"\n{result.summary}")

            if result.findings:
                click.echo(f"\nFound {len(result.findings)} issue(s):\n")
                for i, finding in enumerate(result.findings, 1):
                    severity_label = finding.severity.value.upper()
                    click.echo(f"{i}. [{severity_label}] {finding.file}")
                    if finding.line:
                        click.echo(f"   Line {finding.line}")
                    click.echo(f"   {finding.message}")
                    if finding.suggestion:
                        click.echo(f"   Suggestion: {finding.suggestion}")
                    click.echo()

        if result.success:
            raise SystemExit(ExitCode.SUCCESS)
        else:
            raise SystemExit(ExitCode.FAILURE)

    except KeyboardInterrupt:
        # Handle KeyboardInterrupt with exit code 130
        click.echo("\n\nInterrupted by user.", err=True)
        raise SystemExit(ExitCode.INTERRUPTED) from None

    except AgentError as e:
        # T068: Handle agent errors
        error_msg = format_error(e.message)
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e

    except MaverickError as e:
        # Handle MaverickError hierarchy
        error_msg = format_error(e.message)
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e

    except Exception as e:
        # Unexpected error
        logger.exception("Unexpected error in review command")
        click.echo(f"Error: {e!s}", err=True)
        raise SystemExit(ExitCode.FAILURE) from e


def _format_review_as_markdown(result: ReviewResult, pr_number: int) -> str:
    """Format review result as markdown.

    Args:
        result: ReviewResult from CodeReviewerAgent.
        pr_number: Pull request number.

    Returns:
        Formatted markdown string.
    """
    lines = [
        f"# Code Review: PR #{pr_number}",
        "",
        "## Summary",
        "",
        result.summary,
        "",
    ]

    if result.findings:
        lines.extend(
            [
                f"## Findings ({len(result.findings)})",
                "",
            ]
        )

        # Group findings by severity
        from maverick.models.review import ReviewSeverity

        severity_groups = {
            ReviewSeverity.CRITICAL: [],
            ReviewSeverity.MAJOR: [],
            ReviewSeverity.MINOR: [],
            ReviewSeverity.SUGGESTION: [],
        }

        for finding in result.findings:
            severity_groups[finding.severity].append(finding)

        # Output findings by severity
        for severity in [
            ReviewSeverity.CRITICAL,
            ReviewSeverity.MAJOR,
            ReviewSeverity.MINOR,
            ReviewSeverity.SUGGESTION,
        ]:
            findings = severity_groups[severity]
            if findings:
                lines.extend(
                    [
                        f"### {severity.value.capitalize()} ({len(findings)})",
                        "",
                    ]
                )

                for finding in findings:
                    location = f"{finding.file}"
                    if finding.line:
                        location += f":{finding.line}"

                    lines.extend(
                        [
                            f"**{location}**",
                            "",
                            finding.message,
                            "",
                        ]
                    )

                    if finding.suggestion:
                        lines.extend(
                            [
                                "*Suggestion:*",
                                "",
                                finding.suggestion,
                                "",
                            ]
                        )

    lines.extend(
        [
            "## Metadata",
            "",
            f"- Files reviewed: {result.files_reviewed}",
        ]
    )

    if result.metadata:
        if "branch" in result.metadata:
            lines.append(f"- Branch: {result.metadata['branch']}")
        if "base_branch" in result.metadata:
            lines.append(f"- Base branch: {result.metadata['base_branch']}")
        if "duration_ms" in result.metadata:
            duration_sec = result.metadata["duration_ms"] / 1000
            lines.append(f"- Duration: {duration_sec:.2f}s")

    return "\n".join(lines)


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
        with open(config_file, "w") as f:
            yaml.dump(default_config, f, default_flow_style=False, sort_keys=False)

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
    content = config_file.read_text() if config_file.exists() else ""

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
            config_file.write_text(result)
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
    import re
    import subprocess
    from datetime import datetime

    logger = logging.getLogger(__name__)

    try:
        # T088: Detect git branch using subprocess
        # First, check if we're in a git repository
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                # Not a git repository
                suggestion = (
                    "Initialize with 'git init' or navigate to a git repository"
                )
                error_msg = format_error(
                    "Not a git repository",
                    suggestion=suggestion,
                )
                click.echo(error_msg, err=True)
                raise SystemExit(ExitCode.FAILURE)

        except subprocess.TimeoutExpired:
            error_msg = format_error("Git command timed out")
            click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE) from None
        except FileNotFoundError:
            error_msg = format_error(
                "git is not installed",
                suggestion="Install from https://git-scm.com/downloads",
            )
            click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE) from None

        # Get current branch
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                branch = result.stdout.strip()
                if not branch:
                    # In detached HEAD state
                    branch = "(detached HEAD)"
            else:
                branch = "(unknown)"

        except (subprocess.TimeoutExpired, FileNotFoundError):
            branch = "(unknown)"

        # T089: Detect pending tasks from tasks.md
        pending_tasks = 0
        completed_tasks = 0
        task_file_found = False

        # Look for tasks.md in current directory or .specify/
        spec_task_file = (
            Path.cwd() / ".specify" / branch / "tasks.md"
            if branch not in ("(unknown)", "(detached HEAD)")
            else None
        )
        potential_task_files = [
            Path.cwd() / "tasks.md",
            spec_task_file,
        ]

        for task_file_path in potential_task_files:
            if task_file_path and task_file_path.exists():
                task_file_found = True
                try:
                    content = task_file_path.read_text()
                    # Count pending tasks: lines with - [ ]
                    pending_tasks = len(
                        re.findall(r"^-\s*\[\s*\]", content, re.MULTILINE)
                    )
                    # Count completed tasks: lines with - [x] or - [X]
                    completed_tasks = len(
                        re.findall(r"^-\s*\[[xX]\]", content, re.MULTILINE)
                    )
                    break
                except Exception as e:
                    logger.warning(f"Failed to read task file: {e}")

        # T090: Get recent workflow history from WorkflowHistory
        recent_workflows = []
        try:
            from maverick.tui.history import WorkflowHistoryStore

            history_store = WorkflowHistoryStore()
            recent_entries = history_store.get_recent(count=5)

            for entry in recent_entries:
                # Calculate time ago
                dt = datetime.fromisoformat(entry.timestamp)
                now = datetime.now()
                delta = now - dt

                if delta.days > 0:
                    time_ago = f"{delta.days} day{'s' if delta.days > 1 else ''} ago"
                elif delta.seconds >= 3600:
                    hours = delta.seconds // 3600
                    time_ago = f"{hours} hour{'s' if hours > 1 else ''} ago"
                elif delta.seconds >= 60:
                    minutes = delta.seconds // 60
                    time_ago = f"{minutes} minute{'s' if minutes > 1 else ''} ago"
                else:
                    time_ago = "just now"

                recent_workflows.append(
                    {
                        "workflow_type": entry.workflow_type,
                        "branch": entry.branch_name,
                        "status": entry.final_status,
                        "time_ago": time_ago,
                        "timestamp": entry.timestamp,
                    }
                )

        except Exception as e:
            logger.debug(f"Failed to load workflow history: {e}")

        # T091: Format output as text or JSON
        if fmt == "json":
            # JSON format
            output_data = {
                "branch": branch,
                "tasks": {
                    "pending": pending_tasks,
                    "completed": completed_tasks,
                }
                if task_file_found
                else None,
                "workflows": recent_workflows if recent_workflows else [],
            }
            click.echo(format_json(output_data))
        else:
            # Text format
            lines = [
                "Project Status",
                "==============",
                f"Branch: {branch}",
            ]

            if task_file_found:
                task_summary = (
                    f"Tasks: {pending_tasks} pending, {completed_tasks} completed"
                )
                lines.append(task_summary)
            else:
                lines.append("Tasks: No task file found")

            if recent_workflows:
                lines.append("Recent Workflows:")
                for wf in recent_workflows[:3]:  # Show top 3 in text mode
                    status_icon = "✓" if wf["status"] == "completed" else "✗"
                    workflow_line = (
                        f"  {status_icon} {wf['workflow_type']} "
                        f"({wf['time_ago']}): {wf['status']}"
                    )
                    lines.append(workflow_line)
            else:
                lines.append("Recent Workflows: None")

            click.echo("\n".join(lines))

    except SystemExit:
        raise
    except Exception as e:
        # Unexpected error
        logger.exception("Unexpected error in status command")
        click.echo(f"Error: {e!s}", err=True)
        raise SystemExit(ExitCode.FAILURE) from e


if __name__ == "__main__":
    cli()
