# Phase 0 Spike — OpenAI Agents SDK + LiteLLM end-to-end

**Parent doc:** [BURR.md](./BURR.md). This spike is the decision gate for
phases 1–3 of that migration.

**Goal:** prove the bottom-of-stack works for Maverick's hardest case
(one implementer bead) before committing to the migration. Surface any
blocker now while the spike is throwaway code, not Phase 1 production
code.

**Effort target:** 1–2 days, single-developer.

**Status:** Not yet started.

## What the spike is

A standalone Python script — outside `src/maverick/`, owned by the
spike author — that picks one ready bead from a known sample project,
runs it end-to-end through OpenAI Agents SDK + LiteLLM, and emits a
report covering five validations. The script does NOT integrate with
the existing Maverick runtime; it stands alone.

```
scripts/spike-openai-agents-sdk-litellm.py
```

## Prerequisites

1. `pip install "openai-agents[litellm]"` in a scratch venv (NOT
   `uv sync` against the main project — keep the spike isolated).
2. A `github-copilot` OAuth completed and credentials available. Either:
   - Reuse the existing `~/.local/share/opencode/auth.json` if the
     OAuth flow can extract them (verify in the OAuth validation below), or
   - Run LiteLLM's first-use OAuth device flow, which writes to
     `~/.config/litellm/github_copilot/`.
3. The sample project at `/workspaces/sample-maverick-project` already
   initialized with a refueled plan and at least one ready bead. (We
   have this from the e2e run that produced PR #94's validation —
   beads `sample-maverick-project-37n.3` and `37n.4` remain open.)
4. `git config user.name` / `user.email` set in the sample project
   (required for the eventual commit verification).

## Script outline

