"""Exceptions for assumption ledger operations."""

from __future__ import annotations

from maverick.exceptions.base import MaverickError


class AssumptionLedgerError(MaverickError):
    """Raised when a bd-layer operation on a ledger entry fails.

    Attributes:
        message: Human-readable error message.
    """
