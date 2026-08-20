"""Migration parity tests for the spec-chain workflow's move onto the
shared isolation primitive (057-isolated-bead-workspaces, US6).

Proves contracts/spec-chain-migration.md's guarantees against the
post-migration `SpecChainWorkflow` — the whole contract's premise is that
nothing observable changed, so these tests compare against the real
pre-migration baseline captured in
``tests/fixtures/spec_chain_pre_migration/`` (T094) rather than a
hand-written expectation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from maverick.protection.records import BlockRecord
from maverick.workflows.spec_chain.constants import ChainStep
from maverick.workflows.spec_chain.state import load_chain_state
from maverick.workflows.spec_chain.workflow import SpecChainWorkflow
from maverick.workspace.lifecycle import workspace_dir
from tests.integration.spec_chain.conftest import (
    FEATURE,
    FEATURE_DIR,
    make_config,
    stub_runtime_factory,
)

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "spec_chain_pre_migration"


def _blocked_handler(feature_path: Path, runtime: Any) -> dict[str, Any]:
    return {
        "status": "blocked",
        "artifacts": [],
        "questions": [],
        "findings": [],
        "detail": "induced halt for parity coverage",
    }


def _failing_no_artifacts_handler(feature_path: Path, runtime: Any) -> dict[str, Any]:
    return {
        "status": "completed",
        "artifacts": [],
        "questions": [],
        "findings": [],
        "detail": "claims success but wrote nothing",
    }


async def _run(
    speckit_repo: Path, fake_home: Path, *, run_id: str, prd_path: Path | None = None
) -> tuple[Any, list]:
    workflow = SpecChainWorkflow(config=make_config())
    inputs = {
        "run_id": run_id,
        "feature": FEATURE,
        "cwd": str(speckit_repo),
        "prd_path": str(prd_path or (speckit_repo / "docs" / "prd.md")),
        "home": str(fake_home),
    }
    events = [event async for event in workflow.execute(inputs)]
    return workflow, events


def _workspace_path(speckit_repo: Path, fake_home: Path) -> Path:
    return workspace_dir(
        root=fake_home / ".maverick" / "workspaces",
        checkout=speckit_repo,
        workflow="spec-chain",
        key=FEATURE,
    )


class TestM1LandedArtifactsByteIdentical:
    """Contract M1 (FR-040, SC-009): a full post-migration chain lands the
    same artifacts, byte for byte, as the pre-migration baseline."""

    async def test_full_chain_matches_pre_migration_baseline(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        stub_runtime_factory(monkeypatch)
        workflow, _ = await _run(speckit_repo, fake_home, run_id="parity-m1")

        assert workflow.result is not None
        assert workflow.result.final_output["status"] == "completed"

        baseline_dir = _FIXTURES / "full_chain" / "specs" / FEATURE_DIR
        landed_dir = speckit_repo / "specs" / FEATURE_DIR
        for name in ("spec.md", "plan.md", "tasks.md"):
            baseline_content = (baseline_dir / name).read_text(encoding="utf-8")
            landed_content = (landed_dir / name).read_text(encoding="utf-8")
            assert landed_content == baseline_content, f"{name} diverged from the baseline"


class TestM2M3ResumeAndFailureSemantics:
    """Contract M2/M3 (FR-041, FR-042): resume continues from the first
    incomplete step; a failed step lands no partial artifacts."""

    async def test_halted_chain_resumes_from_first_incomplete_step(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        stub_runtime_factory(monkeypatch, step_handlers={ChainStep.CLARIFY: _blocked_handler})
        await _run(speckit_repo, fake_home, run_id="parity-m2")

        halted = await load_chain_state("parity-m2", speckit_repo)
        assert halted is not None
        assert halted.status == "halted"
        assert halted.steps[ChainStep.SPECIFY].status == "succeeded"
        assert halted.steps[ChainStep.CLARIFY].status == "failed"

        second_runtimes = stub_runtime_factory(monkeypatch)
        await _run(speckit_repo, fake_home, run_id="parity-m2")

        prompts = [c["prompt"] for c in second_runtimes[0].execute_calls]
        assert not any("/speckit-specify" in p for p in prompts)
        assert any("/speckit-clarify" in p for p in prompts)

        final_state = await load_chain_state("parity-m2", speckit_repo)
        assert final_state is not None
        assert final_state.status == "completed"

    async def test_failed_step_lands_no_partial_artifacts(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        stub_runtime_factory(
            monkeypatch, step_handlers={ChainStep.PLAN: _failing_no_artifacts_handler}
        )
        await _run(speckit_repo, fake_home, run_id="parity-m3")

        state = await load_chain_state("parity-m3", speckit_repo)
        assert state is not None
        assert state.status == "halted"
        assert state.steps[ChainStep.PLAN].status == "failed"

        feature_path = speckit_repo / "specs" / FEATURE_DIR
        assert (feature_path / "spec.md").is_file()
        assert not (feature_path / "plan.md").exists()
        assert not (feature_path / "tasks.md").exists()


class TestM4WorkspaceRetentionOnOutcome:
    """Contract M4 (FR-024, FR-025): a halted chain's workspace is
    retained (it holds the failing step's only partial output); a
    completed chain's is torn down."""

    async def test_halted_chain_retains_its_workspace(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        stub_runtime_factory(monkeypatch, step_handlers={ChainStep.CLARIFY: _blocked_handler})
        await _run(speckit_repo, fake_home, run_id="parity-m4-halt")

        assert _workspace_path(speckit_repo, fake_home).is_dir()

    async def test_completed_chain_tears_down_its_workspace(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        stub_runtime_factory(monkeypatch)
        await _run(speckit_repo, fake_home, run_id="parity-m4-complete")

        assert not _workspace_path(speckit_repo, fake_home).exists()


class TestM7FoldBackScopedToFeatureDir:
    """Contract M7 (FR-040): fold-back is scoped to
    ``specs/<feature-dir>`` — a change written elsewhere in the workspace
    never lands in the checkout."""

    async def test_out_of_scope_workspace_write_does_not_land(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        def _specify_and_stray_write(feature_path: Path, runtime: Any) -> dict[str, Any]:
            content = "# Specify\n\nContent for specify.\n"
            (feature_path / "spec.md").write_text(content, encoding="utf-8")
            stray = feature_path.parent.parent / "stray-out-of-scope.txt"
            stray.write_text("this must never land in the checkout\n", encoding="utf-8")
            return {
                "status": "completed",
                "artifacts": ["spec.md"],
                "questions": [],
                "findings": [],
                "detail": "specify written, plus an out-of-scope stray file",
            }

        stub_runtime_factory(
            monkeypatch, step_handlers={ChainStep.SPECIFY: _specify_and_stray_write}
        )
        await _run(speckit_repo, fake_home, run_id="parity-m7")

        assert not (speckit_repo / "stray-out-of-scope.txt").exists()
        assert (speckit_repo / "specs" / FEATURE_DIR / "spec.md").is_file()


class TestS6ProtectionBlocksSurviveCheckpointAndResume:
    """Contract S6 (FR-036): protection blocks still drain per step into
    ``ChainState.protection_blocks`` and survive checkpoint + resume."""

    async def test_protection_block_persists_across_resume(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        def _specify_and_protected_write(feature_path: Path, runtime: Any) -> dict[str, Any]:
            content = "# Specify\n\nContent for specify.\n"
            (feature_path / "spec.md").write_text(content, encoding="utf-8")
            # Workspace-root CLAUDE.md — a protected path under the
            # default policy. The snapshot backstop must revert this.
            (feature_path.parent.parent / "CLAUDE.md").write_text(
                "malicious rewrite\n", encoding="utf-8"
            )
            return {
                "status": "completed",
                "artifacts": ["spec.md"],
                "questions": [],
                "findings": [],
                "detail": "specify written, plus a protected-path write attempt",
            }

        stub_runtime_factory(
            monkeypatch,
            step_handlers={
                ChainStep.SPECIFY: _specify_and_protected_write,
                ChainStep.CLARIFY: _blocked_handler,
            },
        )
        await _run(speckit_repo, fake_home, run_id="parity-s6")

        halted = await load_chain_state("parity-s6", speckit_repo)
        assert halted is not None
        assert halted.status == "halted"
        assert halted.protection_blocks, "specify's protected write should have been recorded"
        blocks = [BlockRecord.from_dict(d) for d in halted.protection_blocks]
        assert any(b.path.endswith("CLAUDE.md") for b in blocks)

        # The checkpoint on disk carries the block record too.
        state_path = speckit_repo / ".maverick" / "runs" / "parity-s6" / "spec-chain.json"
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        assert raw["protection_blocks"], "protection_blocks must survive the on-disk checkpoint"

        stub_runtime_factory(monkeypatch)
        await _run(speckit_repo, fake_home, run_id="parity-s6")

        final_state = await load_chain_state("parity-s6", speckit_repo)
        assert final_state is not None
        assert final_state.status == "completed"
        assert final_state.protection_blocks, (
            "the block recorded before halt must survive resume, not just the halt"
        )
