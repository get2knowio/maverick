# Specify Prompts: Orchestration Roadmap

A working sequence of `specify` prompts derived from
`docs/competitive-analysis-orchestration-platforms.md` §6. Each prompt below is
self-contained and ready to feed into the spec chain:

```bash
# Save the prompt block to a file, then:
maverick spec <feature-name> --from-prd <file>
maverick refuel <feature-name> --speckit
maverick fly --epic <epic-id>
```

(or paste directly into `/speckit-specify` if driving Spec Kit by hand).

Prompts are written per Spec Kit convention — intent, behavior, and constraints,
with implementation left to the plan phase. Where a prompt references existing
Maverick modules, that is context for the planner, not a design mandate.

## Sequencing

```
Tier 0  (housekeeping, no spec):  close spec 042 as superseded

Tier 1  (independent — start in any order):
  1. assumption-batch-scheduler        ← highest value per effort
  2. learned-assumption-resolution     (best after 1)
  3. context-file-protection           (small)
  4. isolated-bead-workspaces          ← unblocks the dispatcher
  5. standalone-code-review            (small)
  6. spec-delta-layer

Tier 2  (the fleet backbone, in order):
  7. maverick-host-daemon
  8. task-container                    (after 7)
  9. concurrent-fly-dispatcher         (after 4 and 7)
 10. credential-pool-leasing           (after 9; record-keeping ties to 8)

Tier 3  (quality + surfaces):
 11. verification-taxonomy             (after 8)
 12. fleet-monitor                     (after 7; full value after 9)
```

Spec numbers (`NNN-`) are assigned by Spec Kit at specify time; the names below
are suggestions. **Tier 0 is not a spec** — spec 042 (ACP integration) should
simply be marked superseded in a small commit: ACP wound down into A2A, and
airframe already occupies the layer 042 proposed.

---

## Tier 1 — independent

### Prompt 1: `assumption-batch-scheduler` (Slice D core)

```
Add schedule-respecting, severity-tiered delivery of assumption-ledger entries
to the human, so that questions raised by agents reach the human in batches
that match the human's schedule instead of requiring them to poll `maverick
brief`.

Today, assumption severity drives enforcement (ready-queue deferral, blocks
edges, the land gate) but not timing: nothing tells the human that entries
exist until they run a command. This feature adds a delivery policy layered on
severity:

- high: interrupt — deliver a notification immediately when the entry is
  recorded.
- medium: batch — accumulate and deliver at the next configured review window.
- low: accumulate silently — surfaced only during a review sweep or bulk
  waive, never delivered proactively.

Configuration lives in maverick.yaml under an assumptions schedule block:
review windows as local times of day (e.g. 09:00 and 17:00), quiet hours
during which nothing is delivered (with an explicit policy choice for whether
high-severity interrupts override quiet hours — default: they do), a minimum
batch size below which a window is skipped (entries roll to the next window),
and a maximum entry age after which an undelivered or unanswered entry
escalates regardless of batching rules.

Delivery is via ntfy (already an optional dependency, currently unused for
this). A batch notification carries: count by severity, the owning specs, the
oldest entry's age, and the exact `maverick review` invocation to start the
sweep. It does not carry entry contents — the notification is a summons, not
the console.

Timeouts and escalation: an unanswered high-severity entry past its maximum
age re-notifies on a backoff schedule. An optional, explicitly configured
policy may auto-waive aged low-severity entries with a recorded rationale on
the ledger entry. Nothing ever expires silently.

The scheduler must work without any resident daemon: it runs as an idempotent
command (suitable for cron or a systemd timer) that evaluates the ledger
against the schedule and delivers anything due. Re-running within the same
window must not re-deliver the same batch. Delivery state (what was delivered,
when) is persisted so that evaluation is deterministic and auditable. A future
host daemon may later call the same evaluation in-process; nothing in this
feature may assume residency.

Out of scope: Slack/email channels, learned auto-resolution from prior
answers, any change to enforcement semantics (the land gate and ready-queue
behavior are untouched).

Success looks like: a human with quiet hours 22:00–07:00 and windows at 09:00
and 17:00 receives exactly one push at 09:00 summarizing everything that
accumulated overnight, is interrupted only for high-severity entries, and can
prove from persisted state why each notification fired.
```

