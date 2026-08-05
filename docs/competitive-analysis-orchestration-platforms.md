# Competitive Analysis: Agent Orchestration Platforms

**Date**: 2026-08-05
**Scope**: The full landscape of agent orchestration for software development — spec-driven
methodology layers, plan-first orchestration products, parallel-agent runners, in-process
multi-agent harnesses, cloud async agents, durable-execution frameworks, and human-in-the-loop
infrastructure — mapped against Maverick, airframe, and remo.
**Method**: Public product documentation, vendor sites, independent tool comparisons, and
practitioner write-ups reviewed 2026-08-05, alongside a survey of this repository,
`get2knowio/airframe`, and `get2knowio/remo`.

> **Naming note**: one competitor — the plan-first desktop/IDE product analyzed in depth in §2.2 —
> is referred to as **the reference platform** at the requester's instruction. Every other product
> is named. If this reads inconsistently, the name can be restored in a single edit.

---

## 1. Executive summary

Three things are true at once:

1. **The category has converged on a shared diagnosis.** Across every serious entrant, the same
   sentence appears in different words: *the bottleneck is no longer code generation, it is
   verification and intent*. Everyone is building upward from the coding agent, not competing with
   it.
2. **Nobody has assembled the specific combination you're describing.** Spec-driven tools stop at
   the spec handoff. Fleet orchestrators run many agents but treat human input as a blocking
   interrupt. Human-in-the-loop infrastructure batches approvals but has no spec model and no
   memory of what was decided. **The three-way intersection — deterministic spec substrate ×
   heterogeneous multi-model execution × batched, schedule-respecting human input — is open.**
3. **We already own the hardest piece of it, and don't market it as such.** The assumption ledger
   plus `reconcile` is the primitive that makes non-blocking parallel execution *safe*. Everyone
   else either blocks the agent on a question or lets it guess silently. We record the guess, keep
   flying, surface it on the human's schedule, and can retroactively fold the correction back into
   history. No competitor documentation describes anything equivalent.

The gap is not intelligence or architecture. It is **parallelism** (Guardrail 0 forbids the
isolation everyone else uses), **residency** (our state dies with the process), and **scheduling**
(we have the queue but no delivery mechanism).

---

## 2. The landscape

### 2.1 Segment map

| Segment | What it owns | Representative entrants |
|---|---|---|
| **A. Spec-driven methodology** | *What to build* — structured intent artifacts | GitHub Spec Kit, OpenSpec, AWS Kiro, Tessl, BMAD-METHOD, Spec Kitty |
| **B. Plan-first orchestration products** | Plan → handoff → verify loop over third-party agents | The reference platform (§2.2), HumanLayer/CodeLayer, Intent |
| **C. Local parallel-agent runners** | Fleet execution with isolation + a board UI | Conductor (Melty Labs), Vibe Kanban, Sculptor (Imbue), Claude Squad, Crystal/Nimbalyst, Emdash, Composio Agent Orchestrator, Spec Kitty orchestrator |
| **D. In-process multi-agent** | Coordination *inside* one harness | Claude Agent Teams, Claude Code subagents, Oh My OpenAgent (OmO/Sisyphus), Google Antigravity |
| **E. Cloud async agents** | Fire-and-forget; PR is the return value | Google Jules, OpenAI Codex Web, GitHub Copilot coding agent, Claude Code Web, Devin, Cursor Cloud Agents |
| **F. Durable execution / SDK** | The plumbing under all of the above | LangGraph, Temporal, OpenAI Agents SDK, CrewAI, Google ADK, Strands, **Burr** (ours) |
| **G. Human-in-the-loop infrastructure** | Approval queues as runtime | HumanLayer API, async-approval libraries, OpenAI Agents SDK HITL flow |

**Where we sit today**: A (consume Spec Kit) + B (plan→verify loop) + F (Burr) + a proprietary slice
of G. **We are absent from C, D, and E** — which is precisely the parallelism gap.

### 2.2 Segment B deep dive — the reference platform

Analyzed in full previously; retained here in compressed form since it remains the most complete
implementation of the plan-first thesis.

- **Architecture**: resident host daemon (owns workspace, files, git diffs, terminals, agent
  processes, provider detection; local or remote, OS-service installable) + desktop/IDE client +
  full CLI + cloud (credits, sync, sharing).
- **Task container**: 1..n workspace folders, each independently choosing run location (in-place /
  new worktree / existing worktree), holding panels, canvas tabs, and artifacts.
- **Artifacts**: Spec / Ticket / Story / Review. Tickets and stories carry status + assignee; specs
  and reviews deliberately do not, because they are *shared context, not work units*.
- **Four modes**: single-PR planning, phased planning (with intent clarification and user-editable
  phases), standalone agentic review, and a collaborative board mode.
