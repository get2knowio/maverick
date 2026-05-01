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

from typing import TYPE_CHECKING, Any, ClassVar

import xoscar as xo
from pydantic import BaseModel, ValidationError

from maverick.logging import get_logger
from maverick.runtime.opencode import (
    OpenCodeClient,
    OpenCodeError,
    OpenCodeStructuredOutputError,
    SendResult,
    opencode_handle_for,
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
    _opencode_provider_id: str | None = None
    _opencode_model_id: str | None = None
    _model_validated: bool = False

    # Subclasses are expected to set these in __init__.
    _cwd: str | None = None
    _step_config: StepConfig | None = None

    # Logging tag — defaults to the class name when not set.
    _actor_tag: str | None = None

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
        self._model_validated = False
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

        Looks up the pool-scoped server handle via :func:`opencode_handle_for`.
        """
        pool_address: str = self.address  # type: ignore[attr-defined]
        handle = opencode_handle_for(pool_address)
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
        """Common path for both structured and text sends."""
        provider_id, model_id = self._resolve_model_binding()
        if provider_id and model_id and not self._model_validated:
            await validate_model_id(client, provider_id, model_id)
            self._model_validated = True

        model_block: dict[str, str] | None = None
        if provider_id and model_id:
            model_block = {"providerID": provider_id, "modelID": model_id}

        return await client.send_with_event_watch(
            session_id,
            prompt,
            model=model_block,
            format=format,
            system=system,
            timeout=timeout,
        )

    def _resolve_model_binding(self) -> tuple[str | None, str | None]:
        """Pull (provider_id, model_id) from this actor's :class:`StepConfig`.

        Returns ``(None, None)`` when neither is set; OpenCode then falls
        back to its server-side default. Phase 5 will override this with
        the tier resolver.
        """
        cfg = self._step_config
        if cfg is None:
            return None, None
        return cfg.provider, cfg.model_id

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