### Prompt 2: `learned-assumption-resolution` (Slice D, items 5–6)

```
Feed resolved assumption-ledger entries into runway as reusable knowledge, so
that when an agent adopts an assumption closely matching one the human has
already answered, the prior answer is proposed as the default during review —
and eventually the fleet stops asking questions the human has already
answered.

Two capabilities:

1. Decisions as labels. Every terminal ledger outcome — answered (with the
   answer text), waived (with the reason), and edited-then-answered — is
   persisted as a structured decision record in runway, carrying the question,
   the adopted answer, the human's resolution, severity, and the owning spec.
   Records survive across specs and runs.

2. Suggested answers at review time. When a new assumption is recorded, it is
   matched against prior decision records. When a sufficiently close prior
   decision exists, the entry carries a suggested resolution with provenance
   (which prior entry, which spec, when). The suggestion surfaces in
   `maverick review --list --json` as a field on the entry row, and the
   maverick-review skill presents it as the default option in its
   AskUserQuestion sweep. The land gate is unchanged: a suggestion never
   auto-answers an entry.

An explicit opt-in policy may allow auto-resolution for low-severity entries
whose match confidence exceeds a configured threshold; auto-resolved entries
are marked as such on the ledger with the source decision's provenance, and
they appear in the land report distinctly from human-answered entries (a land
that relied on any auto-resolution is at most conditionally-verified).

Matching quality matters more than coverage: a wrong suggestion presented as a
default is worse than no suggestion. The feature must define what "closely
matching" means, how confidence is scored, and how false suggestions are
suppressed after the human rejects them (a rejected suggestion for a given
question shape must lower that pairing's future confidence).

Out of scope: cross-repository knowledge sharing; any change to how
assumptions are captured.
```

### Prompt 3: `context-file-protection` (Slice G)

```
Add a safety hook that prevents agents from modifying agent-context files —
AGENTS.md, CLAUDE.md, and the Spec Kit constitution — anywhere in the
repository, unless the human has explicitly allowed it.

Field data shows LLM-generated context files measurably reduce task success
and raise cost, while human-curated ones compound in value. Maverick's own
constitution and CLAUDE.md are load-bearing; an implementer agent "helpfully"
rewriting them mid-bead is silent corruption of the fleet's operating
instructions.

Behavior: any agent-initiated write (create, edit, delete, rename) targeting a
protected path is blocked before it happens, the block is recorded as a
structured event on the run, and the bead continues — a blocked context-file
write is not a bead failure. The protected set defaults to AGENTS.md,
CLAUDE.md, and .specify/memory/** at any depth, and is extensible via
maverick.yaml (additional globs, or an explicit allowlist for repositories
where agents are supposed to maintain such files). The hook applies to every
agent role on every workflow, including inside isolated workspaces.

The hook must fail closed for the protected set but must not degrade anything
else: if the hook infrastructure itself errors, agent writes to unprotected
paths proceed normally.

Out of scope: protecting arbitrary user-designated files beyond the config
mechanism; reviewing or reverting historical agent edits to context files.
```

### Prompt 4: `isolated-bead-workspaces` (Slice C step 1 — the Guardrail 0 amendment)

```
Generalize the spec-chain's hidden-workspace mechanism into a reusable
isolated-execution primitive, and amend Guardrail 0 from "no workspaces" to
"no bd inside a workspace" — its actual load-bearing constraint.

History: Guardrail 0 retired hidden workspaces because bd's gitignored
embeddeddolt/ store does not travel with `jj workspace add`, so bd cannot
function inside one. That is a bd constraint, not a workspace constraint.
Spec 050 (headless spec chain) then proved the workspace mechanism works when
bd stays out: the agent mutates files in the workspace, while all bd, ledger,
and jj-history writes happen in the orchestrating process against the user's
checkout, and completed artifacts land atomically per step.

This feature extracts that proven contract into a reusable primitive that any
workflow can use to run an agent step in isolation:

- The primitive provisions a workspace for a unit of work, executes the
  agent's file mutations there, and folds the resulting delta back into the
  user's checkout via jj on success — or discards it cleanly on failure, with
  nothing half-written ever visible in the checkout.
- The invariant is enforced structurally, not by convention: bd is never
  invoked inside a workspace, and all bead, ledger, and commit-graph writes
  occur in the orchestrating process. It should be difficult to violate this
  accidentally.
- Workspace lifecycle matches what spec-chain already does: created per unit
  of work, torn down on completion, and abandoned workspaces are swept.

As the first consumer and the proof of the fold-back mechanics, `maverick fly`
gains an opt-in isolated mode: each bead executes in its own workspace,
still strictly serially, with the fold-back producing the same bead commit
(same subject prefix, same Bead trailer) the in-checkout path produces. A
fold-back conflict fails the bead with a clear diagnostic; conflict
*resolution* machinery is out of scope here and arrives with the concurrent
dispatcher.

The constitution amendment ships in the same feature: Guardrail 0's text is
updated to state the single-repo model, the bd-stays-out invariant, and that
isolated agent-side execution is permitted under this contract — replacing the
current phrasing where spec-chain is a one-off exception.

Success looks like: a fly run in isolated mode produces byte-identical history
to a normal run for the same beads, the user's checkout never contains
mid-bead intermediate state, and the constitution accurately describes the
system.
```