- **Verification** — the distinguishing mechanic: compares implementation against *the plan it
  issued*, emitting Critical / Major / Minor / **Outdated** findings, with re-verify (cheap,
  iterative) vs. fresh-verify (unbiased) modes.
- **Execution records**: every handoff captured with plan, verification results, commits, status.
- **Autonomy**: fixed mode (config chosen upfront) and adaptive mode (mutates specs and tickets from
  implementation discoveries, re-selects agent/model per ticket, runs tickets in parallel).
- **Config surfaces**: per-step model profiles with a cost calculator; Handlebars-style prompt
  templates; user-defined slash-invocable workflows.
- **Weakness**: autonomy is desktop-tethered — pauses on sleep or IDE disconnect. Monetizes its own
  planning inference via credits.

### 2.3 Segment A — spec-driven methodology layers

The layer we already build on. An independent February 2026 evaluation across 13 scoring categories
found **no universal winner** — rankings shift entirely with priorities.

| Tool | Model | Strength | Weakness |
|---|---|---|---|
| **GitHub Spec Kit** | OSS, model-agnostic, constitution-driven | Greenfield; battle-tested; what we build on | **No worktree automation**; struggles with iterative modification of existing specs |
| **OpenSpec** | MIT | **Delta format** (`ADDED` / `MODIFIED` / `REMOVED`) purpose-built for brownfield; tight `propose → apply → sync → archive` loop | Manual spec-drift management |
| **AWS Kiro** | Proprietary, GA March 2026, Code OSS + Claude via Bedrock | `requirements.md`/`design.md`/`tasks.md` as the unit of work; **agent hooks** (event-driven automation on save/create/delete) and **steering files** (per-folder behavioral rules) | AWS-centric; overkill for small changes |
| **Tessl** | Proprietary | **Spec-as-source** — edit only specs, regenerate code; `.tessl/` tiles teach MCP-compatible agents the workflow | Most opinionated; furthest from how teams work today |
| **BMAD-METHOD** | OSS | 21 specialized agents, enterprise workflow coverage | Sledgehammer overhead |
| **Spec Kitty** | OSS | **Spec Kit + built-in worktree orchestration** + live Kanban + auto-merge + an `orchestrator-api` for external providers | Young; smaller ecosystem |

**Two findings matter directly to us:**

1. **The modification problem.** Spec Kit's identified weakness is exactly the brownfield case —
   iterating on an existing spec rather than authoring a new one. OpenSpec's delta format is the
   field's answer. Our `refuel --speckit` delta re-runs solve this at the *bead* level (append new
   tasks under the existing epic) but not at the *spec* level. Worth evaluating a delta layer over
   `spec.md`.
2. **Spec Kitty is our closest structural competitor.** It is literally Spec Kit + worktrees +
   Kanban + a multi-agent orchestrator API, keeping specs, plans, work packages, acceptance
   criteria, review state, and merge decisions *in the repository*. Same substrate, same in-repo
   philosophy, and it already has the parallelism we lack. It has no assumption-ledger equivalent
   and no history curation — but it is the tool to watch.

### 2.4 Segment C — local parallel-agent runners

The fastest-moving segment, and the one we are entirely absent from. The universal pattern:
**one isolated working copy per agent, a board UI over the fleet, human reviews diffs.**

- **Conductor** (Melty Labs) — Mac app, parallel Claude Code + Codex agents in isolated git
  worktrees. Widely cited as the lowest-friction entry point.
- **Sculptor** (Imbue) — the outlier: each agent runs in its own **Docker container** with a full
  repo copy, not a worktree. Stronger isolation; "Pairing Mode" for switching into an agent's
  workspace. Free in beta.
- **Vibe Kanban** — task cards with diff review; Kanban as the primary interface.
- **Composio Agent Orchestrator** (OSS) — pushes furthest into autonomy: fleets in isolated
  worktrees, each with its own PR, fixing CI failures and review comments, supervised from one
  dashboard.
- **Claude Squad / Crystal / Emdash / Switchboard** — session managers over multiple Claude Code
  instances.
- **Spec Kitty orchestrator** — discovers ready work packages via a host API, runs agents in
  worktrees, transitions through review lanes, auto-merges on accept. 3–10 agents.

**Isolation is table stakes in this segment.** Guardrail 0 puts us on the opposite side of that
consensus. See §5.1 — this is the central architectural tension in your thesis.

### 2.5 Segment D — in-process multi-agent

- **Claude Agent Teams** (shipped with Opus 4.6, 5 Feb 2026) — your session becomes the *lead*;
  teammates are independent Claude Code instances with their own context windows, tool access, and
  permissions, loading project context but **not** the lead's conversation history. Coordination is
  a **shared task list with file locking**; teammates self-claim, blocked tasks auto-unblock when
  dependencies clear, and teammates message each other peer-to-peer. Optimal team size reported at
  **3–5**. Demonstration of scale: 16 instances × 2 weeks × ~2,000 sessions produced a 100k-line
  Rust C compiler that builds the Linux kernel on x86/ARM/RISC-V, for under $20k.
