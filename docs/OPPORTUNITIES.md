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

**Expected impact:** Lower barrier to adoption for new users.

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
