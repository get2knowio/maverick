# Opportunities: Maverick vs. Industry Trends (March 2026)

Research-backed improvement opportunities based on analysis of spec-driven
development trends, multi-agent orchestration patterns, and real-world AI
coding tool performance data from 2025-2026.

## Current Strengths (Validated by Research)

These areas are well-aligned with industry direction and should be maintained:

- **Spec-driven pipeline** (PRD -> Flight Plan -> Beads -> Implement -> Review -> Land) mirrors GitHub Spec Kit, Kiro, and Tessl approaches. Bead granularity (10-20 micro-tasks, each one commit) matches industry consensus.
- **Review-and-fix accountability** is more rigorous than any tool in the landscape. CodeRabbit suggests fixes but doesn't implement them. Maverick's registry-based accountability (fixer must report on every finding, invalid deferrals resent, unresolved items become tech-debt issues) is differentiated.
- **Runway knowledge store** is purpose-built for development workflows. Most AI dev tools have no memory across sessions. Consolidation into semantic summaries puts Maverick ahead of tools that simply accumulate raw context.
- **MCP tool server architecture** aligns with the universal standard (97M monthly SDK downloads, adopted by every major AI provider, donated to Linux Foundation).
- **ACP execution model** provides connection caching, retry, circuit breakers, and provider abstraction that raw subprocess calls lack.

---

## Opportunity 1: Simplify the Briefing Room

**Signal strength:** Strong (multiple independent sources)

**Current state:** 4 parallel briefing agents before flight plan generation
(Scopist, CodebaseAnalyst, CriteriaWriter, Contrarian) and another 4 before
refuel (Navigator, Structuralist, Recon, Contrarian). That's 8 LLM calls just
for context-gathering.

**Research findings:**
- Multi-agent orchestration doesn't help for 95% of tasks (Claude Code docs)
- ETH Zurich: comprehensive auto-generated documentation provides only ~4%
  improvement and can hurt by ~3%
- Martin Fowler's team: AI agents frequently ignore verbose instructions
  despite larger context windows
- Gartner: multi-agent inquiry surge of 1,445%, but counter-prediction that
  single capable agents will supersede multi-agent setups

**Suggested approach:**
- Collapse briefing rooms into 1-2 agents with progressive depth
- Only invoke extra perspectives when the first agent flags uncertainty
- Keep the Contrarian role as a second-pass review rather than a parallel agent
- Measure token cost and quality delta before/after simplification

**Expected impact:** Reduce pre-flight latency by 50-70%, cut token costs
for plan generation and refuel phases.

---

## Opportunity 2: Lean Out Convention Injection

**Signal strength:** Strong (ETH Zurich research, Cursor best practices)

**Current state:** Maverick injects `FRAMEWORK_CONVENTIONS` +
`project_conventions` + runway context into every agent prompt.

**Research findings:**
- Only non-inferable domain knowledge actually helps (specific tooling, custom
  build commands, architectural decisions not deducible from code)
- Anything that ruff/mypy/pytest already enforce shouldn't be in prose rules
- Cursor's advice: "Start simple, add rules only when you notice the agent
  making the same mistake repeatedly"
- Agents faithfully follow bloated instructions, executing unnecessary tests,
  reading irrelevant files, and performing redundant checks

**Suggested approach:**
- Audit convention injection content against what linters/type checkers enforce
- Keep CLAUDE.md under 500 lines of genuinely non-obvious information
- Move machine-checkable constraints to tool configuration (ruff rules, mypy
  strict mode) rather than prose instructions
- Track which convention rules agents actually violate to identify what matters

**Expected impact:** Reduced prompt token usage, faster agent execution,
fewer unnecessary actions.

---

## Opportunity 3: Evolve Runway Toward Observational Memory

**Signal strength:** Medium (emerging pattern, strong theoretical basis)

**Current state:** BM25 retrieval over JSONL episodic records + consolidation
into `consolidated-insights.md` semantic summaries.

**Research findings:**
- Mastra's "Observational Memory" pattern: two background agents (Observer,
  Reflector) compress conversation history into dated observations, eliminating
  retrieval entirely by keeping compressed observations in-context
- This outscores RAG on long-context benchmarks and cuts costs 10x
- The consolidation work already moves in this direction -- the
  `consolidated-insights.md` is essentially an "observation" that replaces
  retrieval

**Suggested approach:**
- Make the consolidated summary the **primary** runway context (always
  injected into agent prompts)
- Demote BM25 to a fallback for specific queries or deep-dive investigations
- Consider a more frequent consolidation cadence (per-fly-session, not just
  during land) to keep the summary current
- Evaluate whether raw JSONL retrieval adds value over the consolidated summary

**Expected impact:** Better agent context quality, simpler retrieval path,
reduced token cost from raw JSONL passages.

### Extension: Two-Layer Learning (Code + Process)

The current consolidator captures **code-level learning** — which files are
tricky, which patterns work, what reviewers flag. This feeds back into agent
prompts and is working as designed.

There is a second layer the consolidator doesn't capture: **process-level
learning.** These are observations about the orchestration itself:
- "This project needs 1800s implement timeouts because cargo builds are slow"
- "Beads with >5 SCs consistently exhaust retries"
- "The implementer rewrites from scratch on retry — prior attempt context
  reduces review issues from 11 to 3"
- "The gate remediation agent can fix clippy errors but not test failures
  because test output was truncated"