- **Oh My OpenAgent (OmO / Sisyphus)** — OpenCode plugin, ~48k stars, 1.6M+ downloads. Three-layer
  architecture: planning (Prometheus/Metis) → orchestration (Atlas) → execution (Sisyphus-Junior +
  9 specialists). **Its multi-model routing is the closest published analogue to what you want**:
  when the orchestrator delegates, it picks a *category* (`visual-engineering`, `ultrabrain`,
  `deep`, `artistry`, `quick`, `unspecified-low`, `unspecified-high`, `writing`) and the category
  maps to a model. Heavy reasoning → Opus; fast exploration → Gemini Flash; utility work → local
  Ollama.
- **The Ralph Loop** — a widely adopted stateless-but-iterative pattern: pick atomic task →
  implement → validate → commit if passing → **reset context**. Our fly loop with
  `rotate_session()` per bead is already this.

### 2.6 Segment E — cloud async agents

The segment that already solves *your third ask*, crudely: **queue work, walk away, review PRs when
you return.** Jules (Google), Codex Web (OpenAI), Copilot coding agent, Claude Code Web, Devin.

The practitioner consensus is a three-tier day: Tier 1 (in-process) for interactive work, Tier 2
(local orchestrators) for parallel sprints, **Tier 3 (cloud async) to drain the backlog overnight**.
"Queue five well-scoped tickets Friday afternoon, review five PRs Monday morning."

**Their batching boundary is the pull request.** That is coarse: the human sees the *result*, never
the *decisions taken along the way*, and cannot correct an early wrong assumption without
re-running. This is exactly the gap the assumption ledger fills.

### 2.7 Segment G — human-in-the-loop infrastructure

The most directly relevant prior art for your third ask.

**HumanLayer / CodeLayer** — began as a human-in-the-loop approval API (approval decorators,
routing to teams or individuals, escalations, timeouts, learned auto-approvals, webhooks; delivery
over Slack and email) and became a full coding-agent IDE. Notable specifics:

- **QRSPI methodology** — six phases: **Q**uestions (clarifying inquiries before any code) →
  **R**esearch (map dependencies and patterns) → **D**esign (draft doc open to real-time team
  comment) → **S**tructure (phased verifiable milestones) → **P**lan (file paths + acceptance
  criteria) → **I**mplement. The *Questions-first* phase is a direct competitor to our clarify step.
- **Design reviews as collaborative checkpoints** — humans and agents comment inline; comments feed
  directly into subsequent agent instructions rather than sitting in a doc.
- **Architecture**: local daemons for parallel sessions + optional cloud daemons for long-running
  work, synced through one API across web, desktop, and mobile. Tasks group sessions, artifacts, and
  worktrees into shared workspaces for **asynchronous** team collaboration.
- **BYOK billing** — Claude, Codex, and other subscriptions plug in directly; no per-token platform
  margin. This is the model that is winning against credit-metered competitors.

**Approval queues as runtime** — the emerging architectural pattern, worth adopting wholesale:

- Approval items are **first-class runtime objects** carrying the proposed action + args, risk
  classification and policy rationale, owner identity, allowed decisions (approve / edit / reject /
  respond), **checkpoint identifier for graph resumption**, audit trace, timeout, and a post-hoc
  receipt.
- **Risk-tiered routing**: low-risk flows through immediately · **medium-risk batches for periodic
  review** · high-risk interrupts a named owner · forbidden actions fail before reaching a human.
- The motivating statistic: **~93% of permission prompts are clicked through** when systems ask for
  blanket permission. Undifferentiated approval is theater.
- **State persists outside model context**; resumption uses the *same thread identifier*, not a
  fresh run.
- Approval decisions are **production labels** — edits and rejections feed evaluation.

Three published patterns for the pause: synchronous gate-keeping (max control, max latency),
**asynchronous escalation** (agent continues other work while approval pends — requires rejection
handling), and parallel feedback (execute while human reviews, halt on rejection — requires
rollback). **Our design is asynchronous escalation with rollback, which is the strongest of the
three and the only one that requires a `reconcile`.**

### 2.8 Segment F — the plumbing, and one protocol note

LangGraph handles micro-level agent reasoning; Temporal handles macro-level durable lifecycle;
sophisticated teams run both. LangGraph 1.0 (Oct 2025) brought production checkpointing; the
OpenAI Agents SDK × Temporal integration went GA March 2026. **Burr sits in the LangGraph tier and
our use of it is well-placed** — but we have no Temporal-tier durability, which is the same
observation as "we have no host daemon."

**Protocol note — ACP is dead; A2A won.** The Agent Client Protocol (Zed, Aug 2025, JSON-RPC over
stdio) wound down active development and contributed its technology into **A2A**, which reached v1.0
in April 2026 under the Linux Foundation with 150+ organizations and native support in AWS, Azure,
and GCP. The settled stack is **MCP for vertical tool integration, A2A for horizontal agent
coordination**.

