"""Activity for checking GitHub CLI status.

This activity verifies that the GitHub CLI (gh) is installed and
the user is authenticated. Supports both host and containerized execution.
"""

import asyncio

from temporalio import activity

from src.models.compose import ComposeEnvironment
from src.models.prereq import PrereqCheckResult
from src.utils.logging import get_structured_logger


logger = get_structured_logger("activity.gh_status")

# Remediation guidance for GitHub CLI issues
GH_NOT_INSTALLED_REMEDIATION = """GitHub CLI is not installed.

Install GitHub CLI:
  • macOS: brew install gh
  • Windows: winget install --id GitHub.cli
  • Linux: See https://github.com/cli/cli/blob/trunk/docs/install_linux.md

After installation, authenticate with:
  gh auth login

Official documentation: https://cli.github.com/
"""

GH_NOT_AUTHENTICATED_REMEDIATION = """GitHub CLI is not authenticated.

Authenticate with GitHub:
  gh auth login

Follow the prompts to authenticate via your browser or personal access token.

Official documentation: https://cli.github.com/manual/gh_auth_login
"""


@activity.defn(name="check_gh_status")
async def check_gh_status(compose_env: ComposeEnvironment | None = None) -> PrereqCheckResult:
    """Check if GitHub CLI is installed and authenticated.

    Args:
        compose_env: Optional Docker Compose environment for containerized execution

    Returns:
        PrereqCheckResult with pass/fail status and remediation guidance
    """
    logger.info(
        "gh_status_check_started",
        containerized=compose_env is not None,
        project_name=compose_env.project_name if compose_env else None,
    )

    # If compose_env provided, run in container
    if compose_env:
        return await _check_gh_status_in_container(compose_env)

    # Otherwise, run on host (original behavior)
    return await _check_gh_status_on_host()


async def _check_gh_status_on_host() -> PrereqCheckResult:
    """Check gh status on the host machine."""
    try:
        # Execute gh auth status
        process = await asyncio.create_subprocess_exec(
            "gh", "auth", "status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10.0
            )
        except asyncio.TimeoutError:  # noqa: UP041
            logger.error("gh_status_timeout", timeout_seconds=10.0)
            return PrereqCheckResult(
                tool="gh",
                status="fail",
                message="GitHub CLI check timed out after 10 seconds",
                remediation="Check if gh is functioning properly and try again"
            )

        # gh auth status returns 0 if authenticated, 1 if not
        if process.returncode == 0:
            logger.info("gh_status_authenticated")
            return PrereqCheckResult(
                tool="gh",
                status="pass",
                message="GitHub CLI is installed and authenticated",
                remediation=None
            )
        else:
            # Parse stderr for helpful context
            stderr_text = stderr.decode('utf-8', errors='replace')
            logger.warning("gh_status_not_authenticated", stderr=stderr_text)

            return PrereqCheckResult(
                tool="gh",
                status="fail",
                message="GitHub CLI is not authenticated",
                remediation=GH_NOT_AUTHENTICATED_REMEDIATION.strip()
            )

    except FileNotFoundError:
        logger.error("gh_status_not_installed", error="command_not_found")
        return PrereqCheckResult(
            tool="gh",
            status="fail",
            message="GitHub CLI is not installed",
            remediation=GH_NOT_INSTALLED_REMEDIATION.strip()
        )
    except Exception as e:
        logger.error("gh_status_error", error_type=type(e).__name__, error_message=str(e))
        return PrereqCheckResult(
            tool="gh",
            status="fail",
            message=f"Error checking GitHub CLI: {str(e)}",
            remediation="Check if gh is functioning properly and try again"
        )


async def _check_gh_status_in_container(compose_env: ComposeEnvironment) -> PrereqCheckResult:
    """Check gh status inside a Docker Compose container.

    Args:
        compose_env: Docker Compose environment details

    Returns:
        PrereqCheckResult with pass/fail status and remediation guidance
    """
    try:
        # Execute gh auth status in container
        cmd = [
            "docker",
            "compose",
            "-p",
            compose_env.project_name,
            "exec",
            "-T",  # Disable pseudo-TTY
            compose_env.target_service,
            "gh",
            "auth",
            "status",
        ]

        logger.info(
            "gh_status_container_exec",
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
            logger.error("gh_status_container_timeout", timeout_seconds=10.0, project_name=compose_env.project_name)
            return PrereqCheckResult(
                tool="gh",
                status="fail",
                message="GitHub CLI check timed out after 10 seconds in container",
                remediation="Check if gh is functioning properly in the container and try again"
            )

        # gh auth status returns 0 if authenticated, 1 if not
        if process.returncode == 0:
            logger.info("gh_status_container_authenticated", project_name=compose_env.project_name)
            return PrereqCheckResult(
                tool="gh",
                status="pass",
                message="GitHub CLI is installed and authenticated (in container)",
                remediation=None
            )
        else:
            # Parse stderr for helpful context
            stderr_text = stderr.decode('utf-8', errors='replace')
            logger.warning("gh_status_container_not_authenticated", stderr=stderr_text, project_name=compose_env.project_name)

            return PrereqCheckResult(
                tool="gh",
                status="fail",
                message="GitHub CLI is not authenticated (in container)",
                remediation=GH_NOT_AUTHENTICATED_REMEDIATION.strip()
            )

    except FileNotFoundError:
        logger.error("gh_status_container_not_installed", error="command_not_found", project_name=compose_env.project_name)
        return PrereqCheckResult(
            tool="gh",
            status="fail",
            message="GitHub CLI is not installed in the container",
            remediation=GH_NOT_INSTALLED_REMEDIATION.strip()
        )
    except Exception as e:
        logger.error("gh_status_container_error", error_type=type(e).__name__, error_message=str(e), project_name=compose_env.project_name)
        return PrereqCheckResult(
            tool="gh",
            status="fail",
            message=f"Error checking GitHub CLI in container: {str(e)}",
            remediation="Check if gh is functioning properly in the container and try again"
        )