```python
# scripts/spike-openai-agents-sdk-litellm.py
"""Phase 0 spike — proves the post-migration bottom layers work end-to-end."""

import asyncio
import os
import time
from pathlib import Path

from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel

from maverick.payloads import SubmitImplementationPayload  # reuse the real payload schema
from maverick.runners.command import CommandRunner          # reuse the existing Bash wrapper

# ── Tools (minimum viable; not production-grade) ─────────────────────

def read_tool(path: str) -> str:
    """Read a file, return its content."""
    return Path(path).read_text(encoding="utf-8")

def write_tool(path: str, content: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} bytes to {path}"

def edit_tool(path: str, old: str, new: str) -> str:
    """Replace exactly one occurrence of `old` with `new` in `path`."""
    content = Path(path).read_text(encoding="utf-8")
    if content.count(old) != 1:
        raise ValueError(f"edit_tool: old-string must appear exactly once (found {content.count(old)})")
    Path(path).write_text(content.replace(old, new), encoding="utf-8")
    return f"edited {path}"

def glob_tool(pattern: str, cwd: str = ".") -> list[str]:
    """Find files matching a glob under cwd."""
    return [str(p) for p in Path(cwd).rglob(pattern) if p.is_file()][:200]

def grep_tool(pattern: str, cwd: str = ".", glob: str = "*") -> list[str]:
    """Recursive ripgrep-style search."""
    import re
    rx = re.compile(pattern)
    hits = []
    for f in Path(cwd).rglob(glob):
        if not f.is_file():
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{f}:{i}:{line}")
                    if len(hits) >= 200:
                        return hits
        except (UnicodeDecodeError, PermissionError):
            continue
    return hits

async def bash_tool(command: str, cwd: str = ".") -> dict:
    """Run a shell command via the existing CommandRunner."""
    runner = CommandRunner()
    result = await runner.run(command, cwd=cwd, timeout=120)
    return {"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode}


# ── Spike configuration ──────────────────────────────────────────────

SAMPLE_PROJECT = Path("/workspaces/sample-maverick-project")
TARGET_BEAD_ID = "sample-maverick-project-37n.3"  # rendering bead (ready, non-trivial)

PRIMARY_MODEL = "github_copilot/gpt-5.3-codex"   # what we expect to use post-migration
FALLBACK_MODEL = "openai/gpt-5.3-codex"           # for cascade simulation in validation 3


# ── Validation 1: Copilot OAuth device flow ──────────────────────────

async def validation_1_oauth() -> dict:
    """First-use OAuth device flow completes; subsequent calls use cached creds."""
    model = LitellmModel(PRIMARY_MODEL)
    # Trivial agent with no tools — just verifies the auth path works.
    agent = Agent(name="oauth-probe", model=model)
    t0 = time.monotonic()
    result = await Runner.run(agent, "Reply with the single word: ready.")
    return {
        "passed": "ready" in result.final_output.lower(),
        "elapsed_s": time.monotonic() - t0,
        "output_sample": result.final_output[:80],
    }


# ── Validation 2: structured output via output_type ──────────────────

async def validation_2_structured_output() -> dict:
    """Agent returns a typed Pydantic payload first-try, no retry loop."""
    bead_prompt = _build_bead_prompt(TARGET_BEAD_ID)
    agent = Agent(
        name="implementer-spike",
        model=LitellmModel(PRIMARY_MODEL),
        output_type=SubmitImplementationPayload,  # ← the real Maverick payload
        instructions="You are an implementer. Use the tools provided to read the bead, "
                     "explore the repo, make changes, and return a SubmitImplementationPayload.",
        tools=[read_tool, glob_tool, grep_tool, edit_tool, write_tool, bash_tool],
    )
    t0 = time.monotonic()
    result = await Runner.run(agent, bead_prompt)
    payload = result.final_output
    return {
        "passed": isinstance(payload, SubmitImplementationPayload),
        "elapsed_s": time.monotonic() - t0,
        "summary": payload.summary[:200] if payload else None,
        "files_modified": getattr(payload, "files_modified", None),
    }


# ── Validation 3: structured output + tool calling combined ──────────

# Implicit in validation_2 — the implementer agent uses tools AND returns
# a typed payload. If validation 2 passes for `github_copilot/claude-sonnet-4.6`
# and `github_copilot/gpt-5.3-codex` both, validation 3 is covered.
# Run validation_2 twice with different PRIMARY_MODEL values to cover this.


# ── Validation 4: prompt-cache hit on repeated invocation ────────────

async def validation_4_prompt_cache() -> dict:
    """Two consecutive runs with shared context → second run shows cache hit."""
    base_messages = _build_seeded_context(TARGET_BEAD_ID)  # ~10k tokens
    agent = Agent(
        name="cache-probe",
        model=LitellmModel(PRIMARY_MODEL),
        instructions="Briefly acknowledge the context, do not call tools.",
    )
    # First call — populates cache.
    r1 = await Runner.run(agent, base_messages + [{"role": "user", "content": "Run 1: acknowledge."}])
    # Second call — same prefix, should be a cache read.
    r2 = await Runner.run(agent, base_messages + [{"role": "user", "content": "Run 2: acknowledge."}])
    # Inspect usage fields. LiteLLM normalizes usage on `response.usage`; cache fields
    # depend on provider — `prompt_tokens_details.cached_tokens` for OpenAI,
    # `cache_read_input_tokens` for Anthropic-via-Copilot.
    return {
        "run1_input_tokens": _extract_input_tokens(r1),
        "run2_input_tokens": _extract_input_tokens(r2),
        "run1_cached": _extract_cached_tokens(r1),
        "run2_cached": _extract_cached_tokens(r2),
        "passed": _extract_cached_tokens(r2) > 0,  # second run must hit cache
    }


# ── Validation 5: cost telemetry surface ─────────────────────────────

async def validation_5_cost_telemetry() -> dict:
    """`agent.cost`-shaped fields are reachable from the result."""
    agent = Agent(name="cost-probe", model=LitellmModel(PRIMARY_MODEL))
    result = await Runner.run(agent, "Reply with: cost-probe-ok.")
    # The interesting question is whether we can fish out:
    #   provider_id, model_id, input_tokens, output_tokens,
    #   cache_read_tokens, cache_write_tokens, cost_usd
    # from `result.usage` / `result.raw_responses` / LiteLLM's hidden_params.
    return {
        "passed": True,
        "usage_keys": _enumerate_usage(result),
        "cost_usd_path": _find_cost_usd_path(result),
        "notes": "see report; cost telemetry parity is informational, not a blocker",
    }


# ── Orchestration ────────────────────────────────────────────────────

async def main() -> None:
    print("Phase 0 spike — OpenAI Agents SDK + LiteLLM + Copilot")
    print(f"Sample project: {SAMPLE_PROJECT}")
    print(f"Target bead: {TARGET_BEAD_ID}")
    print(f"Primary model: {PRIMARY_MODEL}")
    print()

    results = {}
    for name, fn in (
        ("v1_oauth", validation_1_oauth),
        ("v2_structured_output", validation_2_structured_output),
        ("v4_prompt_cache", validation_4_prompt_cache),
        ("v5_cost_telemetry", validation_5_cost_telemetry),
    ):
        print(f"running {name}...")
        try:
            results[name] = await fn()
            print(f"  {'PASS' if results[name]['passed'] else 'FAIL'}: "
                  f"{results[name].get('elapsed_s', '?'):.1f}s" if 'elapsed_s' in results[name]
                  else f"  {'PASS' if results[name]['passed'] else 'FAIL'}")
        except Exception as exc:
            results[name] = {"passed": False, "error": str(exc)}
            print(f"  FAIL: {exc}")

    # Validation 3: re-run v2 with the second model.
    global PRIMARY_MODEL
    PRIMARY_MODEL = "github_copilot/claude-sonnet-4.6"
    print(f"\nrunning v3_structured_output_claude (model={PRIMARY_MODEL})...")
    try:
        results["v3_structured_output_claude"] = await validation_2_structured_output()
    except Exception as exc:
        results["v3_structured_output_claude"] = {"passed": False, "error": str(exc)}

    _write_report(results)


if __name__ == "__main__":
    asyncio.run(main())
```