This retroactively validates a decision we already made: `specs/042-acp-integration/` is still
marked **Draft**, and we built **airframe** instead. That spec should be formally closed as
superseded. If we later want cross-agent interop, the target is A2A, not ACP.

### 2.9 Cross-field findings

Consistent across independent sources:

1. **"The bottleneck is no longer generation. It's verification."** Universal.
2. **Isolation is table stakes** — worktrees (most) or containers (Sculptor).
3. **"Your spec is the leverage."** Vague requirements *multiply* errors across parallel agents —
   the cost of ambiguity scales with fan-out. This is the strongest possible argument for our
   deterministic Spec Kit substrate.
4. **WIP limits of 3–5 concurrent agents** for meaningful human oversight — from both Agent Teams
   guidance and practitioner write-ups. Unbounded fan-out is a known anti-pattern.
5. **Context multiplication**: "small harmless mistakes compound at a rate that's unsustainable"
   without guardrails.
6. **Human-curated `AGENTS.md` compounds; LLM-generated versions marginally *reduce* success (~3%)
   while raising cost 20%+.** Never let agents edit it. We should enforce this.
7. **Multi-model routing by task category is now standard practice**, not a differentiator.
8. **BYOK/subscription beats credit-metering** on developer preference.
9. **Quota handling is a solved pattern**: rotate to the next credential on quota/billing error,
   apply a cooldown (24h cited), fall back to a configured model when exhausted, and use **per-task
   credential leasing** so concurrent subagents don't collide.

---

## 3. Mapping the landscape onto your three-part thesis

> *"Leverage Spec Kit under the covers, defer execution to multiple agents using different
> models/subscriptions, and aggregate the human interaction into batches that meet the human's
> schedule."*

### 3.1 Spec Kit under the covers — **mostly built; one real gap**

| Requirement | State |
|---|---|
| Spec Kit chain runs headlessly | ✅ `maverick spec` (spec 050), checkpointed, resumable, workspace-isolated |
| Deterministic ingestion to a work graph | ✅ `refuel --speckit`, **zero model calls** (Guardrail 8) |
| Phase barriers / dependency ordering | ✅ bd `blocks` edges wired at ingestion |
| Delta re-runs as `tasks.md` grows | ✅ appends under existing epic, no duplicate epics |
| **Delta edits to the spec itself** | ❌ **Gap** — Spec Kit's known brownfield weakness; OpenSpec's `ADDED`/`MODIFIED`/`REMOVED` is the field's answer |
| Per-folder behavioral rules | ⚠️ Partial — constitution + `CLAUDE.md`, but not Kiro-style scoped steering files |
| Event-driven hooks (on save/commit) | ⚠️ Partial — `hooks/` exists for safety; not a general automation surface |

**Verdict: this leg of the thesis is essentially done and is a genuine differentiator.** Spec Kitty
is the only competitor on the same substrate, and it does not have our determinism guarantee. The
one thing worth stealing is OpenSpec's delta model for spec *modification*.

### 3.2 Multi-agent execution across models and subscriptions — **the hard gap**

| Requirement | State |
|---|---|
| Vendor-neutral runtime abstraction | ✅ **airframe** — 9 adapters, 8-method protocol, `Feature` flags, unified errors, `unwrap()`. Better-engineered than anything in the field. |
| Route work to a model by task character | ✅ `actors.<wf>.<actor>.tiers.<complexity>` — **and ours is better grounded than OmO's**: complexity is assigned by the decomposer from the artifact, not guessed per-call |
| Escalation ladder on failure | ✅ `squadron.tiers.escalation_ladder()`, with the correct guard that a rung must be a genuinely distinct binding |
| **Concurrent execution of N beads** | ❌ **Gap** — fly is a serial drain loop |
| **Isolation per concurrent agent** | ❌ **Blocked by Guardrail 0** — see §5.1 |
| **Subscription/quota-aware routing** | ⚠️ Partial — quota *detection* exists (`exceptions/quota.py`); no credential pool, no leasing, no cooldown, no rotation |
| Fleet visibility | ❌ Gap — no board, no monitor |
| WIP limiting | ❌ N/A today (serial), but needed the moment we parallelize |

**Verdict: airframe is the asset; the dispatcher is missing.** We have the routing *policy* layer
and no *execution* layer to apply it across. Everything in §2.4 exists because these teams built the
dispatcher first and the routing later; we did the reverse, which is the better order — but the bill
comes due now.

One honest flag: **multiplexing a single seat-based subscription across many concurrent agents may
violate provider terms of service.** Per-provider concurrency limits should be a first-class config
concept (`max_concurrent` per binding), not an emergent property of how many beads happen to be
ready. Design it in as a compliance control, not just a rate limiter.

