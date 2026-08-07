# Research: Context File Protection

**Feature**: 056-context-file-protection | **Date**: 2026-08-07

All unknowns from the plan's Technical Context are resolved below. Findings
are grounded in a full sweep of the Maverick codebase, the installed
airframe-agents 0.9.0rc1 sources, and the claude-agent-sdk it wraps.

## R1: Enforcement architecture — two layers, backstop is the guarantee

**Decision**: Enforce in two layers. Layer 1 (pre-write) attaches an airframe
`PermissionCallback` that denies write-tool calls targeting protected paths —
active only on providers that support callbacks, and on Claude only after the
airframe precursor (R2) ships. Layer 2 (post-step detect-and-restore) runs
deterministically around **every** agent execution regardless of provider:
capture protected-file state before the model call, re-scan after, restore any
unauthorized mutation, record a block event with `operation="restore"`. The
spec's universal guarantee (SC-001, SC-006) is carried by Layer 2; Layer 1 is
an optimization that stops corruption earlier and teaches the agent (it sees a
denied tool call with a reason) instead of silently undoing it.

**Rationale**: No interception surface is live in Maverick today — every agent
send goes through `AgentRuntime.execute()` (`src/maverick/agents/base.py:166`),
which accepts no permission callback, and the `maverick.hooks` package is
stubbed (`create_safety_hooks()` returns `[]`, zero production consumers).
Provider support for pre-write blocking is uneven (R2's matrix), and Bash-style
channels can mutate files without any tool-level file-path to inspect. Only a
filesystem-truth backstop closes every channel on every provider, which is
exactly what the spec's clarification Q1 adopted.

**Alternatives considered**: (a) Pre-write only — leaves OpenCode/OpenRouter
providers and shell channels unprotected; contradicts clarify Q1. (b) Post-hoc
only — workable but wastes the free win on providers where a clean deny both
prevents the write and gives the agent legible feedback. (c) `.claude/settings.json`
`permissions.deny` files planted in agent cwds (the only pre-write channel that
works on unpatched airframe, via `setting_sources`) — provider-specific,
invisible to debugging, breaks under the spec-chain workspace copy, rejected.

## R2: Airframe precursor — what changes and why it's needed

**Decision**: A small airframe change (separate repo, explicitly authorized by
the user; tracked as
[get2knowio/airframe#79](https://github.com/get2knowio/airframe/issues/79)),
released and pinned before Maverick's Layer 1 activates:

1. **Claude adapter gates through PreToolUse hooks.** When a session has
   `on_permission`, `_build_claude_hooks_config` (adapters/claude_code.py:2060)
   registers a `pre_tool_use` handler that awaits the callback and translates
   `"deny"` into the native
   `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision":
   "deny", "permissionDecisionReason": ...}}` payload; `"allow"`/`"defer"`
   keep returning `{}`. `permission_mode="bypassPermissions"` stays — per the
   claude-agent-sdk docs, PreToolUse hooks gate every tool call regardless of
   permission mode, whereas `can_use_tool` is suppressed by it. (Today those
   hooks are hardcoded observation-only: every handler returns `{}`.)
2. **No API-surface change required.** `AgentRuntime.session(...)` already
   accepts `on_permission` (protocol.py:440); Maverick switches to sessions
   (R4) rather than asking airframe to grow parameters on `execute()`.

**Sequencing — RESOLVED**: the precursor **shipped in airframe v0.9.2**
(2026-08-07; #79 closed via #80). Maverick pins `airframe-agents>=0.9.2` at
setup, so Layer 1 is active on `claude` from the start rather than deferred.
v0.9.2 also fixed hook registration for permission-only sessions (previously
hooks were registered only when `on_event=` was passed) and ships a portable
`test_integration_permission_callback_denies_tool` contract in
`airframe.testing.integration` that the live smoke can lean on. Layer 1 unit
tests still run against a fake runtime implementing the session/callback
protocol — no network in the suite.

**Provider matrix (airframe 0.9.0rc1, verified in adapters)**:

| Provider | `on_permission` | Pre-write layer |
| --- | --- | --- |
| claude | wired to `can_use_tool`, dead under hardcoded `bypassPermissions` | after precursor: PreToolUse-gated deny |
| github-copilot | works (`on_permission_request`, copilot.py:1142) | active immediately |
| kimi | works (`ApprovalRequest`, kimi.py:549; requires `yolo=False`) | active immediately |
| bedrock | works (client-side tool loop, bedrock.py:439) | active immediately |
| opencode family | raises `UnsupportedFeatureError` (opencode_server.py:518) | backstop only |
| openrouter / openai-compat | permanent decline (openai_compatible.py:449) | backstop only |

**Alternatives considered**: making the Claude adapter honor `can_use_tool` by
switching `permission_mode` to `"default"` — rejected: it would surface
permission prompts for every unlisted tool in a headless run; the hook route
gates without changing the permission posture for anything else.

## R3: Home for policy logic — new `protection/` package; retire `hooks/` stubs

**Decision**: Create `src/maverick/protection/` (policy, matching, snapshot,
records, config). Retire the orphaned `src/maverick/hooks/` package: delete the
stub factories and unwired `HookConfig`, absorb the still-relevant ideas
(`normalize_path`, allowlist-before-blocklist ordering, `fail_closed`) into the
new package, and migrate/retire its tests.

**Rationale**: `maverick.hooks` was built for claude-agent-sdk `HookMatcher`,
was de-wired by the ACP migration (its `__init__.py` says so), and has zero
production importers — but it *looks* like a live protection surface
(`SafetyConfig.sensitive_paths`, `validate_file_write`). Leaving it beside a
real protection package guarantees future confusion about which one enforces.
Its matching engine is also semantically wrong for this spec: `fnmatch`'s `*`
crosses `/` and is case-sensitive on POSIX (hooks/safety.py:304), while the
spec requires case-insensitive default names and gitignore-style `**`.
Constitution XII (fix what you find) supports removing dead code encountered
in-scope rather than accreting onto it.

**Alternatives considered**: reviving `maverick.hooks` in place — rejected
(wrong matching semantics at its core, misleading name for a package that
would now also own snapshots/restores/events); leaving it untouched alongside
`protection/` — rejected (two apparent safety surfaces, one dead).

## R4: Attaching the permission callback — Agent holds an `AgentSession`

**Decision**: `Agent.open()` opens `self._runtime.session(on_permission=...,
on_event=...)` and holds the `AgentSession`; `_execute_via_runtime` /
`_execute_text_via_runtime` route through `session.execute(...)` (same
`schema`/`timeout` surface); `rotate_session()` becomes close-and-reopen
instead of `runtime.reset()`; `close()` closes the session before the runtime.
`runtime_for_agent` (or a small helper beside it) exposes a capability probe —
airframe adapters declare `PERMISSION_CALLBACK` support — so the callback is
attached only where supported and the deny path never trips
`UnsupportedFeatureError` on the OpenCode/OpenRouter family.

The callback itself (`protection/policy.py`) inspects the request's
`tool_name`/`tool_args`: known file-write tools (Write/Edit/MultiEdit/
NotebookEdit and per-provider equivalents) have their target path(s) extracted
and matched; a protected match returns `"deny"` with a reason naming the path
and the config escape hatch. Bash/exec tools are **not** parsed for embedded
paths — command-string parsing is heuristic, and the backstop covers that
channel deterministically (spec edge case "indirect mutation").

**Rationale**: sessions are the only airframe surface that accepts
`on_permission` (protocol.py:432-442; `execute()` takes none, and per-call
override is explicitly unsupported — options.py:51). ADR-004's
single-active-session-per-runtime matches Maverick's one-session-per-agent
usage; `rotate_session()`'s contract ("fresh context between beads") is
honored by reopen.

**Alternatives considered**: asking airframe to add `on_permission` to
`execute()` — larger cross-adapter API change for no additional capability;
`AgentSession.unwrap(ClaudeSDKClient)` post-hoc mutation — options are baked
at connect time, so unwrap can't retrofit gating.

## R5: Matching semantics — resolved paths, explicit defaults, `pathspec` globs

**Decision** (all matching in `protection/matching.py`, pure functions):

- **Normalization**: candidate path → absolute → `Path.resolve()` (follows
  symlinks) → relative to the policy root (the agent's `cwd`: checkout or
  workspace). Both the *literal* path (unresolved, for "symlink planted at a
  protected location") and the *resolved* path are matched; protected if
  either matches (spec FR-014). Paths resolving outside the root are not
  protected (out-of-repo writes are out of scope per spec Assumptions).
- **Default rules** (hardcoded, not config-expressible): basename equals
  `agents.md` or `claude.md` case-insensitively at any depth; or the relative
  path is under `.specify/memory/` (any depth, case-insensitive segment
  compare on the fixed prefix).
- **Configured globs** (`additional_globs`, `allowlist`): compiled with
  `pathspec`'s `gitwildmatch` dialect — gitignore-style `**`, one semantics
  users already know. Matched against the resolved relative path (posix
  separators). Evaluation order: allowlist first (exempts), then defaults +
  additional globs (protects) — mirroring the salvaged `hooks/safety.py`
  ordering.
- **Operations**: create/edit/delete each match their single target; rename
  matches source *and* destination, blocked if either side is protected
  (FR-003).

**Rationale**: `fnmatch` fails both spec axes (case, `**`); `pathspec` is the
canonical, widely-deployed gitignore matcher (used by black/pre-commit), pure
Python, tiny — consistent with Guardrail 8's "canonical libraries, no
hand-rolled equivalents". Defaults are hardcoded as explicit rules rather than
globs so FR-012 ("misconfiguration can never widen access") holds trivially:
the default rule objects are constructed with no user input.

**Alternatives considered**: `wcmatch` (heavier, no in-ecosystem precedent);
translating `**` onto `fnmatch` by hand (constitution violation, bug farm);
matching only resolved paths (leaves the planted-symlink hole the clarify
session explicitly closed).

## R6: Backstop mechanics — bytes-manifest snapshot, pruned walk, atomic restore

**Decision** (`protection/snapshot.py`):

- **Pre-step**: enumerate currently-existing protected files (pruned `os.walk`
  from the policy root, skipping `.git`, `.jj`, `.venv`, `node_modules`,
  `.maverick`, plus symlinked dirs) and capture a manifest
  `{relpath: (sha256, bytes)}`. Protected sets are small (two names + one tree
  + user globs), so retained bytes are a few KB.
- **Post-step**: re-walk. For each manifest entry: missing → rewrite bytes
  (delete/rename-away undone); hash differs → rewrite bytes (edit undone). For
  each protected-matching path not in the manifest → delete it (create/
  rename-to undone; if it's a symlink, remove the link). Every restore emits a
  `BlockRecord(operation="restore", ...)` naming the inferred operation in its
  detail.
- Restores go through `maverick.utils.atomic.atomic_write_text` (crash-safe);
  all IO is wrapped in `asyncio.to_thread` (Guardrail 1). The walk is a pure
  filesystem scan — **deliberately no git/jj involvement**, because the
  spec-chain hidden workspace is a non-colocated jj workspace where GitPython
  probes don't work, and untracked files (a freshly created `AGENTS.md`) are
  invisible to `git diff` anyway.
- **Failure semantics (FR-011)**: if the pre-step snapshot itself fails, the
  agent step still runs (protection must not degrade unprotected work) and the
  post-step pass compares against the default-set walk done at squadron open
  as a fallback; if a restore fails, log an error-level event and surface it
  in the run warning — never crash the bead. Fail closed means "the mutation
  does not survive silently", which the restore-or-loud-error pair satisfies.

**Rationale**: the read-bytes/rewrite pattern has direct in-repo precedent
(`fly_beads/_verification.py:186-243`); `jj_restore_operation` is a whole-repo
rewind that would discard legitimate bead work (forbidden by FR-004); git
probes miss untracked files and don't exist in the workspace. Cost: one pruned
walk per agent step, ~tens of ms on a 10k-file tree, invisible next to
multi-minute model calls.

**Alternatives considered**: `git diff --name-only HEAD` pre-filter
(`_vcs_queries.py:12`) — cheap but wrong in the workspace and blind to
untracked creates; copying snapshots into the run dir (`snapshot_prior_attempt`
pattern) — heavier, and the audit need is served by `BlockRecord`s, not file
copies; inotify-style watching — resident machinery for a problem a scan
solves.

## R7: Where the backstop wraps — the `Agent` base execute path

**Decision**: the snapshot/scan/restore pair wraps the runtime call inside
`Agent._execute_via_runtime` and `_execute_text_via_runtime`, driven by an
injected `ProtectionPolicy` (constructed once per run in `Squadron.__init__`
from `MaverickConfig`, threaded to every agent it builds — the same DI shape as
`cost_sink`). Recorded blocks land in a per-squadron `BlockCollector` sink;
workflows drain it at their natural boundaries.

**Rationale**: FR-009 says every role, every workflow, including isolated
workspaces. The per-workflow alternative needs a seam in fly
(actions.py:895, :1016, :1643), spec-chain (workflow.py:556), reconcile's
correction/semantic agents, refuel `--enrich`, plan generate, and land's
curator — and every future workflow must remember to add one; a forgotten seam
is a silent hole in a fail-closed feature. The Agent base already owns
runtime-scope concerns (structured-output validation, cost telemetry); this is
the same category. Deterministic *workflow* side effects (persisting
artifacts, emitting run events, rendering) stay in workflows, which keeps the
Guardrail 2 boundary honest — the justification is recorded in plan.md's
Complexity Tracking.

**Alternatives considered**: per-workflow wrapping (rejected above); a Burr
lifecycle hook (`ProgressEventHook`-style post_run_step) — covers only
Burr-driven workflows, and spec-chain/reconcile agent calls happen outside
Burr actions.

## R8: Events, accumulation, persistence, end-of-run surface

**Decision**:

- **Event**: new frozen dataclass `ContextFileWriteBlocked` in
  `maverick/events.py` (registered in `_EVENT_CLASSES` and `_TUPLE_FIELDS` as
  needed): `agent_role`, `workflow`, `operation`
  (`create|edit|delete|rename|restore`), `path`, `destination_path: str|None`,
  `layer` (`pre-write|backstop`), `bead_id: str|None`, `timestamp`. Rendered
  by `render_workflow_events` as a yellow warning line when it streams.
- **Fly**: new `protection_blocks` state slot seeded in `burr_graph.py`
  (alongside `bead_events`), extended by the actions that call agents (drain
  the squadron collector after each agent-calling action), summarized by one
  `StepOutput(level="warning", metadata={"block_count": n})` at loop exit, and
  persisted by `workflow.py` to `.maverick/runs/<run-id>/protection-blocks.json`.
  The slot is separate from anything feeding fix loops (Guardrail 10 corollary).
- **Spec-chain**: `ChainState.protection_blocks` list field (checkpointed to
  `spec-chain.json` like `clarify_decisions`), drained per step; surfaced in
  `cli/commands/spec.py::_render_summary_and_exit`.
- **Other workflows** (reconcile, refuel `--enrich`, plan generate, land):
  drain the collector at workflow end into the same JSON artifact shape and a
  single warning line via `emit_output(level="warning")`.
- **Never**: assumption-ledger entries, land-gate interaction (FR-005) —
  verified by the land frontier reading only ledger entries, which this
  feature never writes.

**Rationale**: there is no generic event log under `.maverick/runs/` today
(only `SessionJournal`, opt-in and user-pathed), so FR-005's "structured event
on the run" needs a dedicated run artifact; `protection-blocks.json` follows
the `refuel-report.json`/`land-report.json` precedent. The state-slot dance
copies `pending_assumptions`/`bead_events` exactly. Fly currently renders no
end-of-run summary at all (the result dict is discarded by
`execute_python_workflow`), so the warning is emitted as a streamed
`StepOutput` from a loop-exit action — the one mechanism that renders today.

**Alternatives considered**: reusing `StepOutput` alone with metadata (loses
the typed, greppable event class and the persistence schema); building a
general run event log (out of scope — the task-container feature, roadmap
prompt 8, owns that future).

## R9: Config — `protection:` block, lenient loading, degrade-to-defaults

**Decision**: `maverick.yaml` gains a top-level `protection:` block with
exactly two fields: `additional_globs: list[str]` and `allowlist: list[str]`
(gitignore-style patterns). On `MaverickConfig` it is stored as a raw
`dict[str, Any] | None` passthrough (like `actors`), and
`protection/config.py::lookup_protection_config(config)` validates it lazily
into a typed `ProtectionConfig`, returning **defaults plus a
`logger.warning`** on any shape/validation error — the exact
`lookup_tiers_config` idiom (config.py:786-837), chosen because FR-012
requires malformed config to *narrow* to defaults, and a strongly-typed root
field would instead raise `ConfigError` and take down startup. Individually
invalid patterns inside an otherwise-valid block are dropped with a warning
naming the pattern (an invalid allowlist entry must not disable a valid
protected glob, and vice versa — misconfiguration never widens access). There
is no `enabled:` kill-switch: the spec offers none, defaults apply with zero
config, and `allowlist: ["**"]` is the explicit, auditable opt-out for
repositories that truly want agents maintaining context files. `maverick init`
does not write the block (absent == defaults); the config schema contract
documents it for discoverability.

**Alternatives considered**: typed field on `MaverickConfig` (raises on
malformed input — violates FR-012); adding an `enabled: false` flag (an
invisible global off-switch for a safety feature; the allowlist is scoped and
self-documenting); putting it under `assumptions:` or a revived `hooks:` block
(wrong domain, dead namespace).

## R10: Spec-chain specifics — workspace coverage + landing guard

**Decision**: the Agent-base backstop covers spec-chain automatically (the
squadron builds `SpecChainAgent` with `cwd=workspace_path`, so the policy root
is the workspace — protected files there are snapshotted/restored per step,
per the spec's isolated-workspace edge case). As belt-and-braces,
`land_step_artifacts` (spec_chain/landing.py:89) refuses to copy any
protected-matching path from the landed tree into the checkout — relevant only
for configured globs under `specs/**`, since the default protected set lies
outside the per-feature directory that landing copies, but it makes the
landing choke point provably safe rather than incidentally safe.

**Rationale**: research confirmed landing only copies `specs/<feature_dir>/**`,
so default-set corruption cannot reach the checkout through landing today; the
guard turns that accident of scope into a contract.

## R11: Testing strategy

**Decision**: unit-test the pure core exhaustively
(`tests/unit/protection/`): matcher matrix (operation × target × depth ×
case-variant × symlink × allowlist/glob interplay), snapshot/restore matrix
(edit/delete/create/rename undo, restore-failure logging), config degrade
cases (malformed block, invalid single pattern). Integration: stub-runtime
fake agent (existing `stub_squadron_io` pattern) whose "model call" mutates
protected + unprotected files → assert protected restored byte-identical,
unprotected intact, `ContextFileWriteBlocked` events emitted,
`protection-blocks.json` written, bead completes (SC-001…SC-006). Layer 1 unit
tests drive the permission callback directly with fake `PermissionRequest`s
(deny/allow/error paths, fail-closed on protected match); the airframe
precursor's adapter behavior is tested in airframe's own repo, and pinned here
via `uv.lock`.
