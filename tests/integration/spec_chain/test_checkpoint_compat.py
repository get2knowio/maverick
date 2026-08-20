"""Checkpoint compatibility tests (contract M6, FR-043,
057-isolated-bead-workspaces US6).

A checkpoint written by the pre-migration chain
(``.maverick/runs/<run-id>/spec-chain.json``, no ``schema_version`` key)
must resume correctly, or refuse with an explicit, actionable message —
never silently misbehave. Uses the *real* checkpoint fixture captured in
``tests/fixtures/spec_chain_pre_migration/halted_checkpoint/`` (T094)
rather than a hand-synthesized dict.

The fixture itself was captured after ``ChainState`` already gained its
``schema_version`` field (T100 landed before the fixture-capture task
ran), so it carries ``schema_version: 1`` as written. A genuine
pre-057 checkpoint never had that key at all — these tests strip it from
an in-memory copy before use, which is the faithful simulation of what
``load_chain_state``'s ``"schema_version" not in raw`` branch is actually
guarding against, not a "fix" to the committed fixture (the fixture file
on disk is never modified).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maverick.exceptions import WorkflowError
from maverick.workflows.spec_chain.constants import ChainStep
from maverick.workflows.spec_chain.state import load_chain_state
from maverick.workflows.spec_chain.workflow import SpecChainWorkflow
from tests.integration.spec_chain.conftest import (
    FEATURE,
    FEATURE_DIR,
    make_config,
    stub_runtime_factory,
)

_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "spec_chain_pre_migration"
    / "halted_checkpoint"
    / "spec-chain.json"
)

#: What the fixture's own `specify` step landed, before clarify ever
#: touched spec.md — matches `ConfigurableSpeckitRuntime`'s default
#: content for the specify step (see the fixture README's generation
#: notes and `full_chain/spec.md`'s pre-Clarifications prefix).
_SPECIFY_ONLY_CONTENT = "# Specify\n\nContent for specify.\n"


def _load_pre_migration_checkpoint() -> dict:
    raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    raw.pop("schema_version", None)
    return raw


def _install_checkpoint(checkout: Path, checkpoint: dict) -> None:
    run_id = checkpoint["run_id"]
    state_path = checkout / ".maverick" / "runs" / run_id / "spec-chain.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(checkpoint), encoding="utf-8")


class TestPreMigrationCheckpointResumes:
    async def test_verified_pre_migration_checkpoint_resumes_to_completion(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        checkpoint = _load_pre_migration_checkpoint()
        run_id = checkpoint["run_id"]

        # The fixture's prd_path points at the capture run's own tmp
        # checkout, which doesn't exist here — resume re-seeds the
        # workspace's `inputs/` dir from `state.prd_path` regardless of
        # whether specify re-runs, so it must resolve to a real file.
        # `prd_digest` deliberately stays untouched: a mismatch against
        # this repo's actual PRD only warns (FR-020), it never blocks —
        # exactly the tolerance this test exercises.
        checkpoint["prd_path"] = str(speckit_repo / "docs" / "prd.md")

        # Land exactly what the checkpoint claims `specify` produced —
        # the verification `_verify_pre_migration_checkpoint` runs before
        # trusting a schema-version-0 checkpoint.
        feature_path = speckit_repo / "specs" / FEATURE_DIR
        feature_path.mkdir(parents=True)
        (feature_path / "spec.md").write_text(_SPECIFY_ONLY_CONTENT, encoding="utf-8")

        _install_checkpoint(speckit_repo, checkpoint)

        # load_chain_state must accept it (schema_version absent, but
        # every landed artifact verifies) rather than raising.
        loaded = await load_chain_state(run_id, speckit_repo)
        assert loaded is not None
        assert loaded.status == "halted"
        assert loaded.steps[ChainStep.SPECIFY].status == "succeeded"

        stub_runtime_factory(monkeypatch)
        workflow = SpecChainWorkflow(config=make_config())
        inputs = {
            "run_id": run_id,
            "feature": FEATURE,
            "cwd": str(speckit_repo),
            "prd_path": "",
            "home": str(fake_home),
        }
        events = [event async for event in workflow.execute(inputs)]
        assert events  # the run produced progress events, not a silent no-op

        final_state = await load_chain_state(run_id, speckit_repo)
        assert final_state is not None
        assert final_state.status == "completed"
        assert final_state.schema_version == 1, "resume always writes the current schema"
        for step in ChainStep:
            assert final_state.steps[step].status == "succeeded"

        # specify was never re-invoked — it was already succeeded+landed.
        assert workflow.result is not None
        report = workflow.result.final_output
        assert report["status"] == "completed"

    async def test_checkpoint_with_unverifiable_landed_artifact_refuses_explicitly(
        self,
        speckit_repo: Path,
        fake_home: Path,
        bd_stubs: list[str],
    ) -> None:
        """FR-043's other branch: a schema-version-0 checkpoint whose
        claimed landed artifact does not actually exist on disk must
        refuse with an actionable message, never resume as if nothing
        were wrong."""
        checkpoint = _load_pre_migration_checkpoint()
        run_id = checkpoint["run_id"]
        _install_checkpoint(speckit_repo, checkpoint)
        # Deliberately do NOT create specs/001-widget-export/spec.md —
        # the checkpoint claims it landed, but it never did.

        with pytest.raises(WorkflowError) as exc_info:
            await load_chain_state(run_id, speckit_repo)

        message = str(exc_info.value)
        assert run_id in message
        assert "no longer verify" in message
        assert f"maverick spec {FEATURE}" in message
