"""Integration tests for the per-step retry predicate.

The step-run retry loop only retries airframe ``RuntimeTransientError``.
Deterministic failures (auth, model-not-found, context-overflow, budget)
must fail fast — retrying just burns model calls and backoff before the
same failure halts the step. Observed via the stub runtime's
``execute_calls`` count: a transient error is attempted the full
``_STEP_RETRY_ATTEMPTS`` times; a non-transient error is attempted once.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from airframe.errors import RuntimeModelNotFoundError, RuntimeTransientError

from maverick.workflows.spec_chain.constants import ChainStep
from maverick.workflows.spec_chain.state import load_chain_state
from maverick.workflows.spec_chain.workflow import (
    _STEP_RETRY_ATTEMPTS,
    SpecChainWorkflow,
)
from tests.integration.spec_chain.conftest import (
    FEATURE,
    make_config,
    stub_runtime_factory,
)


async def _run_once(speckit_repo: Path, fake_home: Path, *, run_id: str) -> None:
    workflow = SpecChainWorkflow(config=make_config())
    inputs = {
        "run_id": run_id,
        "feature": FEATURE,
        "cwd": str(speckit_repo),
        "prd_path": str(speckit_repo / "docs" / "prd.md"),
        "home": str(fake_home),
    }
    async for _ in workflow.execute(inputs):
        pass


def _raise_transient(_feature_path: Path, _runtime: Any) -> dict[str, Any]:
    raise RuntimeTransientError("temporary blip")


def _raise_model_not_found(_feature_path: Path, _runtime: Any) -> dict[str, Any]:
    raise RuntimeModelNotFoundError("no such model")


class TestRetryPredicate:
    async def test_transient_error_is_retried_full_attempts(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        runtimes = stub_runtime_factory(
            monkeypatch, step_handlers={ChainStep.SPECIFY: _raise_transient}
        )
        await _run_once(speckit_repo, fake_home, run_id="retry-transient")

        # specify raised a transient error on every attempt -> retried the
        # full budget before halting.
        assert len(runtimes[0].execute_calls) == _STEP_RETRY_ATTEMPTS

        state = await load_chain_state("retry-transient", speckit_repo)
        assert state is not None
        assert state.status == "halted"
        assert state.steps[ChainStep.SPECIFY].status == "failed"

    async def test_non_transient_error_fails_fast(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        runtimes = stub_runtime_factory(
            monkeypatch, step_handlers={ChainStep.SPECIFY: _raise_model_not_found}
        )
        await _run_once(speckit_repo, fake_home, run_id="retry-model-not-found")

        # A deterministic model-not-found error is not retried at all.
        assert len(runtimes[0].execute_calls) == 1

        state = await load_chain_state("retry-model-not-found", speckit_repo)
        assert state is not None
        assert state.status == "halted"
        assert state.steps[ChainStep.SPECIFY].status == "failed"
