"""``Agent`` — owns one airframe :class:`AgentRuntime` and one result model.

Subclass requirements:

* ``result_model: ClassVar[type[BaseModel]]`` — the Pydantic model
  used to validate structured-output payloads. Briefing-style agents
  that vary the schema per instance can pass ``result_model=...`` to
  ``__init__`` instead of declaring a class var.
* Implement domain methods that build a prompt and call
  :meth:`_execute_via_runtime`.

Lifecycle:

* :meth:`open` — initialise lazy state. No network calls.
* First :meth:`_execute_via_runtime` call hits the runtime, which
  opens its underlying session lazily.
* :meth:`rotate_session` calls :meth:`AgentRuntime.reset` to drop
  the runtime's scope (used between beads).
* :meth:`close` calls :meth:`AgentRuntime.close` for full teardown.

Async context-manager support (``async with Agent(...)``) calls
:meth:`open` / :meth:`close` for you.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar, Self

from airframe.cost import CostRecord
from airframe.errors import RuntimeStructuredOutputError
from airframe.protocol import AgentRuntime
from pydantic import BaseModel, ValidationError

from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.runtime.registry import CostSink

logger = get_logger(__name__)


DEFAULT_STRUCTURED_TIMEOUT_SECONDS = 600.0
DEFAULT_TEXT_TIMEOUT_SECONDS = 600.0


class AgentPayloadValidationError(RuntimeStructuredOutputError):
    """Runtime returned a structured payload that didn't match the agent's model.

    Subclasses :class:`RuntimeStructuredOutputError` so callers can
    handle schema-rejected payloads under the same `except` clause as
    runtime-reported structured-output failures.
    """


class Agent:
    """Base class: owns one airframe runtime and one result model."""

    # Subclasses override (or pass via __init__ for per-instance schemas).
    result_model: ClassVar[type[BaseModel]] = BaseModel

    # Provider tier name — used by :func:`runtime_for_agent` to look up
    # the role's binding. Subclasses set this.
    provider_tier: ClassVar[str | None] = None

    # Optional persona passed through to airframe-runtime adapters that
    # honour it (Claude Code's bundled agents, OpenCode personas).
    # Subclasses that vary the persona per instance pass
    # ``opencode_agent=...`` to ``__init__`` instead.
    opencode_agent: ClassVar[str | None] = None

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        cwd: str,
        step_config: Any = None,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
        opencode_agent: str | None = None,
        result_model: type[BaseModel] | None = None,
    ) -> None:
        if not cwd:
            raise ValueError(f"{type(self).__name__} requires 'cwd'")
        self._runtime = runtime
        self._cwd = cwd
        # step_config is preserved (some subclasses pass timeouts /
        # max_tokens through it) but no longer drives provider routing.
        self._step_config = step_config
        self._cost_sink = cost_sink
        self._tag = tag or type(self).__name__

        # Per-instance overrides for schema / persona.
        self._result_model_instance: type[BaseModel] | None = result_model
        self._opencode_agent_instance: str | None = opencode_agent

        # Last cost record observed from the runtime; populated on every
        # successful execute. Cleared by :meth:`rotate_session`.
        self._last_cost_record: CostRecord | None = None

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    async def open(self) -> None:
        """No-op hook for symmetry with :meth:`close`.

        The airframe runtime opens its own resources lazily on first
        :meth:`execute`. Subclasses can override for one-time setup
        outside the constructor (e.g. opening files).
        """
        return None

    async def close(self) -> None:
        """Tear down the runtime. Idempotent."""
        await self._runtime.close()

    async def __aenter__(self) -> Self:
        await self.open()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def rotate_session(self) -> None:
        """Drop accumulated runtime state — called between beads."""
        await self._runtime.reset()

    @property
    def last_cost_record(self) -> CostRecord | None:
        return self._last_cost_record

    @property
    def tag(self) -> str:
        return self._tag

    # ------------------------------------------------------------------
    # Send path
    # ------------------------------------------------------------------

    async def _execute_via_runtime(
        self,
        prompt: str,
        *,
        schema: type[BaseModel] | None = None,
        timeout: float = DEFAULT_STRUCTURED_TIMEOUT_SECONDS,
    ) -> BaseModel:
        """Run a prompt through the airframe runtime and return a typed payload.

        Validates the structured payload against ``schema`` (defaulting
        to the agent's effective result model), captures the cost record
        on ``self._last_cost_record``, and emits the ``agent.cost``
        structured-log row.

        Raises:
            RuntimeStructuredOutputError: when ``result.structured`` is None.
            AgentPayloadValidationError: when the payload fails schema
                validation.
        """
        from maverick.agents.system_prompts import load_persona_system_prompt

        target = schema or self._effective_result_model()
        persona = self._opencode_agent_instance or self.opencode_agent
        result = await self._runtime.execute(
            prompt,
            schema=target,
            persona=persona,
            system=load_persona_system_prompt(persona),
            timeout=timeout,
        )
        if result.structured is None:
            raise RuntimeStructuredOutputError(
                f"{self._runtime.label}: structured payload missing",
                body=result.text,
            )
        try:
            payload = target.model_validate(result.structured)
        except ValidationError as exc:
            raise AgentPayloadValidationError(
                f"{target.__name__} validation failed: {exc}",
                body=result.structured,
            ) from exc
        self._last_cost_record = result.cost
        self._emit_cost(result.cost)
        return payload

    # ------------------------------------------------------------------
    # Schema resolution
    # ------------------------------------------------------------------

    def _effective_result_model(self) -> type[BaseModel]:
        return self._result_model_instance or self.result_model

    # ------------------------------------------------------------------
    # Cost telemetry
    # ------------------------------------------------------------------

    def _emit_cost(self, record: CostRecord) -> None:
        """Emit the ``agent.cost`` structured-log row + flush to sink."""
        from maverick.agents.context import current_tags

        tags = current_tags()
        logger.info(
            "agent.cost",
            agent=self._tag,
            tier=self.provider_tier or "inline",
            runtime=self._runtime.label,
            **tags,
            **record.to_dict(),
        )
        sink = self._cost_sink
        if sink is None:
            return
        from maverick.runway.models import CostEntry

        entry = CostEntry(
            actor=self._tag,
            tier=self.provider_tier or "inline",
            provider_id=record.provider_id,
            model_id=record.model_id,
            cost_usd=record.cost_usd,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            cache_read_tokens=record.cache_read_tokens,
            cache_write_tokens=record.cache_write_tokens,
            finish=record.finish,
            bead_id=tags.get("bead_id", ""),
        )
        # Schedule async — the send path must not block on JSONL I/O.
        asyncio.create_task(self._flush_cost_entry(sink, entry))

    async def _flush_cost_entry(self, sink: CostSink, entry: Any) -> None:
        """Best-effort delivery to the cost sink. Never raises."""
        try:
            await sink(entry)
        except Exception as exc:  # noqa: BLE001 — sink failures must not break sends
            logger.debug(
                "agent.cost_sink_failed",
                agent=self._tag,
                error=str(exc)[:200],
            )


__all__ = [
    "DEFAULT_STRUCTURED_TIMEOUT_SECONDS",
    "DEFAULT_TEXT_TIMEOUT_SECONDS",
    "Agent",
    "AgentPayloadValidationError",
]
