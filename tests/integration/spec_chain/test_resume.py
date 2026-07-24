"""Integration tests for resume (US3, T028).

A halted chain re-run continues from the failed step without
regenerating landed artifacts; a landed step whose artifacts vanished
from the checkout gets re-run; a PRD digest mismatch on resume warns
without re-running specify; a completed chain blocks a fresh run for the
same feature as a collision.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from maverick.cli.context import ExitCode
from maverick.main import cli
from maverick.workflows.spec_chain.constants import ChainStep
from maverick.workflows.spec_chain.state import load_chain_state
from maverick.workflows.spec_chain.workflow import SpecChainWorkflow
from tests.integration.spec_chain.conftest import (
    FEATURE,
    FEATURE_DIR,
    make_config,
    stub_runtime_factory,
)


def _failing_handler(feature_path: Path, runtime: Any) -> dict[str, Any]:
    return {
        "status": "failed",
        "artifacts": [],
        "questions": [],
        "findings": [],
        "detail": "induced failure",
    }


async def _run_once(
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


class TestHaltedChainResumesFromFailedStep:
    async def test_resume_continues_without_rerunning_specify(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        run_id = "resume-continues"

        # Run 1: clarify fails, chain halts.
        stub_runtime_factory(monkeypatch, step_handlers={ChainStep.CLARIFY: _failing_handler})
        await _run_once(speckit_repo, fake_home, run_id=run_id)

        state_after_halt = await load_chain_state(run_id, speckit_repo)
        assert state_after_halt is not None
        assert state_after_halt.status == "halted"
        assert state_after_halt.steps[ChainStep.SPECIFY].status == "succeeded"
        assert state_after_halt.steps[ChainStep.CLARIFY].status == "failed"

        # Run 2 (resume): clarify now succeeds, chain completes.
        second_runtimes = stub_runtime_factory(monkeypatch)
        workflow2, _ = await _run_once(speckit_repo, fake_home, run_id=run_id)

        # specify was never re-invoked in the resumed run.
        assert len(second_runtimes) == 1
        prompts = [c["prompt"] for c in second_runtimes[0].execute_calls]
        assert not any("/speckit.specify" in p for p in prompts)
        assert any("/speckit.clarify" in p for p in prompts)

        final_state = await load_chain_state(run_id, speckit_repo)
        assert final_state is not None
        assert final_state.status == "completed"
        for step in ChainStep:
            assert final_state.steps[step].status == "succeeded"

        report = workflow2.result.final_output
        assert report["status"] == "completed"


class TestLandedArtifactVerification:
    async def test_missing_landed_artifact_reruns_its_step(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        run_id = "resume-missing-artifact"

        # Run 1: halt at tasks, so specify/clarify/plan are succeeded+landed.
        stub_runtime_factory(monkeypatch, step_handlers={ChainStep.TASKS: _failing_handler})
        await _run_once(speckit_repo, fake_home, run_id=run_id)

        state = await load_chain_state(run_id, speckit_repo)
        assert state is not None
        assert state.status == "halted"
        assert state.steps[ChainStep.PLAN].status == "succeeded"
        assert state.steps[ChainStep.PLAN].landed is True

        # The user (or something) deletes the landed plan.md.
        plan_path = speckit_repo / "specs" / FEATURE_DIR / "plan.md"
        assert plan_path.is_file()
        plan_path.unlink()

        # Run 2 (resume): plan.md is missing, so plan must re-run even
        # though it was previously "succeeded" — specify/clarify are
        # untouched and must NOT re-run.
        second_runtimes = stub_runtime_factory(monkeypatch)
        await _run_once(speckit_repo, fake_home, run_id=run_id)

        prompts = [c["prompt"] for c in second_runtimes[0].execute_calls]
        assert not any("/speckit.specify" in p for p in prompts)
        assert not any("/speckit.clarify" in p for p in prompts)
        assert any("/speckit.plan" in p for p in prompts)

        final_state = await load_chain_state(run_id, speckit_repo)
        assert final_state is not None
        assert final_state.status == "completed"
        assert final_state.steps[ChainStep.PLAN].status == "succeeded"
        assert plan_path.is_file()


class TestWorkspaceReseedOnResume:
    async def test_deleted_workspace_is_reseeded_from_checkout(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        """If the hidden workspace vanishes between runs (user cleared
        ~/.maverick/workspaces), resume recreates it from the *committed*
        tree — which lacks the un-committed landed spec files. The reseed
        restores those landed upstream artifacts so the next step doesn't
        run against an empty workspace."""
        import shutil

        run_id = "resume-workspace-deleted"

        # Run 1: halt at tasks, so specify/clarify/plan are succeeded+landed.
        stub_runtime_factory(monkeypatch, step_handlers={ChainStep.TASKS: _failing_handler})
        await _run_once(speckit_repo, fake_home, run_id=run_id)

        state = await load_chain_state(run_id, speckit_repo)
        assert state is not None
        assert state.status == "halted"
        assert state.steps[ChainStep.PLAN].landed is True

        # The entire hidden workspace is wiped between runs.
        workspace_root = fake_home / ".maverick" / "workspaces" / "repo" / "spec-chain" / FEATURE
        assert workspace_root.exists()
        shutil.rmtree(workspace_root)

        # Run 2 (resume): workspace is recreated fresh, then reseeded with
        # the landed upstream artifacts before tasks re-runs.
        stub_runtime_factory(monkeypatch)
        await _run_once(speckit_repo, fake_home, run_id=run_id)

        # The reseed restored upstream artifacts into the fresh workspace.
        ws_feature = workspace_root / "specs" / FEATURE_DIR
        assert (ws_feature / "spec.md").is_file()
        assert (ws_feature / "plan.md").is_file()

        final_state = await load_chain_state(run_id, speckit_repo)
        assert final_state is not None
        assert final_state.status == "completed"


class TestPrdDigestMismatchWarns:
    async def test_changed_prd_warns_without_rerunning_specify(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        bd_stubs: list[str],
    ) -> None:
        run_id = "resume-prd-changed"

        stub_runtime_factory(monkeypatch, step_handlers={ChainStep.PLAN: _failing_handler})
        await _run_once(speckit_repo, fake_home, run_id=run_id)

        state = await load_chain_state(run_id, speckit_repo)
        assert state is not None
        assert state.status == "halted"

        # PRD content changes between halt and resume.
        prd_path = speckit_repo / "docs" / "prd.md"
        prd_path.write_text(
            "# Widget Export PRD (v2)\n\nDifferent content now.\n", encoding="utf-8"
        )

        second_runtimes = stub_runtime_factory(monkeypatch)
        _workflow, events = await _run_once(speckit_repo, fake_home, run_id=run_id)

        prompts = [c["prompt"] for c in second_runtimes[0].execute_calls]
        assert not any("/speckit.specify" in p for p in prompts)

        warning_events = [
            e
            for e in events
            if type(e).__name__ == "StepOutput" and getattr(e, "level", None) == "warning"
        ]
        assert any("PRD content has changed" in e.message for e in warning_events)

        final_state = await load_chain_state(run_id, speckit_repo)
        assert final_state is not None
        assert final_state.status == "completed"


class TestCompletedChainCollision:
    def test_completed_chain_same_feature_exits_partial(
        self,
        speckit_repo: Path,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A *completed* chain is not auto-resumable — re-running for the
        same feature without deleting the spec dir is a collision
        (FR-015), not a resume."""
        from maverick.workflows.spec_chain.models import ChainState, StepRecord
        from maverick.workflows.spec_chain.state import save_chain_state

        now = datetime.now(tz=UTC)
        completed_state = ChainState(
            run_id="already-done",
            feature=FEATURE,
            feature_dir=f"specs/{FEATURE_DIR}",
            prd_path=str(speckit_repo / "docs" / "prd.md"),
            prd_digest="0" * 64,
            workspace_path=str(
                fake_home / ".maverick" / "workspaces" / "repo" / "spec-chain" / FEATURE
            ),
            status="completed",
            steps={
                step: StepRecord(
                    step=step,
                    status="succeeded",
                    attempts=1,
                    artifacts=[],
                    landed=True,
                )
                for step in ChainStep
            },
            clarify_decisions=[],
            remediation_bead_ids=[],
            started_at=now,
            updated_at=now,
        )

        import asyncio

        asyncio.run(save_chain_state(completed_state, speckit_repo))
        (speckit_repo / "specs" / FEATURE_DIR).mkdir(parents=True)

        import os

        os.chdir(speckit_repo)
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.setattr("maverick.cli.commands.spec.verify_bd_ready", lambda cwd=None: None)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["spec", FEATURE, "--from-prd", str(speckit_repo / "docs" / "prd.md")],
        )

        assert result.exit_code == ExitCode.PARTIAL
        assert "already exists" in result.output
