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
from maverick.init.prereqs import verify_prerequisites
from maverick.init.provider_discovery import (
    PROVIDER_PREFERENCE_ORDER,
    ProviderDiscoveryResult,
    ProviderProbeResult,
)
from maverick.logging import get_logger

__all__ = [
    # Functions
    "run_init",
    "parse_git_remote",
    "resolve_model_id",
    # Enums
    "ProjectType",
    "DetectionConfidence",
    "PreflightStatus",
    # Constants
    "MARKER_FILE_MAP",
    "VALIDATION_DEFAULTS",
    "PYTHON_DEFAULTS",
    "PROVIDER_PREFERENCE_ORDER",
    # Dataclasses
    "ProjectMarker",
    "ValidationCommands",
    "PrerequisiteCheck",
    "GitRemoteInfo",
    "ProjectDetectionResult",
    "InitPreflightResult",
    "InitResult",
    "ProviderProbeResult",
    "ProviderDiscoveryResult",
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
    """Reset stale bd state when metadata is corrupt or absent.

    Three failure modes have to be handled:

    1. Older bd versions wrote ``dolt_database`` values that the current Dolt
       engine refuses to open (typically because of hyphens carried over from
       the repository directory name). bd init then silently keeps the bad
       name even when given a fresh ``--prefix``.
    2. A previous ``bd init`` attempt may have aborted mid-clone, leaving a
       partial ``embeddeddolt/`` directory that the next bd command rejects
       with "database exists".
    3. ``metadata.json`` exists with a valid ``dolt_database`` but is missing
       ``issue_prefix``. ``bd create`` then fails with
       ``database not initialized: issue_prefix config is missing``, and
       ``bd init`` refuses to re-init because ``embeddeddolt/`` exists. The
       only way out is to wipe the half-state and start fresh — there's no
       data to preserve, since bd needs ``issue_prefix`` to create issues.

    Routes:

    - **Valid metadata, no action**: a healthy ``.beads/`` is left intact so
      :meth:`BeadClient.init_or_bootstrap` can take the SKIP branch.
    - **Invalid metadata** (any of the three failure modes): drop
      ``metadata.json`` *and* wipe the embedded Dolt store; the next
      lifecycle call re-creates them cleanly.
    - **No metadata**: leave the directory alone unless server-mode artifacts
      are present from a half-shut-down previous run; those are always safe
      to remove.
    """
    beads_dir = project_path / ".beads"
    metadata_path = beads_dir / "metadata.json"

    metadata_invalid = False
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text())
        except (OSError, ValueError):
            metadata = None
        if not isinstance(metadata, dict):
            metadata_invalid = True
        else:
            db_name = metadata.get("dolt_database")
            issue_prefix = metadata.get("issue_prefix")
            if not (isinstance(db_name, str) and _is_valid_dolt_db_name(db_name)):
                metadata_invalid = True
            elif not (isinstance(issue_prefix, str) and issue_prefix.strip()):
                # bd's ``bd create`` requires issue_prefix; without it the
                # database is unusable. Treat as invalid so we wipe and
                # re-init from scratch.
                metadata_invalid = True
        if metadata_invalid:
            try:
                metadata_path.unlink()
            except OSError:
                pass

    # Only wipe Dolt directories when we have evidence of corruption.
    # Otherwise a healthy local DB looks "initialized" to the state probe
    # and the SKIP branch can avoid an unnecessary lifecycle call.
    if metadata_invalid:
        embedded_dir = beads_dir / "embeddeddolt"
        if embedded_dir.is_dir():
            shutil.rmtree(embedded_dir, ignore_errors=True)
        server_dir = beads_dir / "dolt"
        if server_dir.is_dir():
            shutil.rmtree(server_dir, ignore_errors=True)

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
# Provider Discovery (best-effort)
# =============================================================================


async def _maybe_discover_providers(
    verbose: bool,
) -> ProviderDiscoveryResult | None:
    """Discover ACP providers on PATH.

    Best-effort: errors are logged but never raised.

    Args:
        verbose: Whether to log progress.

    Returns:
        Discovery result, or None if discovery failed.
    """
    try:
        from maverick.init.provider_discovery import discover_providers

        result = await discover_providers()
        if verbose:
            found = [p.name for p in result.found_providers]
            logger.info(
                "providers_discovered",
                found=found,
                default=result.default_provider,
                duration_ms=result.duration_ms,
            )
        return result
    except Exception as exc:
        logger.debug("provider_discovery_error", error=str(exc))
        return None


# =============================================================================
# Main Entry Point
# =============================================================================


async def run_init(
    *,
    project_path: Path | None = None,
    type_override: ProjectType | None = None,
    use_claude: bool = True,
    force: bool = False,
    verbose: bool = False,
    model_id: str | None = None,
    skip_providers: bool = False,
) -> InitResult:
    """Execute maverick init workflow.

    Orchestrates the complete init workflow:
    1. Verify prerequisites (git, gh, API key, etc.)
    2. Parse git remote information
    3. Detect project type (with Claude or markers only)
    4. Generate configuration
    5. Write maverick.yaml

    Args:
        project_path: Path to project root. Defaults to cwd.
        type_override: Force specific project type (skips detection).
        use_claude: Use Claude for detection (False = marker-only).
        force: Overwrite existing config file.
        verbose: Enable verbose output.
        model_id: Claude model ID to use in config. Defaults to latest sonnet.
        skip_providers: Skip ACP provider discovery.

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
    elif use_claude:
        # Use Claude for detection
        if verbose:
            logger.info("detecting_with_claude")
        detection = await detect_project_type(
            effective_path,
            use_claude=True,
        )
        if verbose:
            logger.info(
                "detection_complete",
                primary_type=detection.primary_type.value,
                confidence=detection.confidence.value,
                method=detection.detection_method,
            )
    else:
        # Marker-only detection (no Claude)
        if verbose:
            logger.info("detecting_with_markers")
        detection = await detect_project_type(
            effective_path,
            use_claude=False,
        )
        if verbose:
            logger.info(
                "detection_complete",
                primary_type=detection.primary_type.value,
                confidence=detection.confidence.value,
                method=detection.detection_method,
            )

    # Step 3.5: Discover ACP providers (best-effort)
    provider_discovery: ProviderDiscoveryResult | None = None
    if not skip_providers:
        provider_discovery = await _maybe_discover_providers(verbose)

    # Step 4: Generate configuration
    config = generate_config(
        git_info=git_info,
        detection=detection,
        project_type=type_override,  # Pass override if specified
        model_id=model_id,  # Pass model ID if specified
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
