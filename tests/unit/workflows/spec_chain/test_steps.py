"""Tests for per-step prompt builders (`maverick.workflows.spec_chain.steps`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.workflows.spec_chain.constants import ChainStep
from maverick.workflows.spec_chain.steps import (
    SLASH_COMMANDS,
    build_step_prompt,
    read_command_body,
)


class TestSlashCommands:
    @pytest.mark.parametrize(
        ("step", "command"),
        [
            (ChainStep.SPECIFY, "/speckit.specify"),
            (ChainStep.CLARIFY, "/speckit.clarify"),
            (ChainStep.PLAN, "/speckit.plan"),
            (ChainStep.TASKS, "/speckit.tasks"),
            (ChainStep.ANALYZE, "/speckit.analyze"),
        ],
    )
    def test_slash_command_per_step(self, step: ChainStep, command: str) -> None:
        assert SLASH_COMMANDS[step] == command

    def test_every_chain_step_has_a_command(self) -> None:
        assert set(SLASH_COMMANDS) == set(ChainStep)


class TestReadCommandBody:
    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        assert read_command_body(tmp_path, ChainStep.SPECIFY) is None

    def test_reads_command_file_body(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "speckit.specify.md").write_text(
            "Do the specify thing.\n", encoding="utf-8"
        )
        body = read_command_body(tmp_path, ChainStep.SPECIFY)
        assert body == "Do the specify thing.\n"

    def test_reads_correct_file_per_step(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "speckit.clarify.md").write_text("clarify body", encoding="utf-8")
        (commands_dir / "speckit.plan.md").write_text("plan body", encoding="utf-8")

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
        assert "/speckit.specify" in prompt
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

    def test_prompt_inlines_command_body_when_present(self, tmp_path: Path) -> None:
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "speckit.plan.md").write_text(
            "UNIQUE PLAN COMMAND BODY MARKER", encoding="utf-8"
        )
        prompt = build_step_prompt(ChainStep.PLAN, workspace=tmp_path, feature="widget-export")
        assert "UNIQUE PLAN COMMAND BODY MARKER" in prompt
        assert "own definition from this repository" in prompt

    def test_prompt_mentions_feature_for_every_step(self, tmp_path: Path) -> None:
        for step in ChainStep:
            prompt = build_step_prompt(step, workspace=tmp_path, feature="my-feature")
            assert "my-feature" in prompt
