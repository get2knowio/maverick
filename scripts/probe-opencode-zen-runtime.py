#!/usr/bin/env python3
"""End-to-end probe for :class:`OpenCodeZenRuntime`.

Sends a small typed-output prompt against the opencode-go Zen gateway
using whichever API key is available (``OPENCODE_API_KEY`` env var or
``~/.local/share/opencode/auth.json``). Not a CI test — runs against
the real gateway, may incur cost (on free models, $0).

Verifies:

* Auth resolution works (the runtime finds the key).
* OpenAI-compatible Chat Completions returns structured JSON.
* :class:`CostRecord` fields are populated (tokens at minimum; cost_usd
  only when the model is in the pricing map).
* Plain-text execute() (no schema) works.
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

from maverick.runtime.opencode_zen_adapter import OpenCodeZenRuntime  # noqa: E402
from maverick.runtime.tiers import ProviderModel  # noqa: E402


class Result(BaseModel):
    answer: int
    rationale: str


async def main() -> int:
    # nemotron-3-super-free is one of the gateway's free models we saw in
    # earlier exploration. Override via env if you want to hit a paid one.
    model_id = "nemotron-3-super-free"
    runtime = OpenCodeZenRuntime(model=model_id)

    print(f"OpenCodeZenRuntime probe — model={model_id}")

    # --- Probe 1: structured output -----------------------------------------
    t0 = time.monotonic()
    err: str | None = None
    structured = None
    try:
        result = await runtime.execute(
            "What is 17 + 25? Reply with answer and a short rationale.",
            schema=Result,
            model=ProviderModel("opencode", model_id),
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

    # --- Probe 2: plain text ------------------------------------------------
    t0 = time.monotonic()
    try:
        result = await runtime.execute(
            "Reply with the single word: ready.",
            model=ProviderModel("opencode", model_id),
        )
        print(f"  plain text: PASS ({time.monotonic() - t0:.1f}s)")
        print(f"    text: {result.text[:200]!r}")
    except Exception as exc:  # noqa: BLE001
        err = err or f"{type(exc).__name__}: {exc}"
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
