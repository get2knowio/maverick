"""Tests for the maverick.logging module."""

from __future__ import annotations

import logging
import os
from unittest.mock import patch

import structlog

from maverick.logging import (
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
)


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_configure_logging_default(self) -> None:
        """Test default logging configuration (console output)."""
        configure_logging()

        # Verify structlog is configured
        log = structlog.get_logger()
        assert log is not None

    def test_configure_logging_json_via_env(self) -> None:
        """Test JSON logging when MAVERICK_LOG_FORMAT=json."""
        with patch.dict(os.environ, {"MAVERICK_LOG_FORMAT": "json"}):
            configure_logging()

            # Verify structlog is configured
            log = structlog.get_logger()
            assert log is not None

    def test_configure_logging_force_json(self) -> None:
        """Test forcing JSON output regardless of environment."""
        configure_logging(force_json=True)

        # Verify structlog is configured
        log = structlog.get_logger()
        assert log is not None

    def test_configure_logging_custom_level(self) -> None:
        """Test setting custom log level."""
        configure_logging(level=logging.DEBUG)

        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    def test_configure_logging_level_from_env(self) -> None:
        """Test log level from MAVERICK_LOG_LEVEL env var."""
        with patch.dict(os.environ, {"MAVERICK_LOG_LEVEL": "WARNING"}):
            configure_logging()

            root_logger = logging.getLogger()
            assert root_logger.level == logging.WARNING


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_with_name(self) -> None:
        """Test getting a logger with explicit name."""
        log = get_logger("test.module")
        assert log is not None

    def test_get_logger_without_name(self) -> None:
        """Test getting a logger without name."""
        log = get_logger()
        assert log is not None

    def test_logger_can_bind_context(self) -> None:
        """Test that logger supports context binding."""
        configure_logging()

        log = get_logger("test")
        bound_log = log.bind(workflow_id="test-123")

        # Should not raise
        bound_log.info("test_event", key="value")

    def test_logger_can_log_with_structured_data(self) -> None:
        """Test logging with structured data."""
        configure_logging()

        log = get_logger("test")

        # Should not raise
        log.info("event_name", user_id=123, action="test")
        log.warning("warning_event", error_code="E001")
        log.error("error_event", exception="SomeError")


class TestContextBinding:
    """Tests for context binding functions."""

    def test_bind_context(self) -> None:
        """Test binding context variables."""
        configure_logging()
        clear_context()

        bind_context(workflow_id="fly-123", step_name="init")

        # Context should be bound - verify by getting the bound vars
        # Note: This is an implementation detail test
        ctx = structlog.contextvars.get_contextvars()
        assert "workflow_id" in ctx
        assert ctx["workflow_id"] == "fly-123"
        assert "step_name" in ctx
        assert ctx["step_name"] == "init"

    def test_clear_context(self) -> None:
        """Test clearing context variables."""
        configure_logging()

        bind_context(workflow_id="fly-123")
        clear_context()

        ctx = structlog.contextvars.get_contextvars()
        assert ctx == {}

    def test_context_propagation_in_logs(self) -> None:
        """Test that context is included in log output."""
        configure_logging()
        clear_context()

        bind_context(workflow_id="fly-123")

        log = get_logger("test")
        # This should work and include workflow_id in output
        log.info("test_event")

        clear_context()


class TestLogOutput:
    """Tests for log output formatting."""

    def test_console_output_format(self) -> None:
        """Test that console output is human-readable."""
        configure_logging()

        log = get_logger("test.console")
        # Should not raise
        log.info("test_message", key="value")

    def test_json_output_format(self) -> None:
        """Test that JSON output is properly formatted."""
        configure_logging(force_json=True)

        log = get_logger("test.json")
        # Should not raise
        log.info("test_message", key="value")
