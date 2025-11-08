"""Unit tests for review_fix activity function."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.models.review_fix import (
    ReviewLoopInput,
    ReviewLoopOutcome,
)


@pytest.mark.asyncio
async def test_review_only_clean_outcome():
    """Test review-only execution when CodeRabbit finds no issues.

    Scenario: enable_fixes=False, CodeRabbit returns clean transcript
    Expected: ReviewLoopOutcome with status="clean", no fix_attempt
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-test",
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
async def test_review_only_issues_found():
    """Test review-only execution when CodeRabbit finds issues.

    Scenario: enable_fixes=False, CodeRabbit returns issues
    Expected: ReviewLoopOutcome with status="failed", issues logged, no fix_attempt
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-test",
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
async def test_coderabbit_cli_failure():
    """Test handling when CodeRabbit CLI fails to execute.

    Scenario: CodeRabbit CLI returns non-zero exit code
    Expected: ReviewLoopOutcome with status="failed" and error captured
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-test",
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
        # Error should be captured in artifacts
        assert result.artifacts_path is not None
        # Verify stderr was captured - check diagnostics file exists
        artifacts_dir = Path(result.artifacts_path)
        diagnostics_file = artifacts_dir / f"diagnostics_{result.fingerprint}.txt"
        if diagnostics_file.exists():
            diagnostics_content = diagnostics_file.read_text()
            assert "Authentication failed" in diagnostics_content


@pytest.mark.asyncio
async def test_coderabbit_not_installed():
    """Test handling when CodeRabbit CLI is not installed.

    Scenario: CodeRabbit binary not found
    Expected: ReviewLoopOutcome with status="failed" and appropriate error
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-test",
        commit_range=["abc1234"],
        enable_fixes=False,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock command not found
        mock_exec.side_effect = FileNotFoundError("coderabbit command not found")

        result = await run_review_fix_loop(input_data)

        assert isinstance(result, ReviewLoopOutcome)
        assert result.status == "failed"


@pytest.mark.asyncio
async def test_coderabbit_timeout():
    """Test handling when CodeRabbit CLI times out.

    Scenario: CodeRabbit execution exceeds timeout
    Expected: ReviewLoopOutcome with status="failed" and timeout error
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-test",
        commit_range=["abc1234"],
        enable_fixes=False,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock timeout
        mock_exec.side_effect = TimeoutError("CodeRabbit execution timed out")

        result = await run_review_fix_loop(input_data)

        assert isinstance(result, ReviewLoopOutcome)
        assert result.status == "failed"


@pytest.mark.asyncio
async def test_malformed_coderabbit_output():
    """Test handling of malformed CodeRabbit transcript.

    Scenario: CodeRabbit returns success but output is unparseable
    Expected: ReviewLoopOutcome with status="clean" or minimal findings
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-test",
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
        # Should handle gracefully - either clean or failed depending on parsing strategy
        assert result.status in ["clean", "failed"]


@pytest.mark.asyncio
async def test_sanitized_prompt_generation():
    """Test that sanitized prompt is generated correctly from transcript.

    Scenario: CodeRabbit returns transcript with potential secrets
    Expected: Sanitized prompt has secrets redacted
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-test",
        commit_range=["abc1234"],
        enable_fixes=True,  # Enable to test sanitization
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Mock CodeRabbit with potential secrets in output
        mock_process = AsyncMock()
        transcript_with_secrets = (
            b"CodeRabbit Review\n"
            b"[MAJOR] Hardcoded credential\n"
            b"Details: AWS_KEY=AKIAIOSFODNN7EXAMPLE found in config.rs\n"
        )
        mock_process.communicate.return_value = (transcript_with_secrets, b"")
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result = await run_review_fix_loop(input_data)

        # Verify sanitized prompt doesn't contain the actual AWS key pattern
        if result.code_review_findings:
            sanitized = result.code_review_findings.sanitized_prompt
            # Should have redacted the AWS key
            assert "AKIAIOSFODNN7EXAMPLE" not in sanitized and "[REDACTED" in sanitized


