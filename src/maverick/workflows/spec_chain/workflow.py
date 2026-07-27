"""``SpecChainWorkflow`` — headless Spec Kit chain orchestration (`maverick spec`).

Async orchestration: hidden workspace -> sequential steps (specify ->
clarify -> plan -> tasks -> analyze) with tenacity retries and explicit
timeouts -> per-step landing -> checkpoint after every transition ->
``SpecChainReport``. Step success is gated on verified filesystem
artifacts, not agent claims (R9) — this workflow owns every deterministic
effect (workspace lifecycle, ordering, checkpointing, landing);
``SpecChainAgent`` provides judgment only (Guardrail X.3 / Principle II).
"""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from airframe.errors import RuntimeTransientError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from maverick.assumptions.ledger import record_standalone_assumption
from maverick.beads.client import BeadClient
from maverick.exceptions import WorkflowError
from maverick.jj.client import JjClient
from maverick.library.actions.beads import create_remediation_beads
from maverick.logging import get_logger
from maverick.payloads import AssumptionPayload
from maverick.squadron.spec_chain import SpecChainSquadron
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.spec_chain.clarify import (
    assumptions_from_spec_md,
    decisions_from_spec_md,
)
from maverick.workflows.spec_chain.constants import (
    CHAIN_STEP_ORDER,
    SOURCE_REF_ASSUMPTIONS,
    SOURCE_REF_CLARIFY,
    ChainStep,
)
from maverick.workflows.spec_chain.landing import (
    land_step_artifacts,
    resolve_feature_dir,
    verify_step_artifacts,
)
from maverick.workflows.spec_chain.models import (
    AnalyzeFinding,
    ChainState,
    ClarifyDecision,
    SpecChainReport,
    StepRecord,
    StepReport,
    StepStatus,
    is_valid_feature_slug,
)
from maverick.workflows.spec_chain.state import (
    load_chain_state,
    resumable_features,
    save_chain_state,
)
from maverick.workflows.spec_chain.steps import build_step_prompt
from maverick.workspace.spec_chain import (
    prepare_workspace,
    sweep_stale_workspaces,
    teardown_workspace,
)

__all__ = ["WORKFLOW_NAME", "SpecChainWorkflow"]

logger = get_logger(__name__)

#: Read by `execute_python_workflow` from this module's namespace.
WORKFLOW_NAME = "spec-chain"

#: Step-run retry policy for transient runtime errors (constitution
#: Principle IV: default 3 attempts, exponential backoff).
_STEP_RETRY_ATTEMPTS = 3


def _normalize_question(question: str) -> str:
    """Casefold + collapse-whitespace normalization for dedup matching.

    Mirrors ``maverick.assumptions.ledger._normalize_question`` so the
    in-state clarify-decision dedup key aligns with the ledger's own
    bead-dedup key — kept local to avoid importing a private helper.
    """
    return " ".join(question.split()).casefold()


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


async def _read_text(path: Path) -> str:
    return await asyncio.to_thread(path.read_text, encoding="utf-8")


async def _list_dir_names(path: Path) -> set[str]:
    def _list() -> set[str]:
        if not path.is_dir():
            return set()
        return {p.name for p in path.iterdir() if p.is_dir()}

    return await asyncio.to_thread(_list)


