"""FlyBeadsWorkflow — bead-driven development workflow."""

from __future__ import annotations

import uuid
from datetime import UTC
from pathlib import Path
from typing import Any

from maverick.exceptions import WorkflowError
from maverick.library.actions.beads import (
    check_epic_done,
    mark_bead_complete,
    select_next_bead,
    verify_bead_completion,
)
from maverick.library.actions.types import VerifyBeadCompletionResult
from maverick.library.actions.git import git_has_changes, snapshot_uncommitted_changes
from maverick.library.actions.preflight import run_preflight_checks
from maverick.library.actions.validation import run_independent_gate
from maverick.library.actions.workspace import create_fly_workspace
from maverick.logging import get_logger
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.fly_beads.constants import (
    BASELINE_GATE,
    COMMIT,
    CREATE_WORKSPACE,
    MAX_BEADS,
    MAX_RETRIES_PER_BEAD,
    PREFLIGHT,
    SELECT_BEAD,
    SNAPSHOT_UNCOMMITTED,
    WORKFLOW_NAME,
)
from maverick.workflows.fly_beads.models import BeadContext, FlyBeadsResult
from maverick.workflows.fly_beads.steps import (
    commit_bead,
    fetch_runway_context,
    load_briefing_context,
    load_prior_attempt_context,
    load_work_unit_files,
    match_bead_to_work_unit,
    resolve_provenance,
    rollback_bead,
    run_acceptance_check,
    run_gate_check,
    run_gate_remediation,
    run_implement_and_validate,
    run_review_and_remediate,
    run_spec_compliance_check,
    snapshot_and_describe,
    snapshot_prior_attempt,
)
from maverick.workspace.manager import WorkspaceManager

