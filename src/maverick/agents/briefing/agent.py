"""``BriefingAgent`` — typed briefing agent.

Used by both refuel briefings (navigator / structuralist / recon /
contrarian) and pre-flight briefings (scopist / codebase_analyst /
criteria_writer / preflight_contrarian). Each instance owns one result
schema and one persona name, both passed at construction time.

**Pattern D migration:** the constructor accepts either ``handle=`` (the
legacy OpenCode path — inherits from :class:`Agent` and uses
``_send_structured``) OR ``runtime=`` (the new path — delegates to an
:class:`AgentRuntime` directly, no OpenCode server required). The two
paths produce identical typed payloads + cost telemetry; only the
transport differs. Phase 2 of
``docs/migration-implementation-plan.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

from maverick.agents.base import Agent

if TYPE_CHECKING:
    from airframe.protocol import AgentRuntime

    from maverick.executor.config import StepConfig
    from maverick.runtime.opencode import (
        CostSink,
        OpenCodeClient,
        OpenCodeServerHandle,
        Tier,
    )

BRIEFING_TIMEOUT_SECONDS = 1200

# Map the in-process agent label to the bundled OpenCode persona file.
# The .md files live at ``runtime/opencode/profile/agents/maverick.<persona>.md``.
OPENCODE_AGENT_MAP: dict[str, str] = {
    "navigator": "maverick.navigator",
    "structuralist": "maverick.structuralist",
    "recon": "maverick.recon",
    "contrarian": "maverick.contrarian",
    "scopist": "maverick.scopist",
    "codebase_analyst": "maverick.codebase-analyst",
    "criteria_writer": "maverick.criteria-writer",
    "preflight_contrarian": "maverick.preflight-contrarian",
}


def opencode_agent_for(agent_name: str) -> str | None:
    """Map an agent label (``"navigator"``) to its bundled persona name.

    Returns ``None`` for unmapped names so the OpenCode server falls
    back to its default agent and surfaces the missing persona in
    logs rather than silently routing to the wrong system prompt.
    """
    return OPENCODE_AGENT_MAP.get(agent_name)


class BriefingAgent(Agent):
    """One briefing agent: per-instance schema + per-instance persona."""

    # Set per-instance via constructor; the class default is BaseModel
    # so type checkers see a valid type.
    result_model: ClassVar[type[BaseModel]] = BaseModel
    provider_tier: ClassVar[str] = "briefing"

    def __init__(
        self,
        *,
        handle: OpenCodeServerHandle | None = None,
        cwd: str,
        agent_name: str,
        result_model: type[BaseModel],
        step_config: StepConfig | dict[str, Any] | None = None,
        tier_overrides: dict[str, Tier] | None = None,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
        client_factory: Callable[[], OpenCodeClient] | None = None,
        runtime: AgentRuntime | None = None,
    ) -> None:
        """Initialize either the legacy OpenCode path or the Pattern D path.

        Exactly one of ``handle`` or ``runtime`` must be provided.

        - When ``handle`` is set: this is the legacy OpenCode HTTP path.
          The agent inherits the base :class:`Agent` plumbing and
          :meth:`brief` calls ``_send_structured``.
        - When ``runtime`` is set: this is the Pattern D path. The agent
          bypasses :class:`Agent`'s OpenCode session machinery and
          :meth:`brief` calls ``runtime.execute`` directly. ``persona``
          is forwarded so OpenCode-compatible runtimes still honour the
          bundled persona file.

        Args:
            handle: OpenCode server handle (legacy path).
            runtime: :class:`AgentRuntime` instance (Pattern D path).
            ... other args are common to both paths.
        """
        if handle is None and runtime is None:
            raise ValueError(f"{type(self).__name__} requires either 'handle' or 'runtime'")
        if handle is not None and runtime is not None:
            raise ValueError(
                f"{type(self).__name__} got both 'handle' and 'runtime'; pass exactly one"
            )

        self._runtime = runtime
        self._agent_name = agent_name

        if runtime is not None:
            # Pattern D path. Skip the OpenCode-shaped base init (which
            # demands a handle) and set just enough state for the runtime
            # path: cwd, tag, schema, persona, cost-record bookkeeping.
            from maverick.actors.step_config import load_step_config

            if not cwd:
                raise ValueError(f"{type(self).__name__} requires 'cwd'")
            self._handle = None  # type: ignore[assignment]
            self._cwd = cwd
            self._step_config = load_step_config(step_config)
            self._tier_overrides = tier_overrides
            self._cost_sink = cost_sink
            self._tag = tag or f"briefing.{agent_name}"
            self._client_factory = None
            self._result_model_instance = result_model
            self._opencode_agent_instance = opencode_agent_for(agent_name)
            self._client = None
            self._session_id = None
            self._validated_bindings = set()
            self._failed_bindings = set()
            self._last_cost_record = None
            return

        # Legacy OpenCode path.
        assert handle is not None
        super().__init__(
            handle=handle,
            cwd=cwd,
            step_config=step_config,
            tier_overrides=tier_overrides,
            cost_sink=cost_sink,
            tag=tag or f"briefing.{agent_name}",
            opencode_agent=opencode_agent_for(agent_name),
            result_model=result_model,
            client_factory=client_factory,
        )

    @property
    def agent_name(self) -> str:
        return self._agent_name

    async def open(self) -> None:
        if self._runtime is not None:
            # Runtime manages its own lifecycle lazily.
            return
        await super().open()

    async def close(self) -> None:
        if self._runtime is not None:
            await self._runtime.close()
            return
        await super().close()

    async def rotate_session(self) -> None:
        if self._runtime is not None:
            await self._runtime.reset()
            return
        await super().rotate_session()

    async def brief(self, prompt: str) -> BaseModel:
        """Run the briefing prompt and return the typed payload."""
        wrapped = (
            "If your analysis surfaces no findings (e.g. greenfield project "
            "with no existing code), set empty arrays / minimal required "
            "fields rather than refusing.\n\n"
            "# Briefing input\n\n"
            f"{prompt}"
        )
        if self._runtime is not None:
            return await self._execute_via_runtime(wrapped, timeout=BRIEFING_TIMEOUT_SECONDS)
        return await self._send_structured(wrapped, timeout=BRIEFING_TIMEOUT_SECONDS)


__all__ = [
    "BRIEFING_TIMEOUT_SECONDS",
    "OPENCODE_AGENT_MAP",
    "BriefingAgent",
    "opencode_agent_for",
]