This process-level knowledge currently lives only in the human's head (or
in this opportunities document). The supervisor agent (Opportunity 8) would
observe these patterns in real time. But even without a supervisor, the
consolidator could be extended to read checkpoint data (timing, retry
counts, escalation depths) alongside the episodic JSONL files and produce
a second section in `consolidated-insights.md`:

```markdown
### Process Observations
- Average gate check time: 18s (warm cache), 400s (cold cache)
- Beads exceeding 1500s implement time: 60% pass gate, 20% pass review
- Escalation chains deeper than 1 tier: 0% converged via review alone
- Prior-attempt context reduced review issues by 40% on retry
```

### Extension: Self-Improving Project Conventions

The `project_conventions` field in `maverick.yaml` is currently static —
written once during `maverick init` and never updated. But the consolidated
insights contain exactly the kind of project-specific knowledge that
belongs in conventions:

- "Always run `cargo check` before `cargo build` — it's 3x faster for
  catching type errors" (learned from validation timing data)
- "Use `#[cfg(target_os = \"linux\")]` compile-time gates, not runtime OS
  checks — the reviewer flags runtime checks every time" (learned from
  recurring review findings)
- "The `compose.rs` file has deep dependency chains — budget 90s per
  build when modifying it" (learned from problematic files data)

The consolidator could propose additions to `project_conventions` based on
patterns it observes. The human reviews these proposals during `land`
(or via `maverick review` from Opportunity 10), and approved conventions
are appended to `maverick.yaml`. Over time, the project's conventions
evolve based on what actually works — a feedback loop from execution
data to agent instructions.

**Implementation path:**
1. Extend consolidator prompt to output a `### Proposed Convention Updates`
   section alongside the four existing sections
2. During `land`, display proposed updates for human approval
3. Approved updates are appended to `maverick.yaml`'s `project_conventions`
4. Next fly run, all agents receive the updated conventions via
   `$project_conventions` in their system prompts

This creates a self-improving cycle: agents execute → runway records
outcomes → consolidator identifies patterns → patterns become conventions
→ agents execute better. The human stays in the loop as the approver
of convention changes, not the discoverer of patterns.

---

## Opportunity 4: Cap Review Retries to Reduce Thrashing

**Signal strength:** Strong (observed in every e2e run)

**Current state:** Beads routinely get stuck in 5-8 review retry loops
("Review requests changes, 1 issues remaining"). This is the single biggest
practical bottleneck in end-to-end runs -- not code generation quality, but
the review loop never converging.

**Research findings:**
- Devin found pre-scoping work thoroughly is the key to high merge rates
- A controlled trial with 16 experienced developers found AI agents made them
  19% slower when review/specification was the bottleneck
- Anthropic's 2026 report: developers use AI in 60% of work but fully
  delegate only 0-20% of tasks -- the gap is the review bottleneck

**Suggested approach:**
- Cap review retries at 3 (currently unlimited within max_beads budget)
- After 3 failed reviews, commit the work and create a tech-debt bead for
  the remaining finding (the registry already supports this pattern)
- Log the unresolved finding to runway for future context
- Consider whether the review standard is too strict for the task granularity

**Expected impact:** 50-70% reduction in fly duration for beads that
currently thrash. Better token efficiency. Unresolved issues still tracked.

---

## Opportunity 5: Strengthen TDD as Primary Feedback Loop

**Signal strength:** Strong (industry consensus)

**Current state:** ImplementerAgent does internal validation (format, lint,
typecheck, test). Gate check enforces independent validation. This is solid.

**Research findings:**
- Cursor: "Agents perform best when they have a clear target to iterate
  against"
- Devin's highest success rates are on tasks with verifiable outcomes
- TDD as agent feedback is the consensus best practice -- agents iterate
  best against failing tests, not prose requirements

**Suggested approach:**
- Make test-first more explicit in bead descriptions: include expected test
  signatures or test scenarios in work unit specs
- Consider a pre-implementation step that generates test stubs from acceptance
  criteria before the implementer runs
- Track validation pass rates in runway to identify which test types catch
  the most issues

**Expected impact:** Higher first-attempt pass rates, clearer implementer
targets, better alignment between specs and delivered code.

---

## Opportunity 6: Consider Agent Teams for Parallel Review

**Signal strength:** Medium (experimental feature, strong fit for review)

**Current state:** Parallel review uses two ACP agent subprocess calls
(CompletenessReviewerAgent + CorrectnessReviewerAgent) orchestrated by
the workflow.

**Research findings:**
- Claude Code v2.1.32+ introduced Agent Teams: fully independent Claude Code
  instances with shared task lists and mailbox communication
- Best use case cited: parallel code review with specialized reviewers
  (security, performance, testing)
- Each teammate has its own context window, avoiding cross-contamination

**Suggested approach:**
- Evaluate whether native Agent Teams could replace the current parallel
  review orchestration
- If adopted, each reviewer becomes a teammate that claims review tasks
  and communicates findings via mailbox
- Potential to add specialized reviewers (security, performance) without
  additional orchestration complexity

**Expected impact:** Simpler review orchestration code, potential for
additional review perspectives without workflow changes.

---

## Opportunity 7: Reduce jj Installation Friction

**Signal strength:** Low-medium (pragmatic concern)

**Current state:** Jujutsu (jj) is required for all write-path VCS
operations. It provides excellent snapshot/rollback semantics but adds an
installation dependency most developers don't have.

**Research findings:**
- Aider achieves state-of-the-art benchmarks with a Git-first approach
  (automatic commits, no exotic VCS)
- The majority of AI coding tools use git directly
- jj's colocated mode shares `.git`, so the rollback benefit could
  potentially be replicated with git stash/worktree patterns

