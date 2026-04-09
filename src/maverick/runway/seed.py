"""Runway seed: brownfield codebase analysis for runway bootstrapping.

Gathers project context (git log, directory tree, config files) and sends
it to an ACP provider for analysis. The agent uses filesystem tools to
explore the codebase and writes semantic markdown files directly to disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiofiles
from pydantic import BaseModel, ConfigDict

from maverick.git import AsyncGitRepository, CommitInfo
from maverick.logging import get_logger

__all__ = [
    "SeedContext",
    "SeedFileEntry",
    "SeedOutput",
    "SeedResult",
    "gather_seed_context",
    "run_seed",
]

logger = get_logger(__name__)

# Max characters per config file read
_MAX_CONFIG_CHARS = 3000

# Max directory tree entries
_MAX_TREE_ENTRIES = 200

# Max directory tree depth
_MAX_TREE_DEPTH = 3

# Max depth for file-type counting (deeper than tree display)
_MAX_COUNT_DEPTH = 5

# Directories to exclude from tree walk
_EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".maverick",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "target",
        "build",
        "dist",
        ".tox",
        ".eggs",
    }
)

# Well-known config files to read
_CONFIG_FILES: tuple[str, ...] = (
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "Makefile",
    "CLAUDE.md",
    "README.md",
    ".editorconfig",
    "ruff.toml",
    "setup.cfg",
    "tsconfig.json",
    "pom.xml",
)

# Expected semantic files produced by the seed agent
_EXPECTED_FILES: tuple[str, ...] = (
    "architecture.md",
    "conventions.md",
    "review-patterns.md",
    "tech-stack.md",
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SeedContext:
    """Gathered repo context for the seed agent."""

    git_log: tuple[CommitInfo, ...] = ()
    directory_tree: str = ""
    config_files: dict[str, str] = field(default_factory=dict)
    file_type_counts: dict[str, int] = field(default_factory=dict)
    output_dir: str = ""


class SeedFileEntry(BaseModel):
    """Single semantic file produced by the seed agent."""

    model_config = ConfigDict(frozen=True)

    filename: str
    content: str


class SeedOutput(BaseModel):
    """Structured output from the runway seed agent."""

    model_config = ConfigDict(frozen=True)

    files: list[SeedFileEntry]


@dataclass(frozen=True, slots=True)
class SeedResult:
    """Result of runway seed operation."""

    success: bool
    files_written: tuple[str, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d: dict[str, Any] = {
            "success": self.success,
            "files_written": list(self.files_written),
        }
        if self.error is not None:
            d["error"] = self.error
        return d


# ---------------------------------------------------------------------------
# Context gathering
# ---------------------------------------------------------------------------


def _walk_project(
    project_path: Path,
) -> tuple[str, dict[str, int]]:
    """Walk project directory once, producing both a tree string and file type counts.

    The tree is built to ``_MAX_TREE_DEPTH`` / ``_MAX_TREE_ENTRIES``.
    File type counts are collected to depth 5 (deeper than the tree).

    Returns:
        (directory_tree, file_type_counts)
    """
    tree_lines: list[str] = []
    counts: dict[str, int] = {}

    def _walk(path: Path, prefix: str, depth: int) -> None:
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        except PermissionError:
            return

        for entry in entries:
            if entry.name in _EXCLUDED_DIRS:
                continue
            if entry.is_dir():
                # Tree display (capped by depth and entry count)
                if depth <= _MAX_TREE_DEPTH and len(tree_lines) < _MAX_TREE_ENTRIES:
                    tree_lines.append(f"{prefix}{entry.name}/")
                # Always recurse for counts (up to count depth)
                if depth < _MAX_COUNT_DEPTH:
                    _walk(entry, prefix + "  ", depth + 1)
            else:
                if depth <= _MAX_TREE_DEPTH and len(tree_lines) < _MAX_TREE_ENTRIES:
                    tree_lines.append(f"{prefix}{entry.name}")
                ext = entry.suffix or "(no extension)"
                counts[ext] = counts.get(ext, 0) + 1

    _walk(project_path, "", 0)
    if len(tree_lines) >= _MAX_TREE_ENTRIES:
        tree_lines.append("... (truncated)")

    sorted_counts = dict(sorted(counts.items(), key=lambda kv: -kv[1]))
    return "\n".join(tree_lines), sorted_counts


async def _read_config_files(project_path: Path) -> dict[str, str]:
    """Read well-known config files, truncating to _MAX_CONFIG_CHARS."""
    result: dict[str, str] = {}
    for name in _CONFIG_FILES:
        fpath = project_path / name
        if fpath.is_file():
            try:
                async with aiofiles.open(fpath, encoding="utf-8", errors="replace") as f:
                    content = await f.read(_MAX_CONFIG_CHARS)
                result[name] = content
            except OSError:
                pass
    return result


async def gather_seed_context(
    project_path: Path,
    output_dir: Path | None = None,
) -> SeedContext:
    """Gather project context for the seed agent.

    Collects git log, directory tree, config file contents, and file type
    distribution from the project.

    Args:
        project_path: Root directory of the project.
        output_dir: Directory where the agent should write semantic files.

    Returns:
        SeedContext with gathered data.
    """
    # Git log — best-effort
    git_log: tuple[CommitInfo, ...] = ()
    try:
        repo = AsyncGitRepository(project_path)
        commits = await repo.log(n=50)
        git_log = tuple(commits)
    except Exception as exc:
        logger.debug("seed_git_log_error", error=str(exc))

    # Directory tree + file type counts (single walk)
    directory_tree, file_type_counts = _walk_project(project_path)

    # Config files
    config_files = await _read_config_files(project_path)

    return SeedContext(
        git_log=git_log,
        directory_tree=directory_tree,
        config_files=config_files,
        file_type_counts=file_type_counts,
        output_dir=str(output_dir) if output_dir else "",
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def run_seed(
    project_path: Path,
    *,
    provider: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    context: SeedContext | None = None,
) -> SeedResult:
    """Seed the runway with AI-generated codebase insights.

    The seed agent uses ACP with filesystem tools to explore the codebase
    and write semantic markdown files directly to disk.

    Args:
        project_path: Root directory of the project.
        provider: Optional ACP provider name override.
        force: Overwrite existing semantic files.
        dry_run: Show what would be generated without writing.
        context: Pre-gathered seed context. If None, gathered automatically.

    Returns:
        SeedResult with success status and files written.
    """
    from maverick.executor import StepConfig, create_default_executor
    from maverick.runway.store import RunwayStore

    runway_path = project_path / ".maverick" / "runway"
    store = RunwayStore(runway_path)

    # Auto-initialize runway if needed
    if not store.is_initialized:
        logger.info("seed_auto_initializing_runway", path=str(runway_path))
        await store.initialize()

    # Check for existing semantic files unless force
    if not force:
        status = await store.get_status()
        if status.semantic_files:
            existing = ", ".join(status.semantic_files)
            return SeedResult(
                success=True,
                files_written=(),
                error=f"Semantic files already exist: {existing}. Use --force to overwrite.",
            )

    # Ensure semantic output directory exists
    semantic_dir = runway_path / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)

    # Gather context if not provided
    if context is None:
        context = await gather_seed_context(project_path, output_dir=semantic_dir)

    # Execute via ACP — the agent writes files directly to semantic_dir
    executor = create_default_executor()
    try:
        # Seed agent explores the codebase and writes files — needs more time
        # than the default 300s timeout.
        step_config = StepConfig(provider=provider, timeout=600)

        await executor.execute(
            step_name="runway-seed",
            agent_name="runway_seed",
            prompt=context,
            config=step_config,
            cwd=project_path,
        )

        # Check which files the agent wrote
        files_written: list[str] = []
        for filename in _EXPECTED_FILES:
            fpath = semantic_dir / filename
            if fpath.is_file() and fpath.stat().st_size > 0:
                files_written.append(filename)
                logger.info(
                    "seed_file_written",
                    filename=filename,
                    size=fpath.stat().st_size,
                )

        if not files_written:
            return SeedResult(
                success=False,
                error="Agent completed but no semantic files were written.",
            )

        return SeedResult(success=True, files_written=tuple(files_written))

    except Exception as exc:
        logger.warning("seed_execution_error", error=str(exc))
        return SeedResult(success=False, error=str(exc))
    finally:
        await executor.cleanup()
