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

import asyncio
import shutil
from pathlib import Path

from maverick.exceptions.init import ConfigExistsError, PrerequisiteError
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
    # Dataclasses
    "ProjectMarker",
    "ValidationCommands",
    "PrerequisiteCheck",
    "GitRemoteInfo",
    "ProjectDetectionResult",
    "InitPreflightResult",
    "InitResult",
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
# Beads Initialization (best-effort)
# =============================================================================

_JJ_INIT_TIMEOUT_SECONDS = 10
_BD_INIT_TIMEOUT_SECONDS = 10


async def _maybe_init_jj_colocated(project_path: Path, verbose: bool) -> bool:
    """Initialize jj in colocated mode if ``jj`` is available.

    Colocated mode (``jj git init --colocate``) shares the ``.git``
    directory so read-only Git tooling (GitPython, MCP tools) continues
    to work while jj handles write operations.

    Skips if ``.jj/`` already exists. This is best-effort: if ``jj``
    isn't installed or init fails, the error is logged but never raised.

    Args:
        project_path: Project root directory.
        verbose: Whether to log progress.

    Returns:
        True if jj was successfully initialized (or already present),
        False otherwise.
    """
    jj_dir = project_path / ".jj"
    if jj_dir.is_dir():
        if verbose:
            logger.debug("jj_already_initialized", path=str(jj_dir))
        return True

    if shutil.which("jj") is None:
        if verbose:
            logger.debug("jj_not_found", message="jj CLI not on PATH, skipping jj init")
        return False

    try:
        proc = await asyncio.create_subprocess_exec(
            "jj",
            "git",
            "init",
            "--colocate",
            cwd=str(project_path),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=_JJ_INIT_TIMEOUT_SECONDS,
        )
        if proc.returncode == 0:
            if verbose:
                logger.info("jj_colocated_initialized", path=str(jj_dir))
            return True
        else:
            logger.debug(
                "jj_init_failed",
                returncode=proc.returncode,
                stderr=stderr.decode(errors="replace").strip(),
            )
            return False
    except (TimeoutError, OSError) as exc:
        logger.debug("jj_init_error", error=str(exc))
        return False


async def _maybe_init_beads(project_path: Path, verbose: bool) -> bool:
    """Initialize beads if ``bd`` is available.

    Uses ``--force`` to handle both fresh and re-init cases. Beads are
    initialized in normal (non-stealth) mode so that ``.beads/issues.jsonl``
    is tracked in git and flows naturally with branches and merges.

    This is best-effort: if ``bd`` isn't installed or ``bd init`` fails, the
    error is logged but never raised.

    Args:
        project_path: Project root directory.
        verbose: Whether to log progress.

    Returns:
        True if beads were successfully initialized, False otherwise.
    """
    if shutil.which("bd") is None:
        if verbose:
            logger.debug(
                "bd_not_found", message="bd CLI not on PATH, skipping beads init"
            )
        return False

    try:
        proc = await asyncio.create_subprocess_exec(
            "bd",
            "init",
            "--force",
            cwd=str(project_path),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=_BD_INIT_TIMEOUT_SECONDS,
        )
        if proc.returncode == 0:
            if verbose:
                logger.info("beads_initialized", path=str(project_path / ".beads"))
            return True
        else:
            logger.debug(
                "bd_init_failed",
                returncode=proc.returncode,
                stderr=stderr.decode(errors="replace").strip(),
            )
            return False
    except (TimeoutError, OSError) as exc:
        logger.debug("bd_init_error", error=str(exc))
        return False


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

    Returns:
        InitResult with complete execution state.

    Raises:
        PrerequisiteError: If prerequisites fail.
        DetectionError: If detection fails.
        ConfigExistsError: If config exists and force=False.
        ConfigWriteError: If write fails.

    Example:
        result = await run_init(force=True)
        if result.success:
            print(f"Config written to {result.config_path}")
    """
    # Use project_path or default to cwd
    effective_path = project_path if project_path is not None else Path.cwd()
    config_path = effective_path / "maverick.yaml"

    # Check if config exists before doing expensive work
    if config_path.exists() and not force:
        raise ConfigExistsError(config_path)

    if verbose:
        logger.info("init_started", project_path=str(effective_path))

    # Step 1: Verify prerequisites
    # Skip API check if not using Claude for detection
    preflight_result = await verify_prerequisites(
        skip_api_check=not use_claude,
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

    # Step 4: Generate configuration
    config = generate_config(
        git_info=git_info,
        detection=detection,
        project_type=type_override,  # Pass override if specified
        model_id=model_id,  # Pass model ID if specified
    )

    if verbose:
        logger.info("config_generated")

    # Step 5: Write configuration file
    write_config(config, config_path, force=force)

    if verbose:
        logger.info("config_written", config_path=str(config_path))

    # Step 6: Initialize jj colocated mode (best-effort, if jj is available)
    jj_initialized = await _maybe_init_jj_colocated(effective_path, verbose)

    # Step 7: Initialize beads (best-effort, if bd is available)
    beads_initialized = await _maybe_init_beads(effective_path, verbose)

    # Build and return result
    return InitResult(
        success=True,
        config_path=str(config_path),
        preflight=preflight_result,
        git_info=git_info,
        config=config,
        detection=detection,
        findings_printed=verbose,
        jj_initialized=jj_initialized,
        beads_initialized=beads_initialized,
    )
