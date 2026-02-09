"""Async client for the ``bd`` (beads) CLI tool.

Wraps ``bd`` commands using :class:`~maverick.runners.command.CommandRunner`
for async-safe subprocess execution with timeouts and retries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from maverick.beads.models import (
    BeadDefinition,
    BeadDependency,
    BeadDetails,
    BeadSummary,
    ClosedBead,
    CreatedBead,
    ReadyBead,
)
from maverick.exceptions.beads import (
    BeadCloseError,
    BeadCreationError,
    BeadDependencyError,
    BeadError,
    BeadQueryError,
)
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

    async def _run_bd(
        self,
        cmd: list[str],
        error_cls: type[BeadError] = BeadError,
        error_msg: str = "bd command failed",
        **error_kwargs: str | None,
    ) -> dict[str, Any]:
        """Run a bd command and parse JSON output.

        Args:
            cmd: Command list to execute.
            error_cls: Exception class to raise on failure.
            error_msg: Error message prefix.
            **error_kwargs: Additional keyword arguments for the exception.

        Returns:
            Parsed JSON output as a dict.

        Raises:
            BeadError (or subclass): If the command fails or output is invalid JSON.
        """
        result = await self._runner.run(cmd, cwd=self._cwd)
        if not result.success:
            raise error_cls(
                f"{error_msg}: {result.stderr.strip()}", **error_kwargs
            )
        try:
            parsed: dict[str, Any] = json.loads(result.stdout)
            return parsed
        except json.JSONDecodeError as e:
            raise error_cls(
                f"{error_msg}: invalid JSON: {e}", **error_kwargs
            ) from e

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

        Translates to::

            bd dep add <blocked> --blocked-by <blocker> --type <type>

        Args:
            dep: Dependency specifying blocker, blocked, and type.

        Raises:
            BeadDependencyError: If ``bd dep add`` fails.
        """
        cmd = [
            "bd",
            "dep",
            "add",
            dep.blocked_id,
            "--blocked-by",
            dep.blocker_id,
            "--type",
            dep.dep_type.value,
        ]

        result = await self._runner.run(cmd, cwd=self._cwd)

        if not result.success:
            raise BeadDependencyError(
                f"Failed to add dependency "
                f"{dep.blocked_id} --blocked-by {dep.blocker_id}: "
                f"{result.stderr.strip()}",
                blocker_id=dep.blocker_id,
                blocked_id=dep.blocked_id,
            )

        logger.debug(
            "dependency_added",
            blocker_id=dep.blocker_id,
            blocked_id=dep.blocked_id,
            dep_type=dep.dep_type.value,
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

    async def ready(
        self,
        parent_id: str,
        limit: int = 1,
        sort: str = "priority",
    ) -> list[ReadyBead]:
        """Get ready beads for a parent (epic) via ``bd ready``.

        Args:
            parent_id: Parent bead (epic) ID.
            limit: Maximum number of beads to return.
            sort: Sort order (e.g., "priority").

        Returns:
            List of ReadyBead models.

        Raises:
            BeadQueryError: If ``bd ready`` fails.
        """
        cmd = [
            "bd", "ready",
            "--parent", parent_id,
            "--limit", str(limit),
            "--sort", sort,
            "--json",
        ]

        data = await self._run_bd(
            cmd,
            error_cls=BeadQueryError,
            error_msg=f"Failed to get ready beads for {parent_id}",
            query=f"ready --parent {parent_id}",
        )

        items = data if isinstance(data, list) else data.get("beads", [])
        beads = [ReadyBead.model_validate(item) for item in items]

        logger.debug(
            "ready_beads_fetched",
            parent_id=parent_id,
            count=len(beads),
        )
        return beads

    async def close(
        self,
        bead_id: str,
        reason: str = "",
    ) -> ClosedBead:
        """Close a bead via ``bd close``.

        Args:
            bead_id: ID of the bead to close.
            reason: Optional reason for closing.

        Returns:
            ClosedBead with final status.

        Raises:
            BeadCloseError: If ``bd close`` fails.
        """
        cmd = ["bd", "close", bead_id, "--json"]
        if reason:
            cmd.extend(["--reason", reason])

        data = await self._run_bd(
            cmd,
            error_cls=BeadCloseError,
            error_msg=f"Failed to close bead {bead_id}",
            bead_id=bead_id,
        )

        closed = ClosedBead.model_validate(data)

        logger.info("bead_closed", bead_id=bead_id, status=closed.status)
        return closed

    async def show(self, bead_id: str) -> BeadDetails:
        """Get full details of a bead via ``bd show``.

        Args:
            bead_id: ID of the bead to show.

        Returns:
            BeadDetails with full bead information.

        Raises:
            BeadQueryError: If ``bd show`` fails.
        """
        cmd = ["bd", "show", bead_id, "--json"]

        data = await self._run_bd(
            cmd,
            error_cls=BeadQueryError,
            error_msg=f"Failed to show bead {bead_id}",
            query=f"show {bead_id}",
        )

        details = BeadDetails.model_validate(data)

        logger.debug("bead_details_fetched", bead_id=bead_id, title=details.title)
        return details

    async def children(self, parent_id: str) -> list[BeadSummary]:
        """Get child beads of a parent via ``bd children``.

        Args:
            parent_id: Parent bead ID.

        Returns:
            List of BeadSummary for children.

        Raises:
            BeadQueryError: If ``bd children`` fails.
        """
        cmd = ["bd", "children", parent_id, "--json"]

        data = await self._run_bd(
            cmd,
            error_cls=BeadQueryError,
            error_msg=f"Failed to get children of {parent_id}",
            query=f"children {parent_id}",
        )

        items = data if isinstance(data, list) else data.get("children", [])
        summaries = [BeadSummary.model_validate(item) for item in items]

        logger.debug(
            "children_fetched",
            parent_id=parent_id,
            count=len(summaries),
        )
        return summaries

    async def query(self, filter_expr: str) -> list[BeadSummary]:
        """Query beads with a filter expression via ``bd query``.

        Args:
            filter_expr: Filter expression string.

        Returns:
            List of BeadSummary matching the query.

        Raises:
            BeadQueryError: If ``bd query`` fails.
        """
        cmd = ["bd", "query", filter_expr, "--json"]

        data = await self._run_bd(
            cmd,
            error_cls=BeadQueryError,
            error_msg=f"Failed to query beads: {filter_expr}",
            query=filter_expr,
        )

        items = data if isinstance(data, list) else data.get("beads", [])
        summaries = [BeadSummary.model_validate(item) for item in items]

        logger.debug(
            "beads_queried",
            filter_expr=filter_expr,
            count=len(summaries),
        )
        return summaries

    async def set_state(
        self,
        bead_id: str,
        state: dict[str, str],
        reason: str = "",
    ) -> None:
        """Set state metadata on a bead via ``bd set-state``.

        Args:
            bead_id: ID of the bead to update.
            state: Key-value pairs to set.
            reason: Optional reason for the state change.

        Raises:
            BeadError: If ``bd set-state`` fails.
        """
        cmd = ["bd", "set-state", bead_id]
        for key, value in state.items():
            cmd.append(f"{key}={value}")
        if reason:
            cmd.extend(["--reason", reason])

        result = await self._runner.run(cmd, cwd=self._cwd)
        if not result.success:
            raise BeadError(
                f"Failed to set state on bead {bead_id}: {result.stderr.strip()}"
            )

        logger.debug(
            "bead_state_set",
            bead_id=bead_id,
            state=state,
        )
