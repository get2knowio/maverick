"""Unit tests for maverick.agents.briefing.prompts."""

from __future__ import annotations

from maverick.agents.briefing.prompts import (
    build_briefing_prompt,
    build_contrarian_prompt,
)
from maverick.briefing.models import (
    NavigatorBrief,
    ReconBrief,
    StructuralistBrief,
)
from maverick.library.actions.decompose import CodebaseContext, FileContent


def _make_navigator() -> NavigatorBrief:
    return NavigatorBrief(
        architecture_decisions=(),
        module_structure="src/",
        integration_points=(),
        summary="Nav summary",
    )


def _make_structuralist() -> StructuralistBrief:
    return StructuralistBrief(entities=(), interfaces=(), summary="Struct summary")


def _make_recon() -> ReconBrief:
    return ReconBrief(
        risks=(),
        ambiguities=(),
        testing_strategy="Unit tests",
        summary="Recon summary",
    )


class TestBuildBriefingPrompt:
    def test_includes_flight_plan(self) -> None:
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)
        result = build_briefing_prompt("## Objective\nBuild auth.", ctx)
        assert "## Objective" in result
        assert "Build auth." in result

    def test_includes_codebase_context(self) -> None:
        ctx = CodebaseContext(
            files=(FileContent(path="src/main.py", content="print('hi')"),),
            missing_files=(),
            total_size=11,
        )
        result = build_briefing_prompt("plan", ctx)
        assert "src/main.py" in result
        assert "print('hi')" in result

    def test_has_flight_plan_section(self) -> None:
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)
        result = build_briefing_prompt("content", ctx)
        assert "## Flight Plan" in result

    def test_has_codebase_context_section(self) -> None:
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)
        result = build_briefing_prompt("content", ctx)
        assert "## Codebase Context" in result

    def test_returns_string(self) -> None:
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)
        result = build_briefing_prompt("content", ctx)
        assert isinstance(result, str)


class TestBuildContrarianPrompt:
    def test_includes_flight_plan(self) -> None:
        result = build_contrarian_prompt(
            "The Plan", _make_navigator(), _make_structuralist(), _make_recon()
        )
        assert "The Plan" in result

    def test_includes_navigator_brief(self) -> None:
        result = build_contrarian_prompt(
            "plan", _make_navigator(), _make_structuralist(), _make_recon()
        )
        assert "## Navigator Brief" in result
        assert "Nav summary" in result

    def test_includes_structuralist_brief(self) -> None:
        result = build_contrarian_prompt(
            "plan", _make_navigator(), _make_structuralist(), _make_recon()
        )
        assert "## Structuralist Brief" in result

    def test_includes_recon_brief(self) -> None:
        result = build_contrarian_prompt(
            "plan", _make_navigator(), _make_structuralist(), _make_recon()
        )
        assert "## Recon Brief" in result

    def test_briefs_as_json(self) -> None:
        result = build_contrarian_prompt(
            "plan", _make_navigator(), _make_structuralist(), _make_recon()
        )
        assert "```json" in result

    def test_returns_string(self) -> None:
        result = build_contrarian_prompt(
            "plan", _make_navigator(), _make_structuralist(), _make_recon()
        )
        assert isinstance(result, str)
