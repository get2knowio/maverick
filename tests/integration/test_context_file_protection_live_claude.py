"""Live-Claude verification of Layer 1 permission gating (056-context-file-protection T034).

Imports airframe's own portable behavioural contract
(``airframe.testing.integration.test_integration_permission_callback_denies_tool``)
against a real :class:`~airframe.adapters.claude_code.ClaudeCodeRuntime` —
the exact adapter/property airframe#79 fixed in v0.9.2 (pinned in
``pyproject.toml``). Confirms the ``claude`` provider actually honours
``session(on_permission=...)`` and denies a tool call, not just that
:meth:`AgentRuntime.supports` reports the capability.

**Credential-gated, like every test in ``airframe.testing.integration``**:
missing ``CLAUDE_CODE_OAUTH_TOKEN``/``ANTHROPIC_API_KEY`` (or a
`RuntimeAuthError`/`RuntimeServerStartError` at the live call) is a clean
``pytest.skip``, never a failure — this file is safe to collect on any
machine, including CI, and only actually calls the network on one that
has Claude credentials exported as env vars. Run explicitly with::

    pytest -m integration -k live_claude

This is the code-level half of quickstart.md §4; the full CLI smoke
(``maverick fly`` against a real epic with a prompt-injected bead)
requires a scratch repo + bd install + a real epic and is intentionally
left as a manual step — see quickstart.md §4 for that procedure.
"""

from __future__ import annotations

from typing import Any

import pytest
from airframe.testing.integration import (
    test_integration_permission_callback_denies_tool,
)

__all__ = ["test_integration_permission_callback_denies_tool"]


@pytest.fixture
def adapter_runtime() -> Any:
    from airframe.adapters.claude_code import ClaudeCodeRuntime

    runtime = ClaudeCodeRuntime(model="claude-haiku-4-5")
    yield runtime


async def test_claude_capability_probe_matches_adapter_declaration() -> None:
    """The capability probe Maverick's Agent base actually calls
    (:func:`maverick.runtime.agent_factory.supports_permission_callback`)
    agrees with the adapter's own declaration — no credentials needed,
    always runs."""
    from airframe.adapters.claude_code import ClaudeCodeRuntime
    from airframe.features import Feature

    from maverick.runtime.agent_factory import supports_permission_callback

    runtime = ClaudeCodeRuntime(model="claude-haiku-4-5")
    assert supports_permission_callback(runtime) is True
    assert runtime.supports(Feature.PERMISSION_CALLBACK) is True
