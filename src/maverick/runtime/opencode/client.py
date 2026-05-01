"""Async HTTP client for an OpenCode local server.

Adapted from the spike client at ``/tmp/opencode-spike/opencode_client.py``
with maverick conventions:

* Logging via :func:`maverick.logging.get_logger`.
* Retries via :class:`tenacity.AsyncRetrying` for transient HTTP failures.
* Errors raised as the proper :mod:`.errors` subclass so callers can react.
* The :func:`structured_of` helper preserves the spike's
  ``_unwrap_envelope`` heuristic — the only known mitigation for Landmine 3
  (Claude wraps tool args in single-key envelopes ~30% of the time).
* :meth:`OpenCodeClient.send_with_event_watch` joins the synchronous send
  call to a parallel event-drain so silent failures (Landmine 2) surface
  as exceptions, not as empty 200-bodies.

Endpoints discovered empirically from ``/doc`` + ``opencode.ai/docs/server``
+ SDK source. The ``/doc`` OpenAPI spec is incomplete; the canonical
reference is the docs page.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Self

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from maverick.logging import get_logger
from maverick.runtime.opencode.errors import (
    OpenCodeAuthError,
    OpenCodeContextOverflowError,
    OpenCodeError,
    OpenCodeModelNotFoundError,
    OpenCodeProtocolError,
    OpenCodeStructuredOutputError,
    OpenCodeTransientError,
)

logger = get_logger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:4096"
DEFAULT_TIMEOUT = 600.0


_ENVELOPE_KEYS = (
    "input",
    "output",
    "parameter",
    "parameters",
    "arguments",
    "content",
    "data",
    "result",
    "value",
)


def _unwrap_envelope(payload: Any) -> Any:
    """Strip a single-key wrapper that some models emit around tool args.

    Claude (via OpenCode's ``StructuredOutput`` tool) sometimes returns
    the payload under a single envelope key like ``input``, ``parameter``,
    or ``content``. If we see that exact shape, unwrap one level. If
    ``content`` holds JSON-as-string, decode that.

    See ``ASSESSMENT.md`` Landmine 3 for the empirical evidence.
    """
    if not isinstance(payload, dict):
        return payload
    if len(payload) == 1:
        ((k, v),) = payload.items()
        if k in _ENVELOPE_KEYS:
            if isinstance(v, str):
                try:
                    parsed = json.loads(v)
                    return _unwrap_envelope(parsed)
                except json.JSONDecodeError:
                    return payload
            return _unwrap_envelope(v)
    return payload


def text_of(message: dict[str, Any]) -> str:
    """Concatenate text-part content from a ``/session/.../message`` response."""
    parts = message.get("parts", []) or []
    out: list[str] = []
    for p in parts:
        if p.get("type") == "text":
            out.append(p.get("text", ""))
    return "".join(out).strip()


def structured_of(message: dict[str, Any], *, unwrap: bool = True) -> Any:
    """Extract the structured-output payload from a message response.

    OpenCode synthesizes a ``StructuredOutput`` tool that the model is
    forced to call when ``format=json_schema``. The validated payload
    appears at ``info.structured`` and as the tool-call's ``state.input``.
    Set ``unwrap=False`` to inspect the raw envelope (e.g. for diagnostics).
    """
    info = message.get("info", {}) or {}
    raw: Any = None
    if "structured" in info:
        raw = info["structured"]
    else:
        for p in message.get("parts", []) or []:
            if p.get("type") == "tool" and p.get("tool") == "StructuredOutput":
                state = p.get("state", {}) or {}
                raw = state.get("input")
                break
    if raw is None:
        return None
    return _unwrap_envelope(raw) if unwrap else raw


def structured_valid(message: dict[str, Any]) -> bool:
    """Whether the StructuredOutput tool call validated against the schema."""
    for p in message.get("parts", []) or []:
        if p.get("type") == "tool" and p.get("tool") == "StructuredOutput":
            state = p.get("state", {}) or {}
            md = state.get("metadata", {}) or {}
            return bool(md.get("valid"))
    return False


@dataclass(frozen=True, slots=True)
class SendResult:
    """Typed result from :meth:`OpenCodeClient.send_with_event_watch`.

    Attributes:
        message: The full ``/message`` response payload.
        text: Concatenated assistant text (post any tool-call output).
        structured: Schema-shaped object (envelope-unwrapped) when
            ``format`` was a JSON schema; ``None`` otherwise.
        valid: Whether the StructuredOutput tool reported schema validation.
        info: Shorthand for ``message.get("info", {})``.
    """

    message: dict[str, Any]
    text: str
    structured: Any
    valid: bool
    info: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Error classification helpers
# ---------------------------------------------------------------------------


_TRANSIENT_STATUSES = frozenset({502, 503, 504, 408, 429})


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except Exception:  # noqa: BLE001 — diagnostic fallback
        return r.text[:500]


def classify_session_error(error_obj: Any) -> OpenCodeError:
    """Map an OpenCode ``session.error`` event payload to an exception.

    Args:
        error_obj: Either the full ``session.error`` event or its
            ``properties.error`` sub-dict. Tolerates both for callers.
    """
    if not isinstance(error_obj, dict):
        return OpenCodeError(f"unrecognized session error: {error_obj!r}")
    # Allow callers to pass the whole event.
    if "properties" in error_obj and "error" in error_obj.get("properties", {}):
        error_obj = error_obj["properties"]["error"]
    name = error_obj.get("name") or ""
    data = error_obj.get("data") or {}
    msg = data.get("message") if isinstance(data, dict) else None
    body = error_obj
    text = msg or name or "session.error"
    lname = name.lower()
    if "providermodelnotfound" in lname or "modelnotfound" in lname:
        return OpenCodeModelNotFoundError(text, body=body)
    if "providerauth" in lname or "authentication" in lname or "unauthor" in lname:
        return OpenCodeAuthError(text, body=body)
    if "contextoverflow" in lname:
        return OpenCodeContextOverflowError(text, body=body)
    if "structuredoutput" in lname:
        retries = 0
        if isinstance(data, dict):
            retries = int(data.get("retries", 0) or 0)
        return OpenCodeStructuredOutputError(text, body=body, retries=retries)
    return OpenCodeError(text, body=body)


def _classify_http_error(response: httpx.Response) -> OpenCodeError:
    body = _safe_json(response)
    status = response.status_code
    name = ""
    message = ""
    if isinstance(body, dict):
        name = (body.get("name") or body.get("error", {}).get("name") or "") if body else ""
        data = body.get("data") if "data" in body else body.get("error", {}).get("data", {})
        if isinstance(data, dict):
            message = data.get("message", "") or ""
    text = message or name or f"HTTP {status}"
    lname = name.lower()
    if "structuredoutput" in lname:
        retries = 0
        if isinstance(body, dict):
            data = body.get("data") if "data" in body else body.get("error", {}).get("data", {})
            if isinstance(data, dict):
                retries = int(data.get("retries", 0) or 0)
        return OpenCodeStructuredOutputError(text, status=status, body=body, retries=retries)
    if "providermodelnotfound" in lname or "modelnotfound" in lname:
        return OpenCodeModelNotFoundError(text, status=status, body=body)
    if "providerauth" in lname or "authentication" in lname or status == 401:
        return OpenCodeAuthError(text, status=status, body=body)
    if status in _TRANSIENT_STATUSES:
        return OpenCodeTransientError(text, status=status, body=body)
    return OpenCodeError(text, status=status, body=body)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class OpenCodeClient:
    """Async HTTP client for an OpenCode server.

    All methods are async. The client owns one :class:`httpx.AsyncClient`
    per instance — call :meth:`aclose` (or use as an async context manager)
    to release it.

    Args:
        base_url: Server base URL (default: ``http://127.0.0.1:4096``).
        timeout: Default per-request timeout (seconds).
        password: Optional ``OPENCODE_SERVER_PASSWORD``. Sent as HTTP
            Basic auth with username ``opencode`` (the auth scheme the
            server enforces when the env var is set).
        max_retry_attempts: Tenacity retry attempts for transient HTTP
            failures (5xx, network blip). Send paths still raise
            structured errors immediately for the non-transient cases.
    """

    BASIC_AUTH_USERNAME = "opencode"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        password: str | None = None,
        max_retry_attempts: int = 3,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._password = password
        self._max_retry_attempts = max_retry_attempts
        auth = httpx.BasicAuth(self.BASIC_AUTH_USERNAME, password) if password else None
        self._http = httpx.AsyncClient(
            base_url=self._base,
            timeout=timeout,
            auth=auth,
        )
        # Per-session defaults (model/agent/system) so callers can stash
        # values once and reuse them across sends.
        self._session_defaults: dict[str, dict[str, Any]] = {}

    @property
    def base_url(self) -> str:
        return self._base

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    # ---- core ----------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        """Probe ``GET /global/health``."""
        r = await self._http.get("/global/health")
        if r.status_code >= 400:
            raise _classify_http_error(r)
        return r.json()

    async def list_providers(self) -> dict[str, Any]:
        """Return ``GET /provider`` — connected providers + models."""
        r = await self._http.get("/provider")
        if r.status_code >= 400:
            raise _classify_http_error(r)
        return r.json()

    async def list_sessions(self) -> list[dict[str, Any]]:
        r = await self._http.get("/session")
        if r.status_code >= 400:
            raise _classify_http_error(r)
        return r.json()

    # ---- sessions ------------------------------------------------------

    async def create_session(
        self,
        *,
        title: str | None = None,
        parent_id: str | None = None,
        agent: str | None = None,
        model: dict[str, str] | None = None,
        system: str | None = None,
    ) -> str:
        """Create a session and return its id.

        ``agent``, ``model``, and ``system`` are not part of session
        creation in OpenCode — they are per-message. Stashed here as
        defaults that subsequent ``send_*`` calls inherit when not
        overridden inline.
        """
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if parent_id is not None:
            body["parentID"] = parent_id
        r = await self._http.post("/session", json=body)
        if r.status_code >= 400:
            raise _classify_http_error(r)
        sid: str = r.json()["id"]
        self._session_defaults[sid] = {
            "agent": agent,
            "model": model,
            "system": system,
        }
        logger.debug("opencode.session_created", session_id=sid, title=title)
        return sid

    async def delete_session(self, session_id: str) -> bool:
        r = await self._http.delete(f"/session/{session_id}")
        if r.status_code >= 400:
            raise _classify_http_error(r)
        self._session_defaults.pop(session_id, None)
        return bool(r.json())

    # ---- messages ------------------------------------------------------

    async def send_message(
        self,
        session_id: str,
        content: str,
        *,
        model: dict[str, str] | None = None,
        agent: str | None = None,
        format: dict[str, Any] | None = None,
        system: str | None = None,
        tools: dict[str, bool] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Synchronous prompt → assistant message.

        Returns the message envelope ``{"info": ..., "parts": [...]}``.
        On HTTP 200 with empty body (Landmine 2 — silent failure),
        returns a sentinel ``{"info": {}, "parts": [], "_empty": True}``.
        Callers that care about silent failures should use
        :meth:`send_with_event_watch` instead, which classifies them
        via the event stream.
        """
        body = self._build_send_body(
            session_id,
            content,
            model=model,
            agent=agent,
            format=format,
            system=system,
            tools=tools,
        )
        kwargs: dict[str, Any] = {"json": body}
        if timeout is not None:
            kwargs["timeout"] = timeout

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_retry_attempts),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            retry=retry_if_exception_type((OpenCodeTransientError, httpx.TransportError)),
            reraise=True,
        ):
            with attempt:
                r = await self._http.post(f"/session/{session_id}/message", **kwargs)
                if r.status_code >= 400:
                    raise _classify_http_error(r)
                if not r.content:
                    return {"info": {}, "parts": [], "_empty": True}
                return r.json()  # type: ignore[no-any-return]
        # Unreachable — AsyncRetrying with reraise=True raises before exit.
        raise OpenCodeError("send_message exhausted retries without a result")

    async def send_message_async(
        self,
        session_id: str,
        content: str,
        *,
        model: dict[str, str] | None = None,
        agent: str | None = None,
        format: dict[str, Any] | None = None,
        system: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Fire-and-forget variant. **Risky** — see Landmine 1.

        A bad ``modelID`` here crashes the server in the background and
        leaves the message in the on-disk queue, producing a permanent
        crash loop. Always validate the model first via
        :func:`maverick.runtime.opencode.validation.validate_model_id`.
        Prefer :meth:`send_message` for load-bearing work.
        """
        body = self._build_send_body(
            session_id,
            content,
            model=model,
            agent=agent,
            format=format,
            system=system,
        )
        kwargs: dict[str, Any] = {"json": body}
        if timeout is not None:
            kwargs["timeout"] = timeout
        r = await self._http.post(f"/session/{session_id}/prompt_async", **kwargs)
        if r.status_code not in (200, 202, 204):
            raise _classify_http_error(r)

    def _build_send_body(
        self,
        session_id: str,
        content: str,
        *,
        model: dict[str, str] | None = None,
        agent: str | None = None,
        format: dict[str, Any] | None = None,
        system: str | None = None,
        tools: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        defaults = self._session_defaults.get(session_id, {})
        eff_model = model or defaults.get("model")
        eff_agent = agent or defaults.get("agent")
        eff_system = system if system is not None else defaults.get("system")

        body: dict[str, Any] = {"parts": [{"type": "text", "text": content}]}
        if eff_model is not None:
            body["model"] = eff_model
        if eff_agent is not None:
            body["agent"] = eff_agent
        if eff_system is not None:
            body["system"] = eff_system
        if tools is not None:
            body["tools"] = tools
        if format is not None:
            body["format"] = format
        return body

    async def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        r = await self._http.get(f"/session/{session_id}/message")
        if r.status_code >= 400:
            raise _classify_http_error(r)
        return r.json()  # type: ignore[no-any-return]

    # ---- events --------------------------------------------------------

    async def stream_events(
        self,
        session_id: str | None = None,
        *,
        timeout: float | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to ``/event`` SSE.

        Yields decoded event objects. When ``session_id`` is provided,
        only events whose ``properties.sessionID`` (or the equivalent
        nested location) matches are yielded. Connection stays open
        until cancelled or the server closes it.

        The wire format is conventional SSE (``data: <json>\\n\\n``).
        Comment / heartbeat lines are skipped.
        """
        # Use a separate client because SSE wants a long-lived stream;
        # set read=None so httpx doesn't time out the long-poll.
        auth = (
            httpx.BasicAuth(self.BASIC_AUTH_USERNAME, self._password) if self._password else None
        )
        async with (
            httpx.AsyncClient(
                base_url=self._base,
                timeout=httpx.Timeout(timeout, read=None),
                auth=auth,
            ) as http,
            http.stream("GET", "/event") as r,
        ):
            if r.status_code >= 400:
                raise _classify_http_error(r)
            async for line in r.aiter_lines():
                if not line:
                    continue
                if line.startswith(":"):  # heartbeat
                    continue
                if line.startswith("data: "):
                    payload = line[len("data: ") :]
                elif line.startswith("data:"):
                    payload = line[len("data:") :]
                else:
                    # Some configs emit raw JSON per line.
                    payload = line
                try:
                    evt = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if session_id is not None and not _event_matches_session(evt, session_id):
                    continue
                yield evt

    # ---- cancellation --------------------------------------------------

    async def cancel(self, session_id: str) -> bool:
        """Abort the in-flight prompt on ``session_id`` (~14ms typical)."""
        r = await self._http.post(f"/session/{session_id}/abort")
        if r.status_code >= 400:
            raise _classify_http_error(r)
        return bool(r.json())

    # ---- combined send + event watch (Landmine 2 mitigation) -----------

    async def send_with_event_watch(
        self,
        session_id: str,
        content: str,
        *,
        model: dict[str, str] | None = None,
        agent: str | None = None,
        format: dict[str, Any] | None = None,
        system: str | None = None,
        tools: dict[str, bool] | None = None,
        timeout: float | None = None,
    ) -> SendResult:
        """Send a prompt and watch the SSE stream for ``session.error`` in parallel.

        OpenCode's synchronous ``/message`` endpoint can return HTTP 200
        with an empty body when the model or auth is wrong (Landmine 2).
        This method joins the send call with an event-drain task that
        cancels the send and raises a structured exception when a
        ``session.error`` event arrives for ``session_id``.

        On success, returns a :class:`SendResult` carrying the parsed
        message, text, structured payload (envelope-unwrapped), and
        validation flag.

        Raises:
            OpenCodeAuthError, OpenCodeModelNotFoundError,
            OpenCodeContextOverflowError, OpenCodeStructuredOutputError,
            OpenCodeError: When the event stream surfaces an error.
            OpenCodeProtocolError: When the response was empty AND no
                error event arrived within the timeout (truly silent).
        """
        send_task = asyncio.create_task(
            self.send_message(
                session_id,
                content,
                model=model,
                agent=agent,
                format=format,
                system=system,
                tools=tools,
                timeout=timeout,
            )
        )
        watch_task = asyncio.create_task(self._watch_for_error(session_id))

        message: dict[str, Any] | None = None
        try:
            while not send_task.done():
                done, _pending = await asyncio.wait(
                    {send_task, watch_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if watch_task in done:
                    watch_exc = watch_task.exception()
                    if watch_exc is None:
                        err = watch_task.result()
                        if err is not None:
                            # Cancel the send and raise the classified error.
                            send_task.cancel()
                            await _drain(send_task)
                            raise err
                        # Watch returned None (stream closed cleanly without
                        # idle/error). Re-arm the watcher and keep waiting
                        # on the send.
                        watch_task = asyncio.create_task(self._watch_for_error(session_id))
                    else:
                        # Watcher errored (network blip on /event). Don't
                        # let that mask a successful send — log and re-arm.
                        logger.debug(
                            "opencode.event_watch_failed_continuing",
                            error=str(watch_exc)[:200],
                        )
                        watch_task = asyncio.create_task(self._watch_for_error(session_id))
            # send_task is done. Surface its result/exception.
            send_exc = send_task.exception()
            if send_exc is not None:
                raise send_exc
            message = send_task.result()
        finally:
            for t in (send_task, watch_task):
                if not t.done():
                    t.cancel()
                    await _drain(t)

        if message is None:  # defensive — flow above guarantees set
            raise OpenCodeError("send_with_event_watch: no message returned")
        if message.get("_empty"):
            raise OpenCodeProtocolError(
                "send_message returned HTTP 200 with empty body and no "
                "session.error event was observed; likely a silent "
                "model/auth failure (Landmine 2). Verify modelID via "
                "GET /provider before sending.",
                body=message,
            )
        return SendResult(
            message=message,
            text=text_of(message),
            structured=structured_of(message),
            valid=structured_valid(message),
            info=message.get("info", {}) or {},
        )

    async def _watch_for_error(self, session_id: str) -> OpenCodeError | None:
        """Drain events for ``session_id``; return classified error on first one.

        Returns ``None`` when the session reaches ``session.idle`` cleanly.
        Cancellation propagates as :class:`asyncio.CancelledError` (caller
        cancels this task when the send completes).
        """
        async for evt in self.stream_events(session_id=session_id):
            t = evt.get("type") or ""
            if t == "session.error":
                err_obj = (evt.get("properties") or {}).get("error") or {}
                return classify_session_error(err_obj)
            # ContextOverflow shows up on assistant messages with finish=error
            if t == "message.updated":
                info = (evt.get("properties") or {}).get("info") or {}
                err_field = info.get("error")
                if isinstance(err_field, dict):
                    return classify_session_error(err_field)
                if info.get("finish") == "error":
                    return OpenCodeError(
                        f"message finished with error (no error field): {info.get('mode')}",
                        body=info,
                    )
            if t == "session.idle":
                return None
        return None

    # ---- abort helper for cooperative cancel ---------------------------

    async def abort(self, session_id: str) -> bool:
        """Alias for :meth:`cancel` — kept for symmetry with the spike API."""
        return await self.cancel(session_id)


def _event_matches_session(evt: dict[str, Any], session_id: str) -> bool:
    props = evt.get("properties") or {}
    sid = props.get("sessionID")
    if sid is None:
        info = props.get("info") or {}
        sid = info.get("sessionID")
    return sid is None or sid == session_id


async def _drain(task: asyncio.Task[Any]) -> None:
    """Await a cancelled/done task, swallowing any exception."""
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