**Suggested approach:**
- Keep jj as the recommended path (the rollback semantics are genuinely
  valuable)
- Consider a git-only fallback for users who can't install jj
- Use `git stash` + `git worktree` as a degraded alternative for
  snapshot/restore

**Important: jj enables retroactive human corrections (Opportunity 10).**
When a human answers a question about bead 3's approach after beads 4-6
have already built on top of it, jj's automatic rebasing makes the fix
trivial:

1. `jj edit` to bead 3's revision
2. Agent applies the human's correction
3. `jj new` to return to the working copy
4. jj automatically rebases beads 4, 5, 6 on top of the amended bead 3
5. Conflicts show up as markers in affected files — the next agent pass
   resolves them naturally

In git, this same operation requires manual `git rebase -i` with conflict
resolution at each step — destructive, error-prone, and not automatable.
This retroactive correction capability is a strong argument for keeping jj
as the primary VCS even if a git fallback is offered. A git-only fallback
would need to either reject retroactive corrections entirely or implement
a fragile rebase-and-resolve loop.

**Expected impact:** Lower barrier to adoption for new users (git fallback),
while preserving jj's unique value for retroactive corrections and
human-agent collaboration during the asynchronous review queue
(Opportunity 10).

---

## Opportunity 8: Supervisor Agent for Adaptive Orchestration

**Signal strength:** Strong (observed across 4 end-to-end runs against Deacon)

**Current state:** The fly workflow loop in `workflow.py` makes decisions with
hardcoded rules — fixed timeouts, fixed retry counts, fixed escalation
thresholds. When these don't fit the project (e.g., Rust compilation needing
longer timeouts than Python linting), a human must manually kill the run,
adjust `maverick.yaml`, and restart. No agent has cross-bead situational
awareness.

**Observed problems (Deacon runs 1-4):**
- Gate remediation timed out at 600s because `cargo build -j2` is slow — a
  human had to bump the timeout to 1200s
- The implementer had a 600s timeout but needed 5+ build-fix cycles at ~90s
  each — a human bumped to 1800s
- Review oscillation (10-16 issues, never converging) ran for 7 escalation
  tiers before a human diagnosed the circuit breaker field-name bug
- The decomposer produced beads covering 4-7 SCs but the validator limit
  was 3 — required 3 decompose attempts to converge
- Build-green SCs (cargo fmt, clippy, test) were included in the flight plan
  but are enforced by the gate check — a human had to trim them

In every case, a supervisor with access to the checkpoint trajectory could
have detected and corrected the issue without human intervention.

**Design direction:**
- A lightweight agent that runs between bead iterations (not during)
- Reads: checkpoint data, issue count trajectory, timeout/duration history,
  gate check results, chain depth
- Writes: config adjustments (timeouts, retry limits), context injections
  for the next bead, skip/escalate decisions
- Does NOT replace the workflow loop — advises it
- Does NOT run during agent steps — only in the orchestration gaps

**Example interventions:**
- "Gate remediation timed out twice on cargo build. Bumping timeout to 1200s."
- "Bead .1 has failed gate check 3 times with the same clippy error. Injecting
  the error text into the implementer prompt for the next attempt."
- "Review issue count has oscillated between 10-14 for 4 attempts. Firing
  circuit breaker."
- "Implement step used 850/900s on last attempt. Bumping timeout to 1800s."

**Tradeoffs:**
- Pro: Single point of situational awareness, can make cross-cutting decisions
  that individual agents can't
- Pro: Eliminates the most common reason for human intervention during fly
- Con: Another agent to pay for (though lightweight — reads JSON, emits small
  config patches)
- Con: Risk of bad interventions (mitigated by conservative defaults and
  audit logging)

**Alternative considered:** Give each agent access to maverick.yaml and the
checkpoint so they can self-adjust. Rejected because agents modifying their
own orchestration config is dangerous — one bad write could break the pipeline,
and there's no single point of awareness across beads.

**Expected impact:** Reduce human intervention during fly from ~5 manual
adjustments per run to near-zero. Enable truly unattended multi-hour runs.

---

## Opportunity 9: Supervisor-Driven Resource Tuning

**Signal strength:** Strong (observed across 4 end-to-end runs against Deacon)

**Current state:** Resource parameters (`-j2` parallelism, per-step timeouts,
`parallel.max_agents`) are static values in `maverick.yaml`, chosen by a human
before the run starts. They don't adapt to actual workload. A bead touching
one file compiles in 40s; a bead touching `compose.rs` with deep dependency
chains takes 180s. The same `-j2` and `timeout: 600` applies to both.

**Observed problems (Deacon runs):**
- Gate remediation timed out at 600s because `cargo build -j2` is slow on
  this codebase — a human had to bump to 1200s
- The implementer had a 600s timeout that allowed only 2 build-fix cycles
  before being killed — a human bumped to 1800s
- `-j2` was a conservative guess for OrbStack constraints; actual utilization
  was unknown
- After timeout bumps, some steps completed in 15-160s — the budget was
  10x what was needed, wasting wall-clock time on other steps that could
  have run sooner

**Design direction (extends Opportunity 8 supervisor):**
The supervisor agent already reads checkpoint data between bead iterations.
Extend it to monitor resource utilization and adjust parameters:

**Data already available in checkpoints:**
- `duration_ms` per gate check stage (proxy for build/test time)
- `timeout` vs actual duration (utilization ratio)
- Step failures with `MaverickTimeoutError` (overload signal)
- Total step count and wall-clock time per bead

