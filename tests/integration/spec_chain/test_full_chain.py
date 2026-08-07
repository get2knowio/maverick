"""Full five-step happy-path integration test for `SpecChainWorkflow`.

Runs against a real tmp jj+git colocated repo fixture (with
`.claude/skills/speckit-*/SKILL.md` and `.specify/` markers) and a stubbed
airframe runtime that writes canned artifacts — no live model calls.
Asserts strict ordering, artifact landing, final report counts, that no
interactive input is ever requested (FR-004), and that spec/plan/tasks
artifact content is byte-identical before and after the analyze step
(FR-011).
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from airframe.cost import CostRecord
from airframe.protocol import RuntimeResult

from maverick.beads.client import BeadClient
from maverick.beads.models import BeadSummary
from maverick.config import AgentBindingConfig, AgentsConfig, MaverickConfig
from maverick.workflows.spec_chain.constants import ChainStep
from maverick.workflows.spec_chain.state import load_chain_state
from maverick.workflows.spec_chain.workflow import SpecChainWorkflow

FEATURE = "widget-export"
FEATURE_DIR = f"001-{FEATURE}"

_COMMAND_STEPS = (
    ChainStep.SPECIFY,
    ChainStep.CLARIFY,
    ChainStep.PLAN,
    ChainStep.TASKS,
    ChainStep.ANALYZE,
)


def _run(cmd: list[str], *, cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _build_speckit_repo(tmp_path: Path) -> Path:
    """A real, colocated jj+git repo with the Spec Kit command/marker
    surface `SpecChainWorkflow` expects, plus a sample PRD."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], cwd=repo)
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _run(["git", "config", "user.name", "Test"], cwd=repo)
    _run(["jj", "git", "init", "--colocate"], cwd=repo)

    # Spec Kit >= 0.14 ships skills, not commands — see the note in
    # `conftest.build_speckit_repo`.
    skills_dir = repo / ".claude" / "skills"
    for step in _COMMAND_STEPS:
        step_dir = skills_dir / f"speckit-{step.value}"
        step_dir.mkdir(parents=True)
        (step_dir / "SKILL.md").write_text(
            f"Instructions for /speckit-{step.value}.\n", encoding="utf-8"
        )

    specify_dir = repo / ".specify"
    specify_dir.mkdir()
    (specify_dir / "init-options.json").write_text(
        '{"speckit_version": "0.16.0"}', encoding="utf-8"
    )

    docs_dir = repo / "docs"
    docs_dir.mkdir()
    (docs_dir / "prd.md").write_text(
        "# Widget Export PRD\n\nExport widgets to CSV.\n", encoding="utf-8"
    )

    _run(["jj", "commit", "-m", "initial speckit repo"], cwd=repo)
    return repo


def _cost() -> CostRecord:
    return CostRecord(
        provider_id="anthropic",
        model_id="claude-haiku-4-5",
        cost_usd=0.01,
        input_tokens=10,
        output_tokens=20,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish="end_turn",
    )