### 3.3 Batched human interaction on the human's schedule — **our moat, half-built**

This is where the analysis gets interesting. Compare what exists:

| Approach | Who | Human interaction model | Weakness |
|---|---|---|---|
| Blocking clarification | Spec Kit `/clarify`, the reference platform's phased mode, HumanLayer's Questions phase | Modal, up-front, synchronous | Blocks the run; the human must be present *now* |
| PR as the batch boundary | Jules, Codex Web, Copilot agent | Review the finished result later | Coarse — decisions taken en route are invisible and uncorrectable without a re-run |
| Approval queue | HumanLayer API, approval-queue pattern | Risk-tiered: low flows, medium batches, high interrupts | Action-scoped, not intent-scoped; queue has no memory once decided |
| Inline design comments | HumanLayer CodeLayer | Async comment threads that feed the next phase | Requires the human before implementation, not after |
| **Assumption ledger** | **Maverick** | Agent adopts a documented assumption, **records it with severity, and keeps flying**; human answers later; `reconcile` folds the answer back into history retroactively | Not yet scheduled, not yet delivered out-of-terminal, not yet batched by time |

**The ledger is categorically different from everything else in the field.** Every other approach
either stops the agent or discards the decision. Ours converts a blocking question into a *durable,
severity-graded, spec-owned artifact* that (a) doesn't stop the fleet, (b) gates landing so it can't
be forgotten, and (c) — uniquely — can be answered *after the code was written* and folded back into
jj history by `reconcile`.

**That last property is what makes deferral safe rather than merely deferred, and it is why this
thesis is achievable for us and not for them.** A competitor who batches questions has to either
block or accept that late answers are unactionable. We can accept a late answer and rewrite history.

What's genuinely missing to complete this leg:

| Requirement | State |
|---|---|
| Non-blocking capture with severity | ✅ `assumptions/ledger.py`, low/medium/high |
| Enforcement so nothing is forgotten | ✅ Strict land gate, any-severity, no bypass flag |
| Retroactive correction | ✅ `maverick reconcile` + mid-flight trigger (spec 051/052) |
| Batch resolution UI | ✅ `maverick-review` skill sweeps the queue via `AskUserQuestion` |
| Bulk disposal | ✅ `review --spec <name> --waive` with severity filter |
| Headless/scriptable | ✅ JSON verbs across review/reconcile/land (spec 053) |
| **Risk-tiered routing of *when* to surface** | ❌ Severity drives *enforcement*, not *timing*. High should interrupt; medium should batch; low should accumulate silently. |
| **Scheduling** — surface at times the human chose | ❌ **Gap.** No windows, no quiet hours, no "review at 9am." |
| **Out-of-terminal delivery** | ❌ **Gap.** ntfy is an optional dep and unused for this. No Slack/email/push. |
| **Timeouts + escalation** | ❌ Gap. An unanswered high-severity entry blocks forever with no nudge. |
| **Learned auto-resolution** | ❌ Gap. HumanLayer learns auto-approvals from prior decisions; runway could do this from prior answers. |
| Decisions as evaluation labels | ❌ Gap. Answers/waivers should feed runway as training signal. |

---

## 4. Where the whitespace is

Plotting the field on two axes — *intent rigor* (how structured the spec substrate is) versus
*human-latency tolerance* (how long the system can run productively without a human):

- **High rigor, low latency tolerance**: Spec Kit, Kiro, Tessl, the reference platform's phased mode,
  HumanLayer QRSPI. Excellent specs; the human must be present at each gate.
- **Low rigor, high latency tolerance**: Jules, Codex Web, Copilot agent, Composio AO. Queue and
  walk away; but "your spec is the leverage" and these have the thinnest specs, so the error
  multiplication problem is worst here.
- **High rigor, high latency tolerance**: **essentially empty.** Spec Kitty is the nearest approach
  and still blocks on review lanes.

**That empty quadrant is the thesis.** The reason it's empty is that high rigor normally *requires*
synchronous human gates — unless you have a mechanism to defer a question without either blocking or
losing it. The assumption ledger is that mechanism. It is the enabling primitive for the quadrant,
and we built it for other reasons.

Stated as a positioning claim:

> **Maverick lets a fleet of heterogeneous agents work a rigorously specified backlog while the
> human is asleep, records every judgment call it had to make instead of guessing silently, batches
> those calls for the human's actual schedule, and rewrites history to match once they answer.**

Nothing in the field currently claims that sentence.

---

## 5. The two architectural tensions

### 5.1 Guardrail 0 versus parallel execution — the central conflict

Every competitor in §2.4 gives each concurrent agent an isolated working copy. Guardrail 0 forbids
exactly that: all long-running ops run in the user's checkout under `Path.cwd()`.

The history matters. Guardrail 0 retired hidden workspaces because **`bd`'s gitignored
`embeddeddolt/` doesn't travel with `jj workspace add`** — a bd constraint, not a worktree
constraint. Spec 050 then proved the mechanism works fine when bd stays out of the workspace (the
spec-chain never runs `bd` inside it).

