"""Tests for the SessionRegistry Protocol.

PATTERNS.md §11 prefers Protocol over inheritance at boundary seams.
The canonical BeadSessionRegistry must satisfy the Protocol, and
arbitrary implementations (test doubles, alternate runtimes) should
too — that's the whole point of the seam.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maverick.executor.config import StepConfig
from maverick.workflows.fly_beads.session_registry import (
    BeadSessionRegistry,
    SessionRegistry,
)


class TestSessionRegistryProtocol:
    def test_bead_session_registry_satisfies_protocol(self) -> None:
        registry = BeadSessionRegistry(bead_id="test-bead")
        # ``runtime_checkable`` verifies attribute presence.
        assert isinstance(registry, SessionRegistry)

    def test_custom_implementation_satisfies_protocol(self) -> None:
        """A test double implementing the surface must pass isinstance."""

        class _StubRegistry:
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
            ) -> str:
                return "stub-session"

            def get_session(self, actor_name: str) -> str | None:
                return None

            def get_provider(self, actor_name: str) -> str | None:
                return None

            def close_all(self) -> None:
                pass

        assert isinstance(_StubRegistry(), SessionRegistry)

    def test_incomplete_implementation_fails_isinstance(self) -> None:
        """Missing a required method must fail the runtime check."""

        class _PartialRegistry:
            # Missing close_all and others
            def get_session(self, actor_name: str) -> str | None:
                return None

        assert not isinstance(_PartialRegistry(), SessionRegistry)
