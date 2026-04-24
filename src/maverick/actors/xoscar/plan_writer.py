"""xoscar PlanWriterActor — writes flight plan + briefing markdown to disk."""

from __future__ import annotations

from pathlib import Path

import xoscar as xo

from maverick.actors.xoscar.messages import WritePlanRequest, WritePlanResult


class PlanWriterActor(xo.Actor):
    """Deterministic file writer for flight plan and briefing."""

    def __init__(self, *, output_dir: str) -> None:
        if not output_dir:
            raise ValueError("PlanWriterActor requires 'output_dir'")
        self._output_dir = output_dir

    async def write(self, request: WritePlanRequest) -> WritePlanResult:
        output_dir = Path(self._output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        plan_path = output_dir / "flight-plan.md"
        plan_path.write_text(request.flight_plan_markdown, encoding="utf-8")

        briefing_path: Path | None = None
        if request.briefing_markdown:
            briefing_path = output_dir / "briefing.md"
            briefing_path.write_text(request.briefing_markdown, encoding="utf-8")

        return WritePlanResult(
            flight_plan_path=str(plan_path),
            briefing_path=str(briefing_path) if briefing_path else None,
        )