**Your thesis requires resolving this.** Options, in increasing order of ambition:

1. **Agent-side isolation only.** Beads execute in worktrees; all bd/ledger/jj writes stay in the
   orchestrating process in the user's checkout — exactly the spec-chain contract, generalized. The
   agent never runs `bd`. This is the smallest change that unlocks parallelism and it follows a
   pattern we have already shipped once.
2. **Container isolation** (the Sculptor model). Stronger, and a better fit for untrusted parallel
   work, but a much larger operational surface. Probably not now.
3. **bd federation** — the pull-work-push architecture in
   `.claude/scratchpads/architecture-pull-work-push.md`. The real answer, and the largest bet.

**Recommendation: option 1.** It respects the actual constraint (bd), reuses a proven mechanism, and
does not require federation. Guardrail 0 should be amended from "no workspaces" to "**no bd inside a
workspace**" — which is what it always really meant.

### 5.2 Serial-by-design versus the WIP-limit finding

Worth noting in our favor: the field's own guidance converges on **3–5 concurrent agents** as the
ceiling for meaningful oversight, and warns that context multiplication makes unbounded fan-out
actively harmful. So the target is not "N agents for large N" — it is **3–5 well-isolated agents
with hard quality gates**, which is a far more tractable engineering problem than it first appears.
Combined with per-provider concurrency caps (§3.2), a bounded dispatcher is the right first build.

---

## 6. Revised path forward

Reordered from the previous version to serve the three-part thesis directly.

### Slice A — `maverick host` (daemon)

Unchanged from prior analysis and now **more** important: a fleet needs a supervisor that outlives
any one command. Per-repo process, JSON-RPC over `.maverick/host.sock`, `~/.maverick/hosts/` for
discovery. Owns squadron lifetime (agents opened once, not per-invocation), run/task state, the
`ProgressEvent` stream, provider health, **and the credential/quota pool from Slice C**. Existing
commands become thin clients with one-shot fallback.

This is also what makes fly survivable — kick it off, detach, reattach. Combined with remo, it
closes the gap where cloud-async competitors are strongest *without* their weakness (their
batch boundary is the PR; ours can be the ledger entry).

### Slice B — the task container

Promote `.maverick/runs/<run-id>/` into a resumable **task** spanning `spec → refuel → fly → land`:

```
.maverick/tasks/<task-id>/
  task.json          # workspace folder(s), run location, spec ref, epic bead id, status
  executions/        # per handoff: plan, verification, commits, cost, (provider, model) binding
  events.jsonl       # full ProgressEvent stream
  checkpoints/       # spec-chain checkpointing, generalized
```

Add the `(provider, model, credential)` binding to each execution record — that's what makes
cross-subscription attribution and cost analysis possible later.

### Slice C — the dispatcher **(the thesis's missing leg)**

The largest new piece. Requires §5.1 resolved.

1. **Amend Guardrail 0** to "no bd inside a workspace" and generalize spec-chain's workspace
   mechanism into a reusable `workspace.run_isolated(...)`.
2. **Concurrent bead execution** — replace fly's serial drain with a bounded worker pool. Default
   WIP 3, hard cap configurable. Ready-set computed from bd's dependency graph as it is today.
3. **Credential pool with leasing** — `agents.<role>.credentials[]` as a pool rather than a single
   binding. Per-task lease, rotate on quota/billing error, cooldown on exhaustion, fall back to a
   configured binding. **Per-binding `max_concurrent` as a ToS compliance control.**
4. **Merge discipline** — each bead's worktree folds back via jj; conflicts route into the existing
   round-budgeted conflict machinery from `reconcile`, which already solves this problem.
5. Keep `tiers` as the routing policy — it is already better than the field's category maps.

### Slice D — the batch scheduler **(the thesis's differentiating leg)**

Turns the ledger from a queue into a *schedule-respecting* queue. Small relative to C, high value.

1. **Severity → timing, not just enforcement.** Today severity drives ready-queue and land-gate
   behavior. Add a delivery policy: `high` → interrupt (push immediately); `medium` → batch to the
   next window; `low` → accumulate, surface only at review time or on `--waive` sweep.
2. **Windows** — `assumptions.schedule` in `maverick.yaml`: review windows (`09:00`, `17:00`), quiet
   hours, minimum batch size, maximum age before forced escalation.
3. **Delivery channels** — ntfy is already an optional dependency and unused for this. A batch
   notification carrying count-by-severity, owning specs, and the `maverick review` invocation is
   most of the value. Slack/email later.
4. **Timeouts and escalation** — an unanswered high-severity entry past its max age escalates
   (re-notify, or auto-waive under an explicit policy with a recorded rationale). Never silent.
