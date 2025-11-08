"""Activity for checking Copilot CLI availability.

This activity verifies that the standalone Copilot CLI is available
and responds to basic commands.
"""

import asyncio

from temporalio import activity

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
async def check_copilot_help() -> PrereqCheckResult:
    """Check if Copilot CLI is available and responds to help command.

    Returns:
        PrereqCheckResult with pass/fail status and remediation guidance
    """
    logger.info("copilot_help_check_started")

    try:
        # Execute copilot help
        process = await asyncio.create_subprocess_exec(
            "copilot", "help", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)
        except TimeoutError:
            logger.error("copilot_help_timeout", timeout_seconds=10.0)
            return PrereqCheckResult(
                tool="copilot",
                status="fail",
                message="Copilot CLI check timed out after 10 seconds",
                remediation="Check if copilot is functioning properly and try again",
            )

        # copilot help should return 0 if successful
        if process.returncode == 0:
            logger.info("copilot_help_available")
            return PrereqCheckResult(
                tool="copilot", status="pass", message="Copilot CLI is available and ready", remediation=None
            )
        else:
            # Command failed
            stderr_text = stderr.decode("utf-8", errors="replace")
            logger.warning("copilot_help_command_failed", exit_code=process.returncode, stderr=stderr_text)

            return PrereqCheckResult(
                tool="copilot",
                status="fail",
                message=f"Copilot CLI command failed with exit code {process.returncode}",
                remediation=COPILOT_FAILED_REMEDIATION.strip(),
            )

    except FileNotFoundError:
        logger.error("copilot_help_not_installed", error="command_not_found")
        return PrereqCheckResult(
            tool="copilot",
            status="fail",
            message="Copilot CLI is not installed or not found in PATH",
            remediation=COPILOT_NOT_INSTALLED_REMEDIATION.strip(),
        )
    except Exception as e:
        logger.error("copilot_help_error", error_type=type(e).__name__, error_message=str(e))
        return PrereqCheckResult(
            tool="copilot",
            status="fail",
            message=f"Error checking Copilot CLI: {str(e)}",
            remediation="Check if copilot is functioning properly and try again",
        )
