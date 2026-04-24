"""xoscar GateActor — deterministic validation gate.

Runs build/lint/test stages against the workspace. Pure async Python;
no MCP inbox, no ``supervisor_ref``.
"""

from __future__ import annotations

import xoscar as xo

from maverick.actors.xoscar.messages import GateRequest, GateResult
from maverick.logging import get_logger

logger = get_logger(__name__)

DEFAULT_GATE_TIMEOUT_SECONDS = 600.0


class GateActor(xo.Actor):
    """Deterministic validation gate. Runs cargo build/clippy/test."""

    def __init__(
        self,
        *,
        validation_commands: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        super().__init__()
        self._validation_commands = validation_commands

    async def gate(self, request: GateRequest) -> GateResult:
        from maverick.library.actions.validation import run_independent_gate
        from maverick.workflows.fly_beads.constants import DEFAULT_VALIDATION_STAGES

        try:
            raw = await run_independent_gate(
                stages=list(DEFAULT_VALIDATION_STAGES),
                cwd=request.cwd,
                validation_commands=self._validation_commands,
                timeout_seconds=request.timeout_seconds,
            )
            return GateResult(
                passed=bool(raw.get("passed", False)),
                summary=str(raw.get("summary", "")),
                stages=tuple(raw.get("stages", ()) or ()),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("gate.error", error=str(exc))
            return GateResult(passed=False, summary=f"Gate error: {exc}")
