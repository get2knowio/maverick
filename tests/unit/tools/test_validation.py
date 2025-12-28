"""Unit tests for validation MCP tools.

Tests the validation MCP tools for running validation commands and parsing output:
- T073: Create test fixtures for mocked subprocess
- T074: test_run_validation_success - verify successful validation run
- T075: test_run_validation_failure - verify failure handling with output
- T076: test_run_validation_timeout - verify timeout handling kills process
- T077: test_parse_validation_output_ruff - verify ruff output parsing
- T078: test_parse_validation_output_mypy - verify mypy output parsing
- T079: test_parse_validation_output_truncation - verify error truncation at MAX_ERRORS
- T080: test_create_validation_tools_server - verify factory creates server
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from maverick.config import ValidationConfig
from maverick.exceptions import ValidationToolsError
from maverick.tools.validation import (
    DEFAULT_TIMEOUT,
    MAX_ERRORS,
    MYPY_PATTERN,
    RUFF_PATTERN,
    SERVER_NAME,
    SERVER_VERSION,
    VALIDATION_TYPES,
    _error_response,
    _run_command_with_timeout,
    _success_response,
    create_validation_tools_server,
)

# Patch path for CommandRunner's create_subprocess_exec
SUBPROCESS_EXEC_PATCH = "maverick.runners.command.asyncio.create_subprocess_exec"

# =============================================================================
# Test Fixtures (T073)
# =============================================================================


def _get_tools_from_server(server: dict[str, Any]) -> tuple[Any, Any]:
    """Extract run_validation and parse_validation_output tools from server.

    Args:
        server: MCP server dict returned by create_validation_tools_server.

    Returns:
        Tuple of (run_validation, parse_validation_output) tools.
    """
    # Access the tool references stored on the server for testing
    tools = server["_tools"]
    return tools["run_validation"], tools["parse_validation_output"]


@pytest.fixture
def mock_process() -> Mock:
    """Create a mock subprocess for testing.

    Returns:
        Mock subprocess with communicate() and kill() methods.
    """
    process = Mock()
    process.returncode = 0
    process.communicate = AsyncMock(return_value=(b"", b""))
    process.kill = Mock()
    return process


@pytest.fixture
def mock_subprocess_exec(mock_process: Mock) -> AsyncMock:
    """Create a mock for asyncio.create_subprocess_exec.

    Args:
        mock_process: Mock subprocess to return.

    Returns:
        AsyncMock that returns the mock process.
    """
    return AsyncMock(return_value=mock_process)


@pytest.fixture
def sample_ruff_output() -> str:
    """Sample ruff output for testing parsing."""
    return """src/foo.py:10:5: E501 Line too long (100 > 88 characters)
src/foo.py:15:1: F401 'os' imported but unused
src/bar.py:23:12: W291 Trailing whitespace
src/baz.py:5:8: E302 Expected 2 blank lines, found 1"""


@pytest.fixture
def sample_mypy_output() -> str:
    """Sample mypy output for testing parsing."""
    return """src/foo.py:10: error: Incompatible types [type-arg]
