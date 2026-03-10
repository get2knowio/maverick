# Product Requirements Document: Repository Substrate Memory

**Document Version**: 1.1
**Date**: 2026-03-09
**Author**: Maverick Team
**Status**: Draft

---

## 1. Overview

### 1.1 Problem Statement

Maverick orchestrates AI agents at discrete points within deterministic workflows. Each agent — implementer, reviewer, curator — operates in isolation: it receives structured inputs, produces structured outputs, and retains nothing. There is no shared understanding of the repository's architecture, no memory of what was tried and failed, no accumulation of learned conventions, and no continuity between beads or across flight plans.

This means:
- A reviewer flags the same anti-pattern in bead after bead because it doesn't know it already flagged it
- An implementer makes the same architectural mistake that was caught and fixed three beads ago
- A new flight plan starts from zero even though the previous flight plan discovered critical patterns about the codebase
- Convention drift goes undetected because no agent has a longitudinal view
- Review findings repeat, fix attempts duplicate, and token spend inflates — all from lack of memory

### 1.2 Proposed Solution

Introduce a **Repository Substrate** — a git-committed, file-based knowledge store that lives alongside the project code and provides persistent, evolving context to all Maverick agents. The substrate accumulates semantic knowledge (architecture, dependencies, contracts) and episodic records (bead outcomes, review findings, fix attempts) — all versioned by git and queryable at agent invocation time. Learned procedural knowledge (conventions, patterns, anti-patterns) is written directly to the project's `AGENTS.md` file, which agents already consume automatically — no new injection mechanism required.

### 1.3 Design Philosophy

The substrate follows three principles drawn from current research:

1. **Git is the temporal knowledge graph.** No external databases. Markdown and JSONL files committed to the repo provide the storage layer. Git history provides the temporal dimension — `git log` and `git diff` answer "what changed and when" without additional infrastructure.

2. **Write-on-complete, read-on-start.** The deterministic workflow controls all substrate I/O. Agents do not write to the substrate directly. Workflow actions write outcomes after agent steps complete, and inject relevant context before agent steps begin. This preserves the separation of concerns between agents (judgment) and workflows (deterministic execution).

3. **Memory must evolve, not just accumulate.** Raw episodic records are periodically consolidated into semantic knowledge updates and learned-pattern additions to `AGENTS.md`. Stale facts are pruned. Contradicted knowledge is corrected. The substrate is a living document, not an append-only log.

4. **Use what already works for procedural memory.** Agents already read `AGENTS.md` automatically on every invocation. Rather than building a parallel procedural memory system, the consolidation process writes learned patterns directly to a managed section of `AGENTS.md`. One source of truth, zero new injection plumbing.

---

## 2. Goals and Non-Goals

### 2.1 Goals

| ID | Goal |
|----|------|
| G-1 | Provide cross-bead continuity so agents benefit from outcomes of prior beads within the same flight plan |
| G-2 | Provide cross-flight-plan continuity so knowledge accumulates across the lifecycle of a repository |
| G-3 | Reduce duplicate review findings and redundant fix attempts by surfacing prior findings to reviewers and implementers |
| G-4 | Enable procedural learning — consolidation writes learned patterns to `AGENTS.md`, which agents already consume automatically |
| G-5 | Store all substrate data as git-committed files — no external databases, no services, no infrastructure beyond the repo itself |
| G-6 | Integrate via MCP tool server so existing agent architecture requires no structural changes |
| G-7 | Support concurrent bead execution — parallel beads in separate jj worktrees must be able to read/write substrate without conflicts |

### 2.2 Non-Goals

| ID | Non-Goal | Rationale |
|----|----------|-----------|
| NG-1 | Cross-repository knowledge sharing | Out of scope for v1; repository substrate is per-repo |
| NG-2 | Real-time vector similarity search | Adds infrastructure dependency; BM25 + structured queries are sufficient for v1 |
| NG-3 | Agent self-modification of substrate or AGENTS.md | Violates separation of concerns; workflows own writes |
| NG-4 | Replacing `.beads/issues.jsonl` | The bead system is orthogonal; the substrate complements it |
| NG-5 | User-facing UI for substrate browsing | Substrate files are human-readable Markdown; no UI needed |
| NG-6 | Separate procedural memory files | AGENTS.md already serves this role; no parallel system |

