"""Unit tests for CLI runtime bootstrap helpers."""

from src.cli import _bootstrap


def test_parse_host_and_port_defaults() -> None:
    """Ensure default host/port are returned when address is empty."""
    host, port = _bootstrap.parse_host_and_port(None)
    assert host == "localhost"
    assert port == _bootstrap.DEFAULT_TEMPORAL_PORT


def test_parse_host_and_port_with_custom_port() -> None:
    """Host:port parsing should respect explicit ports."""
    host, port = _bootstrap.parse_host_and_port("127.0.0.1:4242")
    assert host == "127.0.0.1"
    assert port == 4242


def test_parse_host_and_port_with_invalid_port() -> None:
    """Invalid ports fall back to the default Temporal port."""
    host, port = _bootstrap.parse_host_and_port("localhost:not-a-port")
    assert host == "localhost"
    assert port == _bootstrap.DEFAULT_TEMPORAL_PORT


def test_is_local_host_detection() -> None:
    """Local host detection should recognize loopback names."""
    assert _bootstrap._is_local_host("localhost")  # type: ignore[attr-defined]
    assert _bootstrap._is_local_host("127.0.0.1")  # type: ignore[attr-defined]
    assert not _bootstrap._is_local_host("example.com")  # type: ignore[attr-defined]
