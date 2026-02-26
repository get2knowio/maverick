"""Centralized agent output contract registry.

All agent output types are re-exported from this module for single-import
access.  Use ``validate_output()`` to parse and validate raw agent text
against a contract.

Example::

    from maverick.agents.contracts import FixerResult, validate_output

    result = validate_output(raw_text, FixerResult)
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from maverick.exceptions.base import MaverickError

# ---------------------------------------------------------------------------
# Type variable for validate_output generic return
# ---------------------------------------------------------------------------

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------

_MAX_RAW_DISPLAY = 500


class OutputValidationError(MaverickError):
    """Raised when agent output cannot be parsed into the expected model.

    Attributes:
        expected_model: Name of the expected Pydantic model class.
        raw_output: The raw text that failed (truncated to 500 chars).
        parse_error: What went wrong.
        stage: Where in the pipeline it failed.
    """

    def __init__(
        self,
        *,
        expected_model: str,
        raw_output: str,
        parse_error: str,
        stage: Literal["extraction", "json_parse", "validation"],
    ) -> None:
        self.expected_model = expected_model
        self.raw_output = raw_output[:_MAX_RAW_DISPLAY]
        self.parse_error = parse_error
        self.stage = stage
        super().__init__(
            f"Output validation failed at {stage} stage for {expected_model}: "
            f"{parse_error}"
        )


# ---------------------------------------------------------------------------
# Code-block extraction regex
# ---------------------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.DOTALL)


# ---------------------------------------------------------------------------
# validate_output()
# ---------------------------------------------------------------------------


def validate_output(
    raw: str,
    model: type[T],
    *,
    strict: bool = True,
) -> T | None:
    """Extract JSON from markdown code blocks and validate against a Pydantic model.

    Pipeline:
        1. Search for ````` ```json ... ``` ````` code block (first match wins).
        2. Extract JSON string from code block.
        3. Parse JSON string -> dict.
        4. Validate dict against Pydantic model.

    Args:
        raw: Raw text output from an agent, potentially containing markdown.
        model: The Pydantic BaseModel subclass to validate against.
        strict: If True (default), raise ``OutputValidationError`` on failure.
            If False, return None on failure.

    Returns:
        Validated model instance, or None if ``strict=False`` and validation
        fails.

    Raises:
        OutputValidationError: When ``strict=True`` and extraction, parsing,
            or validation fails.
    """
    model_name = model.__name__

    # 1. Extract from code block
    match = _CODE_BLOCK_RE.search(raw)
    if match is None:
        if strict:
            raise OutputValidationError(
                expected_model=model_name,
                raw_output=raw,
                parse_error="No ```json code block found in agent output",
                stage="extraction",
            )
        return None

    json_str = match.group(1).strip()

    # 2. Parse JSON
    try:
        data: Any = json.loads(json_str)
    except json.JSONDecodeError as e:
        if strict:
            raise OutputValidationError(
                expected_model=model_name,
                raw_output=raw,
                parse_error=f"JSON parse error: {e}",
                stage="json_parse",
            ) from e
        return None

    # 3. Validate against Pydantic model
    try:
        return model.model_validate(data)
    except ValidationError as e:
        if strict:
            raise OutputValidationError(
                expected_model=model_name,
                raw_output=raw,
                parse_error=f"Pydantic validation error: {e}",
                stage="validation",
            ) from e
        return None


# ---------------------------------------------------------------------------
# Re-exports — all agent output types accessible from one module
# ---------------------------------------------------------------------------

from maverick.agents.result import AgentResult  # noqa: E402
from maverick.models.fixer import FixerResult  # noqa: E402
from maverick.models.implementation import ImplementationResult  # noqa: E402
from maverick.models.issue_fix import FixResult  # noqa: E402
from maverick.models.review import ReviewFinding, ReviewResult  # noqa: E402
from maverick.models.review_models import (  # noqa: E402
    Finding,
    FindingGroup,
    FixOutcome,
    GroupedReviewResult,
)

__all__ = [
    # Utilities
    "validate_output",
    "OutputValidationError",
    # Agent output types
    "AgentResult",
    "Finding",
    "FindingGroup",
    "FixerResult",
    "FixOutcome",
    "FixResult",
    "GroupedReviewResult",
    "ImplementationResult",
    "ReviewFinding",
    "ReviewResult",
]
