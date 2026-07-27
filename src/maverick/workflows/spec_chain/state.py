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
    """Load a persisted chain state by run id. ``None`` if not found."""
    path = _state_path(base, run_id)
    if not await asyncio.to_thread(path.is_file):
        return None
    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    return ChainState.model_validate(json.loads(text))


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
            states.append(ChainState.model_validate(json.loads(text)))
        except Exception as exc:
            logger.debug("spec_chain_state_unreadable", path=str(state_path), error=str(exc))
            continue
    return states