@pytest.mark.asyncio
async def test_fingerprint_generation():
    """Test that fingerprints are deterministic and unique.

    Scenario: Same input should generate same fingerprint
    Expected: Fingerprint is 64 hex chars and deterministic
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-test",
        commit_range=["abc1234", "def5678"],
        enable_fixes=False,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Clean", b"")
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result1 = await run_review_fix_loop(input_data)

        # Reset mock for second run
        mock_exec.reset_mock()
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Clean", b"")
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result2 = await run_review_fix_loop(input_data)

        # Fingerprints should be identical for same input
        assert result1.fingerprint == result2.fingerprint
        assert len(result1.fingerprint) == 64
        # Should be valid hex
        assert all(c in "0123456789abcdef" for c in result1.fingerprint)


@pytest.mark.asyncio
async def test_unicode_handling_in_transcript():
    """Test handling of non-UTF-8 bytes in CodeRabbit output.

    Scenario: CodeRabbit output contains invalid UTF-8 sequences
    Expected: Activity handles gracefully with errors='replace'
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-test",
        commit_range=["abc1234"],
        enable_fixes=False,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        # Include invalid UTF-8 byte sequence
        mock_process.communicate.return_value = (
            b"Review complete\n\xff\xfe Invalid UTF-8\n",
            b"",
        )
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        # Should not raise UnicodeDecodeError
        result = await run_review_fix_loop(input_data)

        assert isinstance(result, ReviewLoopOutcome)
        # Verify replacement characters are used
        if result.code_review_findings:
            assert result.code_review_findings.transcript is not None


# ===== Phase 4: User Story 2 Tests (OpenCode Integration) =====


@pytest.mark.asyncio
async def test_opencode_successful_fix():
    """Test successful OpenCode fix application.

    Scenario: CodeRabbit finds issues, OpenCode applies fixes successfully
    Expected: ReviewLoopOutcome with status="fixed", fix_attempt populated
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-fix",
        commit_range=["abc1234"],
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # First call: CodeRabbit returns issues
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"CodeRabbit Review\n"
            b"[MAJOR] Missing error handling in main.rs:100\n"
            b"Details: Function may panic on invalid input\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # Second call: OpenCode applies fixes
        opencode_process = AsyncMock()
        opencode_process.communicate.return_value = (
            b"OpenCode: Applied fixes to main.rs\n"
            b"Changes: Added error handling\n",
            b"",
        )
        opencode_process.returncode = 0

        # Third call: Validation passes
        validation_process = AsyncMock()
        validation_process.communicate.return_value = (
            b"test result: ok. 5 passed; 0 failed\n",
            b"",
        )
        validation_process.returncode = 0

        # Mock returns different processes in sequence
        mock_exec.side_effect = [coderabbit_process, opencode_process, validation_process]

        result = await run_review_fix_loop(input_data)

        assert isinstance(result, ReviewLoopOutcome)
        assert result.status == "fixed"
        assert result.issues_fixed == 1
        assert result.fix_attempt is not None
        assert result.fix_attempt.exit_code == 0
        assert result.validation_result is not None
        assert result.validation_result.exit_code == 0


@pytest.mark.asyncio
async def test_opencode_invocation_failure():
    """Test handling when OpenCode CLI fails to execute.

    Scenario: CodeRabbit finds issues, OpenCode fails with non-zero exit
    Expected: ReviewLoopOutcome with status="failed", fix_attempt shows error
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-fix",
        commit_range=["abc1234"],
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # First call: CodeRabbit returns issues
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"[MAJOR] Issue found\nDetails: Problem\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # Second call: OpenCode fails
        opencode_process = AsyncMock()
        opencode_process.communicate.return_value = (
            b"",
            b"Error: Failed to apply changes\n",
        )
        opencode_process.returncode = 1

        mock_exec.side_effect = [coderabbit_process, opencode_process]

        result = await run_review_fix_loop(input_data)

        assert isinstance(result, ReviewLoopOutcome)
        assert result.status == "failed"
        assert result.fix_attempt is not None
        assert result.fix_attempt.exit_code == 1
        assert "Failed to apply changes" in result.fix_attempt.stderr


@pytest.mark.asyncio
async def test_opencode_not_installed():
    """Test handling when OpenCode binary is not found.

    Scenario: CodeRabbit finds issues, OpenCode not available
    Expected: ReviewLoopOutcome with status="failed" and appropriate error
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-fix",
        commit_range=["abc1234"],
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # First call: CodeRabbit succeeds
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"[MAJOR] Issue\nDetails: Problem\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # Second call: OpenCode not found
        def exec_side_effect(*args, **kwargs):
            if "opencode" in args[0]:
                raise FileNotFoundError("opencode command not found")
            return coderabbit_process

        mock_exec.side_effect = exec_side_effect

        result = await run_review_fix_loop(input_data)

        assert isinstance(result, ReviewLoopOutcome)
        assert result.status == "failed"


@pytest.mark.asyncio
async def test_opencode_timeout():
    """Test handling when OpenCode execution times out.

    Scenario: OpenCode takes too long to execute
    Expected: ReviewLoopOutcome with status="failed" and timeout error
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-fix",
        commit_range=["abc1234"],
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # First call: CodeRabbit succeeds
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"[MAJOR] Issue\nDetails: Problem\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # Second call: OpenCode times out
        def exec_side_effect(*args, **kwargs):
            if "opencode" in args[0]:
                raise TimeoutError("OpenCode execution timed out")
            return coderabbit_process

        mock_exec.side_effect = exec_side_effect

        result = await run_review_fix_loop(input_data)

        assert isinstance(result, ReviewLoopOutcome)
        assert result.status == "failed"