5. **Learned auto-resolution** — feed answered entries into runway; when a new assumption closely
   matches a previously answered one, propose the prior answer as the default in the review sweep.
   This is HumanLayer's learned-auto-approval idea, and runway is the right home for it.
6. **Decisions as labels** — persist answer/waive/edit outcomes as evaluation signal.

### Slice E — verification with a real taxonomy

Split fly's reviewer output into an explicit **plan-conformance** check against the bead's scope and
acceptance criteria, emitting `critical | major | minor | outdated`, persisted as durable review
artifacts under the task, consumed by the fix loop at a configurable severity threshold. Add the
re-verify / fresh-verify distinction. **Keep this taxonomy separate from assumption severity** —
"faithful to the plan" and "we guessed about intent" are different questions and conflating them
muddies the land gate.

### Slice F — console surfaces

1. **`maverick monitor`** — Rich `Live` over the host's event stream. With Slice C this becomes the
   fleet board that every Segment C competitor ships as a GUI: active beads, agent, bound model,
   fix round, cost burn, assumption frontier.
2. **Extend the skill family** — `maverick-review` proves the pattern. Add `maverick-plan` and
   `maverick-verify`, each backed by JSON verbs, none touching jj/bd/files directly.

The strategic point stands and is sharper after this survey: **every competitor in Segments B and C
built a desktop application because their planning intelligence sits *outside* the coding agent.
Ours sits inside it.** A packaged skill is not a lesser console UI — it is what their GUI is
approximating.

### Slice G — smaller, independently valuable

- **OpenSpec-style delta layer** over `spec.md` — closes Spec Kit's known modification weakness.
- **`maverick review-code [--diff|--epic|--paths]`** — standalone agentic review. (Naming needs
  care; `review` is taken.)
- **Prompt templates** — `.maverick/templates/*.md` with frontmatter applicability, Jinja2.
- **Steering files** — Kiro-style per-directory rules, scoped narrower than the constitution.
- **`AGENTS.md` protection** — the field's data says agent-authored context files *hurt*. A safety
  hook forbidding agent writes to `AGENTS.md`/`CLAUDE.md` is cheap and evidence-backed.
- **Model profile presets** — `balanced` / `frontier` over existing `tiers`, plus cost estimation.
- **Close spec 042 (ACP)** as superseded — ACP folded into A2A; airframe was the right call.

### Order

```
A (host) ──┬─→ C (dispatcher, needs §5.1)  ─→ F1 (fleet monitor)
           └─→ B (task container) ─→ E (verification taxonomy)

D (batch scheduler) ── independent, start now
G (small items)     ── independent, start now
```

**D is the highest value-per-effort item and depends on nothing.** It converts an existing,
differentiated capability into the thing you actually described wanting. C is the biggest build and
the one that needs an architectural decision first (§5.1).

---

## 7. Honest assessment

**On substance we are ahead of the field**, in ways that are hard to replicate: deterministic
ingestion, dependency-graph work modeling, assumption provenance, retroactive history correction,
jj-native curation, typed contracts throughout, and a runtime abstraction better engineered than
anything published. `reconcile` solves a problem the category has not yet named.

**On execution surface we are behind an entire segment.** Every Segment C competitor ships parallel
isolated agents with a board; we ship a serial loop with a log. That gap is architectural
(Guardrail 0), not incidental, and your thesis cannot be delivered without resolving it.

**On the human-latency axis we have an unclaimed, defensible position.** The empty
high-rigor/high-latency-tolerance quadrant exists because deferring a question normally means either
blocking or losing it. We have the only published mechanism that does neither. We have not built the
scheduling layer that would let us claim it, and it is a small build.

