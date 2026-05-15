"""Shared fakes for agent unit tests.

Agents don't need xoscar — they take an :class:`OpenCodeServerHandle`
in their constructor and build their own client. Tests inject fakes
by either passing a fake handle (no actor pool) and overriding
``_build_client`` in a subclass, or by patching the client on the
agent instance after :meth:`Agent.open`.
"""

from __future__ import annotations

from typing import Any

from maverick.runtime.opencode import OpenCodeServerHandle, SendResult


class _FakeProcess:
    """Stand-in for asyncio.subprocess.Process in OpenCodeServerHandle."""

    pid = 0
    returncode = 0

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass

    async def wait(self) -> int:
        return 0


def fake_handle(base_url: str = "http://fake-opencode") -> OpenCodeServerHandle:
    """Build a usable :class:`OpenCodeServerHandle` for tests."""
    return OpenCodeServerHandle(
        base_url=base_url,
        password="fake",
        pid=0,
        _process=_FakeProcess(),  # type: ignore[arg-type]
    )


class FakeClient:
    """Programmable stand-in for :class:`OpenCodeClient`.

    Tests inject one by setting ``agent._client = FakeClient(...)``
    before the first send, or by subclassing the agent and overriding
    ``_build_client``.
    """

    def __init__(
        self,
        *,
        send_result: SendResult | None = None,
        send_error: BaseException | None = None,
        validate_error: BaseException | None = None,
    ) -> None:
        self.send_result = send_result
        self.send_error = send_error
        self.validate_error = validate_error
        self.created_sessions: list[str | None] = []
        self.deleted_sessions: list[str] = []
        self.send_calls: list[dict[str, Any]] = []
        self.list_provider_calls = 0
        self.closed = False

    @property
    def base_url(self) -> str:
        return "http://fake-opencode"

    async def list_providers(self) -> dict[str, Any]:
        self.list_provider_calls += 1
        if self.validate_error is not None:
            raise self.validate_error
        # Comprehensive default — accept every provider+model referenced
        # by ``DEFAULT_TIERS`` so per-tier cascade tests don't have to
        # build a custom provider list. Tests that want to exercise the
        # cascade-fallover path subclass and override.
        from maverick.runtime.opencode.tiers import DEFAULT_TIERS

        all_models: dict[str, set[str]] = {}
        for tier in DEFAULT_TIERS.values():
            for binding in tier.bindings:
                all_models.setdefault(binding.provider_id, set()).add(binding.model_id)
        return {
            "connected": list(all_models.keys()),
            "all": [
                {"id": pid, "models": dict.fromkeys(models, {})}
                for pid, models in all_models.items()
            ],
        }

    async def create_session(self, *, title: str | None = None, **_: Any) -> str:
        sid = f"ses_{len(self.created_sessions)}"
        self.created_sessions.append(title)
        return sid

    async def delete_session(self, session_id: str) -> bool:
        self.deleted_sessions.append(session_id)
        return True

    async def send_with_event_watch(
        self,
        session_id: str,
        content: str,
        *,
        model: dict[str, str] | None = None,
        format: dict[str, Any] | None = None,
        system: str | None = None,
        tools: dict[str, bool] | None = None,
        timeout: float | None = None,
        agent: str | None = None,
    ) -> SendResult:
        self.send_calls.append(
            {
                "session_id": session_id,
                "content": content,
                "model": model,
                "format": format,
                "system": system,
                "agent": agent,
                "timeout": timeout,
            }
        )
        if self.send_error is not None:
            raise self.send_error
        if self.send_result is None:
            return SendResult(message={}, text="", structured=None, valid=False)
        return self.send_result

    async def aclose(self) -> None:
        self.closed = True


def payload_send_result(payload: dict[str, Any]) -> SendResult:
    """Build a :class:`SendResult` carrying a structured payload."""
    return SendResult(
        message={"info": {"structured": payload}, "parts": []},
        text="",
        structured=payload,
        valid=True,
        info={},
    )
