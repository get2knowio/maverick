"""T064 — beads remain strictly serial under isolated mode (contract G3,
FR-015, FR-031).

Contract ``fly-isolated-mode.md`` states G3 as: "Beads remain strictly
serial; no unit begins while another's delta is unverified in the
checkout." The production code path that carries this guarantee is a
single ``await``-driven Burr loop (no ``asyncio.gather``/concurrent bead
processing — confirmed by reading ``workflow.py``'s ``_run_bead_loop`` and
``burr_graph.py``'s transition table), so the strongest thing this test can
genuinely exercise is *ordering*, not literal thread-safety: it drives a
real isolated run over several independent beads and asserts, from two
independent angles, that the production code never lets two beads'
workspace lifecycles overlap.

1. **At most one live workspace at a time.** ``_isolation.py``'s
   ``provision_workspace``/``teardown_workspace`` call the module-level
   ``register_live_workspace``/``unregister_live_workspace`` free functions
   (``src/maverick/workspace/session.py``) that back ``assert_checkout``'s
   process-global registry (contract C6). This test monkeypatches those two
   names — at the point ``_isolation.py`` actually looks them up, i.e.
   ``maverick.workflows.fly_beads._isolation.register_live_workspace``/
   ``unregister_live_workspace`` (imported there as bare names via
   ``from maverick.workspace import (...)``, so patching the module
   attribute is what actually intercepts the call) — with instrumented
   wrappers that track the live set and assert no *second, different*
   workspace root is ever registered while one is already live.

2. **No bead's ``provision_workspace`` runs before the prior bead's
   ``fold_back`` + ``commit`` have both completed.** ``fold_back`` (in
   ``_isolation.py``) and ``commit`` (in ``actions.py``) are wrapped the
   same way — both modules import the target functions as plain
   ``@action``-decorated module attributes (``fly_isolation.provision_workspace
   .bind(...)``, ``fly_actions.commit.bind(...)`` in ``burr_graph.py``,
   resolved at ``build_fly_application`` call time) — so patching the
   module attribute before the run intercepts the exact callable the graph
   binds. Each wrapper appends an ``(event, bead_id)`` tuple to one shared,
   ordered log. Grouping that log by consecutive bead id must yield exactly
   one contiguous run per bead, each run's event sequence exactly
   ``["provision", "fold_back", "commit"]`` — any interleaving (bead B's
   provision landing inside bead A's run) would break that grouping.

Uses a 4-bead fixture so there is enough sequence to meaningfully assert
ordering across multiple beads, not just a single before/after pair.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from burr.core import State, action

from maverick.workflows.fly_beads import _isolation as fly_isolation_module
from maverick.workflows.fly_beads import actions as fly_actions_module

if TYPE_CHECKING:
    from maverick.events import ProgressEvent
    from maverick.squadron.fly import FlySquadron
    from maverick.workspace import IsolationPolicy, IsolationSession

from .conftest import (
    BD_UNAVAILABLE,
    JJ_UNAVAILABLE,
    BeadSpec,
    build_fly_repo,
    make_fly_config,
    run_fly_workflow,
    stub_fly_runtime_factory,
    working_copy_dirt,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

if BD_UNAVAILABLE or JJ_UNAVAILABLE:
    pytest.skip("bd/jj CLI not available on PATH", allow_module_level=True)

#: Four independent beads (no shared files) so bead processing has a
#: meaningful sequence to assert ordering across, priority-ordered so
#: selection order is deterministic (mirrors conftest's own
#: ``DEFAULT_BEAD_SPECS`` convention).
_FOUR_BEAD_SPECS = (
    BeadSpec(title="Add alpha module", description="Implement the alpha module.", priority=1),
    BeadSpec(title="Add beta module", description="Implement the beta module.", priority=2),
    BeadSpec(title="Add gamma module", description="Implement the gamma module.", priority=3),
    BeadSpec(title="Add delta module", description="Implement the delta module.", priority=4),
)

# Captured once, at import time, before any test monkeypatches the module
# attributes below — these are the real production callables the tracking
# wrappers delegate to.
_REAL_PROVISION_WORKSPACE = fly_isolation_module.provision_workspace
_REAL_FOLD_BACK = fly_isolation_module.fold_back
_REAL_COMMIT = fly_actions_module.commit


@dataclass
class LiveWorkspaceTracker:
    """Instrumented stand-in for the ``register_live_workspace``/
    ``unregister_live_workspace`` free functions (contract C6's seam).

    Tracks the running set of live workspace roots and asserts — at every
    single registration — that no *different* workspace root is already
    live (the direct proxy for "at most one workspace is live at a time").
    Also records a ``max_concurrent`` high-water mark for a final sanity
    assertion.
    """

    live: set[Path] = field(default_factory=set)
    max_concurrent: int = 0

    def register(self, path: Path) -> Path:
        resolved = path.resolve()
        overlapping = {p for p in self.live if p != resolved}
        assert not overlapping, (
            "workspace overlap detected — a second, different workspace was "
            f"registered as live while {sorted(str(p) for p in overlapping)} "
            f"was still live: {resolved}"
        )
        self.live.add(resolved)
        self.max_concurrent = max(self.max_concurrent, len(self.live))
        return resolved

    def unregister(self, path: Path) -> None:
        self.live.discard(Path(path).resolve())


def _make_tracking_actions(
    event_log: list[tuple[str, str]],
) -> tuple[object, object, object]:
    """Build tracking wrappers for ``provision_workspace``, ``fold_back``,
    and ``commit`` that append ``(event_kind, bead_id)`` to *event_log*
    around a call-through to the real production action, then return them
    for the caller to ``monkeypatch.setattr`` onto the modules
    ``burr_graph.py`` actually resolves at build time.

    Each wrapper is re-decorated with the exact ``reads``/``writes`` of the
    action it wraps (copied verbatim from ``_isolation.py``/``actions.py``)
    so Burr's own state-contract validation sees an identical shape to the
    real action.
    """

    @action(
        reads=["current_bead_id", "isolated"],
        writes=["workspace_path", "bead_aborted"],
    )
    async def tracking_provision_workspace(
        state: State,
        *,
        session: IsolationSession,
        policy: IsolationPolicy,
        checkout: Path,
        jj_client: Any,
        squadron: FlySquadron,
        events: asyncio.Queue[ProgressEvent | None],
    ) -> tuple[dict[str, Any], State]:
        event_log.append(("provision", state["current_bead_id"]))
        return await _REAL_PROVISION_WORKSPACE(  # type: ignore[no-any-return]
            state,
            session=session,
            policy=policy,
            checkout=checkout,
            jj_client=jj_client,
            squadron=squadron,
            events=events,
        )

    @action(
        reads=["current_bead_id", "workspace_path", "isolated"],
        writes=[
            "fold_back_result",
            "unverified_in_checkout",
            "bead_aborted",
            "gate_failure_summary",
        ],
    )
    async def tracking_fold_back(
        state: State,
        *,
        session: IsolationSession,
        checkout: Path,
        now: Any,
        events: asyncio.Queue[ProgressEvent | None],
        protection_policy: Any = None,
    ) -> tuple[dict[str, Any], State]:
        result = await _REAL_FOLD_BACK(  # type: ignore[no-any-return]
            state,
            session=session,
            checkout=checkout,
            now=now,
            events=events,
            protection_policy=protection_policy,
        )
        event_log.append(("fold_back", state["current_bead_id"]))
        return result

    @action(
        reads=[
            "current_bead",
            "current_bead_id",
            "approved",
            "needs_human_review",
            "review_rounds",
            "recorded_assumption_ids",
        ],
        writes=["commit_ok", "commit_change_id"],
    )
    async def tracking_commit(
        state: State,
        *,
        cwd: str,
        events: asyncio.Queue[ProgressEvent | None],
    ) -> tuple[dict[str, Any], State]:
        result = await _REAL_COMMIT(state, cwd=cwd, events=events)  # type: ignore[no-any-return]
        event_log.append(("commit", state["current_bead_id"]))
        return result

    return tracking_provision_workspace, tracking_fold_back, tracking_commit


def _group_by_bead(event_log: list[tuple[str, str]]) -> list[tuple[str, list[str]]]:
    """Group a flat, chronologically-ordered ``(event_kind, bead_id)`` log
    into contiguous ``(bead_id, [event_kind, ...])`` runs.

    If (and only if) beads are strictly serial, every bead's events form
    exactly one contiguous run in this log — a second, later run for a
    bead already seen would mean some other bead's events were interleaved
    in between, which is exactly the regression this test exists to catch.
    """
    groups: list[tuple[str, list[str]]] = []
    for kind, bead_id in event_log:
        if not groups or groups[-1][0] != bead_id:
            groups.append((bead_id, []))
        groups[-1][1].append(kind)
    return groups


@pytest.mark.usefixtures("patch_default_gate_commands")
async def test_beads_remain_strictly_serial_under_isolated_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = build_fly_repo(tmp_path / "repo", bead_specs=_FOUR_BEAD_SPECS)
    stub_fly_runtime_factory(monkeypatch)

    tracker = LiveWorkspaceTracker()
    monkeypatch.setattr(fly_isolation_module, "register_live_workspace", tracker.register)
    monkeypatch.setattr(fly_isolation_module, "unregister_live_workspace", tracker.unregister)

    event_log: list[tuple[str, str]] = []
    tracking_provision, tracking_fold_back, tracking_commit = _make_tracking_actions(event_log)
    monkeypatch.setattr(fly_isolation_module, "provision_workspace", tracking_provision)
    monkeypatch.setattr(fly_isolation_module, "fold_back", tracking_fold_back)
    monkeypatch.setattr(fly_actions_module, "commit", tracking_commit)

    config = make_fly_config(workspace_root=tmp_path / "workspaces")
    outcome = await run_fly_workflow(
        config=config,
        cwd=repo.path,
        epic_id=repo.epic_id,
        isolated=True,
        monkeypatch=monkeypatch,
    )

    # --- Sanity: the run actually completed successfully, so the ordering
    #     assertions below are exercising a genuine full run, not a
    #     truncated one that happens to satisfy them trivially. ------------
    assert outcome.success is True, outcome.final_output
    assert outcome.final_output is not None
    assert outcome.final_output["beads_succeeded"] == len(_FOUR_BEAD_SPECS)
    assert outcome.final_output["beads_failed"] == 0

    # --- Check 1: at most one workspace was ever live at a time. ----------
    assert tracker.max_concurrent == 1, (
        f"expected at most one concurrently-live workspace, saw a high-water "
        f"mark of {tracker.max_concurrent}"
    )
    assert tracker.live == set(), (
        f"every workspace should have been unregistered by run end; still live: {tracker.live}"
    )

    # --- Check 2: no bead's provision ran before the prior bead's
    #     fold_back + commit both completed — i.e. every bead's
    #     provision/fold_back/commit events form one contiguous run, with
    #     no other bead's events interleaved in between. ------------------
    groups = _group_by_bead(event_log)
    assert [bead_id for bead_id, _ in groups] == list(repo.task_ids), (
        f"beads were not processed as {len(repo.task_ids)} contiguous, "
        f"non-interleaved runs: {event_log}"
    )
    for bead_id, kinds in groups:
        assert kinds == ["provision", "fold_back", "commit"], (bead_id, kinds)

    # --- No leftover workspace-fold-back dirt in the checkout. ------------
    dirt = working_copy_dirt(repo.path)
    assert all(path.startswith(".beads/") for path in dirt), dirt
