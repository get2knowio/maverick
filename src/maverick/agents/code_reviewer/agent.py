"""CodeReviewerAgent implementation.

This module implements the CodeReviewerAgent, which performs automated code reviews
on feature branches by analyzing git diffs and checking for correctness, security,
style/conventions, performance, and testability issues.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maverick.agents.base import MaverickAgent
from maverick.agents.code_reviewer.constants import MAX_TOKENS_PER_CHUNK
from maverick.agents.code_reviewer.diff_chunking import (
    chunk_files,
    estimate_tokens,
    truncate_files,
)
from maverick.agents.code_reviewer.parsing import parse_findings
from maverick.agents.code_reviewer.prompts import SYSTEM_PROMPT
from maverick.agents.tools import REVIEWER_TOOLS
from maverick.agents.utils import extract_all_text, extract_streaming_text
from maverick.exceptions import AgentError
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.agents.result import AgentUsage
    from maverick.models.review import ReviewContext, ReviewResult, UsageStats

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
        system_prompt: Expert code reviewer prompt with review dimensions
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
            system_prompt=SYSTEM_PROMPT,
            allowed_tools=list(REVIEWER_TOOLS),
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def execute(self, context: ReviewContext) -> ReviewResult:
        """Execute code review on the specified branch (FR-004).

        This method orchestrates the code review process:
        1. Retrieves diff between feature branch and base branch
        2. Reads CLAUDE.md for convention checking (if exists)
        3. Filters to specific files if requested
        4. Truncates if diff exceeds size limits
        5. Performs review and extracts structured findings
        6. Returns ReviewResult with findings and metadata

        Args:
            context: ReviewContext with branch, base_branch, file_list, and cwd.

        Returns:
            ReviewResult with structured findings and metadata.

        Raises:
            AgentError: If git operations fail, merge conflicts exist,
                or other unrecoverable errors occur.

        Behavior:
            - FR-008: Retrieves diff between branches
            - FR-009: Reads CLAUDE.md for convention checking (if exists)
            - FR-014: Filters to file_list if provided
            - FR-015: Proceeds without conventions if CLAUDE.md missing
            - FR-017: Truncates if diff > 2000 lines or 50 files
            - FR-018: Raises AgentError for git failures
            - FR-019: Returns empty result if no changes
            - FR-020: Silently excludes binary files
            - FR-021: Auto-chunks if approaching token limits
        """
        # Import here to avoid circular dependency
        from maverick.models.review import ReviewResult, ReviewSeverity

        # Track timing and timestamp for metadata (T044)
        start_time = time.time()
        start_timestamp = datetime.now(UTC).isoformat()

        try:
            # Use the provided ReviewContext directly
            review_context = context

            # 1. Check for merge conflicts (T022)
            has_conflicts = await self._check_merge_conflicts(review_context)
            if has_conflicts:
                raise AgentError(
                    "Cannot review: merge conflicts exist. "
                    "Resolve conflicts before review.",
                    agent_name=self.name,
                    error_code="MERGE_CONFLICTS",
                )

            # 2. Get diff stats and 3. Read conventions in parallel (T022)
            diff_stats, conventions = await asyncio.gather(
                self._get_diff_stats(review_context),
                self._read_conventions(review_context),
            )

            # 4. Handle empty diff case (T024)
            if not diff_stats["files"]:
                duration_ms = int((time.time() - start_time) * 1000)
                metadata = {
                    "branch": review_context.branch,
                    "base_branch": review_context.base_branch,
                    "duration_ms": duration_ms,
                    "binary_files_excluded": len(diff_stats["binary_files"]),
                    "timestamp": start_timestamp,
                }
                if review_context.file_list:
                    metadata["files_requested"] = len(review_context.file_list)
                return ReviewResult(
                    success=True,
                    findings=[],
                    files_reviewed=0,
                    summary="No changes to review",
                    metadata=metadata,
                )

            # 5. Apply file list filter if provided (FR-014, T026)
            files_to_review = diff_stats["files"]
            if review_context.file_list:
                # Validate file existence: only include files that exist in diff
                valid_files = set(diff_stats["files"])
                requested_files = set(review_context.file_list)

                # Filter to files that exist in both the diff and the request
                files_to_review = [
                    f for f in diff_stats["files"] if f in requested_files
                ]

                # Log skipped files (files requested but not in diff)
                skipped_files = requested_files - valid_files
                if skipped_files:
                    logger.debug(
                        f"Skipped {len(skipped_files)} files not found in diff: "
                        f"{', '.join(sorted(skipped_files))}"
                    )

                if not files_to_review:
                    duration_ms = int((time.time() - start_time) * 1000)
                    metadata = {
                        "branch": review_context.branch,
                        "base_branch": review_context.base_branch,
                        "duration_ms": duration_ms,
                        "binary_files_excluded": len(diff_stats["binary_files"]),
                        "timestamp": start_timestamp,
                    }
                    if review_context.file_list:
                        metadata["files_requested"] = len(review_context.file_list)
                    return ReviewResult(
                        success=True,
                        findings=[],
                        files_reviewed=0,
                        summary="No matching files to review",
                        metadata=metadata,
                    )

            # 6. Apply truncation if needed (FR-017, T038, T040)
            truncated = False
            truncation_notice = ""

            # Use helper to determine if truncation is needed
            files_to_review, truncation_notice = truncate_files(
                files_to_review, diff_stats
            )
            if truncation_notice:
                truncated = True
                logger.warning(f"Diff truncation: {truncation_notice}")

            # 7. Get diff content for the files
            diff_content = await self._get_diff_content(review_context, files_to_review)

            # 8. Check if chunking is needed (FR-021, T043)
            estimated_tokens = estimate_tokens(diff_content)
            chunks_used = False
            response_text = ""  # Initialize before branching

            if estimated_tokens > MAX_TOKENS_PER_CHUNK:
                # Need to chunk the review
                chunks_used = True
                file_chunks = chunk_files(files_to_review, diff_content)
                logger.info(
                    f"Review chunking: splitting {len(files_to_review)} files "
                    f"into {len(file_chunks)} chunks "
                    f"({estimated_tokens} estimated tokens)"
                )

                # Review each chunk separately and merge findings
                all_findings = []
                for chunk_idx, file_chunk in enumerate(file_chunks):
                    logger.debug(f"Reviewing chunk {chunk_idx + 1}/{len(file_chunks)}")

                    # Get diff for this chunk
                    chunk_diff = await self._get_diff_content(
                        review_context, file_chunk
                    )

                    # Build prompt for this chunk
                    chunk_prompt = self._build_review_prompt(chunk_diff, conventions)

                    # Review the chunk
                    chunk_messages: list[Any] = []
                    async for msg in self.query(chunk_prompt, cwd=review_context.cwd):
                        chunk_messages.append(msg)
                        # Stream text to TUI if callback is set
                        if self.stream_callback:
                            text = extract_streaming_text(msg)
                            if text:
                                await self.stream_callback(text)

                    # Parse findings from chunk
                    chunk_response = extract_all_text(chunk_messages)
                    chunk_findings = parse_findings(chunk_response)
                    all_findings.extend(chunk_findings)

                findings = all_findings
                # messages not used for chunked review (no single usage to track)
                messages: list[Any] = []
            else:
                # Single review without chunking
                # 9. Build the review prompt
                prompt = self._build_review_prompt(diff_content, conventions)

                # 10. Call Claude using self.query() method (T022)
                messages = []
                async for msg in self.query(prompt, cwd=review_context.cwd):
                    messages.append(msg)
                    # Stream text to TUI if callback is set
                    if self.stream_callback:
                        text = extract_streaming_text(msg)
                        if text:
                            await self.stream_callback(text)

                # 11. Collect and join the response text (T022)
                response_text = extract_all_text(messages)

                # 12. Parse findings from response (T022)
                findings = parse_findings(response_text)

            # 12. Build summary with severity counts (T022)
            severity_counts = {
                ReviewSeverity.CRITICAL: 0,
                ReviewSeverity.MAJOR: 0,
                ReviewSeverity.MINOR: 0,
                ReviewSeverity.SUGGESTION: 0,
            }
            for finding in findings:
                severity_counts[finding.severity] += 1

            # Build human-readable summary
            total_issues = len(findings)
            if total_issues == 0:
                summary = f"Reviewed {len(files_to_review)} files, no issues found"
            else:
                parts = [f"Reviewed {len(files_to_review)} files"]
                issue_word = "issues" if total_issues != 1 else "issue"
                parts.append(f"found {total_issues} {issue_word}")

                # Add severity breakdown
                severity_parts = []
                if severity_counts[ReviewSeverity.CRITICAL] > 0:
                    severity_parts.append(
                        f"{severity_counts[ReviewSeverity.CRITICAL]} critical"
                    )
                if severity_counts[ReviewSeverity.MAJOR] > 0:
                    severity_parts.append(
                        f"{severity_counts[ReviewSeverity.MAJOR]} major"
                    )
                if severity_counts[ReviewSeverity.MINOR] > 0:
                    severity_parts.append(
                        f"{severity_counts[ReviewSeverity.MINOR]} minor"
                    )
                if severity_counts[ReviewSeverity.SUGGESTION] > 0:
                    count = severity_counts[ReviewSeverity.SUGGESTION]
                    word = "suggestions" if count != 1 else "suggestion"
                    severity_parts.append(f"{count} {word}")

                if severity_parts:
                    parts.append(f"({', '.join(severity_parts)})")

                summary = ", ".join(parts)

            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            # T044: Build comprehensive metadata
            metadata = {
                "branch": review_context.branch,
                "base_branch": review_context.base_branch,
                "duration_ms": duration_ms,
                "binary_files_excluded": len(diff_stats["binary_files"]),
                "timestamp": start_timestamp,
            }

            # Add files_requested count if file_list was provided
            if review_context.file_list:
                metadata["files_requested"] = len(review_context.file_list)

            # T040: Add truncation notice to metadata if truncated
            if truncation_notice:
                metadata["truncation_notice"] = truncation_notice

            # T043: Add chunking information to metadata
            metadata["chunks_used"] = len(file_chunks) if chunks_used else 0
            if chunks_used:
                metadata["chunking_reason"] = "diff_size_exceeds_token_limit"

            # T045: Extract usage stats from messages and convert to UsageStats
            # For chunked reviews, messages is empty (no single usage to track)
            agent_usage = self._extract_usage(messages)
            usage_stats = (
                self._convert_to_usage_stats(agent_usage, duration_ms)
                if agent_usage
                else None
            )

            # Get response_text for output (may be empty for chunked reviews)
            output_text = response_text if not chunks_used else ""

            # 13. Build and return ReviewResult (T022)
            return ReviewResult(
                success=True,
                findings=findings,
                files_reviewed=len(files_to_review),
                summary=summary,
                truncated=truncated,
                output=output_text,
                metadata=metadata,
                usage=usage_stats,
            )

        except AgentError:
            # Re-raise AgentError instances as-is (T023)
            raise
        except TimeoutError as e:
            # Handle timeout errors (T023)
            raise AgentError(
                "Code review operation timed out",
                agent_name=self.name,
                error_code="TIMEOUT",
            ) from e
        except Exception as e:
            # Wrap other exceptions with appropriate context (T023)
            error_msg = str(e)
            error_code = "GIT_ERROR" if "git" in error_msg.lower() else None

            raise AgentError(
                f"Code review failed: {error_msg}",
                agent_name=self.name,
                error_code=error_code,
            ) from e

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

    def _convert_to_usage_stats(
        self,
        agent_usage: AgentUsage,
        duration_ms: int,
    ) -> UsageStats:
        """Convert AgentUsage to UsageStats model (T045).

        This method bridges the gap between the base MaverickAgent's AgentUsage
        dataclass and the ReviewResult's UsageStats Pydantic model.

        Args:
            agent_usage: AgentUsage instance from _extract_usage().
            duration_ms: Execution duration in milliseconds.

        Returns:
            UsageStats instance compatible with ReviewResult.
        """
        from maverick.models.review import UsageStats

        return UsageStats(
            input_tokens=agent_usage.input_tokens,
            output_tokens=agent_usage.output_tokens,
            total_cost=agent_usage.total_cost_usd,
            duration_ms=duration_ms,
        )

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