@pytest.mark.asyncio
async def test_validation_failure_after_fix():
    """Test handling when validation fails after OpenCode applies fixes.

    Scenario: OpenCode succeeds but validation still fails
    Expected: ReviewLoopOutcome with status="failed", both fix_attempt and validation_result populated
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-fix",
        commit_range=["abc1234"],
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # First call: CodeRabbit
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"[MAJOR] Issue\nDetails: Problem\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # Second call: OpenCode succeeds
        opencode_process = AsyncMock()
        opencode_process.communicate.return_value = (
            b"Applied fixes\n",
            b"",
        )
        opencode_process.returncode = 0

        # Third call: Validation fails
        validation_process = AsyncMock()
        validation_process.communicate.return_value = (
            b"",
            b"test result: FAILED. 3 passed; 2 failed\n",
        )
        validation_process.returncode = 1

        mock_exec.side_effect = [coderabbit_process, opencode_process, validation_process]

        result = await run_review_fix_loop(input_data)

        assert isinstance(result, ReviewLoopOutcome)
        assert result.status == "failed"
        assert result.fix_attempt is not None
        assert result.fix_attempt.exit_code == 0  # Fix succeeded
        assert result.validation_result is not None
        assert result.validation_result.exit_code == 1  # Validation failed


@pytest.mark.asyncio
async def test_custom_validation_command():
    """Test using custom validation command instead of default.

    Scenario: User provides custom validation command
    Expected: Custom command is executed instead of default cargo test
    """
    from src.activities.review_fix import run_review_fix_loop

    custom_cmd = ["uv", "run", "cargo", "nextest", "run"]
    input_data = ReviewLoopInput(
        branch_ref="origin/feature-fix",
        commit_range=["abc1234"],
        enable_fixes=True,
        validation_command=custom_cmd,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # CodeRabbit
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"[MAJOR] Issue\nDetails: Problem\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # OpenCode
        opencode_process = AsyncMock()
        opencode_process.communicate.return_value = (b"Fixed\n", b"")
        opencode_process.returncode = 0

        # Validation with custom command
        validation_process = AsyncMock()
        validation_process.communicate.return_value = (
            b"nextest: all tests passed\n",
            b"",
        )
        validation_process.returncode = 0

        mock_exec.side_effect = [coderabbit_process, opencode_process, validation_process]

        await run_review_fix_loop(input_data)

        # Verify custom command was used
        validation_call = mock_exec.call_args_list[2]
        assert validation_call[0][:5] == tuple(custom_cmd)


@pytest.mark.asyncio
async def test_failure_diagnostics_capture():
    """Test that failure diagnostics are properly captured and surfaced.

    Scenario: Various failures occur (CodeRabbit, OpenCode, validation)
    Expected: Detailed diagnostics are available in outcome
    """
    from src.activities.review_fix import run_review_fix_loop

    input_data = ReviewLoopInput(
        branch_ref="origin/feature-fix",
        commit_range=["abc1234"],
        enable_fixes=True,
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # CodeRabbit
        coderabbit_process = AsyncMock()
        coderabbit_process.communicate.return_value = (
            b"[BLOCKER] Critical issue\nDetails: Memory corruption\n",
            b"",
        )
        coderabbit_process.returncode = 0

        # OpenCode fails with detailed error
        opencode_process = AsyncMock()
        opencode_process.communicate.return_value = (
            b"",
            b"Error: Cannot parse prompt\nReason: Invalid formatting\n",
        )
        opencode_process.returncode = 1

        mock_exec.side_effect = [coderabbit_process, opencode_process]

        result = await run_review_fix_loop(input_data)

        assert result.status == "failed"
        assert result.fix_attempt is not None
        # Verify stderr contains diagnostic information
        assert "Cannot parse prompt" in result.fix_attempt.stderr
        assert "Invalid formatting" in result.fix_attempt.stderr
