"""End-to-end test: ``ReviewerActor`` against a real OpenCode server.

Spawns OpenCode, points the actor at a real provider/model, sends a
synthetic review request, and asserts the supervisor receives a typed
:class:`SubmitReviewPayload`. Skipped when:

* The ``opencode`` binary is missing from ``$PATH``.
* The user has not pre-authenticated a provider via ``opencode auth login``
  (signaled by ``~/.local/share/opencode/auth.json`` containing a key).

Marked ``slow`` and ``integration`` so it doesn't run on every CI pass.
The model selected here is the cheapest reliable option from the spike:
``openrouter`` + ``openai/gpt-4o-mini``. We rely on the spike's empirical
data showing 100% structured-output reliability for this combo so the
test isn't flaky.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
import xoscar as xo

from maverick.actors.xoscar.messages import (
    PromptError,
    ReviewRequest,
)
from maverick.actors.xoscar.pool import actor_pool
from maverick.actors.xoscar.reviewer import ReviewerActor
from maverick.executor.config import StepConfig
from maverick.payloads import SubmitReviewPayload

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
# Gated explicitly because each run bills a real provider and adds 5-30s
# of wall time. Set MAVERICK_E2E_LLM=1 (or run via pytest -k 'e2e') to
# opt in; otherwise we rely on the unit tests in
# ``tests/unit/actors/xoscar_runtime/test_reviewer_opencode.py`` to prove
# the supervisor contract and skip the live-LLM round-trip.
if not os.environ.get("MAVERICK_E2E_LLM"):
    pytest.skip(
        "set MAVERICK_E2E_LLM=1 to run live-LLM end-to-end tests",
        allow_module_level=True,
    )


class _CapturingSupervisor(xo.Actor):
    async def __post_create__(self) -> None:
        self._reviews: list[SubmitReviewPayload] = []
        self._errors: list[PromptError] = []
        self._parse_errors: list[tuple[str, str]] = []

    @xo.no_lock
    async def review_ready(self, payload: SubmitReviewPayload) -> None:
        self._reviews.append(payload)

    @xo.no_lock
    async def aggregate_review_ready(self, payload: SubmitReviewPayload) -> None:
        self._reviews.append(payload)

    @xo.no_lock
    async def prompt_error(self, error: PromptError) -> None:
        self._errors.append(error)

    @xo.no_lock
    async def payload_parse_error(self, tool: str, message: str) -> None:
        self._parse_errors.append((tool, message))

    async def get_summary(self) -> dict:
        return {
            "review_count": len(self._reviews),
            "approved": [p.approved for p in self._reviews],
            "findings_count": [len(p.findings) for p in self._reviews],
            "errors": [e.error for e in self._errors],
            "parse_errors": list(self._parse_errors),
        }


@pytest.mark.timeout(180)
async def test_reviewer_against_real_opencode_returns_typed_payload(tmp_path: Path) -> None:
    """The new reviewer produces a :class:`SubmitReviewPayload` end-to-end."""
    cwd = tmp_path
    (cwd / "calc.py").write_text(
        "def divide(a, b):\n    return a / b  # divide by zero possible\n",
        encoding="utf-8",
    )

    config = StepConfig(
        provider="openrouter",
        # claude-haiku-4.5 is 200K-context; gpt-4o-mini overflowed 128K
        # because OpenCode auto-prepends a hefty project preamble.
        model_id="anthropic/claude-haiku-4.5",
    )

    async with actor_pool(with_opencode=True) as (_pool, address):
        sup = await xo.create_actor(_CapturingSupervisor, address=address, uid="sup-e2e")
        reviewer = await xo.create_actor(
            ReviewerActor,
            sup,
            cwd=str(cwd),
            config=config.model_dump(),
            address=address,
            uid="reviewer-e2e",
        )
        try:
            await xo.wait_for(
                reviewer.send_review(
                    ReviewRequest(
                        bead_id="e2e-1",
                        bead_description="Implement safe division",
                        work_unit_md=(
                            "Implement a divide(a, b) function that returns a/b but "
                            "raises a clear error on divide-by-zero."
                        ),
                    )
                ),
                timeout=120,
            )
            summary = await sup.get_summary()
            assert summary["errors"] == [], f"prompt_error fired unexpectedly: {summary['errors']}"
            assert summary["parse_errors"] == []
            assert summary["review_count"] == 1
        finally:
            await xo.destroy_actor(reviewer)
            await xo.destroy_actor(sup)
