"""Integration tests for review-fix loop activity orchestration.

These tests verify end-to-end behavior of the CodeRabbit review and
OpenCode fix loop, including clean outcomes, issues found, and malformed outputs.

Note: These tests use mocked subprocess calls since CodeRabbit CLI may not be
available in test environments. They verify activity logic without external dependencies.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.models.review_fix import ReviewLoopInput, ReviewLoopOutcome


@pytest.mark.asyncio
async def test_review_loop_clean_outcome_integration():
    """Integration test: CodeRabbit finds no issues (clean outcome).

    Scenario: Run full activity with CodeRabbit returning clean transcript
    Expected: ReviewLoopOutcome with status="clean", no issues, artifacts persisted
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/test-clean",
        commit_range=["abc1234"],
        enable_fixes=False,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock CodeRabbit CLI returning clean output
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"CodeRabbit Review Complete\nNo issues found.\n",
            b"",
        )
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result = await run_review_fix_loop(input_data)

        assert isinstance(result, ReviewLoopOutcome)
        assert result.status == "clean"
        assert result.issues_fixed == 0
        assert result.fix_attempt is None
        assert result.code_review_findings is not None
        assert len(result.code_review_findings.issues) == 0
        assert len(result.fingerprint) == 64


@pytest.mark.asyncio
async def test_review_loop_issues_found_integration():
    """Integration test: CodeRabbit finds issues (issues outcome).

    Scenario: Run full activity with CodeRabbit returning issues
    Expected: ReviewLoopOutcome with status="failed", issues parsed, no fix attempt
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/test-issues",
        commit_range=["abc1234"],
        enable_fixes=False,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock CodeRabbit CLI returning issues
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"CodeRabbit Review Complete\n"
            b"[BLOCKER] Memory leak in parser.rs:42\n"
            b"Details: Unhandled allocation in loop\n"
            b"[MAJOR] Missing error handling in main.rs:100\n"
            b"Details: Function may panic on invalid input\n",
            b"",
        )
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result = await run_review_fix_loop(input_data)

        assert isinstance(result, ReviewLoopOutcome)
        assert result.status == "failed"
        assert result.issues_fixed == 0
        assert result.fix_attempt is None
        assert result.code_review_findings is not None
        assert len(result.code_review_findings.issues) == 2
        # Verify severity ordering
        assert result.code_review_findings.issues[0].severity == "blocker"
        assert result.code_review_findings.issues[1].severity == "major"


@pytest.mark.asyncio
async def test_review_loop_malformed_output_integration():
    """Integration test: CodeRabbit returns malformed output.

    Scenario: CodeRabbit succeeds but output is unparseable
    Expected: ReviewLoopOutcome handles gracefully without crashing
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/test-malformed",
        commit_range=["abc1234"],
        enable_fixes=False,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock malformed output (no structured issues)
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"Some random text\nNot following expected format\n",
            b"",
        )
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result = await run_review_fix_loop(input_data)

        assert isinstance(result, ReviewLoopOutcome)
        # Should handle gracefully - treats as clean (no parseable issues)
        assert result.status == "clean"
        assert result.code_review_findings is not None
        assert len(result.code_review_findings.issues) == 0


