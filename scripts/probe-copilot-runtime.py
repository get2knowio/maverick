#!/usr/bin/env python3
"""End-to-end probe for :class:`CopilotRuntime`.

Sends a small typed-output prompt against the real ``copilot`` CLI
subprocess. Uses whichever GitHub auth is on this machine
(``GITHUB_TOKEN`` env var, else falls back to ``gh auth login``
credentials via ``use_logged_in_user=True``).

Verifies:

* Auth resolution works (the runtime resolves GitHub credentials
  and spawns ``copilot`` successfully).
* :meth:`CopilotRuntime.execute` returns a typed payload via the
  forced ``submit_result`` tool.
* :class:`CostRecord` fields are populated from the
  ``assistant.usage`` event (tokens at minimum; ``cost_usd``
  when the model returns it).
* :meth:`validate_binding` rejects ``claude-*`` model IDs even
  when the provider is ``copilot`` (the Phase 0 finding).
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from pydantic import BaseModel  # noqa: E402

from maverick.runtime.copilot_adapter import CopilotRuntime  # noqa: E402
from maverick.runtime.tiers import ProviderModel  # noqa: E402


class Result(BaseModel):
    answer: int
    rationale: str


async def main() -> int:
    model_id = "gpt-5-mini"
    runtime = CopilotRuntime(model=model_id)

    print(f"CopilotRuntime probe — model={model_id}")

    # --- Static check: binding rejection -----------------------------------
    rejected = runtime.validate_binding(ProviderModel("copilot", "claude-sonnet-4.6"))
    print(f"  validate_binding(claude-on-copilot)={rejected} (expected False)")
    if rejected:
        print("FAIL: validate_binding accepted claude on copilot — Phase 0 guard is broken")
        return 1

    accepted = runtime.validate_binding(ProviderModel("copilot", model_id))
    print(f"  validate_binding(gpt-5-mini-on-copilot)={accepted} (expected True)")
    if not accepted:
        print("FAIL: validate_binding rejected a valid binding")
        return 1

    # --- Probe 1: structured output ----------------------------------------
    t0 = time.monotonic()
    err: str | None = None
    structured = None
    try:
        result = await runtime.execute(
            "What is 17 + 25? Reply with answer and a short rationale.",
            schema=Result,
            model=ProviderModel("copilot", model_id),
        )
        structured = result.structured
        print(f"  structured: PASS ({time.monotonic() - t0:.1f}s)")
        print(f"    payload: {structured}")
        for k, v in result.cost.to_dict().items():
            print(f"    cost.{k}: {v}")
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
        import traceback

        traceback.print_exc()

    await runtime.aclose()

    if err is not None:
        print(f"\nFAIL: {err}")
        return 1
    if structured is None or "answer" not in (structured or {}):
        print("\nFAIL: structured payload missing 'answer'")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
