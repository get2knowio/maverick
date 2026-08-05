"""Tests for per-step prompt builders (`maverick.workflows.spec_chain.steps`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.workflows.spec_chain.constants import ChainStep
from maverick.workflows.spec_chain.steps import (
    SLASH_COMMANDS,
    build_step_prompt,
    read_command_body,
    resolve_command,
)


def _write_skill(root: Path, step: ChainStep, body: str) -> None:
    """Install a Spec Kit >= 0.14 skill definition for *step*."""
    skill_dir = root / ".claude" / "skills" / f"speckit-{step.value}"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")


def _write_command(root: Path, step: ChainStep, body: str) -> None:
    """Install a pre-0.14 command definition for *step*."""
    commands_dir = root / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    (commands_dir / f"speckit.{step.value}.md").write_text(body, encoding="utf-8")


class TestSlashCommands:
    @pytest.mark.parametrize(
        ("step", "command"),
        [
            (ChainStep.SPECIFY, "/speckit-specify"),
            (ChainStep.CLARIFY, "/speckit-clarify"),
            (ChainStep.PLAN, "/speckit-plan"),
            (ChainStep.TASKS, "/speckit-tasks"),
            (ChainStep.ANALYZE, "/speckit-analyze"),
        ],
    )
    def test_slash_command_per_step(self, step: ChainStep, command: str) -> None:
        assert SLASH_COMMANDS[step] == command

    def test_every_chain_step_has_a_command(self) -> None:
        assert set(SLASH_COMMANDS) == set(ChainStep)


class TestResolveCommand:
    def test_defaults_to_skill_form_when_workspace_is_bare(self, tmp_path: Path) -> None:
        command, body = resolve_command(tmp_path, ChainStep.SPECIFY)
        assert command == "/speckit-specify"
        assert body is None

    def test_resolves_skill_surface(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, ChainStep.PLAN, "SKILL BODY")
        assert resolve_command(tmp_path, ChainStep.PLAN) == ("/speckit-plan", "SKILL BODY")

    def test_resolves_legacy_command_surface(self, tmp_path: Path) -> None:
        _write_command(tmp_path, ChainStep.PLAN, "COMMAND BODY")
        assert resolve_command(tmp_path, ChainStep.PLAN) == ("/speckit.plan", "COMMAND BODY")

    def test_skill_wins_when_both_surfaces_present(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, ChainStep.TASKS, "SKILL BODY")
        _write_command(tmp_path, ChainStep.TASKS, "STALE COMMAND BODY")
        command, body = resolve_command(tmp_path, ChainStep.TASKS)
        assert command == "/speckit-tasks"
        assert body == "SKILL BODY"

    def test_resolves_per_step_independently(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, ChainStep.CLARIFY, "clarify skill")
        _write_command(tmp_path, ChainStep.PLAN, "plan command")

        assert resolve_command(tmp_path, ChainStep.CLARIFY) == (
            "/speckit-clarify",
            "clarify skill",
        )
        assert resolve_command(tmp_path, ChainStep.PLAN) == ("/speckit.plan", "plan command")
        assert resolve_command(tmp_path, ChainStep.TASKS) == ("/speckit-tasks", None)


class TestReadCommandBody:
    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        assert read_command_body(tmp_path, ChainStep.SPECIFY) is None

    def test_reads_skill_file_body(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, ChainStep.SPECIFY, "Do the specify thing.\n")
        assert read_command_body(tmp_path, ChainStep.SPECIFY) == "Do the specify thing.\n"

    def test_reads_legacy_command_file_body(self, tmp_path: Path) -> None:
        _write_command(tmp_path, ChainStep.SPECIFY, "Do the specify thing.\n")
        assert read_command_body(tmp_path, ChainStep.SPECIFY) == "Do the specify thing.\n"

    def test_reads_correct_file_per_step(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, ChainStep.CLARIFY, "clarify body")
        _write_skill(tmp_path, ChainStep.PLAN, "plan body")

        assert read_command_body(tmp_path, ChainStep.CLARIFY) == "clarify body"
        assert read_command_body(tmp_path, ChainStep.PLAN) == "plan body"
        assert read_command_body(tmp_path, ChainStep.TASKS) is None


class TestBuildStepPrompt:
    def test_specify_prompt_includes_slash_command_and_feature(self, tmp_path: Path) -> None:
        prompt = build_step_prompt(
            ChainStep.SPECIFY,
            workspace=tmp_path,
            feature="widget-export",
            prd_content="Build widget export.",
        )
        assert "/speckit-specify" in prompt
        assert "widget-export" in prompt

    def test_specify_prompt_injects_prd_content(self, tmp_path: Path) -> None:
        prompt = build_step_prompt(
            ChainStep.SPECIFY,
            workspace=tmp_path,
            feature="widget-export",
            prd_content="UNIQUE PRD MARKER TEXT",
        )
        assert "UNIQUE PRD MARKER TEXT" in prompt

    @pytest.mark.parametrize(
        "step", [ChainStep.CLARIFY, ChainStep.PLAN, ChainStep.TASKS, ChainStep.ANALYZE]
    )
    def test_non_specify_prompts_ignore_prd_content(self, tmp_path: Path, step: ChainStep) -> None:
        prompt = build_step_prompt(
            step,
            workspace=tmp_path,
            feature="widget-export",
            prd_content="UNIQUE PRD MARKER TEXT",
        )
        assert "UNIQUE PRD MARKER TEXT" not in prompt
        assert SLASH_COMMANDS[step] in prompt

    def test_prompt_includes_structured_report_instruction(self, tmp_path: Path) -> None:
        prompt = build_step_prompt(ChainStep.PLAN, workspace=tmp_path, feature="widget-export")
        assert "StructuredOutput" in prompt

    def test_prompt_has_no_inline_fallback_when_command_file_absent(self, tmp_path: Path) -> None:
        prompt = build_step_prompt(ChainStep.PLAN, workspace=tmp_path, feature="widget-export")
        assert "own definition from this repository" not in prompt

    def test_prompt_inlines_skill_body_when_present(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, ChainStep.PLAN, "UNIQUE PLAN SKILL BODY MARKER")
        prompt = build_step_prompt(ChainStep.PLAN, workspace=tmp_path, feature="widget-export")
        assert "UNIQUE PLAN SKILL BODY MARKER" in prompt
        assert "own definition from this repository" in prompt

    def test_prompt_inlines_legacy_command_body_when_present(self, tmp_path: Path) -> None:
        _write_command(tmp_path, ChainStep.PLAN, "UNIQUE PLAN COMMAND BODY MARKER")
        prompt = build_step_prompt(ChainStep.PLAN, workspace=tmp_path, feature="widget-export")
        assert "UNIQUE PLAN COMMAND BODY MARKER" in prompt
        assert "/speckit.plan" in prompt

    def test_prompt_mentions_feature_for_every_step(self, tmp_path: Path) -> None:
        for step in ChainStep:
            prompt = build_step_prompt(step, workspace=tmp_path, feature="my-feature")
            assert "my-feature" in prompt