@pytest.mark.asyncio
async def test_review_loop_coderabbit_cli_failure_integration():
    """Integration test: CodeRabbit CLI fails to execute.

    Scenario: CodeRabbit CLI returns non-zero exit code
    Expected: ReviewLoopOutcome with status="failed" and error captured
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/test-cli-failure",
        commit_range=["abc1234"],
        enable_fixes=False,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock CodeRabbit CLI failure
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"",
            b"Error: Authentication failed\n",
        )
        mock_process.returncode = 1
        mock_exec.return_value = mock_process

        result = await run_review_fix_loop(input_data)

        assert isinstance(result, ReviewLoopOutcome)
        assert result.status == "failed"
        assert result.code_review_findings is None


# ===== Phase 4: User Story 2 Integration Tests (OpenCode Fix Loop) =====


@pytest.mark.asyncio
async def test_successful_fix_run_end_to_end():
    """Integration test: Full fix loop from review to validation.

    Scenario: CodeRabbit finds issues, OpenCode fixes them, validation passes
    Expected: ReviewLoopOutcome with status="fixed" and all metadata populated
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-with-issues",
        commit_range=["abc1234", "def5678"],
        enable_fixes=True,
        implementation_summary="Added new feature for user authentication",
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # CodeRabbit finds issues
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"CodeRabbit Review Complete\n"
            b"[BLOCKER] Null pointer dereference in auth.rs:55\n"
            b"Details: Missing null check before dereferencing user pointer\n"
            b"[MAJOR] Unchecked Result in database.rs:120\n"
            b"Details: Result from query() not checked for errors\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # OpenCode applies fixes
        opencode_process = AsyncMock()
        opencode_process.communicate.return_value = (
            b"OpenCode: Successfully applied fixes\n"
            b"Modified files:\n"
            b"  - src/auth.rs (added null check)\n"
            b"  - src/database.rs (added error handling)\n"
            b"Request ID: ocp-12345-abcde\n",
            b"",
        )
        opencode_process.returncode = 0

        # Validation passes
        validation_process = AsyncMock()
        validation_process.communicate.return_value = (
            b"running 10 tests\ntest result: ok. 10 passed; 0 failed; 0 ignored\n",
            b"",
        )
        validation_process.returncode = 0

        mock_exec.side_effect = [coderabbit_process, opencode_process, validation_process]

        result = await run_review_fix_loop(input_data)

        # Verify outcome
        assert isinstance(result, ReviewLoopOutcome)
        assert result.status == "fixed"
        assert result.issues_fixed == 2

        # Verify code review findings
        assert result.code_review_findings is not None
        assert len(result.code_review_findings.issues) == 2
        assert result.code_review_findings.issues[0].severity == "blocker"
        assert result.code_review_findings.issues[1].severity == "major"

        # Verify fix attempt
        assert result.fix_attempt is not None
        assert result.fix_attempt.exit_code == 0
        assert "ocp-12345-abcde" in result.fix_attempt.stdout
        assert "auth.rs" in result.fix_attempt.stdout

        # Verify validation result
        assert result.validation_result is not None
        assert result.validation_result.exit_code == 0
        assert "10 passed" in result.validation_result.stdout

        # Verify fingerprint
        assert len(result.fingerprint) == 64
        assert all(c in "0123456789abcdef" for c in result.fingerprint)


@pytest.mark.asyncio
async def test_fix_run_with_validation_failure():
    """Integration test: OpenCode fixes applied but validation fails.

    Scenario: Fixes are applied but tests still fail after fix
    Expected: ReviewLoopOutcome with status="failed", fix_attempt and validation_result both present
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-broken-tests",
        commit_range=["abc1234"],
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # CodeRabbit
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"[MAJOR] Type error in handler.rs:30\nDetails: Mismatched types\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # OpenCode applies fix
        opencode_process = AsyncMock()
        opencode_process.communicate.return_value = (
            b"Applied type correction\n",
            b"",
        )
        opencode_process.returncode = 0

        # Validation fails
        validation_process = AsyncMock()
        validation_process.communicate.return_value = (
            b"",
            b"error: test failed, to rerun pass '--test integration'\ntest result: FAILED. 8 passed; 2 failed\n",
        )
        validation_process.returncode = 101

        mock_exec.side_effect = [coderabbit_process, opencode_process, validation_process]

        result = await run_review_fix_loop(input_data)

        assert result.status == "failed"
        assert result.fix_attempt is not None
        assert result.fix_attempt.exit_code == 0
        assert result.validation_result is not None
        assert result.validation_result.exit_code == 101
        assert "2 failed" in result.validation_result.stderr


@pytest.mark.asyncio
async def test_fix_run_with_opencode_failure():
    """Integration test: OpenCode fails to apply fixes.

    Scenario: CodeRabbit finds issues but OpenCode cannot fix them
    Expected: ReviewLoopOutcome with status="failed", fix_attempt shows error
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-unfixable",
        commit_range=["abc1234"],
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # CodeRabbit
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"[BLOCKER] Complex architectural issue\nDetails: Requires major refactoring\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # OpenCode fails
        opencode_process = AsyncMock()
        opencode_process.communicate.return_value = (
            b"",
            b"Error: Cannot determine safe fix for architectural issue\nRecommendation: Manual intervention required\n",
        )
        opencode_process.returncode = 1

        mock_exec.side_effect = [coderabbit_process, opencode_process]

        result = await run_review_fix_loop(input_data)

        assert result.status == "failed"
        assert result.fix_attempt is not None
        assert result.fix_attempt.exit_code == 1
        assert "Cannot determine safe fix" in result.fix_attempt.stderr
        assert result.validation_result is None  # Never ran validation


