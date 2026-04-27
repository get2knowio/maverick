from __future__ import annotations

import contextlib
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.cli.console import err_console
from maverick.cli.context import ExitCode
from maverick.cli.output import format_error
from maverick.exceptions import AgentError, GitError, MaverickError
from maverick.library.agents import register_all_agents
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.registry import ComponentRegistry


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
    logger = get_logger(__name__)

    try:
        yield
    except KeyboardInterrupt:
        err_console.print("\n\n[yellow]Interrupted by user.[/]")
        raise SystemExit(ExitCode.INTERRUPTED) from None
    except GitError as e:
        error_msg = format_error(
            e.message,
            details=[f"Operation: {e.operation}"] if e.operation else None,
        )
        err_console.print(f"[red]Error:[/red] {error_msg}")
        raise SystemExit(ExitCode.FAILURE) from e
    except AgentError as e:
        error_msg = format_error(e.message)
        err_console.print(f"[red]Error:[/red] {error_msg}")
        raise SystemExit(ExitCode.FAILURE) from e
    except MaverickError as e:
        error_msg = format_error(e.message)
        err_console.print(f"[red]Error:[/red] {error_msg}")
        raise SystemExit(ExitCode.FAILURE) from e
    except Exception as e:
        logger.exception("Unexpected error in command")
        err_console.print(f"[red]Error:[/red] {e!s}")
        raise SystemExit(ExitCode.FAILURE) from e


def verify_bd_ready(cwd: Path | None = None) -> None:
    """Preflight: ``bd`` is on PATH AND ``.beads/`` is initialized in ``cwd``.

    Workflows that create or close beads (refuel, fly) must verify both
    conditions before doing any expensive work — otherwise the user
    discovers the missing setup only after the workflow burns through
    decompose / implement and dies on the bead-creation step.

    Exits with :class:`ExitCode.FAILURE` and a friendly remediation
    message when either check fails. Returns ``None`` when both pass.

    Args:
        cwd: Project root to check. Defaults to ``Path.cwd()``.
    """
    import shutil

    from maverick.beads.client import BeadClient
    from maverick.cli.console import console

    if shutil.which("bd") is None:
        console.print(
            "[red]Error:[/red] The [bold]bd[/bold] CLI is required but not found "
            "on PATH.\n"
            "Install it with: [cyan]cargo install bd-cli[/cyan] "
            "(or see https://github.com/get2knowio/bd)"
        )
        raise SystemExit(ExitCode.FAILURE)

    target = cwd if cwd is not None else Path.cwd()
    client = BeadClient(cwd=target)
    if not client.is_initialized():
        console.print(
            f"[red]Error:[/red] this project hasn't been initialized for "
            f"Maverick yet.\n"
            f"Run [cyan]maverick init[/cyan] in [cyan]{target}[/cyan] — "
            f"it's safe to re-run on an existing project (it won't "
            f"overwrite [bold]maverick.yaml[/bold]) and handles both "
            f"fresh setups and joining a project where a teammate has "
            f"already done the initial work.\n"
            f"[dim]Tip: any cached briefing / outline / details from a "
            f"previous run will be picked up automatically, so re-running "
            f"the workflow after init is a fast cache-hit pass.[/]"
        )
        raise SystemExit(ExitCode.FAILURE)


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
    from maverick.registry import ComponentRegistry

    registry = ComponentRegistry(strict=strict)

    # Register all built-in components
    register_all_agents(registry)

    return registry
