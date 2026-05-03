"""Maverick init command implementation.

This package provides the `maverick init` command for project initialization,
including prerequisite validation, project type detection, and configuration
generation.

Public API:
    - run_init: Main entry point for init workflow
    - parse_git_remote: Parse git remote URL to extract owner/repo
    - GitRemoteInfo: Parsed git remote information dataclass

Models are re-exported from maverick.init.models.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from maverick.exceptions.init import InitError, PrerequisiteError
from maverick.init.config_generator import generate_config, write_config
from maverick.init.detector import detect_project_type
from maverick.init.git_parser import parse_git_remote
from maverick.init.models import (
    MARKER_FILE_MAP,
    PYTHON_DEFAULTS,
    VALIDATION_DEFAULTS,
    DetectionConfidence,
    GitRemoteInfo,
    InitConfig,
    InitGitHubConfig,
    InitModelConfig,
    InitPreflightResult,
    InitResult,
    InitValidationConfig,
    PreflightStatus,
    PrerequisiteCheck,
    ProjectDetectionResult,
    ProjectMarker,
    ProjectType,
    ValidationCommands,
    resolve_model_id,
)
from maverick.init.opencode_discovery import (
    ConnectedProvider,
    OpenCodeDiscoveryResult,
    discover_opencode_providers,
)
from maverick.init.prereqs import verify_prerequisites
from maverick.logging import get_logger

__all__ = [
    # Functions
    "run_init",
    "parse_git_remote",
    "resolve_model_id",
    "discover_opencode_providers",
    # Enums
    "ProjectType",
    "DetectionConfidence",
    "PreflightStatus",
    # Constants
    "MARKER_FILE_MAP",
    "VALIDATION_DEFAULTS",
    "PYTHON_DEFAULTS",
    # Dataclasses
    "ProjectMarker",
    "ValidationCommands",
    "PrerequisiteCheck",
    "GitRemoteInfo",
    "ProjectDetectionResult",
    "InitPreflightResult",
    "InitResult",
    "ConnectedProvider",
    "OpenCodeDiscoveryResult",
    # Pydantic models
    "InitGitHubConfig",
    "InitValidationConfig",
    "InitModelConfig",
    "InitConfig",
]

# =============================================================================
# Module Logger
# =============================================================================

logger = get_logger(__name__)


# =============================================================================
# Beads Initialization
# =============================================================================

_BD_INIT_TIMEOUT_SECONDS = 60


def _is_valid_dolt_db_name(name: str) -> bool:
    """Return True iff ``name`` is a legal Dolt database identifier.

    Dolt rejects names with hyphens or other non-alphanumeric/underscore chars,
    and disallows leading digits.
    """
    if not name:
        return False
    if name[0].isdigit():
        return False
    return all(ch.isalnum() or ch == "_" for ch in name)


def _clear_invalid_bd_state(project_path: Path) -> None:
    """Reset stale bd state when the project is in a half-init condition.

    Half-init = ``.beads/`` contains state but bd considers it incomplete.
    Empirically observed forms (each one a separate field bug we shipped):

    1. Older bd versions wrote ``dolt_database`` values the current Dolt
       engine refuses to open (typically hyphens). ``bd init`` then keeps
       the bad name even with a fresh ``--prefix``.
    2. A previous ``bd init`` aborted mid-clone, leaving a partial
       ``embeddeddolt/`` directory. ``bd init`` rejects the next attempt
       with "database exists".
    3. ``metadata.json`` valid but missing ``issue_prefix``. ``bd create``
       fails with "issue_prefix config is missing".
    4. ``dolt/`` (server mode) or ``embeddeddolt/`` exists with NO
       ``metadata.json`` at all — half-init from a previous server-mode
       attempt that never finished. ``config.yaml`` typically still has
       ``sync.remote`` set, causing the next ``bd init`` to try cloning
       Dolt from a non-Dolt git remote and fail with "remote at that url
       contains no Dolt data".

    The trigger is "directory present, metadata missing/invalid" — both
    conditions matter, and the previous version of this code only fired
    on (2) + (3) (metadata-present-and-invalid). Form (4) survived
    unscathed and kept biting users.

    bd uses ``config.yaml`` (not ``.json``) for project config, so the
    wipe targets both extensions defensively.

    Files / dirs we deliberately preserve:
        * ``hooks/`` — bd-installed git hooks; project-level config.
        * ``.gitignore`` / ``AGENTS.md`` / ``README.md`` — documentation.
    """
    beads_dir = project_path / ".beads"
    if not beads_dir.is_dir():
        return

    metadata_path = beads_dir / "metadata.json"
    embedded_dir = beads_dir / "embeddeddolt"
    server_dir = beads_dir / "dolt"
    has_dolt_dir = embedded_dir.is_dir() or server_dir.is_dir()

    # Triage the metadata. Note: ``issue_prefix`` is NOT a metadata.json
    # field — bd stores it in ``config.yaml``. Earlier versions of this
    # function checked ``metadata.get("issue_prefix")`` and never matched
    # bd's actual schema; the check is gone here and the trigger is
    # purely "directory present but metadata is missing or has a bad
    # ``dolt_database``".
    state_invalid = False
    if has_dolt_dir and not metadata_path.is_file():
        # Form (4): dolt directory present but metadata gone. Half-init.
        state_invalid = True
    elif metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text())
        except (OSError, ValueError):
            metadata = None
        if not isinstance(metadata, dict):
            state_invalid = True
        else:
            db_name = metadata.get("dolt_database")
            if not (isinstance(db_name, str) and _is_valid_dolt_db_name(db_name)):
                state_invalid = True
        if state_invalid:
            try:
                metadata_path.unlink()
            except OSError:
                pass

    # Wipe ALL bd-managed state when invalid. ``config.yaml`` is the
    # source of the persistent ``sync.remote`` issue — bd reads it on
    # every init and tries to sync, even after we wipe ``embeddeddolt/``
    # / ``dolt/``. Wiping config.yaml + interactions.jsonl + backup/ +
    # the legacy config.json + issues.jsonl ensures bd starts from a
    # truly clean slate.
    if state_invalid:
        bd_managed_state = (
            "embeddeddolt",
            "dolt",
            "config.yaml",
            "config.json",
            "issues.jsonl",
            "interactions.jsonl",
            "backup",
        )
        for name in bd_managed_state:
            target = beads_dir / name
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.is_file():
                try:
                    target.unlink()
                except OSError:
                    pass

    # Server-mode lock/pid files from a previous run are always safe to
    # clear — they're transient state, never durable storage.
    for stale in (
        "dolt-server.lock",
        "dolt-server.log",
        "dolt-server.pid",
        "dolt-server.port",
        "dolt-server.activity",
        "dolt-monitor.pid",
        "dolt-monitor.pid.lock",
        ".local_version",
    ):
        try:
            (beads_dir / stale).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def _sanitize_bd_prefix(name: str) -> str:
    """Convert a directory name into a Dolt-safe bd issue prefix.

    Dolt rejects hyphens in database names; bd derives the database name from
    the prefix, so we replace any non-alphanumeric character with an underscore
    and collapse repeats. Leading digits get an ``_`` prefix to keep the result
    a valid identifier.
    """
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    if not cleaned:
        cleaned = "project"
    if cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned


async def _init_beads(project_path: Path, verbose: bool) -> bool:
    """Initialize beads via :meth:`BeadClient.init_or_bootstrap`.

    Dispatches to ``bd bootstrap`` when the repo already carries Dolt
    history (remote ``refs/dolt/data`` or a tracked
    ``.beads/issues.jsonl``) and to ``bd init`` only for genuinely fresh
    repositories. ``bd bootstrap`` is non-destructive by design and is
    what bd's own error messages recommend when its remote-divergence
    guard fires; routing through it makes ``maverick init`` safe for
    second-and-onward developers joining a project.

    Raises :class:`InitError` if ``bd`` is not installed or the chosen
    lifecycle command fails, since beads are required for ``refuel`` and
    ``fly`` workflows.

    Args:
        project_path: Project root directory.
        verbose: Whether to log progress.

    Returns:
        True if beads are initialized after this call.

    Raises:
        InitError: If ``bd`` is not found or initialization fails.
    """
    from maverick.beads.client import BeadClient, LifecycleAction
    from maverick.exceptions.beads import BeadLifecycleError
    from maverick.runners.command import CommandRunner

    if shutil.which("bd") is None:
        raise InitError(
            "The 'bd' CLI is required but not found on PATH. "
            "Install it with: cargo install bd-cli (or see "
            "https://github.com/get2knowio/bd)"
        )

    # bd defaults --prefix to the directory name, but Dolt rejects hyphens in
    # database names. Sanitize the directory name so a fresh init succeeds on
    # repos like "sample-maverick-project". (Bootstrap reuses an existing
    # database name, so the sanitized prefix only matters on the init branch.)
    prefix = _sanitize_bd_prefix(project_path.name)

    # If a previous bd init left metadata pointing at an invalid Dolt database
    # name (e.g., one containing hyphens), bd will refuse to open the store
    # and ignore --prefix. Wipe the stale metadata and embedded store so the
    # next lifecycle call can succeed.
    _clear_invalid_bd_state(project_path)

    # Disable git hooks for the bd-internal git commit only. bd installs a
    # pre-commit hook (via core.hooksPath = .beads/hooks) that calls back into
    # ``bd export``, which deadlocks against the embeddeddolt lock the parent
    # ``bd init`` already holds. Injecting core.hooksPath via GIT_CONFIG_*
    # env vars takes effect for git invocations bd makes, without modifying
    # the repository's persistent config. Same risk applies to ``bd
    # bootstrap`` so we thread the env through both.
    bd_env = {
        **os.environ,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": "/dev/null",
    }

    runner = CommandRunner(cwd=project_path, timeout=float(_BD_INIT_TIMEOUT_SECONDS))
    client = BeadClient(cwd=project_path, runner=runner)

    try:
        action = await client.init_or_bootstrap(prefix=prefix, env=bd_env)
    except BeadLifecycleError as exc:
        raise InitError(str(exc)) from exc

    # bd init auto-sets ``sync.remote`` in ``.beads/config.yaml`` to whatever
    # git remote it detects, intending to enable bd's federated dolt-sync.
    # Maverick uses bd as a backing store, not a federated tracker — and a
    # configured ``sync.remote`` is exactly what makes ``bd bootstrap`` (in
    # the workspace, on every fresh clone) prefer cloning stale Dolt history
    # from GitHub over importing the canonical local issues.jsonl. That
    # produces a workspace dolt with a fresh internal ``_project_id`` that
    # mismatches the cloned ``metadata.json``, and every subsequent bd
    # call fails the workspace-identity check. Stripping the line at init
    # time, in the user repo, prevents the whole class of bug at the
    # source instead of papering over it later.
    _strip_bd_sync_remote(project_path / ".beads" / "config.yaml", verbose)

    if verbose:
        if action is LifecycleAction.BOOTSTRAP:
            logger.info(
                "beads_bootstrapped",
                path=str(project_path / ".beads"),
                reason="remote_or_jsonl_present",
            )
        elif action is LifecycleAction.INIT:
            logger.info(
                "beads_initialized",
                path=str(project_path / ".beads"),
                prefix=prefix,
            )
        else:
            logger.debug(
                "beads_already_initialized",
                path=str(project_path / ".beads"),
            )
    return True


def _strip_bd_sync_remote(config_path: Path, verbose: bool) -> None:
    """Remove any active ``sync.remote:`` line from ``.beads/config.yaml``.

    Maverick doesn't use bd's federated dolt-sync; we want bd to operate
    against a single local store and let git carry ``.beads/issues.jsonl``
    as the cross-clone source of truth. Leaving ``sync.remote`` set
    causes ``bd bootstrap`` (which Maverick's hidden workspaces run on
    every fresh clone) to take its highest-priority path: clone Dolt
    history from the configured remote, rather than import from
    ``issues.jsonl``. The cloned dolt usually has its own internal
    ``_project_id``, mismatching the cloned ``metadata.json``, and bd
    refuses every subsequent command.

    Edits the line *out* (rather than commenting it) — this is bd's own
    config file in the user repo, not a workspace shim, and we own the
    decision: federation is off, full stop. Idempotent. No-op when the
    file is missing or the key is absent.

    Best-effort: failures are logged but never raised. The user repo
    remains usable; the bug will surface later in workspace bootstrap
    if this didn't take.
    """
    if not config_path.is_file():
        return
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug(
            "bd_sync_remote_strip_read_failed",
            path=str(config_path),
            error=str(exc),
        )
        return

    new_lines: list[str] = []
    changed = False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("sync.remote:"):
            changed = True
            continue
        new_lines.append(line)

    if not changed:
        return

    try:
        config_path.write_text("".join(new_lines), encoding="utf-8")
    except OSError as exc:
        logger.debug(
            "bd_sync_remote_strip_write_failed",
            path=str(config_path),
            error=str(exc),
        )
        return

    if verbose:
        logger.info("bd_sync_remote_stripped", path=str(config_path))


# =============================================================================
# Runway Initialization (best-effort)
# =============================================================================


async def _maybe_init_runway(project_path: Path, verbose: bool) -> bool:
    """Initialize runway store if not already present.

    Best-effort: errors are logged but never raised.

    Args:
        project_path: Project root directory.
        verbose: Whether to log progress.

    Returns:
        True if runway was initialized, False otherwise.
    """
    try:
        from maverick.runway.store import RunwayStore

        runway_path = project_path / ".maverick" / "runway"
        store = RunwayStore(runway_path)
        if store.is_initialized:
            if verbose:
                logger.debug("runway_already_initialized", path=str(runway_path))
            return True
        await store.initialize()
        if verbose:
            logger.info("runway_initialized", path=str(runway_path))
        return True
    except Exception as exc:
        logger.debug("runway_init_error", error=str(exc))
        return False


# =============================================================================
# .gitignore maintenance (best-effort)
# =============================================================================


#: Lines we ensure are present in ``.gitignore``. Keep this list tightly
#: scoped to maverick's own ephemeral output — language/tool-specific
#: ignores (``node_modules/``, ``dist/``, ``__pycache__``) belong in the
#: project's existing ignore strategy, not in maverick's defaults.
_MAVERICK_GITIGNORE_ENTRIES: tuple[str, ...] = (".maverick/runs/",)

#: Patterns that already cover an entry — used to avoid duplicating
#: the line when a broader pattern like ``.maverick/`` is present.
_MAVERICK_GITIGNORE_COVERED_BY: dict[str, tuple[str, ...]] = {
    ".maverick/runs/": (
        ".maverick/runs",
        ".maverick/runs/",
        ".maverick/",
        ".maverick",
        ".maverick/*",
        ".maverick/**",
    ),
}


async def _ensure_gitignore_entries(project_path: Path, verbose: bool) -> bool:
    """Make sure ``.gitignore`` ignores maverick's ephemeral output.

    Currently appends ``.maverick/runs/`` if no equivalent pattern is
    already present. Idempotent — safe to re-run on every init.

    Best-effort: failures are logged but never raised. The user can
    always edit ``.gitignore`` themselves.

    Args:
        project_path: Project root directory.
        verbose: Whether to log progress.

    Returns:
        True when ``.gitignore`` ended up containing every entry we
        wanted (whether we added anything or not). False if writing
        failed.
    """
    try:
        gitignore_path = project_path / ".gitignore"
        existing_text = (
            gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
        )
        existing_lines = {line.strip() for line in existing_text.splitlines()}

        to_append: list[str] = []
        for entry in _MAVERICK_GITIGNORE_ENTRIES:
            covered_by = _MAVERICK_GITIGNORE_COVERED_BY.get(entry, (entry,))
            if any(pattern in existing_lines for pattern in covered_by):
                continue
            to_append.append(entry)

        if not to_append:
            if verbose:
                logger.debug(
                    "gitignore_already_has_maverick_entries",
                    path=str(gitignore_path),
                )
            return True

        # Preserve trailing-newline hygiene: add one if the existing
        # file doesn't end in one.
        prefix = ""
        if existing_text and not existing_text.endswith("\n"):
            prefix = "\n"

        block = (
            prefix
            + "\n".join(
                ["# maverick", *to_append],
            )
            + "\n"
        )

        with gitignore_path.open("a", encoding="utf-8") as fp:
            fp.write(block)

        if verbose:
            logger.info(
                "gitignore_updated",
                path=str(gitignore_path),
                added=to_append,
            )
        return True
    except Exception as exc:
        logger.debug("gitignore_update_error", error=str(exc))
        return False


async def _untrack_bd_local_state(project_path: Path, verbose: bool) -> bool:
    """Untrack bd state files that bd's own ``.beads/.gitignore`` marks as
    local-only.

    bd's stock template puts ``backup/`` and ``interactions.jsonl`` (among
    others) in its gitignore — they're per-machine ephemera. But early
    Maverick runs (or aggressive ``git add -A`` calls) bundled them into
    user-repo commits before the gitignore took effect. Once tracked,
    git keeps tracking them, and every workspace clone inherits stale
    state that derails bd bootstrap — most visibly, ``bd bootstrap``
    chooses the "restore from backup" code path over the JSONL-import
    path, hits a half-initialized embedded dolt, and fails with
    ``database 'beads' already exists``.

    Running ``git rm --cached`` once per file fixes the symptom for
    all future workspace clones. The files stay on disk; only the
    git index loses them. The user sees a staged deletion in
    ``git status`` and commits at their convenience.

    Conservative scope: only files / directories that bd's own
    template gitignores AND that are observed to break workspace
    bootstrap. Not a wholesale "clean every gitignored bd file" sweep.

    Idempotent. No-op if a path is already untracked, ``.git`` is
    missing, or git invocations fail. Best-effort.

    Returns:
        True when all targeted paths ended up untracked (or already
        were); False on error.
    """
    if not (project_path / ".git").exists():
        return True

    from maverick.runners.command import CommandRunner

    runner = CommandRunner()
    targets = (".beads/backup",)
    success = True

    for target in targets:
        # Check if anything under target is tracked. ``ls-files`` returns
        # exit 0 with empty stdout when nothing matches — we want to skip
        # the rm only when nothing is tracked.
        try:
            check = await runner.run(
                ["git", "ls-files", target],
                cwd=project_path,
            )
        except OSError as exc:
            logger.debug("bd_local_state_check_failed", target=target, error=str(exc))
            success = False
            continue

        if not check.success or not check.stdout.strip():
            continue

        try:
            rm = await runner.run(
                ["git", "rm", "--cached", "-r", target],
                cwd=project_path,
            )
        except OSError as exc:
            logger.debug("bd_local_state_untrack_failed", target=target, error=str(exc))
            success = False
            continue

        if not rm.success:
            logger.debug(
                "bd_local_state_untrack_failed",
                target=target,
                stderr=rm.stderr.strip(),
                returncode=rm.returncode,
            )
            success = False
            continue

        if verbose:
            logger.info(
                "bd_local_state_untracked",
                target=target,
                path=str(project_path / target),
            )

    return success


# =============================================================================
# Provider Discovery (best-effort)
# =============================================================================


async def _maybe_discover_providers(
    verbose: bool,
) -> OpenCodeDiscoveryResult | None:
    """Discover providers connected to the OpenCode runtime.

    Spawns ``opencode serve``, hits ``GET /provider``, and returns the
    ``connected[]`` providers. Best-effort: failures are logged but
    never raised.
    """
    result = await discover_opencode_providers()
    if result is not None and verbose:
        logger.info(
            "providers_discovered",
            connected=[p.provider_id for p in result.providers],
            default=result.default_provider_id,
            duration_ms=result.duration_ms,
        )
    return result


# =============================================================================
# Main Entry Point
# =============================================================================


async def run_init(
    *,
    project_path: Path | None = None,
    type_override: ProjectType | None = None,
    force: bool = False,
    verbose: bool = False,
) -> InitResult:
    """Execute maverick init workflow.

    Orchestrates the complete init workflow:
    1. Verify prerequisites (git, gh, etc.)
    2. Parse git remote information
    3. Detect project type from marker files
    4. Discover OpenCode-connected providers via ``GET /provider``
    5. Generate configuration
    6. Write maverick.yaml

    Args:
        project_path: Path to project root. Defaults to cwd.
        type_override: Force specific project type (skips detection).
        force: Overwrite existing config file.
        verbose: Enable verbose output.

    Returns:
        InitResult with complete execution state. When ``maverick.yaml``
        already existed and ``force=False``, ``config_existed=True`` and
        ``config`` / ``detection`` are ``None`` — only the idempotent
        steps (prereqs, beads, runway) ran.

    Raises:
        PrerequisiteError: If prerequisites fail.
        DetectionError: If detection fails.
        ConfigWriteError: If write fails.

    Example:
        result = await run_init(force=True)
        if result.success:
            print(f"Config written to {result.config_path}")
    """
    # Use project_path or default to cwd
    effective_path = project_path if project_path is not None else Path.cwd()
    config_path = effective_path / "maverick.yaml"
    config_existed = config_path.exists() and not force

    if verbose:
        logger.info(
            "init_started",
            project_path=str(effective_path),
            config_existed=config_existed,
        )

    # Step 1: Verify prerequisites
    preflight_result = await verify_prerequisites(
        cwd=effective_path,
    )

    if not preflight_result.success:
        # Find the first failed check and raise PrerequisiteError
        for check in preflight_result.checks:
            if check.status == PreflightStatus.FAIL:
                logger.error(
                    "prerequisite_failed",
                    check_name=check.name,
                    message=check.message,
                    remediation=check.remediation,
                )
                raise PrerequisiteError(check)
        # Should not reach here, but handle gracefully
        raise PrerequisiteError(
            PrerequisiteCheck(
                name="unknown",
                display_name="Unknown",
                status=PreflightStatus.FAIL,
                message="Prerequisites failed",
            )
        )

    if verbose:
        logger.info(
            "prerequisites_passed",
            duration_ms=preflight_result.total_duration_ms,
        )

    # Step 2: Parse git remote information
    git_info = await parse_git_remote(effective_path)

    if verbose:
        if git_info.full_name:
            logger.info("git_remote_found", full_name=git_info.full_name)
        else:
            logger.warning("git_remote_not_found")

    # Step 3+4+5: Detection / provider discovery / config generation are
    # all skipped when the config already exists and force=False — see
    # FUTURE.md §4.3. Detection is the expensive step (Claude call) and
    # generating a config we won't write is wasted work; provider/model
    # discovery would also overwrite the actors section if applied. We
    # still run the idempotent post-config steps (beads, runway) below so
    # ``maverick init`` is safe to re-run on an existing project.
    if config_existed:
        if verbose:
            logger.info(
                "init_skipping_config_steps",
                reason="config_exists_and_force_false",
                config_path=str(config_path),
            )
        beads_initialized = await _init_beads(effective_path, verbose)
        runway_initialized = await _maybe_init_runway(effective_path, verbose)
        await _ensure_gitignore_entries(effective_path, verbose)
        await _untrack_bd_local_state(effective_path, verbose)
        return InitResult(
            success=True,
            config_path=str(config_path),
            preflight=preflight_result,
            git_info=git_info,
            config=None,
            detection=None,
            findings_printed=verbose,
            beads_initialized=beads_initialized,
            runway_initialized=runway_initialized,
            provider_discovery=None,
            config_existed=True,
        )

    # Step 3: Detect project type
    detection: ProjectDetectionResult | None = None

    if type_override is not None:
        # Use override - create detection result with override type
        if verbose:
            logger.info("type_override_used", project_type=type_override.value)
        detection = ProjectDetectionResult(
            primary_type=type_override,
            detected_types=(type_override,),
            confidence=DetectionConfidence.HIGH,
            findings=(f"Project type manually set to {type_override.value}",),
            markers=(),
            validation_commands=ValidationCommands.for_project_type(type_override),
            detection_method="override",
        )
    else:
        # Marker-based detection (the only path post-OpenCode-substrate)
        if verbose:
            logger.info("detecting_with_markers")
        detection = await detect_project_type(effective_path)
        if verbose:
            logger.info(
                "detection_complete",
                primary_type=detection.primary_type.value,
                confidence=detection.confidence.value,
                method=detection.detection_method,
            )

    # Step 3.5: Discover OpenCode-connected providers (best-effort)
    provider_discovery: OpenCodeDiscoveryResult | None = await _maybe_discover_providers(verbose)

    # Step 4: Generate configuration
    config = generate_config(
        git_info=git_info,
        detection=detection,
        project_type=type_override,  # Pass override if specified
        provider_discovery=provider_discovery,
    )

    if verbose:
        logger.info("config_generated")

    # Step 5: Write configuration file
    write_config(config, config_path, force=force)

    if verbose:
        logger.info("config_written", config_path=str(config_path))

    # Step 6: Initialize beads (required — refuel and fly depend on bd)
    beads_initialized = await _init_beads(effective_path, verbose)

    # Step 7: Initialize runway (best-effort)
    runway_initialized = await _maybe_init_runway(effective_path, verbose)

    # Step 8: Make sure .gitignore covers maverick's ephemeral output
    # (best-effort — never blocks init).
    await _ensure_gitignore_entries(effective_path, verbose)
    await _untrack_bd_local_state(effective_path, verbose)

    # Build and return result
    return InitResult(
        success=True,
        config_path=str(config_path),
        preflight=preflight_result,
        git_info=git_info,
        config=config,
        detection=detection,
        findings_printed=verbose,
        beads_initialized=beads_initialized,
        runway_initialized=runway_initialized,
        provider_discovery=provider_discovery,
    )