Helper functions (`_build_bead_prompt`, `_build_seeded_context`,
`_extract_input_tokens`, `_extract_cached_tokens`, `_enumerate_usage`,
`_find_cost_usd_path`, `_write_report`) are simple shims around the
sample project's bead reader and the OpenAI Agents SDK `RunResult` /
LiteLLM response shapes — flesh out during the spike.

## The five validations

### V1 — Copilot OAuth device flow works in our dev environment

**Why it matters:** the whole migration assumes we can reach
`github_copilot/*` from in-process Python in our containerized dev
setup. If LiteLLM's OAuth flow can't complete (e.g., device-flow URL
unreachable from inside the container), the primary subscription route
fails and we need a different strategy.

**Pass criteria:**
- A single `Runner.run(agent, ...)` against `LitellmModel("github_copilot/<model>")`
  returns a valid response.
- Subsequent runs reuse cached creds without re-prompting.

**Fail modes:**
- OAuth flow demands a browser interaction unavailable in the container
  → document the workaround (forward port, paste device code) and
  proceed.
- LiteLLM cannot find the existing OpenCode-auth creds → run the OAuth
  flow fresh; acceptable cost.
- Auth completes but the call returns 401 → Copilot OAuth scope mismatch;
  investigate before proceeding.

### V2 — Structured output via `output_type=SubmitImplementationPayload`

**Why it matters:** typed Pydantic payloads are non-negotiable for
Maverick. Every agent role today returns a `Submit*Payload` validated
by OpenCode's `format=json_schema`. If the OpenAI Agents SDK can't
deliver this first-try with a tool-using agent, the whole migration
loses its core property.

**Pass criteria:**
- `result.final_output` is an instance of `SubmitImplementationPayload`.
- No retry loop fires (success on first attempt).
- The payload is non-trivial (non-empty `files_modified`, non-empty
  `summary`).

