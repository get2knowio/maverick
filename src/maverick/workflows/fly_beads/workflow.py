"""FlyBeadsWorkflow — bead-driven development workflow."""

from __future__ import annotations

import uuid
from datetime import UTC
from pathlib import Path
from typing import Any

from maverick.exceptions import WorkflowError
from maverick.library.actions.git import git_has_changes
from maverick.library.actions.git_models import GitStatusResult
from maverick.library.actions.jj import jj_snapshot_changes
from maverick.library.actions.preflight import run_preflight_checks
from maverick.library.actions.validation import run_independent_gate
from maverick.logging import get_logger
from maverick.runners.provider_health import providers_for_fly
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.fly_beads.constants import (
    BASELINE_GATE,
    MAX_BEADS,
    PREFLIGHT,
    SNAPSHOT_UNCOMMITTED,
    WORKFLOW_NAME,
)
from maverick.workflows.fly_beads.models import FlyBeadsResult

logger = get_logger(__name__)

_DIRTY_FILE_LIST_LIMIT = 20


def _format_dirty_file_summary(status: GitStatusResult) -> str:
    """Render a short, human-readable list of uncommitted paths.

    Caps each category at ``_DIRTY_FILE_LIST_LIMIT`` so a repo with
    thousands of untracked build artifacts doesn't drown the error
    message. The user can always run ``git status`` for the full list.
    """

    def _section(label: str, paths: tuple[str, ...]) -> list[str]:
        if not paths:
            return []
        head = list(paths[:_DIRTY_FILE_LIST_LIMIT])
        more = len(paths) - len(head)
        lines = [f"  {label} ({len(paths)}):"]
        lines.extend(f"    {p}" for p in head)
        if more > 0:
            lines.append(f"    ... and {more} more")
        return lines

    chunks: list[str] = []
    chunks.extend(_section("Staged", status.staged_files))
    chunks.extend(_section("Unstaged", status.unstaged_files))
    chunks.extend(_section("Untracked", status.untracked_files))
    return "\n".join(chunks) if chunks else "  (no files reported)"


