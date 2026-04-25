"""Tests for ``format_acp_error`` in :mod:`maverick.executor._connection_pool`.

The helper exists to surface ``error.data.details`` from JSON-RPC errors that
``acp.RequestError.__str__`` otherwise drops on the floor — the very thing that
turned a 5-minute "wrong settings.json value" diagnosis into an hour-long hunt.
"""

from __future__ import annotations

from acp import RequestError as AcpRequestError

from maverick.executor._connection_pool import format_acp_error


def test_includes_message_code_and_details() -> None:
    exc = AcpRequestError(
        -32603,
        "Internal error",
        {"details": "Invalid permissions.defaultMode: auto."},
    )
    rendered = format_acp_error(exc)
    assert "Internal error" in rendered
    assert "(code=-32603)" in rendered
    assert "Invalid permissions.defaultMode: auto." in rendered


def test_falls_back_to_repr_when_data_has_no_details() -> None:
    exc = AcpRequestError(-32602, "Invalid params", {"errors": ["foo"]})
    rendered = format_acp_error(exc)
    assert "Invalid params" in rendered
    assert "(code=-32602)" in rendered
    # No "details" key → render the dict so callers don't lose info silently.
    assert "errors" in rendered
    assert "foo" in rendered


def test_handles_non_dict_data() -> None:
    exc = AcpRequestError(-32000, "Authentication required", "string-blob")
    rendered = format_acp_error(exc)
    assert "Authentication required" in rendered
    assert "string-blob" in rendered


def test_handles_missing_data() -> None:
    exc = AcpRequestError(-32601, "Method not found", None)
    rendered = format_acp_error(exc)
    assert rendered == "Method not found (code=-32601)"


def test_handles_empty_message() -> None:
    exc = AcpRequestError(-32603, "", {"details": "boom"})
    rendered = format_acp_error(exc)
    # We substitute a placeholder so callers still get something useful
    # downstream of the format helper.
    assert "ACP error" in rendered
    assert "boom" in rendered


def test_empty_details_string_falls_through_to_data_repr() -> None:
    exc = AcpRequestError(-32603, "Internal error", {"details": ""})
    rendered = format_acp_error(exc)
    # Empty string is not "useful"; helper should still surface the raw data
    # so the caller has something to grep on.
    assert "Internal error" in rendered
    assert "details" in rendered
