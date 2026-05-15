#!/usr/bin/env python3
"""Phase 0b spike — PydanticAI on the same surface that broke OpenAI Agents SDK.

Goal: validate whether PydanticAI's substrate (provider-native APIs +
function-tool-backed typed output) handles the failure modes Phase 0
exposed. Specifically:

  - V2 redo: codex + tools + ``SubmitImplementationPayload`` via PydanticAI
    against the Copilot Responses API.
  - V3 redo: claude + tools + ``SubmitImplementationPayload`` via PydanticAI
    against the Copilot Chat Completions API — the exact path that
    silently dropped tool calls in Phase 0.
  - V4 / V5: cache + cost telemetry on the working path (codex).

Constraint: no direct Anthropic / OpenAI API keys are available in this
dev env — only the Copilot OAuth and the opencode-go (Zen) gateway. So
"PydanticAI on native Anthropic Messages API" remains untested; this
spike validates only what's reachable.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from pydantic_ai import Agent  # noqa: E402
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel  # noqa: E402
from pydantic_ai.providers.openai import OpenAIProvider  # noqa: E402
from pydantic_ai.settings import ModelSettings  # noqa: E402

from maverick.payloads import SubmitImplementationPayload  # noqa: E402

# ── Setup ────────────────────────────────────────────────────────────

SAMPLE_PROJECT = Path("/workspaces/sample-maverick-project")
TARGET_BEAD_ID = "sample-maverick-project-37n.3"
RESULTS_PATH = Path(__file__).with_suffix(".results.json")

LITELLM_API_KEY_FILE = Path.home() / ".config" / "litellm" / "github_copilot" / "api-key.json"

# Headers the SDK strips by default; needed for Copilot IDE auth.
COPILOT_HEADERS = {
    "User-Agent": "GithubCopilot/1.155.0",
    "editor-version": "vscode/1.95.0",
    "editor-plugin-version": "copilot/1.155.0",
    "copilot-integration-id": "vscode-chat",
}


def _copilot_creds() -> tuple[str, str]:
    """Read the Copilot internal API key minted by LiteLLM."""
    data = json.loads(LITELLM_API_KEY_FILE.read_text())
    return data["endpoints"]["api"], data["token"]


def _provider() -> OpenAIProvider:
    base_url, api_key = _copilot_creds()
    return OpenAIProvider(base_url=base_url, api_key=api_key)


def _settings() -> ModelSettings:
    return ModelSettings(extra_headers=COPILOT_HEADERS)


# ── Prompt + bead helpers ────────────────────────────────────────────

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
        f"{SAMPLE_PROJECT}. DO NOT edit any files in this run — use the "
        f"read-only tools (read_file, glob_files) to look at the existing "
        f"code, then return a SubmitImplementationPayload with a one-paragraph "
        f"summary of the changes you WOULD make and the list of files you "
        f"WOULD touch.\n\n"
        f"BEAD TITLE: {bead['title']}\n\n"
        f"BEAD DESCRIPTION:\n{bead['description']}\n"
    )


def build_seeded_context(bead_id: str) -> str:
    bead = _load_bead(bead_id)
    parts = [f"Bead {bead_id}: {bead['title']}", bead["description"]]
    for f in sorted((SAMPLE_PROJECT / "src" / "greet_cli").glob("*.py")):
        parts.append(f"\n--- {f.name} ---\n{f.read_text()}\n")
    for f in sorted((SAMPLE_PROJECT / "tests").glob("test_*.py")):
        parts.append(f"\n--- {f.name} ---\n{f.read_text()}\n")
    return "\n".join(parts)


# ── Agent factory (Copilot Responses API works for codex; Chat for everything else) ──

def _agent_for(model_id: str, *, use_responses: bool, with_tools: bool, system_prompt: str | None = None) -> Agent[None, SubmitImplementationPayload]:
    model_cls = OpenAIResponsesModel if use_responses else OpenAIChatModel
    model = model_cls(model_id, provider=_provider(), settings=_settings())
    agent: Agent[None, SubmitImplementationPayload] = Agent(
        model,
        output_type=SubmitImplementationPayload,
        system_prompt=system_prompt
        or "You are an implementer. Read the bead and the relevant files, "
        "then return a SubmitImplementationPayload describing what you "
        "would change. Use read_file and glob_files freely; do not edit.",
    )

    if with_tools:
        @agent.tool_plain
        def read_file(path: str) -> str:
            """Read a UTF-8 text file (truncated to 200 KB)."""
            return Path(path).read_text(encoding="utf-8", errors="replace")[:200_000]

        @agent.tool_plain
        def glob_files(pattern: str, cwd: str = ".") -> list[str]:
            """Find files matching a glob (max 200 results)."""
            return [str(p) for p in Path(cwd).rglob(pattern) if p.is_file()][:200]

    return agent


# ── Usage / cost extraction ─────────────────────────────────────────

def _dump_usage(result: Any) -> dict[str, Any]:
    u = result.usage() if callable(getattr(result, "usage", None)) else getattr(result, "usage", None)
    if u is None:
        return {}
    if dataclasses.is_dataclass(u):
        return dataclasses.asdict(u)
    if hasattr(u, "model_dump"):
        return u.model_dump()
    return {k: getattr(u, k, None) for k in dir(u) if not k.startswith("_")}


# ── Validations ─────────────────────────────────────────────────────


async def v1_oauth() -> dict[str, Any]:
    """Smoke: PydanticAI + Copilot Responses (codex) returns text."""
    model = OpenAIResponsesModel("gpt-5.3-codex", provider=_provider(), settings=_settings())
    agent: Agent[None, str] = Agent(model, output_type=str, system_prompt="Reply with the single word 'ready'.")
    t0 = time.monotonic()
    result = await agent.run("Reply now.")
    elapsed = time.monotonic() - t0
    final = result.output or ""
    return {
        "passed": "ready" in str(final).lower(),
        "elapsed_s": elapsed,
        "final_output": str(final)[:200],
        "model": "gpt-5.3-codex (Copilot Responses)",
        "usage": _dump_usage(result),
    }


async def v2_structured_codex() -> dict[str, Any]:
    """Codex + read tools + SubmitImplementationPayload on bead 37n.3."""
    agent = _agent_for("gpt-5.3-codex", use_responses=True, with_tools=True)
    t0 = time.monotonic()
    error: str | None = None
    output: SubmitImplementationPayload | None = None
    result: Any = None
    try:
        result = await agent.run(build_bead_prompt(TARGET_BEAD_ID))
        output = result.output
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.monotonic() - t0
    out: dict[str, Any] = {
        "model": "gpt-5.3-codex (Copilot Responses)",
        "elapsed_s": elapsed,
        "passed": isinstance(output, SubmitImplementationPayload),
        "error": error,
    }
    if isinstance(output, SubmitImplementationPayload):
        out["summary"] = output.summary[:400]
        out["files_changed"] = list(output.files_changed)
        out["files_changed_count"] = len(output.files_changed)
    if result is not None:
        out["usage"] = _dump_usage(result)
        try:
            out["message_count"] = len(result.all_messages())
        except Exception:  # noqa: BLE001
            pass
    return out


async def v3_claude_via_copilot() -> dict[str, Any]:
    """Claude via Copilot, probed through both Responses (likely 400) and Chat (validation gap)."""
    findings: dict[str, Any] = {"attempts": []}
    for label, model_cls in (("Responses", OpenAIResponsesModel), ("Chat", OpenAIChatModel)):
        model = model_cls("claude-sonnet-4.6", provider=_provider(), settings=_settings())
        agent: Agent[None, SubmitImplementationPayload] = Agent(
            model,
            output_type=SubmitImplementationPayload,
            system_prompt="When given a bead, return a SubmitImplementationPayload.",
        )
        t0 = time.monotonic()
        try:
            r = await agent.run("Return a minimal SubmitImplementationPayload with summary='probe' and files_changed=['a.py'].")
            findings["attempts"].append({
                "label": label,
                "passed": isinstance(r.output, SubmitImplementationPayload),
                "elapsed_s": time.monotonic() - t0,
                "output_repr": repr(r.output)[:300],
            })
        except Exception as exc:  # noqa: BLE001
            findings["attempts"].append({
                "label": label,
                "passed": False,
                "elapsed_s": time.monotonic() - t0,
                "error": f"{type(exc).__name__}: {exc}"[:400],
            })
    findings["passed"] = any(a.get("passed") for a in findings["attempts"])
    return findings


async def v4_prompt_cache() -> dict[str, Any]:
    """Two consecutive runs with shared seeded context; observe cache fields."""
    seeded = build_seeded_context(TARGET_BEAD_ID)
    model = OpenAIResponsesModel("gpt-5.3-codex", provider=_provider(), settings=_settings())
    agent: Agent[None, str] = Agent(
        model,
        output_type=str,
        system_prompt="Acknowledge the seeded context briefly.",
    )
    r1 = await agent.run(seeded + "\n\n[run 1] Acknowledge briefly.")
    await asyncio.sleep(2)
    r2 = await agent.run(seeded + "\n\n[run 2] Acknowledge briefly.")
    u1 = _dump_usage(r1)
    u2 = _dump_usage(r2)
    # PydanticAI usage shape: input_tokens, output_tokens, cache_read_tokens, cache_write_tokens are top-level.
    return {
        "passed": int(u2.get("cache_read_tokens") or 0) > 0,
        "seeded_char_count": len(seeded),
        "run1_input_tokens": u1.get("input_tokens"),
        "run2_input_tokens": u2.get("input_tokens"),
        "run1_cache_read": u1.get("cache_read_tokens"),
        "run2_cache_read": u2.get("cache_read_tokens"),
        "run1_cache_write": u1.get("cache_write_tokens"),
        "run2_cache_write": u2.get("cache_write_tokens"),
        "run1_usage": u1,
        "run2_usage": u2,
    }


async def v5_cost_telemetry() -> dict[str, Any]:
    """Enumerate PydanticAI's usage / cost surface."""
    model = OpenAIResponsesModel("gpt-5.3-codex", provider=_provider(), settings=_settings())
    agent: Agent[None, str] = Agent(model, output_type=str, system_prompt="Reply 'cost-probe-ok'.")
    r = await agent.run("Reply now.")
    usage = _dump_usage(r)
    return {
        "passed": True,
        "usage_keys": sorted(usage.keys()),
        "usage": usage,
        "agent_cost_parity": {
            "provider_id": None,  # not on usage; lives on the provider object
            "model_id": "gpt-5.3-codex",
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "cache_read_tokens": usage.get("cache_read_tokens"),
            "cache_write_tokens": usage.get("cache_write_tokens"),
            "cost_usd": None,  # PydanticAI doesn't compute cost
        },
    }


