"""Docker Compose lifecycle management activities.

This module provides Temporal activities for managing Docker Compose environments,
including startup, health checking, validation execution, and cleanup.
"""

import asyncio
import hashlib
import json
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from temporalio import activity

from src.models.compose import (
    ComposeCleanupParams,
    ComposeConfig,
    ComposeEnvironment,
    ComposeUpResult,
    ValidateInContainerParams,
    ValidationResult,
    resolve_target_service,
)
from src.utils.logging import get_structured_logger


logger = get_structured_logger("activity.compose")


@activity.defn
async def compose_up_activity(config: ComposeConfig) -> ComposeUpResult:
    """Start Docker Compose environment with health checks.

    Creates temporary compose file, starts environment, polls for health status,
    and returns environment details on success.

    Args:
        config: Docker Compose configuration with YAML content and settings

    Returns:
        ComposeUpResult with environment details or error information

    Algorithm:
        1. Resolve target service using resolve_target_service()
        2. Create temporary directory for compose file
        3. Write yaml_content to temporary file
        4. Execute `docker compose -p <project> -f <file> up -d`
        5. Poll health status using exponential backoff
        6. Return environment details on healthy status
        7. Return error on timeout or unhealthy status
    """
    start_time = time.time()

    # Get activity info for unique project naming
    info = activity.info()

    # Create short deterministic hash from workflow ID + run ID
    # This keeps project names readable while ensuring uniqueness
    combined = f"{info.workflow_id}:{info.workflow_run_id}"
    hash_digest = hashlib.sha256(combined.encode()).hexdigest()[:8]
    project_name = f"maverick-{hash_digest}"

    logger.info(
        "compose_up_starting",
        project_name=project_name,
        workflow_id=info.workflow_id,
        run_id=info.workflow_run_id,
    )

    try:
        # Resolve target service
        target_service = resolve_target_service(config)
        logger.info("target_service_resolved", service=target_service, project_name=project_name)

    except ValueError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("target_service_resolution_failed", error=str(e), project_name=project_name)
        return ComposeUpResult(
            success=False,
            environment=None,
            error_message=str(e),
            error_type="validation_error",
            duration_ms=duration_ms,
        )

    # Create temporary directory and write compose file
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="maverick-compose-")
        compose_file = Path(temp_dir) / "docker-compose.yml"
        compose_file.write_text(config.yaml_content, encoding="utf-8")

        logger.info(
            "compose_file_created",
            file_path=str(compose_file),
            project_name=project_name,
        )

        # Start Docker Compose environment
        cmd = [
            "docker",
            "compose",
            "-p",
            project_name,
            "-f",
            str(compose_file),
            "up",
            "-d",
        ]

        logger.info("docker_compose_up_starting", command=" ".join(cmd), project_name=project_name)

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=config.startup_timeout_seconds,
        )

        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf-8", errors="replace")
            stderr_lines = stderr_text.splitlines()
            stderr_excerpt = "\n".join(stderr_lines[-50:])

            duration_ms = int((time.time() - start_time) * 1000)

            # Categorize error
            error_lower = stderr_text.lower()
            if "docker daemon" in error_lower or "cannot connect" in error_lower:
                error_type = "docker_unavailable"
            else:
                error_type = "startup_failed"

            logger.error(
                "docker_compose_up_failed",
                return_code=result.returncode,
                error_type=error_type,
                stderr_excerpt=stderr_excerpt[:500],
                project_name=project_name,
            )

            return ComposeUpResult(
                success=False,
                environment=None,
                error_message=f"Docker Compose startup failed: {stderr_excerpt[:200]}",
                error_type=error_type,
                duration_ms=duration_ms,
                stderr_excerpt=stderr_excerpt,
            )

        # Poll for health status with exponential backoff
        poll_interval = 1  # Start with 1 second
        max_poll_interval = 30  # Cap at 30 seconds
        elapsed = 0

        logger.info("health_check_polling_started", project_name=project_name)

        while elapsed < config.startup_timeout_seconds:
            # Check health status
            ps_cmd = [
                "docker",
                "compose",
                "-p",
                project_name,
                "ps",
                "--format",
                "json",
            ]

            ps_result = subprocess.run(ps_cmd, capture_output=True, timeout=30)

            if ps_result.returncode == 0:
                ps_output = ps_result.stdout.decode("utf-8", errors="replace")

                # Parse JSON output (one JSON object per line)
                services_status = {}
                for line in ps_output.strip().splitlines():
                    if line.strip():
                        try:
                            service_info = json.loads(line)
                            service_name = service_info.get("Service", "")
                            health = service_info.get("Health", "")
                            services_status[service_name] = health
                        except json.JSONDecodeError:
                            continue

                # Check target service health
                target_health = services_status.get(target_service, "")

                logger.info(
                    "health_check_status",
                    service=target_service,
                    health=target_health,
                    elapsed_seconds=elapsed,
                    project_name=project_name,
                )

                if target_health == "healthy":
                    # Success! Get container IDs
                    container_ids = {}
                    for line in ps_output.strip().splitlines():
                        if line.strip():
                            try:
                                service_info = json.loads(line)
                                svc_name = service_info.get("Service", "")
                                container_id = service_info.get("ID", "")
                                if svc_name and container_id:
                                    container_ids[svc_name] = container_id
                            except json.JSONDecodeError:
                                continue

                    duration_ms = int((time.time() - start_time) * 1000)
                    environment = ComposeEnvironment(
                        project_name=project_name,
                        target_service=target_service,
                        health_status="healthy",
                        container_ids=container_ids,
                        started_at=datetime.now(UTC).isoformat(),
                    )

                    logger.info(
                        "compose_up_success",
                        project_name=project_name,
                        duration_ms=duration_ms,
                        target_service=target_service,
                    )

                    return ComposeUpResult(
                        success=True,
                        environment=environment,
                        error_message=None,
                        error_type="none",
                        duration_ms=duration_ms,
                    )

                elif target_health == "unhealthy":
                    # Service explicitly unhealthy
                    duration_ms = int((time.time() - start_time) * 1000)
                    logger.error(
                        "health_check_failed",
                        service=target_service,
                        health=target_health,
                        project_name=project_name,
                    )

                    return ComposeUpResult(
                        success=False,
                        environment=None,
                        error_message=f"Service '{target_service}' health check failed (status: unhealthy)",
                        error_type="health_check_failed",
                        duration_ms=duration_ms,
                    )

            # Wait with exponential backoff
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            poll_interval = min(poll_interval * 2, max_poll_interval)

        # Timeout reached
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "health_check_timeout",
            service=target_service,
            timeout_seconds=config.startup_timeout_seconds,
            project_name=project_name,
        )

        return ComposeUpResult(
            success=False,
            environment=None,
            error_message=f"Health check timeout after {config.startup_timeout_seconds}s waiting for '{target_service}' to become healthy",
            error_type="health_check_timeout",
            duration_ms=duration_ms,
        )

    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("docker_compose_timeout", project_name=project_name)
        return ComposeUpResult(
            success=False,
            environment=None,
            error_message=f"Docker Compose operation timed out after {config.startup_timeout_seconds}s",
            error_type="startup_failed",
            duration_ms=duration_ms,
        )

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("compose_up_unexpected_error", error=str(e), error_type=type(e).__name__, project_name=project_name)
        return ComposeUpResult(
            success=False,
            environment=None,
            error_message=f"Unexpected error: {str(e)}",
            error_type="startup_failed",
            duration_ms=duration_ms,
        )

    # Note: temp_dir cleanup is intentionally NOT done here
    # The compose file must persist while the environment is running


