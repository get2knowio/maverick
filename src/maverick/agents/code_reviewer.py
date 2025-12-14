"""CodeReviewerAgent implementation.

This module implements the CodeReviewerAgent, which performs automated code reviews
on feature branches by analyzing git diffs and checking for correctness, security,
style/conventions, performance, and testability issues.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maverick.agents.base import MaverickAgent
from maverick.agents.utils import extract_all_text
from maverick.exceptions import AgentError

if TYPE_CHECKING:
    from maverick.agents.context import AgentContext
    from maverick.agents.result import AgentResult

# Try to import review models (handle gracefully if not ready yet)
try:
    from maverick.models.review import ReviewContext, ReviewFinding, ReviewResult
except ImportError:
    # Models not yet implemented - define placeholder types
    ReviewContext = None  # type: ignore
    ReviewFinding = None  # type: ignore
    ReviewResult = None  # type: ignore


# Set up logger
logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

#: Maximum diff lines before truncation (FR-017)
MAX_DIFF_LINES: int = 2000

#: Maximum diff files before truncation (FR-017)
MAX_DIFF_FILES: int = 50

#: Maximum tokens per review chunk (FR-021)
MAX_TOKENS_PER_CHUNK: int = 50_000

#: Read-only tools for code review (FR-006)
ALLOWED_TOOLS: list[str] = ["Read", "Glob", "Grep", "Bash"]

#: Default base branch for comparison
DEFAULT_BASE_BRANCH: str = "main"


# =============================================================================
# System Prompt
# =============================================================================

SYSTEM_PROMPT = """You are an expert code reviewer specializing in Python development.

Your role is to perform thorough, constructive code reviews that help maintain
code quality and prevent defects before they reach production.

## Review Dimensions

When reviewing code, evaluate across these dimensions:

1. **Correctness**: Logic errors, edge cases, proper error handling
   - Are all code paths handled correctly?
   - Are edge cases considered?
   - Is error handling robust and appropriate?

2. **Security**: Injection vulnerabilities, secrets exposure, unsafe patterns
   - Are there any security vulnerabilities?
   - Are secrets or sensitive data properly handled?
   - Are inputs validated and sanitized?

3. **Style & Conventions**: Adherence to CLAUDE.md conventions
   - Does code follow project conventions?
   - Are naming conventions consistent?
   - Is the code structure aligned with project patterns?

4. **Performance**: Inefficient algorithms, resource leaks
   - Are there performance bottlenecks?
   - Are resources properly managed?
   - Are algorithms appropriate for the use case?

5. **Testability**: Test coverage implications
   - Is the code easily testable?
   - Are dependencies properly injected?
   - Are side effects minimized?

## Severity Guidelines

Categorize each finding with appropriate severity:

- **CRITICAL**: Security vulnerabilities, potential data loss, system crashes
  - Examples: SQL injection, XSS vulnerabilities, hardcoded secrets, command injection,
    auth bypass, null pointer dereferences that cause crashes
  - Action: Must fix immediately before merge

- **MAJOR**: Logic errors, incorrect behavior, breaking changes
  - Examples: Off-by-one errors, incorrect return values, missing null checks,
    wrong algorithm implementation, incorrect state handling
  - Action: Should fix before merge

- **MINOR**: Style inconsistencies, minor code smells, formatting issues
  - Examples: Naming conventions violations, missing docstrings, import order,
    formatting inconsistencies, minor refactoring opportunities
  - Action: Fix if time permits

- **SUGGESTION**: Potential improvements, best practices, optimizations
  - Examples: Performance optimization opportunities, alternative approaches,
    best practice recommendations, code structure improvements
  - Action: Consider for future improvements

## Actionable Suggestions (CRITICAL)

For EVERY finding, you MUST provide a specific, actionable suggestion that includes:

1. **Clear explanation** of what needs to be fixed and why
2. **Specific code example** showing how to fix the issue:
   - Use before/after format when replacing existing code
   - Show complete context (not just fragments)
   - Include imports or dependencies if needed
