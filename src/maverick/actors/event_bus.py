"""Event bus mixin for supervisor actors.

All three Thespian supervisor actors (fly, refuel, plan) buffer
``ProgressEvent`` instances in an append-only list and reply to a
``{"type": "get_events", "since": int}`` message with the events appended
since the caller's cursor. This lets the workflow process drain events
while the supervisor keeps running, instead of blocking on a single
``asys.ask(supervisor, "start", ...)`` until everything is done.

The supervisor IS the event bus — no separate status actor, no push hooks.
One mixin, three supervisors. See ``docs/AGENT-MCP.md`` for the broader
actor-mailbox architecture.
"""

from __future__ import annotations

from typing import Any, Literal

from maverick.events import AgentCompleted, AgentStarted, ProgressEvent, StepOutput


class SupervisorEventBusMixin:
    """Mixin that turns a Thespian supervisor actor into an event bus.

    Provides:
    - ``_events``: append-only buffer of ``ProgressEvent`` instances
    - ``_done`` / ``_terminal_result``: terminal-state signaling for the
      workflow's drain loop
    - ``_emit()``: append a ProgressEvent to the buffer
    - ``_emit_output()``: convenience for the most common case (StepOutput)
    - ``_handle_get_events()``: reply handler for ``{"type": "get_events"}``

    Subclasses must call ``_init_event_bus()`` from their ``_init`` method
    before any events are emitted. The ``receiveMessage`` implementation
    must dispatch ``get_events`` messages to ``_handle_get_events`` before
    its other routing.
    """

    # Declared for type checkers; initialized in _init_event_bus().
    _events: list[ProgressEvent]
    _done: bool
    _terminal_result: dict[str, Any] | None

    def _init_event_bus(self) -> None:
        """Initialize event-bus state. Call from the supervisor's ``_init``."""
        self._events = []
        self._done = False
        self._terminal_result = None

    def _emit(self, event: ProgressEvent) -> None:
        """Append a ProgressEvent to the buffer for workflow drain."""
        self._events.append(event)

    def _emit_output(
        self,
        step_name: str,
        message: str,
        level: Literal["info", "success", "warning", "error"] = "info",
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Emit a ``StepOutput`` event — the supervisor's default message type.

        Most supervisor progress reporting is free-form status text mapped to
        one of four levels. Use this over constructing ``StepOutput`` directly
        to keep call sites compact.
        """
        self._emit(
            StepOutput(
                step_name=step_name,
                message=message,
                level=level,
                source=source,
                metadata=metadata,
            )
        )

    def _emit_agent_started(self, step_name: str, agent_name: str, provider: str = "") -> None:
        """Emit an ``AgentStarted`` event for Rich Live rendering."""
        self._emit(AgentStarted(step_name=step_name, agent_name=agent_name, provider=provider))

    def _emit_agent_completed(
        self, step_name: str, agent_name: str, duration_seconds: float
    ) -> None:
        """Emit an ``AgentCompleted`` event."""
        self._emit(
            AgentCompleted(
                step_name=step_name,
                agent_name=agent_name,
                duration_seconds=duration_seconds,
            )
        )

    def _mark_done(self, result: dict[str, Any] | None) -> None:
        """Signal that the supervisor is finished.

        The workflow's next ``get_events`` poll will see ``done=True`` and
        the provided ``result`` payload (what used to ride on the old
        ``{"type": "complete"}`` reply).
        """
        self._terminal_result = result
        self._done = True

    def _handle_get_events(self, message: dict[str, Any], sender: Any) -> None:
        """Reply to a ``{"type": "get_events", "since": int}`` message.

        Must be dispatched from the supervisor's ``receiveMessage`` before
        other handlers (so a completed supervisor can still answer polls).
        """
        since = int(message.get("since", 0))
        if since < 0:
            since = 0
        batch = self._events[since:]
        reply = {
            "type": "events",
            "events": [e.to_dict() for e in batch],  # type: ignore[attr-defined]
            "next_cursor": len(self._events),
            "done": self._done,
            "result": self._terminal_result if self._done else None,
        }
        # self.send is provided by Thespian Actor at runtime.
        self.send(sender, reply)  # type: ignore[attr-defined]
