"""``maverick spec`` — headless Spec Kit chain (`maverick spec`).

Runs the target repository's own Spec Kit chain — specify, clarify,
plan, tasks, analyze — headlessly inside a hidden workspace. See
specs/050-headless-spec-chain/contracts/cli-spec.md for the full
contract.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import click

from maverick.cli.common import cli_error_handler, verify_bd_ready
from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode, async_command
from maverick.init.models import PreflightStatus
from maverick.init.prereqs import check_speckit_installed

__all__ = ["spec"]


def _exit_partial(message: str, *, remediation: str | None = None) -> None:
    err_console.print(f"[red]Error:[/red] {message}")
    if remediation:
        err_console.print(f"[yellow]Remediation:[/yellow] {remediation}")
    raise SystemExit(ExitCode.PARTIAL)


def _check_speckit_or_exit(cwd: Path) -> None:
    check = check_speckit_installed(cwd)
    if check.status != PreflightStatus.PASS:
        _exit_partial(check.message, remediation=check.remediation)


def _check_prd_or_exit(prd_path: Path) -> None:
    try:
        content = prd_path.read_text(encoding="utf-8")
    except OSError as exc:
        _exit_partial(f"cannot read PRD file {prd_path}: {exc}")
        return
    if not content.strip():
        _exit_partial(f"PRD file {prd_path} is empty")


def _check_feature_collision_or_exit(cwd: Path, feature: str) -> None:
    """FR-015: refuse to overwrite an existing spec directory for *feature*.

    Only reached once ``discover_resumable`` has already ruled out an
    auto-resumable (halted/running) chain — a completed/foreign
    ``specs/`` dir for this feature is a genuine collision (FR-020).
    """
    specs_dir = cwd / "specs"
    if not specs_dir.is_dir():
        return
    for candidate in specs_dir.iterdir():
        if candidate.is_dir() and candidate.name.endswith(f"-{feature}"):
            _exit_partial(
                f"a spec directory already exists for '{feature}': {candidate}",
                remediation="Remove or rename it, or choose a different feature name.",
            )


def _render_summary_and_exit(state: object, feature: str) -> None:
    from maverick.workflows.spec_chain.models import ChainState

    if not isinstance(state, ChainState):
        err_console.print(
            "[red]Error:[/red] no chain state found after the run — this "
            "indicates an internal error."
        )
        raise SystemExit(ExitCode.FAILURE)

    console.print()
    console.print("[bold]Summary[/]")
    console.print(f"  Feature dir: [bold]{state.feature_dir or '(none)'}[/]")
    console.print(f"  Clarify questions answered: {len(state.clarify_decisions)}")
    console.print(f"  Remediation beads created: {len(state.remediation_bead_ids)}")
    if state.protection_blocks:
        console.print(
            f"  [yellow]Context-file protection events: "
            f"{len(state.protection_blocks)}[/] (see protection-blocks.json)"
        )

    if state.status == "completed":
        console.print()
        console.print("[green]✓[/] Chain completed.")
        raise SystemExit(ExitCode.SUCCESS)

    console.print()
    console.print("[red]✗[/] Chain halted.")
    console.print(f"[dim]Resume:[/] [bold]maverick spec {feature}[/]")
    raise SystemExit(ExitCode.FAILURE)


@click.command("spec")
@click.argument("feature")
@click.option(
    "--from-prd",
    "prd_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to the PRD file that seeds the chain (required unless resuming).",
)
@click.option(
    "--session-log",
    "session_log",
    type=click.Path(path_type=Path),
    default=None,
    help="Write a session journal (JSONL) to this file path.",
)
@click.pass_context
@async_command
async def spec(
    ctx: click.Context,
    feature: str,
    prd_path: Path | None,
    session_log: Path | None,
) -> None:
    """Run the headless Spec Kit chain for FEATURE from a PRD.

    Runs specify -> clarify -> plan -> tasks -> analyze inside an
    isolated hidden workspace, invoking the target repository's own
    /speckit.* commands. No step ever blocks on interactive input;
    completed-step artifacts land in specs/NNN-FEATURE/. Re-running for a
    feature with a halted or still-running chain auto-resumes it from the
    first incomplete step instead of requiring --from-prd again.
    """
    cwd = Path.cwd().resolve()

    from maverick.workflows.spec_chain.models import is_valid_feature_slug

    with cli_error_handler():
        if not is_valid_feature_slug(feature):
            _exit_partial(
                f"invalid feature name '{feature}' — must be a filesystem-safe "
                "slug (letters, digits, hyphen, underscore; no path separators "
                "or leading dots)"
            )
        verify_bd_ready(cwd)
        _check_speckit_or_exit(cwd)

    from maverick.workflows.spec_chain.state import discover_resumable, load_chain_state

    resumable = await discover_resumable(feature, cwd)

    if resumable is not None:
        run_id = resumable.run_id
        console.print(
            f"[dim]Resuming '{feature}' (run {run_id}, status: {resumable.status}) — "
            "continuing from the first incomplete step.[/]"
        )
    else:
        with cli_error_handler():
            if prd_path is None:
                _exit_partial(
                    f"--from-prd is required to start a new chain for '{feature}'",
                    remediation=(
                        "Pass --from-prd <file>, or omit it if you meant to resume "
                        "an existing halted/running chain for this feature."
                    ),
                )
            assert prd_path is not None  # _exit_partial always raises above
            _check_prd_or_exit(prd_path)
            _check_feature_collision_or_exit(cwd, feature)
        run_id = uuid.uuid4().hex[:8]

    from maverick.cli.workflow_executor import PythonWorkflowRunConfig, execute_python_workflow
    from maverick.workflows.spec_chain.workflow import SpecChainWorkflow

    try:
        await execute_python_workflow(
            ctx,
            PythonWorkflowRunConfig(
                workflow_class=SpecChainWorkflow,
                inputs={
                    "run_id": run_id,
                    "feature": feature,
                    "prd_path": str(prd_path) if prd_path else "",
                    "cwd": str(cwd),
                },
                session_log_path=session_log,
            ),
        )
    except asyncio.CancelledError:
        # Graceful Ctrl-C (T032): the workflow's own rollback already
        # checkpointed status=halted on the freshest on-disk state before
        # this propagates here — print the resume hint before the outer
        # async_command wrapper converts this into exit 130.
        interrupted_state = await load_chain_state(run_id, cwd)
        if interrupted_state is not None:
            err_console.print()
            err_console.print(f"[dim]Resume:[/] [bold]maverick spec {feature}[/]")
        raise

    final_state = await load_chain_state(run_id, cwd)
    _render_summary_and_exit(final_state, feature)