### Prompt 5: `standalone-code-review` (Slice G)

```
Add a standalone agentic code-review command that reviews a diff, an epic's
accumulated changes, or a set of paths on demand — outside the fly loop.

Today the reviewer agent only runs inside `maverick fly` as part of the
per-bead gate. Its judgment is useful on demand: before pushing a manual
change, after landing an epic, or on a colleague's branch.

Scope selection: review the working-copy diff against a base revision, review
everything an epic's beads committed (located via bead commit trailers), or
review explicit paths. The command reuses the existing reviewer agent and tier
routing; it must not fork a second review implementation.

Output: findings rendered to the terminal grouped by file with severity, and a
persisted findings artifact under the run directory. A --json mode emits the
findings through the shared JSON verb envelope so the command is scriptable
and skill-callable. The command is read-only with respect to the repository:
no commits, no bead writes, no fix loop — findings are for the human.

Naming needs care: `maverick review` is taken by the assumption-review
console. The spec should choose a name that will not collide or confuse
(candidates: `maverick inspect`, `maverick critique`, `maverick review-code`).

Out of scope: automated fixing of findings; CI integration; review of
revisions not reachable from the current repository.
```

### Prompt 6: `spec-delta-layer` (Slice G — OpenSpec-style modification)

```
Add a delta layer for modifying existing specs, closing Spec Kit's known
brownfield weakness: today, changing a shipped spec means editing spec.md in
place, and `refuel --speckit`'s delta detection only handles tasks.md growth —
there is no structured way to express "this requirement changed" and have it
flow deterministically into new work.

Model the field's answer (OpenSpec): a change proposal is a structured
artifact describing deltas against an existing spec — requirements added,
modified, or removed — with a lifecycle of propose, apply, and archive.

- Propose: a delta document lives alongside the spec it modifies, expressing
  each change as ADDED, MODIFIED (with before/after), or REMOVED, in a format
  that is deterministically parseable (Guardrail 8: zero model calls to
  ingest).
- Apply: applying a delta rewrites spec.md and tasks.md to their new state,
  and refuel ingests the consequences deterministically — new tasks become new
  beads under the existing epic; removed requirements close their open,
  unstarted beads; modified requirements with in-flight or completed beads
  raise a flag for the human rather than silently mutating work.
- Archive: an applied delta is preserved as provenance — the spec's history of
  intentional change, distinct from git history.

The spec must resolve whether this layer is purely additive on top of Spec Kit
artifacts (preferred: our chain and ingestion continue to work on vanilla
Spec Kit repos) or requires deviating from upstream Spec Kit conventions — and
if the latter, what the compatibility story is.

Out of scope: AI-authored delta proposals (a human or an upstream tool writes
the delta; a later feature may generate them); retroactive reconstruction of
deltas for past spec edits.
```

---

## Tier 2 — the fleet backbone

### Prompt 7: `maverick-host-daemon` (Slice A)

