"""Tests for `maverick.library.actions.beads.create_remediation_beads` (R6)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDetails, BeadSummary
from maverick.library.actions.beads import create_remediation_beads
from maverick.workflows.spec_chain.constants import (
    KEY_FINDING_FINGERPRINT,
    KEY_REMEDIATION_SOURCE,
    KEY_SPECKIT_FEATURE,
    REMEDIATION_SOURCE_ANALYZE,
    SPEC_REMEDIATION_LABEL,
)
from maverick.workflows.spec_chain.models import AnalyzeFinding


def _finding(**overrides: object) -> AnalyzeFinding:
    defaults: dict[str, object] = {
        "title": "Ambiguous auth requirement",
        "category": "ambiguity",
        "severity_hint": "medium",
        "location": "spec.md#FR-003",
        "summary": "FR-003 doesn't specify token lifetime.",
        "feature_dir": "050-headless-spec-chain",
    }
    defaults.update(overrides)
    return AnalyzeFinding(**defaults)  # type: ignore[arg-type]


class TestBeadShape:
    @pytest.mark.asyncio
    async def test_created_unparented_with_expected_state(self) -> None:
        finding = _finding()
        created = type("CreatedBead", (), {"bd_id": "dea-1"})()
        create_bead_mock = AsyncMock(return_value=created)

        with (
            patch.object(BeadClient, "query", new=AsyncMock(return_value=[])),
            patch.object(BeadClient, "create_bead", new=create_bead_mock),
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
        ):
            result = await create_remediation_beads([finding], cwd=Path("/tmp/repo"))

        assert result.created_bead_ids == ("dea-1",)
        assert result.skipped_duplicate_fingerprints == ()
        assert result.errors == ()

        definition = create_bead_mock.await_args.args[0]
        parent_id = create_bead_mock.await_args.kwargs.get("parent_id")
        assert parent_id is None
        assert SPEC_REMEDIATION_LABEL in definition.labels
        assert "Ambiguous auth requirement" in definition.title

        state_dict = mock_set_state.await_args.args[1]
        assert state_dict[KEY_SPECKIT_FEATURE] == "050-headless-spec-chain"
        assert state_dict[KEY_REMEDIATION_SOURCE] == REMEDIATION_SOURCE_ANALYZE
        assert state_dict[KEY_FINDING_FINGERPRINT] == finding.fingerprint

    @pytest.mark.asyncio
    async def test_severity_hint_in_description_not_priority(self) -> None:
        finding = _finding(severity_hint="high")
        created = type("CreatedBead", (), {"bd_id": "dea-1"})()
        create_bead_mock = AsyncMock(return_value=created)

        with (
            patch.object(BeadClient, "query", new=AsyncMock(return_value=[])),
            patch.object(BeadClient, "create_bead", new=create_bead_mock),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
        ):
            await create_remediation_beads([finding], cwd=Path("/tmp/repo"))

        definition = create_bead_mock.await_args.args[0]
        assert "high" in definition.description
        # priority is a fixed advisory constant, not derived from severity.
        assert definition.priority == 2

    @pytest.mark.asyncio
    async def test_empty_findings_creates_nothing(self) -> None:
        create_bead_mock = AsyncMock()
        with patch.object(BeadClient, "create_bead", new=create_bead_mock):
            result = await create_remediation_beads([], cwd=Path("/tmp/repo"))
        create_bead_mock.assert_not_awaited()
        assert result.created_bead_ids == ()


class TestFingerprintIdempotency:
    @pytest.mark.asyncio
    async def test_existing_fingerprint_is_skipped_not_duplicated(self) -> None:
        finding = _finding()

        existing_bead = BeadDetails(
            id="dea-existing",
            title="Spec remediation: Ambiguous auth requirement",
            bead_type="task",
            status="open",
            labels=[SPEC_REMEDIATION_LABEL],
            state={KEY_FINDING_FINGERPRINT: finding.fingerprint},
        )

        async def fake_query(self: BeadClient, expr: str) -> list[BeadSummary]:
            return [
                BeadSummary(
                    id="dea-existing", title=existing_bead.title, status="open", bead_type="task"
                )
            ]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return existing_bead

        create_bead_mock = AsyncMock()

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "create_bead", new=create_bead_mock),
        ):
            result = await create_remediation_beads([finding], cwd=Path("/tmp/repo"))

        create_bead_mock.assert_not_awaited()
        assert result.created_bead_ids == ()
        assert result.skipped_duplicate_fingerprints == (finding.fingerprint,)

    @pytest.mark.asyncio
    async def test_non_remediation_beads_are_ignored_by_fingerprint_scan(self) -> None:
        finding = _finding()

        unrelated_bead = BeadDetails(
            id="dea-unrelated",
            title="Assumption: something else",
            bead_type="task",
            status="open",
            labels=["assumption"],
            state={},
        )

        async def fake_query(self: BeadClient, expr: str) -> list[BeadSummary]:
            return [
                BeadSummary(
                    id="dea-unrelated",
                    title=unrelated_bead.title,
                    status="open",
                    bead_type="task",
                )
            ]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return unrelated_bead

        created = type("CreatedBead", (), {"bd_id": "dea-new"})()

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "create_bead", new=AsyncMock(return_value=created)),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
        ):
            result = await create_remediation_beads([finding], cwd=Path("/tmp/repo"))

        assert result.created_bead_ids == ("dea-new",)

    @pytest.mark.asyncio
    async def test_two_findings_one_duplicate_one_new(self) -> None:
        dup_finding = _finding(title="Already reported")
        new_finding = _finding(title="Brand new finding", location="tasks.md#T005")

        existing_bead = BeadDetails(
            id="dea-existing",
            title="Spec remediation: Already reported",
            bead_type="task",
            status="open",
            labels=[SPEC_REMEDIATION_LABEL],
            state={KEY_FINDING_FINGERPRINT: dup_finding.fingerprint},
        )

        async def fake_query(self: BeadClient, expr: str) -> list[BeadSummary]:
            return [
                BeadSummary(
                    id="dea-existing", title=existing_bead.title, status="open", bead_type="task"
                )
            ]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return existing_bead

        created = type("CreatedBead", (), {"bd_id": "dea-new"})()

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "create_bead", new=AsyncMock(return_value=created)),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
        ):
            result = await create_remediation_beads(
                [dup_finding, new_finding], cwd=Path("/tmp/repo")
            )

        assert result.created_bead_ids == ("dea-new",)
        assert result.skipped_duplicate_fingerprints == (dup_finding.fingerprint,)


class TestBestEffortPerFinding:
    @pytest.mark.asyncio
    async def test_one_finding_failure_does_not_sink_the_others(self) -> None:
        failing_finding = _finding(title="Fails to create")
        ok_finding = _finding(title="Succeeds", location="plan.md#L10")

        call_count = {"n": 0}

        async def flaky_create_bead(
            self: BeadClient, definition: object, parent_id: object = None
        ):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("bd create failed")
            return type("CreatedBead", (), {"bd_id": "dea-ok"})()

        with (
            patch.object(BeadClient, "query", new=AsyncMock(return_value=[])),
            patch.object(BeadClient, "create_bead", new=flaky_create_bead),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
        ):
            result = await create_remediation_beads(
                [failing_finding, ok_finding], cwd=Path("/tmp/repo")
            )

        assert result.created_bead_ids == ("dea-ok",)
        assert len(result.errors) == 1
        assert "Fails to create" in result.errors[0]

    @pytest.mark.asyncio
    async def test_query_failure_does_not_raise_treats_as_no_existing(self) -> None:
        finding = _finding()
        created = type("CreatedBead", (), {"bd_id": "dea-1"})()

        async def failing_query(self: BeadClient, expr: str) -> list:
            raise RuntimeError("bd query failed")

        with (
            patch.object(BeadClient, "query", new=failing_query),
            patch.object(BeadClient, "create_bead", new=AsyncMock(return_value=created)),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
        ):
            result = await create_remediation_beads([finding], cwd=Path("/tmp/repo"))

        assert result.created_bead_ids == ("dea-1",)
