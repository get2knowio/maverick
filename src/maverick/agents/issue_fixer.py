"""IssueFixerAgent for resolving GitHub issues.

This module provides the IssueFixerAgent that resolves GitHub issues
with minimal, targeted code changes.
"""

from __future__ import annotations

import time
from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.prompts.common import (
    CODE_QUALITY_PRINCIPLES,
    TOOL_USAGE_EDIT,
    TOOL_USAGE_GLOB,
    TOOL_USAGE_GREP,
    TOOL_USAGE_READ,
    TOOL_USAGE_WRITE,
)
from maverick.agents.tools import ISSUE_FIXER_TOOLS
from maverick.agents.utils import (
    detect_file_changes,
    extract_all_text,
    extract_streaming_text,
)
from maverick.exceptions import GitHubError
from maverick.logging import get_logger
from maverick.models.issue_fix import FixResult, IssueFixerContext

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

ISSUE_FIXER_SYSTEM_PROMPT = f"""You are an expert software engineer.
You focus on minimal, targeted bug fixes within an orchestrated workflow.

## Your Role

You implement bug fixes by analyzing issues and modifying code.
The orchestration layer handles:
- Fetching issue details from GitHub (issue data is provided to you)
- Git operations (commits are created after you complete your work)
- Validation execution (tests run after implementation)
- PR management and issue closure

You focus on:
- Understanding the issue and identifying root cause
- Making minimal, targeted code changes
- Writing tests that verify the fix

## Core Approach
1. Understand the issue completely before making changes
2. Identify the root cause, not just symptoms
3. Make the MINIMUM changes necessary to fix the issue
4. Do NOT refactor unrelated code
5. Ensure fix is ready for verification (will be run by orchestration)

## Issue Analysis
For each issue:
1. Read the issue title and description (provided to you)
2. Look for reproduction steps
3. Identify affected code paths
4. Find the root cause
5. Plan the minimal fix

## Fix Guidelines
- Change only what's necessary (target <100 lines for typical bugs)
- Don't "improve" surrounding code
- Don't add features while fixing bugs
- Don't change formatting of untouched code
- Add a test that reproduces the bug (if feasible)

## Tool Usage Guidelines

You have access to: **Read, Write, Edit, Glob, Grep**

### Read
{TOOL_USAGE_READ}
- Read is also suitable for reviewing related source files, test files, and
  project conventions to understand context before applying the fix.

### Write
{TOOL_USAGE_WRITE}

### Edit
{TOOL_USAGE_EDIT}

### Glob
{TOOL_USAGE_GLOB}

### Grep
{TOOL_USAGE_GREP}

{CODE_QUALITY_PRINCIPLES}

## Verification
Your fix will be verified by orchestration through:
1. Running reproduction steps (if provided)
2. Running related tests
3. Running full validation pipeline

## Commit Message
The orchestration layer will create a commit using format: `fix(scope): description`
with `Fixes #<issue_number>` in the commit body.

## Output
After fixing, output a JSON summary:
{{
  "issue_number": 42,
  "root_cause": "Description of root cause",
  "fix_description": "What was changed to fix it",
  "files_changed": [{{"path": "src/file.py", "added": 5, "removed": 2}}],
  "verification": "How the fix was verified"
}}
"""


# =============================================================================
# IssueFixerAgent
# =============================================================================