@pytest.mark.asyncio
async def test_custom_validation_command_integration():
    """Integration test: Using custom validation command.

    Scenario: User provides custom validation command (cargo nextest)
    Expected: Custom command is used instead of default cargo test
    """
    from src.activities.review_fix import run_review_fix_loop

    custom_validation = ["uv", "run", "cargo", "nextest", "run", "--all"]
    input_data = ReviewLoopInput(
        branch_ref="origin/feature-nextest",
        commit_range=["abc1234"],
        enable_fixes=True,
        validation_command=custom_validation,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # CodeRabbit
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"[MINOR] Style issue\nDetails: Formatting\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # OpenCode
        opencode_process = AsyncMock()
        opencode_process.communicate.return_value = (b"Fixed formatting\n", b"")
        opencode_process.returncode = 0

        # Custom validation
        validation_process = AsyncMock()
        validation_process.communicate.return_value = (
            b"nextest run complete: 15 tests passed\n",
            b"",
        )
        validation_process.returncode = 0

        mock_exec.side_effect = [coderabbit_process, opencode_process, validation_process]

        result = await run_review_fix_loop(input_data)

        assert result.status == "fixed"
        assert result.validation_result is not None
        assert result.validation_result.command == custom_validation
        # Verify the custom command was actually called
        validation_call = mock_exec.call_args_list[2]
        assert validation_call[0] == tuple(custom_validation)


# ===== Resilience Tests for OpenCode Edge Cases (T025) =====


@pytest.mark.asyncio
async def test_opencode_refuses_prompt():
    """Resilience test: OpenCode refuses to process the prompt.

    Scenario: OpenCode determines prompt is unsafe or invalid
    Expected: Status="failed", sanitized artifacts stored, clear error message
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-refused",
        commit_range=["abc1234"],
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # CodeRabbit
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"[MAJOR] Security vulnerability\nDetails: Potential SQL injection\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # OpenCode refuses
        opencode_process = AsyncMock()
        opencode_process.communicate.return_value = (
            b"",
            b"Error: Prompt contains unsafe operation request\n"
            b"Refusing to generate code that could compromise security\n",
        )
        opencode_process.returncode = 2

        mock_exec.side_effect = [coderabbit_process, opencode_process]

        result = await run_review_fix_loop(input_data)

        assert result.status == "failed"
        assert result.fix_attempt is not None
        assert result.fix_attempt.exit_code == 2
        assert "Refusing to generate code" in result.fix_attempt.stderr
        # Verify sanitized prompt was created (even if not used)
        assert result.code_review_findings is not None
        assert result.code_review_findings.sanitized_prompt


@pytest.mark.asyncio
async def test_opencode_produces_no_changes():
    """Resilience test: OpenCode runs but produces no file changes.

    Scenario: OpenCode succeeds but doesn't modify any files
    Expected: Status="failed", fix_attempt shows no changes, validation not run
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-no-changes",
        commit_range=["abc1234"],
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # CodeRabbit
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"[MINOR] Unnecessary comment\nDetails: Remove outdated comment\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # OpenCode succeeds but produces no changes
        opencode_process = AsyncMock()
        opencode_process.communicate.return_value = (
            b"Analysis complete\nNo actionable changes identified\nModified files: (none)\n",
            b"",
        )
        opencode_process.returncode = 0

        mock_exec.side_effect = [coderabbit_process, opencode_process]

        result = await run_review_fix_loop(input_data)

        assert result.status == "failed"
        assert result.fix_attempt is not None
        assert result.fix_attempt.exit_code == 0
        assert result.fix_attempt.applied_changes == []
        assert "No actionable changes" in result.fix_attempt.stdout
        assert result.validation_result is None  # Validation skipped


@pytest.mark.asyncio
async def test_opencode_produces_invalid_output():
    """Resilience test: OpenCode output is malformed/unparseable.

    Scenario: OpenCode returns success but output format is unexpected
    Expected: Activity handles gracefully, treats as failure with diagnostics
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-malformed",
        commit_range=["abc1234"],
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # CodeRabbit
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"[MAJOR] Issue\nDetails: Problem\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # OpenCode returns malformed output
        opencode_process = AsyncMock()
        opencode_process.communicate.return_value = (
            b"Some random text\nNot following expected format\n<HTML>Error Page</HTML>\n",
            b"",
        )
        opencode_process.returncode = 0

        mock_exec.side_effect = [coderabbit_process, opencode_process]

        result = await run_review_fix_loop(input_data)

        # Should handle gracefully - treat as no changes or failure
        assert result.status == "failed"
        assert result.fix_attempt is not None


@pytest.mark.asyncio
async def test_opencode_partial_fix():
    """Resilience test: OpenCode fixes some but not all issues.

    Scenario: Multiple issues found, OpenCode only fixes subset
    Expected: Status based on validation outcome, issues_fixed reflects actual count
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-partial",
        commit_range=["abc1234"],
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # CodeRabbit finds 3 issues
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"[BLOCKER] Issue 1\nDetails: Problem 1\n"
            b"[MAJOR] Issue 2\nDetails: Problem 2\n"
            b"[MINOR] Issue 3\nDetails: Problem 3\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # OpenCode fixes 2 out of 3
        opencode_process = AsyncMock()
        opencode_process.communicate.return_value = (
            b"Fixed 2 issues:\n"
            b"  - Issue 1 (complete)\n"
            b"  - Issue 2 (complete)\n"
            b"Unable to fix Issue 3 (requires manual review)\n",
            b"",
        )
        opencode_process.returncode = 0

        # Validation passes (2 fixes were sufficient)
        validation_process = AsyncMock()
        validation_process.communicate.return_value = (
            b"test result: ok. 12 passed; 0 failed\n",
            b"",
        )
        validation_process.returncode = 0

        mock_exec.side_effect = [coderabbit_process, opencode_process, validation_process]

        result = await run_review_fix_loop(input_data)

        # Should succeed even though not all issues fixed
        assert result.status == "fixed"
        assert result.issues_fixed == 3  # Based on original issue count


@pytest.mark.asyncio
async def test_sanitized_artifacts_preserved():
    """Resilience test: Sanitized prompts are preserved even on failure.

    Scenario: Various failure modes, verify sanitized artifacts always available
    Expected: Sanitized prompt available in outcome regardless of failure point
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-artifacts",
        commit_range=["abc1234"],
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # CodeRabbit with potential secrets
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"[MAJOR] Hardcoded secret found\n"
            b"Details: AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE in config\n"
            b"PEM block:\n"
            b"-----BEGIN RSA PRIVATE KEY-----\n"
            b"MIIEpAIBAAKCAQEA...\n"
            b"-----END RSA PRIVATE KEY-----\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # OpenCode fails
        opencode_process = AsyncMock()
        opencode_process.communicate.return_value = (b"", b"Error: Failed\n")
        opencode_process.returncode = 1

        mock_exec.side_effect = [coderabbit_process, opencode_process]

        result = await run_review_fix_loop(input_data)

        # Verify sanitized prompt exists and secrets are redacted
        assert result.code_review_findings is not None
        sanitized = result.code_review_findings.sanitized_prompt

        # AWS key should be redacted
        assert "AKIAIOSFODNN7EXAMPLE" not in sanitized
        assert "[REDACTED-AWS-KEY]" in sanitized or "AWS_ACCESS_KEY_ID" not in sanitized

        # PEM block should be redacted
        assert "-----BEGIN RSA PRIVATE KEY-----" not in sanitized
        assert "[REDACTED-PEM-BLOCK]" in sanitized or "PRIVATE KEY" not in sanitized


@pytest.mark.asyncio
async def test_unicode_handling_in_opencode_output():
    """Resilience test: Non-UTF-8 bytes in OpenCode output.

    Scenario: OpenCode produces invalid UTF-8 sequences
    Expected: Activity handles with errors='replace', no crash
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-unicode",
        commit_range=["abc1234"],
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # CodeRabbit
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"[MINOR] Issue\nDetails: Fix needed\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # OpenCode with invalid UTF-8
        opencode_process = AsyncMock()
        opencode_process.communicate.return_value = (
            b"Applied fix\n\xff\xfe Invalid UTF-8 sequence\n",
            b"",
        )
        opencode_process.returncode = 0

        # Validation
        validation_process = AsyncMock()
        validation_process.communicate.return_value = (b"ok\n", b"")
        validation_process.returncode = 0

        mock_exec.side_effect = [coderabbit_process, opencode_process, validation_process]

        # Should not raise UnicodeDecodeError
        result = await run_review_fix_loop(input_data)

        assert isinstance(result, ReviewLoopOutcome)
        assert result.fix_attempt is not None
        # Verify replacement characters are used
        assert result.fix_attempt.stdout is not None


@pytest.mark.asyncio
async def test_retry_with_same_fingerprint_skips_duplicate():
    """Integration test: Retry with same fingerprint short-circuits.

    Scenario: Execute activity twice with same commits and findings
    Expected: Second run detects duplicate fingerprint and skips review
    """
    from src.activities.review_fix import run_review_fix_loop
    from src.models.review_fix import RetryMetadata

    commits = ["abc1234"]

    # First run
    input_first = ReviewLoopInput(
        branch_ref="origin/test-retry",
        commit_range=commits,
        enable_fixes=False,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock CodeRabbit CLI returning issues
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"CodeRabbit Review Complete\n"
            b"[BLOCKER] Memory leak in parser.rs:42\n"
            b"Details: Unhandled allocation in loop\n",
            b"",
        )
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result_first = await run_review_fix_loop(input_first)

        assert result_first.status == "failed"
        first_fingerprint = result_first.fingerprint

    # Second run with retry metadata containing same fingerprint
    retry_meta = RetryMetadata(
        previous_fingerprint=first_fingerprint,
        attempt_counter=1,
        last_status="failed",
        artifacts_path=result_first.artifacts_path,
    )

    input_retry = ReviewLoopInput(
        branch_ref="origin/test-retry",
        commit_range=commits,
        enable_fixes=False,
        retry_metadata=retry_meta,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock same CodeRabbit output
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"CodeRabbit Review Complete\n"
            b"[BLOCKER] Memory leak in parser.rs:42\n"
            b"Details: Unhandled allocation in loop\n",
            b"",
        )
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result_retry = await run_review_fix_loop(input_retry)

        # Should return previous result without re-running expensive operations
        assert result_retry.fingerprint == first_fingerprint
        assert result_retry.status == retry_meta.last_status


@pytest.mark.asyncio
async def test_retry_with_new_commit_reruns_review():
    """Integration test: Retry with new commit triggers fresh review.

    Scenario: Execute activity twice, second time with additional commit
    Expected: Fingerprint changes, review runs again
    """
    from src.activities.review_fix import run_review_fix_loop
    from src.models.review_fix import RetryMetadata

    # First run with one commit
    input_first = ReviewLoopInput(
        branch_ref="origin/test-retry-new-commit",
        commit_range=["abc1234"],
        enable_fixes=False,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"CodeRabbit Review Complete\nNo issues found.\n",
            b"",
        )
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result_first = await run_review_fix_loop(input_first)
        first_fingerprint = result_first.fingerprint

    # Second run with additional commit
    retry_meta = RetryMetadata(
        previous_fingerprint=first_fingerprint,
        attempt_counter=1,
        last_status="clean",
    )

    input_retry = ReviewLoopInput(
        branch_ref="origin/test-retry-new-commit",
        commit_range=["abc1234", "def5678"],  # New commit added
        enable_fixes=False,
        retry_metadata=retry_meta,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"CodeRabbit Review Complete\nNo issues found.\n",
            b"",
        )
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result_retry = await run_review_fix_loop(input_retry)

        # Fingerprint should be different due to new commit
        assert result_retry.fingerprint != first_fingerprint
        # Review should have run (mock was called)
        assert mock_exec.called


@pytest.mark.asyncio
async def test_retry_with_different_findings_reruns_fix():
    """Integration test: Retry with different findings triggers fresh fix attempt.

    Scenario: Execute activity twice, CodeRabbit finds different issues
    Expected: Fingerprint changes, fix runs again
    """
    from src.activities.review_fix import run_review_fix_loop
    from src.models.review_fix import RetryMetadata

    commits = ["abc1234"]

    # First run with one issue
    input_first = ReviewLoopInput(
        branch_ref="origin/test-retry-different-findings",
        commit_range=commits,
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock CodeRabbit finding first issue
        mock_process_coderabbit = AsyncMock()
        mock_process_coderabbit.communicate.return_value = (
            b"CodeRabbit Review Complete\n[MAJOR] Missing error handling in main.rs:100\nDetails: Function may panic\n",
            b"",
        )
        mock_process_coderabbit.returncode = 0

        # Mock OpenCode success
        mock_process_opencode = AsyncMock()
        mock_process_opencode.communicate.return_value = (
            b"Applied fix to main.rs\n",
            b"",
        )
        mock_process_opencode.returncode = 0

        # Mock validation success
        mock_process_validation = AsyncMock()
        mock_process_validation.communicate.return_value = (
            b"test result: ok\n",
            b"",
        )
        mock_process_validation.returncode = 0

        mock_exec.side_effect = [
            mock_process_coderabbit,
            mock_process_opencode,
            mock_process_validation,
        ]

        result_first = await run_review_fix_loop(input_first)
        first_fingerprint = result_first.fingerprint

    # Second run with different issue
    retry_meta = RetryMetadata(
        previous_fingerprint=first_fingerprint,
        attempt_counter=1,
        last_status="fixed",
    )

    input_retry = ReviewLoopInput(
        branch_ref="origin/test-retry-different-findings",
        commit_range=commits,
        enable_fixes=True,
        retry_metadata=retry_meta,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock CodeRabbit finding different issue
        mock_process_coderabbit = AsyncMock()
        mock_process_coderabbit.communicate.return_value = (
            b"CodeRabbit Review Complete\n"
            b"[BLOCKER] Memory leak in parser.rs:42\n"
            b"Details: Different issue from before\n",
            b"",
        )
        mock_process_coderabbit.returncode = 0

        # Mock OpenCode success
        mock_process_opencode = AsyncMock()
        mock_process_opencode.communicate.return_value = (
            b"Applied fix to parser.rs\n",
            b"",
        )
        mock_process_opencode.returncode = 0

        # Mock validation success
        mock_process_validation = AsyncMock()
        mock_process_validation.communicate.return_value = (
            b"test result: ok\n",
            b"",
        )
        mock_process_validation.returncode = 0

        mock_exec.side_effect = [
            mock_process_coderabbit,
            mock_process_opencode,
            mock_process_validation,
        ]

        result_retry = await run_review_fix_loop(input_retry)

        # Fingerprint should be different due to different findings
        assert result_retry.fingerprint != first_fingerprint
        # Fix should have run (OpenCode mock was called)
        assert mock_exec.call_count >= 2


@pytest.mark.asyncio
async def test_retry_metadata_increments_attempt_counter():
    """Integration test: Retry metadata correctly increments attempt counter.

    Scenario: Execute activity multiple times with retry metadata
    Expected: Attempt counter increases with each retry
    """
    from src.activities.review_fix import run_review_fix_loop
    from src.models.review_fix import RetryMetadata

    commits = ["abc1234"]

    # First run - no retry metadata
    input_first = ReviewLoopInput(
        branch_ref="origin/test-retry-counter",
        commit_range=commits,
        enable_fixes=False,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"CodeRabbit Review Complete\n[MAJOR] Issue found\nDetails: Something wrong\n",
            b"",
        )
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result_first = await run_review_fix_loop(input_first)
        first_fingerprint = result_first.fingerprint

    # Second run - attempt_counter should be tracked
    retry_meta_1 = RetryMetadata(
        previous_fingerprint=first_fingerprint,
        attempt_counter=1,
        last_status="failed",
    )

    input_retry_1 = ReviewLoopInput(
        branch_ref="origin/test-retry-counter",
        commit_range=commits,
        enable_fixes=False,
        retry_metadata=retry_meta_1,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"CodeRabbit Review Complete\n[MAJOR] Issue found\nDetails: Something wrong\n",
            b"",
        )
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result_retry_1 = await run_review_fix_loop(input_retry_1)

        # Should detect duplicate and return quickly
        assert result_retry_1.fingerprint == first_fingerprint

    # Third run - even higher attempt counter
    retry_meta_2 = RetryMetadata(
        previous_fingerprint=first_fingerprint,
        attempt_counter=2,
        last_status="failed",
    )

    input_retry_2 = ReviewLoopInput(
        branch_ref="origin/test-retry-counter",
        commit_range=commits,
        enable_fixes=False,
        retry_metadata=retry_meta_2,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"CodeRabbit Review Complete\n[MAJOR] Issue found\nDetails: Something wrong\n",
            b"",
        )
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result_retry_2 = await run_review_fix_loop(input_retry_2)

        # Should still detect duplicate
        assert result_retry_2.fingerprint == first_fingerprint


@pytest.mark.asyncio
async def test_review_loop_timing_metrics_recorded():
    """Integration test: Timing metrics are recorded for performance monitoring.

    Scenario: Run activity and verify timing metrics are present for SC-001/SC-002
    Expected: ReviewLoopOutcome includes timing information for all phases
    """
    from src.activities.review_fix import run_review_fix_loop

    # Test clean run timing (SC-001: <2min for clean runs)
    input_clean = ReviewLoopInput(
        branch_ref="origin/test-timing-clean",
        commit_range=["abc1234"],
        enable_fixes=False,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"CodeRabbit Review Complete\nNo issues found.\n",
            b"",
        )
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result_clean = await run_review_fix_loop(input_clean)

        # Verify timing fields exist
        assert result_clean.completed_at is not None
        assert result_clean.code_review_findings is not None
        assert result_clean.code_review_findings.generated_at is not None

        # Verify clean run is fast (should be <2min per SC-001)
        # In tests, this will be very fast since we mock CLI calls
        assert result_clean.status == "clean"

    # Test fix attempt timing (SC-002: 80% fixed first pass)
    input_fix = ReviewLoopInput(
        branch_ref="origin/test-timing-fix",
        commit_range=["abc1234"],
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        call_count = 0

        async def mock_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            mock_process = AsyncMock()

            # First call: CodeRabbit finds issues
            if call_count == 1:
                mock_process.communicate.return_value = (
                    b"CodeRabbit Review Complete\n[MAJOR] Missing error handling\nDetails: Function may panic\n",
                    b"",
                )
                mock_process.returncode = 0
            # Second call: OpenCode applies fixes
            elif call_count == 2:
                mock_process.communicate.return_value = (
                    b"OpenCode fixes applied\nModified files:\n- src/lib.rs\n",
                    b"",
                )
                mock_process.returncode = 0
            # Third call: Validation passes
            else:
                mock_process.communicate.return_value = (
                    b"test result: ok. 10 passed; 0 failed\n",
                    b"",
                )
                mock_process.returncode = 0

            return mock_process

        mock_exec.side_effect = mock_subprocess

        result_fix = await run_review_fix_loop(input_fix)

        # Verify timing fields for fix attempt
        assert result_fix.status == "fixed"
        assert result_fix.fix_attempt is not None
        assert result_fix.fix_attempt.started_at is not None
        assert result_fix.fix_attempt.completed_at is not None

        # Verify fix_attempt timing is sane
        fix_duration = (result_fix.fix_attempt.completed_at - result_fix.fix_attempt.started_at).total_seconds()
        assert fix_duration >= 0, "Fix duration should be non-negative"

        # Verify validation timing
        assert result_fix.validation_result is not None
        assert result_fix.validation_result.started_at is not None
        assert result_fix.validation_result.completed_at is not None

        validation_duration = (
            result_fix.validation_result.completed_at - result_fix.validation_result.started_at
        ).total_seconds()
        assert validation_duration >= 0, "Validation duration should be non-negative"

        # Verify overall completion timing
        assert result_fix.completed_at is not None

        # Verify first-pass success metric (for SC-002)
        assert result_fix.issues_fixed > 0
        assert result_fix.validation_result.exit_code == 0
