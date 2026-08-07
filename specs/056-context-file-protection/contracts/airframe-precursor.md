# Contract: airframe precursor — Claude adapter permission gating

**Tracked as**: [get2knowio/airframe#79](https://github.com/get2knowio/airframe/issues/79)
**Status**: ✅ **SHIPPED — airframe v0.9.2** (2026-08-07, closed via #80).
Maverick pins `airframe-agents>=0.9.2` at setup (tasks.md T001), so the
pre-write layer is active on `claude` from day one. The release also fixed
hooks being registered only when `on_event=` was passed (permission-only
sessions previously had no gate) and normalizes `tool_name` on the hook path,
and adds a portable `test_integration_permission_callback_denies_tool`
contract to `airframe.testing.integration`. The backstop layer never depended
on this contract; the sections below are preserved as the record of what was
required and why.

## Problem (airframe 0.9.0rc1)

- `adapters/claude_code.py:1362` hardcodes `permission_mode="bypassPermissions"`.
- `on_permission` rides the SDK's `can_use_tool` channel, which
  `bypassPermissions` suppresses entirely — the callback never fires.
- The adapter's registered `PreToolUse` hooks *do* gate every tool call
  regardless of permission mode, but their handlers are hardcoded to
  `return {}` (pure observation), and `on_event` callbacks are synchronous
  with discarded return values.

Net: no airframe surface can block a Claude tool call.

## Required behavior

When a session is created with `on_permission`:

1. The Claude adapter's `pre_tool_use` hook handler awaits the callback with a
   `PermissionRequest` (same `tool_name` normalization as the `can_use_tool`
   path — `mcp__<server>__` prefix stripped; raw `tool_input` as `tool_args`).
2. Decision mapping:
   - `"deny"` → the handler returns the native deny payload:
     `{"hookSpecificOutput": {"hookEventName": "PreToolUse",
     "permissionDecision": "deny", "permissionDecisionReason": <reason>}}`
     — the tool call does not execute; the model sees a tool failure carrying
     the reason.
   - `"allow"` / `"defer"` → handler returns `{}` (today's behavior).
3. A callback exception is caught and treated as `"defer"` — never kills the
   session. (Fail-closed semantics are the *consumer's* job, inside its
   callback — see `protection/policy.py`.)
4. `permission_mode="bypassPermissions"` is unchanged; sessions without
   `on_permission` keep pure-observation hooks; decisions apply to every tool
   call for the session's lifetime.

No public API change: `AgentRuntime.session(on_permission=...)` already
exists; this is adapter-internal wiring.

## What Maverick relies on (cross-provider)

| Provider | Contract |
| --- | --- |
| claude | this precursor; deny via PreToolUse gating |
| github-copilot, kimi, bedrock | `on_permission` already blocks in 0.9.0rc1 — no change requested |
| opencode family, openrouter/openai-compat | permission callbacks unsupported (`UnsupportedFeatureError` / permanent decline) — Maverick's capability probe skips attachment; backstop-only |

Maverick's capability probe reads the adapter's advertised
`PERMISSION_CALLBACK` capability; this contract makes the `claude`
advertisement true in practice but requires no flag changes.

## Verification (in airframe's repo)

- Deny on `Write` targeting `CLAUDE.md` → file unmodified, tool failure with
  reason, session continues.
- Allow/defer → unchanged behavior, with and without `on_permission`.
- Raising callback → tool proceeds per vendor default, session alive.
- Gating persists across many tool calls and post-compaction.

Maverick-side tests (fake runtime implementing the session/callback protocol)
do not depend on the airframe release; only the live `claude` integration
does.
