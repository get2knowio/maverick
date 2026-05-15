"""``Agent`` — owns one OpenCode session and one result model.

Replaces ``OpenCodeAgentMixin``. Decoupled from xoscar: the OpenCode
server handle, tier overrides, and cost sink are injected via the
constructor instead of being looked up by ``self.address`` from the
pool registry. This lets agents be tested in isolation, used outside
xoscar (e.g. from one-shot scripts), and composed by the per-workflow
``Squadron`` (see :mod:`maverick.squadron`).

Subclass requirements:

* ``result_model: ClassVar[type[BaseModel]]`` — the Pydantic model
  used to validate structured-output payloads. Briefing-style agents
  that vary the schema per instance can pass ``result_model=...`` to
  ``__init__`` instead of declaring a class var.
* Implement domain methods that build a prompt and call
  :meth:`_send_structured` / :meth:`_send_text`.

Lifecycle:

* :meth:`open` — initialise lazy state. No network calls.
* First :meth:`_send_structured` (or :meth:`_send_text`) call lazily
  builds the :class:`OpenCodeClient` and creates a session.
* :meth:`rotate_session` drops the current session for a fresh
  context (used between beads).
* :meth:`close` deletes the session and closes the client.

Async context-manager support (``async with Agent(...)``) calls
:meth:`open` / :meth:`close` for you.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, Self

from pydantic import BaseModel, ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from maverick.logging import get_logger
from maverick.runtime.opencode import (
    AgentRuntimeError,
    CascadeOutcome,
    CostRecord,
    CostSink,
    OpenCodeClient,
    OpenCodeServerHandle,
    ProviderModel,
    RuntimeStructuredOutputError,
    RuntimeTransientError,
    SendResult,
    Tier,
    cascade_send,
    cost_record_from_send,
    resolve_tier,
    validate_model_id,
)

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)


DEFAULT_STRUCTURED_TIMEOUT_SECONDS = 600.0
DEFAULT_TEXT_TIMEOUT_SECONDS = 600.0

#: Per-binding transient-retry policy. A 5xx / rate-limit / network blip
#: gets up to 3 attempts on the same binding (with exponential backoff)
#: before the cascade falls over to the next provider. Auth, model-not-
#: found, structured-output, and context-overflow errors are NOT retried
#: here — they have different semantics (cascade or abort).
TRANSIENT_RETRY_ATTEMPTS = 3
TRANSIENT_RETRY_WAIT_MIN_SECONDS = 1.0
TRANSIENT_RETRY_WAIT_MAX_SECONDS = 10.0


class AgentPayloadValidationError(RuntimeStructuredOutputError):
    """Server returned a structured payload that didn't match the agent's model.

    Subclasses :class:`RuntimeStructuredOutputError` so the tier cascade
    treats schema-rejected payloads the same as server-reported
    structured-output failures — both indicate the current binding can't
    produce a usable response and the right recovery is to fall over to
    the next binding.
    """


class Agent:
    """Base class: owns one OpenCode session and one result model."""

    # Subclasses override (or pass via __init__ for per-instance schemas).
    result_model: ClassVar[type[BaseModel]] = BaseModel

    # Provider tier name (see ``maverick.runtime.opencode.DEFAULT_TIERS``).
    # Subclasses set this; ``None`` means "let OpenCode use its server
    # default".
    provider_tier: ClassVar[str | None] = None

    # Bundled OpenCode persona to load on every send. The runtime ships
    # markdown agent files at ``runtime/opencode/profile/agents/<name>.md``.
    # When set, every ``_send_*`` call adds ``"agent": <name>`` so
    # OpenCode loads the matching frontmatter + body as the session's
    # system prompt. Subclasses that vary the persona per instance pass
    # ``opencode_agent=...`` to ``__init__`` instead.
    opencode_agent: ClassVar[str | None] = None

    def __init__(
        self,
        *,
        handle: OpenCodeServerHandle,
        cwd: str,
        step_config: StepConfig | dict[str, Any] | None = None,
        tier_overrides: dict[str, Tier] | None = None,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
        opencode_agent: str | None = None,
        result_model: type[BaseModel] | None = None,
        client_factory: Callable[[], OpenCodeClient] | None = None,
    ) -> None:
        if not cwd:
            raise ValueError(f"{type(self).__name__} requires 'cwd'")
        from maverick.actors.step_config import load_step_config

        self._handle = handle
        self._cwd = cwd
        self._step_config = load_step_config(step_config)
        self._tier_overrides = tier_overrides
        self._cost_sink = cost_sink
        self._tag = tag or type(self).__name__
        self._client_factory = client_factory

        # Per-instance overrides for schema / persona.
        if result_model is not None:
            self._result_model_instance: type[BaseModel] | None = result_model
        else:
            self._result_model_instance = None
        if opencode_agent is not None:
            self._opencode_agent_instance: str | None = opencode_agent
        else:
            self._opencode_agent_instance = None

        # Lazy state — populated by open() / first send.
        self._client: OpenCodeClient | None = None
        self._session_id: str | None = None
        self._validated_bindings: set[ProviderModel] = set()
        self._failed_bindings: set[ProviderModel] = set()
        self._last_cost_record: CostRecord | None = None

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    async def open(self) -> None:
        """Initialise lazy state. No network calls.

        Idempotent — safe to call multiple times. The actual OpenCode
        session is opened on the first send so agent construction
        stays cheap.
        """
        # All state is already set in __init__; this is a no-op hook
        # subclasses can override for one-time setup that must happen
        # outside the constructor (e.g. opening files). Kept as an
        # explicit method so the lifecycle reads symmetrically with
        # :meth:`close`.
        return None

    async def close(self) -> None:
        """Tear down the session and close the client. Idempotent."""
        client = self._client
        sid = self._session_id
        self._client = None
        self._session_id = None
        if client is None:
            return
        if sid is not None:
            try:
                await client.delete_session(sid)
            except Exception as exc:  # noqa: BLE001 — teardown must not raise
                logger.debug(
                    "agent.session_delete_failed",
                    agent=self._tag,
                    session_id=sid,
                    error=str(exc),
                )
        try:
            await client.aclose()
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "agent.client_close_failed",
                agent=self._tag,
                error=str(exc),
            )

    async def __aenter__(self) -> Self:
        await self.open()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def rotate_session(self) -> None:
        """Drop the current OpenCode session so the next send opens a new one.

        Typically called at bead boundaries — within a single bead the
        session is held to keep context warm across implement/fix or
        review rounds. Also clears failed-binding stickiness so a
        transient blip earlier in the run doesn't permanently rule out
        a provider. ``_validated_bindings`` is intentionally preserved:
        the live ``/provider`` snapshot doesn't change between beads,
        so re-validating is wasted latency.
        """
        client = self._client
        sid = self._session_id
        self._session_id = None
        self._failed_bindings.clear()
        if client is not None and sid is not None:
            try:
                await client.delete_session(sid)
            except AgentRuntimeError as exc:
                logger.debug(
                    "agent.session_rotate_delete_failed",
                    agent=self._tag,
                    error=str(exc),
                )

    @property
    def last_cost_record(self) -> CostRecord | None:
        return self._last_cost_record

    @property
    def tag(self) -> str:
        return self._tag

    # ------------------------------------------------------------------
    # Send paths
    # ------------------------------------------------------------------

    async def _send_structured(
        self,
        prompt: str,
        *,
        schema: type[BaseModel] | None = None,
        timeout: float = DEFAULT_STRUCTURED_TIMEOUT_SECONDS,
        system: str | None = None,
        agent: str | None = None,
    ) -> BaseModel:
        """Send a prompt and return a typed payload validated against ``schema``.

        ``schema`` defaults to the agent's :attr:`result_model` (or the
        per-instance override passed to ``__init__``).

        Raises:
            RuntimeAuthError, RuntimeModelNotFoundError,
            RuntimeStructuredOutputError, RuntimeContextOverflowError,
            AgentRuntimeError: When the runtime classifies a server-side failure.
            AgentPayloadValidationError: When the structured payload came
                back but didn't match ``schema``.
            RuntimeProtocolError: When the server returned an empty 200
                with no event explaining why (Landmine 2).
        """
        target_schema = schema or self._effective_result_model()
        client, session_id = await self._ensure_session()
        format_block = {
            "type": "json_schema",
            "schema": target_schema.model_json_schema(),
        }

        def _validate(result: SendResult) -> None:
            # Run inside each cascade attempt so a Pydantic-rejected
            # payload counts as a binding failure.
            self._coerce_payload(result, target_schema)

        result = await self._send_with_model(
            client,
            session_id,
            prompt,
            format=format_block,
            timeout=timeout,
            system=system,
            agent=self._resolve_opencode_agent(agent),
            validate=_validate,
        )
        return self._coerce_payload(result, target_schema)

    async def _send_text(
        self,
        prompt: str,
        *,
        timeout: float = DEFAULT_TEXT_TIMEOUT_SECONDS,
        system: str | None = None,
        agent: str | None = None,
    ) -> str:
        """Send a prompt and return the assistant's plain-text response."""
        client, session_id = await self._ensure_session()
        result = await self._send_with_model(
            client,
            session_id,
            prompt,
            format=None,
            timeout=timeout,
            system=system,
            agent=self._resolve_opencode_agent(agent),
        )
        return result.text

    # ------------------------------------------------------------------
    # Schema / persona resolution
    # ------------------------------------------------------------------

    def _effective_result_model(self) -> type[BaseModel]:
        return self._result_model_instance or self.result_model

    def _resolve_opencode_agent(self, override: str | None) -> str | None:
        """Pick the OpenCode agent label to forward in the message body.

        Per-call ``agent=`` argument wins; then per-instance value
        passed to ``__init__``; then the class-level :attr:`opencode_agent`.
        Returns ``None`` to leave OpenCode using its server default
        agent.
        """
        if override is not None:
            return override
        if self._opencode_agent_instance is not None:
            return self._opencode_agent_instance
        return self.opencode_agent

    # ------------------------------------------------------------------
    # Session / client lifecycle (lazy)
    # ------------------------------------------------------------------

    async def _ensure_session(self) -> tuple[OpenCodeClient, str]:
        """Build the per-agent client + open a session on first use."""
        client = self._client
        if client is None:
            client = self._build_client()
            self._client = client
        sid = self._session_id
        if sid is None:
            sid = await self._create_session(client)
            self._session_id = sid
        return client, sid

    def _build_client(self) -> OpenCodeClient:
        """Create the per-agent :class:`OpenCodeClient`.

        Tests inject a fake by passing ``client_factory=`` at construction
        — no subclassing required. The default factory builds a real
        client against the agent's :class:`OpenCodeServerHandle`.
        """
        if self._client_factory is not None:
            return self._client_factory()
        return OpenCodeClient(
            base_url=self._handle.base_url,
            password=self._handle.password,
        )

    async def _create_session(self, client: OpenCodeClient) -> str:
        """Open a new OpenCode session.

        Default: titles the session after the agent's tag. Subclasses
        can override to set per-session defaults.
        """
        return await client.create_session(title=self._tag)

    async def _send_with_model(
        self,
        client: OpenCodeClient,
        session_id: str,
        prompt: str,
        *,
        format: dict[str, Any] | None,
        timeout: float,
        system: str | None,
        agent: str | None = None,
        validate: Callable[[SendResult], None] | None = None,
    ) -> SendResult:
        """Send the prompt, falling over to lower-tier bindings on failure.

        Picks bindings from the agent's tier (via :func:`resolve_tier`)
        with explicit ``StepConfig.provider/model_id`` taking priority
        when set. Validates each binding against ``GET /provider`` once
        before its first use, then caches.

        On a cascadable error (auth / model-not-found / transient /
        structured-output) the next binding in the tier is tried. On
        success the binding is "sticky" — subsequent sends on this
        agent reuse it without re-traversing the tier from the top.

        Args:
            validate: Optional caller-supplied hook invoked synchronously
                inside the cascade after each successful HTTP send. When
                it raises a :class:`RuntimeStructuredOutputError`
                subclass (e.g. :class:`AgentPayloadValidationError`),
                the cascade treats the binding as failed and falls over
                to the next one.

        Records cost telemetry from each successful send via
        :func:`cost_record_from_send`; callers can inspect
        :attr:`last_cost_record` for the most recent record.
        """
        bindings = self._resolve_cascade_bindings()
        if not bindings:
            # No tier resolved — let OpenCode use its server default.
            result = await client.send_with_event_watch(
                session_id,
                prompt,
                model=None,
                agent=agent,
                format=format,
                system=system,
                timeout=timeout,
            )
            if validate is not None:
                validate(result)
            self._last_cost_record = cost_record_from_send(result)
            self._record_cost(result)
            return result

        async def _send(binding: ProviderModel) -> SendResult:
            if binding not in self._validated_bindings:
                await validate_model_id(client, binding.provider_id, binding.model_id)
                self._validated_bindings.add(binding)

            # Retry transient errors on the SAME binding before letting
            # the cascade fall over. A 503 / rate-limit blip shouldn't
            # be enough to permanently mark this provider as failed —
            # one retry round usually rides through a brief outage.
            result: SendResult | None = None
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type(RuntimeTransientError),
                stop=stop_after_attempt(TRANSIENT_RETRY_ATTEMPTS),
                wait=wait_exponential(
                    multiplier=1,
                    min=TRANSIENT_RETRY_WAIT_MIN_SECONDS,
                    max=TRANSIENT_RETRY_WAIT_MAX_SECONDS,
                ),
                reraise=True,
            ):
                with attempt:
                    result = await client.send_with_event_watch(
                        session_id,
                        prompt,
                        model=binding.to_dict(),
                        agent=agent,
                        format=format,
                        system=system,
                        timeout=timeout,
                    )
                    if validate is not None:
                        validate(result)
            # reraise=True guarantees an exception propagated if every
            # attempt failed; if we reach here, the last attempt set ``result``.
            assert result is not None
            return result

        tier = Tier(name=self._tier_name_or_inline(), bindings=tuple(bindings))
        outcome: CascadeOutcome = await cascade_send(
            tier,
            _send,
            skip=set(self._failed_bindings),
        )
        for failed_binding, _why in outcome.failed_bindings:
            self._failed_bindings.add(failed_binding)
        self._last_cost_record = cost_record_from_send(outcome.result)
        self._record_cost(outcome.result, binding=outcome.binding)
        return outcome.result

    def _resolve_cascade_bindings(self) -> list[ProviderModel]:
        """Build the ordered list of bindings the cascade should try.

        Priority:

        1. An explicit ``StepConfig.provider+model_id`` pair (single
           binding, no fallback — explicit user override).
        2. The configured tier for ``self.provider_tier`` (default
           bindings unless overridden in ``self._tier_overrides``).
        3. Empty — server default.
        """
        cfg = self._step_config
        if cfg is not None and cfg.provider and cfg.model_id:
            return [ProviderModel(cfg.provider, cfg.model_id)]
        tier_name = self.provider_tier
        if tier_name is None:
            return []
        try:
            tier = resolve_tier(tier_name, override=self._tier_overrides)
        except KeyError:
            logger.debug(
                "agent.unknown_tier_falling_back_to_default",
                agent=self._tag,
                tier=tier_name,
            )
            return []
        return list(tier.bindings)

    def _tier_name_or_inline(self) -> str:
        """Return a human-meaningful tier name for log/telemetry use."""
        return self.provider_tier or "inline"

    def _record_cost(
        self,
        result: SendResult,
        *,
        binding: ProviderModel | None = None,
    ) -> None:
        """Emit a structured-log row + (when configured) JSONL append."""
        record = self._last_cost_record
        if record is None:
            return
        from maverick.agents.context import current_tags

        tags = current_tags()
        logger.info(
            "agent.cost",
            agent=self._tag,
            tier=self._tier_name_or_inline(),
            binding=binding.label if binding else None,
            **tags,
            **record.to_dict(),
        )
        sink = self._cost_sink
        if sink is None:
            return
        from maverick.runway.models import CostEntry

        entry = CostEntry(
            actor=self._tag,
            tier=self._tier_name_or_inline(),
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
        # Schedule the append asynchronously — the send path must not
        # block on JSONL I/O. Failures bubble to the structlog only.
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

    def _coerce_payload(self, result: SendResult, schema: type[BaseModel]) -> BaseModel:
        """Validate the unwrapped structured payload against ``schema``."""
        if result.structured is None:
            raise RuntimeStructuredOutputError(
                "OpenCode response had no structured payload "
                "(format=json_schema was requested but model emitted text only)",
                body=result.message,
            )
        try:
            return schema.model_validate(result.structured)
        except ValidationError as exc:
            raise AgentPayloadValidationError(
                f"structured payload failed {schema.__name__} validation: {exc}",
                body=result.structured,
            ) from exc


__all__ = [
    "DEFAULT_STRUCTURED_TIMEOUT_SECONDS",
    "DEFAULT_TEXT_TIMEOUT_SECONDS",
    "Agent",
    "AgentPayloadValidationError",
]
