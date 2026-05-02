"""Direct live-LLM probe of the OpenCode runtime.

Proves the substrate can:

1. Spawn an OpenCode subprocess.
2. Reach a real provider via authenticated OpenCode auth.
3. Send a structured-output prompt with ``format=json_schema``.
4. Get back a valid, schema-validated payload.
5. Report token usage and cost telemetry.

Doesn't go through the actor flow (no xoscar pool, no mailbox actor) —
just the raw :class:`OpenCodeClient` surface. The actor-flow live test
in ``tests/integration/actors/test_reviewer_opencode_e2e.py`` covers
the supervisor wiring; this one isolates the runtime against the
provider and is therefore the more stable smoke when the dev
container is under contention.

Gated like the actor-flow test: set ``MAVERICK_E2E_LLM=1`` to run.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pytest

from maverick.payloads import SubmitReviewPayload
from maverick.runtime.opencode import (
    client_for,
    cost_record_from_send,
    opencode_server,
    validate_model_id,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]


_OPENCODE_AUTH = Path.home() / ".local/share/opencode/auth.json"


def _has_provider_auth() -> bool:
    if not _OPENCODE_AUTH.exists():
        return False
    try:
        data = json.loads(_OPENCODE_AUTH.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return any(isinstance(v, dict) and v.get("key") for v in data.values())


if not shutil.which(os.environ.get("OPENCODE_BIN") or "opencode"):
    pytest.skip("opencode binary not on PATH", allow_module_level=True)
if not _has_provider_auth():
    pytest.skip(
        "no OpenCode provider auth configured (run `opencode auth login`)",
        allow_module_level=True,
    )
if not os.environ.get("MAVERICK_E2E_LLM"):
    pytest.skip(
        "set MAVERICK_E2E_LLM=1 to run live-LLM end-to-end tests",
        allow_module_level=True,
    )


@pytest.mark.timeout(180)
async def test_runtime_round_trip_against_real_provider() -> None:
    """Spawn OpenCode, send a structured prompt, validate the typed payload."""
    async with opencode_server() as handle:
        client = client_for(handle)
        try:
            # Validate the model first — this is what the mixin does, and
            # exercises the Landmine 1 mitigation path against a real
            # /provider response.
            await validate_model_id(client, "openrouter", "anthropic/claude-haiku-4.5")

            sid = await client.create_session(title="live-runtime-probe")
            t0 = time.time()
            send_result = await client.send_with_event_watch(
                sid,
                (
                    "Review this trivial Python: ``def divide(a, b): return a/b``. "
                    "If you spot the divide-by-zero risk, mark severity=major."
                ),
                model={
                    "providerID": "openrouter",
                    "modelID": "anthropic/claude-haiku-4.5",
                },
                format={
                    "type": "json_schema",
                    "schema": SubmitReviewPayload.model_json_schema(),
                },
                timeout=180,
            )
            elapsed = time.time() - t0

            # Schema validation — this is what OpenCodeAgentMixin does.
            payload = SubmitReviewPayload.model_validate(send_result.structured)
            assert isinstance(payload, SubmitReviewPayload)

            # Cost telemetry — populated for any provider that surfaces it
            # (OpenRouter does for Anthropic; Anthropic-direct also does).
            cost = cost_record_from_send(send_result)
            assert cost.provider_id == "openrouter"
            assert cost.model_id == "anthropic/claude-haiku-4.5"
            # claude-haiku-4.5 always reports cost; anything else means
            # the response shape changed and the extractor needs an update.
            assert cost.cost_usd is not None
            assert cost.cost_usd > 0

            # Useful smoke for "is the model actually thinking"; loose
            # bound because output token counts vary by run.
            assert cost.output_tokens > 0

            # Sanity-check that we didn't fall into compaction (Landmine 4).
            assert send_result.info.get("mode") != "compaction"

            # Print enough to make a manual run informative without
            # leaking into CI noise.
            print(
                f"\nlive-probe: {elapsed:.1f}s "
                f"approved={payload.approved} "
                f"findings={len(payload.findings)} "
                f"cost=${cost.cost_usd:.4f} "
                f"input={cost.input_tokens} output={cost.output_tokens}"
            )

            await client.delete_session(sid)
        finally:
            await client.aclose()
