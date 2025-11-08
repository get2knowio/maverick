"""Activity for checking GitHub CLI status.

This activity verifies that the GitHub CLI (gh) is installed and
the user is authenticated.
"""

import asyncio

from temporalio import activity

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
async def check_gh_status() -> PrereqCheckResult:
    """Check if GitHub CLI is installed and authenticated.

    Returns:
        PrereqCheckResult with pass/fail status and remediation guidance
    """
    logger.info("gh_status_check_started")

    try:
        # Execute gh auth status
        process = await asyncio.create_subprocess_exec(
            "gh", "auth", "status", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)
        except TimeoutError:
            logger.error("gh_status_timeout", timeout_seconds=10.0)
            return PrereqCheckResult(
                tool="gh",
                status="fail",
                message="GitHub CLI check timed out after 10 seconds",
                remediation="Check if gh is functioning properly and try again",
            )

        # gh auth status returns 0 if authenticated, 1 if not
        if process.returncode == 0:
            logger.info("gh_status_authenticated")
            return PrereqCheckResult(
                tool="gh", status="pass", message="GitHub CLI is installed and authenticated", remediation=None
            )
        else:
            # Parse stderr for helpful context
            stderr_text = stderr.decode("utf-8", errors="replace")
            logger.warning("gh_status_not_authenticated", stderr=stderr_text)

            return PrereqCheckResult(
                tool="gh",
                status="fail",
                message="GitHub CLI is not authenticated",
                remediation=GH_NOT_AUTHENTICATED_REMEDIATION.strip(),
            )

    except FileNotFoundError:
        logger.error("gh_status_not_installed", error="command_not_found")
        return PrereqCheckResult(
            tool="gh",
            status="fail",
            message="GitHub CLI is not installed",
            remediation=GH_NOT_INSTALLED_REMEDIATION.strip(),
        )
    except Exception as e:
        logger.error("gh_status_error", error_type=type(e).__name__, error_message=str(e))
        return PrereqCheckResult(
            tool="gh",
            status="fail",
            message=f"Error checking GitHub CLI: {str(e)}",
            remediation="Check if gh is functioning properly and try again",
        )
