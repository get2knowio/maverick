"""Tests for ValidationRunner."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from maverick.runners.models import CommandResult, ValidationStage
from maverick.runners.validation import ValidationRunner


@pytest.fixture
def mock_command_result_success():
    return CommandResult(
        returncode=0, stdout="OK", stderr="", duration_ms=100, timed_out=False
    )


@pytest.fixture
def mock_command_result_failure():
    return CommandResult(
        returncode=1, stdout="", stderr="Error", duration_ms=100, timed_out=False
    )


class TestValidationRunner:
    @pytest.mark.asyncio
    async def test_all_stages_pass(self, mock_command_result_success):
        """Test all stages passing."""
        stages = [
            ValidationStage(name="format", command=("ruff", "format", "--check")),
            ValidationStage(name="lint", command=("ruff", "check")),
        ]

        runner = ValidationRunner(stages=stages)

        # Mock the CommandRunner instance
        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=mock_command_result_success)
        runner._command_runner = mock_runner

        output = await runner.run()

        assert output.success is True
        assert output.stages_run == 2
        assert output.stages_passed == 2

    @pytest.mark.asyncio
    async def test_stage_failure_stops_execution(
        self, mock_command_result_success, mock_command_result_failure
    ):
        """Test that failure stops subsequent stages."""
        stages = [
            ValidationStage(name="stage1", command=("cmd1",)),
            ValidationStage(name="stage2", command=("cmd2",)),
            ValidationStage(name="stage3", command=("cmd3",)),
        ]

        runner = ValidationRunner(stages=stages)

        # Mock the CommandRunner instance
        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(
            side_effect=[
                mock_command_result_success,
                mock_command_result_failure,  # Stage 2 fails
            ]
        )
        runner._command_runner = mock_runner

        output = await runner.run()

        assert output.success is False
        assert output.stages_run == 2  # Stage 3 not executed
        assert output.stages_passed == 1

    @pytest.mark.asyncio
    async def test_fixable_stage_retry(
        self, mock_command_result_success, mock_command_result_failure
    ):
        """Test fixable stage runs fix command and retries."""
        stages = [
            ValidationStage(
                name="format",
                command=("ruff", "format", "--check"),
                fixable=True,
                fix_command=("ruff", "format"),
            ),
        ]

        runner = ValidationRunner(stages=stages)

        # Mock the CommandRunner instance
        mock_runner = MagicMock()
        # First check fails, fix runs, second check passes
        mock_runner.run = AsyncMock(
            side_effect=[
                mock_command_result_failure,  # Initial check fails
                mock_command_result_success,  # Fix command
                mock_command_result_success,  # Re-check passes
            ]
        )
        runner._command_runner = mock_runner

        output = await runner.run()

        assert output.success is True
        assert output.stages[0].fix_attempts == 1

    @pytest.mark.asyncio
    async def test_parser_integration(self):
        """Test that output parsers populate StageResult.errors correctly."""
        # Create a stage that produces Python traceback output
        stage = ValidationStage(
            name="test",
            command=("python", "-c", "raise Exception('test')"),
            fixable=False,
        )

        # Mock CommandRunner to return traceback output
        # Format the traceback so the error pattern can match it
        traceback_output = """Traceback (most recent call last):
  File "test.py", line 42, in test_function
    raise ValueError("test error")
ValueError: test error
"""
        mock_result = CommandResult(
            returncode=1,
            stdout=traceback_output,
            stderr="",
            duration_ms=50,
            timed_out=False,
        )

        runner = ValidationRunner(stages=(stage,))

        # Mock the CommandRunner instance
        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(return_value=mock_result)
        runner._command_runner = mock_runner

        # Run and verify errors are populated
        result = await runner.run()

        # Verify stage failed
        assert result.success is False
        assert result.stages_run == 1
        assert result.stages_passed == 0

        # Verify errors were parsed
        stage_result = result.stages[0]
        assert len(stage_result.errors) > 0

        # Verify ParsedError details
        parsed_error = stage_result.errors[0]
        assert parsed_error.file == "test.py"
        assert parsed_error.line == 42
        assert parsed_error.message == "ValueError: test error"
        assert parsed_error.severity == "error"
