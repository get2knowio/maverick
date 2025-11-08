"""Temporal activity for automated review & fix loop.

This module orchestrates CodeRabbit review and OpenCode fix tooling to
automatically identify and remediate issues in AI-generated code changes.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from temporalio import activity

from src.models.review_fix import (
    CodeReviewFindings,
    CodeReviewIssue,
    FixAttemptRecord,
    IssueSeverity,
    ReviewLoopInput,
    ReviewLoopOutcome,
    ValidationResult,
)
from src.utils.logging import get_structured_logger
from src.utils.phase_results_store import (
    save_fix_summary,
    save_review_outcome,
    save_sanitized_prompt,
)
from src.utils.retry_fingerprint import (
    compute_findings_hash,
    compute_review_fingerprint,
)


logger = get_structured_logger("activity.review_fix")

# Timeout for CodeRabbit CLI execution (seconds)
CODERABBIT_TIMEOUT = 120

# Timeout for OpenCode CLI execution (seconds)
OPENCODE_TIMEOUT = 300

# Timeout for validation command execution (seconds)
VALIDATION_TIMEOUT = 600

# Default validation command - Rust project validation via cargo
DEFAULT_VALIDATION_CMD = ["cargo", "test", "--all", "--locked"]


async def _invoke_coderabbit_cli(branch_ref: str, commit_range: list[str]) -> tuple[bytes, bytes, int]:
    """Invoke CodeRabbit CLI via uv and capture output.

    Args:
        branch_ref: Branch reference to review
        commit_range: List of commit SHAs to review

    Returns:
        Tuple of (stdout, stderr, exit_code)

    Raises:
        FileNotFoundError: If CodeRabbit CLI not found
        TimeoutError: If CLI execution exceeds timeout
    """
    started_at = datetime.now(UTC)

    logger.info(
        "coderabbit_invocation_started",
        branch_ref=branch_ref,
        commit_count=len(commit_range),
        timeout_seconds=CODERABBIT_TIMEOUT,
    )

    # Build CodeRabbit command
    # Note: Actual CodeRabbit CLI invocation would be:
    # ["uv", "run", "coderabbit", "review", branch_ref, "--commits", ",".join(commit_range)]
    # For now, we'll use a simpler command that can be mocked
    cmd = ["uv", "run", "coderabbit", "review", branch_ref]
    if commit_range:
        cmd.extend(["--commits", ",".join(commit_range)])

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=CODERABBIT_TIMEOUT,
        )

        exit_code = process.returncode or 0
        completed_at = datetime.now(UTC)
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

        logger.info(
            "coderabbit_invocation_completed",
            exit_code=exit_code,
            stdout_bytes=len(stdout),
            stderr_bytes=len(stderr),
            duration_ms=duration_ms,
        )

        return stdout, stderr, exit_code

    except TimeoutError as e:
        completed_at = datetime.now(UTC)
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)
        logger.error(
            "coderabbit_invocation_timeout",
            timeout_seconds=CODERABBIT_TIMEOUT,
            duration_ms=duration_ms,
        )
        raise TimeoutError(f"CodeRabbit execution exceeded {CODERABBIT_TIMEOUT}s timeout") from e
    except FileNotFoundError as e:
        logger.error(
            "coderabbit_cli_not_found",
            error=str(e),
        )
        raise


def _sanitize_transcript(transcript: str) -> str:
    """Sanitize transcript for safe storage and forwarding to OpenCode.

    Applies:
    - AWS key pattern redaction
    - GitHub token redaction
    - PEM block redaction
    - Length truncation to 10000 characters
    - Whitespace normalization

    Args:
        transcript: Raw CodeRabbit transcript

    Returns:
        Sanitized transcript safe for storage and forwarding
    """
    sanitized = transcript

    # Redact AWS keys (pattern: AKIA followed by 16 alphanumeric)
    aws_pattern = r'AKIA[0-9A-Z]{16}'
    if re.search(aws_pattern, sanitized):
        sanitized = re.sub(aws_pattern, '[REDACTED-AWS-KEY]', sanitized)
        logger.info("sanitization_redacted_aws_keys")

    # Redact GitHub tokens (pattern: ghp_ or gho_ followed by alphanumeric)
    github_pattern = r'gh[po]_[A-Za-z0-9]{36,255}'
    if re.search(github_pattern, sanitized):
        sanitized = re.sub(github_pattern, '[REDACTED-GITHUB-TOKEN]', sanitized)
        logger.info("sanitization_redacted_github_tokens")

    # Redact PEM blocks
    pem_pattern = r'-----BEGIN [A-Z ]+-----[\s\S]*?-----END [A-Z ]+-----'
    if re.search(pem_pattern, sanitized):
        sanitized = re.sub(pem_pattern, '[REDACTED-PEM-BLOCK]', sanitized)
        logger.info("sanitization_redacted_pem_blocks")

    # Truncate to max length
    max_length = 10000
    if len(sanitized) > max_length:
        original_length = len(sanitized)
        sanitized = sanitized[:max_length] + "\n[... truncated ...]"
        logger.info(
            "sanitization_truncated",
            original_length=original_length,
            max_length=max_length,
        )

    # Normalize whitespace - preserve line breaks, collapse horizontal whitespace
    # Replace runs of spaces/tabs with single space
    sanitized = re.sub(r'[ \t]+', ' ', sanitized)
    # Strip trailing/leading whitespace per line while preserving newlines
    lines = sanitized.split('\n')
    sanitized = '\n'.join(line.strip() for line in lines)

    return sanitized


def _parse_coderabbit_transcript(transcript: str) -> list[CodeReviewIssue]:
    """Parse CodeRabbit transcript into structured issues.

    Extracts issues from transcript using heuristic pattern matching:
    - Lines starting with [SEVERITY] are issue titles
    - Following lines starting with "Details:" are issue details
    - Lines with file:line patterns are anchors

    Args:
        transcript: Raw CodeRabbit transcript

    Returns:
        List of CodeReviewIssue objects, sorted by severity (blocker > major > minor)
    """
    issues = []

    # Pattern: [SEVERITY] title text
    # Details: details text
    # Optional: file.rs:line
    issue_pattern = r'\[(BLOCKER|MAJOR|MINOR)\]\s+(.+?)(?:\n|$)'
    details_pattern = r'Details:\s+(.+?)(?:\n|$)'
    anchor_pattern = r'([a-zA-Z0-9_/.-]+\.rs):(\d+)'

    lines = transcript.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]

        # Check for issue header
        issue_match = re.match(issue_pattern, line)
        if issue_match:
            severity_str = issue_match.group(1).lower()
            # Map to IssueSeverity type (validated by regex pattern)
            severity: IssueSeverity = severity_str  # type: ignore[assignment]
            title = issue_match.group(2).strip()

            # Look for details on next line
            details = ""
            anchor = None

            if i + 1 < len(lines):
                next_line = lines[i + 1]
                details_match = re.match(details_pattern, next_line)
                if details_match:
                    details = details_match.group(1).strip()
                    i += 1  # Skip details line

                    # Look for anchor in details or title
                    anchor_match = re.search(anchor_pattern, title + " " + details)
                    if anchor_match:
                        anchor = f"{anchor_match.group(1)}:{anchor_match.group(2)}"

            if not details:
                details = title  # Use title as details if no explicit details

            issues.append(
                CodeReviewIssue(
                    title=title,
                    severity=severity,
                    details=details,
                    anchor=anchor,
                )
            )

        i += 1

    # Sort by severity: blocker > major > minor
    severity_order = {"blocker": 0, "major": 1, "minor": 2}
    issues.sort(key=lambda x: severity_order[x.severity])

    logger.info(
        "coderabbit_transcript_parsed",
        issue_count=len(issues),
        blockers=sum(1 for i in issues if i.severity == "blocker"),
        majors=sum(1 for i in issues if i.severity == "major"),
        minors=sum(1 for i in issues if i.severity == "minor"),
    )

    return issues


def _generate_fingerprint(commit_range: list[str], findings_hash: str) -> str:
    """Generate deterministic fingerprint for retry detection.

    Uses shared fingerprint utility for consistency.

    Args:
        commit_range: List of commit SHAs
        findings_hash: SHA-256 hash of CodeRabbit findings

    Returns:
        64-character hex fingerprint
    """
    fingerprint = compute_review_fingerprint(commit_range, findings_hash)

    logger.info(
        "fingerprint_generated",
        commit_count=len(commit_range),
        fingerprint=fingerprint,
    )

    return fingerprint


async def _invoke_opencode_cli(sanitized_prompt: str, branch_ref: str) -> FixAttemptRecord:
    """Invoke OpenCode CLI to apply fixes based on sanitized prompt.

    Args:
        sanitized_prompt: Sanitized CodeRabbit findings to guide fixes
        branch_ref: Branch reference where fixes should be applied

    Returns:
        FixAttemptRecord with execution details and results

    Raises:
        FileNotFoundError: If OpenCode CLI not found
        TimeoutError: If CLI execution exceeds timeout
    """
    import uuid

    started_at = datetime.now(UTC)
    request_id = f"ocp-{uuid.uuid4().hex[:12]}"

    logger.info(
        "opencode_invocation_started",
        request_id=request_id,
        branch_ref=branch_ref,
        prompt_length=len(sanitized_prompt),
        timeout_seconds=OPENCODE_TIMEOUT,
    )

    # Write prompt to temporary file to avoid argv length limits
    import tempfile
    temp_prompt_file = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as f:
            f.write(sanitized_prompt)
            f.flush()
            temp_prompt_file = f.name

        # Build OpenCode command using temp file
        # Note: Actual OpenCode CLI invocation pattern (to be determined from tooling docs)
        # For now: uv run opencode implement --prompt-file <file> --branch <branch>
        cmd = ["uv", "run", "opencode", "implement", "--branch", branch_ref, "--prompt-file", temp_prompt_file]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=OPENCODE_TIMEOUT,
        )

        exit_code = process.returncode or 0
        completed_at = datetime.now(UTC)

        # Decode with tolerant error handling
        stdout_text = stdout.decode('utf-8', errors='replace')
        stderr_text = stderr.decode('utf-8', errors='replace')

        # Parse applied changes from stdout
        applied_changes = _parse_opencode_changes(stdout_text)

        logger.info(
            "opencode_invocation_completed",
            request_id=request_id,
            exit_code=exit_code,
            changes_count=len(applied_changes),
            stdout_bytes=len(stdout),
            stderr_bytes=len(stderr),
        )

        return FixAttemptRecord(
            request_id=request_id,
            sanitized_prompt=sanitized_prompt,
            exit_code=exit_code,
            started_at=started_at,
            completed_at=completed_at,
            applied_changes=applied_changes,
            stdout=stdout_text,
            stderr=stderr_text,
        )

    except TimeoutError as e:
        completed_at = datetime.now(UTC)
        logger.error(
            "opencode_invocation_timeout",
            request_id=request_id,
            timeout_seconds=OPENCODE_TIMEOUT,
        )
        raise TimeoutError(f"OpenCode execution exceeded {OPENCODE_TIMEOUT}s timeout") from e
    except FileNotFoundError as e:
        completed_at = datetime.now(UTC)
        logger.error(
            "opencode_cli_not_found",
            request_id=request_id,
            error=str(e),
        )
        raise
    finally:
        # Clean up temporary prompt file
        if temp_prompt_file:
            try:
                import os
                os.unlink(temp_prompt_file)
            except Exception:
                pass  # Ignore cleanup errors


def _parse_opencode_changes(stdout: str) -> list[str]:
    """Parse list of modified files from OpenCode output.

    Looks for patterns like:
    - Modified files:
    - Applied changes to:
    - Changed: <file>
    - Applied fixes/changes

    Args:
        stdout: OpenCode stdout text

    Returns:
        List of file paths that were modified (or ["<inferred>"] if changes detected but no files listed)
    """
    changes = []

    # Pattern 1: "Modified files:" section
    if "Modified files:" in stdout:
        lines = stdout.split('\n')
        in_section = False
        for line in lines:
            if "Modified files:" in line:
                in_section = True
                continue
            if in_section:
                # Look for file paths (usually indented)
                match = re.search(r'[-*]\s+(.+\.rs)', line)
                if match:
                    changes.append(match.group(1).strip())
                elif line.strip() and not line.strip().startswith(('-', '*', ' ')):
                    # End of section
                    break

    # Pattern 2: "Applied changes to" or "Changed:"
    changed_pattern = r'(?:Applied changes to|Changed:|Modified):\s+(.+\.rs)'
    for match in re.finditer(changed_pattern, stdout):
        file_path = match.group(1).strip()
        if file_path not in changes:
            changes.append(file_path)

    # Pattern 3: File paths anywhere in output (src/*.rs pattern)
    file_pattern = r'(src/[a-zA-Z0-9_/.-]+\.rs)'
    for match in re.finditer(file_pattern, stdout):
        file_path = match.group(1).strip()
        if file_path not in changes:
            changes.append(file_path)

    # Pattern 4: Look for generic success indicators if no files found
    # If OpenCode says it did something but we can't parse files, assume it worked
    if not changes:
        success_indicators = [
            "applied",
            "fixed",
            "changes:",
            "modified:",
            "updated:",
            "correction",
        ]
        stdout_lower = stdout.lower()
        for indicator in success_indicators:
            if indicator in stdout_lower:
                # Infer that changes were made even if we can't parse file list
                changes.append("<inferred>")
                break

    return changes


def _build_failure_diagnostics(
    findings: CodeReviewFindings | None,
    fix_attempt: FixAttemptRecord | None,
    validation_result: ValidationResult | None,
) -> str:
    """Build human-readable failure diagnostics for escalation.

    Args:
        findings: CodeRabbit findings (if available)
        fix_attempt: OpenCode fix attempt (if attempted)
        validation_result: Validation result (if executed)

    Returns:
        Formatted diagnostic message for human consumption
    """
    diagnostics = []

    # CodeRabbit findings summary
    if findings and findings.issues:
        diagnostics.append(f"CodeRabbit identified {len(findings.issues)} issue(s):")
        for i, issue in enumerate(findings.issues[:5], 1):  # Show first 5
            diagnostics.append(f"  {i}. [{issue.severity.upper()}] {issue.title}")
            if issue.anchor:
                diagnostics.append(f"     Location: {issue.anchor}")
        if len(findings.issues) > 5:
            diagnostics.append(f"  ... and {len(findings.issues) - 5} more issue(s)")
        diagnostics.append("")

    # OpenCode failure details
    if fix_attempt:
        if fix_attempt.exit_code != 0:
            diagnostics.append(f"OpenCode failed with exit code {fix_attempt.exit_code}")
            if fix_attempt.stderr:
                # Show first few lines of stderr
                stderr_lines = fix_attempt.stderr.strip().split('\n')[:10]
                diagnostics.append("Error output:")
                for line in stderr_lines:
                    diagnostics.append(f"  {line}")
                if len(fix_attempt.stderr.split('\n')) > 10:
                    diagnostics.append("  ...")
            diagnostics.append("")
        elif not fix_attempt.applied_changes:
            diagnostics.append("OpenCode ran successfully but produced no changes")
            diagnostics.append("Possible reasons:")
            diagnostics.append("  - Issues require manual intervention")
            diagnostics.append("  - Prompt was not actionable")
            diagnostics.append("  - Changes would introduce new issues")
            diagnostics.append("")

    # Validation failure details
    if validation_result and validation_result.exit_code != 0:
        diagnostics.append(f"Validation failed with exit code {validation_result.exit_code}")
        diagnostics.append(f"Command: {' '.join(validation_result.command)}")
        if validation_result.stderr:
            # Show first few lines of stderr
            stderr_lines = validation_result.stderr.strip().split('\n')[:10]
            diagnostics.append("Error output:")
            for line in stderr_lines:
                diagnostics.append(f"  {line}")
            if len(validation_result.stderr.split('\n')) > 10:
                diagnostics.append("  ...")
        diagnostics.append("")

    # Recommendations
    diagnostics.append("Recommended next steps:")
    if fix_attempt and fix_attempt.exit_code != 0:
        diagnostics.append("  1. Review OpenCode error output above")
        diagnostics.append("  2. Check if prompt formatting is correct")
        diagnostics.append("  3. Verify OpenCode CLI is properly configured")
    elif fix_attempt and not fix_attempt.applied_changes:
        diagnostics.append("  1. Review CodeRabbit findings for manual intervention requirements")
        diagnostics.append("  2. Consider refining the implementation approach")
        diagnostics.append("  3. Check if issues require architectural changes")
    elif validation_result and validation_result.exit_code != 0:
        diagnostics.append("  1. Review validation error output above")
        diagnostics.append("  2. Check if fixes introduced new issues")
        diagnostics.append("  3. Consider running validation locally to debug")
    else:
        diagnostics.append("  1. Review CodeRabbit findings")
        diagnostics.append("  2. Determine if manual intervention is required")
        diagnostics.append("  3. Check activity logs for detailed error information")

    return "\n".join(diagnostics)


async def _invoke_validation_command(
    validation_command: list[str] | None,
    branch_ref: str,
) -> ValidationResult:
    """Execute validation command (default: cargo test) and capture results.

    Args:
        validation_command: Custom validation command or None for default
        branch_ref: Branch reference being validated

    Returns:
        ValidationResult with execution details and outcome
    """
    started_at = datetime.now(UTC)
    cmd = validation_command if validation_command else DEFAULT_VALIDATION_CMD

    logger.info(
        "validation_invocation_started",
        command=" ".join(cmd),
        branch_ref=branch_ref,
        timeout_seconds=VALIDATION_TIMEOUT,
    )

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=VALIDATION_TIMEOUT,
        )

        exit_code = process.returncode or 0
        completed_at = datetime.now(UTC)

        # Decode with tolerant error handling
        stdout_text = stdout.decode('utf-8', errors='replace')
        stderr_text = stderr.decode('utf-8', errors='replace')

        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

        logger.info(
            "validation_invocation_completed",
            exit_code=exit_code,
            duration_ms=duration_ms,
            stdout_bytes=len(stdout),
            stderr_bytes=len(stderr),
        )

        return ValidationResult(
            command=cmd,
            exit_code=exit_code,
            started_at=started_at,
            completed_at=completed_at,
            stdout=stdout_text,
            stderr=stderr_text,
        )

    except TimeoutError as e:
        completed_at = datetime.now(UTC)
        logger.error(
            "validation_invocation_timeout",
            timeout_seconds=VALIDATION_TIMEOUT,
        )
        raise TimeoutError(f"Validation execution exceeded {VALIDATION_TIMEOUT}s timeout") from e
    except FileNotFoundError as e:
        completed_at = datetime.now(UTC)
        logger.error(
            "validation_command_not_found",
            command=" ".join(cmd),
            error=str(e),
        )
        raise


@activity.defn(name="run_review_fix_loop")
async def run_review_fix_loop(input_data: ReviewLoopInput) -> ReviewLoopOutcome:
    """Temporal activity for automated review & fix loop.

    Orchestrates:
    1. CodeRabbit CLI review of specified branch/commits
    2. Transcript parsing and sanitization
    3. Optional OpenCode fix invocation (if enable_fixes=True)
    4. Validation command execution
    5. Outcome classification and artifact persistence

    Args:
        input_data: ReviewLoopInput with branch, commits, and configuration

    Returns:
        ReviewLoopOutcome with status, findings, and artifacts
    """
    logger.info(
        "review_fix_loop_started",
        branch_ref=input_data.branch_ref,
        commit_count=len(input_data.commit_range),
        enable_fixes=input_data.enable_fixes,
        has_retry_metadata=input_data.retry_metadata is not None,
    )

    started_at = datetime.now(UTC)

    # Step 0: Check for retry with same fingerprint (short-circuit if duplicate)
    if input_data.retry_metadata is not None:
        logger.info(
            "retry_detected",
            previous_fingerprint=input_data.retry_metadata.previous_fingerprint,
            attempt_counter=input_data.retry_metadata.attempt_counter,
            last_status=input_data.retry_metadata.last_status,
        )

    # Step 1: Invoke CodeRabbit CLI
    try:
        stdout, stderr, exit_code = await _invoke_coderabbit_cli(
            input_data.branch_ref,
            input_data.commit_range,
        )

        # Decode with tolerant error handling (per AGENTS.md best practices)
        transcript = stdout.decode('utf-8', errors='replace')
        stderr_text = stderr.decode('utf-8', errors='replace')

        if exit_code != 0:
            logger.error(
                "coderabbit_cli_failed",
                exit_code=exit_code,
                stderr=stderr_text[:500],
            )

            # Generate failure fingerprint
            fingerprint = hashlib.sha256(
                f"{','.join(input_data.commit_range)}:cli_failed".encode()
            ).hexdigest()

            return ReviewLoopOutcome(
                status="failed",
                fingerprint=fingerprint,
                completed_at=datetime.now(UTC),
                issues_fixed=0,
                code_review_findings=None,
                artifacts_path="",
            )

    except (FileNotFoundError, TimeoutError) as e:
        logger.error(
            "coderabbit_invocation_error",
            error_type=type(e).__name__,
            error=str(e),
        )

        # Generate failure fingerprint
        fingerprint = hashlib.sha256(
            f"{','.join(input_data.commit_range)}:invocation_failed".encode()
        ).hexdigest()

        return ReviewLoopOutcome(
            status="failed",
            fingerprint=fingerprint,
            completed_at=datetime.now(UTC),
            issues_fixed=0,
            code_review_findings=None,
            artifacts_path="",
        )

    # Step 2: Parse transcript into structured findings
    issues = _parse_coderabbit_transcript(transcript)

    # Step 3: Sanitize transcript
    sanitized_prompt = _sanitize_transcript(transcript)

    # Step 4: Generate raw hash and fingerprint
    raw_hash = hashlib.sha256(transcript.encode()).hexdigest()
    findings_hash = compute_findings_hash(sanitized_prompt)
    fingerprint = _generate_fingerprint(input_data.commit_range, findings_hash)

    # Step 4.5: Check if this is a duplicate retry
    if input_data.retry_metadata is not None:
        if fingerprint == input_data.retry_metadata.previous_fingerprint:
            logger.info(
                "retry_duplicate_detected",
                fingerprint=fingerprint,
                attempt_counter=input_data.retry_metadata.attempt_counter,
                action="returning_previous_result",
            )

            # Return cached result from retry metadata
            completed_at = datetime.now(UTC)
            return ReviewLoopOutcome(
                status=input_data.retry_metadata.last_status,  # type: ignore[arg-type]
                fingerprint=fingerprint,
                completed_at=completed_at,
                issues_fixed=0,  # Can't reconstruct exact count, but status indicates outcome
                code_review_findings=None,  # Don't re-parse
                fix_attempt=None,
                validation_result=None,
                artifacts_path=input_data.retry_metadata.artifacts_path or "",
            )
        else:
            logger.info(
                "retry_fingerprint_changed",
                old_fingerprint=input_data.retry_metadata.previous_fingerprint,
                new_fingerprint=fingerprint,
                action="proceeding_with_fresh_review",
            )

    # Step 5: Build CodeReviewFindings
    findings = CodeReviewFindings(
        issues=issues,
        sanitized_prompt=sanitized_prompt,
        raw_hash=raw_hash,
        generated_at=datetime.now(UTC),
        transcript=transcript,
        summary=f"Found {len(issues)} issue(s)" if issues else "No issues found",
    )

    # Step 6: Determine if fixes should be applied
    fix_attempt: FixAttemptRecord | None = None
    validation_result: ValidationResult | None = None
    issues_fixed = 0
    status: str = "clean"

    if len(issues) == 0:
        # No issues found, clean outcome
        status = "clean"
        logger.info(
            "review_loop_clean",
            fingerprint=fingerprint,
        )

    elif not input_data.enable_fixes:
        # Issues found but fixes disabled
        status = "failed"
        logger.info(
            "review_loop_issues_found_no_fixes",
            issue_count=len(issues),
            fingerprint=fingerprint,
        )

    else:
        # Issues found and fixes enabled - invoke OpenCode
        logger.info(
            "review_loop_attempting_fixes",
            issue_count=len(issues),
        )

        try:
            fix_attempt = await _invoke_opencode_cli(sanitized_prompt, input_data.branch_ref)

            if fix_attempt.exit_code != 0:
                # OpenCode failed
                status = "failed"
                logger.error(
                    "opencode_failed",
                    exit_code=fix_attempt.exit_code,
                    stderr_preview=fix_attempt.stderr[:200],
                )

            elif len(fix_attempt.applied_changes) == 0:
                # OpenCode succeeded but made no changes
                status = "failed"
                logger.warning(
                    "opencode_no_changes",
                    stdout_preview=fix_attempt.stdout[:200],
                )

            else:
                # OpenCode applied fixes - run validation
                logger.info(
                    "opencode_fixes_applied",
                    changes_count=len(fix_attempt.applied_changes),
                )

                try:
                    validation_result = await _invoke_validation_command(
                        input_data.validation_command,
                        input_data.branch_ref,
                    )

                    if validation_result.exit_code == 0:
                        # Validation passed - fixes successful
                        status = "fixed"
                        issues_fixed = len(issues)
                        logger.info(
                            "validation_passed",
                            issues_fixed=issues_fixed,
                        )
                    else:
                        # Validation failed despite fixes
                        status = "failed"
                        logger.error(
                            "validation_failed",
                            exit_code=validation_result.exit_code,
                            stderr_preview=validation_result.stderr[:200],
                        )

                except (FileNotFoundError, TimeoutError) as e:
                    # Validation command failed
                    status = "failed"
                    logger.error(
                        "validation_invocation_error",
                        error_type=type(e).__name__,
                        error=str(e),
                    )

        except (FileNotFoundError, TimeoutError) as e:
            # OpenCode invocation failed
            status = "failed"
            logger.error(
                "opencode_invocation_error",
                error_type=type(e).__name__,
                error=str(e),
            )

    completed_at = datetime.now(UTC)
    duration_ms = int((completed_at - started_at).total_seconds() * 1000)

    # Step 7: Persist artifacts
    artifacts_path = ""
    try:
        import tempfile
        base_artifacts_dir = Path(tempfile.gettempdir()) / "maverick-artifacts"
        artifacts_dir = base_artifacts_dir / fingerprint
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Save sanitized prompt
        if findings.sanitized_prompt:
            prompt_path = save_sanitized_prompt(
                findings.sanitized_prompt,
                fingerprint,
                artifacts_dir,
            )
            logger.info("artifact_saved", artifact_type="sanitized_prompt", path=str(prompt_path))

        # Save fix summary if fix was attempted
        if fix_attempt and fix_attempt.stdout:
            summary_path = save_fix_summary(
                fix_attempt.stdout,
                fingerprint,
                artifacts_dir,
            )
            logger.info("artifact_saved", artifact_type="fix_summary", path=str(summary_path))

        # Save failure diagnostics if status is failed
        if status == "failed":
            diagnostics = _build_failure_diagnostics(findings, fix_attempt, validation_result)
            diagnostics_file = artifacts_dir / f"diagnostics_{fingerprint}.txt"
            with diagnostics_file.open("w", encoding="utf-8") as f:
                f.write(diagnostics)
            logger.info(
                "artifact_saved",
                artifact_type="failure_diagnostics",
                path=str(diagnostics_file),
            )

        artifacts_path = str(artifacts_dir)

    except Exception as e:
        logger.error(
            "artifact_persistence_failed",
            error_type=type(e).__name__,
            error=str(e),
        )
        # Don't fail the activity on persistence errors

    # Calculate phase-specific metrics for SC-001/SC-002
    coderabbit_duration_ms: int | None = None
    opencode_duration_ms: int | None = None
    validation_duration_ms: int | None = None

    if fix_attempt:
        opencode_duration_ms = int(
            (fix_attempt.completed_at - fix_attempt.started_at).total_seconds() * 1000
        )

    if validation_result:
        validation_duration_ms = int(
            (validation_result.completed_at - validation_result.started_at).total_seconds() * 1000
        )

    logger.info(
        "review_fix_loop_completed",
        status=status,
        issue_count=len(issues),
        issues_fixed=issues_fixed,
        duration_ms=duration_ms,
        artifacts_path=artifacts_path,
        # Performance metrics (SC-001: clean runs <2min, SC-002: 80% fixed first pass)
        coderabbit_duration_ms=coderabbit_duration_ms,
        opencode_duration_ms=opencode_duration_ms,
        validation_duration_ms=validation_duration_ms,
        first_pass_success=status == "fixed" if issues_fixed > 0 else None,
    )

    # Create outcome
    outcome = ReviewLoopOutcome(
        status=status,  # type: ignore[arg-type]
        fingerprint=fingerprint,
        completed_at=completed_at,
        issues_fixed=issues_fixed,
        code_review_findings=findings,
        fix_attempt=fix_attempt,
        validation_result=validation_result,
        artifacts_path=artifacts_path,
    )

    # Step 8: Persist outcome to JSON
    try:
        outcome_file = Path(artifacts_path) / "review_outcome.json"
        save_review_outcome(outcome, outcome_file)
        logger.info("outcome_saved", path=str(outcome_file))
    except Exception as e:
        logger.error(
            "outcome_persistence_failed",
            error_type=type(e).__name__,
            error=str(e),
        )
        # Don't fail the activity on persistence errors

    return outcome


__all__ = ["run_review_fix_loop"]
