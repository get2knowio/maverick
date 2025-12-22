"""Tests for CodeRabbitRunner."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.runners.coderabbit import CodeRabbitRunner
from maverick.runners.models import CodeRabbitResult, CommandResult


class TestCodeRabbitRunner:
    @pytest.mark.asyncio
    async def test_run_review_success(self):
        """Test successful code review with findings."""
        mock_output = json.dumps(
            {
                "findings": [
                    {
                        "file": "src/test.py",
                        "line": 10,
                        "severity": "warning",
                        "message": "Consider adding docstring",
                        "suggestion": "Add a docstring to explain the function",
                        "category": "documentation",
                    },
                    {
                        "file": "src/test.py",
                        "line": 25,
                        "severity": "error",
                        "message": "Potential security issue",
                        "category": "security",
                    },
                ]
            }
        )

        mock_result = CommandResult(
            returncode=0,
            stdout=mock_output,
            stderr="",
            duration_ms=5000,
            timed_out=False,
        )

        with patch("shutil.which", return_value="/usr/bin/coderabbit"):
            runner = CodeRabbitRunner()
            runner._command_runner = AsyncMock()
            runner._command_runner.run = AsyncMock(return_value=mock_result)

            result = await runner.run_review()

            assert isinstance(result, CodeRabbitResult)
            assert result.has_findings is True
            assert len(result.findings) == 2
            assert result.error_count == 1
            assert result.warning_count == 1
            assert "2 issues" in result.summary

    @pytest.mark.asyncio
    async def test_coderabbit_not_installed(self):
        """Test graceful degradation when CodeRabbit not installed."""
        with patch("shutil.which", return_value=None):
            runner = CodeRabbitRunner()
            result = await runner.run_review()

            assert isinstance(result, CodeRabbitResult)
            assert result.has_findings is False
            assert len(result.warnings) == 1
            assert "not installed" in result.warnings[0]

    @pytest.mark.asyncio
    async def test_review_specific_files(self):
        """Test reviewing specific files."""
        mock_result = CommandResult(
            returncode=0,
            stdout=json.dumps({"findings": []}),
            stderr="",
            duration_ms=1000,
            timed_out=False,
        )

        with patch("shutil.which", return_value="/usr/bin/coderabbit"):
            runner = CodeRabbitRunner()
            runner._command_runner = AsyncMock()
            runner._command_runner.run = AsyncMock(return_value=mock_result)

            files = [Path("src/file1.py"), Path("src/file2.py")]
            await runner.run_review(files=files)

            # Verify files were passed to command
            call_args = runner._command_runner.run.call_args[0][0]
            assert "src/file1.py" in call_args
            assert "src/file2.py" in call_args

    @pytest.mark.asyncio
    async def test_malformed_output_handling(self):
        """Test graceful handling of malformed JSON output."""
        mock_result = CommandResult(
            returncode=0,
            stdout="This is not valid JSON { broken",
            stderr="",
            duration_ms=1000,
            timed_out=False,
        )

        with patch("shutil.which", return_value="/usr/bin/coderabbit"):
            runner = CodeRabbitRunner()
            runner._command_runner = AsyncMock()
            runner._command_runner.run = AsyncMock(return_value=mock_result)

            result = await runner.run_review()

            # Should handle gracefully without crashing
            assert isinstance(result, CodeRabbitResult)
            assert result.has_findings is False
            assert result.raw_output == "This is not valid JSON { broken"

    @pytest.mark.asyncio
    async def test_is_available_returns_false_when_not_installed(self):
        """Test is_available returns False when CLI not installed."""
        with patch("shutil.which", return_value=None):
            runner = CodeRabbitRunner()
            assert await runner.is_available() is False

    @pytest.mark.asyncio
    async def test_is_available_returns_true_when_installed(self):
        """Test is_available returns True when CLI is installed."""
        with patch("shutil.which", return_value="/usr/bin/coderabbit"):
            runner = CodeRabbitRunner()
            assert await runner.is_available() is True