---

## 3. Research Foundation

This design synthesizes findings from the following sources (see Appendix A for full bibliography):

| Source | Key Contribution to This Design |
|--------|--------------------------------|
| **Letta Context Repositories** | Git-backed MemFS of Markdown files; worktree-based concurrency; background consolidation ("sleep-time") and defragmentation |
| **DiffMem** | Proven model of Markdown-as-memory committed to git; BM25 retrieval; "now view" files with git history as temporal layer; 6+ months production use |
| **A-MEM (NeurIPS 2025)** | Zettelkasten-inspired linked notes; new memories trigger re-evaluation of existing memories; dynamic indexing and relationship discovery |
| **Anthropic MCP Memory Server** | Entity-relation-observation JSONL format; MCP tool interface pattern |
| **Graphiti/Zep** | Bi-temporal data model (event time vs. ingestion time); episode → semantic → community subgraph consolidation |
| **Anthropic Context Engineering** | Selective context injection (not context dumping); minimal viable tool sets; query-on-demand over preamble injection |
| **LangMem** | Three-memory-type taxonomy (semantic, episodic, procedural); procedural memory as prompt rewriting |

---

## 4. Architecture

### 4.1 Storage Layout

All substrate data lives in `.maverick/substrate/` at the repository root, committed to git.

```
.maverick/substrate/
├── semantic/                    # What is true about this repository
│   ├── architecture.md          # Module relationships, key abstractions, data flow
│   ├── contracts.md             # Public API surfaces, interface contracts
│   ├── dependencies.md          # External dependencies, integration points
│   └── conventions.md           # Code style, naming, patterns specific to this repo
│
├── episodic/                    # What happened during execution
│   ├── bead-outcomes.jsonl      # Per-bead: what changed, what was reviewed, outcome
│   ├── review-findings.jsonl    # Per-review: findings, severity, resolution status
│   └── fix-attempts.jsonl       # Per-fix: what was tried, whether it worked, why/why not
│
└── index.json                   # Lightweight index: entity list, last-consolidated timestamp

AGENTS.md                        # Procedural memory (managed section updated by consolidation)
```

Note the absence of a `procedural/` directory. Procedural memory — learned conventions, patterns, and anti-patterns — is written directly to the project's `AGENTS.md` file (see Section 4.3).

### 4.2 Memory Types

#### Semantic Memory (`semantic/`)

Human-readable Markdown files describing what is currently true about the repository. These represent the **"now view"** — git history provides the temporal dimension.

**Example entry in `architecture.md`:**
```markdown
## auth module (`src/app/auth/`)

- Handles JWT-based authentication and RBAC authorization
- Depends on: `redis` (session cache), `postgres` (user store)
- Exposes: `AuthMiddleware`, `require_role()` decorator
- Known constraint: Token refresh uses a sliding window; do not introduce fixed expiry
- Last validated: bead bd-a3f2 (2026-03-08)
```

Semantic files are updated by the consolidation process (Section 4.5), not by individual beads.

#### Episodic Memory (`episodic/`)

JSONL files recording discrete events with full context. These are the raw material that consolidation distills into semantic and procedural knowledge.

**Example entry in `bead-outcomes.jsonl`:**
```json
{
  "bead_id": "bd-a3f2",
  "epic_id": "bd-0012",
  "title": "Add rate limiting to /api/submit endpoint",
  "timestamp": "2026-03-08T14:23:00Z",
  "files_changed": ["src/app/api/submit.py", "tests/test_submit.py"],
  "review_findings_count": 2,
  "review_findings_resolved": 2,
  "validation_passed": true,
  "key_decisions": [
    "Used token bucket algorithm over sliding window — aligns with existing redis patterns",
    "Added rate limit headers per RFC 6585"
  ],
  "mistakes_caught": [
    "Initial implementation used in-memory counter — reviewer caught missing distributed state"
  ]
}
```

#### Procedural Memory (via `AGENTS.md`)

Rather than maintaining a separate procedural memory store, the substrate writes learned patterns directly to the project's `AGENTS.md` file. Agents already read `AGENTS.md` automatically on every invocation — this is how Claude Code, Claude Agent SDK agents, and similar tools consume project-level instructions. No new injection mechanism is needed.

