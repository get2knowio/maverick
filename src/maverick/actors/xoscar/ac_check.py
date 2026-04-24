"""xoscar ACCheckActor — deterministic acceptance-criteria verification."""

from __future__ import annotations

from pathlib import Path

import xoscar as xo

from maverick.actors.xoscar.messages import ACRequest, ACResult
from maverick.logging import get_logger

logger = get_logger(__name__)

AC_CHECK_TIMEOUT_SECONDS = 300.0


class ACCheckActor(xo.Actor):
    """Deterministic AC check. Runs verification commands extracted
    from a work unit's ``verification`` section against the workspace."""

    async def ac_check(self, request: ACRequest) -> ACResult:
        from maverick.runners.command import CommandRunner
        from maverick.workflows.fly_beads.steps import (
            _parse_verification_commands,
            _parse_work_unit_sections,
        )

        sections = _parse_work_unit_sections(request.description)
        verification_text = sections.get("verification", "")
        if not verification_text:
            return ACResult(passed=True)

        reasons: list[str] = []
        work_cwd = Path(request.cwd) if request.cwd else Path.cwd()
        runner = CommandRunner(cwd=work_cwd)

        for cmd_str in _parse_verification_commands(verification_text):
            first_word = cmd_str.split()[0] if cmd_str.split() else ""
            if first_word not in ("rg", "grep", "cargo", "make"):
                continue
            try:
                result = await runner.run(["sh", "-c", cmd_str])
                if result.returncode != 0:
                    reasons.append(f"Verification failed: `{cmd_str}`")
            except Exception as exc:  # noqa: BLE001
                reasons.append(f"Verification error: `{cmd_str}`: {exc}")

        return ACResult(passed=not reasons, reasons=tuple(reasons))
