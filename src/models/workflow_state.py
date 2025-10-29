"""WorkflowState dataclass for tracking workflow execution state."""

from dataclasses import dataclass
from typing import Literal

from src.models.verification_result import VerificationResult


# Workflow state literals
WorkflowStateType = Literal["pending", "verified", "failed"]


@dataclass
class WorkflowState:
    """State of workflow execution.

    Tracks progression through verification and subsequent phases.

    Invariants:
        - state="pending" requires verification=None
        - state="verified" requires verification with status="pass"
        - state="failed" requires verification with status="fail"

    Attributes:
        state: Current workflow state
        verification: Result of repository verification (None until verification completes)
    """

    state: WorkflowStateType
    verification: VerificationResult | None = None

    def __post_init__(self) -> None:
        """Validate state transitions."""
        # Enforce pending state invariant: pending requires verification=None
        if self.state == "pending" and self.verification is not None:
            raise ValueError("state=pending requires verification=None")

        # Enforce verification presence invariant: verification present disallows pending
        if self.verification is not None and self.state == "pending":
            raise ValueError("verification present requires state!=pending")

        # Enforce verified state requirements
        if self.state == "verified" and self.verification is None:
            raise ValueError("state=verified requires verification result")
        if self.state == "failed" and self.verification is None:
            raise ValueError("state=failed requires verification result")

        # Enforce status alignment when verification is present
        if self.verification is not None:
            if self.state == "verified" and self.verification.status != "pass":
                raise ValueError("state=verified requires verification.status=pass")
            if self.state == "failed" and self.verification.status != "fail":
                raise ValueError("state=failed requires verification.status=fail")
