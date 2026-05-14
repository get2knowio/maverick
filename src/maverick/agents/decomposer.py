"""``DecomposerAgent`` — multi-phase decomposition (outline / detail / fix / nudge).

Preserves the session-mode rotation behavior of the legacy actor: detail
and fix phases reuse the same OpenCode session across multiple turns to
keep the seeded context (flight plan + outline JSON) in cache, rotating
when the mode changes or the per-mode turn budget is exhausted.

Two roles:

* ``primary`` — outline + detail + fix entry points.
* ``pool`` — detail-only worker.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

from maverick.agents.base import Agent
from maverick.payloads import (
    SubmitDetailsPayload,
    SubmitFixPayload,
    SubmitOutlinePayload,
)

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig
    from maverick.runtime.opencode import (
        CostSink,
        OpenCodeClient,
        OpenCodeServerHandle,
        Tier,
    )

DETAIL_TIMEOUT_SECONDS = 1200
DEFAULT_PROMPT_TIMEOUT_SECONDS = 1800


class DecomposerAgent(Agent):
    """OpenCode-backed decomposer with session-mode reuse."""

    result_model: ClassVar[type[BaseModel]] = SubmitOutlinePayload
    provider_tier: ClassVar[str] = "decompose"
    opencode_agent: ClassVar[str | None] = "maverick.decomposer"

    def __init__(
        self,
        *,
        handle: OpenCodeServerHandle,
        cwd: str,
        role: str = "primary",
        detail_session_max_turns: int = 5,
        fix_session_max_turns: int = 1,
        step_config: StepConfig | dict[str, Any] | None = None,
        tier_overrides: dict[str, Tier] | None = None,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
        client_factory: Callable[[], OpenCodeClient] | None = None,
    ) -> None:
        super().__init__(
            handle=handle,
            cwd=cwd,
            step_config=step_config,
            tier_overrides=tier_overrides,
            cost_sink=cost_sink,
            tag=tag or f"decomposer.{role}",
            client_factory=client_factory,
        )
        self._role = role
        self._detail_session_max_turns = max(1, int(detail_session_max_turns))
        self._fix_session_max_turns = max(1, int(fix_session_max_turns))

        # Session-mode bookkeeping (preserved from the legacy actor so we
        # keep the seeded prompt-cache benefit across detail turns).
        self._session_mode: str | None = None
        self._session_turns_in_mode = 0

        # Seeded context for detail prompts.
        self._detail_outline_json: str = "{}"
        self._detail_flight_plan: str = ""
        self._detail_verification: str = ""
        self._detail_seed_stale = True

        # Seeded context for fix prompts.
        self._fix_outline_json: str = '{"work_units": []}'
        self._fix_details_json: str = '{"details": []}'
        self._fix_verification: str = ""
        self._fix_seed_stale = True

    @property
    def role(self) -> str:
        return self._role

    async def rotate_session(self) -> None:
        """Reset per-bead session-mode bookkeeping, then drop the session.

        Without this override, ``squadron.rotate_for_new_bead()`` (which
        iterates :meth:`Agent.rotate_session` on every agent) would
        leave ``_session_mode`` / ``_session_turns_in_mode`` carrying
        over from the previous unit's last phase.
        """
        self._session_mode = None
        self._session_turns_in_mode = 0
        await super().rotate_session()

    async def set_context(
        self,
        *,
        outline_json: str,
        flight_plan_content: str,
        verification_properties: str,
    ) -> None:
        """Broadcast context for the upcoming detail phase."""
        self._detail_outline_json = outline_json
        self._detail_flight_plan = flight_plan_content
        self._detail_verification = verification_properties
        self._detail_seed_stale = True

    async def outline(
        self,
        *,
        flight_plan_content: str,
        codebase_context: Any,
        briefing: Any = None,
        runway_context: str | None = None,
        validation_feedback: str | None = None,
    ) -> SubmitOutlinePayload:
        """Run the outline prompt and return :class:`SubmitOutlinePayload`."""
        prompt = self._build_outline_prompt(
            flight_plan_content=flight_plan_content,
            codebase_context=codebase_context,
            briefing=briefing,
            runway_context=runway_context,
            validation_feedback=validation_feedback,
        )
        await self._maybe_rotate_session(mode="outline", seed_stale=True, max_turns=1)
        payload = await self._send_structured(
            prompt, schema=SubmitOutlinePayload, timeout=DEFAULT_PROMPT_TIMEOUT_SECONDS
        )
        assert isinstance(payload, SubmitOutlinePayload)
        return payload

    async def detail(self, *, unit_ids: Sequence[str]) -> SubmitDetailsPayload:
        """Run a detail-pass prompt for one or more units."""
        prompt, refreshed_seed = self._build_detail_prompt(unit_ids=list(unit_ids))
        await self._maybe_rotate_session(
            mode="detail",
            seed_stale=refreshed_seed,
            max_turns=self._detail_session_max_turns,
        )
        payload = await self._send_structured(
            prompt, schema=SubmitDetailsPayload, timeout=DETAIL_TIMEOUT_SECONDS
        )
        assert isinstance(payload, SubmitDetailsPayload)
        # The detail-mode seed has been delivered; future turns within
        # the same session reuse it.
        self._detail_seed_stale = False
        if self._session_mode == "detail":
            self._session_turns_in_mode += 1
        return payload

    async def fix(
        self,
        *,
        coverage_gaps: Sequence[str],
        overloaded: Sequence[str],
        outline_json: str | None = None,
        details_json: str | None = None,
        verification_properties: str | None = None,
    ) -> SubmitFixPayload:
        """Run the fix-pass prompt and return :class:`SubmitFixPayload`."""
        if outline_json:
            self._fix_outline_json = outline_json
        if details_json:
            self._fix_details_json = details_json
        if verification_properties:
            self._fix_verification = verification_properties
        prompt, refreshed_seed = self._build_fix_prompt(
            coverage_gaps=list(coverage_gaps), overloaded=list(overloaded)
        )
        await self._maybe_rotate_session(
            mode="fix",
            seed_stale=refreshed_seed,
            max_turns=self._fix_session_max_turns,
        )
        payload = await self._send_structured(
            prompt, schema=SubmitFixPayload, timeout=DEFAULT_PROMPT_TIMEOUT_SECONDS
        )
        assert isinstance(payload, SubmitFixPayload)
        self._fix_seed_stale = False
        if self._session_mode == "fix":
            self._session_turns_in_mode += 1
        return payload

    async def nudge(
        self,
        *,
        expected_tool: str,
        unit_id: str | None = None,
        reason: str | None = None,
    ) -> BaseModel:
        """Re-prompt when a previous payload was rejected upstream."""
        prompt = self._build_nudge_prompt(
            expected_tool=expected_tool, unit_id=unit_id, reason=reason
        )
        schema_map: dict[str, type[BaseModel]] = {
            "submit_outline": SubmitOutlinePayload,
            "submit_details": SubmitDetailsPayload,
            "submit_fix": SubmitFixPayload,
        }
        schema = schema_map.get(expected_tool, SubmitOutlinePayload)
        return await self._send_structured(
            prompt, schema=schema, timeout=DEFAULT_PROMPT_TIMEOUT_SECONDS
        )

    # ------------------------------------------------------------------
    # Session-mode rotation
    # ------------------------------------------------------------------

    async def _maybe_rotate_session(self, *, mode: str, seed_stale: bool, max_turns: int) -> None:
        """Rotate the OpenCode session when the mode changes or budget is hit."""
        if self._session_id is None:
            self._session_mode = mode
            self._session_turns_in_mode = 0
            return
        if (
            self._session_mode != mode
            or self._session_turns_in_mode >= max(1, max_turns)
            or seed_stale
        ):
            await self.rotate_session()
            self._session_mode = mode
            self._session_turns_in_mode = 0

    # ------------------------------------------------------------------
    # Prompt builders (delegate to the existing decompose helpers)
    # ------------------------------------------------------------------

    def _build_outline_prompt(
        self,
        *,
        flight_plan_content: str,
        codebase_context: Any,
        briefing: Any,
        runway_context: str | None,
        validation_feedback: str | None,
    ) -> str:
        from maverick.library.actions.decompose import build_outline_prompt

        body = build_outline_prompt(
            flight_plan_content,
            codebase_context,
            briefing=briefing,
            runway_context=runway_context,
        )
        if validation_feedback:
            body += (
                "\n\n## PREVIOUS ATTEMPT FAILED VALIDATION\n"
                f"{validation_feedback}\n"
                "Fix these issues in your new decomposition."
            )
        return f"# Decomposition input — outline pass (flight plan + briefing)\n\n{body}"

    def _build_detail_prompt(self, *, unit_ids: list[str]) -> tuple[str, bool]:
        from maverick.library.actions.decompose import (
            build_detail_seed_prompt,
            build_detail_turn_prompt,
        )

        # Always include the seed when the cache is stale; the session
        # rotation logic decides whether the in-session cache hits.
        needs_seed = self._detail_seed_stale or self._session_mode != "detail"
        prompt_parts: list[str] = []
        if needs_seed:
            prompt_parts.append(
                build_detail_seed_prompt(
                    flight_plan_content=self._detail_flight_plan,
                    outline_json=self._detail_outline_json,
                    verification_properties=self._detail_verification,
                )
            )
        prompt_parts.append(build_detail_turn_prompt(unit_ids=unit_ids))
        body = "\n\n".join(prompt_parts)
        return (
            f"# Decomposition input — detail pass (outline + details turn)\n\n{body}",
            needs_seed,
        )

    def _build_fix_prompt(
        self, *, coverage_gaps: list[str], overloaded: list[str]
    ) -> tuple[str, bool]:
        from maverick.library.actions.decompose import (
            build_fix_seed_prompt,
            build_fix_turn_prompt,
        )

        needs_seed = self._fix_seed_stale or self._session_mode != "fix"
        prompt_parts: list[str] = []
        if needs_seed:
            prompt_parts.append(
                build_fix_seed_prompt(
                    outline_json=self._fix_outline_json,
                    details_json=self._fix_details_json,
                    verification_properties=self._fix_verification,
                )
            )
        prompt_parts.append(
            build_fix_turn_prompt(coverage_gaps=coverage_gaps, overloaded=overloaded)
        )
        body = "\n\n".join(prompt_parts)
        return (
            "# Decomposition input — fix pass (submit the COMPLETE updated "
            f"work_units and details, not just the changes)\n\n{body}",
            needs_seed,
        )

    def _build_nudge_prompt(
        self, *, expected_tool: str, unit_id: str | None, reason: str | None
    ) -> str:
        guidance: list[str] = []
        if expected_tool == "submit_details" and unit_id:
            guidance.append(f"Provide a complete entry for `{unit_id}`.")
        else:
            guidance.append("Submit even partial results rather than refusing.")
        if reason:
            guidance.append(f"Reason: {reason}")
        return (
            f"Re-submit your previous response with the corrected payload.\n\n{' '.join(guidance)}"
        )


__all__ = [
    "DEFAULT_PROMPT_TIMEOUT_SECONDS",
    "DETAIL_TIMEOUT_SECONDS",
    "DecomposerAgent",
]
