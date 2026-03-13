"""Runway seed: brownfield codebase analysis for runway bootstrapping.

Gathers project context (git log, directory tree, config files) and sends
it to an ACP provider for analysis. The LLM produces semantic markdown
files that pre-populate the runway knowledge store.
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


def _build_directory_tree(project_path: Path) -> str:
    """Walk project directory and build indented tree string."""
    lines: list[str] = []

    def _walk(path: Path, prefix: str, depth: int) -> None:
        if len(lines) >= _MAX_TREE_ENTRIES:
            return
        if depth > _MAX_TREE_DEPTH:
            return

        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        except PermissionError:
            return

        for entry in entries:
            if len(lines) >= _MAX_TREE_ENTRIES:
                return
            if entry.name in _EXCLUDED_DIRS:
                continue
            if entry.is_dir():
                lines.append(f"{prefix}{entry.name}/")
                _walk(entry, prefix + "  ", depth + 1)
            else:
                lines.append(f"{prefix}{entry.name}")

    _walk(project_path, "", 0)
    if len(lines) >= _MAX_TREE_ENTRIES:
        lines.append("... (truncated)")
    return "\n".join(lines)


def _count_file_types(project_path: Path) -> dict[str, int]:
    """Count files by extension, walking up to depth 5."""
    counts: dict[str, int] = {}

    def _walk(path: Path, depth: int) -> None:
        if depth > 5:
            return
        try:
            for entry in path.iterdir():
                if entry.name in _EXCLUDED_DIRS:
                    continue
                if entry.is_dir():
                    _walk(entry, depth + 1)
                elif entry.is_file():
                    ext = entry.suffix or "(no extension)"
                    counts[ext] = counts.get(ext, 0) + 1
        except PermissionError:
            pass

    _walk(project_path, 0)
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


async def _read_config_files(project_path: Path) -> dict[str, str]:
    """Read well-known config files, truncating to _MAX_CONFIG_CHARS."""
    result: dict[str, str] = {}
    for name in _CONFIG_FILES:
        fpath = project_path / name
        if fpath.is_file():
            try:
                async with aiofiles.open(
                    fpath, encoding="utf-8", errors="replace"
                ) as f:
                    content = await f.read(_MAX_CONFIG_CHARS)
                result[name] = content
            except OSError:
                pass
    return result


async def gather_seed_context(project_path: Path) -> SeedContext:
    """Gather project context for the seed agent.

    Collects git log, directory tree, config file contents, and file type
    distribution from the project.

    Args:
        project_path: Root directory of the project.

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

    # Directory tree
    directory_tree = _build_directory_tree(project_path)

    # Config files
    config_files = await _read_config_files(project_path)

    # File type counts
    file_type_counts = _count_file_types(project_path)

    return SeedContext(
        git_log=git_log,
        directory_tree=directory_tree,
        config_files=config_files,
        file_type_counts=file_type_counts,
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
) -> SeedResult:
    """Seed the runway with AI-generated codebase insights.

    Gathers repo context, sends it to an ACP provider for analysis, and
    writes the resulting semantic files to the runway store.

    Args:
        project_path: Root directory of the project.
        provider: Optional ACP provider name override.
        force: Overwrite existing semantic files.
        dry_run: Show what would be generated without writing.

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
                error=f"Semantic files already exist: {existing}. "
                "Use --force to overwrite.",
            )

    # Gather context
    context = await gather_seed_context(project_path)

    # Execute LLM analysis
    executor = create_default_executor()
    try:
        step_config = StepConfig(provider=provider) if provider else None

        result = await executor.execute(
            step_name="runway-seed",
            agent_name="runway_seed",
            prompt=context,
            output_schema=SeedOutput,
            config=step_config,
        )

        if not result.success or result.output is None:
            return SeedResult(success=False, error="ACP provider returned no output.")

        seed_output: SeedOutput = result.output

        if dry_run:
            return SeedResult(
                success=True,
                files_written=tuple(f.filename for f in seed_output.files),
            )

        # Write semantic files
        files_written: list[str] = []
        for entry in seed_output.files:
            await store.write_semantic_file(entry.filename, entry.content)
            files_written.append(entry.filename)
            logger.info(
                "seed_file_written",
                filename=entry.filename,
                size=len(entry.content),
            )

        return SeedResult(success=True, files_written=tuple(files_written))

    except Exception as exc:
        logger.warning("seed_execution_error", error=str(exc))
        return SeedResult(success=False, error=str(exc))
    finally:
        await executor.cleanup()
