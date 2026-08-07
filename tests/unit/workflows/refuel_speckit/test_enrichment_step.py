"""Tests for the workflow-level ENRICH step (--enrich)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.workflows.refuel_speckit.workflow import SpeckitRefuelWorkflow
from tests.unit.workflows.refuel_speckit.conftest import (
    WORKFLOW_SPEC_MD,
    WORKFLOW_TASKS_MD,
    collect_events,
    make_mock_bead_client,
)

_PATCH_CLIENT = "maverick.beads.client.BeadClient"


def make_feature_dir(tmp_path: Path, name: str = "048-workflow-sample") -> Path:
    feature_dir = tmp_path / "specs" / name
    feature_dir.mkdir(parents=True)
    (feature_dir / "tasks.md").write_text(WORKFLOW_TASKS_MD, encoding="utf-8")
    (feature_dir / "spec.md").write_text(WORKFLOW_SPEC_MD, encoding="utf-8")
    return feature_dir


def make_inputs(feature_dir: Path, cwd: Path, **overrides: object) -> dict[str, object]:
    inputs: dict[str, object] = {
        "feature_dir": str(feature_dir),
        "cwd": str(cwd),
        "dry_run": False,
        "enrich": False,
        "auto_commit": False,
    }
    inputs.update(overrides)
    return inputs


_ENRICH_RESPONSE = """\
### T001
- make test-t001

### T002
- make test-t002

