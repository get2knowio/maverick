"""ACP Step Executor contract — typed interfaces for the ACP integration.

These are the public contracts. Implementation details (private methods,
internal caching) are not part of this contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Configuration Models
# ---------------------------------------------------------------------------


class PermissionMode(str, Enum):
    """Permission handling strategy for ACP agent tool calls."""

    AUTO_APPROVE = "auto_approve"
    DENY_DANGEROUS = "deny_dangerous"
    INTERACTIVE = "interactive"


class AgentProviderConfig(BaseModel, frozen=True):
    """Configuration for a single ACP agent provider.

    Attributes:
        command: Subprocess command and arguments to spawn the agent.
        env: Environment variable overrides for the subprocess.
        permission_mode: How to handle agent permission requests.
        default: Whether this is the default provider.
    """

    command: list[str] = Field(..., min_length=1, description="Spawn command and args")
    env: dict[str, str] = Field(
        default_factory=dict, description="Environment overrides"
    )
    permission_mode: PermissionMode = Field(
        default=PermissionMode.AUTO_APPROVE,
        description="Permission handling strategy",
    )
    default: bool = Field(default=False, description="Is this the default provider?")


# ---------------------------------------------------------------------------
# Provider Registry
# ---------------------------------------------------------------------------


class AgentProviderRegistry:
    """Resolves provider names to configurations (FR-015).

    Validates exactly one default exists. Synthesizes a default Claude Code
    provider when no providers are configured.
    """

    def __init__(self, providers: dict[str, AgentProviderConfig]) -> None: ...

    @classmethod
    def from_config(
        cls, providers: dict[str, AgentProviderConfig]
    ) -> AgentProviderRegistry:
        """Create registry, synthesizing default if empty.

        Args:
            providers: Named provider configurations from maverick.yaml.

        Returns:
            Validated registry.

        Raises:
            ConfigError: If multiple defaults or other validation failures.
        """
        ...

    def get(self, name: str) -> AgentProviderConfig:
        """Look up a provider by name.

        Raises:
            ConfigError: If provider name not found.
        """
        ...

    def default(self) -> tuple[str, AgentProviderConfig]:
        """Return (name, config) of the default provider."""
        ...

    def names(self) -> list[str]:
        """All registered provider names."""
        ...


# ---------------------------------------------------------------------------
# ACP Client (streaming + permissions)
# ---------------------------------------------------------------------------


@dataclass
class _SessionState:
    """Mutable state for a single ACP session within MaverickAcpClient."""

    text_chunks: list[str] = field(default_factory=list)
    tool_call_counts: dict[str, int] = field(default_factory=dict)
    abort: bool = False


# Note: MaverickAcpClient extends acp.Client (not shown here since it's
# a third-party base class). The contract below shows the public interface.


class MaverickAcpClientContract:
    """ACP Client that handles streaming events and permission requests.

    Created per-connection. Supports reset() between sessions on the same
    connection.
    """

    def reset(
        self,
        step_name: str,
        agent_name: str,
        event_callback: Any | None,
        allowed_tools: frozenset[str] | None,
    ) -> None:
        """Reset state for a new session.

        Args:
            step_name: Current step name for event tagging.
            agent_name: Current agent name for event tagging.
            event_callback: Where to forward AgentStreamChunk events.
            allowed_tools: Tools the agent is allowed to use (for deny_dangerous).
        """
        ...

    def get_accumulated_text(self) -> str:
        """Return all accumulated agent text from the current session."""
        ...

    @property
    def aborted(self) -> bool:
        """Whether the circuit breaker triggered for the current session."""
        ...


# ---------------------------------------------------------------------------
# Cached Connection
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CachedConnection:
    """A cached ACP subprocess connection.

    Attributes:
        conn: The ACP client-side connection.
        proc: The subprocess handle.
        client: The Maverick ACP client instance for this connection.
        provider_name: Provider name for logging.
    """

    conn: Any  # acp.ClientSideConnection
    proc: Any  # asyncio.subprocess.Process
    client: MaverickAcpClientContract
    provider_name: str


# ---------------------------------------------------------------------------
# Prompt Builder Protocol (replaces MaverickAgent.execute)
# ---------------------------------------------------------------------------


@runtime_checkable
class AgentPromptBuilder(Protocol):
    """Protocol for agents that build prompts from typed contexts (FR-017).

    Replaces the SDK-coupled MaverickAgent.execute() pattern. Agents
    implement this to construct prompt text; the executor handles
    all interaction with the ACP agent.
    """

    @property
    def name(self) -> str:
        """Agent identifier."""
        ...

    @property
    def instructions(self) -> str:
        """Agent role and behavioral guidelines."""
        ...

    @property
    def allowed_tools(self) -> list[str]:
        """Tools the agent may use."""
        ...

    @property
    def model(self) -> str:
        """Preferred model ID."""
        ...

    def build_prompt(self, context: Any) -> str:
        """Construct the prompt string from a typed context.

        Args:
            context: Domain-specific context (ImplementerContext, ReviewContext, etc.)

        Returns:
            Complete prompt text ready for the ACP agent.
        """
        ...


# ---------------------------------------------------------------------------
# AcpStepExecutor (implements StepExecutor protocol)
# ---------------------------------------------------------------------------


class AcpStepExecutorContract:
    """ACP-based step executor (FR-004).

    Manages ACP subprocess lifecycle, connection caching, streaming,
    structured output extraction, retry, timeout, and circuit breaking.
    """

    def __init__(
        self,
        provider_registry: AgentProviderRegistry,
        agent_registry: Any,  # ComponentRegistry
    ) -> None: ...

    async def execute(
        self,
        *,
        step_name: str,
        agent_name: str,
        prompt: Any,
        instructions: str | None = None,
        allowed_tools: list[str] | None = None,
        cwd: Path | None = None,
        output_schema: type[BaseModel] | None = None,
        config: Any | None = None,  # StepConfig
        event_callback: Any | None = None,  # EventCallback
    ) -> Any:  # ExecutorResult
        """Execute a step via ACP.

        1. Resolve provider from config or default
        2. Get or create cached connection
        3. Reset client state for new session
        4. Create ACP session with cwd
        5. Build and send prompt
        6. Collect streaming events via client callback
        7. Extract output (plain text or structured JSON)
        8. Return ExecutorResult

        Retry: Fresh session per attempt (connection reused).
        Timeout: asyncio.wait_for around prompt().
        Circuit breaker: Via MaverickAcpClient.session_update().
        """
        ...

    async def cleanup(self) -> None:
        """Terminate all cached agent subprocesses.

        Called during workflow teardown (FR-019).
        """
        ...
