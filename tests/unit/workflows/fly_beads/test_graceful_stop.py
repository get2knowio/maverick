"""Tests for the fly graceful-stop flag."""

from __future__ import annotations

import pytest

from maverick.workflows.fly_beads.graceful_stop import (
    is_graceful_stop_requested,
    request_graceful_stop,
    reset_graceful_stop,
)


@pytest.fixture(autouse=True)
def _reset_flag() -> None:
    """Process-level flag must not leak across tests."""
    reset_graceful_stop()
    yield
    reset_graceful_stop()


def test_default_state_is_not_requested() -> None:
    assert is_graceful_stop_requested() is False


def test_request_sets_the_flag() -> None:
    request_graceful_stop()
    assert is_graceful_stop_requested() is True


def test_request_is_idempotent() -> None:
    request_graceful_stop()
    request_graceful_stop()
    request_graceful_stop()
    assert is_graceful_stop_requested() is True


def test_reset_clears_the_flag() -> None:
    request_graceful_stop()
    reset_graceful_stop()
    assert is_graceful_stop_requested() is False
