"""``maverick critique`` — standalone, read-only agentic code review.

Contracts:
- ``specs/058-standalone-code-review/contracts/cli-critique.md``
- ``specs/058-standalone-code-review/contracts/cli-critique-json.md``

The command is read-only with respect to the repository (FR-012): the only
writes on any path are the two artifact files under
``.maverick/runs/<run-id>/``.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import click

from maverick.beads.client import BeadClient
from maverick.cli.common import bd_ready_reason, cli_error_handler
from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode, async_command
from maverick.cli.json_output import (
    ErrorKind,
    JsonEnvelope,
    emit_json,
    json_error_handler,
)
from maverick.config import load_config
from maverick.critique.render import render_report
from maverick.critique.report import persist_report
from maverick.critique.runner import AllLensesFailedError, run_critique
from maverick.critique.scope import (
    ScopeNotFoundError,
    ScopeResolutionError,
    ScopeValidationError,
    resolve_diff_scope,
    resolve_epic_scope,
    resolve_paths_scope,
)
from maverick.exceptions import BeadError
from maverick.logging import get_logger

if TYPE_CHECKING:
    from rich.console import Console

    from maverick.config import MaverickConfig
    from maverick.critique.models import CritiqueReport, ResolvedScope

__all__ = ["critique"]

logger = get_logger(__name__)

#: The one verb this command emits. Scope is a property of the *result*
#: (``result.scope.kind``), not of the verb — a consumer branches on a stable
#: field rather than parsing a verb string.
VERB = "critique.run"

DEFAULT_BASE = "main"


# --- Scope resolution -------------------------------------------------------


def _validate_selection(base: str | None, epic: str | None, paths: tuple[str, ...]) -> None:
    """Reject an invocation naming more than one scope (FR-004).

    There is deliberately no precedence rule. An ambiguous invocation means
    the user believes something about what will be reviewed, and guessing
    which belief is right produces a review of the wrong thing under a
    confident-looking scope line.
    """
    named: list[str] = []
    if epic is not None:
        named.append("--epic")
    if paths:
        named.append("PATH arguments")
    if base is not None:
        named.append("--base")
    if len(named) > 1:
        joined = " and ".join(named)
        raise ScopeValidationError(
            f"{joined} select different scopes; name exactly one per invocation"
        )


async def _resolve_scope(
    *,
    cwd: Path,
    base: str | None,
    epic: str | None,
    paths: tuple[str, ...],
) -> ResolvedScope:
    """Resolve the single selected scope."""
    _validate_selection(base, epic, paths)

    if epic is not None:
        reason = bd_ready_reason(cwd)
        if reason is not None:
            # `verify_available()` returns False rather than raising, so the
            # shared JSON handler cannot classify this — the command owns the
            # translation (see json_output.py's module docstring).
            raise BeadError(reason)
        client = BeadClient(cwd)
        children = await client.children(epic)
        if not children:
            raise ScopeNotFoundError(f"epic '{epic}' does not exist or has no beads")
        return await resolve_epic_scope(
            cwd=cwd, epic_id=epic, bead_ids=[bead.id for bead in children]
        )

    if paths:
        return resolve_paths_scope(cwd=cwd, paths=paths)

    return await resolve_diff_scope(cwd=cwd, base=base or DEFAULT_BASE)


# --- Shared execution -------------------------------------------------------


async def _execute(
    *,
    cwd: Path,
    config: MaverickConfig,
    base: str | None,
    epic: str | None,
    paths: tuple[str, ...],
    out: Console,
) -> tuple[CritiqueReport, Path | None]:
    """Resolve, review, and persist. Returns the report and the md artifact.

    Persistence failure is degraded to a warning here rather than raised:
    FR-018 says it never changes the review outcome or the exit code.
    """
    run_id = uuid.uuid4().hex[:8]
    scope = await _resolve_scope(cwd=cwd, base=base, epic=epic, paths=paths)
    report = await run_critique(cwd=cwd, config=config, scope=scope, run_id=run_id)

    try:
        _, md_path = persist_report(report, cwd=cwd)
    except OSError as exc:
        logger.warning("critique_persist_failed", run_id=run_id, error=str(exc))
        out.print(f"[yellow]Warning:[/yellow] could not write the findings artifact: {exc}")
        from dataclasses import replace

        return replace(report, degraded_persistence=True), None
    return report, md_path


def _fail_on_met(report: CritiqueReport, fail_on: str | None) -> bool:
    return fail_on is not None and report.exceeds(fail_on)


# --- Human mode -------------------------------------------------------------


async def _run_critique_human(
    *,
    cwd: Path,
    config: MaverickConfig,
    base: str | None,
    epic: str | None,
    paths: tuple[str, ...],
    fail_on: str | None,
) -> None:
    with cli_error_handler():
        report, md_path = await _execute(
            cwd=cwd, config=config, base=base, epic=epic, paths=paths, out=err_console
        )
        render_report(report, console=console, artifact_path=md_path)
        if _fail_on_met(report, fail_on):
            err_console.print(
                f"[red]Error:[/red] findings at or above '{fail_on}' are present (--fail-on)."
            )
            raise SystemExit(ExitCode.FAILURE)


# --- JSON mode --------------------------------------------------------------


def _emit_failure(kind: ErrorKind, message: str, **details: object) -> None:
    emit_json(JsonEnvelope.failure(VERB, kind, message, details))
    raise SystemExit(ExitCode.FAILURE)


async def _run_critique_json(
    *,
    cwd: Path,
    config: MaverickConfig,
    base: str | None,
    epic: str | None,
    paths: tuple[str, ...],
    fail_on: str | None,
) -> None:
    with json_error_handler(VERB):
        try:
            report, _ = await _execute(
                cwd=cwd, config=config, base=base, epic=epic, paths=paths, out=err_console
            )
        except ScopeValidationError as exc:
            _emit_failure(ErrorKind.VALIDATION, str(exc))
        except ScopeNotFoundError as exc:
            _emit_failure(ErrorKind.NOT_FOUND, str(exc), epic_id=epic)
        except BeadError as exc:
            _emit_failure(ErrorKind.BD_UNAVAILABLE, str(exc))
        except ScopeResolutionError as exc:
            _emit_failure(ErrorKind.VCS, str(exc))
        except AllLensesFailedError as exc:
            _emit_failure(ErrorKind.INTERNAL, str(exc))

        result = report.to_dict()
        if report.degraded_persistence:
            # Injected here rather than emitted from `to_dict()`: the schema
            # contract puts this key in the envelope only, and an on-disk
            # artifact that persisted cannot meaningfully carry it. Without
            # the injection a machine consumer whose artifact write failed
            # would get a document indistinguishable from a clean run, while
            # a human at the terminal is warned. Same shape as
            # `land_status.py`'s `degraded` injection.
            result["degraded_persistence"] = True

        # A `--fail-on` refusal is a *success* envelope with a non-zero exit:
        # the review completed, and its findings are exactly what the caller
        # asked to be told about. Consumers branch on `ok`, never on the exit
        # code alone (contract: cli-critique-json.md).
        emit_json(JsonEnvelope.success(VERB, result))
        raise SystemExit(ExitCode.FAILURE if _fail_on_met(report, fail_on) else ExitCode.SUCCESS)


# --- Command ----------------------------------------------------------------


@click.command("critique")
@click.argument("paths", nargs=-1, type=click.Path())
@click.option(
    "--base",
    default=None,
    help=f"Base revision for the diff scope.  [default: {DEFAULT_BASE}]",
)
@click.option("--epic", default=None, help="Review everything an epic's beads committed.")
@click.option(
    "--fail-on",
    type=click.Choice(["critical", "major", "minor"]),
    default=None,
    help="Exit non-zero when a finding at or above this severity is present.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit a single machine-readable JSON envelope to stdout.",
)
@click.pass_context
@async_command
async def critique(
    ctx: click.Context,
    paths: tuple[str, ...],
    base: str | None,
    epic: str | None,
    fail_on: str | None,
    json_output: bool,
) -> None:
    """Review a change, an epic, or a set of paths — outside the fly loop.

    Read-only: no commits, no bead writes, no fix loop. Findings are advice,
    so a completed review exits 0 regardless of what it found; use
    ``--fail-on`` to opt into gating.

    \b
    Examples:
      maverick critique                        # working copy vs main
      maverick critique --base origin/main
      maverick critique --epic mv-0041
      maverick critique src/maverick/jj/
      maverick critique --json | jq .result.severity_counts
    """
    cwd = Path.cwd().resolve()
    config = (ctx.obj or {}).get("config") if ctx.obj else None
    if config is None:
        config = load_config()

    runner = _run_critique_json if json_output else _run_critique_human
    await runner(cwd=cwd, config=config, base=base, epic=epic, paths=paths, fail_on=fail_on)
