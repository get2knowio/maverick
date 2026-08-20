"""Spec-chain workflow exceptions (`maverick spec`)."""

from __future__ import annotations

from maverick.exceptions.base import MaverickError


class SpecChainError(MaverickError):
    """Base exception for spec-chain operations."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class SpecChainPreflightError(SpecChainError):
    """A preflight check failed before any chain step ran."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class SpecChainStepError(SpecChainError):
    """A chain step (specify/clarify/plan/tasks/analyze) failed."""

    def __init__(self, step: str, message: str) -> None:
        self.step = step
        super().__init__(f"Step '{step}' failed: {message}")


class SpecChainStateError(SpecChainError):
    """Chain state could not be persisted, loaded, or resolved for resume."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
