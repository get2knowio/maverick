#!/usr/bin/env python3
"""Phase 0 V3-redo spike — function-tool output instead of ``output_type=``.

Hypothesis: routing typed output through a ``submit_implementation``
function-tool call (with ``tool_use_behavior=StopAtTools``) sidesteps
V3's failure mode because tool args are validated at the API wire
format regardless of ``response_format`` support. This is the same
pattern OpenCode uses today via its ``StructuredOutput`` tool.

Pass criteria:
  - Both ``github_copilot/gpt-5.3-codex`` AND
    ``github_copilot/claude-sonnet-4.6`` invoke ``submit_implementation``
    with valid args first try.
  - Captured args validate against ``SubmitImplementationPayload``.
  - No envelope-unwrap layer needed.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agents import Agent, Runner, StopAtTools, function_tool  # noqa: E402
from agents.extensions.models.litellm_model import LitellmModel  # noqa: E402
from agents.model_settings import ModelSettings  # noqa: E402

from maverick.payloads import SubmitImplementationPayload  # noqa: E402

# Same Copilot IDE-auth headers as the parent spike — the SDK's
# ``User-Agent`` override otherwise breaks Chat Completions for Claude.
COPILOT_COMPAT = {
    "User-Agent": "GithubCopilot/1.155.0",
    "editor-version": "vscode/1.95.0",
    "editor-plugin-version": "copilot/1.155.0",
}

SAMPLE_PROJECT = Path("/workspaces/sample-maverick-project")
TARGET_BEAD_ID = "sample-maverick-project-37n.3"
MODELS = [
    "github_copilot/gpt-5.3-codex",
    "github_copilot/claude-sonnet-4.6",
]
RESULTS_PATH = Path(__file__).with_suffix(".results.json")


# ── MVP tool kit (read-only — V3-redo doesn't need to mutate the repo) ──

@function_tool
def read_file(path: str) -> str:
    """Read a UTF-8 text file (truncated to 200 KB)."""
    return Path(path).read_text(encoding="utf-8", errors="replace")[:200_000]


@function_tool
def glob_files(pattern: str, cwd: str = ".") -> list[str]:
    """Find files matching a glob under cwd (max 200 results)."""
    return [str(p) for p in Path(cwd).rglob(pattern) if p.is_file()][:200]


# ── Bead prompt (read-only mode — we only need a typed submission) ──

def _load_bead(bead_id: str) -> dict[str, Any]:
    for raw in (SAMPLE_PROJECT / ".beads" / "issues.jsonl").read_text().splitlines():
        d = json.loads(raw)
        if d.get("id") == bead_id and d.get("_type") == "issue":
            return d
    raise RuntimeError(f"bead {bead_id} not found")


def build_bead_prompt(bead_id: str) -> str:
    bead = _load_bead(bead_id)
    return (
        f"You are an implementer planning bead {bead_id} in the project at "
        f"{SAMPLE_PROJECT}. DO NOT edit any files. Use the read-only tools "
        f"(read_file, glob_files) to look at the existing code, then call "
        f"the submit_implementation tool with a summary of the changes you "
        f"WOULD make and the list of files you WOULD touch. The tool call "
        f"is your final answer — do not narrate after.\n\n"
        f"BEAD TITLE: {bead['title']}\n\n"
        f"BEAD DESCRIPTION:\n{bead['description']}\n"
    )


# ── The pattern under test: function-tool output with StopAtTools ──

async def run_one(model_str: str) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    @function_tool(name_override="submit_implementation")
    def submit_implementation(summary: str, files_changed: list[str]) -> str:
        """Submit the final implementation plan as a typed payload.

        Args:
            summary: One-paragraph description of the changes.
            files_changed: Paths (relative to the project) that would change.
        """
        captured["summary"] = summary
        captured["files_changed"] = list(files_changed)
        return "accepted"

    agent = Agent(
        name=f"impl-redo-{model_str.split('/')[-1]}",
        model=LitellmModel(model_str),
        instructions=(
            "You are an implementer. Read the bead and the relevant files, "
            "then call submit_implementation with a typed payload describing "
            "what you would change. Do not narrate beyond the tool call."
        ),
        tools=[read_file, glob_files, submit_implementation],
        tool_use_behavior=StopAtTools(stop_at_tool_names=["submit_implementation"]),
        model_settings=ModelSettings(extra_headers=COPILOT_COMPAT),
    )

    t0 = time.monotonic()
    error: str | None = None
    payload_valid = False
    payload: SubmitImplementationPayload | None = None
    result: Any = None
    try:
        result = await Runner.run(agent, build_bead_prompt(TARGET_BEAD_ID), max_turns=30)
        if captured:
            try:
                payload = SubmitImplementationPayload.model_validate(captured)
                payload_valid = True
            except Exception as exc:  # noqa: BLE001
                error = f"payload-validate-fail: {type(exc).__name__}: {exc}"
        else:
            error = "tool was never called"
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.monotonic() - t0

    out: dict[str, Any] = {
        "model": model_str,
        "elapsed_s": elapsed,
        "passed": payload_valid,
        "error": error,
        "tool_called": bool(captured),
        "captured_keys": sorted(captured.keys()),
    }
    if payload is not None:
        out["summary"] = payload.summary[:400]
        out["files_changed"] = list(payload.files_changed)
        out["files_changed_count"] = len(payload.files_changed)
    elif captured:
        # If the tool was called but pydantic validation failed, capture
        # the raw args verbatim so we can see how the model drifted.
        out["raw_captured"] = {
            k: (v if isinstance(v, (str, int, float, bool, list)) else repr(v))
            for k, v in captured.items()
        }
    if result is not None:
        out["raw_responses_count"] = len(getattr(result, "raw_responses", []) or [])
        out["new_items_count"] = len(getattr(result, "new_items", []) or [])
    return out


async def main() -> int:
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print("Phase 0 V3-redo spike — function-tool output (StopAtTools)")
    print(f"Sample project: {SAMPLE_PROJECT}")
    print(f"Target bead:    {TARGET_BEAD_ID}")
    print(f"Models:         {MODELS}")
    print()

    results: dict[str, Any] = {"started_at": started_at, "models_probed": MODELS}
    for model in MODELS:
        key = f"v3redo_{model.split('/')[-1].replace('.', '_')}"
        print(f"running {key}...")
        try:
            results[key] = await run_one(model)
        except Exception as exc:  # noqa: BLE001
            results[key] = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
        r = results[key]
        passed = r.get("passed")
        elapsed = r.get("elapsed_s")
        suffix = f" ({elapsed:.1f}s)" if isinstance(elapsed, (int, float)) else ""
        print(f"  {'PASS' if passed else 'FAIL'}{suffix}")
        if not passed:
            print(f"    error: {r.get('error')}")
            print(f"    tool_called: {r.get('tool_called')}")

    results["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=str))
    print()
    print(f"Wrote results to {RESULTS_PATH}")
    fails = [k for k in results if k.startswith("v3redo_") and not results[k].get("passed")]
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
