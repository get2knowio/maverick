"""``maverick land`` command.

Curate the commit history written by ``maverick fly``.

Single-repo (CWD) workflow model: fly commits land directly on the user's
current branch, so land just curates that history in place. Earlier
revisions bridged a hidden jj workspace into the user repo via
``WorkspaceManager`` — that path is retired (see
plans/cryptic-napping-waffle.md).

Three modes (kept for compatibility, all curate the same way; differ
only in the post-curation hint):

* ``--approve`` (default): curate, leave the user to push/PR manually.
* ``--eject``: curate, then print push/PR instructions for an
  ``maverick/preview/<project>`` branch.
* ``--finalize``: curate, then print push/PR instructions for an
  ``maverick/<project>`` branch.

PR opening + remote pushing is intentionally not automated in this
slice. The full architecture (see
``.claude/scratchpads/architecture-pull-work-push.md``) re-introduces
those automations once the underlying state machine lands.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
from rich.panel import Panel
from rich.table import Table

from maverick.cli.commands.land_gate import (
    build_report,
    check_assumption_gate,
    display_verification,
    persist_report_json,
    render_and_persist_land_report,
)
from maverick.cli.commands.land_status import run_status
from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode, async_command
from maverick.cli.json_output import ErrorKind, JsonEnvelope, emit_json
from maverick.cli.output import format_error, format_success, format_warning
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.assumptions.land_report import LandReport

logger = get_logger(__name__)


@click.command()
@click.option(
    "--no-curate",
    is_flag=True,
    default=False,
    help="Skip curation, just emit the next-step hint.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show curation plan without executing.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Auto-approve curation plan.",
)
@click.option(
    "--base",
    default="main",
    show_default=True,
    help="Base revision for curation scope.",
)
@click.option(
    "--heuristic-only",
    is_flag=True,
    default=False,
    help="Use heuristic curation (no agent).",
)
@click.option(
    "--eject",
    is_flag=True,
    default=False,
    help="Curate and emit push/PR instructions for an eject preview branch.",
)
@click.option(
    "--finalize",
    is_flag=True,
    default=False,
    help="Curate and emit push/PR instructions for the maverick branch.",
)
@click.option(
    "--no-consolidate",
    is_flag=True,
    default=False,
    help="Skip runway consolidation.",
)
@click.option(
    "--branch",
    default=None,
    help="Branch label suggested in the next-step hint.",
)
@click.option(
    "--status",
    is_flag=True,
    default=False,
    help="Read-only frontier/landability check — no curation, no mutation.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit machine-readable JSON on stdout instead of Rich console output.",
)
@click.pass_context
@async_command
async def land(
    ctx: click.Context,
    no_curate: bool,
    dry_run: bool,
    yes: bool,
    base: str,
    heuristic_only: bool,
    eject: bool,
    finalize: bool,
    no_consolidate: bool,
    branch: str | None,
    status: bool,
    json_output: bool,
) -> None:
    """Curate commit history written by ``maverick fly``.

    Examples:

    \b
        maverick land
        maverick land --dry-run
        maverick land --no-curate
        maverick land --heuristic-only
        maverick land --eject
        maverick land --finalize
        maverick land --yes
        maverick land --status --json
    """
    if status:
        _validate_status_flags(
            dry_run=dry_run,
            yes=yes,
            eject=eject,
            finalize=finalize,
            no_curate=no_curate,
            heuristic_only=heuristic_only,
            json_mode=json_output,
        )
        await run_status(base=base, cwd=Path.cwd().resolve(), json_mode=json_output)
        return

    from maverick.library.actions.jj import (
        curate_history,
        gather_curation_context,
    )

    cwd = Path.cwd().resolve()
    project_name = cwd.name
    run_id = uuid.uuid4().hex[:8]
    mode = "eject" if eject else "finalize" if finalize else "approve"
    # Narration console: stdout is reserved for the single JSON document in
    # `--json` mode, so every progress line routes to stderr there. Bound
    # once — a later `console.print` added without this routing would
    # silently corrupt the one-document guarantee.
    out = err_console if json_output else console

    # ── 1. Check there are commits to land ──────────────────────────
    curation_ctx = await gather_curation_context(base, cwd=cwd)
    if not curation_ctx["success"]:
        if json_output:
            emit_json(
                JsonEnvelope.failure(
                    "land.run",
                    ErrorKind.VCS,
                    f"Failed to gather commit context: {curation_ctx['error']}",
                )
            )
        else:
            err_console.print(
                format_error(
                    f"Failed to gather commit context: {curation_ctx['error']}",
                )
            )
        raise SystemExit(ExitCode.FAILURE)

    commits = curation_ctx["commits"]
    if not commits:
        if json_output:
            # Same key set as every other `land.run` success document —
            # a consumer reading `result["verification"]` or
            # `result["report"]` must not KeyError just because there was
            # nothing above base. `report` is null here (and only here):
            # the gate is never evaluated on this path, since there is no
            # landing to gate.
            emit_json(
                JsonEnvelope.success(
                    "land.run",
                    {
                        "landed": False,
                        "reason": "nothing-to-land",
                        "mode": mode,
                        "verification": None,
                        "degraded": False,
                        "curation": _curation_summary("none"),
                        "report": None,
                        "report_paths": {},
                        "hint": None,
                    },
                )
            )
        else:
            console.print("Nothing to land — no commits found above base revision.")
        return

    if json_output:
        out.print(f"Found {len(commits)} commit(s) above {base}.")
    else:
        out.print(f"Found {len(commits)} commit(s) above [bold]{base}[/bold].")

    # ── 1b. Display human review manifest if present ─────────────
    if not json_output:
        _display_human_review_manifest(cwd)

    # ── 1c. Assumption ledger gate + provenance report. Blocks unless
    # every entry (any severity, incl. legacy) has been answered or
    # waived via `maverick review`, and no answered entry is pending
    # reconciliation. No bypass flag exists. Every evaluation (blocked,
    # dry-run, successful) renders and persists the grouped provenance
    # report (contracts/cli-land.md); `--dry-run` still evaluates and
    # renders, but only exits non-zero at the end (after the rest of the
    # preview runs) rather than short-circuiting immediately.
    gate_blocks, gate_entries, verification = await check_assumption_gate(cwd, quiet=json_output)
    degraded = verification is None
    report: LandReport | None = None
    report_paths: dict[str, str | None] = {}
    if json_output:
        report = build_report(gate_entries, verification, run_id=run_id, dry_run=dry_run)
        report_paths, _degraded_persistence = persist_report_json(report, cwd=cwd)
    else:
        report_md_path = render_and_persist_land_report(
            gate_entries, verification, run_id=run_id, dry_run=dry_run, cwd=cwd
        )
    if gate_blocks and not dry_run:
        if json_output:
            assert report is not None  # built above whenever json_output is True
            emit_json(_frontier_blocked_envelope(report))
        raise SystemExit(ExitCode.FAILURE)

    # ── 2. Curation ────────────────────────────────────────────────
    curation: dict[str, object] = _curation_summary("none")

    if no_curate:
        out.print("Skipping curation (--no-curate).")
    elif heuristic_only and dry_run:
        # `curate_history` rewrites history (jj absorb + squash). A
        # dry run is a preview on every other curation path, so it must
        # be one here too — the agent path already stops at the plan.
        curation = _curation_summary("heuristic")
        out.print("Dry run — heuristic curation not applied.")
    elif heuristic_only:
        result = await curate_history(base, cwd=cwd)
        if result["success"]:
            squashed = result["squashed_count"]
            absorb_ran = bool(result["absorb_ran"])
            # `absorb_ran` is a distinct signal from `squashed_count`:
            # absorb alone rewrites history with zero squashes, which
            # would otherwise be indistinguishable from "nothing done".
            curation = _curation_summary(
                "heuristic",
                executed_count=squashed,
                total_count=squashed,
                absorb_ran=absorb_ran,
                squashed_count=squashed,
            )
            out.print(
                f"Heuristic curation: absorb={'yes' if absorb_ran else 'no'}, "
                f"squashed={squashed} commits."
            )
        else:
            curation = _curation_summary("heuristic")
            if json_output:
                emit_json(
                    JsonEnvelope.failure(
                        "land.run",
                        ErrorKind.CURATION_FAILED,
                        f"Heuristic curation failed: {result['error']}",
                    )
                )
            else:
                err_console.print(
                    format_error(
                        f"Heuristic curation failed: {result['error']}",
                    )
                )
            raise SystemExit(ExitCode.FAILURE)
    else:
        agent_executed, agent_total = await _agent_curate(
            curation_ctx=curation_ctx,
            base=base,
            dry_run=dry_run,
            auto_approve=yes,
            cwd=cwd,
            json_mode=json_output,
            run_id=run_id,
        )
        curation = _curation_summary(
            "agent", executed_count=agent_executed, total_count=agent_total
        )

    if dry_run:
        out.print("Dry run — skipping next-step hint.")
        if json_output:
            assert report is not None
            if gate_blocks:
                emit_json(_frontier_blocked_envelope(report))
                raise SystemExit(ExitCode.FAILURE)
            emit_json(
                JsonEnvelope.success(
                    "land.run",
                    {
                        "landed": False,
                        "mode": "dry-run",
                        "verification": (verification.value if verification is not None else None),
                        "degraded": degraded,
                        "curation": curation,
                        "report": report.to_dict(),
                        "report_paths": report_paths,
                        "hint": None,
                    },
                )
            )
            return
        if gate_blocks:
            raise SystemExit(ExitCode.FAILURE)
        return

    # ── 3. Runway consolidation (best-effort) ─────────────────────
    await _maybe_consolidate(cwd, no_consolidate, json_mode=json_output)

    # ── 4. Mode-specific next-step hint ───────────────────────────
    if json_output:
        assert report is not None
        if eject:
            preview = branch or f"maverick/preview/{project_name}"
            hint = f"Eject hint: push to a preview branch with `git push origin HEAD:{preview}`."
        elif finalize:
            target = branch or f"maverick/{project_name}"
            md_path = report_paths.get("md")
            body_file = f" --body-file {md_path}" if md_path else ""
            hint = (
                f"Finalize hint: push to {target} and open a PR with "
                f"`gh pr create --base {base}{body_file}`."
            )
        else:
            hint = "Next: push the curated branch to your remote and open a PR."

        emit_json(
            JsonEnvelope.success(
                "land.run",
                {
                    "landed": True,
                    "mode": mode,
                    "verification": (verification.value if verification is not None else None),
                    "degraded": degraded,
                    "curation": curation,
                    "report": report.to_dict(),
                    "report_paths": report_paths,
                    "hint": hint,
                },
            )
        )
        return

    display_verification(verification, gate_entries)
    console.print(format_success(f"Curated {len(commits)} commit(s) on the current branch."))
    if eject:
        preview = branch or f"maverick/preview/{project_name}"
        console.print()
        console.print(
            f"Eject hint: push to a preview branch with "
            f"[bold]git push origin HEAD:{preview}[/bold]."
        )
    elif finalize:
        target = branch or f"maverick/{project_name}"
        # Only point at the markdown artifact when it actually landed —
        # persistence degrades to a warning, and `gh pr create --body-file`
        # against a missing path just fails for the user.
        body_file = f" --body-file {report_md_path}" if report_md_path is not None else ""
        console.print()
        console.print(
            f"Finalize hint: push to [bold]{target}[/bold] and open a PR with "
            f"[bold]gh pr create --base {base}{body_file}[/bold]."
        )
    else:
        console.print()
        console.print("Next: push the curated branch to your remote and open a PR.")


def _validate_status_flags(
    *,
    dry_run: bool,
    yes: bool,
    eject: bool,
    finalize: bool,
    no_curate: bool,
    heuristic_only: bool,
    json_mode: bool,
) -> None:
    """Enforce ``--status``'s mutual exclusion with every apply-path flag.

    ``--base``/``--branch`` are deliberately excluded — the contract accepts
    (and ignores) them in status mode since they always carry a default.
    """
    conflicting = {
        "--dry-run": dry_run,
        "--yes": yes,
        "--eject": eject,
        "--finalize": finalize,
        "--no-curate": no_curate,
        "--heuristic-only": heuristic_only,
    }
    conflicts = [name for name, is_set in conflicting.items() if is_set]
    if not conflicts:
        return

    message = f"--status cannot be combined with {', '.join(conflicts)}."
    if json_mode:
        emit_json(JsonEnvelope.failure("land.status", ErrorKind.VALIDATION, message))
    else:
        err_console.print(format_error(message))
    raise SystemExit(ExitCode.FAILURE)


def _curation_summary(
    strategy: str,
    *,
    executed_count: int = 0,
    total_count: int = 0,
    **extra: object,
) -> dict[str, object]:
    """Build the ``curation`` object carried by every ``land.run`` document.

    ``executed_count``/``total_count`` are the operation counts (agent
    path) or squash counts (heuristic path). Strategy-specific signals go
    in ``extra`` — the heuristic path adds ``absorb_ran``/``squashed_count``
    so an absorb-only rewrite isn't reported as a no-op.
    """
    summary: dict[str, object] = {
        "strategy": strategy,
        "executed_count": executed_count,
        "total_count": total_count,
    }
    summary.update(extra)
    return summary


def _frontier_blocked_envelope(report: LandReport) -> JsonEnvelope:
    """The shared ``frontier-blocked`` failure envelope for ``land.run``.

    Used both for the immediate refusal (non-dry-run) and the deferred
    refusal at the end of a ``--dry-run`` preview (052 semantics: the
    preview still runs, only the exit is delayed).
    """
    return JsonEnvelope.failure(
        "land.run",
        ErrorKind.FRONTIER_BLOCKED,
        "Assumption frontier is not clear — resolve or waive every open entry before landing.",
        details={"report": report.to_dict()},
    )


# =====================================================================
# Runway consolidation
# =====================================================================


async def _maybe_consolidate(
    cwd: Path,
    no_consolidate: bool,
    *,
    json_mode: bool = False,
) -> None:
    """Best-effort runway consolidation.

    Single-repo model: runway data lives in ``<cwd>/.maverick/runway/``
    and survives across runs without any sync step. Consolidation is the
    only operation worth running here — it prunes stale episodic records
    and updates the semantic summary.

    ``json_mode`` routes progress/warning narration to stderr instead of
    stdout — a JSON invocation's stdout must stay exactly one document.
    """
    if no_consolidate:
        return

    out = err_console if json_mode else console

    try:
        from maverick.config import load_config

        config = load_config()
        if not config.runway.enabled or not config.runway.consolidation.auto:
            return

        from maverick.library.actions.consolidation import consolidate_runway

        out.print("Consolidating runway knowledge store...")
        result = await consolidate_runway(
            cwd=cwd,
            max_age_days=config.runway.consolidation.max_episodic_age_days,
            max_records=config.runway.consolidation.max_episodic_records,
            force=False,
        )
        if result.skipped:
            logger.debug("runway_consolidation_skipped", reason=result.skip_reason)
        elif result.success:
            msg = f"  Pruned {result.records_pruned} old records."
            if result.summary_updated:
                msg += " Updated consolidated-insights.md."
            out.print(msg)
        else:
            out.print(format_warning(f"Runway consolidation failed: {result.error}"))
    except Exception as exc:
        # Best-effort — never block landing
        out.print(format_warning(f"Runway consolidation failed: {exc}"))
        logger.debug("runway_consolidation_error", error=str(exc))


# =====================================================================
# Agent curation
# =====================================================================


async def _agent_curate(
    curation_ctx: dict[str, Any],
    base: str,
    dry_run: bool,
    auto_approve: bool,
    cwd: Path,
    *,
    json_mode: bool = False,
    run_id: str = "",
) -> tuple[int, int]:
    """Run agent-driven curation with interactive approval.

    Returns ``(executed_count, total_count)`` — ``(0, 0)`` when the curator
    found nothing to do, ``(0, len(plan))`` for an unexecuted dry-run
    preview. In JSON mode (``json_mode=True``) progress narration goes to
    stderr, the plan table is never rendered to stdout, and reaching the
    interactive approval prompt instead emits a ``confirmation-required``
    envelope and exits — *before* ``execute_curation_plan`` runs (consent is
    the caller's job, never an interactive prompt in headless mode).
    """
    from maverick.library.actions.jj import execute_curation_plan

    out = err_console if json_mode else console
    out.print("Analyzing commits with curator agent...")

    try:
        from maverick.agents.personas import CuratorAgent
        from maverick.config import load_config
        from maverick.library.actions.curation import (
            build_curator_prompt,
            ensure_refs_trailers,
        )
        from maverick.protection import build_ad_hoc_protection
        from maverick.runtime.agent_factory import runtime_for_agent

        config = load_config()
        runtime, _ = runtime_for_agent("review", agents_config=config.agents)
        policy, collector = build_ad_hoc_protection(cwd, config)
        async with CuratorAgent(
            runtime=runtime,
            cwd=str(cwd),
            protection_policy=policy,
            block_collector=collector,
            workflow="land",
        ) as agent:
            payload = await agent.curate(
                build_curator_prompt(
                    {
                        "commits": curation_ctx["commits"],
                        "log_summary": curation_ctx["log_summary"],
                    }
                )
            )
        plan = [
            {"command": step.command, "args": list(step.args), "reason": step.reason}
            for step in payload.steps
        ]
        # Safety net: guarantee every ``describe`` carries a ``Refs:``
        # trailer so eval tooling can join landed commits to runway
        # state even if the curator skipped the prompt instruction
        # (FUTURE.md §3.9).
        plan = ensure_refs_trailers(plan, curation_ctx["commits"])

        # 056-context-file-protection T025: drain + persist, one
        # end-of-run warning when non-empty.
        from maverick.protection.records import drain_and_report

        blocks_run_id = run_id or "land"
        blocked = await drain_and_report(collector, cwd=cwd, run_id=blocks_run_id, workflow="land")
        if blocked:
            out.print(
                f"[yellow]{len(blocked)} context-file protection event(s) this run "
                f"— see .maverick/runs/{blocks_run_id}/protection-blocks.json[/]"
            )
    except SystemExit:
        raise
    except Exception as e:
        if json_mode:
            emit_json(
                JsonEnvelope.failure(
                    "land.run",
                    ErrorKind.CURATION_FAILED,
                    f"Curator agent failed: {e}",
                )
            )
        else:
            err_console.print(
                format_error(
                    f"Curator agent failed: {e}",
                    suggestion="Try --heuristic-only as a fallback.",
                )
            )
        raise SystemExit(ExitCode.FAILURE) from e

    if not plan:
        out.print("Curator: no curation needed — history looks clean.")
        return (0, 0)

    # Display plan (Rich table — stdout only; JSON mode relies on the
    # final curation summary object instead).
    if not json_mode:
        _display_plan(plan)

    if dry_run:
        out.print("Dry run — plan not applied.")
        # Do NOT raise SystemExit here — the caller (`land()`) decides the
        # final exit code from the assumption gate (`gate_blocks`), which
        # this branch must not pre-empt (T012 fix; analysis I1).
        return (0, len(plan))

    # Approval gate
    if not auto_approve:
        if json_mode:
            emit_json(
                JsonEnvelope.failure(
                    "land.run",
                    ErrorKind.CONFIRMATION_REQUIRED,
                    "Agent curation plan is ready but requires confirmation.",
                    details={"hint": "pass --yes"},
                )
            )
            raise SystemExit(ExitCode.FAILURE)
        answer = console.input("\nApply this plan? [y/N] ")
        if not answer.strip().lower().startswith("y"):
            console.print("Curation cancelled.")
            raise SystemExit(ExitCode.SUCCESS)

    # Execute
    out.print("Applying curation plan...")
    result = await execute_curation_plan(plan, cwd=cwd)
    if result["success"]:
        out.print(
            f"Curation complete: "
            f"{result['executed_count']}/{result['total_count']} "
            f"operations applied."
        )
        return (result["executed_count"], result["total_count"])
    else:
        if json_mode:
            emit_json(
                JsonEnvelope.failure(
                    "land.run",
                    ErrorKind.CURATION_FAILED,
                    f"Curation failed: {result['error']}",
                    details={
                        "executed_count": result["executed_count"],
                        "total_count": result["total_count"],
                        "snapshot_id": result["snapshot_id"],
                    },
                )
            )
        else:
            err_console.print(
                format_error(
                    f"Curation failed: {result['error']}",
                    details=[
                        f"Executed {result['executed_count']}/{result['total_count']} steps.",
                        f"Snapshot ID: {result['snapshot_id']} (for manual recovery).",
                    ],
                    suggestion=("Repository was rolled back to pre-curation state."),
                )
            )
        raise SystemExit(ExitCode.FAILURE)


def _display_plan(plan: list[dict[str, Any]]) -> None:
    """Render the curation plan as a Rich table inside a panel."""
    table = Table(
        show_header=True,
        header_style="bold",
        show_lines=False,
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Command", width=30)
    table.add_column("Reason")

    for i, step in enumerate(plan, 1):
        cmd_str = f"jj {step['command']} {' '.join(step.get('args', []))}"
        table.add_row(str(i), cmd_str, step.get("reason", ""))

    panel = Panel(
        table,
        title=(f"Curation Plan ({len(plan)} operation{'s' if len(plan) != 1 else ''})"),
        border_style="cyan",
    )
    console.print(panel)


def _display_human_review_manifest(cwd: Path) -> None:
    """Display human review manifest if one exists from the fly phase."""
    import json as _json

    plans_dir = cwd / ".maverick" / "plans"
    if not plans_dir.is_dir():
        return

    manifest_path = plans_dir / "human-review-manifest.json"
    if not manifest_path.is_file():
        return

    try:
        items = _json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return

    if not items:
        return

    needs_review = [i for i in items if i.get("status") == "needs-human-review"]
    if not needs_review:
        console.print(format_success("All beads passed review cleanly."))
        return

    console.print()
    table = Table(show_header=True, header_style="bold yellow")
    table.add_column("Bead", width=20)
    table.add_column("Title", width=40)
    table.add_column("Key Findings")

    for item in needs_review:
        findings_str = (
            "\n".join(
                f"  - {f[:100]}..." if len(f) > 100 else f"  - {f}"
                for f in item.get("key_findings", [])
            )
            or "(no findings captured)"
        )
        table.add_row(
            item.get("bead_id", "?"),
            item.get("title", "?")[:40],
            findings_str,
        )

    panel = Panel(
        table,
        title=f"Human Review Required ({len(needs_review)} bead{'s' if len(needs_review) != 1 else ''})",  # noqa: E501
        border_style="yellow",
    )
    console.print(panel)
    console.print()
