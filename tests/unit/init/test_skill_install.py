"""Unit tests for the packaged ``maverick-review`` skill install/uninstall.

Covers the ``maverick init`` install step (``_install_review_skill`` in
:mod:`maverick.init`) and the ``maverick uninstall`` removal path
(:mod:`maverick.cli.commands.uninstall`), plus a shape-only assertion on
the packaged ``src/maverick/skills/review_console/SKILL.md`` frontmatter
(content is authored by a separate task; we only assert the frontmatter
contract, not exact prose).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.init import (
    InitPreflightResult,
    PreflightStatus,
    PrerequisiteCheck,
    ProjectType,
    run_init,
)
from maverick.main import cli

_SKILL_RELATIVE_PATH = Path(".claude") / "skills" / "maverick-review" / "SKILL.md"
_PACKAGED_SKILL_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "maverick"
    / "skills"
    / "review_console"
    / "SKILL.md"
)


def _packaged_skill_content() -> str:
    """Read the packaged SKILL.md source shipped with maverick."""
    return _PACKAGED_SKILL_PATH.read_text(encoding="utf-8")


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Minimal YAML-frontmatter parser for simple ``key: value`` pairs.

    Deliberately naive (no real YAML parser) — the packaged SKILL.md is
    authored by a sibling task, so this only needs to confirm the
    frontmatter *shape* (delimiters + flat key/value lines), not parse
    arbitrary YAML.
    """
    assert text.startswith("---\n"), "SKILL.md must start with a '---' frontmatter fence"
    end = text.index("\n---", 4)
    block = text[4:end]
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


# ---------------------------------------------------------------------------
# Packaged source shape
# ---------------------------------------------------------------------------


class TestPackagedSkillFrontmatter:
    def test_packaged_skill_file_exists(self) -> None:
        assert _PACKAGED_SKILL_PATH.is_file(), (
            f"Expected packaged skill at {_PACKAGED_SKILL_PATH} — "
            "if this fails because the sibling authoring task hasn't landed "
            "yet, re-run once it has."
        )

    def test_frontmatter_has_expected_name(self) -> None:
        fields = _parse_frontmatter(_packaged_skill_content())
        assert fields.get("name") == "maverick-review"

    def test_frontmatter_has_nonempty_description(self) -> None:
        fields = _parse_frontmatter(_packaged_skill_content())
        assert fields.get("description")

    def test_frontmatter_has_invocability_marker(self) -> None:
        """Skills invocable via a slash command in this repo's own
        ``.claude/skills/*/SKILL.md`` files carry a ``user-invocable``
        frontmatter key (see e.g. ``.claude/skills/speckit-clarify/SKILL.md``).
        Assert the packaged skill declares itself invocable the same way,
        without hardcoding any of its prose.
        """
        fields = _parse_frontmatter(_packaged_skill_content())
        assert "user-invocable" in fields
        assert fields["user-invocable"].lower() == "true"


# ---------------------------------------------------------------------------
# maverick init — install step
# ---------------------------------------------------------------------------


class TestInstallReviewSkillHelper:
    async def test_fresh_install_writes_packaged_content(self, tmp_path: Path) -> None:
        from maverick.init import _install_review_skill

        result = await _install_review_skill(tmp_path, verbose=False)

        assert result is True
        installed_path = tmp_path / _SKILL_RELATIVE_PATH
        assert installed_path.is_file()
        assert installed_path.read_text(encoding="utf-8") == _packaged_skill_content()

    async def test_locally_modified_file_is_overwritten(self, tmp_path: Path) -> None:
        from maverick.init import _install_review_skill

        installed_path = tmp_path / _SKILL_RELATIVE_PATH
        installed_path.parent.mkdir(parents=True)
        installed_path.write_text("--- locally hacked content ---", encoding="utf-8")

        result = await _install_review_skill(tmp_path, verbose=False)

        assert result is True
        assert installed_path.read_text(encoding="utf-8") == _packaged_skill_content()

    async def test_write_failure_is_non_fatal_and_returns_false(self, tmp_path: Path) -> None:
        from maverick.init import _install_review_skill

        # The install goes through `atomic_write_text` (so an interrupted
        # init can't leave a truncated SKILL.md), hence patching that rather
        # than `Path.write_text`.
        with patch(
            "maverick.utils.atomic.atomic_write_text",
            side_effect=OSError("permission denied"),
        ):
            result = await _install_review_skill(tmp_path, verbose=False)

        assert result is False
        assert not (tmp_path / ".claude" / "skills" / "maverick-review" / "SKILL.md").exists()
        # No exception propagated — best-effort, matches _ensure_gitignore_entries.


