from __future__ import annotations

import contextlib
from collections.abc import Generator
from pathlib import Path
from typing import Any

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


def resolve_verbosity(ctx: Any) -> int:
    """Read the CLI verbosity level (``-v`` count) off a Click context.

    The root group stores it as ``ctx.obj["verbose"]``
    (``maverick.main.cli``). Callers reaching for ``ctx.obj["verbosity"]``
    silently got ``0`` no matter how many ``-v`` flags were passed, which
    is why verbose progress rendering never engaged; both spellings are
    accepted here so neither reader can regress.

    Args:
        ctx: Click context (or anything with an ``obj`` mapping).

    Returns:
        The verbosity level, ``0`` when unset.
    """
    obj = getattr(ctx, "obj", None)
    if not obj:
        return 0
    value = obj.get("verbose", obj.get("verbosity", 0))
    return int(value or 0)


#: ``bd_ready_reason`` result codes. ``BD_MISSING`` — the CLI isn't on
#: PATH; ``BD_NOT_INITIALIZED`` — it is, but this project has no
#: ``.beads/``.
BD_MISSING = "bd-missing"
BD_NOT_INITIALIZED = "bd-not-initialized"


def bd_ready_reason(cwd: Path | None = None) -> str | None:
    """Why ``bd`` isn't usable in *cwd*, or ``None`` when it is.

    The single predicate behind every bd preflight — :func:`verify_bd_ready`
    (human mode, prints + exits) and ``maverick.cli.commands.reconcile.
    _require_bd_ready_json`` (JSON mode, raises ``BeadError``) both consume
    it, so the two can't drift as conditions are added.

    Args:
        cwd: Project root to check. Defaults to ``Path.cwd()``.

    Returns:
        :data:`BD_MISSING`, :data:`BD_NOT_INITIALIZED`, or ``None`` when
        both checks pass.
    """
    import shutil

    from maverick.beads.client import BeadClient

    if shutil.which("bd") is None:
        return BD_MISSING

    target = cwd if cwd is not None else Path.cwd()
    if not BeadClient(cwd=target).is_initialized():
        return BD_NOT_INITIALIZED

    return None


def verify_bd_ready(cwd: Path | None = None) -> None:
    """Preflight: ``bd`` is on PATH AND ``.beads/`` is initialized in ``cwd``.

    Workflows that create or close beads (refuel, fly) must verify both
    conditions before doing any expensive work — otherwise the user
    discovers the missing setup only after the workflow burns through
    decompose / implement and dies on the bead-creation step.

    Exits with :class:`ExitCode.FAILURE` and a friendly remediation
    message when either check fails. Returns ``None`` when both pass.
    The conditions themselves live in :func:`bd_ready_reason`; this
    function owns only the human-facing rendering.

    Args:
        cwd: Project root to check. Defaults to ``Path.cwd()``.
    """
    from maverick.cli.console import console

    reason = bd_ready_reason(cwd)
    if reason is None:
        return

    target = cwd if cwd is not None else Path.cwd()

    if reason == BD_MISSING:
        console.print(
            "[red]Error:[/red] The [bold]bd[/bold] CLI is required but not found "
            "on PATH.\n"
            "Install it with: [cyan]cargo install bd-cli[/cyan] "
            "(or see https://github.com/get2knowio/bd)"
        )
        raise SystemExit(ExitCode.FAILURE)

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