@activity.defn
async def compose_down_activity(params: ComposeCleanupParams) -> dict[str, str | bool]:
    """Tear down Docker Compose environment.

    Removes Docker Compose resources based on cleanup mode.

    Args:
        params: Cleanup parameters with project name and mode

    Returns:
        Dict with 'cleaned' (bool) and optional 'instructions' (str)

    Modes:
        - graceful: Execute `docker compose -p <project> down -v`
        - preserve: Log manual cleanup instructions only
    """
    logger.info(
        "compose_down_starting",
        project_name=params.project_name,
        mode=params.mode,
    )

    if params.mode == "preserve":
        # Preserve mode: Don't clean up, just provide instructions
        instructions = (
            f"Docker Compose environment preserved for troubleshooting.\n"
            f"Project name: {params.project_name}\n"
            f"To inspect: docker compose -p {params.project_name} ps\n"
            f"To view logs: docker compose -p {params.project_name} logs\n"
            f"To clean up manually: docker compose -p {params.project_name} down -v"
        )

        logger.info(
            "compose_down_preserved",
            project_name=params.project_name,
            instructions=instructions,
        )

        return {
            "cleaned": False,
            "instructions": instructions,
        }

    # Graceful mode: Clean up resources
    try:
        cmd = [
            "docker",
            "compose",
            "-p",
            params.project_name,
            "down",
            "-v",  # Remove volumes
        ]

        logger.info(
            "docker_compose_down_starting",
            command=" ".join(cmd),
            project_name=params.project_name,
        )

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=60,  # 60 second timeout for cleanup
        )

        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf-8", errors="replace")
            logger.error(
                "docker_compose_down_failed",
                return_code=result.returncode,
                stderr=stderr_text[:500],
                project_name=params.project_name,
            )

            return {
                "cleaned": False,
                "instructions": f"Cleanup failed: {stderr_text[:200]}. Manual cleanup required: docker compose -p {params.project_name} down -v",
            }

        logger.info(
            "compose_down_success",
            project_name=params.project_name,
        )

        return {
            "cleaned": True,
        }

    except subprocess.TimeoutExpired:
        logger.error(
            "docker_compose_down_timeout",
            project_name=params.project_name,
        )
        return {
            "cleaned": False,
            "instructions": f"Cleanup timed out. Manual cleanup required: docker compose -p {params.project_name} down -v",
        }

    except Exception as e:
        logger.error(
            "compose_down_unexpected_error",
            error=str(e),
            error_type=type(e).__name__,
            project_name=params.project_name,
        )
        return {
            "cleaned": False,
            "instructions": f"Cleanup error: {str(e)}. Manual cleanup required: docker compose -p {params.project_name} down -v",
        }