**Knobs the supervisor could adjust:**
- `-j` flags in `validation.sync_cmd`, `lint_cmd`, `test_cmd`
- `parallel.max_agents` and `parallel.max_tasks`
- Per-step `timeout` values in `steps.*`
- `validation.timeout_seconds` (per-command gate timeout)

**Example interventions:**
- "Last 3 gate checks completed `cargo build` in 45s avg. Bumping `-j2` to
  `-j4` and reducing build timeout from 600s to 120s."
- "Gate remediation used 1150/1200s. Bumping timeout to 1800s for next bead."
- "Implement step completed in 160/1800s. Reducing to 600s to free up time
  budget."
- "System load average >4.0 during last build. Reducing `-j4` back to `-j2`."

**Architecture:** Same thermostat pattern as Opportunity 8 — read checkpoint
metrics, emit config patches, let the deterministic workflow loop execute with
updated parameters. The workflow shape never changes; only the resource
envelope does.

**Expected impact:** Better resource utilization, fewer timeout-induced
failures, adaptive performance without human tuning between runs.

---

## Opportunity 10: Asynchronous Human Review Queue

**Signal strength:** Strong (observed need across all end-to-end runs)

**Current state:** The fly phase runs unattended until completion, then the
human reviews everything during `land`. There is no mechanism for agents to
flag questions, surface assumptions, or request human input during execution.
When an agent encounters ambiguity (e.g., "should this be a compile-time
`#[cfg]` gate or a runtime OS check?"), it makes an assumption and proceeds.
The human only discovers these assumptions during final review — often too
late, since subsequent beads may have built on top of the wrong choice.

Conversely, when a bead exhausts retries and gets tagged `needs-human-review`,
the human doesn't find out until the entire fly completes. On a 2-hour run,
a question that arose in minute 20 sits unanswered for 100 minutes while
dependent work proceeds on assumptions.

**Observed problems (Deacon runs):**
- Agents chose runtime OS checks vs compile-time `#[cfg]` gates without
  asking — reviewer flagged this 3 times across retries
- The circuit breaker tagged beads as `needs-human-review` but the human
  couldn't act until land phase
- Review findings accumulated assumptions ("assumed Alpine shadow-utils
  available") that a 30-second human answer could have resolved

**Design direction — two complementary mechanisms:**

### 1. Question queue (agent → human)

Agents can write structured questions to a queue during any phase:

```
.maverick/runs/{run_id}/questions/
  q-001.json   {"bead_id": "...", "question": "...", "context": "...",
                 "severity": "blocking|advisory", "status": "pending"}
  q-002.json   ...
```

- **Blocking questions** pause the bead (skip to next, come back later)
- **Advisory questions** record the assumption made and continue
- Questions are JSONL or individual files for easy concurrent access

The implementer and reviewer agents would need a tool or convention to
write questions. The simplest path: a `.maverick/context/questions.jsonl`
file that agents append to via their existing Write tool.

### 2. Human review CLI (`maverick review`)

A new subcommand (or addition to `maverick brief`) that a human can run
at any time during a fly session:

```bash
# See pending questions
maverick review --questions

# Answer a specific question
maverick review --answer q-001 "Use #[cfg(target_os)] compile-time gate"

# See beads tagged needs-human-review
maverick review --flagged

# Approve a flagged bead to continue processing
maverick review --approve deacon-uh1.7
```

The fly workflow checks the question queue between bead iterations
(in the supervisor gap between beads, not during agent execution).
If a blocking question has been answered, the paused bead becomes
eligible for retry with the human's answer injected into its context.

### 3. Interaction model

The key design constraint: **the human and the agents never block each
other.** The fly continues processing other beads while questions queue
up. The human can pop in at any time (or not at all — unanswered
questions surface during land). The two operate on independent cadences:

```
Agent timeline:   [bead1]──[bead2]──[bead3]──[bead4]──...
                      ↓         ↓
                   q-001     q-002
                   (advisory) (blocking → skip, come back)

Human timeline:      ·····[review q-001]·····[review q-002]····
                           ↓                  ↓
                        answer recorded     bead retried with answer
```

**Storage:** Questions and answers live in `.maverick/runs/{run_id}/`
alongside bead snapshots, keeping all per-run output organized together.

**Land integration:** During `maverick land --eject`, the curation step
displays unanswered questions alongside the human-review manifest:

```
Landing consumer-core-completion (6 beads)

  ✓ 4 beads passed review cleanly
  ⚠ 1 bead needs human review:
     deacon-uh1.7: ephemeral Dockerfile UID sync
       → 11 review issues after 3 attempts

  ? 2 unanswered questions:
     q-001: Should UID sync use #[cfg] or runtime check? (advisory)
       Agent assumed: runtime check via std::env::consts::OS
     q-002: Should Alpine images get shadow-utils auto-install? (blocking)
       Bead deacon-uh1.2 skipped — awaiting answer
```

**Tradeoffs:**
- Pro: Human and agents collaborate without blocking each other
- Pro: Questions are answered with full context (the human sees the bead
  description, the agent's assumption, and the review findings)
- Pro: Works with any cadence — check every 10 minutes or only at land
- Con: Adds complexity to the fly loop (question queue checking)
- Con: Blocking questions reduce parallelism (bead is skipped until answered)
- Con: Requires a new CLI subcommand and agent tooling

**Implementation phases:**
1. **MVP:** Advisory-only questions via file convention (agents write to
   `.maverick/runs/{run_id}/questions/`). Display during land. No blocking.
2. **V2:** `maverick review` CLI for answering questions mid-flight.
   Blocking question support with bead skip/retry.
3. **V3:** Notification integration (ntfy, Slack) when blocking questions
   arise. Human gets a push notification instead of polling.

**Expected impact:** Reduce assumption-driven rework. Enable longer
unattended runs by letting humans address critical questions asynchronously.
Move the human-in-the-loop from a synchronous gate (land) to an
asynchronous collaboration channel.

---

## Opportunity 11: Provider Quota Detection and Automatic Failover

**Signal strength:** Strong (observed in Deacon runs 8-9)

**Current state:** When a provider hits its usage quota (e.g., "You're out
of extra usage · resets 3pm UTC" or copilot plan limits), the ACP subprocess
returns an error message or empty response. The executor classifies this as
`MalformedResponseError` ("no JSON block found") or `NetworkError` and
retries 3 times against the same broken provider. Each retry fails in
sub-second time, wasting the retry budget. The actual quota error message
is buried in `raw_response` and never surfaced to the user.

**Known error strings:**
- Copilot quota: `"402 You have no quota (Request ID: [id])"`
- Claude quota: `"You're out of extra usage · resets 3pm (UTC)"`
- Claude quota (via ACP): `"You've hit your limit · resets 8pm (undefined)"`

**Observed symptoms:**
- Copilot gpt-5.3-codex returned `402 You have no quota` in ~800ms for
  all detail and implement steps. The executor classified these as
  `MalformedResponseError` ("no JSON block found") because the 402
  error body isn't JSON. Binary split retried down to single units,
  all failed. 20+ minutes of wasted retries.
- Claude sonnet hit "out of extra usage" and failed with `NetworkError`
  after the first retry. Error message was clear but not classified as
  a quota issue.
- During refuel briefing, 3 of 4 Thespian briefing actors hit quota
  mid-session. The supervisor marked them as "completed" (✓) with null
  results, proceeded to the contrarian (which also hit quota), then
  passed empty briefing results to the decomposer which crashed on
  `'dict' object has no attribute 'key_decisions'`. The workflow did
  not exit cleanly — raw ERROR lines leaked to the terminal.

**Three-tier design direction:**

### Tier 1: Clean failure (minimum viable)

When an agent hits quota, the workflow should exit cleanly with a clear
message instead of crashing with an AttributeError downstream.

- Classify quota errors as a specific `ProviderQuotaError` exception type
- In `AcpStepExecutor.execute()`, detect quota patterns in error messages:
  "rate limit", "quota", "plan limit", "usage limit", "out of extra usage",
  "exceeded", "resets", "You have no quota", "hit your limit", "402"
- Mark `ProviderQuotaError` as **non-retryable** (don't waste retries
  against a dead provider)
- Supervisor should detect agent failures (null results) and abort the
  phase cleanly instead of proceeding with missing data
- Surface quota errors via structured CLI output:
  `[red]Error:[/red] Provider 'claude' hit usage quota (resets 8pm UTC)`

### Tier 2: Wait and resume

When quota is hit, pause the affected agents and wait for quota to reset
instead of failing immediately.

- Parse the reset time from the error message ("resets 8pm UTC")
- Display a countdown: `Quota exhausted. Waiting for reset at 8pm UTC...`
- Keep the Thespian actor system alive — actors retain their ACP sessions
- When reset time arrives, retry the failed prompts
- Briefing agents that already succeeded don't need to re-run — only
  retry the ones that failed
- Use a configurable max wait time (default: 60 min) to avoid infinite waits

### Tier 3: Automatic provider failover

When one provider hits quota, switch to an alternative provider that still
has quota available.

- The `agent_providers` config already defines multiple providers
- When `ProviderQuotaError` is raised for provider A, check if provider B
  is configured and available
- Create a new executor for provider B and retry the failed step
- Surface the failover in CLI output:
  `Provider 'claude' hit quota. Switching to 'copilot' for remaining agents.`
- Sub-second failure detection: if 3 consecutive responses complete in
  <2 seconds, treat as provider degradation regardless of error type

**Implementation phases:**
1. **Tier 1 (clean failure):** Error classification, clean exit, clear message
   — **Implemented** (2026-04-15): `ProviderQuotaError` exception,
   `is_quota_error()` detection in all actors, failed agents show ✗,
   supervisor aborts immediately on quota, raw structlog ERROR lines
   suppressed.
2. **Tier 2 (wait and resume):** Parse reset time, countdown, retry on reset
3. **Tier 3 (failover):** Multi-provider routing, automatic switching

### ACP UsageUpdate Events (Tier 2 prerequisite)

The ACP SDK streams `UsageUpdate` notifications during session execution
with fields: `size` (total context window in tokens), `used` (tokens
currently in context), and `cost` (cumulative session cost with amount
and currency). Maverick's `MaverickAcpClient.session_update()` does not
currently handle `UsageUpdate` events — `ExecutorResult.usage` is always
`None`.

Wiring up `UsageUpdate` handling would enable:
- Tracking context window utilization per agent (useful for the supervisor
  in Opportunity 8)
- Cumulative cost tracking per workflow run
- Proactive warning when context is nearly full (before a hard failure)

However, **quota remaining is NOT exposed** via `UsageUpdate` or any other
ACP session metadata. Quota exhaustion is only discoverable when a request
fails with an error message containing the reset time. This means Tier 2
(wait and resume) must rely on parsing the error message, not on proactive
quota checking.

**Expected impact:** Tier 1 eliminates confusing crash output. Tier 2 enables
unattended overnight runs that survive temporary quota exhaustion. Tier 3
enables truly resilient runs across provider outages.

---

## Opportunity 12: Step-Level Evals and Provider/Prompt Testing

**Signal strength:** Strong (direct observation from 10+ Maverick runs)

**Current state:** Pipeline optimization is entirely serial. Each full run
(plan + refuel + fly) takes 30-60 minutes. When a step fails — wrong model
for structured output, prompt that produces brittle verification commands,
reviewer that always finds phantom issues — we don't discover it until the
pipeline stalls. Fixing requires changing config/prompts and rerunning the
entire pipeline to verify. This makes iterating on prompt quality or
provider routing painfully slow.

**Research findings:**
- Eval-driven development is standard practice for LLM applications (Anthropic,
  OpenAI, Braintrust, Humanloop all publish eval frameworks)
- The "evals as unit tests for AI" framing is now consensus — you wouldn't
  ship code without tests, don't ship prompts without evals
- SWE-bench and similar benchmarks demonstrate that model+prompt quality
  varies dramatically per task type — what works for code generation fails
  for structured output, and vice versa

**Observed failures that evals would catch in minutes, not hours:**
- GPT-5.3-Codex cannot produce JSON output (0/6 attempts across two runs)
  — a single step eval with one fixture would show this immediately
- Gemini reviewer file output failures masked by sentinel default of 1
  — a review step eval checking `file_output=true` catches this
- Verification commands that grep source code instead of running tests
  — a prompt variant eval comparing behavioral vs structural commands
- Review severity miscalibration across providers — an eval comparing
  finding counts and severity distributions per provider

**Design direction:**

**Phase 1: Fixture capture (zero-cost, passive).** Add a hook to
`execute_agent` that snapshots step inputs (prompt, config, context) to
`.maverick/eval-fixtures/<step>/<timestamp>.json`. This runs during normal
pipeline execution with no overhead. One good run produces fixtures for
every step.

**Phase 2: Step-level test runner.** A new command:
`maverick eval <step-name> --fixture <path> --matrix <matrix.yaml>`

The matrix defines permutations to test in parallel:
```yaml
decompose-detail:
  permutations:
    - {provider: claude, model_id: sonnet}
    - {provider: copilot, model_id: gpt-5.3-codex}
    - {provider: copilot, model_id: gpt-5.4}
    - {provider: gemini, model_id: gemini-3.1-pro-preview}
  repeat: 3  # catch non-determinism
  evaluate:
    - json_valid       # produced parseable JSON?
    - schema_valid     # matches expected Pydantic model?
    - file_output      # wrote to output_file_path?
    - sc_coverage      # what % of SCs are traced?
```

Runs N permutations x M repeats concurrently via `asyncio.gather`, produces
a comparison table. Tests one step in 3-5 minutes instead of running a full
45-minute pipeline.

**Phase 3: Prompt variant testing.** Same framework but varying prompt
templates instead of (or in addition to) providers. Enables A/B testing
of prompt changes against captured real-world inputs.

**Phase 4: Regression suite.** Version fixtures by run. When a prompt
template or pipeline step changes, run the eval suite against historical
fixtures to verify nothing regressed. This is CI for the pipeline itself.

**Phase 5: Provider routing optimization.** Accumulate eval data across
runs to build a quality/cost/latency profile per model per step type.
Feed this into the supervisor agent (Opportunity 8) for adaptive routing.

**Relationship to other opportunities:**
- **Opportunity 4** (Cap Review Retries): Evals quantify reviewer false
  positive rates, enabling data-driven retry calibration
- **Opportunity 5** (TDD Feedback Loop): Step evals ARE the TDD loop for
  the pipeline itself
- **Opportunity 8** (Supervisor Agent): Needs eval telemetry to make
  adaptive decisions
- **Opportunity 9** (Resource Tuning): Cost/quality metrics from evals
  inform provider allocation
- **Opportunity 11** (Quota Failover): Eval data shows which providers
  are viable fallbacks per step type

**Expected impact:** 10x faster iteration on prompt and provider optimization.
Catch model-fit problems (like Codex + JSON) in minutes, not hours. Enable
confident prompt changes with regression coverage. Build the data foundation
for adaptive orchestration.

---

## Opportunity 13: Idempotent `maverick init`

**Signal strength:** Strong (observed every test cycle)

**Current state:** `maverick init` refuses to run if `maverick.yaml` exists
(`ConfigExistsError`). This means it also skips `bd init`, runway
initialization, and any other setup steps. Users who have a tuned
`maverick.yaml` (custom provider routing, adjusted timeouts, test commands)
must manually run `bd init` and other sub-initialization steps after
resetting their repo.

**The problem:** In iterative testing workflows (reset repo → re-run
pipeline), you always have a pre-existing `maverick.yaml` that you don't
want overwritten. But you do need beads re-initialized, runway seeded, and
prerequisites checked. Currently you must run `bd init` manually and hope
you didn't miss other setup steps.

**Suggested approach:**
- `maverick init` without `--force`: detect existing yaml, skip config
  generation, but still run all other setup steps (bd init, runway init,
  prerequisite checks)
- `maverick init --force`: overwrite yaml AND run all setup steps (current
  `--force` behavior)
- Make each sub-step idempotent: `bd init` already handles re-initialization;
  runway seed should be safe to re-run; prerequisite checks are read-only

**Broader benefit:** Making init idempotent enables treating it as a
"ensure everything is set up" command rather than "one-time setup."
This is valuable for CI/CD pipelines, container rebuilds, and any
workflow where the environment may be partially initialized.

**Expected impact:** Eliminate manual `bd init` / runway seed steps in
testing workflows. Enable `maverick init && maverick plan && maverick
refuel && maverick fly` as a single repeatable sequence regardless of
prior state.

---

## Opportunity 14: Route Agent Tool Calls Through the Owning Actor

**Signal strength:** Strong (observed during cascade debugging, April 2026)

**Current state:** When an agent calls an MCP tool, the call goes:

```
Agent (ACP session)
  └─ MCP tool call
      └─ maverick serve-inbox (subprocess spawned by the owning actor)
          └─ asys.tell(supervisor, {"tool": ..., "arguments": ...})
```

The MCP server subprocess is spawned by the actor that owns the ACP
session (e.g., `DecomposerActor`), but when the agent calls a tool, the
MCP server bypasses its spawner and `tell()`s straight to the supervisor
via `globalName="supervisor-inbox"`. The supervisor's `_handle_tool_call`
treats this identically to any other Thespian message.

This is a tunnel: data from the agent jumps over the actor that owns the
session and lands in a different actor's inbox. The MCP server has to
know Thespian admin ports, the supervisor's globalName, and the wire
format of the supervisor's inbox. The owning actor plays no part in
observing or filtering its own agent's output.

**The layering problem:** two transports (ACP/MCP above, Thespian below)
are blended into one pipeline instead of being separated by a clean
boundary. The MCP server is doing double duty as an MCP endpoint *and* a
Thespian peer. Every subsystem that wants to react to tool calls — the
supervisor's routing, one-shot enforcement, accountability tracking,
future policy rules — must reach into that pipeline at the point where
MCP and Thespian meet. There is no single place where "the agent just
said X" is a first-class event.

**Observed pain (April 2026 cascade debugging):** the primary decomposer
looped through `submit_outline` ten-plus times per refuel, each call
arriving at the supervisor despite guards. Fixing it required threading
a `one_shot_tools` concept from the decomposer actor down through
`AcpStepExecutor.create_session()` into `MaverickAcpClient.reset()`, a
new `_state.one_shot_fired` flag distinct from the circuit-breaker
`abort` flag, and event-callback logic inside the ACP client that fires
`conn.cancel(session_id)` when a matching `ToolCallStart` streams
through. Three files, four concepts, all because the rule ("primary's
turn ends the moment it submits the outline") had to be enforced in the
ACP stream layer — the only layer that naturally observes its own tool
calls in the current topology. The owning actor, which *conceptually*
owns that rule, has no visibility into its own agent's tool calls and
can't participate in the decision.

**Proposed architecture:** tool calls return to the owning actor, which
applies per-role policy and then forwards to the supervisor as a plain
actor message.

```
Agent (ACP session)
  └─ MCP tool call
      └─ maverick serve-inbox (subprocess)
          └─ asys.tell(owning_actor, {"tool": ..., "arguments": ...})
              └─ owning_actor.receiveMessage:
                   - applies per-role policy (e.g., cancel turn for primary)
                   - self.send(supervisor, {"tool": ..., "arguments": ...})
```

The owning actor becomes the layer boundary. Below it: Thespian
messages, ordinary actor state, normal tracing. Above it: ACP sessions
and MCP tool calls. The MCP server needs exactly one address — its own
owning actor's — and nothing else about the broader topology.

**How today's one-shot fix simplifies under this design:**

Current implementation (what we shipped):

- `_SessionState.one_shot_fired: bool` (new state flag)
- `MaverickAcpClient._one_shot_tools: frozenset[str]` (new instance field)
- `MaverickAcpClient.reset(..., one_shot_tools=...)` (new parameter)
- `AcpStepExecutor.create_session(..., one_shot_tools=...)` (new parameter)
- `ToolCallStart` handler branch to fire `conn.cancel(session_id)` when
  a one-shot tool streams through
- Distinct treatment of `aborted` vs `one_shot_fired` so the executor
  doesn't raise `CircuitBreakerError` on the intentional cancellation

Under the proposed architecture:

```python
# In DecomposerActor.receiveMessage
elif msg_type == "agent_tool_call":
    tool = message.get("tool")
    args = message.get("arguments")

    # Primary's turn ends once it submits the outline.
    if self._role == "primary" and tool == "submit_outline":
        self._run_coro(
            self._executor.cancel_session(self._session_id),
            timeout=5,
        )

    self.send(self._supervisor_addr, {"tool": tool, "arguments": args})
```

One branch. No new state fields on the ACP client, no parameters
threaded through `create_session`, no distinct flags to avoid false
circuit-breaker errors. The rule co-locates with the actor that owns
the state it operates on.

**Other wins:**

- **Policy locality.** Accountability, deduplication, nudge-suppression,
  one-shot enforcement — any rule conditioned on "which agent, in which
  role, said what" is naturally a method on the owning actor. Under the
  current design these rules either live in the supervisor (which has to
  know about every agent's role) or in the ACP client (which knows the
  stream but not the actor's role).
- **Uniform observability.** Everything above the MCP boundary is a
  Thespian message. Logging tool calls, tracing cascades, asserting
  message orderings, measuring per-actor throughput — all become
  ordinary Thespian instrumentation. Today the agent→supervisor hop is
  a tunnel that doesn't show up in actor-level traces.
- **Supervisor simplification.** The supervisor stops having two kinds
  of incoming messages (actor-to-actor events vs. agent-originated tool
  calls). Its inbox is strictly Thespian; tool calls arrive as forwarded
  messages from owning actors with clear provenance.
- **Testability.** Unit tests for the owning actor's policy no longer
  need an ACP stream fixture — they're ordinary `receiveMessage`
  assertions with a dict.
- **MCP server simplification.** The `serve-inbox` subprocess collapses
  to "validate and tell my owner." No globalName resolution, no special
  knowledge of supervisor topology, no admin-port plumbing beyond what's
  needed to join the local actor system.

**Implementation path:**

1. Change `maverick serve-inbox` to accept `--owner-global-name <name>`
   (or `--owner-address <serialized>`) instead of relying on
   `globalName="supervisor-inbox"`. It resolves its owning actor address
   at startup and `tell()`s that.
2. Each agent actor registers its own globalName at creation
   (`decomposer-primary`, `decomposer-pool-0`, `briefing-navigator`, ...)
   and passes that name to its spawned MCP server via the `args=` of
   `McpServerStdio`.
3. Add an `agent_tool_call` message handler to the base agent-actor
   class (or a mixin). Default behavior: forward to `self._supervisor_addr`
   unchanged.
4. Per-role overrides: `DecomposerActor` handles `submit_outline` for
   primary role with a cancel-and-forward step; briefing actors forward
   unchanged (or could apply their own policies later).
5. The supervisor's existing `_handle_tool_call` accepts messages that
   now arrive from owning actors instead of from the MCP server. No
   behavior change there once the forwarding is in place.
6. Delete `one_shot_tools` plumbing from `MaverickAcpClient`,
   `AcpStepExecutor.create_session`, and `DecomposerActor._ensure_agent`
   — the rule now lives in the receiveMessage handler instead.
7. Update tests: unit tests for the owning actor's policy (new,
   lightweight), remove the `one_shot_fired` client-state tests.

**Migration safety:** the supervisor's `_handle_tool_call` is the same
code whether the message comes from the MCP server or a forwarding
actor. The refactor can be done incrementally — one agent actor at a
time, each switching its MCP server's tell-target from supervisor to
self without breaking peers.

**Tradeoffs:**

- **Pro:** clean layer boundary between ACP/MCP and Thespian
- **Pro:** per-role rules co-locate with actor state
- **Pro:** uniform observability of tool calls as Thespian messages
- **Pro:** significantly simpler implementation of the one-shot fix and
  future rules of the same shape (accountability, deduplication, turn
  budgets)
- **Con:** one extra Thespian hop per tool call (owning actor → supervisor).
  Latency is negligible at current scale but worth measuring.
- **Con:** real refactor touching MCP server, every agent actor's init,
  every `serve-inbox` invocation, and the supervisor's inbox tests.
- **Con:** forwarding logic is almost always a pass-through. Most
  handlers will read like `self.send(supervisor, message)` with no
  policy applied. That's fine — proxy actors commonly look like this —
  but it's boilerplate every agent actor has to carry.

**Not doing this now:** the one-shot fix shipped in April 2026 is
correct and contained. This refactor is an architectural cleanup, not a
correctness fix, and should be scheduled deliberately after the current
refuel debugging work stabilizes. When it does happen, the `one_shot_tools`
plumbing from that fix becomes the first thing to delete.

**Expected impact:** dramatically simpler implementation of any future
"react to this specific tool from this specific agent" rule. Uniform
tracing and testing above the MCP boundary. Lower cognitive load when
debugging tool-call paths because the flow no longer skips over the
actor that owns the session.

---

## Patterns to Watch

These are emerging but not yet mature enough for immediate adoption:

| Pattern | Source | Relevance |
|---------|--------|-----------|
| Tessl "spec as source of truth" | Tessl | Code marked `// GENERATED FROM SPEC - DO NOT EDIT` -- interesting for generated boilerplate |
| Context engineering as discipline | Martin Fowler, MIT Tech Review | Shift from prompt engineering to curating what information reaches agents, when |
| Kiro frontier agents | AWS | Autonomous agents that work for days on complex tasks |
| Observational memory | Mastra | Replace retrieval with compressed, always-in-context observations |
| Agent Teams mailbox | Claude Code | Peer-to-peer agent communication without central orchestration |

---

## References

- [Thoughtworks: Spec-Driven Development](https://www.thoughtworks.com/en-us/insights/blog/agile-engineering-practices/spec-driven-development-unpacking-2025-new-engineering-practices)
- [Martin Fowler: Understanding SDD Tools](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html)
- [Martin Fowler: Context Engineering for Coding Agents](https://martinfowler.com/articles/exploring-gen-ai/context-engineering-coding-agents.html)
- [GitHub Blog: Spec-Driven Development with Spec Kit](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/)
- [Anthropic 2026 Agentic Coding Trends Report](https://resources.anthropic.com/2026-agentic-coding-trends-report)
- [Claude Code: Agent Teams Documentation](https://code.claude.com/docs/en/agent-teams)
- [Cursor: Agent Best Practices](https://cursor.com/blog/agent-best-practices)
- [InfoQ: AGENTS.md File Value Research](https://www.infoq.com/news/2026/03/agents-context-file-value-review/)
- [CodeRabbit](https://www.coderabbit.ai/)
- [Devin 2025 Performance Review](https://cognition.ai/blog/devin-annual-performance-review-2025)
- [Aider](https://aider.chat/blog/)
- [VentureBeat: Observational Memory](https://venturebeat.com/data/observational-memory-cuts-ai-agent-costs-10x-and-outscores-rag-on-long)
