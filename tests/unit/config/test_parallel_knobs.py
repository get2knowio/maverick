"""Tests for the ``parallel.*`` concurrency knobs in MaverickConfig.

The pre-existing ``max_agents`` / ``max_tasks`` are still advisory (no
runtime enforcement yet — see docstring). The three knobs added in this
commit (``decomposer_pool_size``, ``max_briefing_agents``,
``max_parallel_reviewers``) ARE wired:

* ``decomposer_pool_size`` flows through the refuel workflow into
  ``RefuelInputs.decomposer_pool_size``.
* ``max_briefing_agents`` flows through both the refuel and plan
  workflows into the supervisor inputs and bounds an
  ``asyncio.Semaphore`` around the briefing fan-out.
* ``max_parallel_reviewers`` is read by ``_run_dual_review`` directly
  from ``load_config()`` and bounds the reviewer fan-out.

These tests lock in the defaults + bounds at the model level so a
regression in the ``ParallelConfig`` schema is caught immediately. The
end-to-end wiring is exercised by the supervisor / workflow tests.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maverick.config import ParallelConfig


def test_defaults_match_legacy_behaviour() -> None:
    """Defaults must not change behaviour for existing maverick.yaml files."""
    p = ParallelConfig()
    assert p.max_agents == 3
    assert p.max_tasks == 5
    # Legacy hardcoded DECOMPOSER_POOL_SIZE was 4 = 1 primary + 3 pool workers.
    assert p.decomposer_pool_size == 3
    # Legacy briefing room was navigator/structuralist/recon in parallel.
    assert p.max_briefing_agents == 3
    # Legacy review fan-out was completeness + correctness in parallel.
    assert p.max_parallel_reviewers == 2


@pytest.mark.parametrize(
    "value",
    [-1, 11],
    ids=["below_zero", "above_max"],
)
def test_decomposer_pool_size_rejects_out_of_range(value: int) -> None:
    with pytest.raises(ValidationError):
        ParallelConfig(decomposer_pool_size=value)


def test_decomposer_pool_size_zero_allowed() -> None:
    """Zero pool workers = primary-only decomposer (single ACP subprocess)."""
    p = ParallelConfig(decomposer_pool_size=0)
    assert p.decomposer_pool_size == 0


@pytest.mark.parametrize(
    "value",
    [0, -1, 11],
    ids=["zero", "below_zero", "above_max"],
)
def test_max_briefing_agents_rejects_out_of_range(value: int) -> None:
    """At least 1 briefing must be allowed; cap at 10."""
    with pytest.raises(ValidationError):
        ParallelConfig(max_briefing_agents=value)


def test_max_briefing_agents_one_runs_briefings_sequentially() -> None:
    """Setting 1 is the recipe for sequential briefings on small hosts."""
    p = ParallelConfig(max_briefing_agents=1)
    assert p.max_briefing_agents == 1


@pytest.mark.parametrize(
    "value",
    [0, -1, 5],
    ids=["zero", "below_zero", "above_max"],
)
def test_max_parallel_reviewers_rejects_out_of_range(value: int) -> None:
    """Reviewer cap is 1..4 (only two reviewer types exist today)."""
    with pytest.raises(ValidationError):
        ParallelConfig(max_parallel_reviewers=value)


def test_max_parallel_reviewers_one_runs_sequentially() -> None:
    p = ParallelConfig(max_parallel_reviewers=1)
    assert p.max_parallel_reviewers == 1


def test_yaml_round_trip_preserves_new_knobs() -> None:
    """A YAML payload with the three new knobs round-trips correctly."""
    raw = {
        "max_agents": 2,
        "max_tasks": 4,
        "decomposer_pool_size": 1,
        "max_briefing_agents": 1,
        "max_parallel_reviewers": 1,
    }
    p = ParallelConfig(**raw)
    assert p.model_dump() == raw
