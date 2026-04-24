"""xoscar ValidatorActor — deterministic decomposition validator.

Validates work-unit specs against flight-plan criteria. Pure Python —
no ACP executor, no MCP inbox, no ``supervisor_ref`` dependency. The
supervisor calls ``validate(...)`` via in-pool RPC and awaits the
typed ``ValidationResult``.
"""

from __future__ import annotations

from typing import Any

import xoscar as xo

from maverick.actors.xoscar.messages import ValidateRequest, ValidationResult
from maverick.logging import get_logger

logger = get_logger(__name__)


class ValidatorActor(xo.Actor):
    """Validates decomposition specs against flight-plan success criteria."""

    def __init__(self, flight_plan: Any) -> None:
        self._flight_plan = flight_plan
        sc_list = getattr(flight_plan, "success_criteria", []) or []
        self._sc_count = len(sc_list)
        self._sc_refs: list[str] = []
        for i, sc in enumerate(sc_list):
            ref = getattr(sc, "ref", None) or f"SC-{i + 1:03d}"
            self._sc_refs.append(ref)

    async def validate(self, request: ValidateRequest) -> ValidationResult:
        from maverick.library.actions.decompose import (
            SCCoverageError,
            validate_decomposition,
        )

        try:
            validate_decomposition(
                specs=list(request.specs),
                success_criteria_count=self._sc_count,
                expected_sc_refs=list(self._sc_refs),
            )
            return ValidationResult(passed=True)
        except SCCoverageError as exc:
            return ValidationResult(
                passed=False,
                error_type="coverage",
                gaps=tuple(exc.gaps) if exc.gaps else (),
                message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 — matches legacy behaviour
            logger.error("validator.error", error=str(exc))
            return ValidationResult(
                passed=False,
                error_type="other",
                gaps=(),
                message=str(exc),
            )
