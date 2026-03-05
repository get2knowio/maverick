"""CodeReviewerAgent implementation.

This module implements the CodeReviewerAgent, which performs automated code reviews
on feature branches by analyzing git diffs and checking for correctness, security,
style/conventions, performance, and testability issues.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maverick.agents.base import MaverickAgent
from maverick.agents.code_reviewer.diff_chunking import (
    chunk_files,
    estimate_tokens,
    truncate_files,
)
from maverick.agents.code_reviewer.parsing import parse_findings
from maverick.agents.code_reviewer.prompts import SYSTEM_PROMPT
from maverick.agents.tools import REVIEWER_TOOLS
from maverick.exceptions import AgentError
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.models.review import ReviewContext, ReviewResult

# Try to import review models (handle gracefully if not ready yet)
try:
    from maverick.models.review import ReviewContext, ReviewFinding, ReviewResult
except ImportError:
    # Models not yet implemented - define placeholder types
    ReviewContext = None  # type: ignore
    ReviewFinding = None  # type: ignore
    ReviewResult = None  # type: ignore


# Set up logger
logger = get_logger(__name__)


class CodeReviewerAgent(MaverickAgent["ReviewContext", "ReviewResult"]):
    """Agent for automated code review of feature branches (FR-001).

    This agent analyzes git diffs between a feature branch and base branch,
    checking for correctness, security, style/conventions, performance, and
    testability issues. It uses read-only tools and returns structured findings.

    The agent follows the principle of least privilege by only using read-only
    tools (Read, Glob, Grep) and never modifying code during review.

    Type Parameters:
        Context: ReviewContext - specialized context with branch and file filtering
        Result: ReviewResult - structured review findings with severity categorization

    Attributes:
        name: Always "code-reviewer"
        instructions: Expert code reviewer prompt with review dimensions
        allowed_tools: Read-only tools only
        model: Claude model ID (inherited from MaverickAgent)

    Example:
        ```python
        agent = CodeReviewerAgent()
        context = ReviewContext(
            branch="feature/auth",
            base_branch="main",
            cwd=Path("/workspace/project"),
        )
        result = await agent.execute(context)

        if result.has_critical_findings:
            print("Critical issues found - must fix before merge!")
        ```
    """

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        """Initialize the CodeReviewerAgent.

        Args:
            model: Optional Claude model ID (default: claude-sonnet-4-5-20250929).
            max_tokens: Optional maximum output tokens (SDK default used if None).
            temperature: Optional sampling temperature 0.0-1.0 (SDK default).
        """
        super().__init__(
            name="code-reviewer",
            instructions=SYSTEM_PROMPT,
            allowed_tools=list(REVIEWER_TOOLS),
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def build_prompt(self, context: ReviewContext) -> str:
        """Construct the prompt string from context (FR-017).

        Builds a review prompt directed at the given branch and base_branch.
        The ACP executor will provide the agent access to git tools so it can
        fetch the diff and conventions at runtime.

        Args:
            context: ReviewContext with branch, base_branch, file_list, and cwd.

        Returns:
            Complete prompt text ready for the ACP agent.
        """
        file_filter = (
            f"\nFocus only on these files: {', '.join(context.file_list)}"
            if context.file_list
            else ""
        )
        return (
            f"Review code changes between branch '{context.branch}' "
            f"and base branch '{context.base_branch}'.{file_filter} "
            f"Check CLAUDE.md for project conventions if it exists. "
            f"Return structured findings."
        )

    async def _get_diff_stats(self, context: ReviewContext) -> dict[str, Any]:
        """Get diff statistics without full content (FR-008).

        Uses `git diff --numstat` to quickly retrieve metadata about changed
        files without loading full patch content. This enables efficient
        truncation decisions.

        Args:
            context: Review context with branch and base_branch.

        Returns:
            Dictionary with:
            - files: List of non-binary file paths
            - binary_files: List of binary file paths (excluded from review)
            - total_lines: Total lines changed (added + deleted)

        Raises:
            AgentError: If git command fails.
        """
        try:
            # Execute git diff --numstat asynchronously
            process = await asyncio.create_subprocess_exec(
                "git",
                "diff",
                f"{context.base_branch}...{context.branch}",
                "--numstat",
                cwd=context.cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30.0,
            )

            if process.returncode != 0:
                error_msg = stderr.decode().strip() or stdout.decode().strip()
                raise AgentError(
                    f"Git diff stats failed: {error_msg}",
                    agent_name=self.name,
                    error_code="GIT_ERROR",
                )

            # Parse numstat output
            files: list[str] = []
            binary_files: list[str] = []
            total_lines = 0

            output = stdout.decode().strip()
            if not output:
                return {
                    "files": files,
                    "binary_files": binary_files,
                    "total_lines": total_lines,
                }

            for line in output.split("\n"):
                if not line:
                    continue

                parts = line.split("\t")
                if len(parts) >= 3:
                    added, deleted, filename = parts[0], parts[1], parts[2]

                    # Binary files show as "- -" in numstat (FR-020)
                    if added == "-" and deleted == "-":
                        binary_files.append(filename)
                    else:
                        files.append(filename)
                        total_lines += int(added) + int(deleted)

            return {
                "files": files,
                "binary_files": binary_files,
                "total_lines": total_lines,
            }

        except TimeoutError as e:
            raise AgentError(
                "Git diff stats timed out after 30 seconds",
                agent_name=self.name,
                error_code="TIMEOUT",
            ) from e
        except (OSError, ValueError) as e:
            raise AgentError(
                f"Failed to execute git diff stats: {e}",
                agent_name=self.name,
                error_code="GIT_ERROR",
            ) from e

    async def _get_diff_content(
        self,
        context: ReviewContext,
        files: list[str],
    ) -> str:
        """Get full diff content for specified files (FR-008).

        Uses `git diff --patch` to retrieve full unified diff for the specified
        files. This is called after truncation decisions are made.

        Args:
            context: Review context with branch and base_branch.
            files: List of file paths to include in diff.

        Returns:
            Full unified diff content as string.

        Raises:
            AgentError: If git command fails.
        """
        try:
            # Build git diff command with file list
            cmd = [
                "git",
                "diff",
                f"{context.base_branch}...{context.branch}",
                "--patch",
                "--",
            ]
            cmd.extend(files)

            # Execute git diff --patch asynchronously
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=context.cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30.0,
            )

            if process.returncode != 0:
                error_msg = stderr.decode().strip() or stdout.decode().strip()
                raise AgentError(
                    f"Git diff content failed: {error_msg}",
                    agent_name=self.name,
                    error_code="GIT_ERROR",
                )

            return stdout.decode()

        except TimeoutError as e:
            raise AgentError(
                "Git diff content timed out after 30 seconds",
                agent_name=self.name,
                error_code="TIMEOUT",
            ) from e
        except OSError as e:
            raise AgentError(
                f"Failed to execute git diff content: {e}",
                agent_name=self.name,
                error_code="GIT_ERROR",
            ) from e

    async def _check_merge_conflicts(self, context: ReviewContext) -> bool:
        """Check for merge conflicts in working directory (FR-018).

        Uses `git diff --name-only --diff-filter=U` to detect unmerged files.

        Args:
            context: Review context with cwd.

        Returns:
            True if merge conflicts exist, False otherwise.

        Raises:
            AgentError: If git command fails.
        """
        try:
            # Execute git diff to check for unmerged files
            process = await asyncio.create_subprocess_exec(
                "git",
                "diff",
                "--name-only",
                "--diff-filter=U",
                cwd=context.cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10.0,
            )

            if process.returncode != 0:
                error_msg = stderr.decode().strip() or stdout.decode().strip()
                raise AgentError(
                    f"Git merge conflict check failed: {error_msg}",
                    agent_name=self.name,
                    error_code="GIT_ERROR",
                )

            # If stdout has content, there are unmerged files
            output = stdout.decode().strip()
            return bool(output)

        except TimeoutError as e:
            raise AgentError(
                "Git merge conflict check timed out after 10 seconds",
                agent_name=self.name,
                error_code="TIMEOUT",
            ) from e
        except OSError as e:
            raise AgentError(
                f"Failed to check for merge conflicts: {e}",
                agent_name=self.name,
                error_code="GIT_ERROR",
            ) from e

    async def _read_conventions(self, context: ReviewContext) -> str | None:
        """Read CLAUDE.md conventions if available (FR-009, FR-015).

        Attempts to read CLAUDE.md from repository root. Returns None if file
        does not exist (agent proceeds without convention checking per FR-015).

        Args:
            context: Review context with cwd.

        Returns:
            CLAUDE.md content as string, or None if file does not exist.

        Raises:
            AgentError: If file read fails for reasons other than missing file.
        """
        try:
            # Locate CLAUDE.md in the repository root
            claude_md_path = Path(context.cwd) / "CLAUDE.md"

            # Check if file exists
            if not claude_md_path.exists():
                logger.debug("CLAUDE.md not found, proceeding without conventions")
                return None

            # Read file asynchronously using asyncio.to_thread
            content = await asyncio.to_thread(
                claude_md_path.read_text, encoding="utf-8"
            )
            logger.debug(f"Successfully read CLAUDE.md ({len(content)} bytes)")
            return content

        except FileNotFoundError:
            # File doesn't exist - this is expected and not an error (FR-015)
            logger.debug("CLAUDE.md not found, proceeding without conventions")
            return None
        except (OSError, UnicodeDecodeError) as e:
            # File exists but can't be read - this is an error
            raise AgentError(
                f"Failed to read CLAUDE.md: {e}",
                agent_name=self.name,
                error_code="FILE_READ_ERROR",
            ) from e

    def _build_review_prompt(
        self,
        diff: str,
        conventions: str | None,
    ) -> str:
        """Build the review prompt with diff and conventions (FR-010).

        Constructs a prompt that includes the diff content and optionally
        references CLAUDE.md conventions. Instructs the agent to return
        structured JSON output.

        Args:
            diff: Unified diff content.
            conventions: CLAUDE.md content (if available).

        Returns:
            Formatted prompt string for Claude.
        """
        # Build the base prompt with the diff
        prompt_parts = [
            "Please review the following code changes:\n",
            "```diff",
            diff,
            "```\n",
        ]

        # Add conventions section if available (T036)
        if conventions:
            prompt_parts.extend(
                [
                    "\n## Project Conventions (CLAUDE.md)\n",
                    "Please check the code against these project conventions:\n",
                    "```markdown",
                    conventions,
                    "```\n",
                    "\nWhen a finding violates a specific CLAUDE.md convention, "
                    "populate the `convention_ref` field with the section path "
                    "from CLAUDE.md.\n",
                    "Examples:\n",
                    "- 'Code Style > Naming' for naming convention violations\n",
                    "- 'Core Principles > Async-First' for async/sync violations\n",
                    "- 'Architecture > Separation of Concerns' for architecture\n",
                    "- 'Technology Stack' for dependency or tool violations\n",
                ]
            )

        # Add JSON schema instruction
        schema = ReviewResult.model_json_schema()
        prompt_parts.extend(
            [
                "\n## Output Format\n",
                "Return your findings as a JSON object matching this schema:\n",
                "```json",
                json.dumps(schema, indent=2),
                "```\n",
                "\nProvide your response as valid JSON only, with:",
                "- `success`: true if review completed",
                "- `findings`: array of ReviewFinding objects",
                "- `files_reviewed`: count of files analyzed",
                "- `summary`: brief summary of the review outcome",
                "\nEach finding must include: severity, file, line (optional), "
                "message, and suggestion.",
            ]
        )

        return "\n".join(prompt_parts)

    # Wrapper methods for backward compatibility with tests
    def _estimate_tokens(self, content: str) -> int:
        """Estimate token count for content (delegates to module function)."""
        return estimate_tokens(content)

    def _should_truncate(self, diff_stats: dict[str, Any]) -> bool:
        """Check if diff should be truncated (delegates to module function)."""
        from maverick.agents.code_reviewer.diff_chunking import should_truncate

        return should_truncate(diff_stats)

    def _truncate_files(
        self, files: list[str], diff_stats: dict[str, Any]
    ) -> tuple[list[str], str]:
        """Truncate file list (delegates to module function)."""
        return truncate_files(files, diff_stats)

    def _chunk_files(self, files: list[str], diff_content: str) -> list[list[str]]:
        """Chunk files for review (delegates to module function)."""
        return chunk_files(files, diff_content)

    def _parse_findings(self, response: str) -> list[ReviewFinding]:
        """Parse findings from response (delegates to module function)."""
        return parse_findings(response)

    def _extract_json(self, text: str) -> str | None:
        """Extract JSON from text (delegates to module function)."""
        from maverick.agents.code_reviewer.parsing import extract_json

        return extract_json(text)