class TestRunInitWiresSkillInstall:
    """Exercise ``run_init`` end-to-end (mocking only the heavy externals:
    prerequisite checks and bd) to confirm both return branches thread
    ``_install_review_skill``'s outcome into ``InitResult.skill_installed``.
    """

    @pytest.fixture
    def preflight_ok(self) -> InitPreflightResult:
        return InitPreflightResult(
            success=True,
            checks=(
                PrerequisiteCheck(
                    name="git_installed",
                    display_name="Git",
                    status=PreflightStatus.PASS,
                    message="Git installed",
                ),
            ),
            total_duration_ms=10,
        )

    async def test_fresh_init_installs_skill(
        self,
        tmp_path: Path,
        preflight_ok: InitPreflightResult,
    ) -> None:
        with (
            patch(
                "maverick.init.verify_prerequisites",
                new=AsyncMock(return_value=preflight_ok),
            ),
            patch(
                "maverick.init._init_beads",
                new=AsyncMock(return_value=True),
            ),
        ):
            result = await run_init(
                project_path=tmp_path,
                type_override=ProjectType.PYTHON,
            )

        assert result.success is True
        assert result.skill_installed is True
        installed_path = tmp_path / _SKILL_RELATIVE_PATH
        assert installed_path.is_file()
        assert installed_path.read_text(encoding="utf-8") == _packaged_skill_content()

    async def test_config_existed_branch_still_installs_skill(
        self,
        tmp_path: Path,
        preflight_ok: InitPreflightResult,
    ) -> None:
        (tmp_path / "maverick.yaml").write_text("# existing config\n", encoding="utf-8")

        with (
            patch(
                "maverick.init.verify_prerequisites",
                new=AsyncMock(return_value=preflight_ok),
            ),
            patch(
                "maverick.init._init_beads",
                new=AsyncMock(return_value=True),
            ),
        ):
            result = await run_init(project_path=tmp_path)

        assert result.success is True
        assert result.config_existed is True
        assert result.skill_installed is True
        installed_path = tmp_path / _SKILL_RELATIVE_PATH
        assert installed_path.is_file()
        assert installed_path.read_text(encoding="utf-8") == _packaged_skill_content()

    async def test_skill_install_failure_is_non_fatal(
        self,
        tmp_path: Path,
        preflight_ok: InitPreflightResult,
    ) -> None:
        with (
            patch(
                "maverick.init.verify_prerequisites",
                new=AsyncMock(return_value=preflight_ok),
            ),
            patch(
                "maverick.init._init_beads",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "maverick.init._install_review_skill",
                new=AsyncMock(return_value=False),
            ),
        ):
            result = await run_init(
                project_path=tmp_path,
                type_override=ProjectType.PYTHON,
            )

        assert result.success is True
        assert result.skill_installed is False


# ---------------------------------------------------------------------------
# maverick uninstall — removal step
# ---------------------------------------------------------------------------


class TestUninstallRemovesSkill:
    def test_dry_run_lists_skill_file_without_removing(self, cli_runner, tmp_path: Path) -> None:
        skill_path = tmp_path / _SKILL_RELATIVE_PATH
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text("content", encoding="utf-8")
        (tmp_path / "maverick.yaml").write_text("# config\n", encoding="utf-8")

        import os

        cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = cli_runner.invoke(cli, ["uninstall", "--dry-run"])
        finally:
            os.chdir(cwd)

        assert result.exit_code == 0, result.output
        assert "maverick-review" in result.output or str(skill_path) in result.output
        # Dry run must not touch the filesystem.
        assert skill_path.is_file()

    def test_real_uninstall_removes_skill_file_and_empty_dirs(
        self, cli_runner, tmp_path: Path
    ) -> None:
        skill_dir = tmp_path / ".claude" / "skills" / "maverick-review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("content", encoding="utf-8")
        (tmp_path / "maverick.yaml").write_text("# config\n", encoding="utf-8")

        import os

        cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = cli_runner.invoke(cli, ["uninstall", "--force"])
        finally:
            os.chdir(cwd)

        assert result.exit_code == 0, result.output
        assert not (skill_dir / "SKILL.md").exists()
        assert not skill_dir.exists()
        # .claude/skills/ removed too since it's now empty.
        assert not (tmp_path / ".claude" / "skills").exists()
        # .claude/ itself must never be removed.
        assert (tmp_path / ".claude").exists()

    def test_uninstall_preserves_other_skill_dirs(self, cli_runner, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".claude" / "skills" / "maverick-review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("content", encoding="utf-8")

        other_skill_dir = tmp_path / ".claude" / "skills" / "some-other-skill"
        other_skill_dir.mkdir(parents=True)
        (other_skill_dir / "SKILL.md").write_text("other content", encoding="utf-8")

        (tmp_path / "maverick.yaml").write_text("# config\n", encoding="utf-8")

        import os

        cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = cli_runner.invoke(cli, ["uninstall", "--force"])
        finally:
            os.chdir(cwd)

        assert result.exit_code == 0, result.output
        assert not skill_dir.exists()
        # Other skill dirs untouched, and .claude/skills/ survives because
        # it's non-empty.
        assert other_skill_dir.exists()
        assert (tmp_path / ".claude" / "skills").exists()


class TestSkillPathIsSharedNotDuplicated:
    """Install and removal must resolve the same location.

    They used to each own a literal copy of the path; changing one would
    silently strand a Maverick-owned skill in every uninstalled project.
    """

    def test_init_and_uninstall_use_the_same_constant(self) -> None:
        from maverick.cli.commands import uninstall as uninstall_mod
        from maverick.init import _REVIEW_SKILL_RELATIVE_PATH
        from maverick.skills import REVIEW_SKILL_RELATIVE_PATH

        assert _REVIEW_SKILL_RELATIVE_PATH is REVIEW_SKILL_RELATIVE_PATH
        assert uninstall_mod.REVIEW_SKILL_RELATIVE_PATH is REVIEW_SKILL_RELATIVE_PATH

    async def test_installed_file_is_the_one_uninstall_removes(self, tmp_path: Path) -> None:
        from maverick.cli.commands.uninstall import _remove_review_skill
        from maverick.init import _install_review_skill
        from maverick.skills import REVIEW_SKILL_RELATIVE_PATH

        assert await _install_review_skill(tmp_path, verbose=False) is True
        target = tmp_path / REVIEW_SKILL_RELATIVE_PATH
        assert target.is_file()

        assert _remove_review_skill(target, verbose=False) is True
        assert not target.exists()
