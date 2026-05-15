#!/usr/bin/env python3
"""Phase 0 spike — OpenAI Agents SDK + LiteLLM end-to-end probe.

Throwaway proof code that runs once and produces a report. Lives outside
``src/maverick/`` so the production substrate is untouched.

Run via the scratch venv set up in the spike runbook::

    python -m venv /tmp/spike-venv
    source /tmp/spike-venv/bin/activate
    pip install "openai-agents[litellm]"
    pip install -e /workspaces/maverick   # for maverick.payloads
    python scripts/spike-openai-agents-sdk-litellm.py

See docs/migration-phase-0-spike.md for the validation list and decision
gate. The script writes a JSON results file next to itself and prints a
markdown-formatted summary so the report can be authored from evidence.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

# --- Path setup so the spike venv finds maverick payloads ---------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agents import Agent, AgentOutputSchema, Runner, function_tool  # noqa: E402
from agents.extensions.models.litellm_model import LitellmModel  # noqa: E402
from agents.model_settings import ModelSettings  # noqa: E402

from maverick.payloads import SubmitImplementationPayload  # noqa: E402

# OpenAI Agents SDK overrides `User-Agent` to "Agents/Python 0.17.2" via
# `extra_headers`. Copilot's Chat Completions endpoint (the Claude path)
# 400s with "missing Editor-Version header for IDE auth" when the
# user-agent isn't "GithubCopilot/*"; the Responses endpoint (codex)
# accepts it. We re-inject the three IDE-auth headers on every agent so
# Claude works. Phase 1 will need to do the same in `MaverickCascadingModel`
# (or monkey-patch the SDK).
COPILOT_COMPAT_HEADERS = {
    "User-Agent": "GithubCopilot/1.155.0",
    "editor-version": "vscode/1.95.0",
    "editor-plugin-version": "copilot/1.155.0",
}


def copilot_compat_settings(**overrides: Any) -> ModelSettings:
    """Build a ModelSettings with Copilot IDE-auth headers pre-merged."""
    headers = dict(COPILOT_COMPAT_HEADERS)
    headers.update(overrides.pop("extra_headers", {}) or {})
    return ModelSettings(extra_headers=headers, **overrides)

# --- Spike configuration ------------------------------------------------------

SAMPLE_PROJECT = Path("/workspaces/sample-maverick-project")
TARGET_BEAD_ID = "sample-maverick-project-37n.3"

# Validate both primary bindings for V3; V2 uses the first.
MODELS_TO_PROBE = [
    "github_copilot/gpt-5.3-codex",
    "github_copilot/claude-sonnet-4.6",
]

RESULTS_PATH = Path(__file__).with_suffix(".results.json")
OPENCODE_AUTH = Path.home() / ".local" / "share" / "opencode" / "auth.json"
LITELLM_TOKEN_DIR = Path.home() / ".config" / "litellm" / "github_copilot"


# --- OAuth bootstrap ----------------------------------------------------------


def bootstrap_litellm_creds() -> dict[str, Any]:
    """Seed LiteLLM's Copilot credential file from OpenCode's auth.json if absent.

    LiteLLM reads ``~/.config/litellm/github_copilot/access-token`` (the
    GitHub OAuth ``ghu_…`` token) and refreshes its own Copilot API key
    on first use. OpenCode stores the same OAuth token under
    ``github-copilot.refresh`` in its auth.json. If LiteLLM's file is
    missing we copy across; if it's present we leave it alone.
    """
    info: dict[str, Any] = {
        "opencode_auth_exists": OPENCODE_AUTH.exists(),
        "litellm_token_dir": str(LITELLM_TOKEN_DIR),
        "litellm_access_token_existed": (LITELLM_TOKEN_DIR / "access-token").exists(),
        "litellm_api_key_existed": (LITELLM_TOKEN_DIR / "api-key.json").exists(),
        "bootstrapped": False,
    }
    access_file = LITELLM_TOKEN_DIR / "access-token"
    if access_file.exists():
        return info
    if not OPENCODE_AUTH.exists():
        info["error"] = f"no opencode auth.json at {OPENCODE_AUTH}"
        return info
    try:
        auth = json.loads(OPENCODE_AUTH.read_text())
        refresh = auth.get("github-copilot", {}).get("refresh")
        if not refresh:
            info["error"] = "opencode auth.json missing github-copilot.refresh"
            return info
        LITELLM_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        access_file.write_text(refresh)
        info["bootstrapped"] = True
        return info
    except Exception as exc:  # noqa: BLE001 - report all failures
        info["error"] = f"{type(exc).__name__}: {exc}"
        return info


# --- Tools (MVP, not production-grade) ----------------------------------------


@function_tool
def read_file(path: str) -> str:
    """Read a UTF-8 text file and return its contents (truncated to 200 KB)."""
    data = Path(path).read_text(encoding="utf-8", errors="replace")
    return data[:200_000]


@function_tool
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories. Returns a status string."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} bytes to {path}"


@function_tool
def edit_file(path: str, old: str, new: str) -> str:
    """Replace exactly one occurrence of ``old`` with ``new`` in ``path``."""
    content = Path(path).read_text(encoding="utf-8")
    if content.count(old) != 1:
        return (
            f"ERROR: old-string must appear exactly once in {path} "
            f"(found {content.count(old)})"
        )
    Path(path).write_text(content.replace(old, new), encoding="utf-8")
    return f"edited {path}"


@function_tool
def glob_files(pattern: str, cwd: str = ".") -> list[str]:
    """Find files matching a glob under cwd (max 200 results)."""
    base = Path(cwd)
    return [str(p) for p in base.rglob(pattern) if p.is_file()][:200]


@function_tool
def grep_text(pattern: str, cwd: str = ".", glob: str = "*") -> list[str]:
    """Search files under cwd for a regex pattern; returns ``path:line:text`` rows (max 200)."""
    rx = re.compile(pattern)
    hits: list[str] = []
    for f in Path(cwd).rglob(glob):
        if not f.is_file():
            continue
        try:
            for i, line in enumerate(
                f.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if rx.search(line):
                    hits.append(f"{f}:{i}:{line[:200]}")
                    if len(hits) >= 200:
                        return hits
        except (UnicodeDecodeError, PermissionError, OSError):
            continue
    return hits


@function_tool
def run_bash(command: str, cwd: str = ".", timeout: int = 120) -> dict[str, Any]:
    """Run a shell command. Returns ``{stdout, stderr, exit_code, timed_out}``."""
    try:
        result = subprocess.run(  # noqa: S602 - intentional shell for tool fidelity
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "stdout": result.stdout[:10_000],
            "stderr": result.stderr[:10_000],
            "exit_code": result.returncode,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "timeout", "exit_code": -1, "timed_out": True}


TOOLS = [read_file, write_file, edit_file, glob_files, grep_text, run_bash]


# --- Prompt helpers -----------------------------------------------------------


def _load_bead(bead_id: str) -> dict[str, Any]:
    issues = (SAMPLE_PROJECT / ".beads" / "issues.jsonl").read_text().splitlines()
    for raw in issues:
        d = json.loads(raw)
        if d.get("id") == bead_id and d.get("_type") == "issue":
            return d
    raise RuntimeError(f"bead {bead_id} not found")


def build_bead_prompt(bead_id: str) -> str:
    bead = _load_bead(bead_id)
    return (
        f"You are an implementer working on bead {bead_id} in the project "
        f"at {SAMPLE_PROJECT}.\n\n"
        f"BEAD TITLE: {bead['title']}\n\n"
        f"BEAD DESCRIPTION:\n{bead['description']}\n\n"
        f"Use the tools to read the existing code under "
        f"{SAMPLE_PROJECT}/src/greet_cli/ and {SAMPLE_PROJECT}/tests/, then "
        f"make the code changes the bead requires. Keep edits focused and "
        f"avoid touching unrelated files. When you are done, return a "
        f"SubmitImplementationPayload with a short summary and the list of "
        f"files you changed (relative to {SAMPLE_PROJECT}).\n\n"
        f"Constraints:\n"
        f"- All paths must live under {SAMPLE_PROJECT}.\n"
        f"- You MUST end by returning the structured payload; do not just "
        f"  describe what you would do.\n"
        f"- Do not run git commits; that is verified separately."
    )


def build_seeded_context(bead_id: str) -> str:
    """Build a ~10k-token prompt for the cache probe.

    We don't need tool use here — a long stable prefix is enough to detect
    cache reads. Mix the bead description with the actual project source.
    """
    bead = _load_bead(bead_id)
    parts = [
        "You are a cache probe. Acknowledge this seeded context briefly.",
        f"Bead {bead_id}: {bead['title']}",
        bead["description"],
    ]
    src_root = SAMPLE_PROJECT / "src" / "greet_cli"
    for f in sorted(src_root.glob("*.py")):
        parts.append(f"\n--- {f.name} ---\n{f.read_text()}\n")
    tests_root = SAMPLE_PROJECT / "tests"
    for f in sorted(tests_root.glob("test_*.py")):
        parts.append(f"\n--- {f.name} ---\n{f.read_text()}\n")
    return "\n".join(parts)


# --- Usage / cost extraction --------------------------------------------------


def _dump_usage(result: Any) -> list[dict[str, Any]]:
    """Walk RunResult.raw_responses and pull every Usage into a plain dict."""
    rows: list[dict[str, Any]] = []
    for resp in getattr(result, "raw_responses", []) or []:
        usage = getattr(resp, "usage", None)
        if usage is None:
            continue
        row: dict[str, Any] = {
            "requests": getattr(usage, "requests", None),
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
        details_in = getattr(usage, "input_tokens_details", None)
        if details_in is not None:
            row["input_tokens_details"] = (
                details_in.model_dump()
                if hasattr(details_in, "model_dump")
                else dict(details_in.__dict__)
            )
        details_out = getattr(usage, "output_tokens_details", None)
        if details_out is not None:
            row["output_tokens_details"] = (
                details_out.model_dump()
                if hasattr(details_out, "model_dump")
                else dict(details_out.__dict__)
            )
        req_entries = getattr(usage, "request_usage_entries", None) or []
        if req_entries:
            row["request_usage_entries"] = [
                (
                    e.model_dump()
                    if hasattr(e, "model_dump")
                    else dataclasses.asdict(e)
                    if dataclasses.is_dataclass(e)
                    else dict(getattr(e, "__dict__", {}))
                )
                for e in req_entries
            ]
        rows.append(row)
    return rows


def _extract_cached_tokens(result: Any) -> int:
    total = 0
    for row in _dump_usage(result):
        details = row.get("input_tokens_details") or {}
        total += int(details.get("cached_tokens", 0) or 0)
    return total


def _extract_input_tokens(result: Any) -> int:
    return sum(int(r.get("input_tokens") or 0) for r in _dump_usage(result))


def _find_cost_usd(result: Any) -> dict[str, Any]:
    """Hunt for cost_usd / response_cost across the result tree."""
    found: dict[str, Any] = {"paths": [], "values": []}
    for i, resp in enumerate(getattr(result, "raw_responses", []) or []):
        # OpenAI Agents SDK doesn't surface LiteLLM's hidden_params directly;
        # snapshot every attribute we can find for the report.
        for attr in dir(resp):
            if attr.startswith("_"):
                continue
            try:
                val = getattr(resp, attr)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(val, dict) and "response_cost" in val:
                found["paths"].append(f"raw_responses[{i}].{attr}.response_cost")
                found["values"].append(val.get("response_cost"))
        usage = getattr(resp, "usage", None)
        for attr in ("cost", "cost_usd", "response_cost"):
            v = getattr(usage, attr, None) if usage is not None else None
            if v is not None:
                found["paths"].append(f"raw_responses[{i}].usage.{attr}")
                found["values"].append(v)
    return found


# --- Validations --------------------------------------------------------------


async def validation_1_oauth() -> dict[str, Any]:
    """Smoke test: cheapest call against primary Copilot binding returns text."""
    model = LitellmModel(MODELS_TO_PROBE[0])
    agent = Agent(
        name="oauth-probe",
        model=model,
        model_settings=copilot_compat_settings(),
    )
    t0 = time.monotonic()
    result = await Runner.run(
        agent,
        "Reply with the single word: ready.",
        max_turns=2,
    )
    elapsed = time.monotonic() - t0
    final = result.final_output or ""
    return {
        "passed": "ready" in str(final).lower(),
        "elapsed_s": elapsed,
        "model": MODELS_TO_PROBE[0],
        "final_output": str(final)[:200],
        "usage": _dump_usage(result),
    }


async def validation_2or3_structured(model_str: str) -> dict[str, Any]:
    """Typed-output + tool-using agent end-to-end on bead 37n.3."""
    prompt = build_bead_prompt(TARGET_BEAD_ID)
    # SubmitImplementationPayload has a `files_changed` field with a default
    # factory, which the OpenAI Agents SDK strict-schema generator rejects
    # (strict mode requires every field to be `required`). Wrapping with
    # `strict_json_schema=False` is the documented escape hatch; this is the
    # exact migration cost we'd pay in Phase 1 for any payload with optional
    # fields.
    agent = Agent(
        name=f"implementer-spike-{model_str.split('/')[-1]}",
        model=LitellmModel(model_str),
        output_type=AgentOutputSchema(
            SubmitImplementationPayload, strict_json_schema=False
        ),
        instructions=(
            "You are an implementer. Use the tools provided to read the bead, "
            "explore the repo, make focused edits, and return a "
            "SubmitImplementationPayload describing what you changed."
        ),
        tools=TOOLS,
        model_settings=copilot_compat_settings(),
    )
    t0 = time.monotonic()
    raw_final: Any = None
    error: str | None = None
    payload_passed = False
    try:
        result = await Runner.run(agent, prompt, max_turns=40)
        raw_final = result.final_output
        payload_passed = isinstance(raw_final, SubmitImplementationPayload)
    except Exception as exc:  # noqa: BLE001 - we want the raw failure in the report
        result = None
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.monotonic() - t0
    out: dict[str, Any] = {
        "model": model_str,
        "elapsed_s": elapsed,
        "passed": payload_passed,
        "error": error,
    }
    if isinstance(raw_final, SubmitImplementationPayload):
        out["summary"] = raw_final.summary[:400]
        out["files_changed"] = list(raw_final.files_changed)
        out["files_changed_count"] = len(raw_final.files_changed)
    elif raw_final is not None:
        # Capture raw output verbatim so Stack 2 fallback can be assessed.
        out["raw_final_repr"] = repr(raw_final)[:2000]
    if result is not None:
        out["usage"] = _dump_usage(result)
        out["new_items_count"] = len(getattr(result, "new_items", []) or [])
        out["raw_responses_count"] = len(getattr(result, "raw_responses", []) or [])
    return out


async def validation_4_prompt_cache() -> dict[str, Any]:
    """Two consecutive runs with shared context; second must show cache hit."""
    seeded = build_seeded_context(TARGET_BEAD_ID)
    # Plain-text agent — we just want to drive the cache path, no tools.
    agent = Agent(
        name="cache-probe",
        model=LitellmModel(MODELS_TO_PROBE[0]),
        instructions="Acknowledge the seeded context in one short sentence.",
        model_settings=copilot_compat_settings(),
    )
    seed_chars = len(seeded)
    r1 = await Runner.run(
        agent,
        seeded + "\n\n[run 1] Acknowledge briefly.",
        max_turns=2,
    )
    # Brief pause — cache write needs a beat to materialize on some providers.
    await asyncio.sleep(2)
    r2 = await Runner.run(
        agent,
        seeded + "\n\n[run 2] Acknowledge briefly.",
        max_turns=2,
    )
    r1_cached = _extract_cached_tokens(r1)
    r2_cached = _extract_cached_tokens(r2)
    return {
        "passed": r2_cached > 0,
        "model": MODELS_TO_PROBE[0],
        "seeded_char_count": seed_chars,
        "run1_input_tokens": _extract_input_tokens(r1),
        "run2_input_tokens": _extract_input_tokens(r2),
        "run1_cached_tokens": r1_cached,
        "run2_cached_tokens": r2_cached,
        "run1_usage": _dump_usage(r1),
        "run2_usage": _dump_usage(r2),
    }


async def validation_5_cost_telemetry() -> dict[str, Any]:
    """Enumerate the usage / cost surface available on a RunResult."""
    agent = Agent(
        name="cost-probe",
        model=LitellmModel(MODELS_TO_PROBE[0]),
        model_settings=copilot_compat_settings(),
    )
    result = await Runner.run(agent, "Reply with: cost-probe-ok.", max_turns=2)
    usage_rows = _dump_usage(result)
    usage_keys = sorted({k for row in usage_rows for k in row})
    cost = _find_cost_usd(result)
    # The seven fields Maverick logs today via agent.cost.
    parity = {
        "provider_id": None,  # not on usage; lives in model_str
        "model_id": MODELS_TO_PROBE[0],
        "input_tokens": next((r.get("input_tokens") for r in usage_rows), None),
        "output_tokens": next((r.get("output_tokens") for r in usage_rows), None),
        "cache_read_tokens": _extract_cached_tokens(result),
        "cache_write_tokens": None,  # not exposed via openai-agents Usage
        "cost_usd": cost["values"][0] if cost["values"] else None,
    }
    return {
        "passed": True,  # informational; never fails the gate by itself
        "usage_keys": usage_keys,
        "usage_rows": usage_rows,
        "cost_paths": cost["paths"],
        "cost_values": cost["values"],
        "agent_cost_parity": parity,
        "agent_cost_parity_reachable": [
            k for k, v in parity.items() if v is not None
        ],
        "agent_cost_parity_missing": [k for k, v in parity.items() if v is None],
    }


# --- Orchestration ------------------------------------------------------------


async def main() -> int:
    bootstrap = bootstrap_litellm_creds()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    print("Phase 0 spike — OpenAI Agents SDK + LiteLLM + Copilot")
    print(f"Sample project: {SAMPLE_PROJECT}")
    print(f"Target bead:    {TARGET_BEAD_ID}")
    print(f"Models:         {MODELS_TO_PROBE}")
    print(f"Bootstrap:      {bootstrap}")
    print()

    results: dict[str, Any] = {
        "started_at": started_at,
        "bootstrap": bootstrap,
        "models_probed": MODELS_TO_PROBE,
    }

    async def _run(name: str, coro: Any) -> None:
        print(f"running {name}...")
        try:
            results[name] = await coro
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

    await _run("v1_oauth", validation_1_oauth())
    await _run("v2_structured_codex", validation_2or3_structured(MODELS_TO_PROBE[0]))
    await _run("v3_structured_claude", validation_2or3_structured(MODELS_TO_PROBE[1]))
    await _run("v4_prompt_cache", validation_4_prompt_cache())
    await _run("v5_cost_telemetry", validation_5_cost_telemetry())

    results["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=str))
    print()
    print(f"Wrote results to {RESULTS_PATH}")
    print()
    print("Summary:")
    print(f"  V1 OAuth:                {results['v1_oauth'].get('passed')}")
    print(f"  V2 codex structured:     {results['v2_structured_codex'].get('passed')}")
    print(f"  V3 claude structured:    {results['v3_structured_claude'].get('passed')}")
    print(f"  V4 prompt cache:         {results['v4_prompt_cache'].get('passed')}")
    print(f"  V5 cost telemetry:       {results['v5_cost_telemetry'].get('passed')}")
    fails = [
        k
        for k in (
            "v1_oauth",
            "v2_structured_codex",
            "v3_structured_claude",
            "v4_prompt_cache",
        )
        if not results[k].get("passed")
    ]
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
