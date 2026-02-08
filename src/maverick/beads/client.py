"""Async client for the ``bd`` (beads) CLI tool.

Wraps ``bd`` commands using :class:`~maverick.runners.command.CommandRunner`
for async-safe subprocess execution with timeouts and retries.
"""

from __future__ import annotations

import json
from pathlib import Path

from maverick.beads.models import BeadDefinition, BeadDependency, CreatedBead
from maverick.exceptions.beads import BeadCreationError, BeadDependencyError, BeadError
from maverick.logging import get_logger
from maverick.runners.command import CommandRunner

logger = get_logger(__name__)

# Timeout for bd operations (seconds)
BD_TIMEOUT: float = 30.0


class BeadClient:
    """Async wrapper around the ``bd`` CLI for bead operations.

    Uses :class:`CommandRunner` for subprocess execution. Supports
    dependency injection of the runner for testing.

    Args:
        cwd: Working directory for ``bd`` commands (the git repo root).
        runner: Optional pre-configured CommandRunner. Created if not provided.

    Example:
        ```python
        client = BeadClient(cwd=Path("/project"))
        if await client.verify_available():
            bead = await client.create_bead(definition)
        ```
    """

    def __init__(
        self,
        cwd: Path,
        runner: CommandRunner | None = None,
    ) -> None:
        self._cwd = cwd
        self._runner = runner or CommandRunner(cwd=cwd, timeout=BD_TIMEOUT)

    async def verify_available(self) -> bool:
        """Check if ``bd`` is available in PATH.

        Returns:
            True if ``bd --version`` succeeds.
        """
        result = await self._runner.run(["bd", "--version"], cwd=self._cwd)
        if result.success:
            logger.debug("bd_available", version=result.stdout.strip())
            return True
        logger.warning("bd_not_available", stderr=result.stderr.strip())
        return False

    async def create_bead(
        self,
        definition: BeadDefinition,
        parent_id: str | None = None,
    ) -> CreatedBead:
        """Create a bead using ``bd create``.

        Args:
            definition: Bead definition with title, type, priority, etc.
            parent_id: Optional parent bead ID for hierarchical nesting.

        Returns:
            CreatedBead with the assigned ``bd_id``.

        Raises:
            BeadCreationError: If ``bd create`` fails.
        """
        cmd: list[str] = [
            "bd",
            "create",
            "--title",
            definition.title,
            "--type",
            definition.bead_type.value,
            "--priority",
            str(definition.priority),
            "--json",
        ]

        if definition.description:
            cmd.extend(["--description", definition.description])

        if parent_id:
            cmd.extend(["--parent", parent_id])

        result = await self._runner.run(cmd, cwd=self._cwd)

        if not result.success:
            raise BeadCreationError(
                f"Failed to create bead '{definition.title}': {result.stderr.strip()}",
                bead_title=definition.title,
            )

        # Parse bd_id from JSON output
        try:
            data = json.loads(result.stdout)
            bd_id = data.get("id") or data.get("bead_id", "")
            if not bd_id:
                msg = (
                    f"bd create returned no ID for "
                    f"'{definition.title}': {result.stdout}"
                )
                raise BeadCreationError(
                    msg,
                    bead_title=definition.title,
                )
        except json.JSONDecodeError as e:
            raise BeadCreationError(
                f"Failed to parse bd create output for '{definition.title}': {e}",
                bead_title=definition.title,
            ) from e

        logger.info(
            "bead_created",
            bd_id=bd_id,
            title=definition.title,
            bead_type=definition.bead_type.value,
        )

        return CreatedBead(bd_id=bd_id, definition=definition)

    async def add_dependency(self, dep: BeadDependency) -> None:
        """Add a dependency between two beads using ``bd dep add``.

        Args:
            dep: Dependency specifying source, target, and type.

        Raises:
            BeadDependencyError: If ``bd dep add`` fails.
        """
        cmd = [
            "bd",
            "dep",
            "add",
            dep.from_id,
            dep.to_id,
        ]

        result = await self._runner.run(cmd, cwd=self._cwd)

        if not result.success:
            raise BeadDependencyError(
                f"Failed to add dependency {dep.from_id} -> {dep.to_id}: "
                f"{result.stderr.strip()}",
                from_id=dep.from_id,
                to_id=dep.to_id,
            )

        logger.debug(
            "dependency_added",
            from_id=dep.from_id,
            to_id=dep.to_id,
        )

    async def sync(self) -> None:
        """Sync beads state with ``bd sync``.

        Raises:
            BeadError: If ``bd sync`` fails.
        """
        result = await self._runner.run(["bd", "sync"], cwd=self._cwd)

        if not result.success:
            raise BeadError(f"Failed to sync beads: {result.stderr.strip()}")

        logger.info("beads_synced")
