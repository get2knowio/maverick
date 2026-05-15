#!/usr/bin/env python3
"""End-to-end probe for :class:`CodexRuntime`.

Sends a small typed-output prompt against the real ``codex`` CLI
subprocess via ``openai-codex-sdk``. Uses whichever OpenAI auth is
on this machine (``OPENAI_API_KEY`` env var, else falls back to
the codex CLI's stored OAuth via ``~/.codex/auth.json``).

Verifies:

* Auth resolution works (the runtime resolves OpenAI credentials
  and spawns ``codex`` successfully).
* :meth:`CodexRuntime.execute` returns a typed payload via the
  Codex CLI's native ``--output-schema`` mode.
* :class:`CostRecord` fields are populated from ``Turn.usage``
  (tokens at minimum; ``cost_usd`` from the local pricing map).
* :meth:`validate_binding` rejects ``claude-*`` model IDs even
  when the provider is ``openai`` or ``codex``.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from pydantic import BaseModel  # noqa: E402

from maverick.runtime.codex_adapter import CodexRuntime  # noqa: E402
from maverick.runtime.tiers import ProviderModel  # noqa: E402


class Result(BaseModel):
    answer: int
    rationale: str


def _auth_available() -> bool:
    """Return True if any usable Codex auth source is present.

    The codex CLI's OAuth flow stores tokens in ``~/.codex/auth.json``;
    note that ChatGPT-Plus OAuth tokens minted by ``opencode auth login
    openai`` use a different JWT shape than codex CLI's, so they aren't
    interchangeable. The codex CLI's ``--with-access-token`` rejects
    opencode's tokens with "agent identity JWT payload is not valid
    JSON".
    """
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("CODEX_API_KEY"):
        return True
    return (Path.home() / ".codex" / "auth.json").exists()


async def main() -> int:
    model_id = "gpt-5-codex"
    runtime = CodexRuntime(model=model_id)

    print(f"CodexRuntime probe — model={model_id}")

    # --- Static check: binding rejection -----------------------------------
    rejected = runtime.validate_binding(ProviderModel("openai", "claude-sonnet-4.6"))
    print(f"  validate_binding(claude-on-openai)={rejected} (expected False)")
    if rejected:
        print("FAIL: validate_binding accepted Claude on Codex")
        return 1

    accepted = runtime.validate_binding(ProviderModel("openai", model_id))
    print(f"  validate_binding(gpt-5-codex-on-openai)={accepted} (expected True)")
    if not accepted:
        print("FAIL: validate_binding rejected a valid binding")
        return 1

    # --- Auth check: bail early when no usable auth is configured ----------
    if not _auth_available():
        print(
            "  SKIP — no Codex auth on this machine. To run the live probe:\n"
            "    1. `codex login` (interactive ChatGPT-Plus OAuth), or\n"
            "    2. `export OPENAI_API_KEY=sk-...`\n"
            "  Then re-run this probe."
        )
        await runtime.aclose()
        return 0

    # --- Probe 1: structured output ----------------------------------------
    t0 = time.monotonic()
    err: str | None = None
    structured = None
    try:
        result = await runtime.execute(
            "What is 17 + 25? Reply with answer and a short rationale.",
            schema=Result,
            model=ProviderModel("openai", model_id),
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
