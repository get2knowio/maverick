# Phase 0 Research: Headless Spec Kit Chain

All NEEDS CLARIFICATION items from Technical Context are resolved below. Codebase facts
were verified against the tree on 2026-07-24 (branch `main`, post-airframe migration).

## R1. Executing the target repo's `/speckit.*` commands through airframe

**Decision**: Each chain step is one `AgentRuntime.execute()` call whose prompt instructs
the agent to run the corresponding slash command (e.g. `/speckit.specify <description>`)
in the workspace cwd, and to finish by returning a typed step report against a JSON
schema (`schema=` parameter, same structured-output path as existing `Agent` subclasses).
A new `SpecChainAgent` (`agents/spec_chain.py`) subclasses the existing `Agent` base and
uses `_execute_via_runtime`. Slash-command support is a provider capability: agent-CLI
providers (`claude`, `github-copilot`, `opencode`) execute repo-local commands
(`.claude/commands/speckit.*.md` or equivalent) natively when the prompt invokes them;
for providers without a command surface, the step runner falls back to inlining the
command file's body into the prompt (the command definitions are plain markdown
instructions, readable from the target repo).

**Rationale**: Maverick has no slash-command execution path today (verified — nothing in
`src/` references `/speckit.*`); airframe's `execute(prompt, schema, persona, system,
timeout)` is the only agent surface, and it is sufficient: slash commands are prompt
conventions of the underlying agent CLIs. Inline-body fallback keeps FR-003's "the
repo's own command governs the output" property because the instructions still come from
the target repo's files, not from Maverick.

**Alternatives considered**: (a) Maverick re-implementing the Spec Kit steps natively —
rejected, violates FR-003 and duplicates Spec Kit; (b) shelling out to `claude -p
"/speckit.X"` directly via `CommandRunner` — rejected, bypasses airframe (the canonical
agent wrapper), loses cost telemetry/tier handling, and violates Guardrail X.8; (c) a
per-provider command API — premature; the prompt convention works uniformly.

**Verification task carried to implementation — RESOLVED (2026-07-24)**: airframe-agents
0.9.0rc1's `AgentRuntime.execute()`/`session()` expose no `cwd`/`workdir`/`directory`
parameter (`airframe/protocol.py`), and no runtime constructor accepts one either
(`ClaudeCodeRuntime.__init__`, `OpenCodeServerRuntime.__init__`). `ProviderOptions` does
carry a `working_directory` field, but only for `CopilotOptions`/`KimiOptions`/
`OpenCodeServerOptions` — **not** `ClaudeOptions`, the default `generate`-role provider
(`maverick.yaml` → `config.py`). The underlying `claude_agent_sdk.ClaudeAgentOptions` does
support `cwd`, but airframe's `ClaudeCodeRuntime.session()` never threads it through — an
adapter gap, not an SDK limitation. Maverick's existing `Agent.__init__` already stores
`self._cwd` but nothing ever reads it (verified: no call site passes cwd to
`self._runtime.execute()`).

**Revised decision**: "one runtime per squadron" does not by itself bind cwd (the
constructor has no cwd slot). `SpecChainSquadron`/`SpecChainAgent` instead bind the
working directory via a process-wide `os.chdir()` scoped around each step's
`execute()` call, serialized by a dedicated `asyncio.Lock` (spec-chain runs execute
their five steps strictly sequentially per FR-002, and Maverick's CLI runs one workflow
per process invocation, so the exposure window is a single in-process critical section,
not cross-workflow concurrency). The lock + restore-on-exit is implemented as a small
context manager in `agents/spec_chain.py`, documented as a workaround for the airframe
adapter gap above (worth upstreaming a `cwd`/`working_directory` field on `ClaudeOptions`
later, out of scope here).

## R2. Clarify question interception vs. non-interactive fallback

**Decision**: Two paths behind one `ClarifyPolicy` seam (`workflows/spec_chain/clarify.py`):

1. **Interception path** — used when the provider runtime exposes a tool-permission /
   question callback (probed via an airframe capability check at squadron startup, e.g.
   the runtime advertising an AskUserQuestion-style hook). The harness's callback answers
   each question by selecting the recommended option and captures a `ClarifyDecision`
   (question, adopted, alternatives, severity assessment) synchronously.
2. **Non-interactive path** — default whenever interception is unavailable. The clarify
   step prompt invokes `/speckit.clarify` with Spec Kit's documented non-interactive
   convention (agent adopts informed defaults and records them in the spec's
   `## Assumptions` / `## Clarifications` sections). After the step, the workflow parses
   the updated `spec.md` (reusing `maverick.speckit.parser` extension) and upgrades each
   recorded default into a `ClarifyDecision`.

   **Implementation correction (2026-07-24)**: verified against this repository's own
   Spec Kit output (every `spec.md` under `specs/`), the actual recorded-default format
   is `## Clarifications` → `### Session <date>` → `- Q: <question> → A: <answer>`
   bullets — not the `## Assumptions` section (that section holds narrative prose
   assumptions, not question/answer pairs). `workflows/spec_chain/clarify.py`'s
   `decisions_from_spec_md()` parses the `## Clarifications` bullet format directly
   (regex over `- Q: ... → A: ...` lines) rather than adding a speckit.parser
   extension — the grammar is a single regex, not worth a new parser module function.

