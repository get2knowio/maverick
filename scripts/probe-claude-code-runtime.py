#!/usr/bin/env python3
"""End-to-end probe for :class:`ClaudeCodeRuntime` against the sample project.

Exercises:

* Construct a ``BriefingAgent`` in the Pattern D (``runtime=``) shape.
* Run a real navigator briefing against the sample project's flight plan.
* Verify the typed :class:`SubmitNavigatorBriefPayload` validates.
* Verify ``agent.cost`` structured-log row carries every field
  (provider_id, model_id, cost_usd, tokens, cache_*, finish).

Not a CI test — runs against the real Claude Code SDK, against your
Claude subscription. Manual probe; update as the API evolves.

Equivalent to ``scripts/spike-runtime-protocol-driver.py`` from the v0
spike, but now using the production ``ClaudeCodeRuntime`` and the
canonical error names.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from maverick.agents.briefing.agent import BriefingAgent  # noqa: E402
from maverick.payloads import SubmitNavigatorBriefPayload  # noqa: E402
from maverick.runtime.claude_code_adapter import ClaudeCodeRuntime  # noqa: E402

SAMPLE_PROJECT = Path("/workspaces/sample-maverick-project")


def build_navigator_prompt() -> str:
    flight_plan_md = (
        SAMPLE_PROJECT
        / ".maverick"
        / "plans"
        / "greet-cli-mvp-flight-plan"
        / "flight-plan.md"
    )
    try:
        plan_text = flight_plan_md.read_text()
    except FileNotFoundError:
        plan_text = (
            "Greet CLI — a Python 3.10+ multilingual `Hello, <name>!` "
            "greeting tool with Rich + pyfiglet rendering, language filtering, "
            "and a plain-text fallback."
        )
    return (
        "You are the navigator. Survey the project and surface the "
        "high-level context another agent would need to decompose this "
        "flight plan into beads. Be concise; this is one shot.\n\n"
        f"# Project root\n{SAMPLE_PROJECT}\n\n"
        f"# Flight plan\n{plan_text[:8000]}\n"
    )


async def main() -> int:
    print("Claude Code Runtime end-to-end probe")
    print(f"Project: {SAMPLE_PROJECT}")
    print()

    # Bump max_turns to give Claude plenty of room to read files before
    # calling submit_result. Briefings on a fresh repo often need 10-20
    # tool reads before the model has enough context.
    runtime = ClaudeCodeRuntime(model="claude-haiku-4-5", max_turns=60)
    agent = BriefingAgent(
        runtime=runtime,
        cwd=str(SAMPLE_PROJECT),
        agent_name="navigator",
        result_model=SubmitNavigatorBriefPayload,
    )
    print(f"Agent: tag={agent.tag} schema={SubmitNavigatorBriefPayload.__name__}")

    t0 = time.monotonic()
    payload: SubmitNavigatorBriefPayload | None = None
    error: str | None = None
    try:
        await agent.open()
        prompt = build_navigator_prompt()
        print(f"Prompt: {len(prompt)} chars")
        print("Sending brief...")
        result = await agent.brief(prompt)
        assert isinstance(result, SubmitNavigatorBriefPayload)
        payload = result
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        import traceback

        traceback.print_exc()
    finally:
        await agent.close()
    elapsed = time.monotonic() - t0

    print()
    print(f"Elapsed: {elapsed:.1f}s")
    if payload is not None:
        print("PASS — typed payload validated")
        for k, v in payload.model_dump().items():
            preview = str(v)[:180]
            print(f"  {k}: {preview}")
    if error:
        print(f"FAIL — {error}")

    cost = agent.last_cost_record
    if cost is not None:
        print()
        print("CostRecord:")
        for k, v in cost.to_dict().items():
            print(f"  {k}: {v}")

    return 0 if payload is not None else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