class IssueFixerAgent(MaverickAgent[IssueFixerContext, FixResult]):
    """Agent for resolving GitHub issues with minimal changes.

    Implements targeted bug fixes by analyzing issues, implementing
    minimal fixes, and verifying resolution.

    Type Parameters:
        Context: IssueFixerContext - issue source and execution options
        Result: FixResult - fix outcome with verification status

    Example:
        >>> agent = IssueFixerAgent()
        >>> context = IssueFixerContext(issue_number=42)
        >>> result = await agent.execute(context)
        >>> result.success
        True
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        """Initialize IssueFixerAgent.

        Args:
            model: Claude model ID (defaults to claude-sonnet-4-5-20250929).
            mcp_servers: Optional MCP server configurations.
            max_tokens: Optional maximum output tokens (SDK default used if None).
            temperature: Optional sampling temperature 0.0-1.0 (SDK default).
        """
        super().__init__(
            name="issue-fixer",
            system_prompt=ISSUE_FIXER_SYSTEM_PROMPT,
            allowed_tools=list(ISSUE_FIXER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def execute(self, context: IssueFixerContext) -> FixResult:
        """Fix a GitHub issue.

        Args:
            context: Execution context with issue source and options.

        Returns:
            FixResult with fix details and verification status.

        Raises:
            GitHubError: If issue cannot be fetched (after retries).
            AgentError: On unrecoverable execution errors.
        """
        start_time = time.monotonic()

        try:
            # Fetch issue details
            issue_data = await self._fetch_issue(context)

            issue_number = issue_data["number"]
            issue_title = issue_data.get("title", "")
            issue_url = issue_data.get("url", "")

            logger.info("Fixing issue #%d: %s", issue_number, issue_title)

            # Analyze and fix the issue
            fix_output, root_cause, fix_description = await self._analyze_and_fix(
                issue_data, context
            )

            # Detect file changes (informational - used for result reporting)
            files_changed = await detect_file_changes(context.cwd)

            # Validation, verification, and commits are handled by the workflow layer
            # Agent returns file changes and fix analysis; orchestration runs
            # validation/commits
            verification_passed = True  # Workflow handles verification
            validation_passed = True  # Workflow handles validation
            commit_sha = None  # Workflow handles commits

            duration_ms = int((time.monotonic() - start_time) * 1000)

            return FixResult(
                success=verification_passed and validation_passed,
                issue_number=issue_number,
                issue_title=issue_title,
                issue_url=issue_url,
                root_cause=root_cause,
                fix_description=fix_description,
                files_changed=files_changed,
                commit_sha=commit_sha,
                verification_passed=verification_passed,
                validation_passed=validation_passed,
                output=fix_output,
                metadata={
                    "duration_ms": duration_ms,
                    "dry_run": context.dry_run,
                },
            )

        except GitHubError:
            raise
        except Exception as e:
            logger.exception("Issue fix failed: %s", e)
            return FixResult(
                success=False,
                issue_number=context.effective_issue_number,
                issue_title="",
                errors=[str(e)],
            )

    async def _fetch_issue(self, context: IssueFixerContext) -> dict[str, Any]:
        """Fetch issue details from GitHub or use pre-fetched data.

        Args:
            context: Execution context.

        Returns:
            Issue data dictionary.

        Raises:
            GitHubError: If issue cannot be fetched.
        """
        if context.issue_data:
            return context.issue_data

        from maverick.utils.github import fetch_issue

        return await fetch_issue(context.issue_number or 0, context.cwd)

    async def _analyze_and_fix(
        self,
        issue_data: dict[str, Any],
        context: IssueFixerContext,
    ) -> tuple[str, str, str]:
        """Analyze the issue and implement a fix.

        Args:
            issue_data: Issue details from GitHub.
            context: Execution context.

        Returns:
            Tuple of (raw_output, root_cause, fix_description).
        """
        prompt = self._build_fix_prompt(issue_data)

        messages = []
        async for msg in self.query(prompt, cwd=context.cwd):
            messages.append(msg)
            # Stream text to TUI if callback is set
            if self.stream_callback:
                text = extract_streaming_text(msg)
                if text:
                    await self.stream_callback(text)

        output = extract_all_text(messages)

        # Extract root cause and fix description from output
        # (simplified - full parsing in enhancement phase)
        root_cause = "Identified from issue analysis"
        fix_description = "Fix implemented based on issue requirements"

        return output, root_cause, fix_description

    def _build_fix_prompt(self, issue_data: dict[str, Any]) -> str:
        """Build the prompt for fixing an issue."""
        title = issue_data.get("title", "")
        body = issue_data.get("body", "")
        labels = [label.get("name", "") for label in issue_data.get("labels", [])]

        return f"""Fix the following GitHub issue:

**Issue #{issue_data.get("number", 0)}**: {title}

**Description**:
{body}

**Labels**: {", ".join(labels) if labels else "None"}

Follow the minimal fix approach:
1. Understand the issue completely
2. Find the root cause
3. Implement the MINIMUM fix necessary
4. Add a test if feasible
5. Verify the fix works

After fixing, provide:
- Root cause analysis
- Description of the fix
- Files changed
- How you verified the fix
"""