**Where we can win outright**: headless autonomy (the reference platform pauses on sleep, we don't),
determinism as a cost structure (they bill model calls where we parse), BYOK-by-construction via
airframe (the model the market prefers), in-agent skill surface (they need a desktop app; we need a
markdown file), and — the real one — **safe deferral of human judgment**.

**Two risks worth stating plainly:**

- **Subscription multiplexing has ToS exposure.** Per-binding concurrency caps must be a designed
  compliance control, not an emergent side effect.
- **Spec Kitty is on our substrate with our philosophy and already has parallelism.** It has no
  ledger and no history curation, but it is the competitor most likely to arrive at the same
  quadrant from the other direction. Worth tracking closely.

## 8. Open questions

- Does the host daemon own the Burr application, or supervise subprocesses that own their own?
  (Affects crash isolation and the two-stage Ctrl-C contract — and matters much more once N beads
  run concurrently.)
- How do concurrent beads write to bd safely? Serialize all bd writes through the host daemon, or
  does bd tolerate concurrent writers?
- Does the mid-flight reconcile trigger still hold under parallelism? `_find_flying_run`'s
  concurrency guard assumes one flying run parked at a safe empty-`@` boundary; with a worker pool
  there is no such single boundary.
- Should the batch scheduler live in the host daemon (requires residency) or run as a cron-style
  external trigger (works today)? The latter is a viable Slice-D-without-Slice-A path.
- Is an OpenSpec-style delta layer additive to Spec Kit, or does it force a substrate decision?
- Multi-repo tasks: given the maverick / sample-maverick-project split, useful or a distraction?

## Sources

**Landscape and practitioner analysis**
- [The Code Agent Orchestra — Addy Osmani](https://addyosmani.com/blog/code-agent-orchestra/)
- [From Conductor to Orchestrator: Multi-Agent Coding in 2026](https://htdocs.dev/posts/from-conductor-to-orchestrator-a-practical-guide-to-multi-agent-coding-in-2026/)
- [AI Agent Orchestration Tools for Coding (2026) — Tembo](https://www.tembo.io/blog/ai-agent-orchestration-tools)
- [9 Open-Source Agent Orchestrators for AI Coding — Augment Code](https://www.augmentcode.com/tools/open-source-agent-orchestrators)
- [AI Agent Orchestration in 2026 — amux](https://amux.io/guides/ai-agent-orchestration-2026/)

**Spec-driven development**
- [spec-compare: 6 SDD tools evaluated](https://github.com/cameronsjo/spec-compare)
- [OpenSpec concepts](https://github.com/Fission-AI/OpenSpec/blob/main/docs/concepts.md) ·
  [OpenSpec vs Spec Kit](https://codemyspec.com/blog/openspec-vs-spec-kit)
- [Spec Kitty multi-agent orchestration](https://priivacy-ai.github.io/spec-kitty/explanation/multi-agent-orchestration.html) ·
  [repo](https://github.com/Priivacy-ai/spec-kitty)
- [AWS Kiro: specs as the unit of work](https://builder.aws.com/content/3DbBI7LQgNIcs6UUj7IPPvqFHOp/aws-kiro-the-agentic-ide-that-makes-specs-the-unit-of-work)

**Parallel execution and isolation**
- [Sculptor — Imbue](https://imbue.com/blog/sculptor-announce) ·
  [coding agent sandboxes list](https://gist.github.com/wincent/2752d8d97727577050c043e4ff9e386e)
- [Composio open-sources Agent Orchestrator](https://www.marktechpost.com/2026/02/23/composio-open-sources-agent-orchestrator-to-help-ai-developers-build-scalable-multi-agent-workflows-beyond-the-traditional-react-loops/)
- [Git worktree isolation patterns — Zylos](https://zylos.ai/research/2026-02-22-git-worktree-parallel-ai-development/)

**In-process multi-agent and model routing**
- [Claude Code Agent Teams guide](https://www.morphllm.com/claude-code-agent-teams)
- [Oh My OpenAgent overview](https://github.com/code-yeongyu/oh-my-openagent/blob/dev/docs/guide/overview.md) ·
  [OmO agents and model guide](https://www.glukhov.org/ai-devtools/opencode/oh-my-opencode-agents/)
- [Agent-as-a-Router: agentic model routing for coding tasks (arXiv 2606.22902)](https://arxiv.org/abs/2606.22902)
- [AI agent model routing strategies — Zylos](https://zylos.ai/research/2026-03-02-ai-agent-model-routing/)

**Human-in-the-loop**
- [HumanLayer](https://humanlayer.com)
- [Approval queues are the runtime for agentic AI workflows — Focused Labs](https://focused.io/lab/approval-queues-are-the-runtime-for-agentic-ai-workflows)
- [Async human approval for AI agents](https://github.com/AxmeAI/async-human-approval-for-ai-agents)
- [The human review bottleneck](https://codex.danielvaughan.com/2026/05/24/human-review-bottleneck-code-review-strategies-agent-output/)

**Cloud async agents**
- [Google Jules async coding agent guide](https://www.digitalapplied.com/blog/google-jules-gemini-async-coding-agent-guide)
- [Background coding agents compared](https://techsy.io/en/blog/background-coding-agents-compared)

**Frameworks and protocols**
- [LangGraph vs Temporal](https://www.langchain.com/resources/langgraph-vs-temporal)
- [Durable agent execution in production 2026](https://agentmarketcap.ai/blog/2026/04/10/durable-agent-execution-production-temporal-modal-event-sourced)
- [MCP, A2A, and where ACP went — Zuplo](https://zuplo.com/blog/agent-protocol-stack-mcp-a2a-acp-2026)
- [Agent interoperability protocols 2026 — Zylos](https://zylos.ai/research/2026-03-26-agent-interoperability-protocols-mcp-a2a-acp-convergence/)

**Internal**
- [get2knowio/airframe](https://github.com/get2knowio/airframe) ·
  [get2knowio/remo](https://github.com/get2knowio/remo)
- This repository: `CLAUDE.md`, `FUTURE.md`, `.specify/memory/constitution.md`,
  `specs/042`, `specs/048`–`053`, `src/maverick/`.