src/foo.py:15: warning: Unused import 'os'
src/bar.py:23: error: Name 'undefined_var' is not defined [name-defined]
src/baz.py:5: note: This is informational"""


@pytest.fixture
def validation_config(tmp_path: Path) -> ValidationConfig:
    """Create a ValidationConfig for testing.

    Args:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        ValidationConfig instance.
    """
    return ValidationConfig(
        format_cmd=["ruff", "format", "."],
        lint_cmd=["ruff", "check", "--fix", "."],
        typecheck_cmd=["mypy", "."],
        test_cmd=["pytest", "-x", "--tb=short"],
        timeout_seconds=300,
        max_errors=50,
        project_root=tmp_path,
    )


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_success_response_format(self) -> None:
        """Test _success_response creates proper MCP format."""
        data = {"success": True, "results": []}
        response = _success_response(data)

        assert "content" in response
        assert len(response["content"]) == 1
        assert response["content"][0]["type"] == "text"

        text_data = json.loads(response["content"][0]["text"])
        assert text_data == data

    def test_error_response_format(self) -> None:
        """Test _error_response creates proper MCP error format."""
        response = _error_response("Test error", "TEST_ERROR")

        assert "content" in response
        assert len(response["content"]) == 1
        assert response["content"][0]["type"] == "text"

        error_data = json.loads(response["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["message"] == "Test error"
        assert error_data["error_code"] == "TEST_ERROR"
        assert "retry_after_seconds" not in error_data

    def test_error_response_with_retry_after(self) -> None:
        """Test _error_response includes retry_after when provided."""
        response = _error_response("Rate limited", "RATE_LIMIT", retry_after_seconds=60)

        error_data = json.loads(response["content"][0]["text"])
        assert error_data["retry_after_seconds"] == 60


# =============================================================================
# Command Execution Tests
# =============================================================================


class TestRunCommandWithTimeout:
    """Tests for _run_command_with_timeout helper."""

    @pytest.mark.asyncio
    async def test_successful_command_execution(
        self, mock_subprocess_exec: AsyncMock, mock_process: Mock
    ) -> None:
        """Test successful command execution returns output correctly."""
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"stdout output", b"stderr output")
        )

        with patch(SUBPROCESS_EXEC_PATCH, mock_subprocess_exec):
            stdout, stderr, return_code, timed_out = await _run_command_with_timeout(
                ["echo", "test"]
            )

        assert stdout == "stdout output"
        assert stderr == "stderr output"
        assert return_code == 0
        assert timed_out is False

    @pytest.mark.asyncio
    async def test_command_execution_with_cwd(
        self, mock_subprocess_exec: AsyncMock, tmp_path: Path
    ) -> None:
        """Test command execution with working directory."""
        with patch(SUBPROCESS_EXEC_PATCH, mock_subprocess_exec):
            await _run_command_with_timeout(["ls"], cwd=tmp_path)

        mock_subprocess_exec.assert_called_once()
        call_kwargs = mock_subprocess_exec.call_args[1]
        assert call_kwargs["cwd"] == tmp_path

    @pytest.mark.asyncio
    async def test_command_timeout_terminates_process(
        self, mock_subprocess_exec: AsyncMock, mock_process: Mock
    ) -> None:
        """Test command timeout terminates process gracefully (T076)."""
        # Simulate timeout by making communicate() raise TimeoutError
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_process.terminate = Mock()
        mock_process.kill = Mock()
        # wait() returns successfully after terminate (graceful shutdown)
        mock_process.wait = AsyncMock(return_value=None)

        # Mock stdout/stderr streams for reading after timeout
        mock_stdout = AsyncMock()
        mock_stdout.read = AsyncMock(return_value=b"partial output")
        mock_stderr = AsyncMock()
        mock_stderr.read = AsyncMock(return_value=b"timeout error")
        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr

        with patch(SUBPROCESS_EXEC_PATCH, mock_subprocess_exec):
            stdout, stderr, return_code, timed_out = await _run_command_with_timeout(
                ["sleep", "1000"], timeout=0.1
            )

        # CommandRunner calls terminate (graceful shutdown succeeded)
        mock_process.terminate.assert_called_once()
        # kill should NOT be called if terminate succeeded
        mock_process.kill.assert_not_called()
        assert return_code == -1
        assert timed_out is True
        assert stdout == "partial output"
        assert stderr == "timeout error"

    @pytest.mark.asyncio
    async def test_command_execution_error(
        self, mock_subprocess_exec: AsyncMock
    ) -> None:
        """Test command execution error raises ValidationToolsError."""
        mock_subprocess_exec.side_effect = OSError("Command not found")

        with patch(SUBPROCESS_EXEC_PATCH, mock_subprocess_exec):
            with pytest.raises(ValidationToolsError) as exc_info:
                await _run_command_with_timeout(["nonexistent_command"])

        assert "Failed to execute command" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_command_nonzero_exit_code(
        self, mock_subprocess_exec: AsyncMock, mock_process: Mock
    ) -> None:
        """Test command with non-zero exit code."""
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"error message"))

        with patch(SUBPROCESS_EXEC_PATCH, mock_subprocess_exec):
            stdout, stderr, return_code, timed_out = await _run_command_with_timeout(
                ["exit", "1"]
            )

        assert return_code == 1
        assert timed_out is False


# =============================================================================
# run_validation Tool Tests
# =============================================================================


class TestRunValidation:
    """Tests for run_validation MCP tool."""

    @pytest.mark.asyncio
    async def test_run_validation_success(
        self,
        mock_subprocess_exec: AsyncMock,
        mock_process: Mock,
        validation_config: ValidationConfig,
    ) -> None:
        """Test successful validation run (T074)."""
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"All checks passed", b""))

        # Create server with config - tools are created via closure
        server = create_validation_tools_server(config=validation_config)
        run_validation, _ = _get_tools_from_server(server)

        with patch(SUBPROCESS_EXEC_PATCH, mock_subprocess_exec):
            response = await run_validation.handler({"types": ["format", "lint"]})

        # Parse response
        response_data = json.loads(response["content"][0]["text"])

        assert response_data["success"] is True
        assert len(response_data["results"]) == 2

        for result in response_data["results"]:
            assert result["success"] is True
            assert result["status"] == "success"
            assert result["output"] == "All checks passed"
            assert result["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_run_validation_failure(
        self,
        mock_subprocess_exec: AsyncMock,
        mock_process: Mock,
        validation_config: ValidationConfig,
    ) -> None:
        """Test validation failure with output (T075)."""
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"E501 Line too long", b""))

        server = create_validation_tools_server(config=validation_config)
        run_validation, _ = _get_tools_from_server(server)

        with patch(SUBPROCESS_EXEC_PATCH, mock_subprocess_exec):
            response = await run_validation.handler({"types": ["lint"]})

        response_data = json.loads(response["content"][0]["text"])

        assert response_data["success"] is False
        assert len(response_data["results"]) == 1
        assert response_data["results"][0]["success"] is False
        assert response_data["results"][0]["status"] == "failed"
        assert "E501 Line too long" in response_data["results"][0]["output"]

    @pytest.mark.asyncio
    async def test_run_validation_timeout(
        self,
        mock_subprocess_exec: AsyncMock,
        mock_process: Mock,
        validation_config: ValidationConfig,
    ) -> None:
        """Test validation timeout handling (T076)."""
        # communicate raises TimeoutError (simulating command timeout)
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_process.terminate = Mock()
        mock_process.kill = Mock()
        # wait() returns successfully after terminate (graceful shutdown)
        mock_process.wait = AsyncMock(return_value=None)

        # Mock stdout/stderr streams for reading after timeout
        mock_stdout = AsyncMock()
        mock_stdout.read = AsyncMock(return_value=b"")
        mock_stderr = AsyncMock()
        mock_stderr.read = AsyncMock(return_value=b"Process killed due to timeout")
        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr

        server = create_validation_tools_server(config=validation_config)
        run_validation, _ = _get_tools_from_server(server)

        with patch(SUBPROCESS_EXEC_PATCH, mock_subprocess_exec):
            response = await run_validation.handler({"types": ["test"]})

        response_data = json.loads(response["content"][0]["text"])

        assert response_data["success"] is False
        assert response_data["results"][0]["status"] == "timeout"
        assert response_data["results"][0]["success"] is False

    @pytest.mark.asyncio
    async def test_run_validation_invalid_type(
        self, validation_config: ValidationConfig
    ) -> None:
        """Test validation with invalid type returns error."""
        server = create_validation_tools_server(config=validation_config)
        run_validation, _ = _get_tools_from_server(server)

        response = await run_validation.handler({"types": ["invalid_type"]})

        response_data = json.loads(response["content"][0]["text"])

        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_VALIDATION_TYPE"
        assert "invalid_type" in response_data["message"]

    @pytest.mark.asyncio
    async def test_run_validation_empty_types(
        self, validation_config: ValidationConfig
    ) -> None:
        """Test validation with empty types list returns success."""
        server = create_validation_tools_server(config=validation_config)
        run_validation, _ = _get_tools_from_server(server)

        response = await run_validation.handler({"types": []})

        response_data = json.loads(response["content"][0]["text"])

        assert response_data["success"] is True
        assert response_data["results"] == []

    @pytest.mark.asyncio
    async def test_run_validation_all_types(
        self,
        mock_subprocess_exec: AsyncMock,
        mock_process: Mock,
        validation_config: ValidationConfig,
    ) -> None:
        """Test validation with all valid types."""
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"success", b""))

        server = create_validation_tools_server(config=validation_config)
        run_validation, _ = _get_tools_from_server(server)

        with patch(SUBPROCESS_EXEC_PATCH, mock_subprocess_exec):
            response = await run_validation.handler(
                {"types": ["format", "lint", "typecheck", "test"]}
            )

        response_data = json.loads(response["content"][0]["text"])

        assert len(response_data["results"]) == 4
        assert all(r["success"] for r in response_data["results"])

    @pytest.mark.asyncio
    async def test_run_validation_no_command_configured(
        self, validation_config: ValidationConfig
    ) -> None:
        """Test validation when no command is configured for type."""
        # Create a config, then manually set format_cmd to None to test the None check
        server = create_validation_tools_server(config=validation_config)

        # Manually patch the _config inside the closure to have None for format_cmd
        # This tests the defensive None check in the tool code
        # We'll do this by creating a new server with modified closure state
        # Actually, we can't easily modify closure state, so let's test this differently
        # by testing a validation type that maps to None in type_to_cmd

        # Instead, let's test "build" which is an alias for typecheck
        # If typecheck_cmd is None, build will also map to None

        # Create a custom config where we'll simulate None command
        class MockConfig:
            format_cmd = None
            lint_cmd = ["ruff", "check", "."]
            typecheck_cmd = ["mypy", "."]
            test_cmd = ["pytest"]
            project_root = validation_config.project_root
            timeout_seconds = 300

        server = create_validation_tools_server(config=MockConfig())
        run_validation, _ = _get_tools_from_server(server)

        response = await run_validation.handler({"types": ["format"]})

        response_data = json.loads(response["content"][0]["text"])

        assert response_data["success"] is False
        assert response_data["results"][0]["status"] == "failed"
        assert "No command configured" in response_data["results"][0]["output"]

    @pytest.mark.asyncio
    async def test_run_validation_combines_stdout_stderr(
        self,
        mock_subprocess_exec: AsyncMock,
        mock_process: Mock,
        validation_config: ValidationConfig,
    ) -> None:
        """Test that validation combines stdout and stderr in output."""
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"stdout message", b"stderr message")
        )

        server = create_validation_tools_server(config=validation_config)
        run_validation, _ = _get_tools_from_server(server)

        with patch(SUBPROCESS_EXEC_PATCH, mock_subprocess_exec):
            response = await run_validation.handler({"types": ["lint"]})

        response_data = json.loads(response["content"][0]["text"])
        output = response_data["results"][0]["output"]

        assert "stdout message" in output
        assert "stderr message" in output

    @pytest.mark.asyncio
    async def test_run_validation_mixed_results(
        self,
        mock_subprocess_exec: AsyncMock,
        mock_process: Mock,
        validation_config: ValidationConfig,
    ) -> None:
        """Test validation with mixed success/failure results."""
        # First call succeeds, second fails
        call_count = 0

        async def mock_communicate() -> tuple[bytes, bytes]:
            nonlocal call_count
            call_count += 1
            return (b"output", b"")

        def get_returncode() -> int:
            return 0 if call_count == 1 else 1

        mock_process.communicate = mock_communicate
        type(mock_process).returncode = property(lambda self: get_returncode())

        server = create_validation_tools_server(config=validation_config)
        run_validation, _ = _get_tools_from_server(server)

        with patch(SUBPROCESS_EXEC_PATCH, mock_subprocess_exec):
            response = await run_validation.handler({"types": ["format", "lint"]})

        response_data = json.loads(response["content"][0]["text"])

        assert response_data["success"] is False  # Overall fails if any fails
        assert response_data["results"][0]["success"] is True
        assert response_data["results"][1]["success"] is False


# =============================================================================
# parse_validation_output Tool Tests
# =============================================================================


class TestParseValidationOutput:
    """Tests for parse_validation_output MCP tool."""

    @pytest.mark.asyncio
    async def test_parse_validation_output_ruff(self, sample_ruff_output: str) -> None:
        """Test parsing ruff output (T077)."""
        server = create_validation_tools_server()
        _, parse_validation_output = _get_tools_from_server(server)

        response = await parse_validation_output.handler(
            {"output": sample_ruff_output, "type": "lint"}
        )

        response_data = json.loads(response["content"][0]["text"])

        assert len(response_data["errors"]) == 4
        assert response_data["total_count"] == 4
        assert response_data["truncated"] is False

        # Check first error
        error = response_data["errors"][0]
        assert error["file"] == "src/foo.py"
        assert error["line"] == 10
        assert error["column"] == 5
        assert error["code"] == "E501"
        assert "Line too long" in error["message"]
        assert error["severity"] is None

    @pytest.mark.asyncio
    async def test_parse_validation_output_mypy(self, sample_mypy_output: str) -> None:
        """Test parsing mypy output (T078)."""
        server = create_validation_tools_server()
        _, parse_validation_output = _get_tools_from_server(server)

        response = await parse_validation_output.handler(
            {"output": sample_mypy_output, "type": "typecheck"}
        )

        response_data = json.loads(response["content"][0]["text"])

        assert len(response_data["errors"]) == 4
        assert response_data["total_count"] == 4
        assert response_data["truncated"] is False

        # Check first error
        error = response_data["errors"][0]
        assert error["file"] == "src/foo.py"
        assert error["line"] == 10
        assert error["column"] is None
        assert error["code"] == "type-arg"
        assert "Incompatible types" in error["message"]
        assert error["severity"] == "error"

        # Check warning
        warning = response_data["errors"][1]
        assert warning["severity"] == "warning"

        # Check note
        note = response_data["errors"][3]
        assert note["severity"] == "note"

    @pytest.mark.asyncio
    async def test_parse_validation_output_truncation(self) -> None:
        """Test error truncation at MAX_ERRORS (T079)."""
        server = create_validation_tools_server()
        _, parse_validation_output = _get_tools_from_server(server)

        # Create output with more than MAX_ERRORS errors
        errors = []
        for i in range(MAX_ERRORS + 10):
            errors.append(f"src/file{i}.py:{i}:1: E501 Error {i}")
        output = "\n".join(errors)

        response = await parse_validation_output.handler(
            {"output": output, "type": "lint"}
        )

        response_data = json.loads(response["content"][0]["text"])

        assert len(response_data["errors"]) == MAX_ERRORS
        assert response_data["total_count"] == MAX_ERRORS + 10
        assert response_data["truncated"] is True

    @pytest.mark.asyncio
    async def test_parse_validation_output_invalid_type(self) -> None:
        """Test parsing with invalid type returns error."""
        server = create_validation_tools_server()
        _, parse_validation_output = _get_tools_from_server(server)

        response = await parse_validation_output.handler(
            {"output": "some output", "type": "invalid"}
        )

        response_data = json.loads(response["content"][0]["text"])

        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_PARSE_TYPE"
        assert "invalid" in response_data["message"]

    @pytest.mark.asyncio
    async def test_parse_validation_output_empty(self) -> None:
        """Test parsing empty output."""
        server = create_validation_tools_server()
        _, parse_validation_output = _get_tools_from_server(server)

        response = await parse_validation_output.handler({"output": "", "type": "lint"})

        response_data = json.loads(response["content"][0]["text"])

        assert response_data["errors"] == []
        assert response_data["total_count"] == 0
        assert response_data["truncated"] is False

    @pytest.mark.asyncio
    async def test_parse_validation_output_no_matches(self) -> None:
        """Test parsing output with no pattern matches."""
        server = create_validation_tools_server()
        _, parse_validation_output = _get_tools_from_server(server)

        response = await parse_validation_output.handler(
            {"output": "Some text that doesn't match patterns", "type": "lint"}
        )

        response_data = json.loads(response["content"][0]["text"])

        assert response_data["errors"] == []
        assert response_data["total_count"] == 0

    @pytest.mark.asyncio
    async def test_parse_ruff_various_codes(self) -> None:
        """Test parsing ruff output with various error codes."""
        server = create_validation_tools_server()
        _, parse_validation_output = _get_tools_from_server(server)

        output = """src/a.py:1:1: E501 Line too long