# ── Orchestration ───────────────────────────────────────────────────


async def main() -> int:
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print("Phase 0b spike — PydanticAI on Copilot")
    print(f"Sample project: {SAMPLE_PROJECT}")
    print(f"Target bead:    {TARGET_BEAD_ID}")
    print()
    results: dict[str, Any] = {"started_at": started_at}
    for name, fn in (
        ("v1_oauth", v1_oauth),
        ("v2_structured_codex", v2_structured_codex),
        ("v3_claude_via_copilot", v3_claude_via_copilot),
        ("v4_prompt_cache", v4_prompt_cache),
        ("v5_cost_telemetry", v5_cost_telemetry),
    ):
        print(f"running {name}...")
        try:
            results[name] = await fn()
        except Exception as exc:  # noqa: BLE001
            results[name] = {
                "passed": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        passed = results[name].get("passed")
        elapsed = results[name].get("elapsed_s")
        suffix = f" ({elapsed:.1f}s)" if isinstance(elapsed, (int, float)) else ""
        print(f"  {'PASS' if passed else 'FAIL'}{suffix}")
    results["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=str))
    print()
    print(f"Wrote results to {RESULTS_PATH}")
    print()
    print("Summary:")
    for k in ("v1_oauth", "v2_structured_codex", "v3_claude_via_copilot", "v4_prompt_cache", "v5_cost_telemetry"):
        print(f"  {k:24s} {results[k].get('passed')}")
    fails = [k for k in ("v1_oauth", "v2_structured_codex", "v4_prompt_cache") if not results[k].get("passed")]
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
