"""Async client for the ``bd`` (beads) CLI tool.

Wraps ``bd`` commands using :class:`~maverick.runners.command.CommandRunner`
for async-safe subprocess execution with timeouts and retries.
"""

from __future__ import annotations

import json
from enum import Enum
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
    BeadLifecycleError,
    BeadQueryError,
)
from maverick.logging import get_logger
from maverick.runners.command import CommandRunner

logger = get_logger(__name__)

# Timeout for bd operations (seconds)
BD_TIMEOUT: float = 30.0

# Lifecycle ops can clone Dolt history from a remote, which takes longer
# than a single read/write. Bumped above BD_TIMEOUT.
BD_LIFECYCLE_TIMEOUT: float = 60.0


class LifecycleAction(str, Enum):
    """Action chosen by :meth:`BeadClient.init_or_bootstrap`."""

    INIT = "init"
    BOOTSTRAP = "bootstrap"
    SKIP = "skip"


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
    ) -> dict[str, Any] | list[Any]:
        """Run a bd command and parse JSON output.

        Args:
            cmd: Command list to execute.
            error_cls: Exception class to raise on failure.
            error_msg: Error message prefix.
            **error_kwargs: Additional keyword arguments for the exception.

        Returns:
            Parsed JSON output (dict or list).

        Raises:
            BeadError (or subclass): If the command fails or output is invalid JSON.
        """
        result = await self._runner.run(cmd, cwd=self._cwd)
        if not result.success:
            detail = result.stderr.strip() or "(no output — command may have timed out)"
            raise error_cls(f"{error_msg}: {detail}", **error_kwargs)
        try:
            parsed: dict[str, Any] | list[Any] = json.loads(result.stdout)
            return parsed
        except json.JSONDecodeError as e:
            raise error_cls(f"{error_msg}: invalid JSON: {e}", **error_kwargs) from e

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

        if definition.assignee:
            cmd.extend(["--assignee", definition.assignee])

        if definition.labels:
            cmd.extend(["--labels", ",".join(definition.labels)])

        if parent_id:
            cmd.extend(["--parent", parent_id])

        result = await self._runner.run(cmd, cwd=self._cwd)

        if not result.success:
            detail = result.stderr.strip() or "(no output — command may have timed out)"
            raise BeadCreationError(
                f"Failed to create bead '{definition.title}': {detail}",
                bead_title=definition.title,
            )

        # Parse bd_id from JSON output
        try:
            data = json.loads(result.stdout)
            bd_id = data.get("id") or data.get("bead_id", "")
            if not bd_id:
                msg = f"bd create returned no ID for '{definition.title}': {result.stdout}"
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

    async def ready(
        self,
        parent_id: str | None = None,
        limit: int = 1,
        sort: str = "priority",
    ) -> list[ReadyBead]:
        """Get ready beads via ``bd ready``.

        Args:
            parent_id: Parent bead (epic) ID. When ``None``, queries all
                ready beads without filtering by parent.
            limit: Maximum number of beads to return.
            sort: Sort order (e.g., "priority").

        Returns:
            List of ReadyBead models.

        Raises:
            BeadQueryError: If ``bd ready`` fails.
        """
        cmd = [
            "bd",
            "ready",
            "--limit",
            str(limit),
            "--sort",
            sort,
            "--json",
        ]

        if parent_id:
            cmd.extend(["--parent", parent_id])

        label = f"parent={parent_id}" if parent_id else "all"

        data = await self._run_bd(
            cmd,
            error_cls=BeadQueryError,
            error_msg=f"Failed to get ready beads ({label})",
            query=f"ready {label}",
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

        # bd close --json may return a list; take the first element
        if isinstance(data, list):
            if not data:
                raise BeadCloseError(
                    f"bd close returned empty list for {bead_id}",
                    bead_id=bead_id,
                )
            data = data[0]

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
        """Get child beads of a parent via ``bd list --parent``.

        Args:
            parent_id: Parent bead ID.

        Returns:
            List of BeadSummary for children.

        Raises:
            BeadQueryError: If ``bd list`` fails.
        """
        cmd = ["bd", "list", "--parent", parent_id, "--flat", "--json"]

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
            raise BeadError(f"Failed to set state on bead {bead_id}: {result.stderr.strip()}")

        logger.debug(
            "bead_state_set",
            bead_id=bead_id,
            state=state,
        )

    # ------------------------------------------------------------------
    # Lifecycle (init / bootstrap / state probes)
    # ------------------------------------------------------------------

    def is_initialized(self) -> bool:
        """Check whether ``.beads/`` holds an initialised database.

        bd's real contract for "initialized" (verified empirically against
        a fresh ``bd init`` against bd 1.0.x):

        * an ``embeddeddolt/`` (or ``dolt/`` server-mode) directory, AND
        * a ``metadata.json`` containing a non-empty ``dolt_database``
          field. The other metadata fields (``database``, ``backend``,
          ``dolt_mode``, ``project_id``) come along for free in any
          bd-written state and aren't worth gating on individually.

        Note: ``issue_prefix`` is NOT in ``metadata.json`` — it lives in
        ``config.yaml`` and is auto-detected from the directory name when
        not set. A previous version of this check required ``issue_prefix``
        in metadata.json and always returned False after a fresh init,
        because bd never writes the field there.

        Half-init detection (e.g. ``config.yaml`` with empty
        ``issue-prefix:`` set explicitly) lives in
        ``_clear_invalid_bd_state``, not here — by the time a workflow
        preflight runs, init has already executed any cleanup. This probe
        is intentionally narrow: "does this look like a usable bd
        install?" Anything more invasive belongs in init's cleanup phase.
        """
        beads = self._cwd / ".beads"
        has_dolt_dir = (beads / "embeddeddolt").is_dir() or (beads / "dolt").is_dir()
        if not has_dolt_dir:
            return False
        metadata_path = beads / "metadata.json"
        if not metadata_path.is_file():
            return False
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(metadata, dict):
            return False
        db_name = metadata.get("dolt_database")
        return isinstance(db_name, str) and bool(db_name.strip())

    async def remote_has_dolt_data(self, remote: str = "origin") -> bool:
        """Check whether ``<remote>`` advertises ``refs/dolt/data``.

        bd refuses ``bd init --force`` against a remote that already has
        Dolt history because force only authorizes local divergence. We
        probe for that condition with ``git ls-remote`` so the caller can
        route to ``bd bootstrap`` instead.

        Args:
            remote: Git remote name to query (default ``origin``).

        Returns:
            ``True`` when the remote has ``refs/dolt/data``. ``False``
            when the ref is absent OR ``git ls-remote`` fails for any
            reason (no remote configured, no network, auth failure) —
            on uncertainty we prefer to fall through to ``bd init``,
            which will produce a precise error message.
        """
        result = await self._runner.run(
            ["git", "ls-remote", remote, "refs/dolt/data"],
            cwd=self._cwd,
        )
        if not result.success:
            logger.debug(
                "bd_remote_probe_failed",
                remote=remote,
                stderr=result.stderr.strip(),
            )
            return False
        return bool(result.stdout.strip())

    async def bootstrap(
        self,
        *,
        env: dict[str, str] | None = None,
        timeout: float = BD_LIFECYCLE_TIMEOUT,
    ) -> None:
        """Run ``bd bootstrap --yes`` (non-destructive setup).

        Bootstrap is bd's own state-aware command. Per ``bd bootstrap
        --help`` it auto-detects the right action: clone from remote
        Dolt refs, restore from backup JSONL, import from
        ``.beads/issues.jsonl``, or create fresh — and validates if a
        database already exists. This is what bd's own error messages
        recommend when ``bd init`` runs into the remote-divergence guard.

        Args:
            env: Optional extra environment variables (merged into the
                runner's environment for this call only).
            timeout: Seconds to wait — raised above ``BD_TIMEOUT`` since
                bootstrap can clone Dolt history over the network.

        Raises:
            BeadLifecycleError: If ``bd bootstrap`` exits non-zero or
                times out.
        """
        result = await self._runner.run(
            ["bd", "bootstrap", "--yes"],
            cwd=self._cwd,
            env=env,
            timeout=timeout,
        )
        if not result.success:
            detail = result.stderr.strip() or result.stdout.strip() or "(no output)"
            raise BeadLifecycleError(
                f"'bd bootstrap' failed (exit code {result.returncode}): {detail}",
                action="bootstrap",
            )
        logger.info("bd_bootstrapped", path=str(self._cwd / ".beads"))

    async def init(
        self,
        *,
        prefix: str | None = None,
        from_jsonl: bool = False,
        force: bool = False,
        env: dict[str, str] | None = None,
        timeout: float = BD_LIFECYCLE_TIMEOUT,
    ) -> None:
        """Run ``bd init`` for a fresh repository.

        Prefer :meth:`init_or_bootstrap` over calling this directly —
        ``bd init`` is destructive when the remote already has Dolt
        history, and bd refuses to run in that state.

        Args:
            prefix: Issue prefix. ``None`` lets bd default to the
                directory name. Callers should pre-sanitize for Dolt
                naming rules (no hyphens; no leading digit).
            from_jsonl: Pass ``--from-jsonl`` to import issues from
                ``.beads/issues.jsonl`` rather than re-cloning.
            force: Pass ``--force`` to wipe an existing local database.
                Deprecated upstream in favour of ``--reinit-local``;
                kept here for compatibility with older bd versions.
            env: Extra environment variables (merged for this call).
            timeout: Seconds to wait.

        Raises:
            BeadLifecycleError: If ``bd init`` exits non-zero or times out.
        """
        cmd: list[str] = ["bd", "init", "--non-interactive"]
        if prefix:
            cmd.extend(["--prefix", prefix])
        if from_jsonl:
            cmd.append("--from-jsonl")
        if force:
            cmd.append("--force")
        result = await self._runner.run(cmd, cwd=self._cwd, env=env, timeout=timeout)
        if not result.success:
            detail = result.stderr.strip() or result.stdout.strip() or "(no output)"
            raise BeadLifecycleError(
                f"'bd init' failed (exit code {result.returncode}): {detail}",
                action="init",
            )
        logger.info("bd_initialized", path=str(self._cwd / ".beads"), prefix=prefix)

    async def init_or_bootstrap(
        self,
        *,
        prefix: str | None = None,
        env: dict[str, str] | None = None,
    ) -> LifecycleAction:
        """State-aware dispatch: pick init, bootstrap, or skip.

        State machine:

        =========================================  =====================
        Repo state                                 Action
        =========================================  =====================
        ``.beads/`` already has a local database   :attr:`SKIP`
        Remote ``origin`` advertises Dolt refs     :attr:`BOOTSTRAP`
        ``.beads/issues.jsonl`` exists in a clone  :attr:`BOOTSTRAP`
        Otherwise (truly fresh repo)               :attr:`INIT`
        =========================================  =====================

        Args:
            prefix: Issue prefix for the :attr:`INIT` branch only;
                ignored otherwise.
            env: Extra environment variables threaded into whichever
                lifecycle command runs.

        Returns:
            The :class:`LifecycleAction` actually taken — useful for
            callers that emit different log lines per branch.

        Raises:
            BeadLifecycleError: If the chosen lifecycle command fails.
        """
        if self.is_initialized():
            logger.debug("bd_init_or_bootstrap_skip", path=str(self._cwd / ".beads"))
            return LifecycleAction.SKIP

        # Two signals route to bootstrap: a remote that already has
        # Dolt history (the case the user's error report surfaced), or
        # a clone that already carries `.beads/issues.jsonl` (the
        # second-developer-onboarding case where the JSONL is in git
        # but the local Dolt store hasn't been materialized yet).
        has_remote_dolt = await self.remote_has_dolt_data()
        has_jsonl = (self._cwd / ".beads" / "issues.jsonl").is_file()
        if has_remote_dolt or has_jsonl:
            await self.bootstrap(env=env)
            return LifecycleAction.BOOTSTRAP

        await self.init(prefix=prefix, env=env)
        return LifecycleAction.INIT
