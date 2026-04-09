"""Runway-related exceptions."""

from __future__ import annotations

from maverick.exceptions.base import MaverickError


class RunwayError(MaverickError):
    """Base exception for runway operations."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class RunwayNotInitializedError(RunwayError):
    """Runway directory structure does not exist."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Runway not initialized at {path}. Run 'maverick runway init'.")


class RunwayCorruptedError(RunwayError):
    """Runway data is corrupted or unparseable."""

    def __init__(self, path: str, detail: str = "") -> None:
        self.path = path
        self.detail = detail
        msg = f"Runway data corrupted at {path}"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)
