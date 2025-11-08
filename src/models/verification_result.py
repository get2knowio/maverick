"""VerificationResult dataclass for repo verification outcomes."""

from dataclasses import dataclass
from typing import Literal


# Error taxonomy for verification failures
ErrorCode = Literal[
    "none",  # Success
    "validation_error",  # Malformed URL or unsupported host
    "auth_error",  # GitHub not authenticated
    "not_found",  # Repository does not exist
    "access_denied",  # Repository exists but no access
    "transient_error",  # Network/timeout/rate limit
]

# Verification status
VerificationStatus = Literal["pass", "fail"]

# Tool identifier
Tool = Literal["gh"]


@dataclass
class VerificationResult:
    """Result of GitHub repository verification.

    Attributes:
        tool: CLI tool used for verification (always "gh" for MVP)
        status: Pass or fail outcome
        message: Human-readable result description
        host: GitHub host (e.g., github.com or GHES host)
        repo_slug: Repository in owner/repo format
        error_code: Structured error category
        attempts: Number of verification attempts (1 or 2)
        duration_ms: Total verification duration in milliseconds
    """

    tool: Tool
    status: VerificationStatus
    message: str
    host: str
    repo_slug: str
    error_code: ErrorCode
    attempts: int
    duration_ms: int

    def __post_init__(self) -> None:
        """Validate result fields."""
        if self.attempts < 1:
            raise ValueError("attempts must be >= 1")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be >= 0")
        if self.status == "pass" and self.error_code != "none":
            raise ValueError("status=pass requires error_code=none")
        if self.status == "fail" and self.error_code == "none":
            raise ValueError("status=fail requires non-none error_code")
