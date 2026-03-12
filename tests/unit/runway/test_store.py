"""Tests for RunwayStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.exceptions.runway import RunwayCorruptedError, RunwayNotInitializedError
from maverick.runway.models import (
    BeadOutcome,
    FixAttemptRecord,
    RunwayReviewFinding,
)
from maverick.runway.store import RunwayStore


class TestStoreInitialization:
    """Tests for store initialization."""

    async def test_initialize_creates_structure(self, runway_path: Path) -> None:
        store = RunwayStore(runway_path)
        assert not store.is_initialized
        await store.initialize()
        assert store.is_initialized
        assert (runway_path / "episodic").is_dir()
        assert (runway_path / "semantic").is_dir()
        assert (runway_path / "index.json").is_file()

    async def test_initialize_idempotent(self, initialized_store: RunwayStore) -> None:
        # Second init should not fail or overwrite
        await initialized_store.initialize()
        assert initialized_store.is_initialized

    async def test_is_initialized_false_for_missing(self, tmp_path: Path) -> None:
        store = RunwayStore(tmp_path / "nonexistent")
        assert not store.is_initialized


class TestBeadOutcomeAppendAndRead:
    """Tests for bead outcome JSONL operations."""

    async def test_append_and_read(
        self,
        initialized_store: RunwayStore,
        sample_bead_outcome: BeadOutcome,
    ) -> None:
        await initialized_store.append_bead_outcome(sample_bead_outcome)
        outcomes = await initialized_store.get_bead_outcomes()
        assert len(outcomes) == 1
        assert outcomes[0].bead_id == "bead-001"

    async def test_filter_by_bead_id(self, initialized_store: RunwayStore) -> None:
        await initialized_store.append_bead_outcome(
            BeadOutcome(bead_id="b1", epic_id="e1")
        )
        await initialized_store.append_bead_outcome(
            BeadOutcome(bead_id="b2", epic_id="e1")
        )
        results = await initialized_store.get_bead_outcomes(bead_id="b1")
        assert len(results) == 1
        assert results[0].bead_id == "b1"

    async def test_filter_by_epic_id(self, initialized_store: RunwayStore) -> None:
        await initialized_store.append_bead_outcome(
            BeadOutcome(bead_id="b1", epic_id="e1")
        )
        await initialized_store.append_bead_outcome(
            BeadOutcome(bead_id="b2", epic_id="e2")
        )
        results = await initialized_store.get_bead_outcomes(epic_id="e2")
        assert len(results) == 1
        assert results[0].epic_id == "e2"

    async def test_limit(self, initialized_store: RunwayStore) -> None:
        for i in range(5):
            await initialized_store.append_bead_outcome(
                BeadOutcome(bead_id=f"b{i}", epic_id="e1")
            )
        results = await initialized_store.get_bead_outcomes(limit=2)
        assert len(results) == 2
        # Should return last 2
        assert results[0].bead_id == "b3"
        assert results[1].bead_id == "b4"


class TestReviewFindingAppendAndRead:
    """Tests for review finding JSONL operations."""

    async def test_append_and_read(
        self,
        initialized_store: RunwayStore,
        sample_review_finding: RunwayReviewFinding,
    ) -> None:
        await initialized_store.append_review_finding(sample_review_finding)
        findings = await initialized_store.get_review_findings()
        assert len(findings) == 1
        assert findings[0].finding_id == "F001"

    async def test_filter_by_file_path(self, initialized_store: RunwayStore) -> None:
        await initialized_store.append_review_finding(
            RunwayReviewFinding(finding_id="F1", bead_id="b1", file_path="src/a.py")
        )
        await initialized_store.append_review_finding(
            RunwayReviewFinding(finding_id="F2", bead_id="b1", file_path="src/b.py")
        )
        results = await initialized_store.get_review_findings(file_path="src/a.py")
        assert len(results) == 1


class TestFixAttemptAppendAndRead:
    """Tests for fix attempt JSONL operations."""

    async def test_append_and_read(
        self,
        initialized_store: RunwayStore,
        sample_fix_attempt: FixAttemptRecord,
    ) -> None:
        await initialized_store.append_fix_attempt(sample_fix_attempt)
        attempts = await initialized_store.get_fix_attempts()
        assert len(attempts) == 1
        assert attempts[0].attempt_id == "att-001"

    async def test_filter_by_finding_id(self, initialized_store: RunwayStore) -> None:
        await initialized_store.append_fix_attempt(
            FixAttemptRecord(attempt_id="a1", finding_id="F1", bead_id="b1")
        )
        await initialized_store.append_fix_attempt(
            FixAttemptRecord(attempt_id="a2", finding_id="F2", bead_id="b1")
        )
        results = await initialized_store.get_fix_attempts(finding_id="F1")
        assert len(results) == 1


class TestSemanticFiles:
    """Tests for semantic file operations."""

    async def test_read_nonexistent_returns_none(
        self, initialized_store: RunwayStore
    ) -> None:
        result = await initialized_store.read_semantic_file("missing.md")
        assert result is None

    async def test_write_and_read(self, initialized_store: RunwayStore) -> None:
        await initialized_store.write_semantic_file(
            "architecture.md", "# Architecture\n\nEvent sourcing pattern."
        )
        content = await initialized_store.read_semantic_file("architecture.md")
        assert content is not None
        assert "Event sourcing" in content


class TestIndex:
    """Tests for index operations."""

    async def test_read_default_index(self, initialized_store: RunwayStore) -> None:
        index = await initialized_store.read_index()
        assert index.version == 1

    async def test_write_and_read_index(self, initialized_store: RunwayStore) -> None:
        from maverick.runway.models import RunwayIndex

        new_index = RunwayIndex(
            version=1,
            last_consolidated="2025-01-01",
            entities=["FooService"],
        )
        await initialized_store.write_index(new_index)
        read_back = await initialized_store.read_index()
        assert read_back.last_consolidated == "2025-01-01"
        assert read_back.entities == ["FooService"]

    async def test_read_index_not_initialized(self, tmp_path: Path) -> None:
        store = RunwayStore(tmp_path / "missing")
        with pytest.raises(RunwayNotInitializedError):
            await store.read_index()

    async def test_read_corrupted_index(self, initialized_store: RunwayStore) -> None:
        index_path = initialized_store.path / "index.json"
        index_path.write_text("not json")
        with pytest.raises(RunwayCorruptedError):
            await initialized_store.read_index()


class TestBM25Query:
    """Tests for BM25 query functionality."""

    async def test_query_empty_store(self, initialized_store: RunwayStore) -> None:
        result = await initialized_store.query("test query")
        assert result.passages == []
        assert result.total_candidates == 0

    async def test_query_semantic_content(self, initialized_store: RunwayStore) -> None:
        await initialized_store.write_semantic_file(
            "architecture.md",
            "# Architecture\n\nThe system uses event sourcing for persistence.\n\n"
            "All commands are validated before processing.",
        )
        result = await initialized_store.query("event sourcing")
        assert len(result.passages) > 0
        assert any("event sourcing" in p.content.lower() for p in result.passages)

    async def test_query_episodic_content(self, initialized_store: RunwayStore) -> None:
        await initialized_store.append_bead_outcome(
            BeadOutcome(
                bead_id="b1",
                epic_id="e1",
                title="Implement payment processing",
                key_decisions=["Used stripe for payment processing"],
            )
        )
        # BM25 searches across the raw JSON text; "payment" appears in title
        result = await initialized_store.query("payment")
        assert len(result.passages) > 0
        assert result.total_candidates > 0

    async def test_query_empty_query(self, initialized_store: RunwayStore) -> None:
        await initialized_store.write_semantic_file("test.md", "Some content")
        result = await initialized_store.query("")
        assert result.passages == []

    async def test_query_max_passages(self, initialized_store: RunwayStore) -> None:
        # Write many paragraphs
        paragraphs = "\n\n".join(
            f"Section {i}: the topic is testing." for i in range(20)
        )
        await initialized_store.write_semantic_file("big.md", paragraphs)
        result = await initialized_store.query("testing", max_passages=3)
        assert len(result.passages) <= 3


class TestStatus:
    """Tests for store status."""

    async def test_status_uninitialized(self, tmp_path: Path) -> None:
        store = RunwayStore(tmp_path / "missing")
        status = await store.get_status()
        assert status.initialized is False

    async def test_status_initialized(self, initialized_store: RunwayStore) -> None:
        status = await initialized_store.get_status()
        assert status.initialized is True
        assert status.bead_outcome_count == 0

    async def test_status_with_data(
        self,
        initialized_store: RunwayStore,
        sample_bead_outcome: BeadOutcome,
    ) -> None:
        await initialized_store.append_bead_outcome(sample_bead_outcome)
        status = await initialized_store.get_status()
        assert status.bead_outcome_count == 1
