# Maverick Future

This document supersedes the previous `OPPORTUNITIES.md` files (removed from the repo in favor of this consolidated roadmap).

It was first reconciled against the codebase on 2026-04-19 and **re-reconciled on 2026-08-22**, after specs 048-057 shipped.

## What This Document Is (And Is Not)

This is the **opportunity backlog**: a long tail of observations, most of which
will never be scheduled. It is not the plan of record.

The forward-looking roadmap is
[docs/specify-prompts-orchestration-roadmap.md](docs/specify-prompts-orchestration-roadmap.md)
— twelve sequenced spec prompts in three tiers, of which Tier 1 items 1-4
shipped as specs 054, 055, 056, and 057. Read that first; read this for
context on why a given idea is or isn't worth reviving.

## Status Legend

- **Active**: still missing and worth pursuing.
- **Partial**: groundwork exists, but the design is incomplete.
- **Implemented**: no longer future work; keep regression coverage.
- **Reframed**: the original idea still matters, but the architecture changed and the next step should look different now.
- **Superseded**: the architecture this item was written against no longer
  exists, and the problem it described does not arise in the current one.
  Kept for the record, not as work.

## The 2026-08-22 Reconciliation

The April pass reconciled against an architecture that has since been replaced
twice over. Three substrate changes invalidate whole categories of this
document:

- **xoscar actors are gone** (Burr migration, tracked to completion in #135).
  `src/maverick/actors/` no longer exists. Every supervisor, mailbox, and
  `_end_turn` observation written against it describes code that was deleted.
- **MCP gateways are gone.** Agents return typed Pydantic payloads through
  airframe's structured-output support. `src/maverick/tools/` no longer
  exists, so items about MCP tool-call reliability, routing tool calls
  through an owning actor, and tool-required prompt wrappers no longer have
  a subject.
- **ACP is gone**, and with it `src/maverick/executor/acp.py` and the
  OpenCode runtime module. **airframe** is the one provider-abstraction layer
  (`maverick.runtime.agent_factory`), which also largely answers §4.8's call
  for a named substrate boundary.

A fourth change is narrower but retires an entire section: **the hidden
workspace model was abandoned** in favour of the single-repo (CWD) model
(Guardrail 0), and per-unit isolation now runs through the shared primitive
at `src/maverick/workspace/` (spec 057). `WorkspaceManager` does not exist.

Concretely: of the 94 source paths this document cited in April, **51 no
longer exist**. Statuses and links below have been corrected; where an item
was overtaken by a shipped spec, the spec is named.

## Validated Changes Since The Older Opportunity Notes

*(April observations, re-checked 2026-08-22.)*

- **Runway seed is no longer broken.** Still true. The seed path writes semantic artifacts and is covered by tests in [src/maverick/runway/seed.py](src/maverick/runway/seed.py) and [tests/unit/runway/test_seed.py](tests/unit/runway/test_seed.py).
- **Provider quota clean-failure handling exists now.** Still true, though relocated: [src/maverick/exceptions/quota.py](src/maverick/exceptions/quota.py) is now consumed by the Burr action layer (`workflows/refuel_maverick/actions.py`), not by the deleted xoscar supervisors the April note named.
- **The old "cap review retries" finding is no longer correct for fly-beads.** Still true, and now enforced in the graph rather than a supervisor: review-fix rounds are bounded by `MAX_GATE_FIX_ATTEMPTS` and the review-round cap in [src/maverick/workflows/fly_beads/actions.py](src/maverick/workflows/fly_beads/actions.py).
- **~~Workspace planning moved toward hidden workspaces.~~** **No longer true, and reversed.** Hidden workspaces were tried twice (`jj git clone`, then `jj workspace add`) and abandoned both times — bd's gitignored `embeddeddolt/` cannot travel into a workspace. The contract is now single-repo/CWD (Guardrail 0), with short-lived per-unit isolation via [src/maverick/workspace/](src/maverick/workspace/) for the two consumers that need it (`maverick spec`, `fly --isolated`). See constitution Appendix E.

## Reconciled Opportunity Index

*Re-reconciled 2026-08-22. "Spec" names the shipped feature that closed an item.*

| Opportunity | Status | Note |
|---|---|---|
| Per-epic workspaces | Superseded | §1.1. Hidden workspaces were abandoned; per-unit isolation is spec 057's shared primitive. The per-*epic* question is now a dispatcher concern, not a workspace one. |
| Per-invocation hermetic workspaces | Superseded | §1.1.1. Written against `WorkspaceManager`, which no longer exists. Spec 057 delivers per-unit isolation under the single-repo model instead. |
| Conditional verification in land | **Implemented** | §1.2. Spec **052** — assumption frontier gate, `verified` vs `conditionally-verified`, persisted land report. |
| Variable pipeline by bead type | Partial | §1.3. Bead categories exist; fly still runs one pipeline for every bead. Isolated mode added a *second* shape, but keyed on the flag, not the bead. |
| Provider-agnostic interactive review | **Implemented** | §1.5. Spec **053** — the packaged `maverick-review` skill over JSON CLI verbs, with bare-terminal `maverick review` retained as fallback. |
| Assumptions as spec quality signal | **Implemented** | §1.6. Spec **049** — `maverick brief` reports per-spec assumption counts by status and severity. |
| Asynchronous human review queue | **Implemented** | §1.4. All three April gaps closed: question queue (**049**), mid-flight answer injection (**051** + **052**), notification mechanics (**054**). |
| Simplify the briefing room | Active | §2.1. Still four briefing personas on the legacy flight-plan path. Note the Spec Kit path calls no briefing agents at all, so this now only affects the fallback. |
| Lean out convention injection | Active | §2.2. Prompt convention payloads are still heavy. |
| Observational memory for runway | Active | §3.1. Consolidation exists; retrieval is still not centered on one always-in-context summary. |
| Cap review retries to reduce thrashing | Implemented | §6.3. Now enforced in the Burr graph rather than a supervisor. |
| Strengthen TDD as primary feedback loop | Active | §4.1. |
| Consider Agent Teams for review | Active | §2.6. Still exploratory. |
| Reduce jj installation friction | Active | §4.2. No git-only fallback; `jj` is now a hard dependency of the isolation primitive as well. |
| Supervisor agent for adaptive orchestration | Active | §3.2. Reframe against Burr: this would be a policy layer choosing transitions, not a new actor. |
| Supervisor-driven resource tuning | Active | §3.3. Still depends on telemetry that doesn't exist. |
| Provider quota detection and automatic failover | Partial | §6.2. Tiers 1/1.5/1.6 exist; Tier 2 (wait-and-resume) and Tier 3 (failover) are not built. Failover is now airframe's natural layer, not maverick's. |
| Step-level evals and prompt testing | Active | §3.4. See also issues #17/#26/#27, which propose a Phoenix-backed implementation. |
| Idempotent `maverick init` | Implemented | §4.3. |
| Defer bd-state inference to bd itself | Reframed | §4.5. Investigated 2026-04-28; `bd doctor` doesn't support embedded mode. Filesystem inspection stays. |
| Reduce MCP tool-call reliability as a hard dependency | Superseded | §4.6. There is no MCP layer. airframe's structured output is the contract, and it is enforced by the provider rather than hoped for. |
| Route tool calls through owning actor | Superseded | §2.3. No MCP inbox, no actors. |
| Structured telemetry via OpenTelemetry GenAI conventions | Active | §3.5. Still nothing; `grep -rn trace_id src/` returns zero. |
| Shared mailbox actor scaffold | Superseded | §2.4. Actors are gone; the equivalent seam is `Squadron`. |
| Named capability profiles end-to-end | Active | §2.5. Partly answered by per-complexity tiers (§2.10), but there is still no named profile concept. |
| Unified trace and correlation envelope | Active | §3.6. See #18. |
| Canonical artifact rendering and formatting | Active | §3.7. |
| Reusable supervisor fragments | Superseded | §5.1. The YAML DSL was removed (spec 041) and `library/fragments/` with it. |
| ACP prompt-cache optimization | Implemented (moot) | §2.7. Shipped, then the ACP executor was deleted. Retained only as a record of the measurement. |
| Consolidate agent `_end_turn` helpers | Superseded | §2.8. The five xoscar agents it described no longer exist. |
| Move tool-required framework wrapper to system prompt | Superseded | §2.9. The wrapper was an MCP-era workaround. |
| Per-bead complexity-based model routing | Partial | §2.10. Tier plumbing is real and wired for fly's implementer/reviewer and refuel's decomposer. The implementer's `escalation_threshold` reading is still unimplemented. |
| Auto tech-debt beads from approved-with-findings reviews | Active | §2.11. |
| Free OpenRouter models often skip MCP tool calls | Reframed | §2.12. The MCP framing is gone, but the underlying finding — weak models fail structured output — survived the migration and is exactly issue #166. |
| Fly checkpoint resume ignores `--max-beads` | Implemented | §1.7. |
| Review prompts don't emit `prompt_usage` | Implemented (moot) | §3.8. Fixed in the ACP executor, which no longer exists. |
| Commit provenance for evals | Partial | §3.9. Layer 1 (`Refs:` trailer) shipped; Layer 2 (per-attempt runway capture) still open. |
| Per-project OpenCode agent/skill overrides | Reframed | §4.7. `runtime/opencode/` is gone — OpenCode is an airframe provider now, so any override layer belongs at that boundary. |
| Substrate-swap interface | Largely Implemented | §4.8. airframe *is* the named boundary the item asked for. What remains is narrower: maverick-side concerns that still leak around it. |

## 1. Orchestration And Human Review

### 1.1 Per-Epic Workspaces On Top Of Hidden Workspaces

**Status:** Superseded *(2026-08-22)*

Both architectures this item was written between are gone. The original
proposal assumed jj workspaces in the user-facing flow; the April reframe
pushed it onto hidden workspaces. Hidden workspaces were then abandoned —
twice, once per implementation — because bd's gitignored `embeddeddolt/`
cannot travel into one. The contract is single-repo/CWD (Guardrail 0).

What replaced it: spec **057**'s shared isolation primitive
([src/maverick/workspace/](src/maverick/workspace/)), which gives a *unit* of
work its own short-lived workspace and folds the result back into the
checkout, without bd or the ledger ever leaving it.

The residue worth keeping is not about workspaces at all. "Beads that escalate
to human review create a context-management problem when other epics
continue" is a **scheduling** question, and it now belongs to the concurrent
dispatcher (roadmap Tier 2, item 9), which is where cross-epic concurrency
will actually be decided.

What still matters:

- Beads that escalate to human review still create a context-management problem when other epics continue.
- Correction work still wants the original epic state, not whatever the latest shared workspace happens to contain.
- Watch mode still wants a cleaner story for concurrent producer and consumer behavior across multiple epics.

*April's "what should happen next", now void:*

- ~~Re-scope this as **multiple hidden workspaces or multiple hidden clones per epic**~~ — hidden workspaces were abandoned.
- Keep the user-facing model git-native. **(This one held, and hardened into Guardrail 0.)**
- ~~Treat per-epic workspace switching as a second-stage extension to the hidden workspace architecture.~~

Current references:

- [.specify/memory/constitution.md](.specify/memory/constitution.md) — Guardrail 0 and Appendix E (the isolation mechanism)
- [src/maverick/workspace/](src/maverick/workspace/) — the shared primitive
- `.specify/memory/workspace-isolation-design-brief.md` — the abandoned hidden-workspace design; retained as history, do not build against it

### 1.1.1 Per-Invocation Hermetic Workspaces

**Status:** Superseded *(2026-08-22)*

> **Everything below describes a design that was removed.** `WorkspaceManager`
> does not exist; there is no `~/.maverick/workspaces/<project>/` shared
> workspace, no find-or-create/finalize lifecycle, and no `maverick workspace`
> command group. Long-running ops run directly in the user's checkout
> (Guardrail 0), and spec **057** provides per-unit isolation where it is
> genuinely needed. The concurrency concerns below are real and unaddressed,
> but they are now the concurrent dispatcher's problem (roadmap Tier 2,
> item 9) — a workspace-path change cannot solve them, because there is no
> shared workspace path left to change. Retained for the reasoning only.

Today the workspace lives at `~/.maverick/workspaces/<project>/` — one per project. Plan and refuel are hermetic (find-or-create → work → push → teardown via `WorkspaceManager.finalize`), but fly still leaves its workspace alive for `land` because fly's commits need curation. The workspace path is shared, which means:

- Two concurrent `plan generate` runs on different epics would collide.
- Two concurrent `refuel` runs would collide.
- A second `fly --epic X` started while the first is still going would attach to the same workspace.

**What should happen next:**

- Make the workspace path per-invocation: `~/.maverick/workspaces/<project>/<run-id>/`.
- Concurrent runs become first-class — each command owns its own workspace, no coordination needed.
- Fly absorbs curation: default behaviour runs the curator agent and finalizes itself; `--no-land` opts out for human review.
- Land becomes opt-in — used only when the user explicitly skipped fly's auto-curation.
- `WorkspaceManager` grows registry/list/cleanup APIs (`maverick workspace list`, `maverick workspace clean --all`).
- Cross-invocation caches (refuel briefing, fly checkpoints) move into the user repo as committed `.maverick/` artifacts so they survive workspace teardown via git/jj rather than via a persistent workspace.

**Why this is its own step:**