class _CannedSpeckitRuntime:
    """Stand-in for the airframe runtime — writes canned artifacts to the
    current working directory (the SpecChainAgent has already `os.chdir`ed
    into the hidden workspace by the time `execute()` runs) instead of
    calling a real model."""

    label = "stub"

    def __init__(self, *, model: str | None = None, **kwargs: Any) -> None:
        self.model = model
        self.execute_calls: list[dict[str, Any]] = []
        #: Content written for spec.md/plan.md/tasks.md, keyed by
        #: feature-dir-relative filename — used to prove analyze never
        #: touches them (FR-011).
        self.written_content: dict[str, str] = {}

    async def execute(self, prompt: str, **kwargs: Any) -> RuntimeResult:
        self.execute_calls.append({"prompt": prompt, **kwargs})
        step = self._infer_step(prompt)
        feature_path = Path.cwd() / "specs" / FEATURE_DIR
        feature_path.mkdir(parents=True, exist_ok=True)

        structured: dict[str, Any]
        if step is ChainStep.SPECIFY:
            content = "# Widget Export Spec\n\nSpecified from PRD.\n"
            (feature_path / "spec.md").write_text(content, encoding="utf-8")
            self.written_content["spec.md"] = content
            structured = {
                "status": "completed",
                "artifacts": ["spec.md"],
                "questions": [],
                "findings": [],
                "detail": "Spec written from PRD.",
            }
        elif step is ChainStep.CLARIFY:
            # Simulates Spec Kit's own non-interactive convention: clarify
            # rewrites spec.md, appending a "## Clarifications" section
            # with the adopted defaults (R2).
            spec_path = feature_path / "spec.md"
            existing = spec_path.read_text(encoding="utf-8") if spec_path.is_file() else ""
            updated = existing + (
                "\n## Clarifications\n\n### Session 2026-07-24\n\n"
                "- Q: Should exports include archived widgets? "
                "→ A: No, exclude archived widgets.\n"
            )
            spec_path.write_text(updated, encoding="utf-8")
            self.written_content["spec.md"] = updated
            structured = {
                "status": "completed",
                "artifacts": ["spec.md"],
                "questions": [
                    {
                        "question": "Should exports include archived widgets?",
                        "adopted_answer": "No, exclude archived widgets.",
                        "alternatives": ["Include all widgets"],
                    }
                ],
                "findings": [],
                "detail": "Clarify complete, no ambiguity remained unresolved.",
            }
        elif step is ChainStep.PLAN:
            content = "# Plan\n\nImplementation plan for widget export.\n"
            (feature_path / "plan.md").write_text(content, encoding="utf-8")
            self.written_content["plan.md"] = content
            structured = {
                "status": "completed",
                "artifacts": ["plan.md"],
                "questions": [],
                "findings": [],
                "detail": "Plan written.",
            }
        elif step is ChainStep.TASKS:
            content = "# Tasks\n\n- [ ] T001 Implement export\n"
            (feature_path / "tasks.md").write_text(content, encoding="utf-8")
            self.written_content["tasks.md"] = content
            structured = {
                "status": "completed",
                "artifacts": ["tasks.md"],
                "questions": [],
                "findings": [],
                "detail": "Tasks written.",
            }
        else:
            structured = {
                "status": "completed",
                "artifacts": [],
                "questions": [],
                "findings": [
                    {
                        "title": "Ambiguous export format",
                        "category": "ambiguity",
                        "severity_hint": "low",
                        "location": "spec.md",
                        "summary": "CSV column order unspecified.",
                    }
                ],
                "detail": "Analyze complete.",
            }

        return RuntimeResult(text="", structured=structured, cost=_cost(), finish="end_turn")

    @staticmethod
    def _infer_step(prompt: str) -> ChainStep:
        for step in _COMMAND_STEPS:
            if f"/speckit-{step.value}" in prompt:
                return step
        raise AssertionError(f"could not infer step from prompt: {prompt!r}")

    async def reset(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def validate_binding(self, _binding: Any) -> bool:
        return True

    def supports(self, feature: Any, model: Any = None) -> bool:
        return False

    def session(self, **kwargs: Any) -> _CannedSpeckitSession:
        return _CannedSpeckitSession(self)


class _CannedSpeckitSession:
    """Minimal ``AgentSession`` stand-in — ``Agent.open()`` always routes
    through ``runtime.session(...)`` when a squadron builds a real
    ``ProtectionPolicy`` (056-context-file-protection); delegates back to
    the runtime's own stubbed ``execute()``."""

    def __init__(self, runtime: _CannedSpeckitRuntime) -> None:
        self.id = "stub-session"
        self._runtime = runtime

    async def execute(self, prompt: str, **kwargs: Any) -> RuntimeResult:
        return await self._runtime.execute(prompt, **kwargs)

    async def close(self) -> None:
        return None


@pytest.fixture
def speckit_repo(tmp_path: Path) -> Path:
    return _build_speckit_repo(tmp_path)


@pytest.fixture
def fake_home(tmp_path: Path) -> Path:
    home = tmp_path / "fake-home"
    home.mkdir()
    return home


async def test_full_chain_happy_path(
    speckit_repo: Path,
    fake_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed: list[_CannedSpeckitRuntime] = []

    def _factory(provider_id: str) -> type[_CannedSpeckitRuntime]:
        class _Bound(_CannedSpeckitRuntime):
            def __init__(self, *, model: str | None = None, **kwargs: Any) -> None:
                super().__init__(model=model, **kwargs)
                constructed.append(self)

        return _Bound

    monkeypatch.setattr("airframe.runtime_for", _factory)

    config = MaverickConfig(
        agents=AgentsConfig(generate=AgentBindingConfig(provider="claude", model_id="stub-model"))
    )
    workflow = SpecChainWorkflow(config=config)

    run_id = "test-run-1"
    inputs = {
        "run_id": run_id,
        "feature": FEATURE,
        "cwd": str(speckit_repo),
        "prd_path": str(speckit_repo / "docs" / "prd.md"),
        "home": str(fake_home),
    }

    # Clarify decisions are filed as standalone assumption-ledger entries
    # in the user's checkout (never the workspace) — stub the bd calls
    # `record_standalone_assumption` makes so this test never needs a
    # real `bd` install (T026).
    created_beads: list[str] = []

    async def fake_query(self: BeadClient, expr: str) -> list[BeadSummary]:
        return []  # no existing epics/entries to dedup against

    async def fake_create_bead(
        self: BeadClient, definition: object, parent_id: str | None = None
    ) -> object:
        bd_id = f"dea-{len(created_beads) + 1}"
        created_beads.append(bd_id)
        return type("CreatedBead", (), {"bd_id": bd_id})()

    async def fake_set_state(
        self: BeadClient, bead_id: str, state: dict[str, str], reason: str = ""
    ) -> None:
        return None

    with (
        patch.object(BeadClient, "query", new=fake_query),
        patch.object(BeadClient, "create_bead", new=fake_create_bead),
        patch.object(BeadClient, "set_state", new=fake_set_state),
        patch("maverick.library.actions.beads.defer_bead", new=AsyncMock()),
    ):
        events = [event async for event in workflow.execute(inputs)]

    assert workflow.result is not None
    assert workflow.result.success is True, [e for e in events if hasattr(e, "error")]

    # Exactly one runtime constructed (one squadron, one chain agent).
    assert len(constructed) == 1
    runtime = constructed[0]

    # Strict ordering: five step-completed events for the chain steps
    # (plus "prepare"), all successful, in the exact chain order.
    step_completed_names = [
        e.step_name
        for e in events
        if type(e).__name__ == "StepCompleted" and e.success and e.step_name != "prepare"
    ]
    assert step_completed_names == [s.value for s in ChainStep]

    step_failed_names = [
        e.step_name for e in events if type(e).__name__ == "StepCompleted" and not e.success
    ]
    assert step_failed_names == []

    # No interactive input was ever requested — the runtime stub has no
    # input-request surface at all; every call is a plain execute().
    assert len(runtime.execute_calls) == 5
    for call in runtime.execute_calls:
        assert call["schema"] is not None  # structured-output path only

    # Final chain state: completed, feature_dir resolved, every step
    # succeeded and landed.
    final_state = await load_chain_state(run_id, speckit_repo)
    assert final_state is not None
    assert final_state.status == "completed"
    assert final_state.feature_dir == f"specs/{FEATURE_DIR}"
    for step in ChainStep:
        record = final_state.steps[step]
        assert record.status == "succeeded", f"{step} did not succeed: {record.error}"
        assert record.landed is True

    # Artifacts landed in the checkout as ordinary markdown.
    feature_path = speckit_repo / "specs" / FEATURE_DIR
    assert (feature_path / "spec.md").is_file()
    assert (feature_path / "plan.md").is_file()
    assert (feature_path / "tasks.md").is_file()

    # FR-011: spec/plan/tasks content is byte-identical before and after
    # analyze — the stub never writes to those files during the analyze
    # step, so the landed content must match exactly what specify/plan/
    # tasks wrote.
    for name, content in runtime.written_content.items():
        assert (feature_path / name).read_text(encoding="utf-8") == content

    report = workflow.result.final_output
    assert report["status"] == "completed"
    assert report["feature_dir"] == f"specs/{FEATURE_DIR}"
    assert report["resume_hint"] is None

    # T026: the clarify decision recorded in spec.md's "## Clarifications"
    # section was filed as a standalone ledger entry — one bd created, and
    # the chain state + report both reflect it.
    assert len(final_state.clarify_decisions) == 1
    decision = final_state.clarify_decisions[0]
    assert decision.question == "Should exports include archived widgets?"
    assert decision.adopted_answer == "No, exclude archived widgets."
    assert decision.path == "non_interactive"
    assert decision.ledger_bead_id is not None
    assert report["ledger_entry_count"] == 1

    # T035: the analyze finding became a standalone remediation bead.
    assert report["remediation_bead_count"] == 1
    assert len(final_state.remediation_bead_ids) == 1

    # Two beads total were created: the clarify ledger entry + the
    # remediation bead.
    assert len(created_beads) == 2
    assert decision.ledger_bead_id in created_beads
    assert final_state.remediation_bead_ids[0] in created_beads


def test_prd_digest_is_sha256_of_content(speckit_repo: Path) -> None:
    prd_path = speckit_repo / "docs" / "prd.md"
    content = prd_path.read_text(encoding="utf-8")
    assert hashlib.sha256(content.encode("utf-8")).hexdigest()
