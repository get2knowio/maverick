"""BeadSessionRegistry — ACP session lifecycle management per bead.

Manages persistent ACP sessions scoped to a single bead's processing.
Each agent actor (implementer, reviewer) gets one session that persists
across all their interactions for that bead, enabling multi-turn
conversations with full context retention.

Sessions are created lazily on first use and closed when the bead
completes or is abandoned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from maverick.executor.config import StepConfig
from maverick.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class SessionRegistry(Protocol):
    """Structural contract for per-logical-task ACP session lifecycle.

    Actors interact with whatever concrete registry the workflow provides
    via this surface. Keeps implementers, reviewers, generators, and
    decomposers decoupled from a single concrete registry class
    (PATTERNS.md §11 — prefer Protocol at boundary seams).

    Note: ``@runtime_checkable`` verifies attribute presence but not full
    signature correctness. Static typing still carries the weight —
    ``isinstance`` only catches "totally wrong object," not subtly
    mismatched methods.
    """

    async def get_or_create(
        self,
        actor_name: str,
        executor: Any,
        *,
        cwd: Path | None = None,
        config: StepConfig | None = None,
        step_name: str | None = None,
        agent_name: str | None = None,
        event_callback: Any | None = None,
        allowed_tools: list[str] | None = None,
        mcp_servers: list[Any] | None = None,
    ) -> str: ...

    def get_session(self, actor_name: str) -> str | None: ...

    def get_provider(self, actor_name: str) -> str | None: ...

    def close_all(self) -> None: ...


@dataclass
class BeadSessionRegistry:
    """Manages ACP sessions for actors within a single bead's processing.

    Created when a bead starts.  Closed when the bead completes or is
    abandoned.  Maps actor names to their session IDs.

    Attributes:
        bead_id: The bead being processed.
        sessions: Mapping of actor_name → session_id.
        providers: Mapping of actor_name → provider_name (for routing
            prompt_session calls to the correct connection).
    """

    bead_id: str
    sessions: dict[str, str] = field(default_factory=dict)
    providers: dict[str, str] = field(default_factory=dict)

    async def get_or_create(
        self,
        actor_name: str,
        executor: Any,  # StepExecutor (typed via protocol to avoid circular import)
        *,
        cwd: Path | None = None,
        config: StepConfig | None = None,
        step_name: str | None = None,
        agent_name: str | None = None,
        event_callback: Any | None = None,
        allowed_tools: list[str] | None = None,
        mcp_servers: list[Any] | None = None,
    ) -> str:
        """Return existing session_id for this actor, or create a new one.

        On first call for an actor, creates a fresh ACP session via the
        executor's ``create_session()`` method.  Subsequent calls return
        the cached session_id.

        Args:
            actor_name: Unique actor name (e.g., "implementer", "reviewer").
            executor: The StepExecutor to use for session creation.
            cwd: Working directory for the session.
            config: Step configuration (provider, model, timeout).
            step_name: For logging/observability.
            agent_name: For logging/observability.
            event_callback: Async callback for streaming events.
            allowed_tools: Tool allowlist for the agent.
            mcp_servers: MCP server configs to attach to the session.

        Returns:
            The ACP session_id string.
        """
        if actor_name in self.sessions:
            return self.sessions[actor_name]

        effective_step = step_name or actor_name
        effective_agent = agent_name or actor_name

        # Resolve provider from config
        provider = None
        if config and config.provider:
            provider = config.provider

        session_id = await executor.create_session(
            provider=provider,
            config=config,
            cwd=cwd,
            step_name=effective_step,
            agent_name=effective_agent,
            event_callback=event_callback,
            allowed_tools=allowed_tools,
            mcp_servers=mcp_servers,
        )
        self.sessions[actor_name] = session_id
        if provider:
            self.providers[actor_name] = provider

        logger.info(
            "session_registry.created",
            bead_id=self.bead_id,
            actor=actor_name,
            session_id=session_id,
        )
        return session_id

    def get_session(self, actor_name: str) -> str | None:
        """Return session_id for an actor, or None if not created yet."""
        return self.sessions.get(actor_name)

    def get_provider(self, actor_name: str) -> str | None:
        """Return provider name for an actor, or None."""
        return self.providers.get(actor_name)

    def close_all(self) -> None:
        """Mark all sessions as closed.

        Note: ACP sessions are implicitly closed when the connection
        moves to a new session.  This method clears the registry so
        no further prompts are sent to stale session IDs.
        """
        count = len(self.sessions)
        self.sessions.clear()
        self.providers.clear()
        logger.info(
            "session_registry.closed_all",
            bead_id=self.bead_id,
            sessions_closed=count,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for checkpoint."""
        return {
            "bead_id": self.bead_id,
            "sessions": dict(self.sessions),
            "providers": dict(self.providers),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BeadSessionRegistry:
        """Restore from checkpoint."""
        return cls(
            bead_id=data["bead_id"],
            sessions=dict(data.get("sessions", {})),
            providers=dict(data.get("providers", {})),
        )