**Section ownership model:**

The consolidation process owns a clearly delimited section of `AGENTS.md`. Human-authored content above the delimiter is never touched.

```markdown
# AGENTS.md

## Project Standards
... human-written rules, manually maintained ...

## Substrate: Learned Patterns
<!-- substrate:managed-start — content below is auto-updated by maverick substrate consolidate -->
<!-- last consolidated: 2026-03-08T18:00:00Z -->

### Implementation Patterns

- **Redis connections**: Always use `get_redis_pool()`, never standalone connections.
  Always set TTL on keys.
  *(Learned from: review findings in bd-a1b2, bd-c3d4, bd-e5f6)*

- **Test fixtures**: Prefer `factory_boy` factories over raw fixture functions.
  Use `conftest.py` per test directory, not a global conftest.
  *(Learned from: pattern observed across bd-0001 through bd-0020)*

### Anti-Patterns (things that failed in review)

- **Bare exceptions**: Do not use `raise Exception`. Use the `app.exceptions.AppError`
  hierarchy. All HTTP handlers must catch `AppError` and map to status codes.
  *(Learned from: review finding in bd-b2c3, reinforced in bd-d4e5)*

- **In-memory counters for distributed state**: Rate limiting, session counting, and
  similar features must use Redis, not in-memory dicts.
  *(Learned from: bd-a3f2 — reviewer caught missing distributed state)*

<!-- substrate:managed-end -->
```

**Key behaviors:**

- **Consolidation only writes between the markers.** Everything outside `substrate:managed-start` / `substrate:managed-end` is untouched.
- **First consolidation creates the markers.** If `AGENTS.md` exists but has no managed section, consolidation appends the delimited section. If `AGENTS.md` doesn't exist, consolidation creates it with the managed section.
- **Human deletions are respected.** If a user deletes a learned pattern from the managed section and commits, the consolidation agent sees the deletion in git history and does not re-add it. This is the "human override" mechanism.
- **Source attribution is mandatory.** Every learned pattern includes `*(Learned from: ...)*` with bead IDs, so users can trace why a rule exists and verify it.
- **Git provides full auditability.** `git log AGENTS.md` shows every learning event. `git diff HEAD~1 AGENTS.md` shows what the last consolidation changed. `git revert <sha>` undoes a bad learning.

### 4.3 Integration Surface: MCP Tool Server

The substrate is exposed to agents as an MCP tool server, consistent with Maverick's existing agent architecture. Agents interact with the substrate through tools — they do not read files directly.

**Tools provided:**

| Tool | Purpose | Used By |
|------|---------|---------|
| `substrate_query` | Retrieve relevant knowledge given a natural language query or structured filter | All agents |
| `substrate_get_recent_findings` | Retrieve review findings from recent beads, optionally filtered by file/module | Reviewer agents |
| `substrate_get_bead_history` | Retrieve outcomes of prior beads in the current epic | Implementer agents |

Note: there is no `substrate_get_procedures` tool. Procedural memory lives in `AGENTS.md`, which agents read automatically before invocation — no tool call needed.

**Tools NOT provided to agents (workflow-only):**

| Action | Purpose | Invoked By |
|--------|---------|------------|
| `substrate_record_bead_outcome` | Write episodic record after bead completion | `fly-beads` workflow action |
| `substrate_record_review_findings` | Write review findings after review step | Review workflow action |
| `substrate_record_fix_attempt` | Write fix attempt record after fix step | Fix workflow action |
| `substrate_consolidate` | Run consolidation process | Post-flight-plan workflow action |

This preserves the architectural guardrail: agents provide judgment, workflows own side effects.

### 4.4 Query and Retrieval

Retrieval uses a two-tier strategy:

**Tier 1 — Structured lookup (no LLM cost):**
- Filter episodic JSONL by `bead_id`, `epic_id`, file path, timestamp range
- Read specific semantic files by topic (architecture, conventions, contracts)