```
Add a per-repository host daemon that outlives any single CLI invocation, so
that long-running work survives terminal disconnects and, later, a fleet of
concurrent agents has a resident supervisor.

Today every command is a foreground process: closing the terminal kills the
run, agents are opened and torn down per invocation, and there is no single
place that knows what is currently running. The daemon inverts this:

- One daemon per repository, started on demand by the first command that
  wants it, exposing a local RPC surface over a unix socket in the repo's
  .maverick directory, with per-user discovery metadata so clients and tooling
  can enumerate live hosts.
- The daemon owns: squadron lifetime (agents opened once and reused across
  invocations rather than per-command), run and task state, the ProgressEvent
  stream (fanned out to any number of subscribed clients), and provider health.
- Existing commands become thin clients: `maverick fly` submits work to the
  daemon and streams events; detaching (Ctrl-C in the client, closing the
  terminal, SSH drop) leaves the run flying; a new invocation reattaches to
  the live event stream. The two-stage Ctrl-C contract is preserved with an
  explicit mapping: detach is the default client action, graceful stop and
  hard cancel are explicit signals to the daemon.
- Every command must retain a one-shot fallback that works with no daemon
  present — daemonless operation remains fully supported, and CI or scripting
  contexts never need a resident process.

Lifecycle: clean shutdown on idle after a configurable period, crash recovery
on next start (a daemon that died mid-run must leave enough persisted state
for the run to resume or be cleanly reported as interrupted), and stale
socket/discovery cleanup. Exactly one daemon per repository is enforced.

The spec must resolve one open architectural question: does the daemon own the
Burr application in-process, or supervise subprocesses that own their own?
This decides crash isolation (one bad action taking down the fleet supervisor)
and matters more once beads run concurrently.

Out of scope: concurrent bead execution (the dispatcher builds on this);
remote/network access to the daemon (local socket only); any GUI.
```

### Prompt 8: `task-container` (Slice B)

```
Promote the per-run directory into a durable task container that spans a
feature's whole lifecycle — spec, refuel, fly, land — so that everything
Maverick did for a feature is one resumable, auditable unit.

Today .maverick/runs/<run-id>/ is per-invocation: a feature that goes through
spec, refuel, three fly sessions, and a land leaves its history scattered
across unrelated run directories, and nothing ties them together or to the
spec and epic they served.

A task is created when work begins on a feature and accumulates until the
feature lands:

- Identity and status: which spec directory, which epic bead, which workspace
  folder(s) if isolated execution was used, where the work ran, and a status
  machine covering the lifecycle (specifying, refueled, flying, awaiting-
  review, landing, landed, abandoned).
- Execution records: one per agent handoff, carrying the plan/prompt context,
  the verification outcome, resulting commits, cost, and — critically — the
  resolved (provider, model, credential) binding that served it. That binding
  is what makes cross-subscription attribution and per-feature cost analysis
  possible once a credential pool exists.
- The full ProgressEvent stream for the task, append-only.
- Checkpoints: the spec-chain's checkpoint/resume mechanism generalized, so
  any interrupted phase can resume from its last completed step.

Existing commands adopt the container without breaking: run directories that
exist today keep working, new work is recorded under tasks, and the land
report and brief can aggregate by task. The host daemon, where present, is the
writer of task state; daemonless invocations write it directly.

Success looks like: after a feature lands, a single task directory answers —
what was specified, what was assumed, who implemented each bead on which
model and subscription, what it cost, what the reviewer said, and what
landed.

Out of scope: multi-repository tasks; any UI beyond existing commands reading
task state.
```

### Prompt 9: `concurrent-fly-dispatcher` (Slice C — the thesis's missing leg)