src/b.py:2:2: F401 Unused import
src/c.py:3:3: W291 Trailing whitespace
src/d.py:4:4: N802 Function name should be lowercase"""

        response = await parse_validation_output.handler(
            {"output": output, "type": "lint"}
        )
        response_data = json.loads(response["content"][0]["text"])

        codes = [e["code"] for e in response_data["errors"]]
        assert codes == ["E501", "F401", "W291", "N802"]

    @pytest.mark.asyncio
    async def test_parse_mypy_without_code(self) -> None:
        """Test parsing mypy output without error code."""
        server = create_validation_tools_server()
        _, parse_validation_output = _get_tools_from_server(server)

        output = "src/foo.py:10: error: Some error without code"

        response = await parse_validation_output.handler(
            {"output": output, "type": "typecheck"}
        )
        response_data = json.loads(response["content"][0]["text"])

        assert len(response_data["errors"]) == 1
        assert response_data["errors"][0]["code"] is None

    @pytest.mark.asyncio
    async def test_parse_mypy_with_code(self) -> None:
        """Test parsing mypy output with error code."""
        server = create_validation_tools_server()
        _, parse_validation_output = _get_tools_from_server(server)

        output = "src/foo.py:10: error: Type error [type-arg]"

        response = await parse_validation_output.handler(
            {"output": output, "type": "typecheck"}
        )
        response_data = json.loads(response["content"][0]["text"])

        assert len(response_data["errors"]) == 1
        assert response_data["errors"][0]["code"] == "type-arg"


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateValidationToolsServer:
    """Tests for create_validation_tools_server factory (T080)."""

    def test_create_validation_tools_server_default_config(self) -> None:
        """Test creating server with default configuration."""
        server = create_validation_tools_server()

        assert server is not None
        # Verify it's a FastMCP server dict with expected attributes
        assert isinstance(server, dict)
        assert "name" in server
        assert server["name"] == SERVER_NAME

    def test_create_validation_tools_server_custom_config(
        self, validation_config: ValidationConfig
    ) -> None:
        """Test creating server with custom configuration."""
        server = create_validation_tools_server(config=validation_config)

        assert server is not None
        assert isinstance(server, dict)
        assert server["name"] == SERVER_NAME

    def test_create_validation_tools_server_custom_project_root(
        self, tmp_path: Path
    ) -> None:
        """Test creating server with custom project root."""
        server = create_validation_tools_server(project_root=tmp_path)

        assert server is not None

    def test_create_validation_tools_server_with_both_params(
        self, validation_config: ValidationConfig, tmp_path: Path
    ) -> None:
        """Test creating server with both config and project_root."""
        custom_root = tmp_path / "custom"
        custom_root.mkdir()

        server = create_validation_tools_server(
            config=validation_config,
            project_root=custom_root,
        )

        assert server is not None

    def test_server_has_correct_tools(self) -> None:
        """Test that created server has all expected tools."""
        server = create_validation_tools_server()

        # The server should have the tools registered
        assert isinstance(server, dict)
        assert server["name"] == SERVER_NAME
        assert "instance" in server


# =============================================================================
# Pattern Matching Tests
# =============================================================================


class TestPatternMatching:
    """Tests for regex pattern matching."""

    def test_ruff_pattern_matches_valid_output(self) -> None:
        """Test RUFF_PATTERN matches valid ruff output."""
        line = "src/foo.py:10:5: E501 Line too long"
        match = RUFF_PATTERN.search(line)

        assert match is not None
        assert match.group(1) == "src/foo.py"
        assert match.group(2) == "10"
        assert match.group(3) == "5"
        assert match.group(4) == "E501"
        assert match.group(5) == "Line too long"

    def test_ruff_pattern_rejects_invalid_output(self) -> None:
        """Test RUFF_PATTERN rejects invalid format."""
        invalid_lines = [
            "not a valid line",
            "src/foo.py:10: missing column",
            "src/foo.py:10:5:",  # Missing code and message
            "src/foo.py:abc:5: E501 Invalid line number",  # Non-numeric line
            "src/foo.py:10:def: E501 Invalid column",  # Non-numeric column
        ]

        for line in invalid_lines:
            match = RUFF_PATTERN.search(line)
            assert match is None, f"Pattern should not match: {line}"

    def test_mypy_pattern_matches_valid_output(self) -> None:
        """Test MYPY_PATTERN matches valid mypy output."""
        line = "src/foo.py:10: error: Type mismatch [type-arg]"
        match = MYPY_PATTERN.search(line)

        assert match is not None
        assert match.group(1) == "src/foo.py"
        assert match.group(2) == "10"
        assert match.group(3) == "error"
        assert match.group(4) == "Type mismatch"
        assert match.group(5) == "type-arg"

    def test_mypy_pattern_matches_without_code(self) -> None:
        """Test MYPY_PATTERN matches output without error code."""
        line = "src/foo.py:10: error: Type mismatch"
        match = MYPY_PATTERN.search(line)

        assert match is not None
        assert match.group(5) is None  # No error code

    def test_mypy_pattern_matches_all_severities(self) -> None:
        """Test MYPY_PATTERN matches error, warning, and note."""
        for severity in ["error", "warning", "note"]:
            line = f"src/foo.py:10: {severity}: Message"
            match = MYPY_PATTERN.search(line)

            assert match is not None
            assert match.group(3) == severity

    def test_mypy_pattern_rejects_invalid_output(self) -> None:
        """Test MYPY_PATTERN rejects invalid format."""
        invalid_lines = [
            "not a valid line",
            "src/foo.py: missing line number",
            "src/foo.py:10: invalid_severity: Message",
        ]

        for line in invalid_lines:
            match = MYPY_PATTERN.search(line)
            assert match is None, f"Pattern should not match: {line}"


# =============================================================================
# Constants Tests
# =============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_default_timeout_value(self) -> None:
        """Test DEFAULT_TIMEOUT is set correctly."""
        assert DEFAULT_TIMEOUT == 300.0

    def test_max_errors_value(self) -> None:
        """Test MAX_ERRORS is set correctly."""
        assert MAX_ERRORS == 50

    def test_validation_types_contains_all_types(self) -> None:
        """Test VALIDATION_TYPES contains expected types."""
        assert {"format", "lint", "build", "typecheck", "test"} == VALIDATION_TYPES

    def test_server_name_value(self) -> None:
        """Test SERVER_NAME is set correctly."""
        assert SERVER_NAME == "validation-tools"

    def test_server_version_value(self) -> None:
        """Test SERVER_VERSION is set correctly."""
        assert SERVER_VERSION == "1.0.0"


# =============================================================================
# Integration-Style Tests
# =============================================================================


class TestValidationIntegration:
    """Integration-style tests combining multiple components."""

    @pytest.mark.asyncio
    async def test_full_validation_flow_with_parsing(
        self,
        mock_subprocess_exec: AsyncMock,
        mock_process: Mock,
        validation_config: ValidationConfig,
        sample_ruff_output: str,
    ) -> None:
        """Test full flow: run validation, then parse output."""
        # Step 1: Run validation that returns ruff output
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(
            return_value=(sample_ruff_output.encode(), b"")
        )

        server = create_validation_tools_server(config=validation_config)
        run_validation, parse_validation_output = _get_tools_from_server(server)

        with patch(SUBPROCESS_EXEC_PATCH, mock_subprocess_exec):
            run_response = await run_validation.handler({"types": ["lint"]})

        run_data = json.loads(run_response["content"][0]["text"])
        assert run_data["success"] is False
        output = run_data["results"][0]["output"]

        # Step 2: Parse the output
        parse_response = await parse_validation_output.handler(
            {"output": output, "type": "lint"}
        )

        parse_data = json.loads(parse_response["content"][0]["text"])
        assert len(parse_data["errors"]) == 4
        assert parse_data["errors"][0]["code"] == "E501"

    @pytest.mark.asyncio
    async def test_validation_with_timeout_in_config(
        self, mock_subprocess_exec: AsyncMock, mock_process: Mock, tmp_path: Path
    ) -> None:
        """Test validation respects timeout from config."""
        config = ValidationConfig(
            timeout_seconds=30,  # Minimum allowed timeout
            project_root=tmp_path,
        )

        # communicate raises TimeoutError (simulating command timeout)
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_process.terminate = Mock()
        mock_process.kill = Mock()
        # wait() returns successfully after terminate (graceful shutdown)
        mock_process.wait = AsyncMock(return_value=None)

        # Mock stdout/stderr streams for reading after timeout
        mock_stdout = AsyncMock()
        mock_stdout.read = AsyncMock(return_value=b"")
        mock_stderr = AsyncMock()
        mock_stderr.read = AsyncMock(return_value=b"timeout")
        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr

        server = create_validation_tools_server(config=config)
        run_validation, _ = _get_tools_from_server(server)

        with patch(SUBPROCESS_EXEC_PATCH, mock_subprocess_exec):
            response = await run_validation.handler({"types": ["test"]})

        response_data = json.loads(response["content"][0]["text"])
        assert response_data["results"][0]["status"] == "timeout"