logger = get_logger(__name__)


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
        step_executor: Optional agent step executor for implement steps.
        workflow_name: Identifier for this workflow instance.
    """

    def __init__(self, **kwargs: Any) -> None:
        workflow_name = kwargs.pop("workflow_name", WORKFLOW_NAME)
        super().__init__(workflow_name=workflow_name, **kwargs)

    async def _run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the fly-beads workflow.

        Args:
            inputs: Workflow inputs with keys:
                - epic_id: Optional epic to filter beads (default "")
                - max_beads: Maximum beads to process (default MAX_BEADS)
                - dry_run: If True, skip workspace creation (default False)
                - skip_review: If True, skip review step (default False)

        Returns:
            Summary dict with counts and workspace info.
        """
        # Parse inputs with defaults
        epic_id: str = str(inputs.get("epic_id", "") or "")
        max_beads: int = int(inputs.get("max_beads", MAX_BEADS))
        dry_run: bool = bool(inputs.get("dry_run", False))
        skip_review: bool = bool(inputs.get("skip_review", False))
        auto_commit: bool = bool(inputs.get("auto_commit", False))
        # Actor-mailbox architecture is the default, but falls back to
        # legacy path if the executor doesn't support multi-turn sessions
        # (e.g., in unit tests with mock executors).
        use_supervisor: bool = True

        # Load checkpoint to get previously completed beads
        checkpoint = await self.load_checkpoint()
        completed_bead_ids: set[str] = set()
        workspace_path: Path | None = None

        if checkpoint:
            completed_bead_ids = set(checkpoint.get("completed_bead_ids", []))
            ws_path_str = checkpoint.get("workspace_path")
            if ws_path_str:
                workspace_path = Path(ws_path_str)

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
        if epic_id:
            run_meta = find_run_for_epic(epic_id)
            if run_meta:
                run_id = run_meta.run_id
                run_dir = Path.cwd() / ".maverick" / "runs" / run_id
                run_meta.status = "flying"
                write_metadata(run_dir, run_meta)

        if not run_id:
            run_id = uuid.uuid4().hex[:8]
            run_dir = Path.cwd() / ".maverick" / "runs" / run_id
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

        # Track per-bead attempt counts for snapshot numbering
        bead_attempt_count: dict[str, int] = {}

        # Track counts for summary
        beads_succeeded = 0
        beads_failed = 0
        beads_skipped = 0

        # Track failure reasons per bead for retry context
        bead_failure_history: dict[str, list[str]] = {}
        # Track last review result per bead so we can reconstruct context
        # when a bead exhausts retries (ctx is not yet built at that point)
        bead_last_review: dict[str, dict[str, Any] | None] = {}
        # Track review issue counts per escalation chain root for
        # non-convergence detection
        chain_issue_trajectory: dict[str, list[int]] = {}
        # Accumulate items that need human review at land phase
        human_review_items: list[dict[str, Any]] = []
        # Track escalation depth per root bead across checkpoint boundaries.
        # Key: root bead ID, Value: number of follow-up tiers created.
        # Persisted in checkpoint so it survives session restarts.
        chain_depth: dict[str, int] = {}

        if checkpoint:
            chain_depth = checkpoint.get("chain_depth", {})

        # ----------------------------------------------------------------
        # Step 1: Preflight
        # ----------------------------------------------------------------
        await self.emit_step_started(PREFLIGHT)
        try:
            preflight_result = await run_preflight_checks(
                check_providers=True,
                check_git=True,
                check_jj=True,
                check_bd=True,
                check_validation_tools=False,
                fail_on_error=True,
                config=self._config,
            )
        except Exception as exc:
            await self.emit_step_failed(PREFLIGHT, str(exc))
            raise
        await self.emit_step_completed(PREFLIGHT, preflight_result.to_dict())

        # ----------------------------------------------------------------
        # Step 2: Snapshot uncommitted changes
        # ----------------------------------------------------------------
        # jj git clone only picks up committed state. If maverick init (or
        # the user) left uncommitted files, we need to commit them first so
        # the workspace clone includes everything.
        if not dry_run:
            await self.emit_step_started(SNAPSHOT_UNCOMMITTED)
            try:
                change_status = await git_has_changes()
                if change_status["has_any"]:
                    if auto_commit:
                        snap = await snapshot_uncommitted_changes()
                        if not snap["success"]:
                            err = snap["error"] or "commit failed"
                            await self.emit_step_failed(SNAPSHOT_UNCOMMITTED, err)
                            raise WorkflowError(
                                f"Snapshot failed: {err}",
                                workflow_name=WORKFLOW_NAME,
                            )
                        await self.emit_output(
                            SNAPSHOT_UNCOMMITTED,
                            f"Committed uncommitted changes ({snap['commit_sha'][:8]})",
                            level="info",
                        )
                        if snap.get("warning"):
                            await self.emit_output(
                                SNAPSHOT_UNCOMMITTED,
                                snap["warning"],
                                level="warning",
                            )
                    else:
                        await self.emit_step_failed(
                            SNAPSHOT_UNCOMMITTED,
                            "Uncommitted changes detected. Commit them first "
                            "or re-run with --auto-commit.",
                        )
                        raise WorkflowError(
                            "Uncommitted changes detected in the working directory. "
                            "The workspace clone will not include these changes. "
                            "Please commit them first or re-run with --auto-commit.",
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
        # Step 3: Create workspace (skipped in dry_run)
        # ----------------------------------------------------------------
        if not dry_run:
            await self.emit_step_started(CREATE_WORKSPACE)
            try:
                ws_result = await create_fly_workspace()
            except Exception as exc:
                await self.emit_step_failed(CREATE_WORKSPACE, str(exc))
                raise

            if not ws_result.get("success"):
                error_msg = ws_result.get("error") or "workspace creation failed"
                await self.emit_step_failed(CREATE_WORKSPACE, error_msg)
                raise WorkflowError(
                    f"create_fly_workspace failed: {error_msg}",
                    workflow_name=WORKFLOW_NAME,
                )

            workspace_path = Path(ws_result["workspace_path"])
            await self.emit_step_completed(CREATE_WORKSPACE, ws_result)

            # Initialize runway in workspace so recording works
            await _init_workspace_runway(workspace_path)

            # Register workspace teardown as rollback
            ws_manager = WorkspaceManager(user_repo_path=Path.cwd())

            async def _teardown() -> None:
                await ws_manager.teardown()

            self.register_rollback("workspace_teardown", _teardown)

        # ----------------------------------------------------------------
        # Step 3.5: Baseline validation gate
        # ----------------------------------------------------------------
        # Fail fast if the codebase isn't green before any bead work starts.
        # Pre-existing test/lint failures waste agent budget on unrelated fixes.
        if not dry_run:
            await self.emit_step_started(BASELINE_GATE)
            try:
                from maverick.workflows.fly_beads.steps import (
                    _build_validation_commands,
                )

                baseline_cmds = _build_validation_commands(
                    self._config.validation
                )
                baseline_result = await run_independent_gate(
                    stages=["format", "lint", "typecheck", "test"],
                    cwd=str(workspace_path),
                    validation_commands=baseline_cmds or None,
                    timeout_seconds=float(
                        self._config.validation.timeout_seconds
                    ),
                )
                if not baseline_result.get("passed"):
                    summary = baseline_result.get(
                        "summary", "unknown failures"
                    )
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
                await self.emit_step_completed(
                    BASELINE_GATE, baseline_result
                )

        # ----------------------------------------------------------------
        # Load work unit files once for bead description enrichment
        # ----------------------------------------------------------------
        # The bead database stores truncated plain-text descriptions.
        # The full structured markdown (File Scope, Acceptance Criteria,
        # Instructions, Test Specification, Verification) lives in the
        # work unit files on disk. Load them once and match to beads.
        _work_unit_bodies: dict[str, str] = {}
        _verification_properties: str = ""
        if not dry_run:
            # Try all known flight plan names from the first bead
            # (we'll populate on first bead selection)
            pass

        # ----------------------------------------------------------------
        # Bead loop
        # ----------------------------------------------------------------
        # max_beads caps *successful* completions, not total iterations.
        # Global safety limit prevents runaway loops; per-bead retry limit
        # (MAX_RETRIES_PER_BEAD) defers stuck beads after N failed attempts.
        max_iterations = max_beads * 3
        _iteration = 0
        while beads_succeeded < max_beads and _iteration < max_iterations:
            _iteration += 1
            # --- Select next bead ---
            await self.emit_step_started(SELECT_BEAD)
            try:
                select_result = await select_next_bead(epic_id=epic_id)
            except Exception as exc:
                await self.emit_step_failed(SELECT_BEAD, str(exc))
                raise
            await self.emit_step_completed(SELECT_BEAD, select_result.to_dict())

            # No more beads — done
            if select_result.done or not select_result.found:
                await self.emit_output(
                    SELECT_BEAD,
                    "No more ready beads — bead loop complete",
                    level="success",
                )
                break

            bead_id = select_result.bead_id
            bead_title = select_result.title

            await self.emit_output(
                SELECT_BEAD,
                f"Selected bead {bead_id}: {bead_title}",
                level="info",
            )

            # Skip beads we already completed (checkpoint resume)
            if bead_id in completed_bead_ids:
                beads_skipped += 1
                await self.emit_output(
                    SELECT_BEAD,
                    f"Skipping already-completed bead {bead_id}: {bead_title}",
                    level="info",
                )
                continue

            # Detect retry of a previously-failed bead
            prior_failures = bead_failure_history.get(bead_id, [])
            if prior_failures:
                attempt_num = len(prior_failures) + 1

                # Per-bead retry limit — commit what we have and spin off
                # a follow-up bead for unresolved review issues.
                if len(prior_failures) >= MAX_RETRIES_PER_BEAD:
                    reasons_summary = "; ".join(prior_failures[-3:])
                    await self.emit_output(
                        SELECT_BEAD,
                        f"Bead {bead_id} exhausted"
                        f" {MAX_RETRIES_PER_BEAD} attempts:"
                        f" {reasons_summary}."
                        " Escalating.",
                        level="warning",
                    )
                    try:
                        from maverick.workflows.fly_beads.steps import (
                            commit_bead_with_followup,
                        )

                        # Build a fresh context — ctx hasn't been
                        # constructed for this iteration yet.
                        retry_ctx = BeadContext(
                            bead_id=bead_id,
                            title=bead_title,
                            description=select_result.description,
                            epic_id=select_result.epic_id,
                            cwd=workspace_path,
                            run_dir=run_dir,
                            flight_plan_name=select_result.flight_plan_name or "",
                            prior_failures=prior_failures,
                            briefing_context=load_briefing_context(
                                select_result.flight_plan_name
                            ),
                        )
                        retry_ctx.review_result = bead_last_review.get(
                            bead_id
                        )

                        # Populate discovered-from chain for escalation
                        await resolve_provenance(retry_ctx)

                        # Track escalation depth from workflow state
                        # (survives checkpoint boundaries, unlike chain walk)
                        chain_root = (
                            retry_ctx.discovered_from_chain[0]
                            if retry_ctx.discovered_from_chain
                            else bead_id
                        )
                        current_depth = chain_depth.get(chain_root, 0) + 1
                        chain_depth[chain_root] = current_depth
                        retry_ctx.escalation_depth = current_depth

                        await commit_bead_with_followup(
                            self, retry_ctx, prior_failures
                        )
                        completed_bead_ids.add(bead_id)
                        beads_succeeded += 1
                        # Record for human review manifest if tagged
                        if retry_ctx.human_review_tag:
                            key_findings: list[str] = []
                            if retry_ctx.review_result:
                                for f in retry_ctx.review_result.get(
                                    "review_findings", []
                                )[:3]:
                                    key_findings.append(
                                        f.get("description", "")[:200]
                                    )
                            human_review_items.append({
                                "bead_id": bead_id,
                                "title": bead_title,
                                "status": "needs-human-review",
                                "escalation_depth": retry_ctx.escalation_depth,
                                "key_findings": key_findings,
                            })
                    except Exception as exc:
                        logger.warning(
                            "fly_beads_followup_failed",
                            bead_id=bead_id,
                            error=str(exc),
                        )
                        beads_failed += 1
                    continue

                prev_reason = prior_failures[-1]
                await self.emit_output(
                    SELECT_BEAD,
                    f"Retrying bead {bead_id} (attempt {attempt_num},"
                    f" previous failure: {prev_reason})",
                    level="warning",
                )

            # Load prior attempt context if this bead has been tried before
            prior_attempt_ctx: str | None = None
            prev_attempt = bead_attempt_count.get(bead_id, 0)
            if prev_attempt > 0:
                prior_attempt_ctx = load_prior_attempt_context(
                    run_dir, bead_id, prev_attempt
                )

            # Enrich bead description with full work unit markdown.
            # The bead database stores truncated plain-text; the work
            # unit files have structured sections the implementer and
            # AC checker need (File Scope, Instructions, Test Spec, etc.)
            fp_name = select_result.flight_plan_name or ""

            # Fallback: if flight_plan_name isn't on the bead, try
            # to discover it from .maverick/plans/ directory or epic
            if not fp_name and not _work_unit_bodies:
                plans_dir = Path.cwd() / ".maverick" / "plans"
                if plans_dir.is_dir():
                    for candidate in plans_dir.iterdir():
                        if candidate.is_dir() and (
                            candidate / "flight-plan.md"
                        ).exists():
                            fp_name = candidate.name
                            break

            if fp_name and not _work_unit_bodies:
                _work_unit_bodies.update(load_work_unit_files(fp_name))
                # Load verification properties from flight plan
                if not _verification_properties:
                    fp_path = (
                        Path.cwd()
                        / ".maverick"
                        / "plans"
                        / fp_name
                        / "flight-plan.md"
                    )
                    if fp_path.exists():
                        content = fp_path.read_text(encoding="utf-8")
                        from maverick.flight.parser import (
                            _split_h2_sections,
                        )

                        h2 = _split_h2_sections(content)
                        _verification_properties = h2.get(
                            "Verification Properties", ""
                        ).strip()

                # Fallback: read from run dir VP file
                if not _verification_properties and run_dir:
                    vp_file = run_dir / "verification-properties.txt"
                    if vp_file.exists():
                        _verification_properties = vp_file.read_text(
                            encoding="utf-8"
                        ).strip()

            enriched_description = select_result.description
            if _work_unit_bodies:
                wu_body = match_bead_to_work_unit(
                    bead_title, _work_unit_bodies
                )
                if wu_body:
                    enriched_description = wu_body

            # Build per-bead context
            ctx = BeadContext(
                bead_id=bead_id,
                title=bead_title,
                description=enriched_description,
                epic_id=select_result.epic_id,
                cwd=workspace_path,
                run_dir=run_dir,
                flight_plan_name=fp_name,
                prior_failures=prior_failures,
                prior_attempt_context=prior_attempt_ctx,
                briefing_context=load_briefing_context(fp_name),
            )

            logger.info(
                "fly_beads_processing_bead",
                bead_id=bead_id,
                title=bead_title,
                has_briefing=ctx.briefing_context is not None,
            )

            try:
                await resolve_provenance(ctx)
                await fetch_runway_context(self, ctx)
                await snapshot_and_describe(self, ctx)

                # Check if executor supports multi-turn (has create_session).
                # Mock executors in tests may not — fall back to legacy.
                _can_use_supervisor = (
                    use_supervisor
                    and self._step_executor is not None
                    and hasattr(self._step_executor, "create_session")
                )

                if _can_use_supervisor:
                    # --- Actor-mailbox path ---
                    outcome = await self._process_bead_with_supervisor(
                        ctx=ctx,
                        verification_properties=_verification_properties,
                    )
                    if outcome.committed:
                        completed_bead_ids.add(bead_id)
                        beads_succeeded += 1
                    else:
                        beads_failed += 1
                        bead_failure_history.setdefault(
                            bead_id, []
                        ).append(outcome.error or "supervisor failed")
                else:  # noqa: PLR5501
                    # --- Legacy step-pipeline path ---

                    # Agent implements + validates internally
                    await run_implement_and_validate(self, ctx)

                    # Orchestrator verifies independently (trust-but-verify)
                    await run_gate_check(self, ctx)

                    # One remediation attempt if gate failed
                    if ctx.gate_result and not ctx.gate_result.get("passed", False):
                        await run_gate_remediation(self, ctx)
                        await run_gate_check(self, ctx)

                    # Acceptance criteria check
                    gate_passed = ctx.gate_result and ctx.gate_result.get(
                        "passed", False
                    )
                    ac_passed = True
                    if gate_passed:
                        ac_passed, ac_reasons = await run_acceptance_check(
                            self, ctx
                        )
                        if not ac_reasons:
                            ac_reasons = []
                        if not ac_passed:
                            ctx.verify_result = VerifyBeadCompletionResult(
                                passed=False,
                                reasons=tuple(ac_reasons),
                            )
                            ac_attempt = bead_attempt_count.get(
                                bead_id, 0
                            ) + 1
                            bead_attempt_count[bead_id] = ac_attempt
                            await snapshot_prior_attempt(
                                run_dir, ctx, ac_attempt
                            )
                            if ac_attempt < MAX_RETRIES_PER_BEAD:
                                await rollback_bead(self, ctx)
                            beads_failed += 1
                            bead_failure_history.setdefault(
                                bead_id, []
                            ).append("; ".join(ac_reasons))
                            bead_last_review[bead_id] = ctx.review_result
                            continue

                    # Spec compliance
                    spec_passed = True
                    if (
                        gate_passed
                        and ac_passed
                        and _verification_properties
                    ):
                        spec_passed, spec_reasons = (
                            await run_spec_compliance_check(
                                self, ctx, _verification_properties
                            )
                        )
                        if not spec_passed:
                            ctx.verify_result = VerifyBeadCompletionResult(
                                passed=False,
                                reasons=tuple(spec_reasons),
                            )
                            sp_attempt = (
                                bead_attempt_count.get(bead_id, 0) + 1
                            )
                            bead_attempt_count[bead_id] = sp_attempt
                            await snapshot_prior_attempt(
                                run_dir, ctx, sp_attempt
                            )
                            if sp_attempt < MAX_RETRIES_PER_BEAD:
                                await rollback_bead(self, ctx)
                            beads_failed += 1
                            bead_failure_history.setdefault(
                                bead_id, []
                            ).append("; ".join(spec_reasons))
                            bead_last_review[bead_id] = ctx.review_result
                            continue

                    # Review
                    skip_this_review = skip_review or (
                        spec_passed and bool(_verification_properties)
                    )
                    if gate_passed and ac_passed:
                        await run_review_and_remediate(
                            self, ctx, skip_review=skip_this_review
                        )
                        if not skip_this_review and ctx.review_result:
                            await run_gate_check(self, ctx)

                    # Verify and decide
                    ctx.verify_result = await verify_bead_completion(
                        validation_result=ctx.gate_result or {},
                        review_result=ctx.review_result,
                        skip_review=skip_review,
                    )

                    if ctx.verify_result and ctx.verify_result.passed:
                        await commit_bead(self, ctx)
                        completed_bead_ids.add(ctx.bead_id)
                        beads_succeeded += 1
                    else:
                        attempt_num = bead_attempt_count.get(bead_id, 0) + 1
                        bead_attempt_count[bead_id] = attempt_num
                        await snapshot_prior_attempt(
                            run_dir, ctx, attempt_num
                        )
                        is_last_attempt = (
                            attempt_num >= MAX_RETRIES_PER_BEAD
                        )
                        if not is_last_attempt:
                            await rollback_bead(self, ctx)
                        beads_failed += 1
                        reasons = (
                            "; ".join(ctx.verify_result.reasons)
                            if ctx.verify_result
                            else "unknown"
                        )
                        bead_failure_history.setdefault(bead_id, []).append(reasons)
                        bead_last_review[bead_id] = ctx.review_result
                        if ctx.review_result:
                            issue_count = ctx.review_result.get(
                                "issues_remaining",
                                ctx.review_result.get("issues_found", 0),
                            )
                            chain_root = (
                                ctx.discovered_from_chain[0]
                                if ctx.discovered_from_chain
                                else bead_id
                            )
                            chain_issue_trajectory.setdefault(
                                chain_root, []
                            ).append(issue_count)

            except Exception as exc:
                logger.warning(
                    "fly_beads_bead_error",
                    bead_id=bead_id,
                    error=str(exc),
                )
                beads_failed += 1
                bead_failure_history.setdefault(bead_id, []).append(str(exc))

            # --- Checkpoint after each bead attempt ---
            await self.save_checkpoint(
                {
                    "completed_bead_ids": list(completed_bead_ids),
                    "workspace_path": str(workspace_path) if workspace_path else None,
                    "epic_id": epic_id,
                    "chain_depth": chain_depth,
                }
            )

            # --- Check if epic is done ---
            try:
                done_result = await check_epic_done(epic_id=epic_id)
                if done_result.done:
                    # Close the epic if all its children are closed.
                    if done_result.all_children_closed and epic_id:
                        try:
                            await mark_bead_complete(
                                bead_id=epic_id,
                                reason="All child beads completed",
                            )
                            await self.emit_output(
                                COMMIT,
                                f"Epic {epic_id} closed — all"
                                f" {done_result.total_children} child"
                                " beads completed",
                                level="success",
                            )
                        except Exception as exc:
                            logger.warning(
                                "epic_close_failed",
                                epic_id=epic_id,
                                error=str(exc),
                            )
                    await self.emit_output(
                        COMMIT,
                        "Epic done — no more ready beads"
                        f" (completed {beads_succeeded})",
                        level="success",
                    )
                    break
            except Exception as exc:
                logger.warning("check_epic_done_failed", error=str(exc))

        # Write human review manifest for the land phase
        if human_review_items:
            import json as _json

            manifest_dir = Path.cwd() / ".maverick" / "plans"
            manifest_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = manifest_dir / "human-review-manifest.json"
            try:
                manifest_path.write_text(
                    _json.dumps(human_review_items, indent=2)
                )
                logger.info(
                    "human_review_manifest_written",
                    path=str(manifest_path),
                    count=len(human_review_items),
                )
            except Exception as exc:
                logger.warning(
                    "human_review_manifest_write_failed", error=str(exc)
                )

        beads_processed = beads_succeeded + beads_failed + beads_skipped

        # Update run metadata with final status
        if run_dir:
            final_meta = read_metadata(run_dir)
            if final_meta:
                from datetime import datetime as _dt

                final_meta.status = (
                    "completed" if beads_failed == 0 else "failed"
                )
                final_meta.completed_at = (
                    _dt.now(tz=UTC).isoformat()
                )
                write_metadata(run_dir, final_meta)

        result = FlyBeadsResult(
            epic_id=epic_id,
            workspace_path=str(workspace_path) if workspace_path else None,
            beads_processed=beads_processed,
            beads_succeeded=beads_succeeded,
            beads_failed=beads_failed,
            beads_skipped=beads_skipped,
            human_review_items=tuple(human_review_items),
        )
        return result.to_dict()

    async def _process_bead_with_supervisor(
        self,
        *,
        ctx: BeadContext,
        verification_properties: str = "",
    ) -> Any:
        """Process a bead using the actor-mailbox supervisor.

        Creates actors, runs the supervisor loop, writes the fly report.
        Returns a BeadOutcome.

        This replaces the inline step pipeline for a single bead's
        processing when use_supervisor=True.
        """
        from datetime import datetime as _dt

        from maverick.workflows.fly_beads.actors.acceptance import (
            AcceptanceCriteriaActor,
        )
        from maverick.workflows.fly_beads.actors.committer import CommitActor
        from maverick.workflows.fly_beads.actors.gate import GateActor
        from maverick.workflows.fly_beads.actors.implementer import (
            ImplementerActor,
        )
        from maverick.workflows.fly_beads.actors.reviewer import ReviewerActor
        from maverick.workflows.fly_beads.actors.spec_compliance import (
            SpecComplianceActor,
        )
        from maverick.workflows.fly_beads.fly_report import (
            build_fly_report,
            write_fly_report,
        )
        from maverick.workflows.fly_beads.session_registry import (
            BeadSessionRegistry,
        )
        from maverick.workflows.fly_beads.steps import (
            _build_validation_commands,
            _is_verification_only,
            _parse_work_unit_sections,
        )
        from maverick.workflows.fly_beads.supervisor import BeadSupervisor

        import shutil as _shutil

        from acp.schema import McpServerStdio

        started_at = _dt.now(tz=UTC).isoformat()
        cwd_str = str(ctx.cwd) if ctx.cwd else None

        # Set up MCP inbox for agent actors
        inbox_dir = (
            ctx.run_dir / "beads" / ctx.bead_id / "inbox"
            if ctx.run_dir
            else Path.cwd() / ".maverick" / "tmp" / "inbox"
        )
        inbox_dir.mkdir(parents=True, exist_ok=True)
        _maverick_bin = _shutil.which("maverick") or "maverick"

        def _mcp_config(tools: str, agent_name: str) -> McpServerStdio:
            return McpServerStdio(
                name="supervisor-inbox",
                command=_maverick_bin,
                args=[
                    "serve-inbox",
                    "--tools", tools,
                    "--output", str(inbox_dir / f"{agent_name}-inbox.json"),
                ],
                env=[],
            )

        # Build validation commands from config (defensive for tests with mocks)
        validation_commands: dict[str, list[str]] | None = None
        _timeout_secs = 600.0
        try:
            validation_commands = _build_validation_commands(
                self._config.validation
            )
            _timeout_secs = float(self._config.validation.timeout_seconds)
        except (AttributeError, TypeError):
            pass

        # Create session registry for this bead
        session_registry = BeadSessionRegistry(bead_id=ctx.bead_id)

        # Resolve step configs for implementer and reviewer
        from maverick.executor.config import StepConfig  # noqa: E402
        from maverick.workflows.base import StepType  # noqa: E402

        impl_config = self.resolve_step_config(
            step_name="implement",
            step_type=StepType.PYTHON,
            agent_name="implementer",
        )
        review_config = self.resolve_step_config(
            step_name="completeness_review",
            step_type=StepType.PYTHON,
            agent_name="completeness_reviewer",
        )

        # Determine allowed tools
        allowed_tools = None
        if _is_verification_only(ctx):
            allowed_tools = ["Read", "Glob", "Grep"]

        # Build initial implement payload from work unit sections
        parsed = _parse_work_unit_sections(ctx.description)
        initial_payload: dict[str, Any] = {
            "task_description": parsed.get("task", ctx.description),
            "cwd": cwd_str,
        }
        if parsed.get("acceptance criteria"):
            initial_payload["acceptance_criteria"] = parsed["acceptance criteria"]
        if parsed.get("file scope"):
            initial_payload["file_scope"] = parsed["file scope"]
        procedure = parsed.get("procedure") or parsed.get("instructions")
        if procedure:
            initial_payload["procedure"] = procedure
        if parsed.get("test specification"):
            initial_payload["test_to_pass"] = parsed["test specification"]
        if parsed.get("verification"):
            initial_payload["verification_commands"] = parsed["verification"]
        if ctx.runway_context:
            initial_payload["runway_context"] = ctx.runway_context

        # Create actors
        actors: dict[str, Any] = {
            "implementer": ImplementerActor(
                session_registry=session_registry,
                executor=self._step_executor,
                cwd=ctx.cwd,
                config=impl_config,
                allowed_tools=allowed_tools,
                inbox_path=inbox_dir / "implementer-inbox.json",
                mcp_server_config=_mcp_config(
                    "submit_implementation,submit_fix_result", "implementer"
                ),
            ),
            "gate": GateActor(
                cwd=cwd_str,
                validation_commands=validation_commands,
                timeout_seconds=_timeout_secs,
            ),
            "acceptance_criteria": AcceptanceCriteriaActor(
                cwd=ctx.cwd,
                description=ctx.description,
            ),
            "spec_compliance": SpecComplianceActor(
                cwd=ctx.cwd,
                verification_properties=verification_properties,
            ),
            "reviewer": ReviewerActor(
                session_registry=session_registry,
                executor=self._step_executor,
                cwd=ctx.cwd,
                config=review_config,
                bead_description=ctx.description,
                inbox_path=inbox_dir / "reviewer-inbox.json",
                mcp_server_config=_mcp_config(
                    "submit_review", "reviewer"
                ),
            ),
            "committer": CommitActor(
                bead_id=ctx.bead_id,
                title=ctx.title,
                cwd=ctx.cwd,
            ),
        }

        # Run supervisor
        supervisor = BeadSupervisor(
            bead_id=ctx.bead_id,
            actors=actors,
            initial_payload=initial_payload,
        )

        await self.emit_output(
            "supervisor",
            f"Processing bead {ctx.bead_id} with actor-mailbox supervisor",
            level="info",
        )

        outcome = await supervisor.process_bead()

        # Clean up sessions
        session_registry.close_all()

        # Write fly report
        if ctx.run_dir:
            report = build_fly_report(
                bead_outcome=outcome,
                title=ctx.title,
                epic_id=ctx.epic_id,
                started_at=started_at,
            )
            await write_fly_report(report, ctx.run_dir)

        # Emit result
        status = "completed" if outcome.committed else "failed"
        tag = " [needs-human-review]" if outcome.needs_human_review else ""
        await self.emit_output(
            "supervisor",
            f"Bead {ctx.bead_id} {status}{tag}"
            f" ({outcome.review_rounds} review rounds,"
            f" {len(outcome.message_log)} messages,"
            f" {outcome.duration_seconds:.1f}s)",
            level="success" if outcome.committed else "warning",
        )

        return outcome


async def _init_workspace_runway(workspace_path: Path) -> None:
    """Initialize runway store in the workspace (best-effort).

    The workspace is a fresh jj clone without ``.maverick/runway/``.
    Without initialization, all runway recording during fly silently
    fails because ``_get_store()`` returns None.

    Args:
        workspace_path: Path to the hidden workspace directory.
    """
    from maverick.runway.store import RunwayStore

    try:
        runway_path = workspace_path / ".maverick" / "runway"
        store = RunwayStore(runway_path)
        if not store.is_initialized:
            await store.initialize()
            logger.info(
                "workspace_runway_initialized",
                path=str(runway_path),
            )
    except Exception as exc:
        # Best-effort — don't block fly if runway init fails
        logger.warning(
            "workspace_runway_init_failed",
            error=str(exc),
        )
