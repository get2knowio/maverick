"""Tests for :mod:`maverick.agents.context` ambient tagging."""

from __future__ import annotations

import asyncio

from maverick.agents.context import current_tags, tagged


def test_no_active_block_returns_empty() -> None:
    assert current_tags() == {}


def test_tagged_extends_active_tags() -> None:
    with tagged(bead_id="b-1"):
        assert current_tags() == {"bead_id": "b-1"}
        with tagged(complexity="simple"):
            assert current_tags() == {"bead_id": "b-1", "complexity": "simple"}
        # Inner block left the outer state intact.
        assert current_tags() == {"bead_id": "b-1"}
    assert current_tags() == {}


def test_inner_tag_overrides_outer() -> None:
    with tagged(bead_id="b-1"):
        with tagged(bead_id="b-2"):
            assert current_tags()["bead_id"] == "b-2"
        # Outer value restored.
        assert current_tags()["bead_id"] == "b-1"


def test_tags_reset_on_exception() -> None:
    try:
        with tagged(bead_id="b-1"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert current_tags() == {}


async def test_concurrent_tasks_see_independent_tags() -> None:
    """Each ``asyncio.gather`` branch gets its own tag view.

    The whole point of using ``contextvars`` over a mutable instance
    attribute. Two concurrent tasks each set their own ``bead_id``
    and the snapshots taken inside each must not bleed.
    """
    seen: dict[str, str] = {}

    async def branch(bead_id: str) -> None:
        with tagged(bead_id=bead_id):
            # Yield so the other branch runs and we can prove no bleed.
            await asyncio.sleep(0)
            seen[bead_id] = current_tags()["bead_id"]

    await asyncio.gather(branch("b-1"), branch("b-2"), branch("b-3"))
    assert seen == {"b-1": "b-1", "b-2": "b-2", "b-3": "b-3"}


def test_current_tags_returns_copy() -> None:
    """Mutating the returned dict doesn't affect the live context."""
    with tagged(bead_id="b-1"):
        snapshot = current_tags()
        snapshot["bead_id"] = "tampered"
        assert current_tags() == {"bead_id": "b-1"}
