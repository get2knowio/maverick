"""``maverick refuel`` command.

Decomposes a flight plan into beads (work units), either via AI
decomposition (classic path) or deterministic Spec Kit ingestion
(``--speckit`` / auto-detected).
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.commands.flight_plan._group import DEFAULT_PLANS_DIR
from maverick.cli.console import console
from maverick.cli.context import ExitCode, async_command


@click.command()
@click.argument("name")
@click.option(
    "--list-steps",
    is_flag=True,
    default=False,
    help="List workflow steps and exit without executing.",
)
@click.option(
    "--session-log",
    type=click.Path(path_type=Path),
    default=None,
    help="Write session journal (JSONL) to this file path.",
)
@click.option(
    "--skip-briefing",
    is_flag=True,
    default=False,
    help="Skip the briefing room step (parallel agent analysis).",
)
@click.option(
    "--auto-commit",
    is_flag=True,
    default=False,
    help=(
        "Commit any uncommitted changes (including refuel's own output) "
        "after refuel succeeds. Lets ``maverick fly`` pick up the work "
        "without tripping the snapshot check."
    ),
)
@click.option(
    "--plans-dir",
    default=DEFAULT_PLANS_DIR,
    show_default=True,
    help="Base plans directory. Ignored in Spec Kit ingestion mode.",
)
@click.option(
    "--speckit",
    is_flag=True,
    default=False,
    help="Force Spec Kit ingestion mode (parse specs/NNN-name/ deterministically).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Spec Kit mode only: preview the ingestion plan; make zero writes.",
)
@click.option(
    "--enrich",
    is_flag=True,
    default=False,
    help=(
        "Spec Kit mode only: one-shot model pass attaching verification "
        "commands to new task beads."
    ),
)
@click.pass_context
@async_command
async def refuel(
    ctx: click.Context,
    name: str,
    list_steps: bool,
    session_log: Path | None,
    skip_briefing: bool,
    auto_commit: bool,
    plans_dir: str,
    speckit: bool,
    dry_run: bool,
    enrich: bool,
) -> None:
    """Decompose a flight plan into beads.

    NAME resolves to a classic flight plan
    (.maverick/plans/<name>/flight-plan.md) or, in a Spec Kit-managed
    repository, a ``specs/NNN-name/`` feature directory (exact name,
    ``NNN`` prefix, or exact name suffix) — auto-detected from
    repository shape, or forced with ``--speckit``.

    Examples:

        maverick refuel my-feature

        maverick refuel my-feature --skip-briefing

        maverick refuel 048 --speckit --dry-run

        maverick refuel 048-my-feature --speckit
    """
    # Preflight: bd installed AND .beads initialized. Catches missing
    # setup in seconds rather than after the full briefing+decompose
    # burn (which we just spent ~13 minutes learning to fail at the
    # bead-creation step).
    from maverick.cli.common import verify_bd_ready

    verify_bd_ready()

    # Refuel runs in the user's checkout. ``maverick init`` runs
    # ``jj git init --colocate`` so the cwd is always a jj+git repo,
    # which means every jj-only action (jj_commit_bead, jj log, etc.)
    # works without vcs detection. Bead commits and plan files land
    # directly on the user's current branch.
    cwd = Path.cwd().resolve()

    from maverick.cli.common import cli_error_handler

    with cli_error_handler():
        use_speckit, speckit_dir = _dispatch_mode(
            name, speckit_flag=speckit, cwd=cwd, plans_dir=plans_dir, list_steps=list_steps
        )

    if use_speckit:
        # In list-steps mode the feature need not resolve to a concrete
        # directory (the step list is static), so speckit_dir may be None.
        if not list_steps:
            assert speckit_dir is not None
            console.print(f"[dim]Using Spec Kit ingestion ({speckit_dir})[/]")
        if skip_briefing:
            console.print(
                "[yellow]Warning:[/yellow] --skip-briefing has no effect in "
                "Spec Kit ingestion mode (there is no briefing step)"
            )
        await _run_speckit_refuel(
            ctx,
            speckit_dir=speckit_dir,
            cwd=cwd,
            list_steps=list_steps,
            session_log=session_log,
            dry_run=dry_run,
            enrich=enrich,
            auto_commit=auto_commit,
        )
        return

    if dry_run:
        console.print(
            "[yellow]Warning:[/yellow] --dry-run only applies to Spec Kit "
            "ingestion mode and is ignored on the classic refuel path "
            "(this run will write beads)"
        )
    if enrich:
        console.print(
            "[yellow]Warning:[/yellow] --enrich only applies to Spec Kit "
            "ingestion mode and is ignored on the classic refuel path"
        )

    await _run_classic_refuel(
        ctx,
        name=name,
        cwd=cwd,
        list_steps=list_steps,
        session_log=session_log,
        skip_briefing=skip_briefing,
        auto_commit=auto_commit,
        plans_dir=plans_dir,
    )


def _dispatch_mode(
    name: str, *, speckit_flag: bool, cwd: Path, plans_dir: str, list_steps: bool = False
) -> tuple[bool, Path | None]:
    """Resolve NAME against classic + Spec Kit shapes and pick a mode.

    Args:
        name: The ``NAME`` argument as given on the command line.
        speckit_flag: Whether ``--speckit`` was passed (forces ingestion).
        cwd: Repository root.
        plans_dir: The CLI's ``--plans-dir`` — threaded through so a
            classic plan under a non-default directory still resolves.
        list_steps: Whether ``--list-steps`` was passed. When True,
            resolution failures degrade to a mode choice rather than
            raising — the step list is static and useful to inspect
            before the plan/feature exists.

    Returns:
        ``(use_speckit, speckit_dir)`` — ``speckit_dir`` is set whenever
        ``use_speckit`` is True and NAME resolves; it may be None in
        ``list_steps`` mode, where the concrete directory is not needed.

    Raises:
        SpeckitError: E01 (ambiguous — both match), E02 (unresolvable).
        AmbiguousFeatureError: E03 (multiple Spec Kit candidates).
    """
    from maverick.speckit.detect import resolve_feature
    from maverick.speckit.errors import SpeckitError

    resolution = resolve_feature(name, cwd=cwd, plans_dir=plans_dir)

    if speckit_flag:
        if resolution.speckit_dir is None:
            if list_steps:
                # Listing steps doesn't need a resolved feature directory.
                return True, None
            raise SpeckitError(
                f"--speckit given but {name!r} does not resolve to a Spec Kit "
                f"feature directory (looked for specs/{name}*/ with spec.md "
                "and tasks.md)"
            )
        return True, resolution.speckit_dir

    if resolution.mode == "ambiguous":
        if list_steps:
            # Both shapes exist; show the Spec Kit steps for the listing.
            return True, resolution.speckit_dir
        raise SpeckitError(
            f"{name!r} matches both a classic flight plan "
            f"({resolution.flight_plan_path}) and a Spec Kit feature "
            f"({resolution.speckit_dir}). Rerun with --speckit to select "
            "ingestion, or rename one of them to disambiguate."
        )
    if resolution.mode == "speckit":
        return True, resolution.speckit_dir
    if resolution.mode == "classic":
        return False, None

    if list_steps:
        # Nothing resolves yet (e.g. the plan hasn't been created); default
        # to the classic step list so ``--list-steps`` stays inspectable.
        return False, None
    plans_input = Path(plans_dir)
    plans_base = plans_input if plans_input.is_absolute() else cwd / plans_input
    raise SpeckitError(
        f"could not resolve {name!r} to a flight plan or Spec Kit feature "
        f"(looked in {plans_base / name} and specs/{name}*/)"
    )


async def _run_speckit_refuel(
    ctx: click.Context,
    *,
    speckit_dir: Path | None,
    cwd: Path,
    list_steps: bool,
    session_log: Path | None,
    dry_run: bool,
    enrich: bool,
    auto_commit: bool,
) -> None:
    """Dispatch to :class:`SpeckitRefuelWorkflow`."""
    from maverick.workflows.refuel_speckit.constants import (
        CHAIN_EPIC,
        CHECK_TEMPLATE,
        COMMIT_OUTPUT,
        CREATE_BEADS,
        ENRICH,
        PARSE_ARTIFACTS,
        PLAN_INGESTION,
        RECORD_RUN,
        RESOLVE_FEATURE,
        WIRE_DEPS,
        WORKFLOW_NAME,
    )

    steps = [
        RESOLVE_FEATURE,
        CHECK_TEMPLATE,
        PARSE_ARTIFACTS,
        PLAN_INGESTION,
        ENRICH,
        CREATE_BEADS,
        WIRE_DEPS,
        CHAIN_EPIC,
        RECORD_RUN,
        COMMIT_OUTPUT,
    ]

    if list_steps:
        from maverick.cli.workflow_executor import _display_name

        console.print(f"[bold]Workflow: {WORKFLOW_NAME}[/]")
        console.print()
        console.print("[bold]Steps:[/]")
        for i, step_name in enumerate(steps, 1):
            console.print(f"  {i}. {_display_name(step_name)}")
        console.print()
        raise SystemExit(ExitCode.SUCCESS)

    # Past the list-steps short-circuit an actual run needs a resolved dir.
    assert speckit_dir is not None

    from maverick.cli.workflow_executor import (
        PythonWorkflowRunConfig,
        execute_python_workflow,
    )
    from maverick.workflows.refuel_speckit import SpeckitRefuelWorkflow

    workflow_inputs: dict[str, object] = {
        "feature_dir": str(speckit_dir),
        "cwd": str(cwd),
        "dry_run": dry_run,
        "enrich": enrich,
        "auto_commit": auto_commit,
    }

    await execute_python_workflow(
        ctx,
        PythonWorkflowRunConfig(
            workflow_class=SpeckitRefuelWorkflow,
            inputs=workflow_inputs,
            session_log_path=session_log,
        ),
    )

    if dry_run:
        return

    from maverick.runway.run_metadata import find_latest_run

    meta = find_latest_run(speckit_dir.name, base=cwd)
    if meta and meta.epic_id:
        console.print()
        console.print(f"[dim]Next:[/] [bold]maverick fly --epic {meta.epic_id}[/]")


async def _run_classic_refuel(
    ctx: click.Context,
    *,
    name: str,
    cwd: Path,
    list_steps: bool,
    session_log: Path | None,
    skip_briefing: bool,
    auto_commit: bool,
    plans_dir: str,
) -> None:
    """Dispatch to :class:`RefuelMaverickWorkflow` (unchanged classic path)."""
    from maverick.cli.workflow_executor import (
        PythonWorkflowRunConfig,
        execute_python_workflow,
    )
    from maverick.workflows.refuel_maverick import RefuelMaverickWorkflow
    from maverick.workflows.refuel_maverick.constants import (
        BRIEFING,
        CREATE_BEADS,
        DECOMPOSE,
        GATHER_CONTEXT,
        PARSE_FLIGHT_PLAN,
        VALIDATE,
        WIRE_DEPS,
        WORKFLOW_NAME,
        WRITE_WORK_UNITS,
    )

    steps = [
        PARSE_FLIGHT_PLAN,
        GATHER_CONTEXT,
        BRIEFING,
        DECOMPOSE,
        VALIDATE,
        WRITE_WORK_UNITS,
        CREATE_BEADS,
        WIRE_DEPS,
    ]

    if list_steps:
        from maverick.cli.workflow_executor import _display_name

        console.print(f"[bold]Workflow: {WORKFLOW_NAME}[/]")
        console.print()
        console.print("[bold]Steps:[/]")
        for i, step_name in enumerate(steps, 1):
            console.print(f"  {i}. {_display_name(step_name)}")
        console.print()
        raise SystemExit(ExitCode.SUCCESS)

    plans_input = Path(plans_dir)
    plans_base = plans_input if plans_input.is_absolute() else cwd / plans_input
    flight_plan_path = plans_base / name / "flight-plan.md"

    workflow_inputs: dict[str, object] = {
        "flight_plan_path": str(flight_plan_path),
        "skip_briefing": skip_briefing,
        "auto_commit": auto_commit,
        "cwd": str(cwd),
    }

    await execute_python_workflow(
        ctx,
        PythonWorkflowRunConfig(
            workflow_class=RefuelMaverickWorkflow,
            inputs=workflow_inputs,
            session_log_path=session_log,
        ),
    )

    # Surface the "what next" command. The workflow writes the bd epic id
    # into ``.maverick/runs/<run_id>/metadata.json`` — read it back so the
    # user doesn't have to dig for it.
    from maverick.runway.run_metadata import find_latest_run

    meta = find_latest_run(name, base=cwd)
    if meta and meta.epic_id:
        console.print()
        console.print(f"[dim]Next:[/] [bold]maverick fly --epic {meta.epic_id}[/]")