3. **Reference to documentation or conventions** when applicable:
   - Link to CLAUDE.md sections for convention violations (via convention_ref field)
   - Reference Python PEPs for language-level issues
   - Cite relevant library documentation

**Example of a good suggestion:**
```
Before:
    user_id = request.GET['id']
    query = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(query)

After:
    user_id = request.GET.get('id')
    if not user_id:
        return HttpResponse(status=400)
    query = "SELECT * FROM users WHERE id = %s"
    cursor.execute(query, [user_id])

This prevents SQL injection by using parameterized queries. See OWASP SQL Injection Prevention Cheat Sheet.
```

## Output Format

Return your findings as structured JSON matching this schema:
- Each finding must include: severity, file, line (optional), message, suggestion
- Provide a summary of the overall review
- Be constructive and specific in feedback
- Reference CLAUDE.md sections when applicable

## Convention Reference

If CLAUDE.md is provided, check code against documented conventions:
- Architecture patterns (separation of concerns)
- Code style (naming, structure)
- Technology stack usage
- Testing requirements
- Error handling patterns

When a finding violates a specific CLAUDE.md convention, populate the `convention_ref`
field with the section path (e.g., "Code Style > Naming", "Core Principles > Async-First",
"Architecture > Separation of Concerns"). This helps developers quickly locate the
relevant documentation.

