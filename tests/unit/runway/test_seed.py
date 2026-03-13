"""Tests for maverick.runway.seed."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.runway.seed import (
    SeedContext,
    SeedFileEntry,
    SeedOutput,
    SeedResult,
    gather_seed_context,
    run_seed,
)

# ---------------------------------------------------------------------------
# SeedResult
# ---------------------------------------------------------------------------


class TestSeedResult:
    def test_to_dict_success(self) -> None:
        result = SeedResult(
            success=True,
            files_written=("architecture.md", "conventions.md"),
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["files_written"] == ["architecture.md", "conventions.md"]
        assert "error" not in d

    def test_to_dict_with_error(self) -> None:
        result = SeedResult(success=False, error="provider timeout")
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "provider timeout"

    def test_frozen(self) -> None:
        result = SeedResult(success=True)
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SeedOutput models
# ---------------------------------------------------------------------------


class TestSeedOutputModels:
    def test_seed_file_entry(self) -> None:
        entry = SeedFileEntry(filename="architecture.md", content="# Architecture")
        assert entry.filename == "architecture.md"
        assert entry.content == "# Architecture"

    def test_seed_output(self) -> None:
        output = SeedOutput(
            files=[
                SeedFileEntry(filename="a.md", content="content a"),
                SeedFileEntry(filename="b.md", content="content b"),
            ]
        )
        assert len(output.files) == 2
        assert output.files[0].filename == "a.md"

    def test_seed_output_frozen(self) -> None:
        output = SeedOutput(files=[])
        with pytest.raises(Exception):
            output.files = []  # type: ignore[misc]


# ---------------------------------------------------------------------------
# gather_seed_context
# ---------------------------------------------------------------------------


class TestGatherSeedContext:
    @pytest.mark.asyncio
    async def test_gathers_directory_tree(self, tmp_path: Path) -> None:
        """Directory tree should include files and subdirectories."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_main.py").write_text("def test(): pass")

        context = await gather_seed_context(tmp_path)

        assert "src/" in context.directory_tree
        assert "main.py" in context.directory_tree
        assert "tests/" in context.directory_tree

    @pytest.mark.asyncio
    async def test_excludes_ignored_dirs(self, tmp_path: Path) -> None:
        """Excluded directories like .git, node_modules should be skipped."""
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("gitconfig")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg").mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("")

        context = await gather_seed_context(tmp_path)

        assert ".git/" not in context.directory_tree
        assert "node_modules/" not in context.directory_tree
        assert "src/" in context.directory_tree

    @pytest.mark.asyncio
    async def test_reads_config_files(self, tmp_path: Path) -> None:
        """Well-known config files should be read."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")
        (tmp_path / "README.md").write_text("# My Project")

        context = await gather_seed_context(tmp_path)

        assert "pyproject.toml" in context.config_files
        assert "README.md" in context.config_files
        assert "[project]" in context.config_files["pyproject.toml"]

    @pytest.mark.asyncio
    async def test_truncates_large_config_files(self, tmp_path: Path) -> None:
        """Config files exceeding 3000 chars should be truncated."""
        large_content = "x" * 5000
        (tmp_path / "pyproject.toml").write_text(large_content)

        context = await gather_seed_context(tmp_path)

        assert len(context.config_files["pyproject.toml"]) <= 3000

    @pytest.mark.asyncio
    async def test_counts_file_types(self, tmp_path: Path) -> None:
        """File type distribution should count by extension."""
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "c.ts").write_text("")

        context = await gather_seed_context(tmp_path)

        assert context.file_type_counts[".py"] == 2
        assert context.file_type_counts[".ts"] == 1

    @pytest.mark.asyncio
    async def test_handles_non_git_dir(self, tmp_path: Path) -> None:
        """Non-git directory should produce empty git log."""
        (tmp_path / "file.txt").write_text("hello")

        context = await gather_seed_context(tmp_path)

        assert context.git_log == ()

    @pytest.mark.asyncio
    async def test_git_log_with_repo(self, tmp_path: Path) -> None:
        """Git repo with commits should populate git_log."""

        @dataclass(frozen=True)
        class FakeCommit:
            sha: str = "abc1234567890"
            short_sha: str = "abc1234"
            message: str = "initial commit"
            author: str = "Test User"
            date: str = "2025-01-01"

        fake_commits = [FakeCommit()]

        with patch("maverick.runway.seed.AsyncGitRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.log = AsyncMock(return_value=fake_commits)
            mock_repo_cls.return_value = mock_repo

            context = await gather_seed_context(tmp_path)

        assert len(context.git_log) == 1
        assert context.git_log[0].message == "initial commit"


# ---------------------------------------------------------------------------
# RunwaySeedAgent
# ---------------------------------------------------------------------------


class TestRunwaySeedAgent:
    def test_agent_properties(self) -> None:
        from maverick.agents.seed import RunwaySeedAgent

        agent = RunwaySeedAgent()

        assert agent.name == "runway_seed"
        assert agent.allowed_tools == []
        assert agent._output_model is SeedOutput

    def test_build_prompt_includes_git_log(self) -> None:
        from maverick.agents.seed import RunwaySeedAgent

        @dataclass(frozen=True)
        class FakeCommit:
            sha: str = "abc1234567890"
            short_sha: str = "abc1234"
            message: str = "feat: add login"
            author: str = "Dev"
            date: str = "2025-01-01"

        agent = RunwaySeedAgent()
        context = SeedContext(git_log=(FakeCommit(),))  # type: ignore[arg-type]
        prompt = agent.build_prompt(context)

        assert "abc1234" in prompt
        assert "feat: add login" in prompt

    def test_build_prompt_includes_tree(self) -> None:
        from maverick.agents.seed import RunwaySeedAgent

        agent = RunwaySeedAgent()
        context = SeedContext(directory_tree="src/\n  main.py\ntests/")
        prompt = agent.build_prompt(context)

        assert "src/" in prompt
        assert "main.py" in prompt

    def test_build_prompt_includes_config_files(self) -> None:
        from maverick.agents.seed import RunwaySeedAgent

        agent = RunwaySeedAgent()
        context = SeedContext(config_files={"pyproject.toml": "[project]\nname='test'"})
        prompt = agent.build_prompt(context)

        assert "pyproject.toml" in prompt
        assert "[project]" in prompt

    def test_build_prompt_empty_context(self) -> None:
        from maverick.agents.seed import RunwaySeedAgent

        agent = RunwaySeedAgent()
        context = SeedContext()
        prompt = agent.build_prompt(context)

        assert "No git history available" in prompt

    def test_build_prompt_from_dict(self) -> None:
        from maverick.agents.seed import RunwaySeedAgent

        agent = RunwaySeedAgent()
        prompt = agent.build_prompt({"directory_tree": "src/\n  app.py"})

        assert "src/" in prompt
        assert "app.py" in prompt


# ---------------------------------------------------------------------------
# run_seed
# ---------------------------------------------------------------------------


def _mock_executor(
    seed_output: SeedOutput | None = None,
    success: bool = True,
    raise_error: Exception | None = None,
) -> MagicMock:
    """Create a mock executor that returns the given seed output."""
    mock = MagicMock()

    if raise_error:
        mock.execute = AsyncMock(side_effect=raise_error)
    else:
        result = MagicMock()
        result.success = success
        result.output = seed_output
        mock.execute = AsyncMock(return_value=result)

    mock.cleanup = AsyncMock()
    return mock


class TestRunSeed:
    @pytest.mark.asyncio
    async def test_writes_semantic_files(self, tmp_path: Path) -> None:
        """Successful seed should write semantic files to store."""
        seed_output = SeedOutput(
            files=[
                SeedFileEntry(filename="architecture.md", content="# Architecture"),
                SeedFileEntry(filename="conventions.md", content="# Conventions"),
            ]
        )
        mock_exec = _mock_executor(seed_output=seed_output)

        with patch("maverick.executor.create_default_executor", return_value=mock_exec):
            result = await run_seed(tmp_path)

        assert result.success
        assert "architecture.md" in result.files_written
        assert "conventions.md" in result.files_written

        # Verify files exist on disk
        semantic_dir = tmp_path / ".maverick" / "runway" / "semantic"
        assert (semantic_dir / "architecture.md").read_text() == "# Architecture"
        assert (semantic_dir / "conventions.md").read_text() == "# Conventions"

    @pytest.mark.asyncio
    async def test_auto_initializes_runway(self, tmp_path: Path) -> None:
        """If runway is not initialized, seed should auto-initialize it."""
        seed_output = SeedOutput(
            files=[SeedFileEntry(filename="tech.md", content="# Tech")]
        )
        mock_exec = _mock_executor(seed_output=seed_output)

        # No .maverick/runway directory exists
        assert not (tmp_path / ".maverick" / "runway").exists()

        with patch("maverick.executor.create_default_executor", return_value=mock_exec):
            result = await run_seed(tmp_path)

        assert result.success
        assert (tmp_path / ".maverick" / "runway").is_dir()

    @pytest.mark.asyncio
    async def test_skips_existing_without_force(self, tmp_path: Path) -> None:
        """Existing semantic files without --force should skip."""
        from maverick.runway.store import RunwayStore

        store = RunwayStore(tmp_path / ".maverick" / "runway")
        await store.initialize()
        await store.write_semantic_file("architecture.md", "existing")

        result = await run_seed(tmp_path, force=False)

        assert result.success
        assert result.files_written == ()
        assert "already exist" in (result.error or "")

    @pytest.mark.asyncio
    async def test_overwrites_with_force(self, tmp_path: Path) -> None:
        """Force flag should overwrite existing semantic files."""
        from maverick.runway.store import RunwayStore

        store = RunwayStore(tmp_path / ".maverick" / "runway")
        await store.initialize()
        await store.write_semantic_file("architecture.md", "old content")

        seed_output = SeedOutput(
            files=[
                SeedFileEntry(filename="architecture.md", content="# New Architecture")
            ]
        )
        mock_exec = _mock_executor(seed_output=seed_output)

        with patch("maverick.executor.create_default_executor", return_value=mock_exec):
            result = await run_seed(tmp_path, force=True)

        assert result.success
        assert "architecture.md" in result.files_written

        semantic_dir = tmp_path / ".maverick" / "runway" / "semantic"
        assert (semantic_dir / "architecture.md").read_text() == "# New Architecture"

    @pytest.mark.asyncio
    async def test_dry_run_no_writes(self, tmp_path: Path) -> None:
        """Dry run should return file list but not write anything."""
        seed_output = SeedOutput(
            files=[
                SeedFileEntry(filename="architecture.md", content="# Arch"),
                SeedFileEntry(filename="conventions.md", content="# Conv"),
            ]
        )
        mock_exec = _mock_executor(seed_output=seed_output)

        with patch("maverick.executor.create_default_executor", return_value=mock_exec):
            result = await run_seed(tmp_path, dry_run=True)

        assert result.success
        assert "architecture.md" in result.files_written

        # Files should NOT be written in dry run — but runway was auto-initialized
        # so the semantic dir exists, but the file shouldn't
        semantic_dir = tmp_path / ".maverick" / "runway" / "semantic"
        assert not (semantic_dir / "architecture.md").exists()

    @pytest.mark.asyncio
    async def test_executor_error_returns_gracefully(self, tmp_path: Path) -> None:
        """Executor errors should not crash, return SeedResult with error."""
        mock_exec = _mock_executor(raise_error=RuntimeError("connection refused"))

        with patch("maverick.executor.create_default_executor", return_value=mock_exec):
            result = await run_seed(tmp_path)

        assert not result.success
        assert "connection refused" in (result.error or "")

    @pytest.mark.asyncio
    async def test_executor_no_output(self, tmp_path: Path) -> None:
        """Executor returning no output should report failure."""
        mock_exec = _mock_executor(seed_output=None, success=False)

        with patch("maverick.executor.create_default_executor", return_value=mock_exec):
            result = await run_seed(tmp_path)

        assert not result.success

    @pytest.mark.asyncio
    async def test_passes_provider_override(self, tmp_path: Path) -> None:
        """Provider override should be passed to StepConfig."""
        seed_output = SeedOutput(files=[SeedFileEntry(filename="a.md", content="x")])
        mock_exec = _mock_executor(seed_output=seed_output)

        with patch("maverick.executor.create_default_executor", return_value=mock_exec):
            await run_seed(tmp_path, provider="copilot")

        # Verify StepConfig was passed with provider
        call_kwargs = mock_exec.execute.call_args.kwargs
        assert call_kwargs["config"].provider == "copilot"

    @pytest.mark.asyncio
    async def test_cleanup_called_on_success(self, tmp_path: Path) -> None:
        """Executor cleanup should be called even on success."""
        seed_output = SeedOutput(files=[SeedFileEntry(filename="a.md", content="x")])
        mock_exec = _mock_executor(seed_output=seed_output)

        with patch("maverick.executor.create_default_executor", return_value=mock_exec):
            await run_seed(tmp_path)

        mock_exec.cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_called_on_error(self, tmp_path: Path) -> None:
        """Executor cleanup should be called even on error."""
        mock_exec = _mock_executor(raise_error=RuntimeError("boom"))

        with patch("maverick.executor.create_default_executor", return_value=mock_exec):
            await run_seed(tmp_path)

        mock_exec.cleanup.assert_awaited_once()
