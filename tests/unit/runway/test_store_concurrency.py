"""Tests for concurrent JSONL append safety."""

from __future__ import annotations

import asyncio

from maverick.runway.models import BeadOutcome
from maverick.runway.store import RunwayStore


class TestConcurrentAppends:
    """Verify concurrent coroutine appends don't lose records."""

    async def test_concurrent_bead_outcome_appends(
        self, initialized_store: RunwayStore
    ) -> None:
        """Multiple coroutines appending simultaneously should not lose data."""
        count = 20

        async def append_one(i: int) -> None:
            outcome = BeadOutcome(bead_id=f"b{i}", epic_id="e1")
            await initialized_store.append_bead_outcome(outcome)

        await asyncio.gather(*(append_one(i) for i in range(count)))

        outcomes = await initialized_store.get_bead_outcomes()
        assert len(outcomes) == count

    async def test_concurrent_mixed_appends(
        self, initialized_store: RunwayStore
    ) -> None:
        """Appends to different JSONL files concurrently."""
        from maverick.runway.models import FixAttemptRecord, RunwayReviewFinding

        tasks = []
        for i in range(10):
            tasks.append(
                initialized_store.append_bead_outcome(
                    BeadOutcome(bead_id=f"b{i}", epic_id="e1")
                )
            )
            tasks.append(
                initialized_store.append_review_finding(
                    RunwayReviewFinding(finding_id=f"F{i}", bead_id=f"b{i}")
                )
            )
            tasks.append(
                initialized_store.append_fix_attempt(
                    FixAttemptRecord(
                        attempt_id=f"a{i}",
                        finding_id=f"F{i}",
                        bead_id=f"b{i}",
                    )
                )
            )

        await asyncio.gather(*tasks)

        outcomes = await initialized_store.get_bead_outcomes()
        findings = await initialized_store.get_review_findings()
        attempts = await initialized_store.get_fix_attempts()

        assert len(outcomes) == 10
        assert len(findings) == 10
        assert len(attempts) == 10
