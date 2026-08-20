"""Chain-state persistence and resume discovery for the spec-chain workflow.

Chain state is persisted to ``.maverick/runs/<run-id>/spec-chain.json``
(schema_version 1) via atomic temp-file+rename writes after every step
transition. See specs/050-headless-spec-chain/contracts/chain-state.md.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from maverick.logging import get_logger
from maverick.utils.atomic import atomic_write_text
from maverick.workflows.spec_chain.models import ChainState

__all__ = [
    "discover_resumable",
    "load_chain_state",
    "resumable_features",
    "save_chain_state",
]

logger = get_logger(__name__)

_RUNS_SUBDIR = Path(".maverick") / "runs"
_STATE_FILENAME = "spec-chain.json"

#: Chain statuses discover_resumable treats as resumable. "running" covers
#: crash/kill — staleness is assumed, not probed (single-user CLI).
_RESUMABLE_STATUSES = frozenset({"halted", "running"})


def _state_path(base: Path, run_id: str) -> Path:
    return base / _RUNS_SUBDIR / run_id / _STATE_FILENAME


async def save_chain_state(state: ChainState, base: Path) -> None:
    """Atomically persist *state* to ``.maverick/runs/<run_id>/spec-chain.json``."""
    path = _state_path(base, state.run_id)
    content = json.dumps(state.model_dump(mode="json"), indent=2)
    await asyncio.to_thread(atomic_write_text, path, content, mkdir=True)


async def load_chain_state(run_id: str, base: Path) -> ChainState | None:
    """Load a persisted chain state by run id. ``None`` if not found.

    057-isolated-bead-workspaces (FR-043, contracts/spec-chain-migration.md
    "Checkpoint compatibility"): a checkpoint written before this feature
    carries no ``schema_version`` key at all — ``ChainState``'s own
    ``default=1`` would otherwise silently treat that absence as the
    current schema, exactly the "resume must never silently misbehave"
    failure this guards against. An absent key is read as version 0 and
    verified before being trusted; see :func:`_verify_pre_migration_checkpoint`.
    """
    path = _state_path(base, run_id)
    if not await asyncio.to_thread(path.is_file):
        return None
    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    raw = json.loads(text)
    state = ChainState.model_validate(raw)
    if "schema_version" not in raw:
        await _verify_pre_migration_checkpoint(state, base)
    return state


async def _verify_pre_migration_checkpoint(state: ChainState, base: Path) -> None:
    """Verify a schema-version-0 (pre-057) checkpoint before resume trusts
    it (FR-043).

    Rule: resume either succeeds correctly or fails with an explicit,
    actionable message — never silently. Accepted only when every
    ``landed`` step's claimed artifacts still verify on disk; a
    pre-migration checkpoint's other fields (e.g. ``workspace_path``, a
    hidden-workspace path the new primitive doesn't necessarily reuse
    the same way) are not otherwise re-validated here, so this is the one
    signal available to decide whether the rest of the checkpoint is
    trustworthy.

    Raises:
        WorkflowError: A landed step's artifacts no longer verify.
    """
    if state.feature_dir is None:
        return  # nothing landed yet -- nothing to verify
    feature_dir_name = Path(state.feature_dir).name
    feature_path = base / "specs" / feature_dir_name

    def _find_missing() -> list[tuple[str, list[str]]]:
        problems: list[tuple[str, list[str]]] = []
        for step, record in state.steps.items():
            if record.status != "succeeded" or not record.landed:
                continue
            missing = [a for a in record.artifacts if not (feature_path / a).is_file()]
            if missing:
                problems.append((step.value, missing))
        return problems

    problems = await asyncio.to_thread(_find_missing)
    if problems:
        from maverick.exceptions import WorkflowError

        detail = "; ".join(f"{step}: missing {missing}" for step, missing in problems)
        raise WorkflowError(
            f"checkpoint for run {state.run_id!r} (feature {state.feature!r}) predates "
            f"057-isolated-bead-workspaces and its landed artifacts no longer verify on "
            f"disk ({detail}). Re-run 'maverick spec {state.feature} --from-prd <file>' "
            "to start fresh.",
            workflow_name="spec-chain",
        )


async def discover_resumable(feature: str, base: Path) -> ChainState | None:
    """Scan ``.maverick/runs/*/spec-chain.json`` for the newest resumable
    state matching *feature* (contracts/chain-state.md "Resume resolution").

    Returns the state with the newest ``updated_at`` among those with
    ``feature == feature`` and ``status in {"halted", "running"}``.
    Corrupt or unparseable sibling state files are skipped, not fatal.
    """
    candidates = [
        state
        for state in await _load_all_states(base)
        if state.feature == feature and state.status in _RESUMABLE_STATUSES
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.updated_at)


async def resumable_features(base: Path) -> set[str]:
    """Every feature under *base* with a halted or still-running chain.

    The complement of this set is safe to collect: a completed chain's hidden
    workspace cannot be resumed at all (re-running the feature hits the CLI's
    spec-dir collision check), so nothing durable is lost by removing it.
    Shares :func:`_load_all_states` with :func:`discover_resumable` so the two
    can never disagree about what "resumable" means — they gate the same
    decision from opposite directions.
    """
    return {
        state.feature
        for state in await _load_all_states(base)
        if state.status in _RESUMABLE_STATUSES
    }


async def _load_all_states(base: Path) -> list[ChainState]:
    """Parse every readable ``.maverick/runs/*/spec-chain.json`` under *base*.

    Corrupt or unparseable siblings are skipped, not fatal — one bad file
    must not hide every other run's state.
    """
    runs_dir = base / _RUNS_SUBDIR
    if not await asyncio.to_thread(runs_dir.is_dir):
        return []

    run_dirs = await asyncio.to_thread(lambda: list(runs_dir.iterdir()))
    states: list[ChainState] = []
    for run_dir in run_dirs:
        state_path = run_dir / _STATE_FILENAME
        if not await asyncio.to_thread(state_path.is_file):
            continue
        try:
            text = await asyncio.to_thread(state_path.read_text, encoding="utf-8")
            raw = json.loads(text)
            state = ChainState.model_validate(raw)
            if "schema_version" not in raw:
                await _verify_pre_migration_checkpoint(state, base)
            states.append(state)
        except Exception as exc:
            # A pre-migration checkpoint that fails verification lands
            # here too (WorkflowError is an Exception) -- unlike
            # load_chain_state's direct-by-run-id lookup, discovery
            # degrades an unverifiable checkpoint to "not a candidate"
            # rather than raising, matching every other corrupt-sibling
            # case this function already tolerates.
            logger.debug("spec_chain_state_unreadable", path=str(state_path), error=str(exc))
            continue
    return states