**Tier 2 — BM25 text search (no external infrastructure):**
- Full-text search across all Markdown files in the substrate
- Uses `rank-bm25` (pure Python, already compatible with Maverick's stack)
- Returns ranked passages with source file and line context
- Sufficient for v1; vector search can be added later without changing the interface

The `substrate_query` tool accepts a natural language query and returns a ranked set of passages from across all substrate files, combining structured filtering (if entity names or bead IDs are detected) with BM25 text search.

### 4.5 Consolidation Process

Consolidation is the mechanism by which raw episodic data is distilled into durable semantic and procedural knowledge. It runs as a dedicated workflow step, not continuously.

**When it runs:**
- After a flight plan completes (all beads in an epic are closed)
- Optionally: on `maverick refuel` as a maintenance step
- Manually: `maverick substrate consolidate`

**What it does:**

1. **Episodic → Semantic**: An agent reads recent episodic records and the current semantic files. It identifies new architectural facts, updated module relationships, or changed contracts, and proposes edits to the semantic Markdown files.

2. **Episodic → AGENTS.md (Procedural)**: The agent analyzes patterns in review findings and fix attempts. Recurring mistakes become anti-pattern warnings. Recurring successes become recommended patterns. The agent proposes updates to the `substrate:managed` section of `AGENTS.md`. Only content between the `substrate:managed-start` and `substrate:managed-end` markers is modified — human-authored sections are never touched.

3. **Human override detection**: Before writing to `AGENTS.md`, the consolidation agent checks git history for patterns that were previously written and then deleted by a human. Deleted patterns are recorded in `index.json` under `suppressed_patterns` and are not re-added in future consolidations.

4. **Pruning**: Facts in semantic files that contradict recent episodic evidence are flagged for removal or correction. Episodic records older than a configurable threshold (default: 90 days / 500 beads) are archived to `.maverick/substrate/archive/`.

5. **Index update**: The `index.json` file is refreshed with current entity lists, the consolidation timestamp, and the suppressed patterns list.

**Consolidation is itself an agent step** — it uses Claude to reason about what knowledge to extract and how to update the files. But the writes are executed by the workflow action, not the agent.

### 4.6 Concurrency Model

Maverick executes beads in parallel using jj worktrees. The substrate must handle concurrent reads and writes.

**Design:**
- **Reads are always safe** — each worktree has a snapshot of the substrate from its branch point
- **Writes are append-only to JSONL** — episodic records are appended, not edited in place. JSONL is merge-friendly: concurrent appends to different lines produce clean merges
- **Semantic files and AGENTS.md are only written during consolidation** — consolidation runs after flight plan completion, when parallel work has been merged. No concurrent writes to Markdown files.
- **Conflict resolution** — in the rare case of JSONL merge conflicts (identical line positions), jj's merge resolution or a simple "keep both" strategy applies, since each line is a self-contained record

This matches the existing `.beads/issues.jsonl` concurrency model, which has proven reliable.

---

## 5. User Interaction

### 5.1 Initialization

```bash
maverick init
# Existing behavior + creates .maverick/substrate/ with empty scaffolding

maverick substrate init
# Standalone: initializes substrate in an existing maverick project
```

On first `maverick fly` in a repo with no substrate, Maverick creates the scaffold automatically (zero-config start).

### 5.2 During `maverick fly`

No user interaction required. The substrate is read and written transparently by the workflow:

1. **Before each bead's implementation step**: Workflow queries substrate for relevant context (architecture of affected modules, prior findings for affected files) and injects it into the agent's system prompt. Procedural guidance is already available via `AGENTS.md`, which agents read automatically.

2. **After each bead completes**: Workflow writes the bead outcome to `episodic/bead-outcomes.jsonl`.

3. **After each review step**: Workflow writes findings to `episodic/review-findings.jsonl`.

4. **After flight plan completes**: Consolidation step runs.

### 5.3 Manual Inspection

The substrate is human-readable by design:

```bash
# Read current architectural knowledge
cat .maverick/substrate/semantic/architecture.md

# See what agents have learned (procedural memory)
cat AGENTS.md

# See recent bead outcomes
tail -20 .maverick/substrate/episodic/bead-outcomes.jsonl | jq .

# See how knowledge evolved
git log --oneline .maverick/substrate/ AGENTS.md

# See what changed in last consolidation
git diff HEAD~1 .maverick/substrate/semantic/ AGENTS.md
```

### 5.4 Manual Override

Users can edit any substrate file directly — they're just Markdown and JSONL. For procedural memory, users edit `AGENTS.md` directly: delete a learned pattern from the managed section and commit, and consolidation will not re-add it (see Section 4.5, human override detection). Move a learned pattern from the managed section into the human-authored section to "promote" it to a permanent rule that consolidation can never overwrite.

### 5.5 CLI Commands

| Command | Purpose |
|---------|---------|
| `maverick substrate init` | Initialize substrate in current project |
| `maverick substrate status` | Show substrate statistics (file count, last consolidated, episodic record count) |
| `maverick substrate consolidate` | Manually trigger consolidation |
| `maverick substrate query "<question>"` | Ad-hoc query for debugging/inspection |

---

## 6. Data Model

### 6.1 Episodic Records

**BeadOutcome** (appended to `episodic/bead-outcomes.jsonl`):

| Field | Type | Description |
|-------|------|-------------|
| `bead_id` | string | Bead identifier (e.g., `bd-a3f2`) |
| `epic_id` | string | Parent epic identifier |
| `flight_plan` | string | Flight plan name |
| `title` | string | Bead title |
| `timestamp` | ISO 8601 | Completion timestamp |
| `files_changed` | string[] | Files modified by this bead |
| `review_findings_count` | int | Number of review findings raised |
| `review_findings_resolved` | int | Number resolved before close |
| `validation_passed` | bool | Whether validation succeeded |
| `key_decisions` | string[] | Notable implementation decisions |
| `mistakes_caught` | string[] | Issues caught by review/validation |

**ReviewFinding** (appended to `episodic/review-findings.jsonl`):

| Field | Type | Description |
|-------|------|-------------|
| `finding_id` | string | Unique finding identifier |
| `bead_id` | string | Bead under review |
| `reviewer` | string | Agent role that raised it |
| `severity` | enum | `critical`, `major`, `minor`, `suggestion` |
| `category` | string | e.g., `security`, `correctness`, `style`, `architecture` |
| `file_path` | string | Primary file affected |
| `description` | string | Finding description |
| `resolution` | enum | `fixed`, `deferred`, `wont_fix`, `duplicate` |
| `resolution_notes` | string | How/why resolved |
| `timestamp` | ISO 8601 | When finding was raised |

**FixAttempt** (appended to `episodic/fix-attempts.jsonl`):

| Field | Type | Description |
|-------|------|-------------|
| `attempt_id` | string | Unique attempt identifier |
| `finding_id` | string | Finding being addressed |
| `bead_id` | string | Bead performing the fix |
| `approach` | string | What was tried |
| `succeeded` | bool | Whether the fix resolved the finding |
| `failure_reason` | string | null | Why it failed (if applicable) |
| `timestamp` | ISO 8601 | When attempt was made |

### 6.2 Index

**`index.json`**:

```json
{
  "version": 1,
  "last_consolidated": "2026-03-08T18:00:00Z",
  "entities": [
    {"name": "auth module", "type": "module", "file": "semantic/architecture.md"},
    {"name": "redis", "type": "dependency", "file": "semantic/dependencies.md"}
  ],
  "episodic_counts": {
    "bead_outcomes": 47,
    "review_findings": 123,
    "fix_attempts": 31
  },
  "suppressed_patterns": [
    {
      "pattern_hash": "a1b2c3d4",
      "description": "Prefer dataclasses over NamedTuple",
      "suppressed_at": "2026-03-07T10:00:00Z",
      "reason": "Human deleted from AGENTS.md managed section"
    }
  ]
}
```

---

## 7. Integration Points with Existing Maverick Architecture

### 7.1 Workflow Integration (`fly-beads`)

The `FlyBeadsWorkflow` gains three new actions:

| Action | When | What |
|--------|------|------|
| `inject_substrate_context` | Before `execute_agent` for implementation | Queries substrate, adds relevant semantic/episodic passages to agent's context |
| `record_bead_outcome` | After bead close | Writes `BeadOutcome` to episodic JSONL |
| `consolidate_substrate` | After epic completion | Runs consolidation agent step; updates semantic files and `AGENTS.md` managed section |

### 7.2 Review Integration

The review workflow fragment gains:

| Action | When | What |
|--------|------|------|
| `inject_prior_findings` | Before reviewer agent | Queries substrate for prior findings on affected files |
| `record_review_findings` | After review merge | Writes `ReviewFinding` records to episodic JSONL |
| `record_fix_attempt` | After each fix iteration | Writes `FixAttempt` to episodic JSONL |

### 7.3 Agent Registration

The substrate MCP server is registered in the agent registry alongside existing tool servers. Agents that should have substrate access declare it in their tool configuration:

```python
SUBSTRATE_READ_TOOLS = [
    "substrate_query",
    "substrate_get_recent_findings",
    "substrate_get_bead_history",
]
# Note: procedural memory is delivered via AGENTS.md, not a substrate tool.
# Agents read AGENTS.md automatically — no tool call or explicit injection needed.
```

### 7.4 Configuration

```yaml
# maverick.yaml
substrate:
  enabled: true                    # default: true
  path: .maverick/substrate        # default
  consolidation:
    auto: true                     # consolidate after flight plan completion
    max_episodic_age_days: 90      # archive threshold
    max_episodic_records: 500      # archive threshold
  retrieval:
    max_passages: 10               # max passages returned per query
    bm25_top_k: 20                 # BM25 candidates before re-ranking
```

---

## 8. Phased Delivery

### Phase 1: Foundation (MVP)

**Scope**: Storage layout, episodic recording, basic retrieval, workflow integration.

- Create `.maverick/substrate/` scaffolding on `maverick init`
- Implement `SubstrateStore` — read/write Pydantic models to JSONL and Markdown
- Implement `record_bead_outcome` and `record_review_findings` workflow actions
- Implement `substrate_query` with BM25 retrieval over all substrate files
- Integrate into `fly-beads`: record outcomes after each bead
- Add `maverick substrate init` and `maverick substrate status` CLI commands
- Write substrate files to git as part of bead commit

**Deliverables**: Agents don't use the substrate yet, but it accumulates data. Humans can inspect it.

### Phase 2: Context Injection

**Scope**: Agents receive substrate context. Read path is live.

- Implement `SubstrateMCPServer` with read-only tools
- Implement `inject_substrate_context` workflow action — queries substrate and adds to agent system prompt
- Implement `inject_prior_findings` for reviewer agents
- Register substrate tools in agent configurations
- Measure token impact and tune `max_passages`

**Deliverables**: Agents make decisions informed by prior bead outcomes and accumulated knowledge.

### Phase 3: Consolidation and Procedural Learning

**Scope**: Episodic data is distilled into durable knowledge. Agents get better over time.

- Implement consolidation agent step (episodic → semantic, episodic → `AGENTS.md`)
- Implement `substrate:managed-start` / `substrate:managed-end` section management in `AGENTS.md`
- Implement human override detection (respect deletions from managed section)
- Implement `suppressed_patterns` tracking in `index.json`
- Implement pruning and archival of old episodic records
- Implement `maverick substrate consolidate` CLI command
- Integrate consolidation as post-flight-plan step

**Deliverables**: The substrate evolves. Learned patterns appear in `AGENTS.md` automatically. Reviewer agents stop flagging resolved patterns. Implementer agents avoid previously-caught mistakes. No new injection mechanism — agents pick up learned patterns for free because they already read `AGENTS.md`.

### Phase 4: Advanced Retrieval and Observability

**Scope**: Richer queries, metrics, optional semantic search.

- Add optional sentence-transformer embedding for semantic search (opt-in, not required)
- Add `maverick substrate query` CLI for ad-hoc queries
- Add substrate health metrics to `maverick substrate status` (staleness, coverage, finding recurrence rate)
- Add substrate diff view to `maverick land` output — show what knowledge was gained in this flight plan

---

## 9. Success Criteria

| ID | Metric | Target |
|----|--------|--------|
| SC-1 | Duplicate review findings (same finding on same pattern across beads) | Reduce by ≥50% vs. no-substrate baseline |
| SC-2 | Fix attempt count per finding (fewer wasted attempts) | Reduce average from current to ≤1.5 attempts |
| SC-3 | Substrate query latency | <500ms p95 for BM25 retrieval |
| SC-4 | Token overhead per agent invocation from substrate context | <2,000 tokens average |
| SC-5 | Zero external infrastructure required | No databases, no servers, no API keys beyond Claude |
| SC-6 | Substrate data survives branch/merge operations | JSONL merge conflicts in <1% of merges |

---

## 10. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Substrate files grow too large for git comfort | Medium | Medium | Archival of old episodic records; keep semantic files focused (split when >500 lines) |
| Consolidation agent produces incorrect knowledge | Medium | High | Semantic files are human-reviewable Markdown; `AGENTS.md` changes are visible in `git diff`; users delete bad patterns from managed section and they stay suppressed; consolidation runs as a reviewable commit |
| Context injection bloats agent prompts | Medium | Medium | Hard cap on injected tokens (`max_passages`); selective retrieval, not context dumping |
| JSONL merge conflicts in parallel beads | Low | Low | Each record is one line; concurrent appends to different lines merge cleanly; worst case: keep-both |
| BM25 retrieval quality insufficient | Medium | Low | BM25 is the floor; architecture supports adding vector search in Phase 4 without interface changes |
| Substrate becomes stale if consolidation doesn't run | Medium | Medium | Auto-consolidation after flight plans; staleness warning in `substrate status`; manual trigger available |

---

## 11. Dependencies

| Dependency | Status | Notes |
|------------|--------|-------|
| `rank-bm25` (Python package) | Available on PyPI | Pure Python, no native deps, ~50KB |
| `fly-beads` workflow actions | Exists | New actions added alongside existing ones |
| Review workflow fragment | Exists | New recording actions added |
| `maverick init` | Exists | Extended to scaffold substrate directory |
| Agent registry | Exists | Substrate MCP server registered like any other |
| jj worktree concurrency | Exists | JSONL append model is worktree-compatible |

No new infrastructure. No new external services. No new runtime dependencies beyond `rank-bm25`.

---

## Appendix A: Research Bibliography

1. **Letta Context Repositories** — "Introducing Context Repositories: Git-based Memory for Coding Agents" (2025). https://www.letta.com/blog/context-repositories

2. **DiffMem** — "Git Based Memory Storage for Conversational AI Agent" (2025). https://github.com/Growth-Kinetics/DiffMem

3. **A-MEM** — Xu et al., "A-MEM: Agentic Memory for LLM Agents," NeurIPS 2025. https://arxiv.org/abs/2502.12110

4. **Graphiti/Zep** — Rasmussen et al., "Zep: A Temporal Knowledge Graph Architecture for Agent Memory" (2025). https://arxiv.org/abs/2501.13956

5. **Anthropic Context Engineering** — "Effective context engineering for AI agents," Anthropic Engineering Blog (2025). https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

6. **LangMem** — "Long-term Memory in LLM Applications," LangChain (2025). https://langchain-ai.github.io/langmem/concepts/conceptual_guide/

7. **Cognee** — "How Cognee Builds AI Memory for Agents" (2025). https://www.cognee.ai/blog/fundamentals/how-cognee-builds-ai-memory

8. **Anthropic MCP Memory Server** — Model Context Protocol Knowledge Graph Memory Server. https://github.com/modelcontextprotocol/servers/tree/main/src/memory

9. **Manus Context Engineering** — "Context Engineering for AI Agents: Lessons from Building Manus" (2025). https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus

10. **MIRIX** — Wang & Chen, "MIRIX: Multi-Agent Memory System for LLM-Based Agents" (2025). https://arxiv.org/pdf/2507.07957

## Appendix B: Glossary

| Term | Definition |
|------|-----------|
| **Substrate** | The persistent, git-committed knowledge store that provides context continuity across agent invocations |
| **Semantic memory** | Facts about the repository's current state — architecture, contracts, dependencies, conventions |
| **Episodic memory** | Records of specific events — bead outcomes, review findings, fix attempts |
| **Procedural memory** | Learned behavioral guidance written to the `substrate:managed` section of `AGENTS.md`, which agents read automatically |
| **Consolidation** | The process of distilling episodic records into semantic knowledge and `AGENTS.md` updates |
| **Context injection** | The workflow action that queries the substrate and adds relevant semantic/episodic passages to an agent's input |
| **Managed section** | The delimited region of `AGENTS.md` between `substrate:managed-start` and `substrate:managed-end` markers, owned by the consolidation process |
| **Human override** | Deleting a learned pattern from the managed section of `AGENTS.md`; consolidation respects this and will not re-add the pattern |
| **BM25** | A probabilistic text retrieval algorithm; lightweight, no infrastructure required |