If CLAUDE.md is not available, apply general Python best practices.
"""


# =============================================================================
# CodeReviewerAgent
# =============================================================================


class CodeReviewerAgent(MaverickAgent):
    """Agent for automated code review of feature branches (FR-001).

    This agent analyzes git diffs between a feature branch and base branch,
    checking for correctness, security, style/conventions, performance, and
    testability issues. It uses read-only tools and returns structured findings.

    The agent follows the principle of least privilege by only using read-only
    tools (Read, Glob, Grep, Bash) and never modifying code during review.

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
    ) -> None:
        """Initialize the CodeReviewerAgent.

        Args:
            model: Optional Claude model ID (defaults to claude-sonnet-4-5-20250929).
        """
        super().__init__(
            name="code-reviewer",
            system_prompt=SYSTEM_PROMPT,
            allowed_tools=ALLOWED_TOOLS,
            model=model,
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute code review on the specified branch (FR-004).

        This method orchestrates the code review process:
        1. Retrieves diff between feature branch and base branch
        2. Reads CLAUDE.md for convention checking (if exists)
        3. Filters to specific files if requested
        4. Truncates if diff exceeds size limits
        5. Performs review and extracts structured findings
        6. Returns ReviewResult with findings and metadata

        Args:
            context: Runtime context with cwd, branch, config, and extra params.
                     Expected extra params:
                     - base_branch: Base branch for comparison (default: main)
                     - file_list: Optional list of files to review

        Returns:
            AgentResult with ReviewResult as structured output.

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
        from maverick.models.review import ReviewContext, ReviewResult, ReviewSeverity

        # Track timing and timestamp for metadata (T044)
        start_time = time.time()
        start_timestamp = datetime.now(timezone.utc).isoformat()

        try:
            # Build ReviewContext from AgentContext
            review_context = ReviewContext(
                branch=context.branch or "HEAD",
                base_branch=context.extra.get("base_branch", DEFAULT_BASE_BRANCH),
                file_list=context.extra.get("file_list"),
                cwd=context.cwd,
            )

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
            files_to_review, truncation_notice = self._truncate_files(
                files_to_review, diff_stats
            )
            if truncation_notice:
                truncated = True
                logger.warning(f"Diff truncation: {truncation_notice}")

            # 7. Get diff content for the files
            diff_content = await self._get_diff_content(review_context, files_to_review)

            # 8. Check if chunking is needed (FR-021, T043)
            estimated_tokens = self._estimate_tokens(diff_content)
            chunks_used = False

            if estimated_tokens > MAX_TOKENS_PER_CHUNK:
                # Need to chunk the review
                chunks_used = True
                file_chunks = self._chunk_files(files_to_review, diff_content)
                logger.info(
                    f"Review chunking: splitting {len(files_to_review)} files "
                    f"into {len(file_chunks)} chunks ({estimated_tokens} estimated tokens)"
                )

                # Review each chunk separately and merge findings
                all_findings = []
                for chunk_idx, file_chunk in enumerate(file_chunks):
                    logger.debug(f"Reviewing chunk {chunk_idx + 1}/{len(file_chunks)}")

                    # Get diff for this chunk
                    chunk_diff = await self._get_diff_content(review_context, file_chunk)

                    # Build prompt for this chunk
                    chunk_prompt = self._build_review_prompt(chunk_diff, conventions)

                    # Review the chunk
                    chunk_messages = []
                    async for msg in self.query(chunk_prompt, cwd=review_context.cwd):
                        chunk_messages.append(msg)

                    # Parse findings from chunk
                    chunk_response = extract_all_text(chunk_messages)
                    chunk_findings = self._parse_findings(chunk_response)
                    all_findings.extend(chunk_findings)

                findings = all_findings
                # messages not used for chunked review (no single usage to track)
                messages = []
            else:
                # Single review without chunking
                # 9. Build the review prompt
                prompt = self._build_review_prompt(diff_content, conventions)

                # 10. Call Claude using self.query() method (T022)
                messages = []
                async for msg in self.query(prompt, cwd=review_context.cwd):
                    messages.append(msg)

                # 11. Collect and join the response text (T022)
                response_text = extract_all_text(messages)

                # 12. Parse findings from response (T022)
                findings = self._parse_findings(response_text)

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
                parts.append(f"found {total_issues} issue{'s' if total_issues != 1 else ''}")

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
                    severity_parts.append(
                        f"{severity_counts[ReviewSeverity.SUGGESTION]} suggestion{'s' if severity_counts[ReviewSeverity.SUGGESTION] != 1 else ''}"
                    )

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

            # T043: Add chunking information to metadata if chunks were used
            if chunks_used:
                metadata["chunks_used"] = len(file_chunks)
                metadata["chunking_reason"] = "diff_size_exceeds_token_limit"

            # T045: Extract usage stats from messages and convert to UsageStats
            # For chunked reviews, messages is empty (no single usage to track)
            agent_usage = self._extract_usage(messages)
            usage_stats = self._convert_to_usage_stats(agent_usage, duration_ms) if agent_usage else None

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
        except asyncio.TimeoutError as e:
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

    async def _get_diff_stats(self, context: ReviewContext) -> dict:
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

        except asyncio.TimeoutError as e:
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

        except asyncio.TimeoutError as e:
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

        except asyncio.TimeoutError as e:
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
            prompt_parts.extend([
                "\n## Project Conventions (CLAUDE.md)\n",
                "Please check the code against these project conventions:\n",
                "```markdown",
                conventions,
                "```\n",
                "\nWhen a finding violates a specific CLAUDE.md convention, populate the "
                "`convention_ref` field with the section path from CLAUDE.md.\n",
                "Examples:\n",
                "- 'Code Style > Naming' for naming convention violations\n",
                "- 'Core Principles > Async-First' for async/sync violations\n",
                "- 'Architecture > Separation of Concerns' for architectural issues\n",
                "- 'Technology Stack' for dependency or tool violations\n",
            ])

        # Add JSON schema instruction
        schema = ReviewResult.model_json_schema()
        prompt_parts.extend([
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
        ])

        return "\n".join(prompt_parts)

    def _parse_findings(self, response: str) -> list[ReviewFinding]:
        """Parse structured findings from Claude response (FR-011, FR-016).

        Extracts ReviewFinding objects from the JSON response. Handles
        malformed responses gracefully by logging errors and returning
        partial results. Validates severity levels and defaults to SUGGESTION
        for invalid severities (T029).

        Args:
            response: Raw text response from Claude (expected to contain JSON).

        Returns:
            List of ReviewFinding objects extracted from response.

        Raises:
            AgentError: If response is completely unparseable.
        """
        # Import here to avoid circular dependency
        from maverick.models.review import ReviewSeverity

        # Extract JSON from response (may be wrapped in markdown code blocks)
        json_str = self._extract_json(response)

        if not json_str:
            logger.warning("No JSON found in response, returning empty findings list")
            return []

        # Parse JSON
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return []

        # Extract findings array from the response
        findings_data = data.get("findings", [])
        if not isinstance(findings_data, list):
            logger.warning("'findings' field is not a list, returning empty")
            return []

        # Parse each finding with Pydantic validation
        findings: list[ReviewFinding] = []
        for idx, finding_dict in enumerate(findings_data):
            try:
                # Explicit severity validation before Pydantic validation (T029)
                if "severity" in finding_dict:
                    severity_value = finding_dict["severity"]
                    valid_severities = {s.value for s in ReviewSeverity}

                    if severity_value not in valid_severities:
                        logger.warning(
                            f"Invalid severity '{severity_value}' at index {idx}, "
                            f"using SUGGESTION as default"
                        )
                        finding_dict["severity"] = ReviewSeverity.SUGGESTION.value

                finding = ReviewFinding.model_validate(finding_dict)

                # T035: Log if finding has empty or very short suggestion
                if not finding.suggestion or len(finding.suggestion.strip()) < 10:
                    logger.debug(
                        f"Finding at index {idx} has empty or insufficient suggestion "
                        f"(file: {finding.file}, line: {finding.line})"
                    )

                findings.append(finding)
            except Exception as e:
                logger.warning(
                    f"Failed to validate finding at index {idx}: {e}. "
                    f"Data: {finding_dict}"
                )
                # Continue processing remaining findings (graceful degradation)
                continue

        # T035: Track findings with missing suggestions for potential enhancement
        findings_without_suggestions = sum(
            1 for f in findings if not f.suggestion or len(f.suggestion.strip()) < 10
        )
        if findings_without_suggestions > 0:
            logger.info(
                f"Review completed with {findings_without_suggestions} finding(s) "
                f"lacking detailed suggestions out of {len(findings)} total"
            )

        return findings

    def _extract_json(self, text: str) -> str | None:
        """Extract JSON from text that may be wrapped in markdown code blocks.

        Handles formats like:
        - Plain JSON
        - ```json ... ```
        - ``` ... ```

        Args:
            text: Raw text that may contain JSON.

        Returns:
            Extracted JSON string, or None if no JSON found.
        """
        # Try to extract from markdown code block first
        # Pattern: ```json ... ``` or ``` ... ```
        code_block_pattern = r"```(?:json)?\s*\n(.*?)\n```"
        match = re.search(code_block_pattern, text, re.DOTALL)

        if match:
            return match.group(1).strip()

        # Try to find JSON object or array in the text
        # Look for opening { or [ and try to parse from there
        json_start = text.find("{")
        if json_start == -1:
            json_start = text.find("[")

        if json_start != -1:
            # Try to parse from this position to the end
            potential_json = text[json_start:].strip()
            try:
                # Validate it's parseable JSON
                json.loads(potential_json)
                return potential_json
            except json.JSONDecodeError:
                # Try to find the closing bracket
                # This is a simple heuristic - may not work for all cases
                pass

        # No JSON found
        return None

    def _convert_to_usage_stats(
        self,
        agent_usage: Any,
        duration_ms: int,
    ) -> Any:
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

    def _should_truncate(self, diff_stats: dict) -> bool:
        """Check if diff exceeds size limits (T037, FR-017).

        Args:
            diff_stats: Dictionary with 'files' list and 'total_lines' count.

        Returns:
            True if truncation is needed (exceeds MAX_DIFF_LINES or MAX_DIFF_FILES).

        Examples:
            >>> agent._should_truncate({"files": ["a.py"], "total_lines": 100})
            False
            >>> agent._should_truncate({"files": ["a.py"] * 60, "total_lines": 100})
            True
            >>> agent._should_truncate({"files": ["a.py"], "total_lines": 3000})
            True
        """
        return (
            len(diff_stats["files"]) > MAX_DIFF_FILES
            or diff_stats["total_lines"] > MAX_DIFF_LINES
        )

    def _truncate_files(
        self,
        files: list[str],
        diff_stats: dict,
    ) -> tuple[list[str], str]:
        """Truncate file list and generate notice (T038, FR-017).

        Files are kept in git diff order (alphabetical) for reproducibility.

        Args:
            files: List of files to potentially truncate.
            diff_stats: Dictionary with 'files' list and 'total_lines' count.

        Returns:
            Tuple of (truncated_file_list, truncation_notice_string).
            If no truncation needed, notice is empty string.

        Examples:
            >>> files = ["a.py", "b.py", "c.py"]
            >>> stats = {"files": files, "total_lines": 100}
            >>> agent._truncate_files(files, stats)
            (['a.py', 'b.py', 'c.py'], '')

            >>> files = ["file{}.py".format(i) for i in range(60)]
            >>> stats = {"files": files, "total_lines": 100}
            >>> truncated, notice = agent._truncate_files(files, stats)
            >>> len(truncated)
            50
            >>> "50 of 60" in notice
            True
        """
        if not self._should_truncate(diff_stats):
            return files, ""

        # Truncate to MAX_DIFF_FILES
        truncated_files = files[:MAX_DIFF_FILES]
        total_files = len(diff_stats["files"])
        skipped = total_files - MAX_DIFF_FILES

        notice = (
            f"Truncated: reviewing {MAX_DIFF_FILES} of {total_files} files "
            f"({skipped} skipped)"
        )

        return truncated_files, notice

    def _estimate_tokens(self, content: str) -> int:
        """Rough estimate of token count for content (T041, FR-021).

        Uses rough heuristic: 1 token ≈ 4 characters. This is a conservative
        estimate for determining when to chunk reviews.

        Args:
            content: Text content to estimate.

        Returns:
            Estimated token count.

        Examples:
            >>> agent._estimate_tokens("Hello world!")
            3
            >>> agent._estimate_tokens("A" * 400)
            100
        """
        return len(content) // 4

    def _chunk_files(
        self,
        files: list[str],
        diff_content: str,
    ) -> list[list[str]]:
        """Split files into chunks respecting token budget (T042, FR-021).

        Each chunk's combined diff content should be under MAX_TOKENS_PER_CHUNK.
        Files are kept together (not split mid-file).

        Args:
            files: List of file paths to chunk.
            diff_content: Full diff content for all files.

        Returns:
            List of file chunks, where each chunk is a list of file paths.

        Examples:
            >>> files = ["a.py", "b.py", "c.py"]
            >>> diff = "small diff content"
            >>> agent._chunk_files(files, diff)
            [['a.py', 'b.py', 'c.py']]

        Note:
            This is a best-effort chunking strategy. Very large individual files
            may still exceed the token limit.
        """
        chunks: list[list[str]] = []
        current_chunk: list[str] = []
        current_tokens = 0

        for file_path in files:
            # Extract this file's diff section (heuristic: find the file's diff block)
            # This is approximate - we estimate based on the full diff content
            file_pattern = rf"diff --git a/{re.escape(file_path)} b/{re.escape(file_path)}"
            file_match = re.search(file_pattern, diff_content)

            if file_match:
                # Find next file or end of diff
                start_pos = file_match.start()
                next_file_pattern = r"diff --git a/"
                next_match = re.search(next_file_pattern, diff_content[start_pos + 1:])

                if next_match:
                    file_diff = diff_content[start_pos:start_pos + 1 + next_match.start()]
                else:
                    file_diff = diff_content[start_pos:]

                file_tokens = self._estimate_tokens(file_diff)
            else:
                # Fallback: assume average token count
                file_tokens = 1000

            # Check if adding this file would exceed chunk limit
            if current_tokens + file_tokens > MAX_TOKENS_PER_CHUNK and current_chunk:
                # Start new chunk
                chunks.append(current_chunk)
                current_chunk = [file_path]
                current_tokens = file_tokens
            else:
                # Add to current chunk
                current_chunk.append(file_path)
                current_tokens += file_tokens

        # Add final chunk if not empty
        if current_chunk:
            chunks.append(current_chunk)

        # Ensure we always return at least one chunk
        if not chunks:
            chunks = [files] if files else [[]]

        return chunks
