"""``Agent`` — owns one airframe :class:`AgentRuntime` and one result model.

Subclass requirements:

* ``result_model: ClassVar[type[BaseModel]]`` — the Pydantic model
  used to validate structured-output payloads. Briefing-style agents
  that vary the schema per instance can pass ``result_model=...`` to
  ``__init__`` instead of declaring a class var.
* Implement domain methods that build a prompt and call
  :meth:`_execute_via_runtime`.

Lifecycle:

* :meth:`open` — initialise lazy state. No network calls, *unless*
  ``protection_policy`` is set (see below), in which case it opens an
  airframe :class:`~airframe.protocol.AgentSession` up front so the
  session's ``on_permission=`` gate is live before the first send.
* First :meth:`_execute_via_runtime` call hits the runtime.
* :meth:`rotate_session` drops the runtime's accumulated scope (used
  between beads) — ``runtime.reset()`` when no session was opened, or a
  close-and-reopen of the session otherwise.
* :meth:`close` tears down the session (if any) then the runtime.

Async context-manager support (``async with Agent(...)``) calls
:meth:`open` / :meth:`close` for you.

Context-file protection (056-context-file-protection)
------------------------------------------------------

Passing ``protection_policy=`` (constructed once per run by the owning
:class:`~maverick.squadron.base.Squadron`, per
``specs/056-context-file-protection/research.md`` R7) switches this
agent's execute path onto two enforcement layers:

* **Layer 1 (pre-write)** — :meth:`open` attaches a
  :class:`~maverick.protection.policy.PermissionGate` to the session's
  ``on_permission=`` callback, but only when the runtime's adapter
  advertises :data:`~airframe.features.Feature.PERMISSION_CALLBACK`
  (:func:`~maverick.runtime.agent_factory.supports_permission_callback`).
  Providers that decline simply run without it — Layer 2 still covers
  them.
* **Layer 2 (backstop)** — every :meth:`_execute_via_runtime` /
  :meth:`_execute_text_via_runtime` call is bracketed by a
  :class:`~maverick.protection.snapshot.SnapshotManifest` capture before
  the send and a :func:`~maverick.protection.snapshot.restore_and_report`
  pass after, regardless of what channel the model used to mutate files.

``protection_policy=None`` (the default) disables both layers with zero
behavior change — the agent sends via ``runtime.execute()`` exactly as
before this feature existed. This keeps every caller that doesn't thread
protection through (most existing tests) byte-for-byte unaffected.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, ClassVar, Self

from airframe.cost import CostRecord
from airframe.errors import RuntimeStructuredOutputError
from airframe.protocol import AgentRuntime
from pydantic import BaseModel, ValidationError

from maverick.logging import get_logger

if TYPE_CHECKING:
    from airframe.protocol import AgentSession, RuntimeResult

    from maverick.protection.policy import PermissionGate, ProtectionPolicy
    from maverick.protection.records import BlockCollector
    from maverick.protection.snapshot import SnapshotManifest
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
    # the role's binding. Subclasses set this. Doubles as the
    # ``agent_role`` recorded on context-file-protection
    # :class:`~maverick.protection.records.BlockRecord`\\ s.
    provider_tier: ClassVar[str | None] = None

    # Optional persona label. Forwarded to airframe adapters as
    # ``persona=`` (accepted by the protocol; no shipped adapter
    # currently consumes it — every adapter discards it in favour of
    # ``system=``) and looked up via :func:`load_persona_system_prompt`
    # to derive ``system=`` — the universal channel every adapter
    # honours. Subclasses that vary the persona per instance pass
    # ``persona_name=...`` to ``__init__``.
    persona_name: ClassVar[str | None] = None

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        cwd: str,
        step_config: Any = None,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
        persona_name: str | None = None,
        result_model: type[BaseModel] | None = None,
        protection_policy: ProtectionPolicy | None = None,
        block_collector: BlockCollector | None = None,
        workflow: str = "",
        baseline_manifest: SnapshotManifest | None = None,
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
        self._persona_name_instance: str | None = persona_name

        # Last cost record observed from the runtime; populated on every
        # successful execute. Cleared by :meth:`rotate_session`.
        self._last_cost_record: CostRecord | None = None

        # Context-file protection (056-context-file-protection).
        # ``protection_policy=None`` keeps every send on the legacy
        # ``runtime.execute()`` path with zero behavior change.
        self._protection_policy = protection_policy
        self._block_collector = block_collector
        self._workflow = workflow
        # Fallback manifest for a step whose own pre-send capture fails
        # (research.md R6) — threaded in once by the owning Squadron,
        # captured at squadron-open time.
        self._baseline_manifest = baseline_manifest
        self._permission_gate: PermissionGate | None = None
        self._session: AgentSession | None = None

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    async def open(self) -> None:
        """No-op unless ``protection_policy`` is set.

        When protection is active, opens an
        :class:`~airframe.protocol.AgentSession` up front (rather than
        relying on the runtime's lazy-open-on-first-``execute``
        behavior) so the ``on_permission=`` gate — when the adapter
        supports it — is live before the first send. Subclasses can
        still override for one-time setup outside the constructor.
        """
        if self._protection_policy is None:
            return None
        await self._open_session()

    async def close(self) -> None:
        """Tear down the session (if any) then the runtime. Idempotent.

        The runtime teardown is in a ``finally``: a session whose
        ``close()`` misbehaves must not strand the runtime's own
        resources (subprocess pool, HTTP client). ``Squadron.close``
        swallows per-agent teardown errors, so a leak here would be
        completely silent.
        """
        try:
            if self._session is not None:
                await self._close_session_only()
        finally:
            await self._runtime.close()

    async def __aenter__(self) -> Self:
        await self.open()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def rotate_session(self) -> None:
        """Drop accumulated runtime state — called between beads.

        With no protection policy active, this is unchanged:
        ``runtime.reset()``. With protection active, ADR-004's
        single-active-session-per-runtime means "reset" is a
        close-and-reopen of the session — the same (reused)
        :class:`~maverick.protection.policy.PermissionGate` instance
        re-attaches, since ``agent_role``/``workflow`` never change for
        a given agent (``bead_id`` is read fresh per call, not baked
        into the gate — see ``PermissionGate.handle``).
        """
        if self._session is None:
            await self._runtime.reset()
            return
        await self._close_session_only()
        await self._open_session()

    @property
    def last_cost_record(self) -> CostRecord | None:
        return self._last_cost_record

    @property
    def tag(self) -> str:
        return self._tag

    # ------------------------------------------------------------------
    # Session management (context-file protection)
    # ------------------------------------------------------------------

    async def _open_session(self) -> None:
        """Open a fresh :class:`AgentSession`, attaching the permission gate
        when the runtime's adapter supports it.
        """
        from maverick.agents.system_prompts import load_persona_system_prompt
        from maverick.runtime.agent_factory import supports_permission_callback

        if self._permission_gate is None:
            self._permission_gate = self._build_permission_gate()

        on_permission = None
        if self._permission_gate is not None and supports_permission_callback(self._runtime):
            on_permission = self._permission_gate

        persona = self._persona_name_instance or self.persona_name
        self._session = self._runtime.session(
            system=load_persona_system_prompt(persona),
            on_permission=on_permission,
        )

    def _build_permission_gate(self) -> PermissionGate | None:
        if self._protection_policy is None:
            return None
        from maverick.protection.policy import PermissionGate
        from maverick.protection.records import BlockCollector

        if self._block_collector is None:
            self._block_collector = BlockCollector()
        return PermissionGate(
            policy=self._protection_policy,
            collector=self._block_collector,
            agent_role=self.provider_tier or "inline",
            workflow=self._workflow,
        )

    async def _close_session_only(self) -> None:
        session = self._session
        self._session = None
        if session is None:
            return
        close = getattr(session, "close", None)
        if close is not None:
            await close()

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
        structured-log row. When ``protection_policy`` is set, brackets
        the send with the backstop snapshot/restore pass (Layer 2).

        Raises:
            RuntimeStructuredOutputError: when ``result.structured`` is None.
            AgentPayloadValidationError: when the payload fails schema
                validation.
        """
        target = schema or self._effective_result_model()

        async def _send() -> RuntimeResult:
            return await self._dispatch(prompt, schema=target, timeout=timeout)

        result = await self._execute_protected(_send)
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

    async def _execute_text_via_runtime(
        self,
        prompt: str,
        *,
        timeout: float = DEFAULT_TEXT_TIMEOUT_SECONDS,
    ) -> str:
        """Run a prompt through the airframe runtime in plain-text mode.

        For personas that genuinely return free-form text (consolidator,
        validation-fixer, runway-seed, verification-properties), or that
        return a "done" signal only — wrapping their response in a
        throwaway one-field Pydantic schema buys no validation. Plain-text
        mode (airframe v0.3+) returns ``result.text`` directly.

        Captures the cost record + emits the ``agent.cost`` row exactly
        like the structured path. Empty text is a legitimate outcome
        (e.g. a tool-only turn that wrote files and finished); callers
        decide whether empty means failure. When ``protection_policy`` is
        set, brackets the send with the backstop snapshot/restore pass
        (Layer 2), same as :meth:`_execute_via_runtime`.
        """

        async def _send() -> RuntimeResult:
            return await self._dispatch(prompt, schema=None, timeout=timeout)

        result = await self._execute_protected(_send)
        self._last_cost_record = result.cost
        self._emit_cost(result.cost)
        return result.text

    async def _dispatch(
        self,
        prompt: str,
        *,
        schema: type[BaseModel] | None,
        timeout: float,
    ) -> RuntimeResult:
        """Issue one send — via the session when protection is active, via
        the legacy ``runtime.execute()`` sugar otherwise.

        ``persona=``/``system=`` are session-construction-time concerns
        when a session is open (baked in by :meth:`_open_session`); on
        the legacy path they're passed per-call exactly as before this
        feature existed.
        """
        if self._session is not None:
            return await self._session.execute(prompt, schema=schema, timeout=timeout)

        from maverick.agents.system_prompts import load_persona_system_prompt

        persona = self._persona_name_instance or self.persona_name
        return await self._runtime.execute(
            prompt,
            schema=schema,
            persona=persona,
            system=load_persona_system_prompt(persona),
            timeout=timeout,
        )

    async def _execute_protected(
        self, send: Callable[[], Awaitable[RuntimeResult]]
    ) -> RuntimeResult:
        """Run ``send()`` (a zero-arg async callable returning ``RuntimeResult``),
        bracketed by the Layer 2 backstop when ``protection_policy`` is set.

        A snapshot failure never blocks the send (protection must not
        degrade unprotected work) — it falls back to ``baseline_manifest``
        (captured once at squadron open and threaded into every agent it
        builds), per research.md R6. Restore happens even when ``send()``
        raises, so a mid-turn crash can't leave a mutated protected file
        behind — and a failure *inside* the restore is logged rather than
        raised, because raising from a ``finally`` would replace the
        real error from ``send()`` with a protection-internal one.
        """
        policy = self._protection_policy
        if policy is None:
            return await send()

        manifest = await self._capture_snapshot(policy)
        try:
            return await send()
        finally:
            if manifest is not None:
                await self._restore_after_send(manifest, policy)

    async def _restore_after_send(
        self, manifest: SnapshotManifest, policy: ProtectionPolicy
    ) -> None:
        """Run the post-send restore pass, swallowing its own failures.

        Called from a ``finally`` — see :meth:`_execute_protected`.
        """
        from maverick.protection.snapshot import restore_and_report

        try:
            await restore_and_report(
                manifest,
                policy,
                agent_role=self.provider_tier or "inline",
                workflow=self._workflow,
                bead_id=self._current_bead_id(),
                collector=self._block_collector,
            )
        except Exception as exc:  # noqa: BLE001 — must never mask the send's own outcome
            logger.warning(
                "protection_restore_pass_failed",
                agent=self._tag,
                error=str(exc),
            )

    async def _capture_snapshot(self, policy: ProtectionPolicy) -> SnapshotManifest | None:
        """Capture the pre-send manifest, falling back to the squadron-open
        baseline (``self._baseline_manifest``) when capture itself fails.

        A failed per-step capture must never abort the agent step
        (FR-011) — the step still runs; the post-step compare simply
        uses the baseline instead, so protected paths are never left
        unguarded for a whole step. If no baseline was threaded in
        either (``baseline_manifest=`` unset), the post-step compare for
        *this one step* is skipped — the next successful step's own
        snapshot resumes normal coverage.
        """
        from maverick.protection.snapshot import SnapshotManifest

        try:
            return await SnapshotManifest.capture(policy.root, policy)
        except Exception as exc:  # noqa: BLE001 — never block the send on a snapshot failure
            logger.warning(
                "protection_snapshot_capture_failed",
                agent=self._tag,
                error=str(exc),
            )
            return self._baseline_manifest

    @staticmethod
    def _current_bead_id() -> str | None:
        from maverick.agents.context import current_tags

        return current_tags().get("bead_id") or None

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