Both paths converge: every `ClarifyDecision` is filed as an assumption-ledger entry by
the *workflow* (never the agent) after the clarify step completes. Severity is assessed
per question by the harness and defaults to `low` per the spec clarification (FR-007a) —
the chain passes severity explicitly, deliberately not relying on the ledger's
`DEFAULT_SEVERITY = MEDIUM`. Escalation signals are a defined constant list (in
`workflows/spec_chain/constants.py`), by category: **scope** (feature boundaries,
in/out-of-scope, user roles/permissions), **security/privacy** (auth, credentials, data
protection, retention, PII), **compliance** (regulatory/legal), **data integrity**
(irreversible migrations, deletion semantics) — a question matching any category is at
least `medium`. A question with no recommended option still gets an adopted informed
default recorded identically (never skipped, per the spec edge case); if the harness
cannot form a defensible default, the clarify step is treated as blocked and the chain
halts (FR-009).

**Rationale**: Matches FR-005/FR-006 exactly; the policy seam makes each path
independently testable and keeps the "no decision off the record" invariant (SC-002) in
one place. Filing from the workflow (not the agent) preserves Guardrail X.3.

**Alternatives considered**: interception-only (rejected: not all providers support it —
FR-006 mandates the fallback); having the agent file ledger entries itself via a tool
(rejected: agents must not own deterministic side effects).

## R3. Hidden workspace mechanism

**Decision**: A minimal spec-chain workspace helper (`workspace/spec_chain.py`) built on
the canonical `JjClient`:

- Location: `~/.maverick/workspaces/<project-slug>/spec-chain/<feature>/` (outside the
  repo, so nothing pollutes the user's tree or gitignore). The path is **per-feature**:
  chains for different features never share a workspace, so a fresh run for feature B
  cannot destroy a halted feature A's resumable workspace. `<project-slug>` is the
  sanitized repository directory name (stable across runs from the same checkout).
- Creation: `JjClient.workspace_add` from the user's colocated checkout (init guarantees
  `.jj/` exists). Shared backing store means committed files — including
  `.claude/commands/speckit.*.md`, `.specify/**`, and existing `specs/**` — are
  materialized in the workspace.
- Uncommitted inputs: the PRD file may be untracked in the user's checkout; the workflow
  copies it into the workspace under a scratch path before the specify step.
- Reuse & cleanup: an active chain (persisted state, R4) reuses its workspace on resume;
  a completed or freshly-started chain forgets/recreates it (`workspace_forget` + delete)
  so runs start clean.
- bd never runs inside the workspace. All bead/ledger writes happen in the user's
  checkout via the workflow — this is precisely why the historic bd/workspace impedance
  mismatch (gitignored `embeddeddolt/` not traveling) does not apply.

**Artifact landing**: after each successful step, `landing.py` syncs the feature's
artifact set (`specs/NNN-<feature>/**` plus nothing else) from workspace → user checkout
via an atomic staged copy (write to temp sibling, rename into place). Per-step landing
is what makes FR-016 (no partial artifacts) and FR-020 (resume reuses completed-step
artifacts) compose.