class FlyBeadsWorkflow(PythonWorkflow):
    """Bead-driven development workflow with invariant-based orchestration.

    For each bead: implement+validate (agent) → gate check (orchestrator) →
    optional gate remediation → review+remediate → final gate → commit/rollback.

    The agent owns implementation and validation internally. The workflow
    enforces gates (independent validation) and structural invariants.

    Args:
        config: Project configuration.
        registry: Component registry.
        checkpoint_store: Optional checkpoint persistence.
        workflow_name: Identifier for this workflow instance.
    """

    def __init__(self, **kwargs: Any) -> None:
        # Extract checkpoint_store before passing to super (which ignores it)
        self._checkpoint_store = kwargs.pop("checkpoint_store", None)
        workflow_name = kwargs.pop("workflow_name", WORKFLOW_NAME)
        super().__init__(workflow_name=workflow_name, **kwargs)

    # ------------------------------------------------------------------
    # Checkpointing (fly-specific)
    # ------------------------------------------------------------------

    async def save_checkpoint(self, data: dict[str, Any]) -> None:
        """Save a checkpoint via the configured CheckpointStore.

        No-op if checkpoint_store is None.

        Args:
            data: Checkpoint data to persist.
        """
        if self._checkpoint_store is None:
            return

        from datetime import UTC, datetime

        from maverick.checkpoint.data import CheckpointData, compute_inputs_hash
        from maverick.events import CheckpointSaved

        checkpoint_id = self._current_step or "checkpoint"
        cp = CheckpointData(
            checkpoint_id=checkpoint_id,
            workflow_name=self._workflow_name,
            inputs_hash=compute_inputs_hash(data),
            step_results=tuple(r.to_dict() for r in self._step_results),
            saved_at=datetime.now(tz=UTC).isoformat(),
            user_data=data,
        )
        await self._checkpoint_store.save(self._workflow_name, cp)

        await self._event_queue.put(
            CheckpointSaved(
                step_name=self._current_step or "checkpoint",
                workflow_id=self._workflow_name,
            )
        )

    async def load_checkpoint(self) -> dict[str, Any] | None:
        """Load the latest checkpoint for this workflow.

        Returns:
            Checkpoint data dict, or None if no checkpoint exists or
            checkpoint_store is None.
        """
        if self._checkpoint_store is None:
            return None

        cp = await self._checkpoint_store.load_latest(self._workflow_name)
        if cp is None:
            return None

        # Return the user-provided data from the checkpoint (not the metadata)
        return cp.user_data

    async def _run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the fly-beads workflow.

        Args:
            inputs: Workflow inputs with keys:
                - epic_id: Optional epic to filter beads (default "")
                - max_beads: Maximum beads to process (default MAX_BEADS)

        Returns:
            Summary dict with counts and workspace info.
        """
        # Parse inputs with defaults
        epic_id: str = str(inputs.get("epic_id", "") or "")
        max_beads: int = int(inputs.get("max_beads", MAX_BEADS))
        auto_commit: bool = bool(inputs.get("auto_commit", False))
        watch: bool = bool(inputs.get("watch", False))
        watch_interval: int = int(inputs.get("watch_interval", 30))
        skip_preflight: bool = bool(inputs.get("skip_preflight", False))
        isolated: bool = bool(inputs.get("isolated", False))

        # Load checkpoint to get previously completed beads.
        checkpoint = await self.load_checkpoint()
        completed_bead_ids: set[str] = set()

        if checkpoint:
            completed_bead_ids = set(checkpoint.get("completed_bead_ids", []))

        # The workflow's ``cwd`` is required — the CLI command resolves
        # ``Path.cwd()`` at the entry boundary and threads it through
        # inputs. A missing ``cwd`` here would silently fall back to
        # ``Path.cwd()`` and write per-run output (``.maverick/runs/``)
        # into whatever directory pytest happened to run from, which
        # has caused real repo contamination — see Guardrail 7.
        cwd_input = inputs.get("cwd")
        if not cwd_input:
            raise WorkflowError("'cwd' input is required")
        cwd = Path(str(cwd_input)).resolve()

        # Per-run output directory for snapshots, logs, and context.
        # Try to find an existing run for the epic (created by refuel).
        # Fall back to generating a new run_id if none found.
        from maverick.runway.run_metadata import (
            RunMetadata as _RunMeta,  # noqa: N814
        )
        from maverick.runway.run_metadata import (
            find_run_for_epic,
            read_metadata,
            write_metadata,
        )

        run_id = ""
        run_dir: Path | None = None
        flight_plan_name: str = ""
        if epic_id:
            run_meta = find_run_for_epic(epic_id, base=cwd)
            if run_meta:
                run_id = run_meta.run_id
                run_dir = cwd / ".maverick" / "runs" / run_id
                run_meta.status = "flying"
                write_metadata(run_dir, run_meta)
                flight_plan_name = run_meta.plan_name or ""

        if not run_id:
            run_id = uuid.uuid4().hex[:8]
            run_dir = cwd / ".maverick" / "runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            write_metadata(
                run_dir,
                _RunMeta(
                    run_id=run_id,
                    plan_name="",
                    epic_id=epic_id,
                    status="flying",
                ),
            )

        # ----------------------------------------------------------------
        # Step 1: Preflight
        # ----------------------------------------------------------------
        if skip_preflight:
            await self.emit_step_started(PREFLIGHT, display_label="Pre-flight checks")
            await self.emit_output(
                PREFLIGHT,
                "Skipped (--skip-preflight)",
                level="warning",
            )
            await self.emit_step_completed(PREFLIGHT, {"skipped": True})
        else:
            await self.emit_step_started(PREFLIGHT, display_label="Pre-flight checks")
            try:
                preflight_result = await run_preflight_checks(
                    check_providers=True,
                    check_git=True,
                    check_jj=True,
                    check_bd=True,
                    check_validation_tools=False,
                    fail_on_error=True,
                    config=self._config,
                    provider_filter=providers_for_fly(self._config),
                )
            except Exception as exc:
                await self.emit_step_failed(PREFLIGHT, str(exc))
                raise
            await self.emit_step_completed(PREFLIGHT, preflight_result.to_dict())

        # ----------------------------------------------------------------
        # Step 2: Snapshot uncommitted changes
        # ----------------------------------------------------------------
        # Single-repo model: bead commits land directly on the user's
        # current branch, so a dirty tree at fly start would interleave
        # with bead commits. Fail closed unless --auto-commit is set,
        # then snapshot via the right VCS (jj or plain-git).
        await self.emit_step_started(SNAPSHOT_UNCOMMITTED, display_label="Snapshotting changes")
        try:
            change_status = await git_has_changes()
            if change_status.has_any:
                if auto_commit:
                    snap = await jj_snapshot_changes(
                        message="chore: snapshot uncommitted changes before fly",
                        cwd=cwd,
                    )
                    if not snap.success:
                        err = snap.error or "commit failed"
                        await self.emit_step_failed(SNAPSHOT_UNCOMMITTED, err)
                        raise WorkflowError(
                            f"Snapshot failed: {err}",
                            workflow_name=WORKFLOW_NAME,
                        )
                    sha_preview = (snap.commit_sha or "")[:8]
                    await self.emit_output(
                        SNAPSHOT_UNCOMMITTED,
                        f"Committed uncommitted changes ({sha_preview})",
                        level="info",
                    )
                    if snap.warning:
                        await self.emit_output(
                            SNAPSHOT_UNCOMMITTED,
                            snap.warning,
                            level="warning",
                        )
                else:
                    file_list = _format_dirty_file_summary(change_status)
                    await self.emit_step_failed(
                        SNAPSHOT_UNCOMMITTED,
                        "Uncommitted changes detected. Commit them first "
                        "or re-run with --auto-commit.\n" + file_list,
                    )
                    raise WorkflowError(
                        "Uncommitted changes detected in the working directory. "
                        "Bead commits will interleave with your in-progress edits. "
                        "Please commit them first or re-run with --auto-commit.\n" + file_list,
                        workflow_name=WORKFLOW_NAME,
                    )
            else:
                await self.emit_output(
                    SNAPSHOT_UNCOMMITTED,
                    "Working directory clean — no snapshot needed",
                    level="info",
                )
        except WorkflowError:
            raise
        except Exception as exc:
            await self.emit_step_failed(SNAPSHOT_UNCOMMITTED, str(exc))
            raise
        await self.emit_step_completed(SNAPSHOT_UNCOMMITTED, change_status)

        # ----------------------------------------------------------------
        # Step 3: Baseline validation gate
        # ----------------------------------------------------------------
        # Fail fast if the codebase isn't green before any bead work starts.
        # Pre-existing test/lint failures waste agent budget on unrelated fixes.
        await self.emit_step_started(BASELINE_GATE, display_label="Baseline gate check")
        try:
            from maverick.workflows.fly_beads.steps import (
                _build_validation_commands,
            )

            baseline_cmds = _build_validation_commands(self._config.validation)
            baseline_result = await run_independent_gate(
                stages=["format", "lint", "typecheck", "test"],
                cwd=str(cwd),
                validation_commands=baseline_cmds or None,
                timeout_seconds=float(self._config.validation.timeout_seconds),
            )
            if not baseline_result.get("passed"):
                summary = baseline_result.get("summary", "unknown failures")
                await self.emit_output(
                    BASELINE_GATE,
                    f"WARNING: Baseline validation failed: {summary}. "
                    f"Pre-existing failures may consume agent budget. "
                    f"Consider fixing these before running fly.",
                    level="warning",
                )
        except WorkflowError:
            raise
        except Exception as exc:
            # Non-fatal: if baseline check itself errors, warn and
            # continue — don't block the entire fly on infra issues.
            logger.warning(
                "baseline_gate_error",
                error=str(exc),
            )
            await self.emit_output(
                BASELINE_GATE,
                f"Baseline gate check error (continuing): {exc}",
                level="warning",
            )
        else:
            await self.emit_step_completed(BASELINE_GATE, baseline_result)

        # ----------------------------------------------------------------
        # Bead loop — driven by the Burr application around the
        # FlySquadron. Watch mode keeps the loop alive after the bead
        # queue drains, polling for newly-ready beads every
        # ``watch_interval`` seconds up to a fixed idle cap.
        # ----------------------------------------------------------------
        burr_result = await _run_bead_loop(
            self,
            epic_id=epic_id,
            cwd=cwd,
            max_beads=max_beads,
            completed_bead_ids=tuple(completed_bead_ids or ()),
            flight_plan_name=flight_plan_name,
            watch=watch,
            watch_interval=watch_interval,
            run_id=run_id,
            isolated=isolated,
        )

        # 057-isolated-bead-workspaces (FR-018): an undo failure is the
        # worst state this feature can produce — halt the run loudly with
        # recovery instructions rather than let it read as an ordinary
        # bead failure. Checked before any of the summary/metadata work
        # below, which still assumes a normal (non-halted) outcome.
        isolation_halt_reason = str(burr_result.get("isolation_halt_reason") or "")
        if isolation_halt_reason:
            from maverick.cli.console import err_console

            err_console.print(
                "[red]Isolated run halted: an isolation undo failed.[/red]\n"
                f"{isolation_halt_reason}\n\n"
                "[yellow]No further beads were started.[/yellow] The checkout may hold "
                "an unverified fold-back delta. Inspect it by hand (`jj status`, "
                "`jj op log`), then remove the isolation journal at "
                f"{cwd / '.maverick' / 'runs' / 'isolation-journal.json'} before retrying."
            )
            raise WorkflowError(
                f"isolated fly run halted: {isolation_halt_reason}",
                workflow_name=WORKFLOW_NAME,
            )

        beads_succeeded = int(burr_result.get("beads_completed", 0))
        beads_failed = int(burr_result.get("beads_failed", 0))
        beads_skipped = int(burr_result.get("beads_skipped", 0))
        human_review_items = burr_result.get("human_review_items")
        if human_review_items is None:
            human_review_items = [
                {
                    "bead_id": event["bead_id"],
                    "title": event["title"],
                    "status": "needs-human-review",
                    "tag": event.get("tag"),
                    "review_rounds": event.get("review_rounds", 0),
                }
                for event in burr_result.get("bead_events", [])
                if event.get("tag") == "needs-human-review"
            ]
        human_review_items = tuple(human_review_items)
        beads_processed = beads_succeeded + beads_failed + beads_skipped

        # 056-context-file-protection: persist protection-blocks.json when
        # this run produced any blocks — no-op (returns None) on an empty
        # list, and a write failure degrades to a warning, never fails
        # the run.
        if run_dir:
            from maverick.protection.records import BlockRecord, persist_blocks_artifact

            protection_records = [
                BlockRecord.from_dict(d) for d in burr_result.get("protection_blocks", [])
            ]
            await persist_blocks_artifact(
                run_dir=run_dir,
                run_id=run_id,
                workflow=WORKFLOW_NAME,
                records=protection_records,
            )

            # Update run metadata with final status
            final_meta = read_metadata(run_dir)
            if final_meta:
                from datetime import datetime as _dt

                final_meta.status = "completed" if beads_failed == 0 else "failed"
                final_meta.completed_at = _dt.now(tz=UTC).isoformat()
                write_metadata(run_dir, final_meta)

        result = FlyBeadsResult(
            epic_id=epic_id,
            cwd=str(cwd),
            beads_processed=beads_processed,
            beads_succeeded=beads_succeeded,
            beads_failed=beads_failed,
            beads_skipped=beads_skipped,
            human_review_items=human_review_items,
        )
        return result.to_dict()


def _cost_sink_for_cwd(cwd: Path) -> Any:
    """Return a :class:`CostSink` appender for the user repo's runway store.

    Returns ``None`` when the runway store under ``<cwd>/.maverick/runway/``
    isn't initialized — callers fall back to structured-log-only telemetry.
    Run ``maverick runway init`` to enable persistent cost recording.

    The sink closes over the :class:`RunwayStore` so the actor mixin can
    fire-and-forget without touching workflow state.
    """
    from maverick.runway.store import RunwayStore, make_cost_sink

    runway_path = cwd / ".maverick" / "runway"
    store = RunwayStore(runway_path)
    if not store.is_initialized:
        return None
    return make_cost_sink(store)


async def _run_bead_loop(
    workflow: Any,
    *,
    epic_id: str,
    cwd: Path,
    max_beads: int,
    completed_bead_ids: tuple[str, ...],
    flight_plan_name: str = "",
    watch: bool = False,
    watch_interval: int = 30,
    run_id: str = "",
    isolated: bool = False,
) -> dict[str, Any]:
    """Drive the fly Burr application; return the aggregate bead counts.

    Lives outside the class so the import-cycle (squadron → workflow)
    stays manageable: callers pass ``self`` in as ``workflow``.

    Args:
        run_id: This run's own ``run_id`` (already minted by
            :meth:`FlyBeadsWorkflow._run` before the bead loop starts) —
            threaded to the mid-flight reconcile actions
            (052-conditional-landing) so a triggered ``ReconcileWorkflow``
            pass can exclude this run from its own concurrent-fly guard.
        isolated: 057-isolated-bead-workspaces — run every bead's agent
            steps in its own workspace. ``IsolationSession``'s lock
            (contract C1) and stale-journal refusal (contract C2) span
            this whole function, not just one bead — that is what "held
            for the whole isolated run" means (research.md R8).
    """
    import asyncio as _asyncio
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime

    from maverick.burr import BurrWorkflowDriver
    from maverick.config import lookup_tiers_config
    from maverick.events import ProgressEvent
    from maverick.squadron.fly import FlySquadron
    from maverick.workflows.fly_beads.burr_graph import (
        FLY_TERMINAL_ACTIONS,
        build_fly_application,
    )

    cost_sink = _cost_sink_for_cwd(cwd)

    def _isolation_now() -> _datetime:
        # UTC-aware, matching spec-chain's `_utcnow` — both consumers feed
        # the same shared ApplicationRecord.started_at/IsolationLease.created_at
        # fields, which must carry a consistent, comparable clock.
        return _datetime.now(_UTC)

    isolation_session: Any = None
    isolation_policy: Any = None
    if isolated:
        from maverick.config import lookup_workspace_config
        from maverick.jj.client import JjClient
        from maverick.protection.config import lookup_protection_config
        from maverick.workflows.fly_beads._isolation import build_isolation_policy
        from maverick.workspace import CheckoutPath, IsolationSession

        workspace_config = lookup_workspace_config(workflow._config)
        protection_config = lookup_protection_config(workflow._config)
        # Best-effort second protection layer (research.md R11) — the
        # protection policy re-rooted at the workspace (T075) is the
        # primary defense; this fixed set plus the user's own configured
        # globs is a belt-and-braces exclusion on the fold-back fileset
        # itself. Does not attempt to replicate the protected set's
        # basename-anywhere matching for AGENTS.md/CLAUDE.md at arbitrary
        # depth — only the common top-level case.
        fold_exclusions = (
            ".specify/memory",
            "AGENTS.md",
            "CLAUDE.md",
            *protection_config.additional_globs,
        )
        isolation_policy = build_isolation_policy(
            root=workspace_config.root, fold_exclusions=fold_exclusions
        )
        isolation_session = IsolationSession(
            checkout=CheckoutPath(cwd),
            policy=isolation_policy,
            jj_client=JjClient(cwd=cwd),
            run_id=run_id,
            now=_isolation_now,
        )

    async with (
        _isolation_session_scope(isolation_session),
        FlySquadron(
            cwd=cwd,
            config=workflow._config,
            cost_sink=cost_sink,
            # ``actors.fly.{implementer,reviewer}.tiers`` was parsed by the
            # supervisors the Burr migration deleted, which left the whole
            # tier surface inert (#135). The squadron has always accepted
            # these; nothing was passing them.
            implementer_tiers=lookup_tiers_config(workflow._config, "fly-beads", "implementer"),
            reviewer_tiers=lookup_tiers_config(workflow._config, "fly-beads", "reviewer"),
        ) as squadron,
    ):
        if isolation_session is not None:
            # No workspace is ever meant to survive across runs (fly's
            # policy is reuse=False) — sweep clears anything an
            # interrupted prior run left behind before this one's own
            # bead loop starts (FR-028, T092).
            await isolation_session.sweep(keep=set())

        event_queue: _asyncio.Queue[ProgressEvent | None] = _asyncio.Queue()
        app = build_fly_application(
            squadron=squadron,
            event_queue=event_queue,
            epic_id=epic_id,
            cwd=str(cwd),
            max_beads=max_beads,
            completed_bead_ids=completed_bead_ids,
            validation_commands=None,
            project_type=getattr(workflow._config, "project_type", "rust") or "rust",
            flight_plan_name=flight_plan_name,
            watch=watch,
            watch_interval=watch_interval,
            reconcile_config=workflow._config,
            fly_run_id=run_id,
            isolated=isolated,
            isolation_session=isolation_session,
            isolation_policy=isolation_policy,
            isolation_now=_isolation_now if isolated else None,
        )
        driver = BurrWorkflowDriver(
            app,
            halt_after=FLY_TERMINAL_ACTIONS,
            event_queue=event_queue,
        )
        async for evt in driver.events():
            await workflow._event_queue.put(evt)
        _, _result, state = driver.result

    bead_events = list(state.get("bead_events") or ())
    return {
        "beads_completed": int(state.get("succeeded_count", 0)),
        "beads_failed": int(state.get("failed_count", 0)),
        "beads_skipped": int(state.get("skipped_count", 0)),
        "completed_bead_ids": list(state.get("completed_bead_ids") or ()),
        "bead_events": bead_events,
        "human_review_items": tuple(
            {
                "bead_id": e["bead_id"],
                "title": e["title"],
                "status": "needs-human-review",
                "tag": e.get("tag"),
                "review_rounds": e.get("review_rounds", 0),
            }
            for e in bead_events
            if e.get("tag") == "needs-human-review"
        ),
        # 056-context-file-protection: serialized BlockRecord dicts
        # accumulated across the whole run, for the caller to persist.
        "protection_blocks": list(state.get("protection_blocks") or ()),
        # 057-isolated-bead-workspaces: set only when an undo failed
        # (FR-018) — the caller halts and prints recovery instructions.
        "isolation_halt_reason": state.get("isolation_halt_reason") or "",
    }


def _isolation_session_scope(session: Any) -> Any:
    """``async with session:`` when isolated, a no-op otherwise — keeps
    ``_run_bead_loop`` from branching its whole body on ``isolated``."""
    import contextlib

    if session is None:
        return contextlib.nullcontext()
    return session
