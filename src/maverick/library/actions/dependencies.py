"""Dependency sync actions for workflow execution.

Detects and runs the appropriate package manager sync/install command
before validation steps. Supports explicit configuration via `sync_cmd`
in maverick.yaml or auto-detection from lock/manifest files.
"""

from __future__ import annotations

from pathlib import Path

from maverick.library.actions.types import DependencySyncResult
from maverick.logging import get_logger
from maverick.runners.command import CommandRunner

logger = get_logger(__name__)

# Shared runner instance with generous timeout for dependency installs
_runner = CommandRunner(timeout=120.0)

# Ordered list of (file_to_probe, sync_command) for auto-detection.
# Earlier entries take priority.
_MANIFEST_COMMANDS: tuple[tuple[str, list[str]], ...] = (
    ("uv.lock", ["uv", "sync"]),
    ("pyproject.toml", ["pip", "install", "-e", ".[dev]"]),
    ("package-lock.json", ["npm", "install"]),
    ("yarn.lock", ["yarn", "install"]),
    ("pnpm-lock.yaml", ["pnpm", "install"]),
    ("Cargo.toml", ["cargo", "build"]),
    ("go.mod", ["go", "mod", "download"]),
)


def _detect_sync_command(working_dir: Path) -> list[str] | None:
    """Detect the sync command from lock/manifest files.

    Args:
        working_dir: Directory to probe for manifest files.

    Returns:
        Command list if a known manifest is found, None otherwise.
    """
    for filename, command in _MANIFEST_COMMANDS:
        if (working_dir / filename).exists():
            logger.info(
                "auto_detected_sync_command",
                manifest=filename,
                command=" ".join(command),
            )
            return command
    return None


async def sync_dependencies(
    cwd: str | None = None,
    sync_cmd: list[str] | None = None,
) -> DependencySyncResult:
    """Sync/install project dependencies.

    Uses the explicit sync_cmd if provided, otherwise auto-detects from
    lock/manifest files in the working directory.

    Args:
        cwd: Working directory (defaults to current directory).
        sync_cmd: Explicit sync command from config (highest priority).

    Returns:
        DependencySyncResult with success status and details.
    """
    working_dir = Path(cwd) if cwd else Path.cwd()

    # Determine which command to run
    command = sync_cmd if sync_cmd else _detect_sync_command(working_dir)

    if command is None:
        logger.info("no_sync_command_detected", cwd=str(working_dir))
        return DependencySyncResult(
            success=True,
            command=None,
            output=None,
            skipped=True,
            reason="No package manifest detected; skipping dependency sync",
            error=None,
        )

    command_str = " ".join(command)
    logger.info("syncing_dependencies", command=command_str, cwd=str(working_dir))

    result = await _runner.run(command, cwd=working_dir)

    if result.success:
        logger.info(
            "dependency_sync_complete",
            command=command_str,
            duration_ms=result.duration_ms,
        )
        return DependencySyncResult(
            success=True,
            command=command_str,
            output=result.stdout,
            skipped=False,
            reason=None,
            error=None,
        )

    logger.warning(
        "dependency_sync_failed",
        command=command_str,
        returncode=result.returncode,
        stderr=result.stderr[:500],
    )
    return DependencySyncResult(
        success=False,
        command=command_str,
        output=result.stdout,
        skipped=False,
        reason=None,
        error=result.stderr,
    )
