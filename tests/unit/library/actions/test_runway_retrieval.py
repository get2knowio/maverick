"""Unit tests for retrieve_runway_context action."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.library.actions.runway import retrieve_runway_context
from maverick.runway.models import BeadOutcome
from maverick.runway.store import RunwayStore


@pytest.fixture
async def initialized_runway(tmp_path: Path) -> Path:
    """Create an initialized runway store directory."""
    runway_path = tmp_path / ".maverick" / "runway"
    store = RunwayStore(runway_path)
    await store.initialize()
    return tmp_path


class TestRetrieveRunwayContext:
    async def test_returns_empty_when_not_initialized(self, tmp_path: Path) -> None:
        """No runway dir → success=True, context_text=''."""
        result = await retrieve_runway_context(
            title="Add auth",
            description="Implement auth module",
            epic_id="e1",
            cwd=tmp_path,
        )
        assert result.success is True
        assert result.context_text == ""
        assert result.outcomes_used == 0
        assert result.passages_used == 0
        assert result.error is None

    async def test_returns_empty_when_no_data(self, initialized_runway: Path) -> None:
        """Initialized but empty → empty context."""
        result = await retrieve_runway_context(
            title="Add auth",
            description="Implement auth module",
            epic_id="e1",
            cwd=initialized_runway,
        )
        assert result.success is True
        assert result.context_text == ""

    async def test_returns_structured_outcomes(self, initialized_runway: Path) -> None:
        """Outcomes from same epic appear in context_text."""
        runway_path = initialized_runway / ".maverick" / "runway"
        store = RunwayStore(runway_path)

        for i in range(3):
            await store.append_bead_outcome(
                BeadOutcome(
                    bead_id=f"b{i}",
                    epic_id="e1",
                    title=f"Bead {i}",
                    validation_passed=True,
                    review_findings_count=2,
                    review_fixed_count=2,
                    key_decisions=["Used JWT"],
                    mistakes_caught=["Missing error handling"],
                )
            )

        result = await retrieve_runway_context(
            title="Add auth",
            description="Implement auth module",
            epic_id="e1",
            cwd=initialized_runway,
        )

        assert result.success is True
        assert result.outcomes_used == 3
        assert "Recent Outcomes" in result.context_text
        assert "b0" in result.context_text
        assert "Used JWT" in result.context_text
        assert "Missing error handling" in result.context_text

    async def test_returns_bm25_passages(self, initialized_runway: Path) -> None:
        """Semantic passages appear in context_text."""
        runway_path = initialized_runway / ".maverick" / "runway"
        store = RunwayStore(runway_path)

        # Add a semantic file and an outcome to give BM25 something to match
        await store.write_semantic_file(
            "architecture.md",
            "# Architecture\n\nThe authentication module uses JWT tokens.\n",
        )
        await store.append_bead_outcome(
            BeadOutcome(
                bead_id="b1",
                epic_id="e1",
                title="Setup JWT auth",
                validation_passed=True,
            )
        )

        result = await retrieve_runway_context(
            title="JWT auth module",
            description="Implement JWT authentication",
            epic_id="e1",
            cwd=initialized_runway,
        )

        assert result.success is True
        assert result.passages_used > 0
        assert "Relevant Past Context" in result.context_text

    async def test_respects_max_context_chars(self, initialized_runway: Path) -> None:
        """Large data → truncated to max_context_chars."""
        runway_path = initialized_runway / ".maverick" / "runway"
        store = RunwayStore(runway_path)

        # Add many outcomes to generate a lot of text
        for i in range(50):
            await store.append_bead_outcome(
                BeadOutcome(
                    bead_id=f"b{i}",
                    epic_id="e1",
                    title=f"Very long bead title number {i} with lots of text",
                    validation_passed=True,
                    key_decisions=[f"Decision {j} for bead {i}" for j in range(5)],
                    mistakes_caught=[f"Mistake {j} for bead {i}" for j in range(5)],
                )
            )

        result = await retrieve_runway_context(
            title="Test bead",
            description="Test",
            epic_id="e1",
            max_context_chars=500,
            cwd=initialized_runway,
        )

        assert result.success is True
        assert len(result.context_text) <= 500

    async def test_filters_by_epic_id(self, initialized_runway: Path) -> None:
        """Only matching epic outcomes shown in structured section."""
        runway_path = initialized_runway / ".maverick" / "runway"
        store = RunwayStore(runway_path)

        await store.append_bead_outcome(BeadOutcome(bead_id="b1", epic_id="e1", title="Same epic"))
        await store.append_bead_outcome(
            BeadOutcome(bead_id="b2", epic_id="e2", title="Different epic")
        )

        result = await retrieve_runway_context(
            title="Test",
            description="Test",
            epic_id="e1",
            cwd=initialized_runway,
        )

        assert result.outcomes_used == 1
        assert "Same epic" in result.context_text
        # b2 may appear in BM25 passages but not in structured outcomes
        # The structured section should only show e1

    async def test_best_effort_on_exception(self, tmp_path: Path) -> None:
        """Store exception → graceful empty return."""
        # Create a corrupted runway directory
        runway_path = tmp_path / ".maverick" / "runway"
        runway_path.mkdir(parents=True)
        (runway_path / "episodic").mkdir()
        (runway_path / "semantic").mkdir()
        # Write invalid JSON to index.json
        (runway_path / "index.json").write_text("{invalid json")
        # Write invalid JSONL to bead outcomes
        (runway_path / "episodic" / "bead-outcomes.jsonl").write_text("{invalid\n")

        result = await retrieve_runway_context(
            title="Test",
            description="Test",
            epic_id="e1",
            cwd=tmp_path,
        )

        # Should return without raising
        assert result.success is True
        assert result.context_text == ""
