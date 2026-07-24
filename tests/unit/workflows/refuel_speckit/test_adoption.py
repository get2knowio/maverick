"""Tests for SpeckitRefuelWorkflow's post-ingest remediation-bead adoption
step (US4, T037/contracts/ledger-and-beads.md "Adoption")."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from maverick.beads.models import BeadDetails, BeadSummary
from maverick.workflows.refuel_speckit.workflow import SpeckitRefuelWorkflow
from maverick.workflows.spec_chain.constants import (
    KEY_ADOPTED_BY_EPIC,
    KEY_SPECKIT_FEATURE,
    SPEC_REMEDIATION_LABEL,
)
from tests.unit.workflows.refuel_speckit.conftest import make_mock_bead_client
from tests.unit.workflows.refuel_speckit.test_workflow import make_feature_dir, make_inputs

_PATCH_CLIENT = "maverick.beads.client.BeadClient"


def _remediation_bead(
    bead_id: str, *, feature: str, parent_id: str | None = None, adopted_by: str | None = None
) -> BeadDetails:
    state = {KEY_SPECKIT_FEATURE: feature}
    if adopted_by:
        state[KEY_ADOPTED_BY_EPIC] = adopted_by
    return BeadDetails(
        id=bead_id,
        title=f"Spec remediation: finding for {feature}",
        bead_type="task",
        status="open",
        parent_id=parent_id,
        labels=[SPEC_REMEDIATION_LABEL],
        state=state,
    )


class TestAdoptionOnFreshRun:
    @pytest.mark.asyncio
    async def test_unparented_matching_bead_is_adopted_under_new_epic(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path, name="048-workflow-sample")
        remediation = _remediation_bead("dea-rem-1", feature="048-workflow-sample")
        mock_client = make_mock_bead_client(
            remediation_candidates=[
                BeadSummary(
                    id="dea-rem-1", title=remediation.title, status="open", bead_type="task"
                )
            ],
        )
        mock_client.show.side_effect = lambda bead_id: (
            remediation if bead_id == "dea-rem-1" else _raise_lookup(bead_id)
        )

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            from tests.unit.workflows.refuel_speckit.conftest import collect_events

            _events, result = await collect_events(workflow, make_inputs(feature_dir, tmp_path))

        assert result is not None
        assert result.success
        output = result.final_output
        assert output["adopted_remediation_bead_ids"] == ["dea-rem-1"]

        # Adopted via add_dependency (DISCOVERED_FROM epic->bead) + state stamp.
        adopt_dep_calls = [
            c
            for c in mock_client.add_dependency.call_args_list
            if c.args[0].blocked_id == "dea-rem-1"
        ]
        assert len(adopt_dep_calls) == 1
        assert adopt_dep_calls[0].args[0].blocker_id == output["epic_id"]

        adopt_state_calls = [
            c for c in mock_client.set_state.call_args_list if c.args[0] == "dea-rem-1"
        ]
        assert len(adopt_state_calls) == 1
        assert adopt_state_calls[0].args[1][KEY_ADOPTED_BY_EPIC] == output["epic_id"]


class TestAdoptionIdempotency:
    @pytest.mark.asyncio
    async def test_already_parented_bead_is_skipped(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path, name="048-workflow-sample")
        already_parented = _remediation_bead(
            "dea-rem-2", feature="048-workflow-sample", parent_id="epic-existing"
        )
        mock_client = make_mock_bead_client(
            remediation_candidates=[
                BeadSummary(
                    id="dea-rem-2",
                    title=already_parented.title,
                    status="open",
                    bead_type="task",
                )
            ],
        )
        mock_client.show.side_effect = lambda bead_id: (
            already_parented if bead_id == "dea-rem-2" else _raise_lookup(bead_id)
        )

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            from tests.unit.workflows.refuel_speckit.conftest import collect_events

            _events, result = await collect_events(workflow, make_inputs(feature_dir, tmp_path))

        assert result is not None
        output = result.final_output
        assert output["adopted_remediation_bead_ids"] == []
        adopt_dep_calls = [
            c
            for c in mock_client.add_dependency.call_args_list
            if c.args[0].blocked_id == "dea-rem-2"
        ]
        assert adopt_dep_calls == []

    @pytest.mark.asyncio
    async def test_already_stamped_bead_is_skipped(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path, name="048-workflow-sample")
        already_stamped = _remediation_bead(
            "dea-rem-3", feature="048-workflow-sample", adopted_by="epic-prior"
        )
        mock_client = make_mock_bead_client(
            remediation_candidates=[
                BeadSummary(
                    id="dea-rem-3", title=already_stamped.title, status="open", bead_type="task"
                )
            ],
        )
        mock_client.show.side_effect = lambda bead_id: (
            already_stamped if bead_id == "dea-rem-3" else _raise_lookup(bead_id)
        )

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            from tests.unit.workflows.refuel_speckit.conftest import collect_events

            _events, result = await collect_events(workflow, make_inputs(feature_dir, tmp_path))

        assert result is not None
        output = result.final_output
        assert output["adopted_remediation_bead_ids"] == []

    @pytest.mark.asyncio
    async def test_non_matching_feature_is_ignored(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path, name="048-workflow-sample")
        other_feature = _remediation_bead("dea-rem-4", feature="099-unrelated-feature")
        mock_client = make_mock_bead_client(
            remediation_candidates=[
                BeadSummary(
                    id="dea-rem-4", title=other_feature.title, status="open", bead_type="task"
                )
            ],
        )
        mock_client.show.side_effect = lambda bead_id: (
            other_feature if bead_id == "dea-rem-4" else _raise_lookup(bead_id)
        )

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            from tests.unit.workflows.refuel_speckit.conftest import collect_events

            _events, result = await collect_events(workflow, make_inputs(feature_dir, tmp_path))

        assert result is not None
        output = result.final_output
        assert output["adopted_remediation_bead_ids"] == []


class TestAdoptionBestEffort:
    @pytest.mark.asyncio
    async def test_one_bead_adoption_failure_does_not_abort_ingestion(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path, name="048-workflow-sample")
        failing = _remediation_bead("dea-rem-fail", feature="048-workflow-sample")
        ok = _remediation_bead("dea-rem-ok", feature="048-workflow-sample")

        mock_client = make_mock_bead_client(
            remediation_candidates=[
                BeadSummary(
                    id="dea-rem-fail", title=failing.title, status="open", bead_type="task"
                ),
                BeadSummary(id="dea-rem-ok", title=ok.title, status="open", bead_type="task"),
            ],
        )

        def _show(bead_id: str) -> BeadDetails:
            if bead_id == "dea-rem-fail":
                return failing
            if bead_id == "dea-rem-ok":
                return ok
            _raise_lookup(bead_id)
            raise AssertionError("unreachable")

        mock_client.show.side_effect = _show

        async def _flaky_add_dependency(dep: object) -> None:
            if getattr(dep, "blocked_id", None) == "dea-rem-fail":
                raise RuntimeError("bd add-dep failed")

        mock_client.add_dependency.side_effect = _flaky_add_dependency

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            from tests.unit.workflows.refuel_speckit.conftest import collect_events

            _events, result = await collect_events(workflow, make_inputs(feature_dir, tmp_path))

        assert result is not None
        assert result.success
        output = result.final_output
        assert output["adopted_remediation_bead_ids"] == ["dea-rem-ok"]


def _raise_lookup(bead_id: str) -> BeadDetails:
    raise LookupError(bead_id)