- Folding curation into fly is a real refactor of the fly supervisor — the curator agent is currently driven from `land`'s ACP path.
- The cache-survival decision needs per-artifact thought (what's domain state vs. ephemeral).
- Bd has implicit single-writer assumptions that need verification before two flies can write concurrently.
- These should land as one coordinated change, not piecemeal.

Until then, fly remains the bridged exception. New code should not add per-invocation workspace logic ad-hoc.

Relevant code:

- `src/maverick/workspace/manager.py` — `find_or_create`, `finalize`, `apply_to_user_repo`, `cleanup_user_repo_branch`
- [src/maverick/cli/commands/flight_plan/generate.py](src/maverick/cli/commands/flight_plan/generate.py) — already hermetic
- [src/maverick/cli/commands/refuel/_group.py](src/maverick/cli/commands/refuel/_group.py) — already hermetic
- [src/maverick/cli/commands/fly/_group.py](src/maverick/cli/commands/fly/_group.py) — still leaves workspace for land
- [src/maverick/cli/commands/land.py](src/maverick/cli/commands/land.py) — handles fly's deferred finalize today

### 1.2 Conditional Verification In Land

**Status:** Implemented — spec **052** (conditional landing) *(2026-08-22)*

Delivered essentially as described. `maverick land` now evaluates an
assumption frontier gate before curation and classifies the result
`verified` (every entry answered, or none at all) or `conditionally-verified`
(frontier empty but at least one entry waived) — the exact "verified
conditional on an unresolved assumption" distinction this item asked for.

Any open entry of any severity, or any answered-but-unreconciled entry,
blocks the command with a per-spec table and a non-zero exit; there is no
bypass flag. Every evaluation persists a report to
`.maverick/runs/<run-id>/land-report.{json,md}`, which is the audit trail the
item wanted in place of a single `needs-human-review` tag.

See [src/maverick/cli/commands/land_gate.py](src/maverick/cli/commands/land_gate.py),
[src/maverick/assumptions/land_report.py](src/maverick/assumptions/land_report.py),
and `specs/052-conditional-landing/`.

*Original observation:* Land still treats work as either done or not done. There is no first-class notion of "verified conditional on an unresolved assumption" even though the human-review and correction-bead model is pushing in that direction.

Why it still matters:

- The current human-review flow already distinguishes optimistic commits from clean approvals.
- Assumption-driven work should leave a more precise audit trail than a single needs-human-review tag.
- This is the missing reporting layer between optimistic execution and later correction.

Relevant code:

- [src/maverick/cli/commands/land.py](src/maverick/cli/commands/land.py)
- [src/maverick/workflows/fly_beads/workflow.py](src/maverick/workflows/fly_beads/workflow.py)

### 1.3 Variable Pipelines By Bead Type

**Status:** Partial *(re-checked 2026-08-22)*

Still accurate. Bead categories and labels exist; the fly graph does not
branch on them.

What exists:

- Bead category support in [src/maverick/beads/models.py](src/maverick/beads/models.py).
- Assumption / human-review labels applied by [src/maverick/workflows/fly_beads/actions.py](src/maverick/workflows/fly_beads/actions.py) (`record_assumptions`, `create_human_bead`) and consumed by [src/maverick/cli/commands/review/](src/maverick/cli/commands/review/).

What is still missing:

- A dispatcher that says validation beads, correction beads, review beads, and implementation beads should not all run the exact same pipeline.

**Note (2026-08-22):** spec 057 introduced a *second* pipeline shape — isolated
mode reorders to `implement -> checks -> review -> fold-back -> gate -> commit`
— which proves the graph can carry more than one sequence. But it branches on
a CLI flag, not on the bead. The machinery this item wants now exists; the
signal to drive it is what's missing.

### 1.4 Asynchronous Human Review Queue

**Status:** Implemented — specs **049**, **051**, **052**, **054** *(2026-08-22)*

All three April gaps are closed, each by a different spec:

- **"A question queue for advisory or blocking questions during execution"** →
  the **assumption ledger** (spec 049). Agents report adopted assumptions in
  their structured payloads; each becomes a bead under the owning epic with a
  `discovered-from` edge. Severity drives enforcement: `low` is deferred out
  of the ready queue, `high` gains a `blocks` edge onto the next spec's epic.
- **"Mid-flight answer injection back into paused or retried work"** →
  `maverick reconcile` (spec 051) applies a changed answer retroactively via
  jj history surgery, and spec 052 wires it into fly at every bead boundary
  so a running drain loop picks up answers without stopping.
- **"Notification or polling mechanics beyond review the bead later"** →
  `maverick notify` (spec 054), a daemonless scheduler with severity-tiered
  delivery windows, quiet hours, and age escalation.

The loop the April note called "the broader async collaboration loop" is the
one thing this project now does that the surveyed field did not: proceed on a
recorded assumption, then apply the human's answer retroactively.

See [src/maverick/assumptions/](src/maverick/assumptions/),
[src/maverick/workflows/reconcile/](src/maverick/workflows/reconcile/), and
[src/maverick/workflows/fly_beads/mid_flight.py](src/maverick/workflows/fly_beads/mid_flight.py).

### 1.5 Provider-Agnostic Interactive Review

**Status:** Implemented — spec **053** *(2026-08-22)*

Delivered, though not by the route the April note imagined. Rather than
opening a conversational ACP session, spec 053 split frontend from plumbing:

- Every review-lifecycle verb became headlessly invocable with `--json`
  (`review --list`, `review <id> --answer/--waive`, `review --spec --waive`),
  sharing one envelope and error-kind registry.
- A packaged Claude Code skill, `maverick-review`, installed by `maverick
  init`, sweeps the open queue one entry at a time via `AskUserQuestion` and
  applies each decision through those verbs. It never touches jj, git, bd, or
  files directly.

This satisfies the item's three "why it still matters" bullets exactly: richer
iteration lives in the skill, the structured command stayed narrow, and the
interactive mode is optional — `maverick review` without `--json` is unchanged
and remains the bare-terminal fallback for humans without Claude Code.

The "provider-agnostic" ambition is only partly met: the skill is Claude
Code-specific. The *CLI contract* underneath it is provider-agnostic, so a
second frontend needs no new maverick code.

Relevant code:

- [src/maverick/cli/commands/review/](src/maverick/cli/commands/review/)
- [src/maverick/skills/review_console/SKILL.md](src/maverick/skills/review_console/SKILL.md)
- [src/maverick/cli/json_output.py](src/maverick/cli/json_output.py)

### 1.6 Assumptions As A Spec Quality Signal

**Status:** Implemented — spec **049** *(2026-08-22)*

The metric is surfaced. `maverick brief` reports per-spec assumption counts
(open / answered / waived, by severity, plus a legacy bucket), and the land
report (spec 052) carries the same provenance grouped by spec.

Both of the April note's "good next step" destinations were used: the land
summary got it directly, and spec 055 went further by feeding *resolved*
assumptions into a decision corpus under the runway store, so past human
answers suggest resolutions for new ones.

Relevant code:

- [src/maverick/cli/commands/brief.py](src/maverick/cli/commands/brief.py) — `_assumption_counts_dicts`
- [src/maverick/assumptions/land_report.py](src/maverick/assumptions/land_report.py)
- [src/maverick/assumptions/suggestions.py](src/maverick/assumptions/suggestions.py)

**What is genuinely still open:** the count is reported but nothing *acts* on
it. There is no threshold at which a spec is flagged as underspecified, and no
feedback into the spec chain that would make the next `maverick spec` run ask
more clarifying questions. That is the residue worth reviving.

### 1.7 Fly Checkpoint Resume Ignores `--max-beads`

**Status:** Implemented

Originally observed during the 2026-04-24 e2e run on `sample-maverick-project`: launched ``maverick fly --epic <id> --max-beads 2`` and the final report showed **12 beads** processed. The header banner showed ``max_beads=2`` parsed correctly. The first log line was:

> Resuming from checkpoint 'checkpoint' (saved at 2026-03-19T02:24:14...)

Root cause was a reporting bug, not a loop runaway. The bead loop in `src/maverick/actors/xoscar/fly_supervisor.py` (``_bead_loop``) correctly capped ``processed < max_beads`` for new work in this run. But the terminal-result payload reported ``"beads_completed": len(self._completed_beads)`` — and ``self._completed_beads`` is seeded from ``_inputs.completed_bead_ids`` (loaded from the checkpoint) so the loop's "skip already done" guard works on resume. With a stale checkpoint of 10 prior IDs and 2 new beads processed, the cumulative list was 12, so the report said "12 beads completed" without doing 12 beads of work.

**Fix shipped** *(in the pre-Burr `FlySupervisor`; the fix survived the migration into the Burr action layer, the file cited below did not)*: ``FlySupervisor`` tracks ``self._processed_this_run: int`` separately, set to 0 on construction and incremented inside ``_bead_loop`` alongside the local counter. All three ``_mark_done`` payloads (success, exception, prompt-error) now report ``"beads_completed": self._processed_this_run`` while keeping ``completed_bead_ids`` cumulative (still needed for resume state). Regression test in `tests/unit/actors/xoscar_runtime/test_fly_supervisor.py` (``test_terminal_result_reports_only_this_runs_beads``) seeds 10 prior IDs, triggers the terminal path, and asserts ``beads_completed == 0``.

Reflection: the FUTURE.md hypothesis ("the bead-loop counter must reset / re-evaluate the budget") was misdirected — the loop counter was already correct. The user-visible inflated count came from the reporting layer, not from extra agent work. Cost-control intent was always enforced; only the report was lying.

## 2. Agent Architecture And MCP Boundaries

### 2.1 Simplify The Briefing Room

**Status:** Active — but the blast radius shrank *(re-checked 2026-08-22)*

The repo still pays for multiple specialist briefing agents before plan generation and refuel. The specialist fan-out pattern is real and useful, but it is also an obvious cost center.

The question is no longer whether the pattern exists. It does. The question is whether the current eight-agent footprint is still the right budget.

**Reconciliation note:** this now only affects the **fallback** path.
`refuel --speckit` — the default since spec 048 — calls no briefing agents at
all (`grep -rn "contrarian\|briefing" src/maverick/workflows/refuel_speckit/`
returns nothing), and makes zero model calls outside opt-in `--enrich`. So the
cost this item targets is only paid by repositories without Spec Kit
artifacts. That weakens the urgency and strengthens a different option:
retiring the briefing room along with the legacy path, rather than optimizing
it. Note also issue #166 — the contrarian agent fails structured output
repeatedly on haiku, which is a reason to shrink the footprint on its own.

Relevant code:

- [src/maverick/agents/briefing/](src/maverick/agents/briefing/)
- [src/maverick/preflight_briefing/serializer.py](src/maverick/preflight_briefing/serializer.py)
- [src/maverick/workflows/generate_flight_plan/workflow.py](src/maverick/workflows/generate_flight_plan/workflow.py)
- [src/maverick/workflows/refuel_maverick/workflow.py](src/maverick/workflows/refuel_maverick/workflow.py)

### 2.2 Lean Out Convention Injection

**Status:** Active

Convention injection is still broad. The codebase now has more machine-enforced structure than when the older notes were written, which makes this opportunity stronger, not weaker.

The real target is not "fewer rules" in the abstract. It is:

- less prose for rules already enforced by tests, linters, or typed boundaries;
- more precise project-specific rules derived from real failures.

Relevant code:

- [src/maverick/agents/system_prompts/](src/maverick/agents/system_prompts/) — one persona file per role
- [CLAUDE.md](CLAUDE.md)
- [src/maverick/agents/coding.py](src/maverick/agents/coding.py)

### 2.3 Route Agent Tool Calls Through The Owning Actor

**Status:** Superseded *(2026-08-22)*

Neither side of this item exists. There is no MCP inbox server
(`src/maverick/tools/` is gone) and no actors (`src/maverick/actors/` is
gone). The layering problem it described — per-role tool-call policy leaking
into the ACP client or up into the supervisor — was dissolved rather than
fixed: agents no longer *call a tool* to return their result. They declare a
`result_model` and airframe forces the provider to produce it, so the payload
arrives as a validated Pydantic object on the return path of
`Agent._execute_via_runtime`.

The boundary the item wanted is now `Agent` (owns HOW: prompt, role, result
model) versus the Burr action that invoked it (owns WHAT/WHEN). Nothing routes
around it.

*Retained because the underlying instinct — the component that owns an agent
should observe what that agent does — is still a good test to apply to new
designs.*

### 2.4 Shared Mailbox Actor Scaffold

**Status:** Superseded — and independently delivered *(2026-08-22)*

The duplication this described was real, and it was removed — not by
extracting a mailbox scaffold, but by deleting the mailbox model entirely.
The Burr migration replaced per-workflow actors with two composed layers:

- **`Squadron`** ([src/maverick/squadron/](src/maverick/squadron/)) — the
  per-run lifecycle container. It builds one runtime per role, opens every
  agent, and closes them all on exit. This is the "shared scaffold" the item
  asked for.
- **`Agent`** ([src/maverick/agents/base.py](src/maverick/agents/base.py)) —
  owns runtime scope, structured-output validation, session rotation, and cost
  telemetry, so subclasses add only prompts and domain methods.

Each of the six repeated mechanics below is gone or centralized: lazy executor
creation and session lookup live in `Agent.open()`/`rotate_session()`; the
required-tool suffix and inbox read/parse/unlink no longer exist at all, since
structured output replaced tool-call-as-return; nudge retries are airframe's
concern.

*Original observation, for the record.* Several mailbox-oriented actors repeated the same mechanics:

- lazy executor creation;
- session lookup or creation;
- required-tool instruction suffixes;
- inbox-file read, parse, and unlink;
- nudge retries when the tool was not called;
- shallow state snapshotting.

The repetition is visible across:

- `src/maverick/workflows/generate_flight_plan/actors/briefing.py`
- `src/maverick/workflows/fly_beads/actors/implementer.py`
- `src/maverick/workflows/fly_beads/actors/reviewer.py`

Maverick had already extracted async loop plumbing for top-level actors into `src/maverick/actors/_bridge.py`; the mailbox actors wanted the same treatment. All of these files were deleted in the Burr migration.

### 2.5 Named Capability Profiles End-To-End

**Status:** Active — reframed *(2026-08-22)*

The original framing (`agents/tools.py`, executor overrides, MCP tool
additions) is obsolete; none of those exist. But a version of the problem
survived the migration in a new form.

Capability intent is now split across three places that do not know about each
other:

- **`agents.<role>`** in `maverick.yaml` — the provider/model binding per role,
  resolved by [src/maverick/runtime/agent_factory.py](src/maverick/runtime/agent_factory.py).
- **`actors.<workflow>.<actor>.tiers`** — per-complexity overrides for three
  actors only (fly's implementer and reviewer, refuel's decomposer), see §2.10.
- **`Agent` subclass attributes** — `result_model`, `provider_tier`,
  `persona_name`, declared in Python, not config.

There is still no named profile that says "this is what a *reviewer* is,
end to end." The drift risk the item named is unchanged; only the surfaces
moved.

Relevant code:

- [src/maverick/runtime/agent_factory.py](src/maverick/runtime/agent_factory.py)
- [src/maverick/squadron/tiers.py](src/maverick/squadron/tiers.py)
- [src/maverick/agents/base.py](src/maverick/agents/base.py)

### 2.6 Consider Agent Teams For Parallel Review

**Status:** Active *(re-checked 2026-08-22)*

Still worth evaluating, still not an obvious must-have — but the comparison
baseline changed. The "mature actor-mailbox model" this weighed against no
longer exists; concurrency is now expressed as Burr graph structure plus
`Squadron`-managed agent lifetimes.

The narrow question is unchanged and still the right one:

- would native Agent Teams replace meaningful orchestration code or just rename it?

Until there is a clearer payoff, this should remain exploratory. Note that the
roadmap's concurrent dispatcher (Tier 2, item 9) will answer the adjacent
question — bounded parallelism across *beads* — using the isolation primitive
rather than any vendor team abstraction, which is likely to settle this by
precedent.

### 2.7 ACP Prompt-Cache Optimization

**Status:** Implemented, now moot *(2026-08-22)*

> **The ACP executor was deleted.** `src/maverick/executor/acp.py`,
> `_connection_pool.py`, and the xoscar actors named throughout this section
> are all gone; every LLM call now goes through **airframe**, which owns
> session and cache behaviour. The engineering below shipped and then the
> subsystem it shipped into was replaced.
>
> Kept for one durable finding, which is provider behaviour rather than
> maverick behaviour and therefore still true: **Anthropic's prompt cache is
> content-keyed, not session-keyed.** Two different sessions with the same
> prefix share cache (structuralist and recon each read ~33.9K cached tokens
> in one refuel). That is why session rotation between beads costs nothing in
> cache terms — a fact `Agent.rotate_session()` still quietly depends on.
>
> The rest — Phase A/B implementation notes, the xoscar-migration bug list —
> is archaeology.

*Original entry (Phase A and Phase B shipped 2026-04-24; Phases C / D / 1h-TTL closed as not needed):*

Per-turn Anthropic quota burn has been unsustainable. The original hypothesis was that Maverick was getting ~0% cache hits because the Claude Agent SDK disables caching by default when MCP servers are attached (per Anthropic docs). Phase A observability proved that hypothesis **wrong**. Live run against `sample-maverick-project` on 2026-04-24:

| agent | input | cache_read | cache_write | output |
|---|---|---|---|---|
| structuralist (parallel) | 6 | 33,946 | 0 | 171 |
| recon (parallel) | 6 | 33,940 | 0 | 167 |
| navigator (parallel) | 14 | 119,754 | 19,287 | 5,526 |
| contrarian (sequential after) | 13 | 81,896 | 61,969 | 12,588 |

Caching is working end-to-end with MCP attached. Three parallel briefings all hit a warm prefix cache (~34K read tokens apiece with 0 cache writes on two of them), and the sequential contrarian then benefited from navigator's cache write (navigator wrote 19K; contrarian read 82K). The 6-token `input_tokens` on parallel briefings versus their ~19KB prompts means ~99.98% of the prompt content is being cache-served.

This reframes Phases B–D — the original framing assumed MCP was actively suppressing caching, so every agent prompt was a cold start. With caching working, the phases shrink from "unblock a broken feature" to "squeeze a few more points out of an already-working one":

**Phase A — Observability (Implemented 2026-04-24):**

- `AcpStepExecutor` now captures `PromptResponse.usage` on both the one-shot `execute()` path and the multi-turn `prompt_session()` path.
- A structured `acp_executor.prompt_usage` INFO log line is emitted per prompt with `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `session_id`, `session_kind` (`one_shot` or `multi_turn`), and `usage_reported`.
- `ExecutorResult.usage` is populated from the ACP usage payload instead of hardcoded `None`.
- Relevant commits: `a007364` (plumbing + tests), `2e57017` (format drift sweep).

**Xoscar-migration bugs fixed on the way to validating Phase A** (2026-04-24): every xoscar actor was missing `super().__init__()` so `self._generators` was never set and `@xo.generator run()` crashed on first iteration (`4eb67ef`); every supervisor used `self.ref` instead of `self.ref()` and passed the unbound Cython method to children as `supervisor_ref` (`b9c2dd3`); `self.uid` returns bytes so supervisor-child uid f-strings produced the `b'...'` repr which garbled the MCP subprocess argv (`6be0a9d`); briefing/decomposer/implementer/reviewer/generator `on_tool_call` was missing `@xo.no_lock` and deadlocked with the agent's own `send_*` method that holds the actor lock across the ACP prompt (`4e8689f`); one-shot cancel fired on `ToolCallStart` racing against the MCP round-trip (`da65394`); supervisor callback methods (`*_ready`, `*_error`, `get_terminal_result`) all needed `@xo.no_lock` because the `@xo.generator run()` method holds the supervisor's lock while awaiting the event queue and the callbacks are what push onto that queue (`06fed8e`). None of these were caught by the existing unit tests because those tests assert on method-level routing, not on end-to-end generator iteration or cross-actor RPC. Regression guards added in `tests/unit/actors/xoscar_runtime/test_super_init.py` (parametrised per actor file) to keep new actors correct by default.

**Phase B — Retry-session reuse (Implemented 2026-04-24, `6eed6a1`):**

`_execute_with_retry` used to call `conn.new_session(...)` on every retry attempt, so a transient hiccup + one retry meant paying for two cache-prefix writes on the same content. After `6eed6a1`, `_run_single_attempt` calls `_ensure_session()` which is a no-op when a session already exists; a reconnect (subprocess died) still forces a fresh session on the new connection. Regression tests lock in both behaviors: `test_retry_reuses_session` and `test_reconnect_does_create_fresh_session`.

The originally proposed "warm-up cascade" for the briefing fan-out was dropped — Phase A data showed parallel briefings already share cache (`cache_read_tokens≈33,946` on all three with zero cache writes on two), so sequencing the first agent would buy zero tokens at the cost of wall-clock latency.

**Phase C — Unblock MCP caching (Closed, not needed):**

Phase A data contradicted the premise. The Anthropic docs claim MCP servers disable caching by default; the live run showed clear cache reads (99.98% of prompt served from cache on parallel briefings) with the agent tool gateway MCP attached. No upstream patch needed.

**Phase D — Session-lifetime refactors (Closed, not needed):**

The premise of Phase D was that rotating sessions across bead/mode boundaries discarded the prefix cache. Phase A data shows that's wrong: Anthropic's prompt cache is **content-keyed, not session-keyed**. Proof: structuralist (session A) and recon (session B) both read 33,940+ cached tokens in the same refuel — different sessions, same content, shared cache. Fusing implementer/reviewer/decomposer sessions across beads would therefore buy essentially nothing on token cost while introducing real regression risk (longer conversation history, cross-bead context bleed, harder debugging).

Reopen only if a live refuel/fly run shows `cache_write_tokens` climbing on prompts that should have been cache-fed — that would indicate either a cache-key invalidation (prompt drift) or actual 5-min TTL eviction, and the remedy would differ case by case.

**Phase B leftover — 1h TTL (`ENABLE_PROMPT_CACHING_1H=1`) (Not needed):**

The 5-min default is enough for every phase we've measured. Structuralist/recon hit cache with `cache_write=0` (didn't even need to write — already warm). Contrarian ran 215s and still completed inside 5 min of briefing start. No evidence of eviction-driven re-writes. If later data shows `cache_write_tokens` rising across same-prefix prompts in a multi-minute session, this is a one-env-var change — until then it's a bet with 2× write cost.

Relevant code:

- `src/maverick/executor/acp.py` (`_execute_with_retry`, `_ensure_session`)
- `src/maverick/executor/_connection_pool.py` (subprocess env construction — site for `ENABLE_PROMPT_CACHING_1H` if ever needed)

### 2.8 Consolidate Agent `_end_turn` Helpers

**Status:** Superseded *(2026-08-22)*

Resolved by deletion. The five xoscar agent actors this described do not
exist, and neither does the pattern: agents no longer end a turn by cancelling
an ACP session after a tool call forwards a payload, because there is no tool
call on the return path. `Agent._execute_via_runtime` returns the validated
payload directly.

The item's own deferral condition ("defer until a sixth agent-with-inbox gets
added") was never met and now never can be.

*Original observation.* Each of the five xoscar agent actors (`briefing`, `decomposer`, `implementer`, `reviewer`, `generator`) has its own ``_end_turn()`` helper that does the same thing: after ``on_tool_call`` forwards a payload to the supervisor, cancel the current ACP turn via ``self._executor.cancel_session(self._session_id)`` with best-effort error handling. The five copies are identical modulo the logger name.

This is a minor code smell rather than a bug — each copy is ~10 lines and they don't drift easily since the regression test in `test_super_init.py` forces the presence of the agent-side cancel pattern. Extraction options:

- Module-level helper: `async def end_acp_turn(executor, session_id, log_tag) -> None` in a shared utility module.
- Mixin class `AgentInboxEndTurnMixin` that every agent actor inherits alongside `xo.Actor`. Xoscar's MRO handles this cleanly since `xo.Actor` itself is just a class.

Either works; the mixin is slightly cleaner since the helper needs `self._session_id`, `self._executor`, and `self._actor_tag` anyway. Defer until a sixth agent-with-inbox gets added — at four copies it's just duplication; at six it's a pattern waiting for a name.

Relevant code:

- `src/maverick/actors/xoscar/briefing.py` (`_end_turn`)
- `src/maverick/actors/xoscar/decomposer.py` (`_end_turn`)
- `src/maverick/actors/xoscar/implementer.py` (`_end_turn`)
- `src/maverick/actors/xoscar/reviewer.py` (`_end_turn`)
- `src/maverick/actors/xoscar/generator.py` (`_end_turn`)

### 2.9 Move Tool-Required Framework Wrapper To System Prompt

**Status:** Superseded *(2026-08-22)*

> The wrapper this proposed to relocate no longer exists.
> `src/maverick/actors/xoscar/_agentic.py` was deleted with the rest of the
> actor tree, and the problem it solved — getting a model to reliably call
> `submit_*` as its return path — was removed at the root: airframe's
> structured output makes the provider enforce the result schema, so there is
> no "REQUIRED: submit via tool call" instruction to inject, and therefore no
> per-turn boilerplate to hoist into a system prompt.
>
> **Worth carrying forward:** the *original* bug is a real hazard that outlives
> this fix. A user-supplied document (a PRD, a spec) can be misread as
> instructions to the agent. Structured output removed one instance of that
> confusion; it does not make prompt injection from ingested documents
> impossible, and any future feature that appends framework instructions after
> user content should reintroduce explicit content markers.

*Original entry (per-turn token-overhead reduction).* Commit `3d1303f` introduced `build_tool_required_prompt()` /
`build_tool_required_nudge_prompt()` in `src/maverick/actors/xoscar/_agentic.py` to fix
a real prompt-injection-style refusal we hit on the earlybird PRD: the
codebase analyst was treating maverick's appended `## REQUIRED: Submit
via tool call` instruction as if the user-supplied document was telling
it what to do. The fix wraps every user prompt with framework-attributed
headers and `<<<BEGIN/END USER CONTENT>>>` markers that the model can
syntactically distinguish from the document.

The wrapper text is *identical* across turns within the same session
because `expected_tool` and `role_intro` don't vary turn-to-turn for a
given actor. So we send the same ~250 tokens of framework boilerplate
inside *every* user message in a session — for the decomposer detail
phase that's 5×, for the reviewer fix loop it can be more.

Anthropic prompt caching keys on contiguous *prefixes* of the full
message list, so the repeated wrappers don't hit cache (each new user
message is uncached at the byte level even when its prefix matches a
prior message's prefix). Within-session caching of prior turns still
works fine — there's no regression — but the per-turn input cost grows
linearly in the wrapper size.

Two approaches, in order of payoff:

1. **Move the framework instruction into the ACP session's system
   prompt** so it's sent once per session and the per-turn user message
   only carries the BEGIN/END user content block. The system prompt is
   also more authoritative in the model's training, which strengthens
   the prompt-injection defense as a side effect. This needs the ACP
   executor's `create_session(...)` path to expose a `system_prompt`
   parameter and thread it through `claude-agent-acp` (current call
   sites in the five actors all pass the wrapper inside `prompt_text`
   only).

2. **Drop the wrapper on follow-up turns within a session.** The agent
   already saw the framework framing on turn 1; turns 2..N could send
   bare `<<<BEGIN/END>>>` content. Smaller code change, smaller win
   (only saves the wrapper text on N-1 turns out of N), but no API
   change required.

Option (1) is the architecturally right move; option (2) is a band-aid
that's worth doing if the executor refactor is non-trivial. Defer until
prompt-cache cost is a measurable problem — the wrapper is ~250 tokens
on a typical 14k-token prompt (~1.8% overhead), and the
prompt-injection refusal it prevents costs ~50k tokens *and* a
user-visible failure.

Relevant code:

- `src/maverick/actors/xoscar/_agentic.py` (`build_tool_required_prompt`,
  `build_tool_required_nudge_prompt`)
- `src/maverick/executor/acp.py` (`create_session` — would need a
  `system_prompt` parameter for option 1)
- All five actor `_send_*` methods.

### 2.10 Per-Bead Complexity-Based Model Routing

**Status:** Partial — the routing survived the migration, one reading of it did not *(2026-08-22)*

The feature is real and in use. Complexity classification, the tier config
block, and per-complexity binding resolution all came through the Burr
migration; the surfaces moved, so the file references in the phase notes below
are largely stale (`tools/agent_inbox/*`, `library/actions/decompose.py` as an
actor path). Current homes:

- [src/maverick/config.py](src/maverick/config.py) — `lookup_tiers_config()`,
  which degrades a malformed block to `None` with a warning rather than failing
  startup.
- [src/maverick/squadron/tiers.py](src/maverick/squadron/tiers.py) —
  `TIER_ORDER`, the `DEFAULT_TIER` sentinel, `binding_for_complexity()`,
  `escalation_ladder()`.
- [src/maverick/runtime/agent_factory.py](src/maverick/runtime/agent_factory.py) —
  role-to-runtime resolution.

Three tier-aware actors exist: fly's `implementer` and `reviewer`, refuel's
`decomposer`.

**Two things are worth knowing that the phase notes below do not say:**

1. **Escalation ladders come from the squadron, never hardcoded.** A rung may
   only name a tier the squadron built a *distinct* binding for, so a squadron
   with no `tiers:` config yields a one-rung ladder and nothing escalates.
   Escalating to an identical binding is a retry wearing a costume, and it
   hides the fact that the binding never varied.
2. **`escalation_threshold` is still unimplemented on the implementer.** It
   means different things on different models — "escalation steps" on
   `DecomposerTiersConfig`, "fix rounds before promoting" on
   `ImplementerTiersConfig` — which is why `escalation_ladder()` takes an
   explicit `max_steps` rather than reading it. The implementer reading is not
   wired up. That is the concrete open work in this item.

*Original phase notes follow; treat their file paths as historical.*

**Background.** Bead workloads vary wildly inside a single epic — "create
LICENSE file" and "implement complete tax engine" are both single beads
under maverick's current model. They go through the same implementer
with the same model, which means we either pay frontier prices for
trivial work or accept weaker output on hard work. With opencode +
OpenRouter giving us cheap access to the full open-weight catalog
(GPT-OSS-20B at $0.13/Mtok up through Kimi K2.6 at ~$1.70/Mtok), it's
finally cheap to route by need.

**Phase 1 (implemented).** The decomposer classifies each bead at
outline time into one of `trivial | simple | moderate | complex`.
Schema additions span:

- `src/maverick/tools/agent_inbox/models.py`
  (`WorkUnitOutlinePayload.complexity`, `WorkUnitComplexity` Literal)
- `src/maverick/tools/agent_inbox/schemas.py`
  (`SUBMIT_OUTLINE` JSONSchema enum + classification rubric in the
  property description)
- [src/maverick/library/actions/decompose.py](src/maverick/library/actions/decompose.py)
  (`build_outline_prompt` — the decomposer's instruction set teaches
  the rubric and asks for honest classification)
- [src/maverick/workflows/refuel_maverick/models.py](src/maverick/workflows/refuel_maverick/models.py)
  (`WorkUnitSpec.complexity`)
- [src/maverick/flight/models.py](src/maverick/flight/models.py)
  (`WorkUnit.complexity`)
- [src/maverick/flight/serializer.py](src/maverick/flight/serializer.py)
  + [src/maverick/flight/loader.py](src/maverick/flight/loader.py)
  (markdown frontmatter round-trip; unknown enum values silently
  load as None for forward compat)
- [src/maverick/workflows/refuel_maverick/workflow.py](src/maverick/workflows/refuel_maverick/workflow.py)
  (write_work_units now logs the complexity distribution after refuel
  so users can see what the decomposer produced before trusting Phase 2
  routing with money)

Nothing routes on `complexity` yet — it's hint-only. This phase exists
so we can observe whether the decomposer's classifications match human
intuition over a few real refuels before wiring routing.

**Phase 2 (implemented): Tier routing for `implement` + escalation on
fix-loop overflow.**

Configuration shape:

```yaml
steps:
  implement:
    tiers:
      trivial:    { provider: opencode, model_id: openai/gpt-oss-20b }
      simple:     { provider: opencode, model_id: openai/gpt-oss-120b }
      moderate:   { provider: opencode, model_id: moonshot/kimi-k2-6 }
      complex:    { provider: claude,   model_id: opus }
    # Backward-compat: when `tiers` is omitted, fall back to the
    # current top-level `provider` / `model_id`.
    provider: opencode
    model_id: openai/gpt-oss-120b
```

Code-side changes:

1. Extend `StepConfig` (or a sibling) to carry an optional `tiers`
   mapping: `dict[Literal["trivial", "simple", "moderate", "complex"],
   StepConfig]`.
2. Thread the bead's `complexity` field through `ImplementRequest` so
   the implementer can resolve the right tier. The implementer already
   rotates its ACP session per bead via `new_bead(request)`, so per-bead
   model switching is feasible — `_executor.create_session` takes a
   config and we can build a different one per session.
3. **Escalation on fix-loop overflow.** When the supervisor's
   per-bead fix-loop count exceeds a configurable threshold (default 2),
   automatically promote the bead one tier and retry once. This is the
   safety net for misclassification: if the decomposer marks a bead as
   "simple" and the cheap model can't actually deliver, we burn a retry
   on the next tier up rather than spinning indefinitely on a model
   that's out of its depth. Recorded in the runway as a
   `complexity_escalated` event so the decomposer's classification
   accuracy can be measured over time.

**As shipped** (commit pending push):

- `ImplementerTierConfig` and `ImplementerTiersConfig` Pydantic models
  in [src/maverick/config.py](src/maverick/config.py).
- `FlyInputs.implementer_tiers` carries the parsed tiers config from
  the workflow into the supervisor.
- `FlySupervisor.__post_create__` spawns one `ImplementerActor` per
  defined tier (with merged StepConfig) when tiers are configured;
  legacy single-actor behaviour preserved when omitted.
- `_resolve_implementer_tier(complexity, escalation_level)` picks the
  tier name. Unrecognised/None complexity defaults to `moderate`.
  Sparse tier configs round DOWN to the nearest cheaper defined tier
  (and round UP only when nothing at-or-below exists).
- `_load_bead_context` extracts `complexity` from the work-unit md
  YAML frontmatter and stores it on the bead dict.
- `_send_fix` checks fix-round count against the configured
  `escalation_threshold` (default 2). When exceeded and a higher
  defined tier exists, promotes the bead one tier up, rotates the
  higher-tier actor's session, and emits a structured
  `fly.complexity_escalated`-style warning.

Risks worth flagging in the implementation:

- **Misclassification under-shoots.** Decomposer marks complex bead
  as "simple" → cheap model fails review → fix-loop retries on the
  same model → eventually escalates. Net cost: extra round-trips before
  the retry. Mitigated by the fix-loop-overflow escalation above.
- **Misclassification over-shoots.** Decomposer marks LICENSE file as
  "complex" → wasted money but no broken work. Lower-stakes than
  under-shooting.
- **Operational burden.** Users now maintain a `tiers` map. Mitigated
  by sensible shipped defaults.

Relevant code:

- [src/maverick/executor/config.py](src/maverick/executor/config.py)
  (StepConfig — the place to add optional `tiers`)
- `src/maverick/actors/xoscar/messages.py`
  (`ImplementRequest` — needs a `complexity` field)
- `src/maverick/actors/xoscar/implementer.py`
  (`send_implement` / `new_bead` — pick tier, build per-bead config)
- `src/maverick/actors/xoscar/fly_supervisor.py`
  (read bead complexity from the work-unit markdown / spec, pass in
  ImplementRequest, drive escalation when fix-loop count exceeds
  threshold)

**Phase 2b (implemented): Global ACP-subprocess cap with LRU eviction.**

Before Phase 2b, the only knob bounding live `claude-agent-acp` /
`opencode acp` subprocesses was *per-phase* (e.g.
`parallel.max_briefing_agents`, `parallel.decomposer_pool_size`). With
Phase 2 tier actors live, a mixed-complexity epic could spawn up to N
implementer subprocesses (one per tier actually used in the epic), all
alive until fly ended. On a small host that was too many.

The right shape is a single global ceiling: `parallel.max_agents = N`
caps total live ACP subprocesses across the whole workflow run. Per-
phase knobs are *soft ideals* (how much fan-out the phase wants); the
global cap is the hard ceiling.

**As shipped:**

- New :class:`SubprocessQuota`
  (`src/maverick/tools/agent_inbox/subprocess_quota.py`):
  pool-scoped acquire/release with LRU eviction of idle leases. The
  slot is held for the lifetime of the executor's subprocess pool, not
  per-prompt. Reentrant (a re-acquire by the same uid bumps activity).
- :class:`AgentToolGateway` accepts `max_subprocesses` and exposes
  `subprocess_quota`. Workflows pass `parallel.max_agents` through
  `actor_pool(max_subprocesses=...)`.
- :class:`AcpStepExecutor` accepts `subprocess_quota` + `actor_uid`;
  threads them into :class:`ConnectionPool.get_or_create` (acquire
  before first spawn) and `cleanup()` (release).
  `prompt_session` brackets each prompt with `mark_busy`/`mark_idle`
  so mid-prompt actors are shielded from eviction.
- New `cleanup_for_eviction()` on the executor: closes subprocesses
  *without* re-releasing the quota slot (the quota already popped the
  lease). Invoked via the `_on_evicted` bridge wired into the
  connection pool.
- :class:`AgenticActorMixin` exposes a `_build_quota_aware_executor()`
  helper used by every actor's `_ensure_executor()` and an
  `_invalidate_sessions_for_eviction()` hook (default: clears
  `self._session_id`) wired in via `set_session_invalidator`.
- `ParallelConfig.max_agents` flipped from advisory-only to the hard
  ceiling. Default stays at 3; tune up on richer hosts. Eviction cost
  is documented (~200ms handshake + ACP-session conversation context
  loss).

Per-phase knobs (`max_briefing_agents`, `decomposer_pool_size`,
`max_parallel_reviewers`) keep their existing semantics — they bound
*how much parallelism a phase wants*. With `max_agents=2` and
`max_briefing_agents=3`: 2 briefings concurrent, 3rd waits for an
eviction or release.

**Phase 3 (implemented): Extend tier routing to `review`, `fix`,
`decompose_detail`.**

Each of these has the same per-unit invocation pattern as `implement`
and benefits from the same complexity gating.

**As shipped:**

- New :class:`ReviewerTiersConfig` and :class:`DecomposerTiersConfig`
  in [src/maverick/config.py](src/maverick/config.py) — both reuse
  :class:`ImplementerTierConfig` for per-tier overrides.
- :class:`FlySupervisor` extracted the implementer's two-step tier
  resolver into :meth:`_resolve_tier_in` (a static method working
  against any actor map). Reviewer reuses it via
  :meth:`_resolve_reviewer_tier`. Reviewer has no escalation — review
  is one-shot per round; the *implementer* is the actor that escalates
  on fix-loop overflow.
- :class:`FlyInputs.reviewer_tiers` carries the parsed config; when
  set, the supervisor spawns one ReviewerActor per defined tier and
  routes `new_bead` + `send_review` through `_reviewer_for(complexity)`.
- :class:`RefuelInputs.decomposer_tiers` carries the parsed config;
  when set, the supervisor replaces the round-robin pool with one
  DecomposerActor per defined tier (each in `pool` role). Per-unit
  detail prompts route through the unit's outline complexity.
- The fix path is automatically tier-routed because it runs on the
  same per-tier ImplementerActor that handled the original implement
  prompt — no separate wiring needed.
- Workflows extract `actors.fly.reviewer.tiers` and
  `actors.refuel.decomposer.tiers` from `maverick.yaml` and pass them
  through the supervisor inputs.

**Tradeoff (decompose_detail):** tier mode trades cross-worker
parallelism for per-tier model differentiation. With one worker per
tier, multiple same-complexity units queue on that worker. Crank
`parallel.decomposer_pool_size` AND enable tiers if both knobs
matter; otherwise pick the one that fits the workload.

**Aggregate review** (the final cross-bead check) is *not* tiered —
it sees diff across the whole epic and can't be classified per-bead.
Stays on the base reviewer config (effectively the legacy single-
actor path even when per-bead reviewer tiers are configured).

Suggested defaults:

```yaml
steps:
  review:
    tiers:
      trivial:    { provider: opencode, model_id: openai/gpt-oss-20b }
      simple:     { provider: opencode, model_id: openai/gpt-oss-120b }
      moderate:   { provider: opencode, model_id: zai/glm-5-1 }
      complex:    { provider: claude,   model_id: sonnet }
  fix:
    tiers:
      trivial:    { provider: opencode, model_id: openai/gpt-oss-20b }
      simple:     { provider: opencode, model_id: openai/gpt-oss-120b }
      moderate:   { provider: opencode, model_id: openai/gpt-oss-120b }
      complex:    { provider: opencode, model_id: moonshot/kimi-k2-6 }
  decompose_detail:
    tiers:
      trivial:    { provider: opencode, model_id: openai/gpt-oss-120b }
      simple:     { provider: opencode, model_id: openai/gpt-oss-120b }
      moderate:   { provider: opencode, model_id: openai/gpt-oss-120b }
      complex:    { provider: opencode, model_id: moonshot/kimi-k2-6 }
```

`decompose_detail` is mostly mechanical "fill in instructions for this
work unit" — the primary outline pass already did the architectural
work. Most beads can use a single mid-tier model regardless of
complexity; only `complex` beads benefit from extra reasoning capacity
during detail generation.

Aggregate review (the final cross-bead check) should *not* tier — it
sees diff across the whole epic and can't be classified per-bead. Keep
it on a fixed frontier model.

**Other axes worth considering, but not for v1**

Complexity is the right *first* axis because it's the cleanest signal
of "how much intelligence is needed." Other axes that may matter
eventually:

- **Domain** — writing tests vs business logic. A "moderate" test bead
  probably wants a different model than a "moderate" engine bead.
- **Risk** — security-critical vs UI tweak. Lets you keep frontier
  review on auth code regardless of complexity.
- **File language** — TypeScript-heavy beads vs Python-heavy.
  Specialists differ.

These are refinements over per-bead-complexity, not replacements. Land
Phase 2 + Phase 3 first, see how often the misclassification cases
cluster on a particular dimension, then add the next axis if they do.

### 2.11 Auto Tech-Debt Beads From Approved-With-Findings Reviews

**Status:** Active *(re-checked 2026-08-22 — still accurate)*

Verified against the current graph: `review` transitions to
`create_human_bead` only when `needs_human_review` is set, otherwise straight
to `commit`. Non-blocking findings on an approved review are still recorded to
runway and dropped. Substitute "the `record_outcome` action" for "the
supervisor" in the proposal below; everything else stands.

**Background.** Today the fly review loop has a hard binary: a review is
either `approved` (bead commits, fly moves on) or `not approved` (fix
loop fires). But reviewers regularly come back with `approved` AND a
list of non-blocking findings — improvements they noticed but didn't
think warranted gating the bead. Those findings get:

* recorded to runway (`record_review_findings`) — historical context
  for future briefings,
* captured in the per-bead `fly-report.json` — audit trail,
* and otherwise *dropped on the floor*. No follow-up bead, no surface
  in the aggregate review prompt, no human nudge.

In practice this means a moderate-tier reviewer flagging "this should
use a context manager" disappears into the runway and never becomes
work someone or some implementer addresses. As cheap-tier reviewers
flag more (per Phase 3, simple/moderate beads now get reviewed by
cheaper models with looser standards), the lost-finding rate grows.

**Proposal.** When a review is `approved` AND contains findings at or
above a configurable severity floor (default `major`), the supervisor
auto-files each finding as a tech-debt bead under the same epic.

**Bead shape:**

```yaml
parent: <epic_id>            # e.g. sample_maverick_project-e6c
type: task
labels: [tech-debt]
metadata:
  source_bead: <bead_id>     # e.g. sample_maverick_project-e6c.8
  source_round: 2            # which review round produced it
  severity: major
  reviewer_tier: complex     # which tier flagged it
  finding_text: "<original message>"
title: "[tech-debt] <one-line summary from finding>"
```

**Design choices:**

* **Child of the epic, no `depends_on`.** The source bead already
  shipped and the reviewer explicitly didn't gate on these — they're
  not blockers. Filing under the epic preserves lineage without
  blocking epic closure. Six months later, "why are we using this
  awkward pattern?" → one click to the source review finding.
* **`tech-debt` label** so users can filter the normal ready queue
  (`bd ready --exclude-label tech-debt`) or batch-triage them
  (`bd ready --label tech-debt`).
* **Severity floor (default `major`)** to keep noise down. `minor`
  findings stay in the runway only. Configurable per project via
  `fly.tech_debt_severity_floor` so teams can tighten or loosen.
* **One bead per source finding (no dedupe in v1).** If the same
  pattern fires across 5 beads in an epic, you get 5 tech-debt beads.
  Dedupe (by similarity-hash of `finding_text` within an epic) is a
  v2 add if it gets noisy in practice.

**Cost considerations:**

* No extra LLM cost — reviews already produce findings; this only
  changes what we *do* with them.
* Linear bd writes per qualifying finding. Negligible at typical fly
  volumes (≤5 beads × ≤3 review rounds × ~3 findings).

**Code-side changes:**

* New `record_tech_debt_findings` action in
  [src/maverick/library/actions/runway.py](src/maverick/library/actions/runway.py)
  (sibling of `record_review_findings`).
* `FlySupervisor._review_loop` calls it when a review returns
  `approved=True` with findings ≥ severity floor.
* New `fly.tech_debt_severity_floor: Literal["minor", "major", "critical"]`
  field in `MaverickConfig`. Default `"major"`.
* Bead-creation goes through the existing `BeadCreatorActor` /
  `bd add` path — adds the parent + label + metadata fields.
* CLI surfacing: a one-line `created N tech-debt bead(s)` event after
  each approved-with-findings review so the user sees what got filed.

**Telemetry / future tuning:**

The runway already tracks per-tier review patterns. Add a
`tech_debt_created` event so we can later answer: "do moderate-tier
reviewers create more tech-debt-worthy findings than complex-tier
ones?" That's a signal for whether to bump moderate review up a tier
in the default config.

**Out of scope for v1:**

* Auto-resolution of tech-debt beads when a later bead happens to fix
  the issue.
* GitHub Issue mirroring (the existing `review-and-fix-with-registry`
  fragment does this for the legacy review path; we'd port it later
  if there's demand).
* Cross-epic dedupe (only same-epic dedupe is even on the table).

**Relevant code:**

* `src/maverick/actors/xoscar/fly_supervisor.py`
  (`_review_loop` — natural call site)
* [src/maverick/library/actions/runway.py](src/maverick/library/actions/runway.py)
  (existing `record_review_findings` — add a sibling)
* [src/maverick/library/actions/beads.py](src/maverick/library/actions/beads.py)
  (existing bead creation — extend with parent + label fields)
* [src/maverick/config.py](src/maverick/config.py) (new
  `tech_debt_severity_floor` knob)
* `src/maverick/library/fragments/review-and-fix-with-registry.yaml`
  (precedent for how the legacy review path handles this — worth
  reading before implementing for consistency)

### 2.12 Free OpenRouter Models Often Skip MCP Tool Calls

**Status:** Reframed — the finding survived, the mechanism didn't *(2026-08-22)*

There is no MCP tool call to skip. But the underlying observation — **weak or
free-tier models fail to produce a valid structured result, and the failure
surfaces as an empty or unusable turn** — survived the migration intact. It is
now expressed as airframe raising
`error_max_structured_output_retries` after exhausting its internal attempts.

Live evidence post-migration: issue **#166**, where the contrarian briefing
agent fails structured output on `claude-haiku-4-5` twice in a row on the same
input, five internal retries each time, while its three sibling personas on the
identical binding succeed every run.

Both of the item's proposals translate directly and are still unbuilt:

- **Detect at config-load time** — warn when a role or tier is bound to a model
  known to be unreliable for structured output. The `:free` suffix heuristic
  generalizes to "model capability is not validated against the payload
  complexity the role demands."
- **Auto-fallback on consecutive failures** — escalate a tier rather than
  failing the unit. The escalation ladder now exists
  ([src/maverick/squadron/tiers.py](src/maverick/squadron/tiers.py)) but is
  driven by complexity and fix rounds, not by structured-output failure.

*Original entry (known limitation, hit during 2026-04-27 Phase 3 validation).*

When `qwen3-coder:free` was wired into the moderate implementer tier
via opencode/OpenRouter, the agent returned empty responses on both
the initial prompt and the self-nudge — the model finished its turn
without calling `submit_implementation` at all, and our `_run_with_self_nudge`
helper correctly routed a `PromptError`. We've also seen similar
patterns with other `:free`-suffixed OpenRouter models in earlier
sessions.

The hypothesis: free-tier OpenRouter routing tends to land on smaller
or more aggressively rate-limited variants that either (a) don't
reliably parse and emit MCP tool-call structure, or (b) are throttled
hard enough that the response never lands within the prompt timeout.
Either way, the mailbox-pattern actors (which require an MCP tool
call to produce any useful output) silently fail.

What we'd want:

- **Detect the failure mode at config-load time**: when a tier is
  configured with `provider: opencode` + `model_id: *:free`, emit a
  warning that MCP-tool reliability is not guaranteed and recommend a
  fallback tier or a paid alternative.
- **Optionally auto-fallback on consecutive empty turns**: if an actor
  produces N empty turns in a row, escalate the bead one tier up
  (similar to the implementer fix-loop escalation in §2.10 Phase 2)
  rather than just failing the bead. The runway already records
  per-bead outcomes — this would be observable.
  *Status note*: implemented for the **decomposer detail** path in §6.2
  Tier 1.6. Still open for briefing / generator / reviewer mailbox
  paths.
- **Prefer copilot or claude for tool-required actors**: the four
  agentic actor types (briefing, decomposer, implementer, reviewer,
  generator) all *require* MCP tool calls. The non-agentic `steps`
  paths (navigator, structuralist, recon, etc. when not using the
  mailbox pattern) tolerate text-only responses fine. Document this
  distinction in the config schema so users don't accidentally wire
  a free-tier model into a mailbox actor.

Workaround in the meantime: **use copilot's free tier (gpt-5-mini) or
gemini's free tier instead of OpenRouter `:free` models** for any
tier that powers a mailbox actor. Both reliably call MCP tools.

Relevant code:

- `src/maverick/actors/xoscar/_agentic.py`
  (`_run_with_self_nudge` — natural place to count consecutive empty
  turns and trigger escalation)
- [src/maverick/config.py](src/maverick/config.py) (warn on
  `:free`-model + mailbox-actor config combos)

## 3. Learning, Feedback, And Telemetry

### 3.1 Observational Memory For Runway

**Status:** Active

Runway has already moved partway toward summary-first memory, but it has not fully crossed over.

What exists:

- episodic records;
- consolidation logic;
- semantic seed files.

What is missing:

- one canonical, always-in-context summary as the primary memory surface;
- a cleaner split between summary context and deeper retrieval;
- process-level learning as a first-class output.

Relevant code:

- [src/maverick/workflows/fly_beads/_runway.py](src/maverick/workflows/fly_beads/_runway.py)
- [src/maverick/library/actions/consolidation.py](src/maverick/library/actions/consolidation.py)
- [src/maverick/runway/seed.py](src/maverick/runway/seed.py)

### 3.2 Supervisor Agent For Adaptive Orchestration

**Status:** Active

The repo still has deterministic orchestration with static timeouts, thresholds, and retry budgets. The newer code has better typed payloads and clearer event paths, but that only strengthens the case for a small advisor layer.

The most important constraint remains the same:

- the workflow loop should stay authoritative;
- any supervisor agent should advise or patch policy, not replace routing logic.

**Reconciliation note (2026-08-22):** reframe against Burr. There is no
supervisor to make adaptive — orchestration is a declared state machine, so
the natural shape of this item is now a *policy layer that influences
transitions and bound parameters* (retry budgets, tier selection, timeouts),
leaving `burr_graph.py`'s topology authoritative. That is a smaller and
better-defined change than the original "advisor actor alongside a supervisor".

Relevant code:

- [src/maverick/burr/driver.py](src/maverick/burr/driver.py)
- [src/maverick/workflows/fly_beads/burr_graph.py](src/maverick/workflows/fly_beads/burr_graph.py)
- [src/maverick/workflows/base.py](src/maverick/workflows/base.py)
- [src/maverick/session_journal.py](src/maverick/session_journal.py)

### 3.3 Supervisor-Driven Resource Tuning

**Status:** Active

Static resource envelopes remain the default. This is still a separate opportunity from the broader supervisor-agent idea because it needs durable runtime metrics, not just policy hooks.

This item now depends even more clearly on better telemetry and traceability than it did in the older notes.

### 3.4 Step-Level Evals And Prompt Or Provider Testing

**Status:** Active

There is still no first-class eval layer, no fixture capture pipeline, and no dedicated command for replaying a step across provider or prompt variants.

This remains high leverage because it speeds up every other optimization loop.

**Reconciliation note (2026-08-22):** still unbuilt, and the seam improved.
airframe is a single interception point for every LLM call, and agents already
declare typed `result_model`s — so a fixture-capture pipeline now has one place
to hook and a schema to validate replays against, neither of which was true in
April. Issues **#17** (evaluator protocol), **#26** (OpenInference tracing), and
**#27** (Phoenix backend) propose a concrete implementation; note that #27's
design assumes a session-log substrate that should be re-checked before it is
picked up.

Relevant code:

- [src/maverick/runtime/agent_factory.py](src/maverick/runtime/agent_factory.py)
- [src/maverick/agents/base.py](src/maverick/agents/base.py)
- [src/maverick/cli/workflow_executor.py](src/maverick/cli/workflow_executor.py)
- [pyproject.toml](pyproject.toml)

### 3.5 Structured Telemetry Via OpenTelemetry GenAI Conventions

**Status:** Active

No OpenTelemetry or OpenLLMetry dependencies are present today, and there is no standard trace model spanning workflows, actor invocations, tool calls, or token usage.

Why it still matters:

- it unlocks adaptive orchestration and resource tuning;
- it makes provider comparison tractable;
- it gives child-process observability that structlog alone does not.

Relevant code:

- [pyproject.toml](pyproject.toml)
- [src/maverick/events.py](src/maverick/events.py)
- [src/maverick/logging.py](src/maverick/logging.py)

### 3.6 Unified Trace And Correlation Envelope

**Status:** Active

This is a distinct, codebase-driven opportunity that should exist whether or not full OTel support lands soon.

Pieces already exist:

- workflow identifiers in [src/maverick/events.py](src/maverick/events.py);
- run metadata in [src/maverick/runway/run_metadata.py](src/maverick/runway/run_metadata.py);
- per-run directories under `.maverick/runs/<run-id>/` — the land report, protection-blocks artifact, and spec-chain checkpoints all key off the same run id.

What is missing is one causality envelope that ties logs, events, Burr state
transitions, and persisted artifacts together end to end. Confirmed still
missing on 2026-08-22: `grep -rn trace_id src/` returns nothing. The `run_id`
is the closest thing to a correlation key today, and it is threaded by
convention rather than carried in a typed envelope. See issue **#18**.

### 3.7 Canonical Artifact Rendering And Formatting

**Status:** Active

The codebase has started moving toward canonical renderers, especially around generated flight plans, but it is not yet universal.

What exists:

- canonical flight plan markdown in [src/maverick/workflows/generate_flight_plan/markdown.py](src/maverick/workflows/generate_flight_plan/markdown.py);
- typed agent result payloads in [src/maverick/payloads.py](src/maverick/payloads.py);
- **a worked example of getting this right** (2026-08-22): spec 053's
  `entry_to_dict` ([src/maverick/assumptions/serialize.py](src/maverick/assumptions/serialize.py))
  is one row projection shared verbatim by `review --list --json` and the land
  report, specifically so the two surfaces cannot drift. Spec 056 did the same
  for `BlockRecord.to_dict()` across its event stream and its artifact. That is
  the pattern this item is asking to generalize.

What should happen next:

- give every durable artifact a single renderer and a single reader;
- stop scattering format rules across ad hoc JSON dumps and inline markdown assembly.

### 3.8 Review Prompts Don't Emit `acp_executor.prompt_usage`

**Status:** Implemented, now moot *(2026-08-22)*

> Fixed in the ACP executor, which no longer exists. Cost/usage telemetry is
> now airframe's, surfaced through each `Agent`'s cost sink into the squadron.
> Retained only because the *shape* of the fix is a good habit: the usage log
> fired from a `finally` with an `exit_path` field, so no return path —
> success, timeout, error, circuit-breaker — could bypass it.

*Original entry:* **Status:** Implemented

Originally observed during the 2026-04-24 e2e run on `sample-maverick-project`. The fly run closed 12 beads with this log breakdown:

| signal | count |
|---|---|
| ``acp_executor.session_created`` with ``step_name=review`` | 13 |
| ``bead_closed`` (review gate passed) | 12 |
| ``acp_executor.prompt_usage`` with ``step_name=review`` | **0** |

Reviews clearly succeeded (12 beads closed) but ``prompt_usage`` never logged for them. Implementer prompts on the same run logged correctly. Hypothesis was that the reviewer's agent-side cancel from ``on_tool_call._end_turn`` was racing the response path, routing prompt() returns through a branch that bypassed the inline log.

**Fix shipped:** rather than chase the specific bypass, made the log structurally unbypassable. ``prompt_session`` in `src/maverick/executor/acp.py` now logs ``acp_executor.prompt_usage`` from a ``finally`` block with a new ``exit_path`` field tracked across the prompt's lifetime. Locals ``usage`` and ``exit_path`` are initialized to safe defaults (``None`` / ``"unknown"``) and updated as execution progresses; the finally fires the log regardless of whether the path was success, timeout, ``AcpRequestError``, circuit-breaker abort, or any unexpected exception. ``usage`` is captured *before* the circuit-breaker check so token counts stay visible on aborts.

**Tests added** in ``TestPromptUsageExitPath`` (`tests/unit/executor/test_acp_executor.py`) — one per exit path:

- ``success`` → ``usage_reported=True`` with token counts.
- ``timeout`` → ``usage_reported=False`` (no response captured).
- ``acp_request_error`` → ``usage_reported=False``.
- ``circuit_breaker_aborted`` → ``usage_reported=True`` (usage captured before the abort fires, so we still see the burned tokens).

Reflection: the original framing assumed the bug was a missing branch in the executor. The pragmatic fix was to remove the branching dependency entirely — making the log fire unconditionally is both more diagnosable (``exit_path`` tells us what really happened) and immune to future race conditions of the same shape. ``_run_single_attempt`` (one-shot path used by briefing/decomposer/curator) still has the inline log; if a similar gap surfaces there, the same finally-block pattern applies.

### 3.9 Commit Provenance For Evals

**Status:** Partial — Layer 1 (Refs: trailer) implemented; Layer 2 (per-attempt runway capture) still active.

The CuratorAgent system prompt deliberately strips bead IDs and pipeline mechanics from commit messages so public git history reads as human-authored. Pre-`land`, the bead linkage exists ([src/maverick/workflows/fly_beads/_commit.py](src/maverick/workflows/fly_beads/_commit.py) writes ``bead({id}): {title}``), but the curator's squash + describe pass erased it by design. For eval work (§3.4), commit-level traceability is one of the two natural query axes.

**Layer 1 — `Refs:` trailer in landed commits (Implemented):**

CuratorAgent's `SYSTEM_PROMPT` now keeps stripping bead IDs from the subject but instructs the model to extract every ``bead(id):`` source prefix and emit a single ``Refs: <id>, <id>`` trailer at the bottom of every rewritten message — squashes plural, snapshots empty.

Two new helpers in the same module:

- ``extract_bead_ids(description)`` — pulls IDs from any ``bead(<id>):`` prefixes in a commit description. Anchors at line start so casual mentions inside body text don't generate false positives.
- ``ensure_refs_trailers(plan, commits)`` — safety-net post-processor. For each ``describe`` step, if the new message lacks a ``Refs:`` trailer, append one derived from the *target change_id*'s own bead IDs. No-op when the trailer is already present (curator followed the prompt) or when the source is a snapshot. The land command in [src/maverick/cli/commands/land.py](src/maverick/cli/commands/land.py) calls it after ``parse_plan``.

Caveat documented in the helper: post-processing only knows the describe target's bead IDs, not commits that were *squashed into* the target before the describe. Squash-merge attribution still relies on the LLM following the prompt — the safety net guarantees a trailer exists, the prompt is responsible for cross-commit completeness.

Tests in ``TestExtractBeadIds`` and ``TestEnsureRefsTrailers`` (`tests/unit/agents/test_curator.py`) cover: single bead, multiple beads in a squash, snapshot (no trailer), pre-existing trailer (preserved), unknown change_id (left alone), multi-paragraph body (blank-line separator preserved), non-describe commands (untouched).

**Layer 2 — Runway as system of record for full provenance (Active):**

The trailer is the join key from public git history into runway. Without runway behind it as the system of record for *(provider, model, prompt_hash, fix-loop history)*, ``Refs:`` is a foreign key pointing at nothing. Some of this already lands via ``record_bead_outcome`` / ``record_review_findings``; what's missing is per-attempt ``(provider, model, prompt_hash)`` capture on the implementer and reviewer paths.

**Out of scope for v1:**

- Embedding full prompts in the trailer. Too big; runway is the right home.
- jj-native metadata via the still-pending design in jj-vcs/jj #8166 / #6664. The trailer approach is git-tooling-agnostic and works today.
- Notes-based storage. Squash and rebase make ``refs/notes/*`` brittle, and jj has no ``jj notes`` command yet.

**Relevant code:**

- `src/maverick/agents/curator.py` (SYSTEM_PROMPT, ``extract_bead_ids``, ``ensure_refs_trailers``)
- [src/maverick/cli/commands/land.py](src/maverick/cli/commands/land.py) (calls ``ensure_refs_trailers`` after ``parse_plan``)
- [src/maverick/workflows/fly_beads/_commit.py](src/maverick/workflows/fly_beads/_commit.py) (existing ``bead({id}): {title}`` source)
- [src/maverick/runway/](src/maverick/runway/) (Layer 2 — per-attempt ``(provider, model, prompt_hash)`` capture, still pending)

## 4. Developer Experience And Platform

### 4.1 Strengthen TDD As The Primary Feedback Loop

**Status:** Active

The repo already values tests highly, but the opportunity still stands because the prompt and artifact layers do not yet make the test target as explicit as they could.

The best next move is not ideological TDD messaging. It is tighter coupling between acceptance criteria, test specification fields, and the actual implementation loop.

Relevant code:

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [src/maverick/library/actions/decompose.py](src/maverick/library/actions/decompose.py)
- [src/maverick/workflows/refuel_maverick/models.py](src/maverick/workflows/refuel_maverick/models.py)

### 4.2 Reduce jj Installation Friction

**Status:** Active

There is still no true fallback path for environments that cannot or should not rely on jj.

The future shape of this work should be informed by the hidden workspace direction, not the older colocated-jj assumptions. The most promising version is likely:

- keep jj as the primary internal engine;
- bundle or manage it more transparently;
- only add a degraded fallback if the operational cost is justified.

### 4.3 Idempotent `maverick init`

**Status:** Implemented

Originally fail-fast: `run_init` raised ``ConfigExistsError`` early when ``maverick.yaml`` was present without ``--force``. Sub-pieces (``_init_beads`` via ``bd init --force``, ``_maybe_init_runway`` via the ``is_initialized`` skip) were already idempotent, but the top-level command refused to re-run.

**Fix shipped** in [src/maverick/init/__init__.py](src/maverick/init/__init__.py) and [src/maverick/cli/commands/init.py](src/maverick/cli/commands/init.py): when ``config_path.exists() and not force``, ``run_init`` now takes the *idempotent re-init* path:

1. Verify prerequisites (sanity check — useful when upgrading maverick or moving machines).
2. Skip detection / provider discovery / config generation / config write — all of those would either re-do expensive work for no reason or risk overwriting the user's customizations.
3. Run ``_init_beads`` (already idempotent via ``bd init --force``).
4. Run ``_maybe_init_runway`` (already skips when initialized).
5. Return ``InitResult(config_existed=True, config=None, detection=None, …)``.

The CLI branches on ``result.config_existed``: prints "Already initialized at <path> — beads + runway re-checked, configuration unchanged" and a hint about ``--force``. Skips the model-discovery and actor-distribution rewrite that would otherwise mutate the existing config's actors section.

``InitResult.config`` was widened to ``InitConfig | None`` so the idempotent path doesn't have to fabricate a placeholder. ``to_dict`` handles the None.

**Tests added:**

- ``test_init_is_idempotent_when_config_exists`` ([tests/integration/test_init_command.py](tests/integration/test_init_command.py)) — replaces the old ``test_init_config_exists_error``: existing config preserved verbatim, exit code 0, "Already initialized" in output, ``detect_project_type`` not called (fast path skipped detection), prereqs still ran.
- ``test_config_existed_defaults_false`` and ``test_idempotent_re_init_shape`` ([tests/unit/init/test_models.py](tests/unit/init/test_models.py)) — guard the new InitResult shape.

The pre-existing ``test_init_force_overwrites_config`` continues to verify that ``--force`` still regenerates from scratch.

### 4.4 `maverick land` Fails On `.beads/issues.jsonl` Merge Conflict

**Status:** Implemented

Originally hit during 2026-04-27 Phase 3 live validation. When a fly run ends with the workspace's `.beads/issues.jsonl` deleted (bd's dolt backend regenerates it on demand) and the source repo has modified the same file, `maverick land` was failing with:

```
CONFLICT (modify/delete): .beads/issues.jsonl deleted in
maverick/sample-maverick-project and modified in HEAD.
```

Both `--no-curate` and `--finalize` modes hit it. The diff was spurious — `.beads/` is a dolt-managed working area whose files represent the *current shared dolt state* (same on both branches; bd writes back to the shared DB), so the JSONL view's content can diverge across snapshots without the underlying state actually changing.

**Fix shipped** in [src/maverick/library/actions/git.py](src/maverick/library/actions/git.py): `git_merge` now has a third recovery branch (alongside the existing `already up to date` and `untracked working tree files would be overwritten` cases) that triggers on `CONFLICT (modify/delete)` output. The branch:

1. Calls `git status --porcelain=v1` to enumerate unmerged paths and their codes.
2. Splits them into dolt-managed `.beads/*` modify/delete entries (UD or DU codes) and everything else.
3. If *any* non-dolt unmerged path remains, runs `git merge --abort` to restore a clean working tree and bubbles the original error — we never silently drop a real conflict.
4. Otherwise, runs `git rm -f <path>` for each dolt path (accepting deletion; bd will regenerate on next access) and completes the merge with `git commit --no-edit` using the auto-generated MERGE_MSG.

**Tests added** in `TestGitMerge` ([tests/unit/library/actions/test_git_actions.py](tests/unit/library/actions/test_git_actions.py)):

- `test_resolves_dolt_modify_delete_by_accepting_deletion` — UD direction (FUTURE.md case).
- `test_resolves_dolt_modify_delete_in_either_direction` — DU direction (HEAD deleted, theirs modified).
- `test_aborts_when_non_dolt_path_also_conflicts` — guard against silently dropping real conflicts.

Reflection: the `.gitattributes merge=ours` approach considered earlier needs a custom merge driver registered in `.git/config`, which is per-clone and not committed — so it doesn't help shared / cloned repos. The runtime recovery in `git_merge` works for both new and existing projects with no init migration.

**Out of scope (separate ergonomic improvements):**
- `.gitattributes` setup at `maverick init` for explicit declaration (still useful as documentation, but the runtime fix already handles the conflict).
- Auto-adding `.beads/issues.jsonl` to `.gitignore` so it's never tracked. Existing repos with the file already committed make this a breaking change; revisit if the file becomes universally regenerable.

### 4.5 Defer bd-state Inference To bd Itself

**Status:** Reframed — proposed approach doesn't work for embedded
mode; see "Investigation findings" below.

#### Original motivation

We currently infer "is bd initialized?" by probing the filesystem:
``BeadClient.is_initialized()`` checks for ``.beads/embeddeddolt/`` (or
``dolt/``) AND for a valid ``metadata.json`` with ``issue_prefix``.
``_clear_invalid_bd_state`` likewise inspects metadata.json and decides
whether to wipe based on field validity.

That contract drifted from bd's own definition of "initialized" twice
during the 2026-04-27 / 2026-04-28 sessions:

1. ``BeadClient.is_initialized`` originally checked only the directory.
   bd's ``bd create`` rejected projects whose metadata was missing
   ``issue_prefix`` even though our probe said "ready" — leading to a
   670-second refuel run that died on the bead-creation step. Fixed
   by tightening the probe.
2. ``_clear_invalid_bd_state`` originally cleared only on bad
   ``dolt_database`` names, not on missing ``issue_prefix``. Stale
   ``config.json`` (with ``sync.remote`` pointing at a non-Dolt git
   URL) survived cleanup; the next ``bd init`` then tried to clone
   Dolt data from a regular git remote and failed. Fixed by widening
   the cleanup trigger and the wipe set.

Original proposal: replace the filesystem probe with a call to
``bd doctor --json`` (or similar) and trust bd's own "is this healthy?"
answer.

#### Investigation findings (2026-04-28)

**``bd doctor`` is not available in embedded mode.** Running it on a
project initialized with maverick's default ``bd init`` (embedded-Dolt
backend) prints:

```
Note: 'bd doctor' is not yet supported in embedded mode.

For embedded mode troubleshooting:
  • Verify database exists:  ls -la .beads/embeddeddolt/
  • Check bd version:        bd version
  • Reinitialize if needed:  bd init --force
  • Switch to server mode:   bd init --server
```

bd's own remediation guidance for embedded mode is filesystem
inspection — i.e., what we already do.

**Other bd read-only commands don't catch half-init either.**
Empirically tested against a half-init state (embeddeddolt directory
present, ``metadata.json`` missing ``issue_prefix``):

| Command | Half-init result | Useful as probe? |
|---|---|---|
| ``bd doctor`` | `Note: 'bd doctor' is not yet supported in embedded mode` | No |
| ``bd status`` | succeeds, prints empty stats | No |
| ``bd info`` | succeeds, prints empty stats | No |
| ``bd context`` | errors on missing git repo (different cause) | No |
| ``bd list --json`` | succeeds, returns ``[]`` | No |
| ``bd ready --json`` | succeeds, returns ``[]`` | No |
| ``bd query --json`` | succeeds (modulo expression parse) | No |
| ``bd create`` | errors with "issue_prefix config is missing" | Yes — but it's destructive, can't use as a probe |

The only bd command that catches the half-init state is ``bd create``
itself — and that mutates state, so we can't use it for read-only
detection at preflight time.

#### Realistic next steps

The original premise ("bd has an authoritative checker") doesn't hold
for embedded mode in the current bd CLI surface. Three forward paths,
none of them simple:

1. **Contribute embedded-mode support to bd's ``doctor`` upstream.**
   The cleanest fix; turns this from a maverick problem into a one-time
   bd PR. Likely needs equivalent metadata-validation logic on the bd
   side, which the maintainers may or may not want.

2. **Migrate maverick to bd's server mode.** ``bd doctor`` works in
   server mode. But server mode runs an external dolt sql-server
   (per-project or shared), which adds an operational dependency we
   currently don't have. Worth considering if/when other server-mode
   benefits accumulate.

3. **Stay on filesystem inspection but minimise drift.** Document bd's
   expected metadata schema in code comments, write a regression test
   per known-required field (``dolt_database``, ``issue_prefix``), and
   add new fields as we encounter them. This is what we have now; the
   defensive wipe in ``_clear_invalid_bd_state`` is generous enough
   that recovery is reliable even when our probe is wrong.

Realistically, the maverick bug rate from contract drift is one
incident per ~6 months — not a frequent enough failure mode to
justify the operational cost of (1) or (2). (3) is what we're doing
and what the code reflects after the 2026-04-28 fixes.

If a third drift incident materialises, revisit (1) or (2). Until
then, this stays "Reframed" — the original proposal isn't viable, and
the current filesystem-inspection approach is the pragmatic
alternative.

Relevant code:

- [src/maverick/beads/client.py](src/maverick/beads/client.py)
  (``is_initialized``, lifecycle ops)
- [src/maverick/init/__init__.py](src/maverick/init/__init__.py)
  (``_clear_invalid_bd_state``)

### 4.6 Reduce MCP Tool-Call Reliability As A Hard Dependency

**Status:** Superseded — solved at the root *(2026-08-22)*

> This item's premise was that structured output *depends on the model
> choosing to call a tool*, which is model-dependent and therefore unreliable.
> That dependency is gone. Agents declare a `result_model` and **airframe
> forces the provider to return it**, using each provider's native
> structured-output mechanism rather than a hoped-for MCP tool call. There is
> no `submit_details` tool, no mailbox file, no nudge retry.
>
> The sub-items resolve as follows:
>
> - **§4.6.1 JSON-in-text fallback** — implemented for the decomposer before
>   the migration, then made redundant by it.
> - **§4.6.2 `response_format: json_schema`** — effectively *delivered*, since
>   this is precisely what airframe now negotiates per provider. The item was
>   asking maverick to do what its runtime layer now does for it.
> - **§4.6.3 Per-tier capability documentation** — the only part still worth
>   anything, and it belongs to §2.12: models still vary in whether they can
>   satisfy a complex schema, they just fail differently now
>   (`error_max_structured_output_retries` instead of a silent empty turn).
>   Issue **#166** is a live instance.
>
> The hit-rate table below is worth keeping as a record of how wide the
> spread was.

*Original entry — Active, three sub-items, ordered by ROI.*

Maverick's mailbox-actor protocol required every agentic actor (briefing,
decomposer, implementer, reviewer, generator) to deliver structured
output via an MCP tool call (``submit_details``, ``submit_review``, etc.).
Schema-validated payloads from Pydantic are a real win, but tool-call
reliability is model-dependent:

| Tier model | Observed tool-call hit rate |
|---|---|
| claude/opus, claude/sonnet | ~100% |
| copilot/gpt-5.4, gpt-5.3-codex, gpt-5-mini | ~100% |
| claude/haiku | ~70% (one-in-three turns misses) |
| gemini/gemini-3.1-pro-preview | ~0% on detail prompts |
| openrouter/*:free | varies; documented unreliable in project memory |

This forces users to choose between two bad options: pay frontier
prices on every tier, or accept escalation churn. The
2026-04-27 / 2026-04-28 sessions hit this repeatedly — escalation
recovers most cases but burns ~4 LLM turns per failure (prompt + nudge,
then prompt + nudge at the higher tier).

The architectural alternative — replace the supervisor with an LLM
agent and switch to agent-to-agent natural language — multiplies the
failure modes (LLM in supervisor inherits all the same problems) and
loses Pydantic validation. We should not go there.

The structural fix is narrower: make MCP tool calling optional, not
required, while keeping schema validation.

#### 4.6.1 JSON-In-Text Fallback For Tool-Call Misses

**Status:** Implemented for the decomposer (outline / detail / fix paths).

When the agent's turn ends without firing the expected MCP tool, scan
its text response for a fenced JSON code block matching the expected
schema. If found, treat it as if the tool was called. This is a
documented Anthropic pattern ("implicit tool use"); many models that
miss tool calls produce the JSON inline.

As shipped:

- Module-level helpers in
  `src/maverick/actors/xoscar/_agentic.py`:
  ``_extract_json_candidates`` finds fenced code blocks (``\`\`\`json``,
  ``\`\`\``) plus the whole text as a final fallback;
  ``try_parse_tool_payload_from_text`` runs each candidate through
  ``parse_supervisor_tool_payload`` and returns the first match.
- :meth:`AgenticActorMixin._run_with_self_nudge` accepts an optional
  ``json_fallback`` callable. After both prompt and nudge fail to
  deliver the tool, the mixin invokes the fallback with the most
  recent response (then the first response as a secondary attempt).
  On success, the actor marks the tool as delivered and returns
  cleanly — equivalent to the tool firing.
- :class:`DecomposerActor` wires the fallback for ``submit_details``
  in ``send_detail`` (post-prompt path; the detail phase opts out of
  self-nudge since the supervisor's per-unit retry handles missing
  tools), and for ``submit_outline`` / ``submit_fix`` via
  ``_run_with_self_nudge``'s new parameter.
- 15 unit tests in
  `tests/unit/actors/xoscar_runtime/test_json_fallback.py`:
  fenced-block extraction, plain-text extraction, multi-candidate
  ordering, schema mismatches, malformed JSON, non-dict JSON, end-to-
  end parse for ``submit_details`` / ``submit_outline`` /
  ``submit_fix``.

Coverage observed against the failure cases that motivated this:

- claude/haiku ~30% miss rate → expected near-zero abandon rate
  (haiku's misses include the JSON inline).
- copilot/gpt-5.4 top-tier ~5% miss rate → recovered without needing
  escalation budget.

Still open: extending the same fallback to briefing actors,
implementer/reviewer, and generator. Same mechanism — pass a
``json_fallback`` callable to ``_run_with_self_nudge``. Worth doing
once we have evidence the fallback is reliable in practice on the
decomposer paths.

#### 4.6.2 ``response_format: json_schema`` For Providers That Support It

Where the provider supports strict JSON-schema generation (OpenAI/copilot
since 2024-08, Anthropic 2025+, increasingly Gemini), generation is
schema-constrained — the model literally cannot emit malformed output.
This bypasses tool-calling entirely while preserving structure.

Implementation sketch:

- Add ``StepConfig.use_response_format: bool | None`` (None = auto-detect
  from provider capability).
- When True, the agentic actor's prompt builder emits the schema as a
  ``response_format`` field on the create-session call instead of
  registering an MCP tool.
- The supervisor's tool handler is replaced by a "parse final agent
  message" handler that runs the same Pydantic validation.

Tradeoff: provider coverage. Where ``response_format`` isn't supported
(or isn't supported for a given model), fall back to the MCP path or
the JSON-in-text fallback.

Cost: bigger than 4.6.1 — touches the executor's session creation,
prompt builders, and per-actor handler logic. Maybe 1 day of work
plus careful provider-by-provider testing.

#### 4.6.3 Per-Tier Capability Documentation

Add a ``required_capabilities`` field to tier configs:

```yaml
actors:
  fly:
    implementer:
      tiers:
        moderate:
          provider: copilot
          model_id: gpt-5-mini
          required_capabilities: [tool_calls]    # or [structured_output]
```

When a user configures a tier whose provider/model doesn't support the
required capability, the preflight rejects fast with a clear message:
"moderate tier configured with claude/haiku but the implement step
requires reliable tool calls; haiku has documented misses around
30%. Consider claude/sonnet or copilot/gpt-5.4."

Implementation sketch:

- Maintain a ``KNOWN_TOOL_CALL_RELIABILITY`` table in
  ``maverick.executor.provider_registry`` keyed by ``(provider, model_prefix)``,
  values like ``"reliable"`` / ``"weak"`` / ``"unreliable"``.
- ``verify_bd_ready`` (or a sibling ``verify_tier_capabilities``)
  walks the user's tier config, looks up each tier's reliability, and
  warns/errors on weak/unreliable matches.
- Document expected capabilities per actor type in code comments.

This is the smallest of the three but probably the highest immediate
ROI — it stops the "configured haiku, got 30% misses, didn't know why"
class of bug at preflight, before any expensive work runs. Cost: ~50
lines + the reliability table that we maintain by hand based on
observed runs.

#### Sequencing

Land 4.6.1 first (cheapest, highest fix-rate impact). Then 4.6.3 (cheap,
prevents misconfiguration). 4.6.2 is the biggest piece and should wait
until we have evidence that the first two aren't enough — likely we'll
find that 4.6.1 + 4.6.3 + the existing escalation already cover ~95%
of the pain.

### 4.7 Per-Project OpenCode Agent/Skill Overrides

**Status:** Reframed *(2026-08-22)*

> The OpenCode-native simplification described below was not the direction
> taken. `src/maverick/runtime/opencode/` does not exist; OpenCode is one
> airframe provider among several (Claude Code, Copilot, OpenRouter, Bedrock,
> Kimi), selected per role in `maverick.yaml`. Persona prompts live in
> [src/maverick/agents/system_prompts/](src/maverick/agents/system_prompts/)
> as markdown that ships with the package — so the *bundled defaults* half of
> this item happened, just not via `OPENCODE_CONFIG_DIR`.
>
> **The follow-on is still open and now provider-neutral:** there is no way for
> a project to override or extend a persona prompt without editing the
> installed package. The right shape is a per-project override layer keyed by
> role, resolved once in `agent_factory`, rather than anything OpenCode-specific.
>
> Precedent worth copying: spec 053's `maverick-review` skill is installed into
> the project at `.claude/skills/` and deliberately **always overwritten**,
> because it is maverick-owned and versions with the wheel. A user-owned
> override layer needs the opposite policy, and the distinction should be
> explicit wherever it lands.

*Original entry (Active, deferred — defaults-only path ships first).*

The OpenCode-native simplification effort moves persona prompts out of
`src/maverick/agents/*.py` and into markdown agent/skill files loaded
by OpenCode via `OPENCODE_CONFIG_DIR`. The first cut ships these as
**bundled defaults inside the maverick package** at
`src/maverick/runtime/opencode/profile/{agents,skills,AGENTS.md}`. They
version with the package, never touch the user's repo, and `maverick
init` does not copy them anywhere.

This item is the follow-on: let users override or extend the bundled
agents/skills on a per-project basis, with overrides committed in
their repo so the team shares them.

What this would add:

- Recognized override location at `.maverick/opencode/{agents,skills,
  AGENTS.md}` in the user's repo.
- At workflow start, maverick assembles an overlay directory (bundled
  defaults + per-project overrides, with overrides winning by file
  name) and points `OPENCODE_CONFIG_DIR` at the overlay rather than
  directly at the package profile.
- Optional `maverick agents eject <name>` (or similar) to copy a
  bundled agent into `.maverick/opencode/agents/<name>.md` for
  editing — opt-in, named, intentional. Avoids the "two copies that
  drift" failure mode of seeding the directory at `init` time.
- Naming convention: bundled agents use a `maverick.` prefix
  (`maverick.navigator`, `maverick.reviewer`, …) so user-defined agents
  in their own `.opencode/` can never collide with the bundled set.

What is intentionally not part of this item:

- Auto-seeding `.maverick/opencode/` at `init` time. Defaults belong in
  the package; per-project content should appear only when the user
  asks for it.
- Cross-machine override discovery. `~/.config/opencode/` already
  exists for personal customization; we're not layering on top of that.

Sequencing: ship the bundled-defaults path first
(`OPENCODE_CONFIG_DIR=<package>/runtime/opencode/profile`, no overlay).
Add the override layer once we have at least one real ask for project-
specific persona tweaks. Until then, users who really need a tweak can
fork their maverick install or use a global `~/.config/opencode/agents/`
override.

Relevant code (forthcoming):

- `src/maverick/runtime/opencode/profile/` (bundled defaults)
- `src/maverick/runtime/opencode/server.py` (env-injection point)

### 4.8 Substrate-Swap Interface

**Status:** Largely Implemented — by adopting one, not by defining one *(2026-08-22)*

> This item asked for a deliberate `Substrate` Protocol so that swapping the
> LLM runtime would be a mechanical refactor. **airframe is that boundary**,
> and it arrived as a dependency rather than as the `runtime/substrate.py`
> file proposed below. Every LLM call goes through
> `runtime_for_agent(role, ...)` → an `airframe.AgentRuntime`; providers
> (Claude Code, Copilot, OpenCode, OpenRouter, Bedrock, Kimi) are selected per
> role in `maverick.yaml`, with the binding validated against the adapter
> before it is returned.
>
> Note that the item's own justification was vindicated almost immediately:
> it argued the seam was worth designing *before* anyone had a concrete reason
> to switch off OpenCode. The switch happened, and the modules it named
> (`runtime/opencode/*`, `actors/xoscar/opencode_mixin.py`) were all deleted —
> which is the good outcome, achieved the other way round.
>
> **What genuinely remains** is narrower than the original item and worth
> stating precisely: capability *variation between providers* still leaks into
> maverick rather than being normalized by the boundary. Spec 056 is the clean
> example — context-file protection has to ask
> `supports_permission_callback()` and silently run without Layer 1 on
> providers that decline (the OpenCode/OpenRouter family), with a
> provider-blind snapshot backstop carrying the actual guarantee. That is the
> right design, but it means "which features does this provider support"
> is answered ad hoc at each call site instead of by a capability contract.
> That, plus §2.5's named profiles, is the residue.

*Original entry (Active).* The OpenCode-substrate migration shipped in
[`7ea1028`](https://github.com/get2knowio/maverick/commit/7ea1028)
unified every LLM invocation onto a single substrate
(`agent="maverick.<role>"` resolved against bundled markdown personas
via OpenCode's HTTP runtime). A side effect of the cleanup: substrate
concerns are now concentrated in a small, well-bounded set of modules
— `runtime/opencode/{client,executor,server,tiers,errors}.py` plus
`actors/xoscar/opencode_mixin.py`. That's accidentally a good shape
for a future swap to a different substrate (pi.dev, a hypothetical
"opencode v2", a self-hosted runtime, …), but the boundary is
*incidental*, not *intentional*.

This item makes the boundary deliberate so swapping substrates is a
mechanical refactor on five modules instead of an architecture
question.

Why now:

- Designing the seam while one substrate is fresh in mind is cheaper
  than retrofitting it later when someone has a concrete reason to
  switch.
- It's option-preservation, not migration. We are explicitly **not**
  switching off OpenCode — we have no concrete pain on it. The point
  is to keep "could swap if we needed to" within mechanical-refactor
  reach instead of letting it drift toward "would require a rewrite."
- The pi.dev comparison done during the migration cleanup confirmed
  no present reason to switch, but also surfaced three trip-wires
  that, if they ever fired, would justify a swap: structured-output
  reliability regression on OpenCode, breaking server-protocol
  changes upstream, or a need for embedded-library deployment
  (single-process maverick). None are visible today; designing the
  seam now means responding to them later is a few-day project, not
  a few-week one.

What "intentional" looks like:

- **Define a `Substrate` Protocol** at `src/maverick/runtime/substrate.py`.
  Methods should be substrate-neutral and tightly scoped:
  - `send_named(*, agent: str, prompt: str, result_model: type[BaseModel] | None, ...) -> SubstrateResult`
  - `create_session() / prompt_session() / cancel_session() / close_session()` for multi-turn callers
  - `validate_model(provider: str, model_id: str) -> bool` for tier-cascade pre-flight
- **Lift substrate-neutral types** into `runtime/`: `CostRecord`,
  `SubstrateError` hierarchy (currently the `OpenCodeAuthError` /
  `OpenCodeContextOverflowError` / `OpenCodeStructuredOutputError`
  family — they describe categories, not OpenCode-specific events),
  `StructuredOutputResult`. Keep the OpenCode-specific subclasses for
  cases where the message text is helpful, but the supertype lives at
  the substrate layer.
- **`OpenCodeAgentMixin` and `OpenCodeStepExecutor` depend on the
  Protocol**, not the concrete `OpenCodeClient`. Today the mixin
  imports `OpenCodeClient` directly and constructs one per actor;
  after this refactor it imports `Substrate` and is handed an
  instance.
- **One concrete `OpenCodeSubstrate` impl** stays in
  `runtime/opencode/`. The three landmines mitigations
  (envelope-unwrap, async-dispatch crash recovery, silent-error
  detection) live inside that impl as substrate-specific concerns.
- **Tier cascade plugs in at the Protocol layer.** Currently
  `cascade_send` lives inside `runtime/opencode/tiers.py` and is
  coupled to the OpenCode client. The cascade logic is substrate-
  agnostic ("on recoverable failure, drop the binding and retry on
  the next one") and belongs above the Substrate seam.
- **Test-only `StubSubstrate`** in
  `tests/fixtures/substrate.py` proves the seam works: takes a dict
  of `{agent_name: canned_response}` mappings, returns them. Used by
  unit tests that today have to mock `OpenCodeClient`. Validates the
  Protocol surface is small enough to actually stub without writing
  half a runtime.

Non-goals:

- Adding a second concrete substrate. We're not shipping pi support
  or anything else; we're just keeping that door visible.
- Feature parity. Tier cascade, three-landmine mitigation, and
  structured-output forcing stay specific to OpenCode where they
  belong. The Protocol exposes outcomes, not implementation.
- Persona portability. `.md` agent files are an OpenCode convention.
  If we ever swap, the migration includes re-shipping personas in
  the new substrate's format. The Substrate Protocol doesn't promise
  to abstract that away.

Sequencing:

1. Land the Substrate Protocol + neutral type extractions. No behavior
   change. Existing OpenCode code starts implementing the Protocol.
2. Refactor `OpenCodeAgentMixin` to depend on the Protocol; pool
   wiring continues to construct a concrete `OpenCodeSubstrate`.
3. Refactor `OpenCodeStepExecutor` likewise.
4. Move `cascade_send` above the substrate boundary.
5. Land `StubSubstrate` and migrate the most-mocked test sites onto
   it as a forcing function — if the stub can't replace the mock,
   the Protocol surface is wrong.

Acceptance: a hypothetical second substrate impl could be added by
writing one new module under `runtime/<name>/` plus a registration
hook, with no edits to xoscar actors, the executor, the supervisor
fan-out, or the workflow layer.

Relevant code (current):

- `src/maverick/runtime/opencode/client.py` (3-landmines mitigation)
- `src/maverick/runtime/opencode/executor.py` (named-agent path + multi-turn API)
- `src/maverick/runtime/opencode/server.py` (lifecycle + `OPENCODE_CONFIG_DIR` injection)
- `src/maverick/runtime/opencode/tiers.py` (cascade — moves above the seam)
- `src/maverick/runtime/opencode/errors.py` (error classification — splits into neutral + OpenCode-specific)
- `src/maverick/actors/xoscar/opencode_mixin.py` (the `agent=` plumbing — refactors to depend on Protocol)

## 5. Reusable Workflow Building Blocks

### 5.1 Reusable Supervisor Fragments

**Status:** Superseded *(2026-08-22)*

All three supervisors named below were deleted in the Burr migration, and the
YAML DSL that would have hosted "fragments" was removed outright in spec 041
(`library/fragments/` no longer exists). Composition is now expressed in
Python: `@action` functions declaring their `reads`/`writes`, wired by
`build_*_application()`.

The four repeated shapes it identified are worth re-reading as a description
of what the graphs still do — and two of them *have* since been extracted,
independently:

- **specialist fan-out followed by synthesis** — still duplicated between the
  briefing room and refuel's decomposer pool.
- **typed tool-intake and routing** — gone; structured output replaced it.
- **validation or gate stages with fallback behavior** — partially shared via
  `run_independent_gate` and `library/actions/validation.py`.
- **result aggregation and artifact writing** — converging: see §3.7's note on
  `entry_to_dict` and `BlockRecord.to_dict()` as shared projections.

The instinct — "extract the two or three orchestration fragments that already
repeat", not "add another framework" — is still the right instinct, and is
better served now that the repetition is plain Python rather than YAML.

*Original entry, for the record.* The major supervisors were intentionally
different, but repeated a recognizable set of shapes; the relevant files were
`workflows/generate_flight_plan/supervisor.py`,
`actors/refuel_supervisor.py`, and `workflows/fly_beads/supervisor.py`.

## 6. Completed Or Mostly Addressed Items

These should not be treated as primary future work anymore.

### 6.1 Runway Seed Agent Fix

**Status:** Implemented

The current seed path is exercised by [tests/unit/runway/test_seed.py](tests/unit/runway/test_seed.py) and backed by [src/maverick/runway/seed.py](src/maverick/runway/seed.py). Keep regression coverage, but retire the old "seed is broken" framing.

### 6.2 Provider Quota Detection And Recovery

**Status:** Partial — Tiers 1 / 1.5 / 1.6 implemented; Tier 2 + Tier 3 still open. *(re-checked 2026-08-22)*

**Reconciliation note.** The detection layer survived the Burr migration —
[src/maverick/exceptions/quota.py](src/maverick/exceptions/quota.py) is intact
and `is_quota_error` is still the entry point — but every *consumer* named
below (`PlanSupervisor`, `RefuelSupervisor`, `_run_detail_fan_out`, the agent
actors) was replaced by the Burr action layer. Read the tier descriptions for
behaviour, not for call sites; the quota handling now lives in
`workflows/refuel_maverick/actions.py`'s escalation helpers.

Two things changed the outlook for the open tiers:

- **Tier 3 (automatic failover) is arguably no longer maverick's job.**
  airframe owns provider selection, and a failover policy that switches
  provider mid-run belongs at that boundary rather than in a workflow action.
- **Tier 2 (wait-and-resume) is unaffected** and remains the more useful half:
  a quota reset is a schedulable event, and spec 054 introduced the codebase's
  first real clock seam (`assumptions/schedule/clock.py`) plus a daemonless
  scheduler pattern that a wait-and-resume implementation could reuse rather
  than reinvent.

#### Tier 1 — Detection (implemented)

- :func:`maverick.exceptions.quota.is_quota_error` regex-detects quota
  exhaustion in upstream error strings.
- Every agent actor (decomposer, implementer, reviewer, briefing,
  generator) sets ``quota_exhausted=True`` on the
  :class:`PromptError` it sends the supervisor.
- :class:`PlanSupervisor` and :class:`RefuelSupervisor` surface the
  flag for outline / fix / briefing phases (top-level abort with the
  flag in the result).

#### Tier 1.5 — Detail-Phase Surfacing And Retry Short-Circuit (implemented)

The detail phase used to silently swallow ``quota_exhausted`` to a
``logger.debug`` and burn the full retry budget against the exhausted
provider. As shipped:

- :class:`RefuelSupervisor` records ``unit_id → error_str`` on the
  ``_detail_quota_errors`` map when ``prompt_error`` reports a
  quota signal during detail phase.
- ``_run_detail_fan_out._one`` consults that map after each
  ``send_detail`` returns. If quota was reported, it abandons the unit
  immediately (skipping the remaining retries — they would all fail
  the same way) and emits ``AgentCompleted`` with
  ``error="quota: <truncated message>"``.
- The abandon-step error message breaks out the quota-driven count
  separately (``"X/Y unit(s) abandoned — N due to provider quota
  exhaustion (resets 6am UTC). Successful units are cached on disk
  ..."``), guiding the user to either wait or switch tier.
- The CLI agent-table renderer shows the ``error`` suffix on failed
  rows (``∟ unit-id (provider/model) (quota) ✗``).

#### Tier 1.6 — Decomposer Detail-Phase Escalation (implemented)

The implementer already escalates beads to a higher tier on fix-loop
overflow (§2.10 Phase 2). The decomposer detail phase now does the same
on any unit abandon — timeout, no-tool-call, or quota.

As shipped:

- New ``DecomposerTiersConfig.escalation_threshold`` (default ``1``,
  range 0–5). ``1`` allows one escalation: a unit that fails on its
  natural tier gets one re-attempt at the next-defined-higher tier.
  ``0`` disables escalation entirely.
- :meth:`RefuelSupervisor._run_detail_fan_out` now wraps the existing
  same-tier retry loop in an outer escalation loop. After the inner
  loop returns ``"timeout" | "no_tool_call" | "quota"``, the outer
  loop checks if a higher tier exists (via
  :meth:`FlySupervisor._resolve_tier_in` with ``escalation_level + 1``)
  and re-dispatches once at that tier. The inner ``_try_one_tier``
  helper emits its own AgentStarted/AgentCompleted pair per attempt.
- Per-unit display name carries a ``↑`` suffix per escalation step
  (``unit-id`` → ``unit-id ↑`` → ``unit-id ↑↑``) so the CLI shows each
  tier attempt as a separate row. Reading the table top-to-bottom, the
  user can see exactly which tier won.
- Quota signals from the previous tier are cleared before the
  escalation attempt (different tier may be a different provider with
  no quota issue). If both tiers share a provider, the same-tier quota
  short-circuit fires again on the new attempt and the unit abandons
  in seconds — no wasted retry budget.
- ``_unit_escalated_count`` tracks how many escalations happened in
  the run for telemetry.

Why default ``1`` instead of the implementer's ``2``: detail generation
is mostly mechanical, and a single escalation step from moderate→complex
captures essentially all "this tier is too weak for this unit" cases.
A second escalation step rarely adds value because the highest-defined
tier is the strongest option available.

#### Tier 2 — Wait-And-Resume (open)

When a tier hits quota mid-run, pause new dispatch for that tier and
resume automatically when capacity returns. The hard parts:

- **What's the wait signal?** ``parse_quota_reset`` already pulls
  reset-time hints from common error strings (``"resets 6am UTC"``).
  When parseable, sleep until then plus a small jitter; otherwise
  fall back to exponential backoff with a sane cap (e.g. 5 / 15 /
  60 minutes).
- **Per-tier pause, not global.** The demand pool's tier
  identity already gives us this: a quota event on the ``moderate``
  tier should not block ``simple`` or ``complex`` workers from
  picking up their own units.
- **Live-table feedback.** Currently a paused tier looks identical
  to a stuck one. Need a "paused — resumes in 17 min" status row so
  the user knows the run is alive.
- **How do we know capacity returned?** Either the user-supplied
  reset time or a probe: dispatch a single tiny prompt periodically
  and resume the full pool when it succeeds.

Sketch:

```python
class _DecomposerPool:
    # New state:
    _tier_paused_until: dict[str, float]  # tier → monotonic deadline

    async def acquire(self, tier):
        # ... existing reuse / spawn / evict logic ...
        # Before spawning OR busy-wait, honor a paused tier.
        deadline = self._tier_paused_until.get(tier)
        if deadline and time.monotonic() < deadline:
            await sleep_until(deadline)
            self._tier_paused_until.pop(tier, None)
        # ... continue ...
```

Plus supervisor-side: when ``prompt_error`` records a quota event,
call ``pool.pause_tier(tier_name, until=parse_quota_reset(err) or
default_backoff)``. The pool refuses new work for that tier until the
deadline.

This is not landed because the design needs care around three things:

1. **Don't leak unit-tier mapping back into prompt_error.** Today the
   supervisor doesn't know which tier a quota-erroring unit was
   running against — that lives in the dispatch-side closure in
   ``_one``. We'd thread tier_name into ``PromptError`` or maintain a
   ``unit_id → tier_name`` map populated at acquire-time.
2. **Don't pause a tier indefinitely.** If the reset string is
   unparseable AND the probe never succeeds (network down? wrong
   error?), we need a bound on how long we'll wait before giving up
   and abandoning.
3. **Caching aligns with this.** Per-unit detail caching (already
   implemented) means a paused-then-resumed run only re-processes
   the units that hadn't completed before the pause, so the wait
   isn't an obvious throughput hit.

#### Tier 3 — Automatic Failover (open)

When a tier hits quota and the user has configured a fallback model
for that tier, switch to the fallback for the duration of the
quota-reset window. Requires a per-tier ``fallback`` field on
``ImplementerTierConfig`` / ``DecomposerTierConfig``. Failover is
strictly opt-in; without an explicit fallback, Tier 2 wait-and-resume
is the only remediation.

This is the right shape only after Tier 2 ships — Tier 2 establishes
the per-tier pause primitive, and Tier 3 is just "instead of pause,
re-route." Don't build them in the other order.

Relevant code:

- [src/maverick/exceptions/quota.py](src/maverick/exceptions/quota.py)
- `src/maverick/actors/xoscar/plan_supervisor.py`
- `src/maverick/actors/xoscar/refuel_supervisor.py`
- `src/maverick/actors/xoscar/decomposer.py` (and peers)

### 6.3 Review Retry Caps

**Status:** Implemented, with follow-on tuning still possible

The old future item was too broad. The important distinction now is:

- the fly-beads supervisor has a hard review cap in `src/maverick/workflows/fly_beads/supervisor.py`;
- the library review-fix loop is bounded by `max_attempts` in `src/maverick/library/actions/review.py`.

The remaining work is observability and budget tuning, not adding a cap from scratch.

## 7. Recommended Next Moves

If Maverick only takes a few of these forward in the near term, the highest-leverage sequence looks like this:

1. **Shared mailbox actor scaffold** plus **tool calls through the owning actor**.
2. **Structured telemetry** plus a **unified trace and correlation envelope**.
3. **Step-level evals** for provider and prompt selection.
4. **Asynchronous human review queue** beyond the current review-bead model.
5. **Per-epic hidden workspace strategy** once the hidden workspace model is fully settled.

That sequence improves correctness, operability, and iteration speed before taking on the larger product-facing workflow expansions.