**Rationale**: `jj workspace add` is the cheapest isolation the repo already supports;
the clarified requirement mandates hidden-workspace execution; per-step atomic landing
gives "only completed artifacts land" without a final big-bang merge.

**Alternatives considered**: full `jj git clone` (rejected: the drift problems that
retired the clone-based WorkspaceManager); running in-checkout with staging dirs
(rejected by clarification Q1); landing only at chain end (rejected: a crash before the
end would discard completed-step work, violating FR-020's reuse guarantee).

## R4. Chain state persistence and resume discovery

**Decision**: Chain state lives at `.maverick/runs/<run-id>/spec-chain.json` (Pydantic
`ChainState`, see data-model.md), beside a standard `metadata.json` written through the
existing `run_metadata` helpers (`plan_name` = feature name, `status` ∈ existing values).
Resume discovery: `maverick spec <feature>` scans `.maverick/runs/*/spec-chain.json` for
the newest non-terminal state matching the feature (same scan pattern as
`find_latest_run`). If found → resume from `next_step`; else → fresh run. State is
written atomically (temp + rename) after every step transition, including step-start
(so an interrupt mid-step resumes *at* that step, not after it).

**Rationale**: Reuses the established `.maverick/runs/` convention (already gitignored
by init) instead of inventing a new state root; feature-keyed discovery is exactly how
`find_latest_run` already works for refuel.

**Alternatives considered**: the generic `checkpoint/` store (viable, but its
abstraction adds nothing over one small Pydantic file for a linear 5-step chain);
`.maverick/spec-chains/<feature>/` (a second state root to document and gitignore — not
worth it).

## R5. Standalone assumption-ledger entries (no epic yet)

**Decision**: Extend `assumptions/ledger.py` with a standalone-entry path:
`record_standalone_assumption(client, *, payload, owner_spec, source_ref)` that creates
the same bead shape as `record_assumption` (labels `assumption` + legacy pair, state
keys `assumption_severity/status/owner_spec`, description built by the existing
`_build_description`) but with no parent epic and `source_ref` recording the chain step
(e.g. `spec-chain:clarify`) in place of a spawning bead id. Dedup-by-question runs
against open standalone entries with the same `owner_spec`. `owner_spec` is set to the
`NNN-<feature>` directory name, which `per_spec_counts` and the land gate already key on.

**Rationale**: `record_assumption` requires `epic_id` + `source_bead_id`, neither of
which exists at chain time (epic arrives with `refuel --speckit`). Reusing the bead
shape and state keys means `brief`, `review`, and the land gate work unchanged
(FR-007) — verified: they read labels/state keys, not the parent edge.

**Alternatives considered**: creating the epic early to satisfy the current API
(rejected by clarification Q3); a file-based ledger sidecar (rejected: diverges from the
spec-049 storage contract and would need parallel brief/review/land support).

## R6. Remediation beads and later adoption by `refuel --speckit`

**Decision**: Analyze findings become standalone task beads (label
`spec-remediation` + state keys `speckit_feature=<feature-dir>`,
`remediation_source=spec-chain:analyze`, finding fingerprint for idempotency). Adoption:
`refuel --speckit` gains a post-ingest step that queries open beads with
`speckit_feature == <feature>` lacking a parent and adopts them under the epic it
created/found. Primitive: add `BeadClient.update_parent(bead_id, parent_id)` if the
`bd` CLI supports parent update (verify `bd update --parent` at implementation start);
if it does not, adoption falls back to wiring a `parent-child` dependency edge via the
existing `add_dependency` plus stamping `adopted_by_epic` state — functionally
equivalent for `bd ready`/traversal purposes.

**Rationale**: Matches clarification Q3 (standalone now, adopted at refuel). Keying on
`speckit_feature` state reuses the exact mechanism `_find_existing_epic` already uses
for delta detection, so adoption slots into the existing delta path. Fingerprinting
findings keeps re-runs of analyze idempotent (spec assumption: dedup within a run;
fingerprints also make cross-run re-analysis safe).

**Verification task carried to implementation — RESOLVED (2026-07-24)**: `bd` is not
installed in the implementation sandbox, so `bd update --parent` could not be exercised
directly. `src/maverick/beads/client.py`'s `BeadClient` confirms no parent-update
primitive exists today — only `add_dependency()` (`bd dep add <blocked> --blocked-by
<blocker> --type <dep_type>`) and `set_state()` (`bd set-state <id> key=value`), exactly
matching the documented fallback. Proceeding with the fallback as the implementation:
`add_dependency` for the `parent-child` edge plus `set_state(adopted_by_epic=<epic-id>)`.
`BeadClient.update_parent` may be added later if a live `bd` install confirms
`--parent` support; the adoption call site is isolated to one helper so swapping the
primitive later is a one-file change.

**Alternatives considered**: findings-as-file converted at refuel (rejected by Q3);
immediate epic creation (rejected by Q3).

## R7. `maverick init` Spec Kit verification and install offer

**Decision**: Add `check_speckit_installed(cwd)` to `init/prereqs.py` as an *advisory*
check (never hard-fails init): "installed" means the repo has the `.specify/` marker
with a compatible `speckit_version` — the same signal `check_template_compatibility`
already gates on (`>=0.14,<0.15`). When missing and the session is interactive, init
offers installation via Click confirm and runs the Spec Kit installer (`uvx --from
specify-cli specify init --here`, pinned to the supported range) through
`CommandRunner`; decline records a notice on `InitResult` and init still succeeds
(FR-017, US5 scenario 3). Non-interactive init (`--yes`-style or no TTY) skips the offer
and prints the notice. `maverick spec` independently fail-fasts on the same check
(FR-018) so a skipped init can't cause a mid-chain failure.

**Rationale**: Init currently has no interactive prompts; an advisory + confirm keeps it
non-blocking and idempotent (re-init already re-runs best-effort steps). Reusing the
`.specify/` version gate keeps one definition of "Spec Kit installed."

**Alternatives considered**: hard prerequisite (rejected: Spec Kit is only needed for
`maverick spec`/`refuel --speckit`, and US5 scenario 3 requires init to succeed on
decline); checking for a global `specify` binary (rejected: Spec Kit is per-repo
template state, not a machine-level tool).

## R8. Spec directory numbering (NNN allocation)

**Decision**: Delegated entirely to the target repo's `/speckit.specify` command, which
already allocates the next number per the repo's `feature_numbering` convention.
Maverick reads the allocated directory back from the workspace after the specify step
(diff of `specs/` before/after, cross-checked against `.specify/feature.json`) and
records it in `ChainState.feature_dir`. Maverick never allocates numbers (verified: no
allocation logic exists in `maverick.speckit`, by design).

**Rationale**: FR-003/FR-013 — the repo's own conventions govern; duplicating the
allocator invites divergence.

## R9. Structured step reports from slash-command runs

**Decision**: Every step prompt ends with an instruction to report completion via the
structured-output schema (`StepReport`: status, artifacts touched, questions asked/
answered, findings list for analyze, failure reason). The workflow treats the *filesystem*
as ground truth (artifact existence/content decides step success) and the report as
telemetry + parse accelerator; a well-formed report with missing artifacts is a step
failure, not a success.

**Rationale**: Agent self-reports are not trustworthy enough to gate ordering (FR-008);
artifacts are. This mirrors how fly gates on validation rather than agent claims.

## R10. Provider role/tier for the chain agent

**Decision**: The chain agent binds to the existing `"generate"` role in
`KNOWN_ROLES` (used today for flight-plan generation — the closest semantic match:
long-form document synthesis). A `SpecChainSquadron` owns the single runtime for the
run, constructed via `runtime_for_agent("generate", agents_config=config.agents)` with
per-run cwd binding (R1). No new role is added to `KNOWN_ROLES` unless implementation
surfaces a real need for independent model selection per chain step.

**Rationale**: Smallest configuration surface; users already know how to override the
`generate` binding. Per-step tiering is a premature optimization for v1.

**Alternatives considered**: a new `"spec"` role (deferred — additive later without
breaking config); reusing `"decompose"` (worse semantic fit).