```
Replace fly's serial drain loop with a bounded concurrent dispatcher: N beads
in flight at once, each in its own isolated workspace, with all coordination
serialized through the orchestrator.

Prerequisites: isolated bead workspaces (the fold-back contract, already
proven serially) and the host daemon (the resident supervisor).

- Worker pool: default WIP limit of 3 concurrent beads, configurable with a
  hard cap. The field's evidence is that 3–5 is the ceiling for meaningful
  oversight; the default should reflect that, not maximize throughput.
- Scheduling: the ready set continues to come from bd's dependency graph
  exactly as today. The dispatcher claims a ready bead, leases it to a worker,
  and never hands two workers overlapping file scopes when the beads declare
  them (task-level [P] markers and file scope from Spec Kit ingestion are the
  signal); beads with unknown scope are conservatively serialized.
- Isolation: each bead executes in its own workspace via the isolated-
  execution primitive. All bd writes, ledger writes, and jj history mutations
  are serialized through the orchestrating process — bd is never assumed to
  tolerate concurrent writers.
- Merge discipline: a completed bead folds back into the checkout via jj. A
  fold-back conflict routes into the existing round-budgeted conflict-
  resolution machinery from reconcile (positioned child, agent resolution,
  squash back, bounded rounds, escalate to a human bead on exhaustion) rather
  than failing the bead outright.
- Mid-flight reconcile must be re-contracted: its current guard assumes one
  flying run parked at a safe empty-working-copy boundary between beads. Under
  a pool there is no single boundary. The spec must define when reconcile may
  run during a concurrent fly (e.g. a quiesce point where the dispatcher
  drains in-flight beads before reconciling) or explicitly defer mid-flight
  reconcile in concurrent mode to a follow-up, with the manual command still
  available.
- Failure isolation: one bead's failure (agent error, fold-back escalation,
  budget exhaustion) never takes down the pool. The two-stage stop contract
  generalizes: graceful stop finishes in-flight beads and claims no new ones;
  hard cancel aborts workers and discards their workspaces cleanly.
- Fix loops, tier routing, and escalation ladders apply per bead unchanged.

Success looks like: an epic whose task graph permits parallelism completes in
materially less wall-clock time than serial fly, with history that is
bead-for-bead equivalent in structure to what serial fly would have produced,
and with zero corrupted bd state across a large test matrix of concurrent
runs.

Out of scope: credential pooling across subscriptions (next feature — this
feature runs the pool against each role's existing single binding, which
naturally bounds per-provider concurrency); cross-repository dispatch.
```

### Prompt 10: `credential-pool-leasing` (Slice C — subscriptions)

```
Let a single agent role draw from a pool of credentials across providers and
subscriptions, with per-task leasing, quota-aware rotation, and per-binding
concurrency caps as a first-class terms-of-service compliance control.

Today each role resolves to exactly one (provider, model) binding. With
concurrent beads, that binding becomes both a throughput bottleneck and a
compliance risk: multiplexing one seat-based subscription across many
concurrent agents may violate provider terms.

- Pool configuration: a role may declare a list of credential bindings instead
  of a single one, each carrying provider, model, auth reference, and — 
  required, not optional — max_concurrent. The cap is a designed compliance
  control reflecting what the subscription's terms permit, not a rate limiter;
  configuration that omits it does not validate.
- Leasing: a worker leases one binding for the duration of a bead and releases
  it on completion. Leases respect max_concurrent absolutely: no binding ever
  serves more simultaneous work than its cap, even transiently.
- Rotation and cooldown: on a quota or billing error (detection already exists
  in the quota exception hierarchy), the lease's binding enters a cooldown
  with backoff, the work retries on the next eligible binding in the pool, and
  an exhausted pool falls back to an explicitly configured fallback binding or
  parks the bead as blocked-on-capacity — never silent failure, never
  hammering an exhausted subscription.
- Attribution: every execution record in the task container carries the
  binding that actually served it, so per-subscription usage and cost are
  auditable after the fact.
- Interaction with tiers: complexity tiers remain the routing policy (which
  class of model should do this work); the pool is the capacity layer beneath
  it (which concrete credential serves it now). Tier selection happens first,
  then leasing within that tier's pool.

Success looks like: a two-subscription setup with caps of 2 and 1 never
exceeds either cap under a WIP-5 dispatcher, rotates within one retry on a
simulated quota exhaustion, recovers the cooled binding after its window, and
the task container attributes every bead to the subscription that ran it.

Out of scope: automatic discovery of credentials; sharing pools across
repositories; any attempt to evade provider rate limits — this feature exists
to respect them.
```

---

## Tier 3 — quality and surfaces

### Prompt 11: `verification-taxonomy` (Slice E)