### T003
- make test-t003
"""


class TestEnrichmentSuccess:
    @pytest.mark.asyncio
    async def test_enrichment_augments_verification_and_ingests(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path)
        mock_client = make_mock_bead_client()

        mock_agent = MagicMock()
        mock_agent.__aenter__ = AsyncMock(return_value=mock_agent)
        mock_agent.__aexit__ = AsyncMock(return_value=False)
        mock_agent.enrich = AsyncMock(return_value=_ENRICH_RESPONSE)

        with (
            patch(_PATCH_CLIENT, return_value=mock_client),
            patch("maverick.config.load_config", return_value=mock_config),
            patch(
                "maverick.runtime.agent_factory.runtime_for_agent",
                return_value=(MagicMock(), MagicMock()),
            ),
            patch(
                "maverick.agents.personas.SpeckitEnrichmentAgent",
                return_value=mock_agent,
            ),
        ):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            _events, result = await collect_events(
                workflow, make_inputs(feature_dir, tmp_path, enrich=True)
            )

        assert result is not None and result.success
        output = result.final_output
        assert output["enriched"] is True

        created_descriptions = [
            call.args[0].description for call in mock_client.create_bead.call_args_list
        ]
        assert any("make test-t001" in d for d in created_descriptions)


class TestEnrichmentPartialCoverage:
    @pytest.mark.asyncio
    async def test_enrich_count_reflects_only_tasks_with_commands(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path)
        mock_client = make_mock_bead_client()

        # Model returns commands for only 1 of the 3 new tasks.
        mock_agent = MagicMock()
        mock_agent.__aenter__ = AsyncMock(return_value=mock_agent)
        mock_agent.__aexit__ = AsyncMock(return_value=False)
        mock_agent.enrich = AsyncMock(return_value="### T001\n- make test-t001\n")

        with (
            patch(_PATCH_CLIENT, return_value=mock_client),
            patch("maverick.config.load_config", return_value=mock_config),
            patch(
                "maverick.runtime.agent_factory.runtime_for_agent",
                return_value=(MagicMock(), MagicMock()),
            ),
            patch(
                "maverick.agents.personas.SpeckitEnrichmentAgent",
                return_value=mock_agent,
            ),
        ):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            events, result = await collect_events(
                workflow, make_inputs(feature_dir, tmp_path, enrich=True)
            )

        assert result is not None and result.success
        messages = [getattr(e, "message", "") for e in events if hasattr(e, "message")]
        # Reports the actual applied count (1), not the total new-task count (3).
        assert any("Enriched 1 of 3 task beads" in m for m in messages)


class TestEnrichmentFailure:
    @pytest.mark.asyncio
    async def test_enrichment_failure_degrades_to_warning_and_still_ingests(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path)
        mock_client = make_mock_bead_client()

        with (
            patch(_PATCH_CLIENT, return_value=mock_client),
            patch(
                "maverick.runtime.agent_factory.runtime_for_agent",
                side_effect=RuntimeError("no provider auth configured"),
            ),
        ):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            _events, result = await collect_events(
                workflow, make_inputs(feature_dir, tmp_path, enrich=True)
            )

        assert result is not None and result.success
        output = result.final_output
        assert output["enriched"] is False
        assert any("enrichment failed" in w for w in output["warnings"])
        # Ingestion still succeeded — all 3 tasks created unenriched.
        assert len(output["created_bead_ids"]) == 3


class TestNoModelConstructionWithoutEnrich:
    @pytest.mark.asyncio
    async def test_no_agent_or_runtime_import_when_enrich_absent(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path)
        mock_client = make_mock_bead_client()

        # Poison the agent-factory import path — if the workflow imports it
        # at all on the non-enrich path, this raises and the run fails.
        with (
            patch(_PATCH_CLIENT, return_value=mock_client),
            patch.dict(
                sys.modules,
                {
                    "maverick.runtime.agent_factory": None,
                    "maverick.agents.personas": None,
                },
            ),
        ):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            _events, result = await collect_events(
                workflow, make_inputs(feature_dir, tmp_path, enrich=False)
            )

        assert result is not None and result.success
        assert result.final_output["enriched"] is False


class TestDryRunWithEnrich:
    @pytest.mark.asyncio
    async def test_dry_run_enrich_previews_enriched_content_with_zero_writes(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path)
        mock_client = make_mock_bead_client()

        mock_agent = MagicMock()
        mock_agent.__aenter__ = AsyncMock(return_value=mock_agent)
        mock_agent.__aexit__ = AsyncMock(return_value=False)
        mock_agent.enrich = AsyncMock(return_value=_ENRICH_RESPONSE)

        with (
            patch(_PATCH_CLIENT, return_value=mock_client),
            patch("maverick.config.load_config", return_value=mock_config),
            patch(
                "maverick.runtime.agent_factory.runtime_for_agent",
                return_value=(MagicMock(), MagicMock()),
            ),
            patch(
                "maverick.agents.personas.SpeckitEnrichmentAgent",
                return_value=mock_agent,
            ),
        ):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            _events, result = await collect_events(
                workflow,
                make_inputs(feature_dir, tmp_path, enrich=True, dry_run=True),
            )

        assert result is not None and result.success
        output = result.final_output
        assert output["dry_run"] is True
        assert output["enriched"] is True
        mock_client.create_bead.assert_not_called()
        mock_client.add_dependency.assert_not_called()
        mock_client.set_state.assert_not_called()


class TestEnrichmentProtectionArtifactSharesRunDir:
    """``protection-blocks.json`` must land in *this* run's directory.

    An earlier revision minted a throwaway ``uuid4()`` for the artifact, so
    it landed in a ``.maverick/runs/<random>/`` holding nothing else — while
    ``_record_run`` wrote ``metadata.json`` under a *different* random id.
    The warning told the user to read a file they could not locate.
    """

    @pytest.mark.asyncio
    async def test_artifact_lands_beside_run_metadata(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        from maverick.protection.records import BlockCollector, BlockRecord

        feature_dir = make_feature_dir(tmp_path)
        mock_client = make_mock_bead_client()

        mock_agent = MagicMock()
        mock_agent.__aenter__ = AsyncMock(return_value=mock_agent)
        mock_agent.__aexit__ = AsyncMock(return_value=False)
        mock_agent.enrich = AsyncMock(return_value=_ENRICH_RESPONSE)

        # A collector that already holds a block, so the drain has
        # something to persist without needing a real protected write.
        collector = BlockCollector()
        collector.append(
            BlockRecord(
                agent_role="generate",
                workflow="refuel-speckit",
                operation="edit",
                path="CLAUDE.md",
                layer="backstop",
            )
        )

        with (
            patch(_PATCH_CLIENT, return_value=mock_client),
            patch("maverick.config.load_config", return_value=mock_config),
            patch(
                "maverick.runtime.agent_factory.runtime_for_agent",
                return_value=(MagicMock(), MagicMock()),
            ),
            patch(
                "maverick.agents.personas.SpeckitEnrichmentAgent",
                return_value=mock_agent,
            ),
            patch(
                "maverick.protection.build_ad_hoc_protection",
                return_value=(MagicMock(), collector),
            ),
        ):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            events, result = await collect_events(
                workflow, make_inputs(feature_dir, tmp_path, enrich=True)
            )

        assert result is not None and result.success

        runs_dir = tmp_path / ".maverick" / "runs"
        run_dirs = sorted(p for p in runs_dir.iterdir() if p.is_dir())
        # Exactly one run directory — not one for metadata and a second,
        # orphaned one for the protection artifact.
        assert len(run_dirs) == 1
        run_dir = run_dirs[0]
        assert (run_dir / "metadata.json").is_file()
        artifact = run_dir / "protection-blocks.json"
        assert artifact.is_file()

        # The artifact's own run_id agrees with the directory it sits in.
        body = json.loads(artifact.read_text(encoding="utf-8"))
        assert body["run_id"] == run_dir.name

        # And the warning points at that exact path.
        messages = [getattr(e, "message", "") for e in events if hasattr(e, "message")]
        expected = f".maverick/runs/{run_dir.name}/protection-blocks.json"
        assert any(expected in m for m in messages)
