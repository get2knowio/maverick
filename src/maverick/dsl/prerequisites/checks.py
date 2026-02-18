"""Built-in prerequisite check functions.

This module consolidates all built-in prerequisite checks into a single
location. Each check is registered with the global prerequisite_registry.

Check Catalog:
- git: Git CLI is available
- git_repo: Current directory is a Git repository
- git_identity: Git user.name and user.email are configured
- git_remote: Git remote origin is configured
- gh: GitHub CLI is available
- gh_auth: GitHub CLI is authenticated
- anthropic_key: ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN is set
- anthropic_api: Anthropic API is accessible (network check)
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time

from maverick.dsl.prerequisites.models import PrerequisiteResult
from maverick.dsl.prerequisites.registry import prerequisite_registry
from maverick.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Git Prerequisites
# =============================================================================


@prerequisite_registry.register(
    name="git",
    display_name="Git CLI",
    cost=1,
    remediation="Install Git from https://git-scm.com/",
)
async def check_git() -> PrerequisiteResult:
    """Check that Git CLI is available on PATH."""
    start = time.monotonic()

    if shutil.which("git") is None:
        return PrerequisiteResult(
            success=False,
            message="Git is not installed or not on PATH",
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    return PrerequisiteResult(
        success=True,
        message="Git CLI found",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


@prerequisite_registry.register(
    name="git_repo",
    display_name="Git Repository",
    dependencies=("git",),
    cost=1,
    remediation="Run 'git init' or navigate to an existing git repository",
)
async def check_git_repo() -> PrerequisiteResult:
    """Check that current directory is a Git repository."""
    start = time.monotonic()

    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                "git",
                "rev-parse",
                "--git-dir",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=5,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode().strip() if stderr else "Not a git repository"
            return PrerequisiteResult(
                success=False,
                message=f"Not in a Git repository: {error_msg}",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        git_dir = stdout.decode().strip()
        return PrerequisiteResult(
            success=True,
            message=f"Git repository found ({git_dir})",
            duration_ms=int((time.monotonic() - start) * 1000),
            details={"git_dir": git_dir},
        )

    except TimeoutError:
        return PrerequisiteResult(
            success=False,
            message="Git repository check timed out",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except OSError as e:
        return PrerequisiteResult(
            success=False,
            message=f"Git repository check failed: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


@prerequisite_registry.register(
    name="git_identity",
    display_name="Git Identity",
    dependencies=("git",),
    cost=1,
    remediation=(
        "Configure your Git identity:\n"
        "  git config --global user.name 'Your Name'\n"
        "  git config --global user.email 'you@example.com'"
    ),
)
async def check_git_identity() -> PrerequisiteResult:
    """Check that Git user.name and user.email are configured."""
    start = time.monotonic()
    errors = []
    details: dict[str, str] = {}

    try:
        # Check user.name
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                "git",
                "config",
                "user.name",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=5,
        )
        stdout, _ = await proc.communicate()
        user_name = stdout.decode().strip() if stdout else ""

        if proc.returncode != 0 or not user_name:
            errors.append("Git user.name is not configured")
        else:
            details["user_name"] = user_name

        # Check user.email
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                "git",
                "config",
                "user.email",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=5,
        )
        stdout, _ = await proc.communicate()
        user_email = stdout.decode().strip() if stdout else ""

        if proc.returncode != 0 or not user_email:
            errors.append("Git user.email is not configured")
        else:
            details["user_email"] = user_email

        duration_ms = int((time.monotonic() - start) * 1000)

        if errors:
            return PrerequisiteResult(
                success=False,
                message="; ".join(errors),
                duration_ms=duration_ms,
                details=details if details else None,
            )

        return PrerequisiteResult(
            success=True,
            message=f"Git identity configured: {user_name} <{user_email}>",
            duration_ms=duration_ms,
            details=details,
        )

    except TimeoutError:
        return PrerequisiteResult(
            success=False,
            message="Git identity check timed out",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except OSError as e:
        return PrerequisiteResult(
            success=False,
            message=f"Git identity check failed: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


@prerequisite_registry.register(
    name="git_remote",
    display_name="Git Remote",
    dependencies=("git_repo",),
    cost=1,
    remediation="Add a remote: git remote add origin <url>",
)
async def check_git_remote() -> PrerequisiteResult:
    """Check that Git remote origin is configured."""
    start = time.monotonic()

    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                "git",
                "remote",
                "get-url",
                "origin",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=5,
        )
        stdout, _ = await proc.communicate()

        if proc.returncode != 0:
            return PrerequisiteResult(
                success=False,
                message="Git remote 'origin' is not configured",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        remote_url = stdout.decode().strip()
        return PrerequisiteResult(
            success=True,
            message=f"Git remote origin: {remote_url}",
            duration_ms=int((time.monotonic() - start) * 1000),
            details={"remote_url": remote_url},
        )

    except TimeoutError:
        return PrerequisiteResult(
            success=False,
            message="Git remote check timed out",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except OSError as e:
        return PrerequisiteResult(
            success=False,
            message=f"Git remote check failed: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


# =============================================================================
# Jujutsu (jj) Prerequisites
# =============================================================================


@prerequisite_registry.register(
    name="jj",
    display_name="Jujutsu CLI",
    cost=1,
    remediation="Install Jujutsu from https://martinvonz.github.io/jj/latest/install-and-setup/",
)
async def check_jj() -> PrerequisiteResult:
    """Check that Jujutsu CLI (jj) is available on PATH."""
    start = time.monotonic()

    if shutil.which("jj") is None:
        return PrerequisiteResult(
            success=False,
            message="Jujutsu (jj) is not installed or not on PATH",
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    return PrerequisiteResult(
        success=True,
        message="Jujutsu CLI found",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


@prerequisite_registry.register(
    name="jj_colocated",
    display_name="Jujutsu Colocated Repo",
    dependencies=("jj", "git_repo"),
    cost=1,
    remediation=(
        "Initialize a colocated jj repo: jj git init --colocate\n"
        "This shares the .git directory so GitPython reads still work."
    ),
)
async def check_jj_colocated() -> PrerequisiteResult:
    """Check that the current directory has a colocated jj repository."""
    start = time.monotonic()

    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                "jj",
                "root",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=5,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode().strip() if stderr else "Not a jj repository"
            return PrerequisiteResult(
                success=False,
                message=f"Not in a jj repository: {error_msg}",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        jj_root = stdout.decode().strip()
        return PrerequisiteResult(
            success=True,
            message=f"Jujutsu colocated repo found ({jj_root})",
            duration_ms=int((time.monotonic() - start) * 1000),
            details={"jj_root": jj_root},
        )

    except TimeoutError:
        return PrerequisiteResult(
            success=False,
            message="Jujutsu repository check timed out",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except OSError as e:
        return PrerequisiteResult(
            success=False,
            message=f"Jujutsu repository check failed: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


# =============================================================================
# GitHub CLI Prerequisites
# =============================================================================


@prerequisite_registry.register(
    name="gh",
    display_name="GitHub CLI",
    cost=1,
    remediation="Install GitHub CLI from https://cli.github.com/",
)
async def check_gh() -> PrerequisiteResult:
    """Check that GitHub CLI (gh) is available on PATH."""
    start = time.monotonic()

    if shutil.which("gh") is None:
        return PrerequisiteResult(
            success=False,
            message="GitHub CLI (gh) is not installed or not on PATH",
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    return PrerequisiteResult(
        success=True,
        message="GitHub CLI found",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


@prerequisite_registry.register(
    name="gh_auth",
    display_name="GitHub Auth",
    dependencies=("gh",),
    cost=2,
    remediation="Authenticate with GitHub: gh auth login",
)
async def check_gh_auth() -> PrerequisiteResult:
    """Check that GitHub CLI is authenticated."""
    start = time.monotonic()

    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                "gh",
                "auth",
                "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=10,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode().strip() if stderr else "Not authenticated"
            return PrerequisiteResult(
                success=False,
                message=f"GitHub CLI is not authenticated: {error_msg}",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        # Extract username from output if available
        output = stdout.decode() + stderr.decode()
        return PrerequisiteResult(
            success=True,
            message="GitHub CLI is authenticated",
            duration_ms=int((time.monotonic() - start) * 1000),
            details={"raw_output": output[:200]} if output else None,
        )

    except TimeoutError:
        return PrerequisiteResult(
            success=False,
            message="GitHub auth check timed out",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except OSError as e:
        return PrerequisiteResult(
            success=False,
            message=f"GitHub auth check failed: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


# =============================================================================
# Beads CLI Prerequisites
# =============================================================================


@prerequisite_registry.register(
    name="bd",
    display_name="Beads CLI",
    dependencies=("git",),
    cost=1,
    remediation="Install the Beads CLI from https://github.com/steveyegge/beads",
)
async def check_bd() -> PrerequisiteResult:
    """Check that Beads CLI (bd) is available on PATH."""
    start = time.monotonic()

    if shutil.which("bd") is None:
        return PrerequisiteResult(
            success=False,
            message="Beads CLI (bd) is not installed or not on PATH",
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    return PrerequisiteResult(
        success=True,
        message="Beads CLI found",
        duration_ms=int((time.monotonic() - start) * 1000),
    )


# =============================================================================
# Anthropic API Prerequisites
# =============================================================================


@prerequisite_registry.register(
    name="anthropic_key",
    display_name="Anthropic API Key",
    cost=1,
    remediation=(
        "Set your Anthropic API key:\n"
        "  export ANTHROPIC_API_KEY='your-api-key'\n"
        "Or use OAuth: export CLAUDE_CODE_OAUTH_TOKEN='your-token'"
    ),
)
async def check_anthropic_key() -> PrerequisiteResult:
    """Check that ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN is set."""
    start = time.monotonic()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")

    if not api_key and not oauth_token:
        return PrerequisiteResult(
            success=False,
            message=(
                "Neither ANTHROPIC_API_KEY nor CLAUDE_CODE_OAUTH_TOKEN "
                "environment variable is set"
            ),
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    auth_method = "ANTHROPIC_API_KEY" if api_key else "CLAUDE_CODE_OAUTH_TOKEN"
    return PrerequisiteResult(
        success=True,
        message=f"Anthropic credentials found ({auth_method})",
        duration_ms=int((time.monotonic() - start) * 1000),
        details={"auth_method": auth_method},
    )


@prerequisite_registry.register(
    name="anthropic_api",
    display_name="Anthropic API Access",
    dependencies=("anthropic_key",),
    cost=3,
    remediation=(
        "Verify your API key is valid and your account has API access. "
        "Check https://console.anthropic.com/ for details."
    ),
)
async def check_anthropic_api() -> PrerequisiteResult:
    """Check that Anthropic API is accessible with a minimal request."""
    start = time.monotonic()

    try:
        from claude_agent_sdk import ClaudeAgentOptions, query

        from maverick.constants import CLAUDE_HAIKU_LATEST

        options = ClaudeAgentOptions(
            system_prompt="Respond with exactly 'OK'.",
            model=CLAUDE_HAIKU_LATEST,
            max_turns=1,
            allowed_tools=[],
        )

        # Minimal request - wrap async iterator in coroutine for timeout
        async def make_request() -> None:
            async for _ in query(prompt="Hi", options=options):
                pass

        await asyncio.wait_for(make_request(), timeout=10.0)

        return PrerequisiteResult(
            success=True,
            message="Anthropic API is accessible",
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    except TimeoutError:
        return PrerequisiteResult(
            success=False,
            message="Anthropic API request timed out. Check network connectivity.",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except ImportError:
        return PrerequisiteResult(
            success=False,
            message="claude-agent-sdk is not installed",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except Exception as e:
        error_msg = str(e)
        # Provide specific guidance based on error type
        if "401" in error_msg or "invalid" in error_msg.lower():
            message = (
                "Invalid credentials. Verify ANTHROPIC_API_KEY or "
                "CLAUDE_CODE_OAUTH_TOKEN is correct."
            )
        elif "403" in error_msg or "permission" in error_msg.lower():
            message = (
                "API key does not have access to the requested model. "
                "Check your Anthropic account plan."
            )
        elif "429" in error_msg or "rate" in error_msg.lower():
            message = "Rate limit exceeded. Please try again later."
        else:
            message = f"Anthropic API error: {error_msg}"

        return PrerequisiteResult(
            success=False,
            message=message,
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def register_builtin_checks() -> None:
    """Ensure all built-in checks are registered.

    This function is a no-op since checks are registered at module import
    time via decorators. It exists for explicit initialization when needed.
    """
    # All checks are registered via decorators when this module is imported.
    # This function exists for explicit initialization patterns.
    logger.debug(
        "Built-in prerequisite checks registered",
        count=len(prerequisite_registry.list_names()),
    )