```
Give fly's review gate a real verification taxonomy: an explicit plan-
conformance check against the bead's scope and acceptance criteria, findings
graded on their own scale, persisted as durable artifacts, and consumed by the
fix loop at a configurable threshold.

Today the reviewer returns a pass/fail-ish judgment with prose findings.
Missing: a defined severity scale for findings, an explicit check that the
implementation matches the bead's declared scope (not just that the code is
good), durable persistence of what the reviewer said, and a tunable answer to
"which findings force a fix round?"

- Findings taxonomy: critical, major, minor, outdated — where outdated marks a
  finding invalidated by a later fix round rather than resolved. This scale is
  deliberately distinct from assumption severity: "the code deviates from the
  plan" and "the agent guessed about intent" are different questions, and
  conflating them muddies the land gate. Nothing from this taxonomy enters
  the assumption ledger.
- Plan conformance: the reviewer explicitly verifies the diff against the
  bead's scope, file expectations, and acceptance criteria from ingestion, and
  reports out-of-scope changes as findings. Scope creep is a first-class
  finding type, not a vibe.
- Durable artifacts: each review round persists its full findings under the
  bead's execution record in the task container, so review history survives
  the session and is auditable per fix round.
- Fix-loop threshold: which severities trigger a fix round is configuration
  (default: critical and major fix; minor records without blocking). The
  existing fix-round budget and tier-escalation behavior are unchanged.
- Re-verify versus fresh-verify: after a fix round, the reviewer distinguishes
  re-checking prior findings (marking them resolved or outdated) from
  reviewing the fix as new code, and both are recorded.

Out of scope: changing the reviewer agent's underlying model or prompts beyond
what the structured output requires; standalone review (separate feature);
any change to assumption-ledger semantics.
```

### Prompt 12: `fleet-monitor` (Slice F1)

```
Add `maverick monitor`: a live terminal fleet board over the host daemon's
event stream, showing everything currently in flight in one place.

This is the console answer to the GUI board every parallel-runner competitor
ships. brief --watch already proves the render loop (Rich Live, in-place
refresh); the monitor generalizes it from bead counts to the whole fleet.

One screen shows, per in-flight bead: the bead id and title, current phase
(implementing, gate, reviewing, fix round N), the agent role and its resolved
model binding (and credential, once pooling exists), elapsed time, and cost so
far. Around the board: the run/task identity, WIP versus limit, ready-queue
depth, the assumption frontier (open entries by severity — the number that
gates landing), and cumulative cost burn for the session.

The monitor is a pure client of the daemon's event stream: read-only,
attachable and detachable at any time, multiple monitors may watch one run,
and it renders a truthful "nothing is flying" state (plus last-completed
summary) when the fleet is idle. With a serial fly it degrades gracefully to a
single-row board — useful on day one, before the dispatcher lands.

Follow rendering conventions: no emoji, human-readable phase names, no
implementation labels, structured warnings.

Out of scope: any interaction beyond watching (answering entries stays in
maverick review; stopping stays in the fly client); web or GUI surfaces;
historical analytics (the task container holds the data for that later).
```

---

## Smaller follow-ons (specify when wanted)

Not sequenced — each is small, independent, and can slot in anywhere:

- **`maverick-plan` / `maverick-verify` skills** (Slice F2) — extend the
  packaged-skill family proven by `maverick-review`; each backed entirely by
  JSON verbs, never touching jj/bd/files directly.
- **Prompt templates** — `.maverick/templates/*.md` with frontmatter
  applicability rules, rendered into agent prompts.
- **Steering files** — Kiro-style per-directory behavioral rules, scoped
  narrower than the constitution.
- **Model profile presets** — named `balanced` / `frontier` presets over the
  existing tiers config, plus pre-run cost estimation.

## Relationship to the analysis

| Prompt | Analysis slice | Depends on |
|---|---|---|
| 1 batch scheduler | D (1–4) | — |
| 2 learned resolution | D (5–6) | 1 (soft) |
| 3 context-file protection | G | — |
| 4 isolated workspaces | C step 1 / §5.1 | — |
| 5 standalone review | G | — |
| 6 spec delta layer | G | — |
| 7 host daemon | A | — |
| 8 task container | B | 7 |
| 9 dispatcher | C steps 2, 4, 5 | 4, 7 |
| 10 credential pool | C step 3 | 9 (uses 8) |
| 11 verification taxonomy | E | 8 |
| 12 fleet monitor | F1 | 7 (full value: 9) |

The three-part thesis maps as: **Spec Kit under the covers** — already built,
sharpened by 6; **multiple agents / models / subscriptions** — 4 → 7 → 9 → 10;
**batched human interaction on the human's schedule** — 1 → 2, delivered
independently of everything else and first.
