"""``OpenCodeAgentMixin`` — replacement for :class:`AgenticActorMixin`.

Each agentic actor declares **one** Pydantic model (its result type)
instead of an MCP tool-schema list. The mixin converts that into
``format=json_schema`` for OpenCode's synthesized ``StructuredOutput``
tool, sends the prompt via :meth:`OpenCodeClient.send_with_event_watch`
(Landmine 2 mitigation), unwraps the envelope (Landmine 3), and
validates with the declared model.

Subclasses no longer:

* Register MCP tools.
* Implement ``on_tool_call``.
* Hold a per-actor ACP subprocess.
* Care about HTTP error surfacing — the mixin raises classified
  :class:`OpenCodeError` subclasses for every observed failure mode.

Subclasses still own:

* Their prompt-building (HOW).
* Session rotation (``new_bead``).
* The mapping from typed payload → supervisor RPC.

Each actor gets its own :class:`OpenCodeClient` — connection state is
per-instance, the OpenCode server is shared per actor pool. The pool's
:func:`actor_pool` context manager spawns the server when called with
``with_opencode=True`` and registers the handle so the mixin can look
it up by ``self.address``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar

import xoscar as xo
from pydantic import BaseModel, ValidationError

from maverick.logging import get_logger
from maverick.runtime.opencode import (
    CascadeOutcome,
    CostRecord,
    CostSink,
    OpenCodeClient,
    OpenCodeError,
    OpenCodeStructuredOutputError,
    ProviderModel,
    SendResult,
    Tier,
    cascade_send,
    cost_record_from_send,
    cost_sink_for,
    opencode_handle_for,
    resolve_tier,
    tier_overrides_for,
    validate_model_id,
)

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)


DEFAULT_STRUCTURED_TIMEOUT_SECONDS = 600.0
DEFAULT_TEXT_TIMEOUT_SECONDS = 600.0


class OpenCodePayloadValidationError(OpenCodeError):
    """Server returned a structured payload that didn't match the actor's model.

    Distinct from :class:`OpenCodeStructuredOutputError` (which the server
    raises when it gives up forcing the model to call StructuredOutput) —
    this fires when the server *did* return a payload but our Pydantic
    model rejected it. Almost always a prompt/schema-shape mismatch worth
    reporting upstream.
    """


class OpenCodeAgentMixin:
    """Base for actors that own one OpenCode session and one result model.

    Subclass requirements:

    * ``result_model: ClassVar[type[BaseModel]]`` — the Pydantic model the
      mixin validates structured-output payloads against.
    * Set ``self._cwd`` (str or Path) and ``self._step_config`` (StepConfig
      or None) in ``__init__``. Those drive prompt-time provider/model
      selection.
    * Call ``super().__init__()`` from your own ``__init__``.

    Lifecycle:

    * ``__post_create__`` initialises lazy state — no network calls.
    * First :meth:`_send_structured` (or :meth:`_send_text`) call lazily
      builds the per-actor :class:`OpenCodeClient` and creates a session.
    * :meth:`new_bead` rotates the session for a fresh context.
    * ``__pre_destroy__`` deletes the session and closes the client.
    """

    # Subclasses override.
    result_model: ClassVar[type[BaseModel]] = BaseModel

    # Optional: tier name for the Phase 5 provider tier system. Phase 2
    # ignores it; subclasses may set it now and it'll start being used
    # later without a code change.
    provider_tier: ClassVar[str | None] = None

    # Per-instance lazy state (set in __post_create__ or first send).
    _client: OpenCodeClient | None = None
    _session_id: str | None = None

    # Subclasses are expected to set these in __init__.
    _cwd: str | None = None
    _step_config: StepConfig | None = None

    # Logging tag — defaults to the class name when not set.
    _actor_tag: str | None = None

    # Tier-cascade state (initialised in ``_opencode_post_create``).
    _validated_bindings: set[ProviderModel]
    _failed_bindings: set[ProviderModel]
    _last_cost_record: CostRecord | None
    # Optional override for the per-actor tier table — populated from
    # config in :meth:`_opencode_post_create` when the actor's pool
    # supplies one.
    _tier_overrides: dict[str, Tier] | None = None
    # Pool-scoped cost sink (set lazily on first send). When None, the
    # mixin falls back to structured-log emission only.
    _cost_sink: CostSink | None = None
    _cost_sink_resolved: bool = False
    # Optional bead identifier — set by subclasses when the workflow
    # context knows which bead a send belongs to. Empty otherwise.
    _current_bead_id: str = ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _opencode_post_create(self) -> None:
        """Initialise lazy state. Call from your ``__post_create__``.

        Does not contact OpenCode — the actual session is opened on the
        first send. This keeps actor creation cheap and lets workflows
        stand up actor pools without paying connection cost upfront.
        """
        self._client = None
        self._session_id = None
        self._validated_bindings = set()
        self._failed_bindings = set()
        self._last_cost_record = None
        self._cost_sink = None
        self._cost_sink_resolved = False
        self._current_bead_id = ""
        if self._actor_tag is None:
            uid = getattr(self, "uid", b"?")
            uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
            self._actor_tag = f"{type(self).__name__}[{uid_str}]"

    async def _opencode_pre_destroy(self) -> None:
        """Tear down the session and close the client. Call from
        ``__pre_destroy__``."""
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
                    "opencode_actor.session_delete_failed",
                    actor=self._actor_tag,
                    session_id=sid,
                    error=str(exc),
                )
        try:
            await client.aclose()
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "opencode_actor.client_close_failed",
                actor=self._actor_tag,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Subclass surface
    # ------------------------------------------------------------------

    async def _rotate_session(self) -> None:
        """Drop the current OpenCode session so the next send opens a new one.

        Subclasses' ``new_bead`` typically calls this. Kept as a private
        helper so subclasses can declare their own ``new_bead`` signature
        (the supervisor calls them with concrete request types) without
        fighting an incompatible mixin signature.
        """
        client = self._client
        sid = self._session_id
        self._session_id = None
        if client is not None and sid is not None:
            try:
                await client.delete_session(sid)
            except OpenCodeError as exc:
                logger.debug(
                    "opencode_actor.session_rotate_delete_failed",
                    actor=self._actor_tag,
                    error=str(exc),
                )

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
    ) -> BaseModel:
        """Send a prompt and return a typed payload validated against
        ``schema`` (defaults to ``self.result_model``).

        Raises:
            OpenCodeAuthError, OpenCodeModelNotFoundError,
            OpenCodeStructuredOutputError, OpenCodeContextOverflowError,
            OpenCodeError: When the runtime classifies a server-side failure.
            OpenCodePayloadValidationError: When the structured payload
                came back but didn't match ``schema``.
            OpenCodeProtocolError: When the server returned an empty 200
                with no event explaining why (Landmine 2).
        """
        target_schema = schema or self.result_model
        client, session_id = await self._ensure_session()
        format_block = {
            "type": "json_schema",
            "schema": target_schema.model_json_schema(),
        }
        result = await self._send_with_model(
            client,
            session_id,
            prompt,
            format=format_block,
            timeout=timeout,
            system=system,
        )
        return self._coerce_payload(result, target_schema)

    async def _send_text(
        self,
        prompt: str,
        *,
        timeout: float = DEFAULT_TEXT_TIMEOUT_SECONDS,
        system: str | None = None,
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
        )
        return result.text

    # ------------------------------------------------------------------
    # Session / client lifecycle (lazy)
    # ------------------------------------------------------------------

    async def _ensure_session(self) -> tuple[OpenCodeClient, str]:
        """Build the per-actor client + open a session on first use."""
        client = self._client
        if client is None:
            client = await self._build_client()
            self._client = client
        sid = self._session_id
        if sid is None:
            sid = await self._create_session(client)
            self._session_id = sid
        return client, sid

    async def _build_client(self) -> OpenCodeClient:
        """Create the per-actor :class:`OpenCodeClient`.

        Also picks up the pool-scoped tier overrides (if any) so the
        cascade resolver sees user config without each actor reaching
        into ``MaverickConfig`` itself.
        """
        pool_address: str = self.address  # type: ignore[attr-defined]
        handle = opencode_handle_for(pool_address)
        if self._tier_overrides is None:
            self._tier_overrides = tier_overrides_for(pool_address)
        return OpenCodeClient(base_url=handle.base_url, password=handle.password)

    async def _create_session(self, client: OpenCodeClient) -> str:
        """Open a new OpenCode session.

        Default: titles the session after the actor, leaves model selection
        to the per-message ``send`` call. Subclasses can override to set
        per-session defaults.
        """
        title = self._actor_tag or type(self).__name__
        return await client.create_session(title=title)

    async def _send_with_model(
        self,
        client: OpenCodeClient,
        session_id: str,
        prompt: str,
        *,
        format: dict[str, Any] | None,
        timeout: float,
        system: str | None,
    ) -> SendResult:
        """Send the prompt, falling over to lower-tier bindings on failure.

        Picks bindings from the actor's tier (via :func:`resolve_tier`)
        with explicit ``StepConfig.provider/model_id`` taking priority
        when set. Validates each binding against ``GET /provider`` once
        before its first use, then caches.

        On a cascadable error (auth / model-not-found / transient /
        structured-output) the next binding in the tier is tried. On
        success the binding is "sticky" — subsequent sends on this
        actor reuse it without re-traversing the tier from the top.

        Records cost telemetry from each successful send via
        :func:`cost_record_from_send`; callers can inspect
        ``self._last_cost_record`` for the most recent record.
        """
        bindings = self._resolve_cascade_bindings()
        if not bindings:
            # No tier resolved — let OpenCode use its server default.
            result = await client.send_with_event_watch(
                session_id,
                prompt,
                model=None,
                format=format,
                system=system,
                timeout=timeout,
            )
            self._last_cost_record = cost_record_from_send(result)
            self._record_cost(result)
            return result

        async def _send(binding: ProviderModel) -> SendResult:
            if binding not in self._validated_bindings:
                await validate_model_id(client, binding.provider_id, binding.model_id)
                self._validated_bindings.add(binding)
            return await client.send_with_event_watch(
                session_id,
                prompt,
                model=binding.to_dict(),
                format=format,
                system=system,
                timeout=timeout,
            )

        tier = Tier(name=self._tier_name_or_inline(), bindings=tuple(bindings))
        outcome: CascadeOutcome = await cascade_send(
            tier,
            _send,
            skip=set(self._failed_bindings),
        )
        # Mark every cascade-failed binding so future sends skip them
        # without paying the latency to retry.
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
           bindings unless overridden in :attr:`_tier_overrides`).
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
                "opencode_actor.unknown_tier_falling_back_to_default",
                actor=self._actor_tag,
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
        """Emit a structured-log row + (when configured) JSONL append.

        Always logs at info level. When a pool-scoped cost sink is
        registered (typically by the workflow's
        ``register_cost_sink(address, ...)`` call), also schedules a
        :class:`CostEntry` append against the sink — fire-and-forget so
        the send path is never blocked on I/O.
        """
        record = self._last_cost_record
        if record is None:
            return
        logger.info(
            "opencode_actor.cost",
            actor=self._actor_tag,
            tier=self._tier_name_or_inline(),
            binding=binding.label if binding else None,
            **record.to_dict(),
        )
        sink = self._resolve_cost_sink()
        if sink is None:
            return
        from maverick.runway.models import CostEntry

        entry = CostEntry(
            actor=self._actor_tag or type(self).__name__,
            tier=self._tier_name_or_inline(),
            provider_id=record.provider_id,
            model_id=record.model_id,
            cost_usd=record.cost_usd,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            cache_read_tokens=record.cache_read_tokens,
            cache_write_tokens=record.cache_write_tokens,
            finish=record.finish,
            bead_id=self._current_bead_id,
        )
        # Schedule the append asynchronously — the send path must not
        # block on JSONL I/O. Failures bubble to the structlog only.
        asyncio.create_task(self._flush_cost_entry(sink, entry))

    def _resolve_cost_sink(self) -> CostSink | None:
        """Lazily look up the pool-scoped cost sink (cached per actor)."""
        if self._cost_sink_resolved:
            return self._cost_sink
        try:
            pool_address: str = self.address  # type: ignore[attr-defined]
        except AttributeError:
            self._cost_sink_resolved = True
            return None
        self._cost_sink = cost_sink_for(pool_address)
        self._cost_sink_resolved = True
        return self._cost_sink

    async def _flush_cost_entry(self, sink: CostSink, entry: Any) -> None:
        """Best-effort delivery to the cost sink. Never raises."""
        try:
            await sink(entry)
        except Exception as exc:  # noqa: BLE001 — sink failures must not break sends
            logger.debug(
                "opencode_actor.cost_sink_failed",
                actor=self._actor_tag,
                error=str(exc)[:200],
            )

    def _coerce_payload(self, result: SendResult, schema: type[BaseModel]) -> BaseModel:
        """Validate the unwrapped structured payload against ``schema``."""
        if result.structured is None:
            # The send completed without a StructuredOutput tool call.
            # OpenCode treats this as a StructuredOutputError when it
            # detects it, so this branch is mostly a safety net for
            # well-formed but content-empty replies.
            raise OpenCodeStructuredOutputError(
                "OpenCode response had no structured payload "
                "(format=json_schema was requested but model emitted text only)",
                body=result.message,
            )
        try:
            return schema.model_validate(result.structured)
        except ValidationError as exc:
            raise OpenCodePayloadValidationError(
                f"structured payload failed {schema.__name__} validation: {exc}",
                body=result.structured,
            ) from exc


def text_of(result: SendResult) -> str:
    """Convenience: return the plain-text portion of a :class:`SendResult`."""
    return result.text


def info_cost(result: SendResult) -> dict[str, Any]:
    """Extract usage / cost info from a :class:`SendResult` for telemetry."""
    info = result.info or {}
    return {
        "providerID": info.get("providerID"),
        "modelID": info.get("modelID"),
        "cost": info.get("cost"),
        "tokens": info.get("tokens"),
        "finish": info.get("finish"),
    }


# Workflow-level helpers exposed for actor implementations.
__all__ = [
    "DEFAULT_STRUCTURED_TIMEOUT_SECONDS",
    "DEFAULT_TEXT_TIMEOUT_SECONDS",
    "OpenCodeAgentMixin",
    "OpenCodePayloadValidationError",
    "info_cost",
    "text_of",
]


# Make `xo` reachable for static analysis on pieces that look at the
# mixin in isolation (the actual runtime depends on subclasses pulling
# `xo.Actor` into their MRO).
_ = xo
