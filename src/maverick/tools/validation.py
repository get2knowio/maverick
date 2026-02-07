"""Validation MCP tools for Maverick agents.

This module provides MCP tools for running validation commands
(format, lint, typecheck, test) and parsing their output into structured errors.
Tools are async functions decorated with @tool that return MCP-formatted responses.

Usage:
    from maverick.tools.validation import create_validation_tools_server

    server = create_validation_tools_server()
    agent = MaverickAgent(mcp_servers={"validation-tools": server})
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from maverick.config import ValidationConfig
from maverick.exceptions import ValidationToolsError
from maverick.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

#: Default timeout for validation operations in seconds
DEFAULT_TIMEOUT: float = 300.0

#: MCP Server configuration
SERVER_NAME: str = "validation-tools"
SERVER_VERSION: str = "1.0.0"

#: Valid validation types
VALIDATION_TYPES: set[str] = {"format", "lint", "build", "typecheck", "test", "sync"}

#: Ruff output pattern: path:line:col: code message
RUFF_PATTERN: re.Pattern[str] = re.compile(
    r"^(.+):(\d+):(\d+): (\w+) (.+)$", re.MULTILINE
)

#: Mypy output pattern: path:line: severity: message [code]
MYPY_PATTERN: re.Pattern[str] = re.compile(
    r"^(.+):(\d+): (error|warning|note): (.+?)(?: \[(.+)\])?$", re.MULTILINE
)

#: Default max errors to return (prevent overwhelming output)
MAX_ERRORS: int = 50

# =============================================================================
# Helper Functions
# =============================================================================


def _success_response(data: dict[str, Any]) -> dict[str, Any]:
    """Create MCP success response.

    Args:
        data: Response data to JSON-serialize.

    Returns:
        MCP-formatted success response.
    """
    return {"content": [{"type": "text", "text": json.dumps(data)}]}


def _error_response(
    message: str,
    error_code: str,
    retry_after_seconds: int | None = None,
) -> dict[str, Any]:
    """Create MCP error response.

    Args:
        message: Human-readable error message.
        error_code: Machine-readable error code.
        retry_after_seconds: Seconds to wait (for rate limits).

    Returns:
        MCP-formatted error response.
    """
    error_data: dict[str, Any] = {
        "isError": True,
        "message": message,
        "error_code": error_code,
    }
    if retry_after_seconds is not None:
        error_data["retry_after_seconds"] = retry_after_seconds
    return {"content": [{"type": "text", "text": json.dumps(error_data)}]}


async def _run_command_with_timeout(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[str, str, int, bool]:
    """Run a command with timeout using CommandRunner.

    Uses CommandRunner for proper async subprocess execution per CLAUDE.md.

    Args:
        cmd: Command and arguments to execute.
        cwd: Working directory for command execution.
        timeout: Maximum execution time in seconds.

    Returns:
        Tuple of (stdout, stderr, return_code, timed_out).

    Raises:
        ValidationToolsError: If command execution fails unexpectedly.
    """
    from maverick.runners.command import CommandRunner

    try:
        logger.debug("Running command: %s", " ".join(cmd))

        runner = CommandRunner(cwd=cwd, timeout=timeout)
        result = await runner.run(cmd, timeout=timeout)

        timed_out = result.timed_out
        if timed_out:
            logger.warning("Command timed out after %ss: %s", timeout, " ".join(cmd))
        else:
            logger.debug("Command completed with return code %s", result.returncode)

        return result.stdout, result.stderr, result.returncode, timed_out

    except Exception as e:
        logger.error("Command execution error: %s", e)
        raise ValidationToolsError(f"Failed to execute command: {' '.join(cmd)}") from e


# =============================================================================
# Factory Function
# =============================================================================


def create_validation_tools_server(
    config: ValidationConfig | None = None,
    project_root: Path | None = None,
) -> McpSdkServerConfig:
    """Create MCP server with all validation tools registered (T049).

    This factory function creates an MCP server instance with all validation
    tools registered. Configuration is optional - if not provided, uses defaults.

    Args:
        config: Validation configuration. Defaults to ValidationConfig().
        project_root: Project root directory for running validation commands.
            Defaults to current working directory.

    Returns:
        Configured MCP server instance.

    Example:
        ```python
        from maverick.tools.validation import create_validation_tools_server
        from maverick.config import ValidationConfig

        config = ValidationConfig(timeout_seconds=120)
        server = create_validation_tools_server(config)
        agent = MaverickAgent(
            mcp_servers={"validation-tools": server},
            allowed_tools=["mcp__validation-tools__run_validation"],
        )
        ```
    """
    # Initialize config without global state
    _config = config if config is not None else ValidationConfig()

    # Set project root on config if provided
    if project_root is not None:
        # Create new config with project_root set
        _config = ValidationConfig(
            format_cmd=_config.format_cmd,
            lint_cmd=_config.lint_cmd,
            typecheck_cmd=_config.typecheck_cmd,
            test_cmd=_config.test_cmd,
            timeout_seconds=_config.timeout_seconds,
            max_errors=_config.max_errors,
            project_root=project_root,
        )

    logger.info("Creating validation tools MCP server (version %s)", SERVER_VERSION)

    # =============================================================================
    # MCP Tool Functions (using closure to capture _config)
    # =============================================================================

    @tool(
        "run_validation",
        (
            "Run project validation commands. "
            "Pass types: a list of one or more of "
            '"format", "lint", "typecheck", "test", "sync". '
            'Use "sync" to install/update dependencies (replaces uv sync, '
            "npm install, etc.). You do NOT have Bash — use this tool for "
            "all validation and dependency operations."
        ),
        {"types": list},
    )
    async def run_validation(args: dict[str, Any]) -> dict[str, Any]:
        """Run validation commands based on ValidationConfig.

        Args:
            args: Tool arguments with 'types' list (format/lint/typecheck/test).

        Returns:
            MCP response with validation results:
            {
                "success": bool,
                "results": [
                    {
                        "type": str,
                        "success": bool,
                        "output": str,
                        "duration_ms": int,
                        "status": str  # "success", "failed", or "timeout"
                    }
                ]
            }

        Raises:
            Never raises - always returns MCP response format with success or error.
        """
        try:
            types_to_run: list[str] = args.get("types", [])

            # Validate types
            invalid_types = set(types_to_run) - VALIDATION_TYPES
            if invalid_types:
                logger.error("Invalid validation types: %s", invalid_types)
                return _error_response(
                    f"Invalid validation types: {invalid_types}. "
                    f"Valid types: {VALIDATION_TYPES}",
                    "INVALID_VALIDATION_TYPE",
                )

            if not types_to_run:
                logger.warning("No validation types specified")
                return _success_response({"success": True, "results": []})

            logger.info("Running validation types: %s", types_to_run)

            # Map validation types to commands
            type_to_cmd: dict[str, list[str] | None] = {
                "format": _config.format_cmd,
                "lint": _config.lint_cmd,
                "build": _config.typecheck_cmd,  # build is an alias for typecheck
                "typecheck": _config.typecheck_cmd,
                "test": _config.test_cmd,
                "sync": _config.sync_cmd,
            }

            results: list[dict[str, Any]] = []
            overall_success = True

            for validation_type in types_to_run:
                cmd: list[str] | None = type_to_cmd.get(validation_type)

                if cmd is None:
                    logger.warning("No command configured for %s", validation_type)
                    results.append(
                        {
                            "type": validation_type,
                            "success": False,
                            "output": f"No command configured for {validation_type}",
                            "duration_ms": 0,
                            "status": "failed",
                        }
                    )
                    overall_success = False
                    continue

                # Run command with timeout tracking
                start_time = time.monotonic()
                (
                    stdout,
                    stderr,
                    return_code,
                    timed_out,
                ) = await _run_command_with_timeout(
                    cmd,
                    cwd=_config.project_root,
                    timeout=float(_config.timeout_seconds),
                )
                duration_ms = int((time.monotonic() - start_time) * 1000)

                # Combine stdout and stderr
                output = stdout
                if stderr:
                    output += f"\n{stderr}"

                # Determine status
                if timed_out:
                    status = "timeout"
                    success = False
                    logger.warning(
                        "Validation '%s' timed out after %sms",
                        validation_type,
                        duration_ms,
                    )
                elif return_code == 0:
                    status = "success"
                    success = True
                    logger.info(
                        "Validation '%s' succeeded in %sms",
                        validation_type,
                        duration_ms,
                    )
                else:
                    status = "failed"
                    success = False
                    logger.warning(
                        "Validation '%s' failed with code %s in %sms",
                        validation_type,
                        return_code,
                        duration_ms,
                    )

                results.append(
                    {
                        "type": validation_type,
                        "success": success,
                        "output": output.strip(),
                        "duration_ms": duration_ms,
                        "status": status,
                    }
                )

                if not success:
                    overall_success = False

            logger.info("Validation complete: overall_success=%s", overall_success)
            return _success_response({"success": overall_success, "results": results})

        except Exception as e:
            logger.error("Validation execution error: %s", e)
            return _error_response(str(e), "VALIDATION_EXECUTION_ERROR")

    @tool(
        "parse_validation_output",
        "Parse validation command output into structured errors",
        {"output": str, "type": str},
    )
    async def parse_validation_output(args: dict[str, Any]) -> dict[str, Any]:
        """Parse lint or typecheck output into structured error list.

        Args:
            args: Tool arguments with 'output' (str) and
                'type' (str: 'lint' or 'typecheck').

        Returns:
            MCP response with parsed errors:
            {
                "errors": [
                    {
                        "file": str,
                        "line": int,
                        "column": int | None,
                        "code": str | None,
                        "message": str,
                        "severity": str | None
                    }
                ],
                "total_count": int,
                "truncated": bool
            }

        Raises:
            Never raises - always returns MCP response format with success or error.
        """
        try:
            output: str = args.get("output", "")
            parse_type: str = args.get("type", "")

            if parse_type not in {"lint", "typecheck"}:
                logger.error("Invalid parse type: %s", parse_type)
                return _error_response(
                    f"Invalid parse type: {parse_type}. "
                    f"Valid types: 'lint', 'typecheck'",
                    "INVALID_PARSE_TYPE",
                )

            logger.info("Parsing %s output (%s chars)", parse_type, len(output))

            errors: list[dict[str, Any]] = []

            # Map parse_type to the appropriate pattern
            if parse_type == "lint":
                # Parse ruff output: path:line:col: code message
                for match in RUFF_PATTERN.finditer(output):
                    file_path, line_str, col_str, code, message = match.groups()
                    errors.append(
                        {
                            "file": file_path,
                            "line": int(line_str),
                            "column": int(col_str),
                            "code": code,
                            "message": message.strip(),
                            "severity": None,
                        }
                    )

            elif parse_type == "typecheck":
                # Parse mypy output: path:line: severity: message [code]
                for match in MYPY_PATTERN.finditer(output):
                    file_path, line_str, severity, message, code = match.groups()
                    errors.append(
                        {
                            "file": file_path,
                            "line": int(line_str),
                            "column": None,
                            "code": code,
                            "message": message.strip(),
                            "severity": severity,
                        }
                    )

            total_count = len(errors)
            truncated = total_count > MAX_ERRORS

            if truncated:
                logger.warning("Truncating %s errors to %s", total_count, MAX_ERRORS)
                errors = errors[:MAX_ERRORS]

            logger.info(
                "Parsed %s errors (total: %s, truncated: %s)",
                len(errors),
                total_count,
                truncated,
            )

            return _success_response(
                {
                    "errors": errors,
                    "total_count": total_count,
                    "truncated": truncated,
                }
            )

        except Exception as e:
            logger.error("Parse validation output error: %s", e)
            return _error_response(str(e), "PARSE_ERROR")

    # Create and return MCP server with all tools
    server = create_sdk_mcp_server(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        tools=[
            run_validation,
            parse_validation_output,
        ],
    )

    # Store tool references on server for testing
    # Type ignore because we're adding to the dict for test purposes
    server["_tools"] = {  # type: ignore[typeddict-unknown-key]
        "run_validation": run_validation,
        "parse_validation_output": parse_validation_output,
    }

    return server