def _set_step(
    state: ChainState,
    step: ChainStep,
    *,
    status: StepStatus,
    artifacts: list[str] | None = None,
    landed: bool | None = None,
    error: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> ChainState:
    """Return *state* with *step*'s record updated (functional — ``steps``
    values are frozen models, so every transition builds a fresh record)."""
    existing = state.steps.get(step)
    attempts = existing.attempts if existing else 0
    if status == "in_progress":
        attempts += 1
    record = StepRecord(
        step=step,
        status=status,
        attempts=attempts,
        artifacts=artifacts if artifacts is not None else (existing.artifacts if existing else []),
        landed=landed if landed is not None else (existing.landed if existing else False),
        error=error,
        started_at=started_at
        if started_at is not None
        else (existing.started_at if existing else None),
        finished_at=finished_at,
    )
    new_steps = dict(state.steps)
    new_steps[step] = record
    return state.model_copy(update={"steps": new_steps, "updated_at": _utcnow()})


def _mark_downstream_skipped(state: ChainState, failed_step: ChainStep) -> ChainState:
    """FR-010: every step after *failed_step* that never got a record is
    marked ``skipped`` — so a halted chain's report names not just what
    failed, but everything that consequently never ran.
    """
    idx = CHAIN_STEP_ORDER.index(failed_step)
    new_steps = dict(state.steps)
    for later in CHAIN_STEP_ORDER[idx + 1 :]:
        if later not in new_steps:
            new_steps[later] = StepRecord(
                step=later,
                status="skipped",
                attempts=0,
                artifacts=[],
                landed=False,
                error=None,
                started_at=None,
                finished_at=None,
            )
    return state.model_copy(update={"steps": new_steps})


def _build_report(state: ChainState) -> SpecChainReport:
    resume_hint = f"maverick spec {state.feature}" if state.status == "halted" else None
    return SpecChainReport(
        feature_dir=state.feature_dir,
        status=state.status,
        steps=tuple(state.steps[s] for s in CHAIN_STEP_ORDER if s in state.steps),
        ledger_entry_count=len(state.clarify_decisions),
        remediation_bead_count=len(state.remediation_bead_ids),
        resume_hint=resume_hint,
    )


class SpecChainWorkflow(PythonWorkflow):
    """Runs the headless Spec Kit chain for one feature."""

    def __init__(self, **kwargs: Any) -> None:
        if "workflow_name" not in kwargs:
            kwargs["workflow_name"] = WORKFLOW_NAME
        super().__init__(**kwargs)

    async def _run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the spec chain — fresh, or resumed from a halted/running
        checkpoint (contracts/chain-state.md "Resume resolution").

        Args:
            inputs: Required: ``run_id`` (str — the CLI resolves this
                *before* calling the workflow: either the run id of a
                resumable chain discovered via
                :func:`~maverick.workflows.spec_chain.state.discover_resumable`,
                or a freshly generated one, so it can read the final
                persisted state back afterward), ``feature`` (str), ``cwd``
                (str, user checkout). ``prd_path`` (str) is required for a
                fresh run, optional when resuming (the persisted state
                already has the original PRD path/digest). Optional:
                ``home`` (str) — override for ``~`` (tests only;
                production never sets this, so ``prepare_workspace`` uses
                the real home directory).

        Returns:
            :meth:`SpecChainReport.to_dict`.
        """
        feature: str = inputs["feature"]
        # Validate the slug BEFORE any path is built from it: the hidden
        # workspace dir is derived from `feature` (prepare_workspace) well
        # before ChainState's model-level validator runs, so a value like
        # "../../x" would otherwise traverse outside the workspace root and
        # create a stray jj workspace before validation ever fires.
        if not is_valid_feature_slug(feature):
            raise WorkflowError(
                f"invalid feature name {feature!r}: must be a non-empty, "
                "filesystem-safe slug (letters, digits, hyphen, underscore; "
                "no path separators or leading dots)"
            )
        cwd = Path(inputs["cwd"])
        run_id_input: str | None = inputs.get("run_id") or None
        prd_path_str: str = inputs.get("prd_path", "")
        home_str: str | None = inputs.get("home")
        home = Path(home_str) if home_str else None

        await self.emit_step_started("prepare", display_label="Preparing")

        existing_state = await load_chain_state(run_id_input, cwd) if run_id_input else None
        resuming = existing_state is not None and existing_state.status in (
            "running",
            "halted",
        )

        if resuming:
            assert existing_state is not None  # narrows for type checkers
            state, run_id, prd_content, workspace_path = await self._resume(
                existing_state, feature=feature, cwd=cwd, prd_path_str=prd_path_str, home=home
            )
        else:
            if not prd_path_str:
                raise WorkflowError("'prd_path' input is required for a fresh spec-chain run")
            state, run_id, prd_content, workspace_path = await self._start_fresh(
                run_id_input, feature=feature, cwd=cwd, prd_path_str=prd_path_str, home=home
            )

        async def _checkpoint_halted_on_cancel() -> None:
            """Graceful-interrupt rollback (T032): flip status to `halted`
            on the freshest on-disk checkpoint. Re-loads from disk rather
            than an in-memory snapshot since `_run_one_step` checkpoints
            *before* every cancellable await — the on-disk state is
            always current up to the last safe boundary. A hard crash
            (kill -9) never runs this and leaves `status="running"`,
            which resume treats as stale-resumable (contracts/chain-state.md).
            """
            current = await load_chain_state(run_id, cwd)
            if current is not None and current.status == "running":
                halted = current.model_copy(update={"status": "halted", "updated_at": _utcnow()})
                await save_chain_state(halted, cwd)
                logger.info("spec_chain_checkpointed_halted_on_interrupt", run_id=run_id)

        self.register_rollback("spec_chain_checkpoint_on_interrupt", _checkpoint_halted_on_cancel)

        checkout_specs_before = await _list_dir_names(cwd / "specs")
        await self.emit_step_completed("prepare", output={"workspace_path": str(workspace_path)})
        logger.info(
            "spec_chain_workspace_prepared",
            run_id=run_id,
            feature=feature,
            workspace_path=str(workspace_path),
            resumed=resuming,
        )

        async with SpecChainSquadron(cwd=workspace_path, config=self._config) as squadron:
            for step in CHAIN_STEP_ORDER:
                existing_record = state.steps.get(step)
                if existing_record is not None and existing_record.status == "succeeded":
                    continue  # resume: never regenerate a landed step (FR-020)
                state = await self._run_one_step(
                    step,
                    state=state,
                    squadron=squadron,
                    workspace=workspace_path,
                    checkout=cwd,
                    checkout_specs_before=checkout_specs_before,
                    prd_content=prd_content,
                )
                if state.status != "running":
                    break

        if state.status == "running":
            state = state.model_copy(update={"status": "completed", "updated_at": _utcnow()})
            await save_chain_state(state, cwd)
            # Completed only. A halted or interrupted chain keeps its
            # workspace: it holds the failing step's partial output, and
            # resume reuses it. A completed chain's cannot even be resumed —
            # re-running the feature hits the CLI's spec-dir collision check —
            # so it is pure garbage, and left alone it would strand a stray
            # anonymous head in the user's own commit graph forever.
            # Checkpointed first: cleanup is best-effort and must never be
            # able to lose the record that the chain finished.
            await teardown_workspace(
                cwd=cwd, feature=feature, jj_client=JjClient(cwd=cwd), home=home
            )

        logger.info("spec_chain_finished", run_id=run_id, feature=feature, status=state.status)
        return _build_report(state).to_dict()

    async def _sweep_stale_workspaces(
        self, *, cwd: Path, feature: str, jj_client: JjClient, home: Path | None
    ) -> None:
        """Collect workspaces left behind by chains that never completed.

        Teardown-on-completion never fires for a chain the user abandoned
        with Ctrl-C, which is the realistic leak, so the sweep is what
        actually bounds growth.

        The keep-set is this layer's policy call, which is why it is computed
        here rather than inside ``workspace/``: resumability is a property of
        ``.maverick/runs`` state, not of the filesystem. *feature* is always
        kept — on a fresh run ``prepare_workspace`` is about to recreate it,
        on a resume it is in active use.
        """
        try:
            keep = await resumable_features(cwd)
        except Exception as exc:  # noqa: BLE001 — never block a run on cleanup
            logger.warning("spec_chain_workspace_sweep_skipped", error=str(exc))
            return
        keep.add(feature)
        await sweep_stale_workspaces(cwd=cwd, jj_client=jj_client, keep=keep, home=home)

    async def _start_fresh(
        self,
        run_id_input: str | None,
        *,
        feature: str,
        cwd: Path,
        prd_path_str: str,
        home: Path | None,
    ) -> tuple[ChainState, str, str, Path]:
        run_id = run_id_input or uuid4().hex[:8]
        prd_path = Path(prd_path_str)
        prd_content = await _read_text(prd_path)
        prd_digest = hashlib.sha256(prd_content.encode("utf-8")).hexdigest()

        jj_client = JjClient(cwd=cwd)
        await self._sweep_stale_workspaces(
            cwd=cwd, feature=feature, jj_client=jj_client, home=home
        )
        workspace_path = await prepare_workspace(
            cwd=cwd,
            feature=feature,
            prd_path=prd_path,
            reuse=False,
            jj_client=jj_client,
            home=home,
        )

        now = _utcnow()
        state = ChainState(
            run_id=run_id,
            feature=feature,
            feature_dir=None,
            prd_path=str(prd_path),
            prd_digest=prd_digest,
            workspace_path=str(workspace_path),
            status="running",
            steps={},
            clarify_decisions=[],
            remediation_bead_ids=[],
            started_at=now,
            updated_at=now,
        )
        await save_chain_state(state, cwd)
        return state, run_id, prd_content, workspace_path

    async def _resume(
        self,
        existing_state: ChainState,
        *,
        feature: str,
        cwd: Path,
        prd_path_str: str,
        home: Path | None,
    ) -> tuple[ChainState, str, str, Path]:
        state = existing_state
        run_id = state.run_id
        prd_path = Path(state.prd_path)

        if prd_path_str and Path(prd_path_str).resolve() != prd_path.resolve():
            await self.emit_output(
                "prepare",
                f"Ignoring --from-prd on resume; continuing with the original PRD ({prd_path})",
                level="warning",
            )

        prd_content = ""
        if prd_path.is_file():
            prd_content = await _read_text(prd_path)
            current_digest = hashlib.sha256(prd_content.encode("utf-8")).hexdigest()
            if current_digest != state.prd_digest:
                await self.emit_output(
                    "prepare",
                    "PRD content has changed since this chain started — "
                    "continuing without re-running specify (FR-020).",
                    level="warning",
                )

        jj_client = JjClient(cwd=cwd)
        await self._sweep_stale_workspaces(
            cwd=cwd, feature=feature, jj_client=jj_client, home=home
        )
        workspace_path = await prepare_workspace(
            cwd=cwd,
            feature=feature,
            prd_path=prd_path,
            reuse=True,
            jj_client=jj_client,
            home=home,
        )

        state = state.model_copy(
            update={
                "status": "running",
                "workspace_path": str(workspace_path),
                "updated_at": _utcnow(),
            }
        )
        state = await self._verify_landed_or_reset(state, checkout=cwd)
        self._reseed_workspace_from_checkout(state, workspace=workspace_path, checkout=cwd)
        await save_chain_state(state, cwd)
        return state, run_id, prd_content, workspace_path

    async def _verify_landed_or_reset(self, state: ChainState, *, checkout: Path) -> ChainState:
        """Resume guarantee (contracts/chain-state.md): verify each
        `landed` step's artifacts still exist in the checkout; a step
        whose artifacts vanished (e.g. the user deleted the spec dir) is
        reset to `pending` so it re-runs instead of being trusted blindly.
        """
        if state.feature_dir is None:
            return state
        feature_dir_name = Path(state.feature_dir).name
        feature_path = checkout / "specs" / feature_dir_name

        new_steps = dict(state.steps)
        changed = False
        for step, record in state.steps.items():
            if record.status != "succeeded" or not record.landed:
                continue
            missing = [a for a in record.artifacts if not (feature_path / a).is_file()]
            if missing:
                new_steps[step] = record.model_copy(
                    update={"status": "pending", "landed": False, "artifacts": []}
                )
                changed = True
                logger.warning(
                    "spec_chain_landed_artifacts_missing_resetting_step",
                    step=step.value,
                    missing=missing,
                )
        if not changed:
            return state
        return state.model_copy(update={"steps": new_steps, "updated_at": _utcnow()})

    def _reseed_workspace_from_checkout(
        self, state: ChainState, *, workspace: Path, checkout: Path
    ) -> None:
        """Restore landed upstream artifacts into a freshly-recreated
        workspace on resume.

        Landed artifacts live only in the checkout's working copy (landing
        copies workspace -> checkout after each step; nothing is committed
        into the workspace). If the on-disk hidden workspace vanished
        between runs (e.g. the user cleared ``~/.maverick/workspaces``),
        ``prepare_workspace(reuse=True)`` rebuilds it from the *committed*
        tree — which lacks those un-committed spec files — so the next step
        would run against a workspace missing everything upstream. Copy the
        checkout's landed feature dir back in to close that gap. Idempotent:
        a no-op when the workspace already has all landed artifacts (the
        normal reuse case).
        """
        if state.feature_dir is None:
            return
        feature_dir_name = Path(state.feature_dir).name
        checkout_feature = checkout / "specs" / feature_dir_name
        workspace_feature = workspace / "specs" / feature_dir_name
        if not checkout_feature.is_dir():
            return

        landed_artifacts = {
            artifact
            for record in state.steps.values()
            if record.status == "succeeded" and record.landed
            for artifact in record.artifacts
        }
        if landed_artifacts and all(
            (workspace_feature / artifact).is_file() for artifact in landed_artifacts
        ):
            return  # workspace already holds every landed artifact — reuse path.

        shutil.copytree(checkout_feature, workspace_feature, dirs_exist_ok=True)
        logger.info(
            "spec_chain_workspace_reseeded_from_checkout",
            feature_dir=feature_dir_name,
            artifacts=sorted(landed_artifacts),
        )

    async def _run_one_step(
        self,
        step: ChainStep,
        *,
        state: ChainState,
        squadron: SpecChainSquadron,
        workspace: Path,
        checkout: Path,
        checkout_specs_before: set[str],
        prd_content: str,
    ) -> ChainState:
        display = step.value.title()
        await self.emit_step_started(step.value, display_label=display)
        started_at = _utcnow()
        state = _set_step(state, step, status="in_progress", started_at=started_at)
        await save_chain_state(state, checkout)
        logger.info("spec_chain_step_started", step=step.value, run_id=state.run_id)

        prompt = build_step_prompt(
            step,
            workspace=workspace,
            feature=state.feature,
            prd_content=prd_content if step is ChainStep.SPECIFY else None,
        )

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(_STEP_RETRY_ATTEMPTS),
                wait=wait_exponential(multiplier=1, min=2, max=20),
                # Only transient runtime errors are worth retrying. Auth,
                # model-not-found, context-overflow, budget-exceeded, etc.
                # are deterministic — retrying just burns model calls and
                # backoff before the same failure. Matches how the fly /
                # refuel actions treat airframe errors (only
                # RuntimeTransientError bumps a tier); everything else
                # falls straight through to `_fail_step` below. CLAUDE.md:
                # context-overflow is intentionally never retried.
                retry=retry_if_exception_type(RuntimeTransientError),
                reraise=True,
            ):
                with attempt:
                    report = await squadron.chain_agent.run_step(prompt)
        except Exception as exc:  # noqa: BLE001 - any runtime failure halts this step
            logger.warning("spec_chain_step_run_failed", step=step.value, error=str(exc))
            return await self._fail_step(state, step, checkout, started_at, str(exc), display)

        # The filesystem is ground truth for *success* (R9) — a
        # well-formed "completed" report with no artifacts is still a
        # failure, checked below. But an honest agent self-report of
        # "blocked" or "failed" (FR-009's clarify-can't-form-a-defensible-
        # default edge case) must not be silently overridden just because
        # some file happens to already exist from an earlier step.
        if report.status in ("blocked", "failed"):
            return await self._fail_step(
                state,
                step,
                checkout,
                started_at,
                report.detail or f"agent reported {report.status}",
                display,
            )

        if step is ChainStep.SPECIFY and state.feature_dir is None:
            feature_dir_name = resolve_feature_dir(
                workspace=workspace, checkout_specs_before=checkout_specs_before
            )
            if feature_dir_name is None:
                return await self._fail_step(
                    state,
                    step,
                    checkout,
                    started_at,
                    "specify did not allocate a resolvable specs/NNN-<feature> directory",
                    display,
                )
            state = state.model_copy(update={"feature_dir": f"specs/{feature_dir_name}"})

        if state.feature_dir is None:
            return await self._fail_step(
                state, step, checkout, started_at, "no feature directory known yet", display
            )
        feature_dir_name = Path(state.feature_dir).name

        artifacts = verify_step_artifacts(
            workspace=workspace, feature_dir=feature_dir_name, step=step
        )
        if step is not ChainStep.ANALYZE and not artifacts:
            return await self._fail_step(
                state,
                step,
                checkout,
                started_at,
                f"{step.value} produced no verifiable artifacts",
                display,
            )

        if step is ChainStep.CLARIFY:
            state = await self._file_clarify_decisions(
                state,
                workspace=workspace,
                checkout=checkout,
                feature_dir_name=feature_dir_name,
            )

        if step is ChainStep.ANALYZE:
            state = await self._create_remediation_beads(
                state, checkout=checkout, feature_dir_name=feature_dir_name, report=report
            )

        try:
            land_step_artifacts(
                workspace=workspace, checkout=checkout, feature_dir=feature_dir_name
            )
        except OSError as exc:
            return await self._fail_step(
                state, step, checkout, started_at, f"landing failed: {exc}", display
            )
        logger.info(
            "spec_chain_step_landed",
            step=step.value,
            feature_dir=state.feature_dir,
            artifacts=artifacts,
        )

        finished_at = _utcnow()
        state = _set_step(
            state,
            step,
            status="succeeded",
            artifacts=artifacts,
            landed=True,
            finished_at=finished_at,
        )
        await save_chain_state(state, checkout)
        logger.info(
            "spec_chain_step_checkpointed",
            step=step.value,
            status="succeeded",
            run_id=state.run_id,
        )
        await self.emit_step_completed(
            step.value, output={"artifacts": artifacts}, display_label=display
        )
        return state

    async def _file_clarify_decisions(
        self,
        state: ChainState,
        *,
        workspace: Path,
        checkout: Path,
        feature_dir_name: str,
    ) -> ChainState:
        """File every clarify decision recorded in spec.md as a standalone
        assumption-ledger entry (R2/R5) — in the user's checkout, never the
        workspace (Guardrail X.3: the workflow owns deterministic side
        effects, the agent never writes beads).

        Best-effort per decision: a single bd failure is logged and the
        decision is still recorded on ``ChainState`` (without a
        ``ledger_bead_id``) rather than sinking clarify's success — the
        audit trail is advisory, not load-bearing for chain progress.
        """
        spec_md_path = workspace / "specs" / feature_dir_name / "spec.md"
        if not spec_md_path.is_file():
            return state
        spec_content = await _read_text(spec_md_path)
        # Two sources, one ledger. `## Clarifications` holds what clarify was
        # asked and answered; `## Assumptions` holds what specify decided
        # unasked. Both are adopted answers with no human in the loop, so both
        # belong in front of the land gate. Clarify wins a tie: if the same
        # topic appears in both, its bullet is the more deliberate record.
        parsed_decisions = decisions_from_spec_md(spec_content)
        seen = {_normalize_question(d.question) for d in parsed_decisions}
        assumption_decisions = [
            d
            for d in assumptions_from_spec_md(spec_content)
            if _normalize_question(d.question) not in seen
        ]
        parsed_decisions.extend(assumption_decisions)
        if not parsed_decisions:
            return state

        bead_client = BeadClient(cwd=checkout)
        filed: list[ClarifyDecision] = []
        for decision in parsed_decisions:
            payload = AssumptionPayload(
                question=decision.question,
                adopted_answer=decision.adopted_answer,
                alternatives=decision.alternatives,
                severity=decision.severity.value,
                severity_defaulted=decision.severity_defaulted,
            )
            try:
                record = await record_standalone_assumption(
                    bead_client,
                    payload=payload,
                    owner_spec=feature_dir_name,
                    source_ref=(
                        SOURCE_REF_ASSUMPTIONS
                        if decision.path == "assumptions_section"
                        else SOURCE_REF_CLARIFY
                    ),
                )
            except Exception as exc:  # noqa: BLE001 — one bad entry must not sink clarify
                logger.warning(
                    "spec_chain_clarify_ledger_filing_failed",
                    question=decision.question,
                    error=str(exc),
                )
                filed.append(decision)
                continue
            bead_id = record.bead_id if record is not None else None
            filed.append(replace(decision, ledger_bead_id=bead_id))

        logger.info(
            "spec_chain_clarify_decisions_filed",
            count=len(filed),
            ledger_entries=sum(1 for d in filed if d.ledger_bead_id),
        )
        # Merge by normalized question rather than blindly appending: on a
        # resume that re-runs clarify (e.g. it halted after filing but
        # before the next step landed), `state.clarify_decisions` already
        # holds the prior run's decisions and re-parsing spec.md yields the
        # same questions. Blind append would double the list and inflate
        # `ledger_entry_count` / the CLI's "Clarify questions answered"
        # count, even though ledger dedup already prevented duplicate beads.
        merged: dict[str, ClarifyDecision] = {
            _normalize_question(d.question): d for d in state.clarify_decisions
        }
        for decision in filed:
            merged[_normalize_question(decision.question)] = decision
        return state.model_copy(update={"clarify_decisions": list(merged.values())})

    async def _create_remediation_beads(
        self,
        state: ChainState,
        *,
        checkout: Path,
        feature_dir_name: str,
        report: StepReport,
    ) -> ChainState:
        """After a successful analyze step, convert each reported finding
        into a standalone remediation bead (R6) — in the user's checkout,
        never the workspace. Best-effort: bd failures are logged, never
        raised — analyze findings must never block an otherwise-successful
        run (FR-012).
        """
        if not report.findings:
            return state

        findings = [
            AnalyzeFinding(
                title=f.title,
                category=f.category,
                severity_hint=f.severity_hint,
                location=f.location,
                summary=f.summary,
                feature_dir=feature_dir_name,
            )
            for f in report.findings
        ]

        try:
            result = await create_remediation_beads(findings, cwd=checkout)
        except Exception as exc:  # noqa: BLE001 — analyze findings must never block the chain
            logger.warning("spec_chain_remediation_bead_creation_failed", error=str(exc))
            return state

        if result.errors:
            logger.warning("spec_chain_remediation_bead_partial_failure", errors=result.errors)
        logger.info(
            "spec_chain_remediation_beads_created",
            count=len(result.created_bead_ids),
            skipped=len(result.skipped_duplicate_fingerprints),
        )
        return state.model_copy(
            update={
                "remediation_bead_ids": [
                    *state.remediation_bead_ids,
                    *result.created_bead_ids,
                ]
            }
        )

    async def _fail_step(
        self,
        state: ChainState,
        step: ChainStep,
        checkout: Path,
        started_at: datetime,
        error: str,
        display: str,
    ) -> ChainState:
        """Record *step* as failed and halt the chain — unless *step* is
        ``analyze``, whose failures degrade to a warning (FR-012) and never
        block an otherwise-successful run.
        """
        finished_at = _utcnow()
        state = _set_step(state, step, status="failed", error=error, finished_at=finished_at)
        new_status = "completed" if step is ChainStep.ANALYZE else "halted"
        if new_status == "halted":
            state = _mark_downstream_skipped(state, step)
        state = state.model_copy(update={"status": new_status, "updated_at": finished_at})
        await save_chain_state(state, checkout)
        if step is ChainStep.ANALYZE:
            await self.emit_output(
                step.value, f"analyze failed (non-fatal): {error}", level="warning"
            )
            await self.emit_step_completed(
                step.value, output={"error": error}, display_label=display
            )
        else:
            await self.emit_step_failed(step.value, error, display_label=display)
        return state