**Fail modes:**
- The model returns text instead of a structured payload → check that
  `output_type=` was honored; verify provider support for structured
  output via LiteLLM (the [Gemini issue](https://github.com/openai/openai-agents-python/issues/1575)
  was Gemini-specific but verify for our bindings).
- The payload validates but is empty / hallucinated → tooling problem,
  not framework problem; tune prompts.
- The payload fails Pydantic validation → may be intermittent; capture
  the raw output and assess.

### V3 — Structured output + tools combined for both primary bindings

**Why it matters:** the known compatibility gap is specifically
"structured output + tool calling together." Our two front-of-line
bindings are `github_copilot/gpt-5.3-codex` (implement) and
`github_copilot/claude-sonnet-4.6` (decompose/generate). Both must work.

**Pass criteria:**
- V2 passes for `github_copilot/gpt-5.3-codex`.
- V2 passes for `github_copilot/claude-sonnet-4.6`.

**Fail modes:**
- One of the two fails → fall back to its corresponding `openai/*`
  binding for the role; acceptable but reduces subscription leverage.
- Both fail → serious problem; consider Instructor + LiteLLM + custom
  loop as the Stack 2 fallback (see [BURR.md](./BURR.md) alternatives).

### V4 — Anthropic / OpenAI prompt cache engages across runs

**Why it matters:** Maverick's decomposer relies on warm cache across
the outline → detail handoff. Implementer's fix loop relies on warm
cache across review → fix turns. A 10–30k token seeded context that
*doesn't* cache costs 4–10× more per call.

**Pass criteria:**
- Second run's usage shows `cached_tokens > 0` (OpenAI) or
  `cache_read_input_tokens > 0` (Anthropic-via-Copilot).
- The cached fraction is meaningful (>50% of the prefix).

**Fail modes (and what each means):**
- **Cache works transparently** → great, no wiring needed beyond
  `message_history`. Migration is clean.
- **Cache works but needs explicit markers** → small wiring effort in
  the Maverick `Agent` layer to add `cache_control` markers around
  seeded context. Tractable; add to Phase 1 scope.
- **Cache doesn't engage at all** → reroute cache-sensitive paths
  (decomposer, implementer fix loop) to `openai/gpt-5.x` in
  `DEFAULT_TIERS`. Copilot stays as primary for non-cache-sensitive
  roles. Document as a Phase 1 constraint.

### V5 — Cost-telemetry surface

**Why it matters:** today's `agent.cost` structured log row carries
`provider_id`, `model_id`, `input_tokens`, `output_tokens`,
`cache_read_tokens`, `cache_write_tokens`, `cost_usd`. Maverick's
runway store records this per bead for cost forecasting.

**Pass criteria:** all seven fields are reachable from `result.usage` /
LiteLLM's `_hidden_params["response_cost"]` or equivalent.

**Fail modes:**
- All fields reachable → no work needed.
- Token counts but no `cost_usd` → we maintain our own cost table
  per `(provider, model)` and compute it ourselves. Annoying, not
  blocking.
- Token counts missing → unlikely; if it happens, fall back to
  consulting raw responses; flag as a Phase 1 concern.

This is the only validation whose failure is **non-blocking**. We can
proceed without cost telemetry parity if necessary.

## Decision gate

After all five validations:

| V1 | V2 | V3 | V4 | V5 | Decision |
|---|---|---|---|---|---|
| pass | pass | pass | pass | pass | **Proceed to Phase 1** as planned |
| pass | pass | pass | pass | fail | **Proceed to Phase 1**, wire cost telemetry ourselves |
| pass | pass | pass | partial | * | **Proceed to Phase 1**, document cache constraints in `DEFAULT_TIERS` |
| pass | pass | partial | * | * | **Proceed to Phase 1** with reduced Copilot leverage for one binding |
| pass | pass | fail | * | * | **Reconsider** — Stack 2 (Instructor + LiteLLM + custom loop) fallback |
| pass | fail | * | * | * | **Abort migration as planned** — typed-output guarantee is non-negotiable; re-evaluate |
| fail | * | * | * | * | **Abort migration as planned** — primary subscription path unavailable; re-evaluate |

The "reconsider" path doesn't mean stay on OpenCode — it means revisit
the framework choice with V3 evidence in hand.

## Deliverables

1. `scripts/spike-openai-agents-sdk-litellm.py` — the spike script
   (~300 LOC including helpers).
2. `docs/migration-phase-0-report.md` — a one-page report covering:
   - Each validation's pass/fail with timing and notes.
   - The raw OAuth credential location (so Phase 1 knows where to read).
   - The exact LiteLLM model strings that worked / failed.
   - Cache field paths for the providers tested.
   - Cost telemetry field paths.
   - Any gotchas worth flagging to Phase 1.
3. A go / no-go recommendation against the decision-gate table.

The script and report live in-repo so Phase 1 can build on them.

## Out of scope for Phase 0

- Burr is NOT involved. Phase 0 validates Slots A–C only.
- Tool implementations are MVP — production-grade Read/Write/Edit/Glob/
  Grep/Bash/Task come in Phase 1c.
- Subagent / `as_tool()` patterns are NOT validated here. The
  implementer doesn't spawn subagents for a single bead; that's a
  decomposer / fanout concern handled separately in Phase 1.
- `MaverickCascadingModel` (~200 LOC tier-cascade wrapper) is NOT
  validated here. We test the primary binding only. The cascade is
  algorithmically identical to today's `cascade_send` and is built in
  Phase 1a.
- No integration with the existing Maverick runtime. The spike is
  throwaway.

## Pre-commit checklist for the spike author

Before declaring Phase 0 done:

- [ ] Spike script runs successfully against `sample-maverick-project`.
- [ ] All five validations executed (report includes results for each).
- [ ] OAuth credential path documented.
- [ ] Cache field paths documented per provider.
- [ ] Decision recorded against the decision-gate table.
- [ ] Report committed to `docs/migration-phase-0-report.md`.
- [ ] Findings shared with the team before Phase 1 kickoff.
