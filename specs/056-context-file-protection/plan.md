# Implementation Plan: Context File Protection

**Branch**: `056-context-file-protection` | **Date**: 2026-08-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/056-context-file-protection/spec.md`

## Summary

Prevent agents from modifying agent-context files (`AGENTS.md`, `CLAUDE.md`,
`.specify/memory/**`) anywhere in the repository, via two enforcement layers
that together make the guarantee universal:

1. **Pre-write blocking** through airframe's `PermissionCallback` — a small
   **precursor change in airframe** (explicitly authorized) makes the Claude
   adapter gate tool calls through its already-registered `PreToolUse` hooks
   when a permission callback is attached (today those hooks are
   observation-only and `permission_mode="bypassPermissions"` short-circuits
   `can_use_tool`). Maverick's `Agent` base moves from `runtime.execute()` to
   holding an `AgentSession` so the callback can be attached at all. Providers
   that decline permission callbacks (OpenCode/OpenRouter family) simply skip
   this layer.
2. **Post-step detect-and-restore backstop** in Maverick — deterministic,
   provider-independent, wrapped around every agent execution in the `Agent`
   base class: snapshot protected-file state before the model call, re-scan
   after, restore any unauthorized mutation, record a block event. This is the
   layer that makes the spec's guarantee absolute (SC-001, SC-006) regardless
   of provider capabilities or write channel (shell commands included).

All policy logic lives in a new `src/maverick/protection/` package: a
deterministic path matcher (resolved repo-relative paths, case-insensitive
default names, `pathspec` for configured globs), a snapshot/restore engine,
typed block records, and a lenient config loader that degrades to defaults on
malformed input. Blocks accumulate per run, surface as one end-of-run warning,
and persist to `.maverick/runs/<run-id>/protection-blocks.json`. Zero model
calls anywhere in this feature.

## Technical Context

**Language/Version**: Python 3.11+ (`from __future__ import annotations`)

**Primary Dependencies**: airframe-agents **>= 0.9.2** (Claude adapter
permission gating shipped 2026-08-07 — see `contracts/airframe-precursor.md`;
bumped from 0.9.0rc1 at setup); Pydantic v2 (config models); Burr (fly
state slot); structlog; `pathspec` (**new dependency** — canonical
gitignore-style `**` matching for configured globs; stdlib `fnmatch` crosses
`/` and is case-sensitive, so it cannot express the spec's semantics)

**Storage**: files only — `.maverick/runs/<run-id>/protection-blocks.json`
(run-scoped block audit artifact); `spec-chain.json` gains a
`protection_blocks` field for the spec-chain workflow

**Testing**: pytest + pytest-asyncio (`asyncio_mode=auto`) + xdist; unit tests
mirror `src/` layout (`tests/unit/protection/`, `tests/unit/config/`,
`tests/unit/workflows/fly_beads/`); integration test with the stub-runtime
fixture (`tests/unit/workflows/conftest.py::stub_squadron_io` pattern)

**Target Platform**: Linux/macOS developer checkouts (same as all Maverick
commands); applies inside the spec-chain hidden jj workspace too

**Project Type**: single Python package (CLI + library), existing repo

**Performance Goals**: backstop overhead ≤ ~100 ms per agent step on a 10k-file
tree (one pruned `os.walk` + hash compare of a handful of files, offloaded via
`asyncio.to_thread`) — negligible against multi-minute model calls

**Constraints**: fail closed for the protected set, fail open for everything
else (FR-011); blocked write ≠ bead failure (FR-004); no assumption-ledger or
land-gate interaction (FR-005); malformed config degrades to defaults + warning
(FR-012); zero model calls (Principle XIII)

**Scale/Scope**: protected set is small (two names at any depth + one tree +
user globs); repos up to ~50k files must not see measurable slowdown

## Constitution Check

*GATE: evaluated against `.specify/memory/constitution.md` before Phase 0;
re-checked after Phase 1 design.*

| Gate | Verdict | Notes |
| --- | --- | --- |
| I. Async-first (Guardrail 1) | PASS | Snapshot/scan/restore file IO runs via `asyncio.to_thread`; no `subprocess.run` on async paths (no subprocess needed at all — the backstop is pure-Python file IO, deliberately VCS-free so it works in the non-colocated spec-chain workspace). |
| II. Separation of concerns (Guardrail 2) | PASS w/ justification | The backstop lives in the `Agent` base's execute path. This is deliberate and justified in Complexity Tracking: protection is a property of the agent's runtime scope (like the structured-output validation and cost telemetry the base class already owns), not workflow business logic — and the Agent seam is the only single point that covers every role in every workflow (FR-009). Agents still own zero *workflow* side effects: block records are drained and persisted by workflows/CLI. |
| III. Dependency injection | PASS | `ProtectionPolicy` is constructed once from config at squadron open and injected into agents; no global state. |
| IV. Fail gracefully (Guardrail 4) | PASS | Backstop restore is real (writes bytes back, verified in tests); hook-infrastructure errors deny protected writes and allow unprotected ones (FR-011). A blocked write never crashes a workflow. |
| V. Test-first | PASS | Red-green per module; matcher/snapshot/restore are pure functions with exhaustive unit matrices (SC-001's operation × target × depth × channel grid). |
| VI. Type safety (Guardrail 3) | PASS | `BlockRecord` frozen dataclass with `to_dict()`; `ProtectionConfig` Pydantic model; new `ContextFileWriteBlocked` event registered in `_EVENT_CLASSES`. |
| VII/XI. Simplicity, modularize early | PASS | New focused package `src/maverick/protection/` (~5 small modules); the orphaned `maverick.hooks` stubs are retired rather than accreted onto (see research R3). |
| VIII/XII. Relentless progress / ownership | PASS | The dead `create_safety_hooks()` stubs and unwired `HookConfig` are cleaned up as part of this feature, not left as a second protection surface. |
| IX. Hardening (Guardrail 8) | PASS | Canonical libraries: `pathspec` for glob semantics (new, justified — no hand-rolled matcher), `structlog` logging, `atomic_write_text` for restores. No new subprocess wrappers. |
| X. Guardrail 0/7 (cwd threading) | PASS | Policy root is the agent's `cwd` (checkout or workspace), threaded from the CLI boundary exactly as today; no `Path.cwd()` in workflows. |
| X. Guardrail 10 / XIII. Determinism | PASS | Zero model calls. Block records get their own state slot (`protection_blocks`) — never shared with fixer-feeding slots, so an uncloseable condition can't reach a fix loop. Matching is deterministic parsing, not inference. |

**Post-Phase-1 re-check**: PASS — design artifacts introduce no new
violations; the single justified deviation (backstop in Agent base) is
recorded below.

## Project Structure

### Documentation (this feature)

```text
specs/056-context-file-protection/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── protection-config.md     # maverick.yaml `protection:` block schema
│   ├── block-event.md           # ContextFileWriteBlocked event + protection-blocks.json schema
│   └── airframe-precursor.md    # required airframe changes (separate repo, pinned release)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/maverick/
├── protection/                  # NEW package — all policy logic
│   ├── __init__.py              #   public surface re-exports
│   ├── policy.py                #   ProtectionPolicy: effective rule set, decide(path, op)
│   ├── matching.py              #   resolved-path normalization + default-name/tree/pathspec matching
│   ├── snapshot.py              #   pre-step manifest capture, post-step scan, restore
│   ├── records.py               #   BlockRecord frozen dataclass, BlockCollector sink
│   └── config.py                #   lookup_protection_config() lenient loader (lookup_* idiom)
├── config.py                    # + `protection` raw block on MaverickConfig (lazy-validated)
├── events.py                    # + ContextFileWriteBlocked event (+ _EVENT_CLASSES registration)
├── agents/base.py               # Agent: session-based execution, on_permission attach,
│                                #   backstop wrap in _execute_via_runtime/_execute_text_via_runtime
├── runtime/agent_factory.py     # capability probe: does this provider accept on_permission?
├── squadron/base.py             # build ProtectionPolicy once per run; inject into agents
├── workflows/fly_beads/
│   ├── burr_graph.py            # + protection_blocks state slot (seed + .with_state)
│   ├── actions.py               # drain agent block collectors into state; end-of-run warning
│   └── workflow.py              # persist protection-blocks.json from final state
├── workflows/spec_chain/
│   ├── workflow.py              # backstop scope already covered via Agent base; drain into ChainState
│   ├── models.py                # ChainState + protection_blocks field
│   └── landing.py               # belt-and-braces: refuse protected paths in landed tree
├── cli/commands/spec.py         # summary line for blocks in _render_summary_and_exit
├── hooks/                       # RETIRED: stubs removed; salvageable logic absorbed into protection/
tests/
├── unit/protection/             # matcher, snapshot/restore, policy, records, config-degrade
├── unit/config/test_protection_config.py
├── unit/workflows/fly_beads/test_protection_backstop.py
├── unit/agents/test_agent_session_protection.py
└── integration/test_context_file_protection.py   # stub-runtime end-to-end (SC-001 grid)
```

**Structure Decision**: single new focused package `src/maverick/protection/`
(mirrors `src/maverick/assumptions/` precedent from specs 049–055), with thin
touch-points in the existing agent/squadron/workflow layers. The orphaned
`src/maverick/hooks/` package (stubbed since the ACP migration, zero production
consumers — research R3) is retired in this feature; its still-useful
path-normalization ideas move into `protection/matching.py`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Backstop (a deterministic side effect: file restore) executes inside `Agent` base rather than a workflow action (tension with Guardrail 2) | FR-009 requires coverage of *every* agent role on *every* workflow including inside isolated workspaces; the Agent execute path is the only single seam all of them share. The base class already owns runtime-scope concerns (structured-output validation, cost telemetry) and this is the same kind: a property of the execution scope, not workflow logic. Workflows keep ownership of persistence/rendering of the resulting records. | Per-workflow insertion (fly `actions.py:895/:1016/:1643`, spec-chain `workflow.py:556`, reconcile, refuel `--enrich`, plan generate, land curator…) means N seams that every future workflow must remember to add — exactly how coverage gaps are born. A missed seam is a silent hole in a fail-closed safety feature. |
| New third-party dependency `pathspec` (Guardrail 8 asks for canonical libraries, not fewer libraries) | Configured globs need gitignore-style `**` semantics and predictable case handling; stdlib `fnmatch` lets `*` cross `/` and is case-sensitive on POSIX — wrong on both axes (research R5). | Hand-rolling a `**` matcher violates the constitution's "no hand-rolled equivalents of canonical libraries" rule and is a well-known bug farm (escaping, separators, anchoring). |
| Precursor change landed in airframe (separate repo/release) rather than being worked around in Maverick | Airframe 0.9.0rc1 could not block a Claude tool call at all: `on_permission` rode `can_use_tool`, which `permission_mode="bypassPermissions"` (hardcoded) suppresses; hook events were observation-only (research R2). The user explicitly authorized precursor work in airframe; it **shipped in v0.9.2** (airframe#79, 2026-08-07) and Maverick pins `>=0.9.2` at setup. | Working around it inside Maverick (e.g. planting `.claude/settings.json` `permissions.deny` files in agent cwds via `setting_sources`) couples Maverick to one provider's settings format, breaks in the spec-chain workspace copy step, and is invisible/undebuggable. The backstop additionally keeps the guarantee provider-independent — pre-write remains an optimization layer, not the guarantee (research R1). |
