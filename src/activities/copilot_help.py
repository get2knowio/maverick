"""Activity for checking Copilot CLI availability.

This activity verifies that the standalone Copilot CLI is available
and responds to basic commands. Supports both host and containerized execution.
"""

import asyncio

from temporalio import activity

from src.models.compose import ComposeEnvironment
from src.models.prereq import PrereqCheckResult
from src.utils.logging import get_structured_logger


logger = get_structured_logger("activity.copilot_help")

# Remediation guidance for Copilot CLI issues
COPILOT_NOT_INSTALLED_REMEDIATION = """Copilot CLI is not installed.

Install the standalone Copilot CLI:
  • Download from: https://github.com/github/gh-copilot
  • Or install via GitHub CLI extension:
    gh extension install github/gh-copilot

Note: This check requires the standalone 'copilot' binary to be available on your PATH.

Official documentation: https://docs.github.com/en/copilot/github-copilot-in-the-cli
"""

COPILOT_FAILED_REMEDIATION = """Copilot CLI is installed but failed to execute properly.

Troubleshooting steps:
  1. Verify the copilot binary is executable: which copilot
  2. Check if there are any permission issues
  3. Try running: copilot help

If issues persist, try reinstalling from: https://github.com/github/gh-copilot
"""


@activity.defn(name="check_copilot_help")
async def check_copilot_help(compose_env: ComposeEnvironment | None = None) -> PrereqCheckResult:
    """Check if Copilot CLI is available and responds to help command.

    Args:
        compose_env: Optional Docker Compose environment for containerized execution

    Returns:
        PrereqCheckResult with pass/fail status and remediation guidance
    """
    logger.info(
        "copilot_help_check_started",
        containerized=compose_env is not None,
        project_name=compose_env.project_name if compose_env else None,
    )

    # If compose_env provided, run in container
    if compose_env:
        return await _check_copilot_help_in_container(compose_env)

    # Otherwise, run on host (original behavior)
    return await _check_copilot_help_on_host()


async def _check_copilot_help_on_host() -> PrereqCheckResult:
    """Check copilot help on the host machine."""
    try:
        # Execute copilot help
        process = await asyncio.create_subprocess_exec(
            "copilot", "help",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10.0
            )
        except asyncio.TimeoutError:  # noqa: UP041
            logger.error("copilot_help_timeout", timeout_seconds=10.0)
            return PrereqCheckResult(
                tool="copilot",
                status="fail",
                message="Copilot CLI check timed out after 10 seconds",
                remediation="Check if copilot is functioning properly and try again"
            )

        # copilot help should return 0 if successful
        if process.returncode == 0:
            logger.info("copilot_help_available")
            return PrereqCheckResult(
                tool="copilot",
                status="pass",
                message="Copilot CLI is available and ready",
                remediation=None
            )
        else:
            # Command failed
            stderr_text = stderr.decode('utf-8', errors='replace')
            logger.warning("copilot_help_command_failed", exit_code=process.returncode, stderr=stderr_text)

            return PrereqCheckResult(
                tool="copilot",
                status="fail",
                message=f"Copilot CLI command failed with exit code {process.returncode}",
                remediation=COPILOT_FAILED_REMEDIATION.strip()
            )

    except FileNotFoundError:
        logger.error("copilot_help_not_installed", error="command_not_found")
        return PrereqCheckResult(
            tool="copilot",
            status="fail",
            message="Copilot CLI is not installed or not found in PATH",
            remediation=COPILOT_NOT_INSTALLED_REMEDIATION.strip()
        )
    except Exception as e:
        logger.error("copilot_help_error", error_type=type(e).__name__, error_message=str(e))
        return PrereqCheckResult(
            tool="copilot",
            status="fail",
            message=f"Error checking Copilot CLI: {str(e)}",
            remediation="Check if copilot is functioning properly and try again"
        )


async def _check_copilot_help_in_container(compose_env: ComposeEnvironment) -> PrereqCheckResult:
    """Check copilot help inside a Docker Compose container.

    Args:
        compose_env: Docker Compose environment details

    Returns:
        PrereqCheckResult with pass/fail status and remediation guidance
    """
    try:
        # Execute copilot help in container
        cmd = [
            "docker",
            "compose",
            "-p",
            compose_env.project_name,
            "exec",
            "-T",  # Disable pseudo-TTY
            compose_env.target_service,
            "copilot",
            "help",
        ]

        logger.info(
            "copilot_help_container_exec",
            command=" ".join(cmd),
            project_name=compose_env.project_name,
            service=compose_env.target_service,
        )

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10.0
            )
        except asyncio.TimeoutError:  # noqa: UP041
            logger.error("copilot_help_container_timeout", timeout_seconds=10.0, project_name=compose_env.project_name)
            return PrereqCheckResult(
                tool="copilot",
                status="fail",
                message="Copilot CLI check timed out after 10 seconds in container",
                remediation="Check if copilot is functioning properly in the container and try again"
            )

        # copilot help should return 0 if successful
        if process.returncode == 0:
            logger.info("copilot_help_container_available", project_name=compose_env.project_name)
            return PrereqCheckResult(
                tool="copilot",
                status="pass",
                message="Copilot CLI is available and ready (in container)",
                remediation=None
            )
        else:
            # Command failed
            stderr_text = stderr.decode('utf-8', errors='replace')
            logger.warning("copilot_help_container_command_failed", exit_code=process.returncode, stderr=stderr_text, project_name=compose_env.project_name)

            return PrereqCheckResult(
                tool="copilot",
                status="fail",
                message=f"Copilot CLI command failed with exit code {process.returncode} (in container)",
                remediation=COPILOT_FAILED_REMEDIATION.strip()
            )

    except FileNotFoundError:
        logger.error("copilot_help_container_not_installed", error="command_not_found", project_name=compose_env.project_name)
        return PrereqCheckResult(
            tool="copilot",
            status="fail",
            message="Copilot CLI is not installed or not found in PATH (in container)",
            remediation=COPILOT_NOT_INSTALLED_REMEDIATION.strip()
        )
    except Exception as e:
        logger.error("copilot_help_container_error", error_type=type(e).__name__, error_message=str(e), project_name=compose_env.project_name)
        return PrereqCheckResult(
            tool="copilot",
            status="fail",
            message=f"Error checking Copilot CLI in container: {str(e)}",
            remediation="Check if copilot is functioning properly in the container and try again"
        )
