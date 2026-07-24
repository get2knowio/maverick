"""Shared fixtures/helpers for spec-chain integration tests.

Builds a real tmp jj+git colocated repo with the Spec Kit command/marker
surface `SpecChainWorkflow` expects, plus a configurable stubbed airframe
runtime — no live model calls, no real `bd` install required.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
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

pytestmark = pytest.mark.integration

FEATURE = "widget-export"
FEATURE_DIR = f"001-{FEATURE}"

COMMAND_STEPS = (
    ChainStep.SPECIFY,
    ChainStep.CLARIFY,
    ChainStep.PLAN,
    ChainStep.TASKS,
    ChainStep.ANALYZE,
)

#: Artifact each step writes by default (mirrors landing.py's expected set).
_DEFAULT_ARTIFACT = {
    ChainStep.SPECIFY: "spec.md",
    ChainStep.PLAN: "plan.md",
    ChainStep.TASKS: "tasks.md",
}


def _run(cmd: list[str], *, cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def build_speckit_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], cwd=repo)
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _run(["git", "config", "user.name", "Test"], cwd=repo)
    _run(["jj", "git", "init", "--colocate"], cwd=repo)

    commands_dir = repo / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    for step in COMMAND_STEPS:
        (commands_dir / f"speckit.{step.value}.md").write_text(
            f"Instructions for /speckit.{step.value}.\n", encoding="utf-8"
        )

    specify_dir = repo / ".specify"
    specify_dir.mkdir()
    (specify_dir / "init-options.json").write_text(
        '{"speckit_version": "0.14.0"}', encoding="utf-8"
    )

    docs_dir = repo / "docs"
    docs_dir.mkdir()
    (docs_dir / "prd.md").write_text(
        "# Widget Export PRD\n\nExport widgets to CSV.\n", encoding="utf-8"
    )

    _run(["jj", "commit", "-m", "initial speckit repo"], cwd=repo)
    return repo


def make_cost() -> CostRecord:
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


#: A step handler receives (feature_path, runtime) and returns the
#: structured StepReport-shaped payload. Override via `step_handlers` to
#: simulate a failure/blocked step for halt/resume tests.
StepHandler = Callable[[Path, "ConfigurableSpeckitRuntime"], dict[str, Any]]


class ConfigurableSpeckitRuntime:
    """Stand-in airframe runtime with per-step overridable behavior."""

    label = "stub"

    def __init__(
        self,
        *,
        model: str | None = None,
        step_handlers: dict[ChainStep, StepHandler] | None = None,
        **kwargs: Any,
    ) -> None:
        self.model = model
        self.execute_calls: list[dict[str, Any]] = []
        self.written_content: dict[str, str] = {}
        self._step_handlers = step_handlers or {}

    async def execute(self, prompt: str, **kwargs: Any) -> RuntimeResult:
        self.execute_calls.append({"prompt": prompt, **kwargs})
        step = self._infer_step(prompt)
        feature_path = Path.cwd() / "specs" / FEATURE_DIR
        feature_path.mkdir(parents=True, exist_ok=True)

        handler = self._step_handlers.get(step)
        structured = handler(feature_path, self) if handler else self._default(step, feature_path)
        return RuntimeResult(text="", structured=structured, cost=make_cost(), finish="end_turn")

    def _default(self, step: ChainStep, feature_path: Path) -> dict[str, Any]:
        if step is ChainStep.CLARIFY:
            spec_path = feature_path / "spec.md"
            existing = spec_path.read_text(encoding="utf-8") if spec_path.is_file() else ""
            updated = existing + (
                "\n## Clarifications\n\n### Session 2026-07-24\n\n"
                "- Q: Should exports include archived widgets? "
                "→ A: No, exclude archived widgets.\n"
            )
            spec_path.write_text(updated, encoding="utf-8")
            self.written_content["spec.md"] = updated
            return {
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
                "detail": "Clarify complete.",
            }
        if step is ChainStep.ANALYZE:
            return {
                "status": "completed",
                "artifacts": [],
                "questions": [],
                "findings": [],
                "detail": "Analyze complete.",
            }
        name = _DEFAULT_ARTIFACT[step]
        content = f"# {step.value.title()}\n\nContent for {step.value}.\n"
        (feature_path / name).write_text(content, encoding="utf-8")
        self.written_content[name] = content
        return {
            "status": "completed",
            "artifacts": [name],
            "questions": [],
            "findings": [],
            "detail": f"{step.value} written.",
        }

    @staticmethod
    def _infer_step(prompt: str) -> ChainStep:
        for step in COMMAND_STEPS:
            if f"/speckit.{step.value}" in prompt:
                return step
        raise AssertionError(f"could not infer step from prompt: {prompt!r}")

    async def reset(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def validate_binding(self, _binding: Any) -> bool:
        return True


def stub_runtime_factory(
    monkeypatch: pytest.MonkeyPatch,
    *,
    step_handlers: dict[ChainStep, StepHandler] | None = None,
) -> list[ConfigurableSpeckitRuntime]:
    """Patch `airframe.runtime_for`; returns the constructed-instances list."""
    constructed: list[ConfigurableSpeckitRuntime] = []

    def _factory(provider_id: str) -> type[ConfigurableSpeckitRuntime]:
        class _Bound(ConfigurableSpeckitRuntime):
            def __init__(self, *, model: str | None = None, **kwargs: Any) -> None:
                super().__init__(model=model, step_handlers=step_handlers, **kwargs)
                constructed.append(self)

        return _Bound

    monkeypatch.setattr("airframe.runtime_for", _factory)
    return constructed


def make_config() -> MaverickConfig:
    return MaverickConfig(
        agents=AgentsConfig(generate=AgentBindingConfig(provider="claude", model_id="stub-model"))
    )


@pytest.fixture
def speckit_repo(tmp_path: Path) -> Path:
    return build_speckit_repo(tmp_path)


@pytest.fixture
def fake_home(tmp_path: Path) -> Path:
    home = tmp_path / "fake-home"
    home.mkdir()
    return home


@pytest.fixture
def bd_stubs() -> Any:
    """Patch bd calls so `record_standalone_assumption` needs no real
    `bd` install. Yields the list of created bead ids."""
    created: list[str] = []

    async def fake_query(self: BeadClient, expr: str) -> list[BeadSummary]:
        return []

    async def fake_create_bead(
        self: BeadClient, definition: object, parent_id: str | None = None
    ) -> object:
        bd_id = f"dea-{len(created) + 1}"
        created.append(bd_id)
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
        yield created
