from __future__ import annotations

import contextlib
from collections.abc import Generator
from pathlib import Path

from maverick.cli.console import err_console
from maverick.cli.context import ExitCode
from maverick.cli.output import format_error
from maverick.exceptions import AgentError, GitError, MaverickError
from maverick.logging import get_logger


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


async def resolve_publish_branch_label(repo_path: Path) -> str:
    """Return a human-readable label for the user repo's current branch.

    Used by post-finalize CLI messages (``plan generate``, ``refuel``)
    so the "published to user repo" line names the **destination
    branch** the work landed on (typically ``main`` or a feature
    branch) instead of the temporary ``maverick/<project>`` transport
    bookmark, which has already been deleted by ``finalize`` by the
    time the CLI prints.

    Auto-detects jj vs git via :func:`create_vcs_repository`; falls back
    to a generic ``"current branch"`` label if branch resolution raises
    (detached HEAD, missing repo, etc.) so the success path never breaks
    on a display concern.
    """
    from maverick.vcs.factory import create_vcs_repository

    try:
        repo = create_vcs_repository(repo_path)
        branch = await repo.current_branch()
    except Exception as exc:  # noqa: BLE001 — display concern, never break
        get_logger(__name__).debug(
            "publish_branch_resolve_failed",
            repo_path=str(repo_path),
            error=str(exc),
        )
        return "current branch"
    return str(branch).strip() or "current branch"
