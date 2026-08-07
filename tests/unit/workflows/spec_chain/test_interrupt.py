"""Unit tests for graceful-interrupt handling (US3, T029).

A graceful SIGINT during a step cancels `SpecChainWorkflow._run()`;
`PythonWorkflow._run_with_cleanup`'s CancelledError handling runs the
workflow's registered rollbacks, which flip the freshest on-disk
checkpoint's status to ``halted`` (never re-deriving from a possibly
stale in-memory snapshot). A hard crash never reaches that rollback and
leaves ``status="running"`` — which `discover_resumable` still treats as
stale-resumable (contracts/chain-state.md).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from maverick.config import AgentBindingConfig, AgentsConfig, MaverickConfig
from maverick.workflows.spec_chain.constants import ChainStep
from maverick.workflows.spec_chain.state import discover_resumable, load_chain_state
from maverick.workflows.spec_chain.workflow import SpecChainWorkflow
from tests.integration.spec_chain.conftest import FEATURE, build_speckit_repo


class _HangingSession:
    """A session whose ``execute()`` never returns until cancelled — the
    same hang :class:`_HangingRuntime` provides on its own legacy
    ``execute()``, but via the session path every squadron now routes
    through (056-context-file-protection builds a real
    ``ProtectionPolicy`` at squadron-open, so ``Agent.open()`` always
    opens a session)."""

    def __init__(self, entered: asyncio.Event) -> None:
        self.id = "hanging-session"
        self._entered = entered

    async def execute(self, prompt: str, **kwargs: Any) -> Any:
        self._entered.set()
        await asyncio.sleep(999)

    async def close(self) -> None:
        return None


class _HangingRuntime:
    """Never returns from `execute()` until cancelled — lets the test
    control exactly when mid-step cancellation happens."""

    label = "stub"

    def __init__(self, *, model: str | None = None, **kwargs: Any) -> None:
        self.model = model
        self.entered = asyncio.Event()

    async def execute(self, prompt: str, **kwargs: Any) -> Any:
        self.entered.set()
        await asyncio.sleep(999)

    async def reset(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def validate_binding(self, _binding: Any) -> bool:
        return True

    def supports(self, feature: Any, model: Any = None) -> bool:
        return False

    def session(self, **kwargs: Any) -> _HangingSession:
        return _HangingSession(self.entered)


def _make_config() -> MaverickConfig:
    return MaverickConfig(
        agents=AgentsConfig(generate=AgentBindingConfig(provider="claude", model_id="stub-model"))
    )


async def _drive_and_cancel_mid_step(
    speckit_repo: Path, fake_home: Path, monkeypatch: pytest.MonkeyPatch, run_id: str
) -> tuple[SpecChainWorkflow, str]:
    """Start the chain, wait for the first step to actually enter its
    (hanging) runtime call, then cancel — mirroring how a graceful SIGINT
    cancels the workflow's own background task in production
    (`PythonWorkflow._run_with_cleanup`)."""
    constructed: list[_HangingRuntime] = []

    def _factory(provider_id: str) -> type[_HangingRuntime]:
        class _Bound(_HangingRuntime):
            def __init__(self, *, model: str | None = None, **kwargs: Any) -> None:
                super().__init__(model=model, **kwargs)
                constructed.append(self)

        return _Bound

    monkeypatch.setattr("airframe.runtime_for", _factory)

    workflow = SpecChainWorkflow(config=_make_config())
    inputs = {
        "run_id": run_id,
        "feature": FEATURE,
        "cwd": str(speckit_repo),
        "prd_path": str(speckit_repo / "docs" / "prd.md"),
        "home": str(fake_home),
    }

    # Mirror PythonWorkflow.execute()'s own setup so this test has direct
    # access to the background task PythonWorkflow._run_with_cleanup runs
    # as `run_task` internally — the same object graceful shutdown cancels.
    workflow._event_queue = asyncio.Queue()
    workflow._step_results = []
    workflow._step_start_times = {}
    workflow._current_step = None
    workflow._rollback_stack = []
    workflow.result = None

    run_task = asyncio.create_task(workflow._run_with_cleanup(inputs))

    # Wait until the hanging runtime is actually inside execute() — i.e.
    # we're mid-step, not still in workspace prep.
    for _ in range(200):
        if constructed and constructed[0].entered.is_set():
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("runtime never entered execute() — test setup broken")

    run_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run_task

    return workflow, run_id


class TestGracefulInterruptCheckspointsHalted:
    async def test_status_flipped_to_halted_on_cancel(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        speckit_repo = build_speckit_repo(tmp_path)
        fake_home = tmp_path / "fake-home"
        fake_home.mkdir()

        _workflow, run_id = await _drive_and_cancel_mid_step(
            speckit_repo, fake_home, monkeypatch, "interrupt-halted"
        )

        state = await load_chain_state(run_id, speckit_repo)
        assert state is not None
        assert state.status == "halted"

    async def test_specify_step_left_in_progress_not_falsely_succeeded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        speckit_repo = build_speckit_repo(tmp_path)
        fake_home = tmp_path / "fake-home"
        fake_home.mkdir()

        _workflow, run_id = await _drive_and_cancel_mid_step(
            speckit_repo, fake_home, monkeypatch, "interrupt-in-progress"
        )

        state = await load_chain_state(run_id, speckit_repo)
        assert state is not None
        assert state.steps[ChainStep.SPECIFY].status == "in_progress"

    async def test_workspace_preserved_for_resume(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        speckit_repo = build_speckit_repo(tmp_path)
        fake_home = tmp_path / "fake-home"
        fake_home.mkdir()

        _workflow, run_id = await _drive_and_cancel_mid_step(
            speckit_repo, fake_home, monkeypatch, "interrupt-workspace"
        )

        state = await load_chain_state(run_id, speckit_repo)
        assert state is not None
        assert Path(state.workspace_path).is_dir()

    async def test_halted_state_is_discoverable_as_resumable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        speckit_repo = build_speckit_repo(tmp_path)
        fake_home = tmp_path / "fake-home"
        fake_home.mkdir()

        await _drive_and_cancel_mid_step(
            speckit_repo, fake_home, monkeypatch, "interrupt-resumable"
        )

        resumable = await discover_resumable(FEATURE, speckit_repo)
        assert resumable is not None
        assert resumable.run_id == "interrupt-resumable"
        assert resumable.status == "halted"


class TestHardCrashLeavesRunningStatus:
    async def test_state_saved_before_cancellation_hook_runs_still_shows_running(
        self, tmp_path: Path
    ) -> None:
        """A hard crash (kill -9, power loss) never gets a chance to run
        any rollback — simulated here by checkpointing "in_progress" the
        same way `_run_one_step` does, then asserting on that raw
        checkpoint without ever invoking the cancellation/rollback path.
        `discover_resumable` still treats `status="running"` as
        stale-resumable (contracts/chain-state.md), which the resume
        integration tests already verify end-to-end."""
        from datetime import UTC, datetime

        from maverick.workflows.spec_chain.models import ChainState, StepRecord
        from maverick.workflows.spec_chain.state import save_chain_state

        now = datetime.now(tz=UTC)
        state = ChainState(
            run_id="hard-crash",
            feature=FEATURE,
            feature_dir=None,
            prd_path="docs/prd.md",
            prd_digest="0" * 64,
            workspace_path=str(tmp_path / "workspace"),
            status="running",
            steps={
                ChainStep.SPECIFY: StepRecord(
                    step=ChainStep.SPECIFY, status="in_progress", started_at=now
                )
            },
            clarify_decisions=[],
            remediation_bead_ids=[],
            started_at=now,
            updated_at=now,
        )
        await save_chain_state(state, tmp_path)

        loaded = await load_chain_state("hard-crash", tmp_path)
        assert loaded is not None
        assert loaded.status == "running"

        resumable = await discover_resumable(FEATURE, tmp_path)
        assert resumable is not None
        assert resumable.status == "running"