@activity.defn
async def validate_in_container_activity(
    params: ValidateInContainerParams,
) -> ValidationResult:
    """Execute validation command inside target container.

    Runs command via `docker compose exec <service> <command>`.

    Args:
        params: Validation parameters with project, service, command, and timeout

    Returns:
        ValidationResult with command output and status

    Algorithm:
        1. Build command: `docker compose -p <project> exec -T <service> <command>`
        2. Execute with timeout from params
        3. Capture stdout, stderr, return code
        4. Track duration using time measurements
        5. Return ValidationResult with all details
    """
    start_time = time.time()

    logger.info(
        "validate_in_container_starting",
        project_name=params.project_name,
        service_name=params.service_name,
        command=params.command,
    )

    try:
        # Build docker compose exec command
        cmd = [
            "docker",
            "compose",
            "-p",
            params.project_name,
            "exec",
            "-T",  # Disable pseudo-TTY allocation
            params.service_name,
        ] + params.command

        logger.info(
            "docker_compose_exec_starting",
            command=" ".join(cmd),
            project_name=params.project_name,
        )

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=params.timeout_seconds,
        )

        stdout_text = result.stdout.decode("utf-8", errors="replace")
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        duration_ms = int((time.time() - start_time) * 1000)

        success = result.returncode == 0

        logger.info(
            "validate_in_container_complete",
            return_code=result.returncode,
            success=success,
            duration_ms=duration_ms,
            project_name=params.project_name,
        )

        return ValidationResult(
            success=success,
            stdout=stdout_text,
            stderr=stderr_text,
            return_code=result.returncode,
            duration_ms=duration_ms,
        )

    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "validate_in_container_timeout",
            timeout_seconds=params.timeout_seconds,
            project_name=params.project_name,
        )

        return ValidationResult(
            success=False,
            stdout="",
            stderr=f"Command timed out after {params.timeout_seconds}s",
            return_code=-1,
            duration_ms=duration_ms,
        )

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "validate_in_container_unexpected_error",
            error=str(e),
            error_type=type(e).__name__,
            project_name=params.project_name,
        )

        return ValidationResult(
            success=False,
            stdout="",
            stderr=f"Unexpected error: {str(e)}",
            return_code=-1,
            duration_ms=duration_ms,
        )
