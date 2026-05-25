# Maverick

AI-powered development workflow orchestration. Point your AI agents at a
flight plan and let them fly — Maverick handles implementation, code review,
spec compliance, human escalation, and commit curation autonomously.

## What is Maverick?

Maverick is a Python CLI that orchestrates the complete development lifecycle
on top of [airframe](https://github.com/get2knowio/airframe), a vendor-neutral
agent runtime protocol. From a PRD, it generates a flight plan, decomposes it
into work units, implements them with AI agents, validates against project
conventions, reviews code, escalates to humans when needed, and curates clean
commit history — all driven by a **bead-based work graph** where humans and
agents create work for each other.

**Core idea**: Everything is a bead. A bead is a unit of work managed by the
`bd` CLI tool. Implementation beads, review findings, human escalations, and
correction tasks all live in the same dependency graph.

### Key Features

- **Full PRD-to-code pipeline** — `plan` generates a flight plan, `refuel`
  decomposes into work units with acceptance criteria, `fly` implements and
  validates, `land` curates commits and merges
- **Deterministic spec compliance** — Grep-based convention checker catches
  `unwrap()` in runtime code, blocking `std::process::Command` in async
  functions, and other project-specific anti-patterns before review
- **Enriched code review** — Reviewer agents receive the full work unit spec
  (acceptance criteria, file scope), pre-flight briefing (contrarian findings,
  risk assessment), and runway historical context
- **Post-flight aggregate review** — After all beads complete, a cross-bead
  review checks architectural coherence and dead code across the full diff
- **Human-in-the-loop via assumption beads** — When agents exhaust fix
  attempts, they create human-assigned review beads with full escalation
  context. Humans review via `maverick review` (approve/reject/defer) and
  correction beads flow back to agents. Works from a phone terminal.
- **Continuous fly mode** — `maverick fly --watch` polls for new beads,
  enabling concurrent `plan`/`refuel` in another terminal while fly
  continuously drains work
- **Cross-epic dependency wiring** — New epics automatically depend on
  existing open epics, serializing execution while allowing tasks within
  each epic to parallelize
- **Multi-provider routing** — Each of the five canonical roles
  (`implement`, `review`, `briefing`, `decompose`, `generate`) binds to one
  airframe-supported provider + model in `maverick.yaml`. Airframe ships
  adapters for `claude`, `github-copilot`, `opencode`, `opencode-go`,
  `opencode-zen`, `openrouter`, and `bedrock` — each speaks its native
  vendor SDK directly (OAuth for Claude Max, copilot CLI, API keys
  elsewhere). Misconfigured bindings fail at squadron-open with a clear
  `UnsupportedBindingError`, not mid-workflow.
- **Runway knowledge store** — Episodic records of bead outcomes, review
  findings, and fix attempts build project-specific context. Agents
  progressively discover this context via the `.maverick/runway/` directory
- **xoscar actor system** — All workflows run on a single xoscar pool
  (`n_process=0`, in-pool coroutines). The workflow's `Squadron` constructs
  one `airframe.AgentRuntime` per role at startup, validates every binding
  against the adapter, and shares that fleet across mailbox actors.
- **Jujutsu (jj) VCS** — Write operations use jj for snapshot/rollback
  safety. Curation skips immutable commits gracefully.

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — Fast Python package manager
- [GitHub CLI](https://cli.github.com/) (`gh`)
- [Jujutsu](https://martinvonz.github.io/jj/) (`jj`)
- [bd](https://beads.dev/) for bead/work-item management
- Authentication for at least one airframe-supported provider:
  - **claude** — Claude Max subscription OAuth (`~/.claude/.credentials.json`),
    or `ANTHROPIC_API_KEY`
  - **github-copilot** — GitHub Copilot subscription via the `gh copilot` CLI
  - **opencode-go** / **opencode-zen** — `opencode auth login <provider>`
  - **openrouter** — `OPENROUTER_API_KEY`
  - **bedrock** — AWS credentials + `AWS_REGION`
- Git repository with remote origin

### Installation

```bash
uv tool install maverick-cli
```

Or from the repository:

```bash
uv tool install git+https://github.com/get2knowio/maverick.git
```

### The Pipeline

```bash
# 1. Initialize the project
maverick init

# 2. Seed the runway with codebase knowledge
maverick runway seed

# 3. Generate a flight plan from a PRD
maverick plan generate my-feature --from-prd spec.md

# 4. Decompose into work units and create beads
maverick refuel my-feature

# 5. Implement beads (in isolated workspace)
maverick fly --epic <epic-id> --auto-commit

# 6. Review any human-escalated beads
maverick brief --human
maverick review <bead-id>

# 7. Curate history and merge
maverick land --yes
```

### Continuous Mode

Run fly as a long-lived daemon while adding work from another terminal:

```bash
# Terminal 1: fly drains beads continuously
maverick fly --watch --auto-commit

# Terminal 2: keep adding work
maverick plan generate feature-2 --from-prd feature-2.md
maverick refuel feature-2

# Terminal 3: review escalations
maverick brief --human
maverick review <bead-id> --reject "use tokio::process::Command instead"
```

## Commands

### `maverick plan generate` — Flight Plan from PRD

Runs a Pre-Flight Briefing Room — four parallel AI agents analyze the PRD,
then a generator synthesizes a flight plan with success criteria and scope.

| Agent | Role |
|-------|------|
| **Scopist** | Defines scope boundaries |
| **Codebase Analyst** | Maps relevant modules and patterns |
| **Criteria Writer** | Drafts acceptance criteria |
| **Contrarian** | Identifies risks and blind spots |

```bash
maverick plan generate my-feature --from-prd spec.md
maverick plan generate my-feature --from-prd spec.md --skip-briefing
```

### `maverick refuel` — Decompose into Beads

Decomposes a flight plan into work units with acceptance criteria, file scope,
and verification commands. Creates epic + task beads via `bd`. New epics
automatically chain behind existing open epics.

```bash
maverick refuel my-feature
maverick refuel my-feature --skip-briefing
maverick refuel my-feature --dry-run
```

### `maverick fly` — Bead-Driven Development

Iterates over ready beads. For each bead:

```
Implement → Gate (fmt/lint/test) → AC Check → Spec Check → Review → Commit
     ↑                                              |
     └──── Fix (if rejected, up to 3 rounds) ───────┘
     
If fix attempts exhausted → escalate to human (assumption bead)
                          → commit optimistically → continue
```

After all beads: aggregate cross-bead review, then report with structured
per-bead events and `ACTION REQUIRED` for any `needs-human-review` beads.

| Flag | Default | Description |
|------|---------|-------------|
| `--epic <id>` | (any) | Filter to beads under this epic |
| `--max-beads <n>` | 30 | Maximum beads to process |
| `--watch` | false | Poll for new beads when queue is empty |
| `--watch-interval <s>` | 30 | Seconds between polls |
| `--auto-commit` | false | Auto-commit uncommitted changes |
| `--skip-review` | false | Skip code review step |
| `--dry-run` | false | Preview mode |

### `maverick land` — Curate and Merge

AI curator reorganizes commits — squashes fix commits, strips bead IDs,
writes conventional commit messages, reorders for logical flow. Skips
immutable commits gracefully. Consolidates runway after merge.

```bash
maverick land --yes              # Curate + merge + cleanup
maverick land --dry-run          # Show plan only
maverick land --no-curate        # Skip curation, just merge
maverick land --heuristic-only   # Keyword-based curation (no agent)
```

### `maverick review` — Human Decision Capture

Lightweight review of human-assigned assumption beads. Displays escalation
context and captures a decision: approve, reject (with guidance), or defer.
Rejection spawns a correction bead back into the agent pipeline.

```bash
maverick brief --human                              # See the queue
maverick review <bead-id>                           # Interactive
maverick review <bead-id> --approve                 # Scriptable
maverick review <bead-id> --reject "use Dockerfile" # With guidance
```

### `maverick brief` — Bead Dashboard

```bash
maverick brief                   # All ready/blocked beads
maverick brief --epic <id>       # Children of an epic
maverick brief --human           # Human review queue only
maverick brief --watch           # Live polling
maverick brief --format json     # JSON output
```

### `maverick runway` — Knowledge Store

```bash
maverick runway init             # Initialize the store
maverick runway seed             # AI-generated codebase analysis
maverick runway status           # Show metrics
maverick runway consolidate      # Distill old records into summaries
```

The runway records bead outcomes, review findings, and fix attempts as JSONL.
Agents discover this context progressively via the `.maverick/runway/`
directory. Consolidation (automatic during `land`) distills episodic records
into semantic summaries.

### `maverick init` — Project Setup

Initializes `maverick.yaml`, probes installed airframe adapters via
`runtime.list_models()` to discover which providers are authenticated,
and writes a starter `agents:` block binding the five canonical roles
(`implement`, `review`, `briefing`, `decompose`, `generate`).

```bash
maverick init                                        # auto-detect
maverick init --providers claude,opencode-go         # narrow the spread
maverick init --models claude:claude-sonnet-4-6      # pin per-provider models
```

## Configuration

```yaml
project_type: rust

github:
  owner: your-org
  repo: your-repo
  default_branch: main

validation:
  format_cmd: [cargo, fmt]
  lint_cmd: [cargo, clippy, --fix, --allow-dirty]
  test_cmd: [make, test-nextest-fast]
  timeout_seconds: 600

# One airframe binding per canonical role. Provider IDs come from
# airframe.list_providers(); model IDs are whatever that adapter's
# list_models() returns. Bindings are validated at squadron-open —
# misconfigurations fail fast.
agents:
  implement:
    provider: claude
    model_id: claude-sonnet-4-6
  review:
    provider: claude
    model_id: claude-haiku-4-5
  briefing:
    provider: opencode-go
    model_id: minimax-m2.7
  decompose:
    provider: claude
    model_id: claude-sonnet-4-6
  generate:
    provider: github-copilot
    model_id: gpt-5-mini

# Per-complexity overrides for a specific actor still work — they take
# priority over the role binding for that (workflow, actor, tier).
actors:
  fly:
    implementer:
      tiers:
        complex:
          provider: claude
          model_id: claude-opus-4-7
```

## Architecture

```
CLI (Click)
  │
Workflow Layer (async Python)
  │ Resolves cwd at the entry boundary and threads it down.
  │
Squadron (per-workflow lifecycle container)
  │ Constructs one airframe.AgentRuntime per role via runtime_for_agent(),
  │ runs validate_binding() at open, exposes the typed agents to actors.
  │
xoscar Actor Layer (in-pool coroutines, n_process=0, ephemeral 127.0.0.1:0)
  │
  ├── Supervisors (typed RPC fan-out)
  │   FlySupervisor, RefuelSupervisor, PlanSupervisor
  │
  ├── Mailbox actors (each owns an Agent instance)
  │   ImplementerActor, ReviewerActor, DecomposerActor,
  │   GeneratorActor, BriefingActor
  │
  └── Deterministic actors (pure Python, no LLM)
      Gate, SpecCheck, ACCheck, Committer, Validator
  │
airframe Pattern D runtime (one AgentRuntime per role)
  ClaudeCodeRuntime, CopilotRuntime, OpenCodeRuntime,
  OpenCodeGoRuntime, OpenCodeZenRuntime, OpenRouterRuntime,
  BedrockRuntime — each fronts its vendor SDK directly.
```

### How Agents Communicate

Each mailbox actor holds an `Agent` instance built around the
role's `AgentRuntime`. Domain methods (`coder.implement(prompt, *,
bead_id)`) call `_send_structured(prompt)`, which invokes
`runtime.execute()` with `format=json_schema` derived from the agent's
`result_model`. Airframe synthesizes a `StructuredOutput` tool the model
is forced to call, normalises any vendor-specific envelope wrapping, and
validates the result against the Pydantic model. The typed payload
flows back to the supervisor via xoscar RPC. Built-in tools (Read,
Write, Bash) are for doing work; the `StructuredOutput` tool is for
reporting results.

## Technology Stack

| Category | Technology |
|----------|-----------|
| Language | Python 3.11+ |
| Package Manager | uv |
| Agent Runtime | [airframe](https://github.com/get2knowio/airframe) Pattern D — one `AgentRuntime` per role |
| Actor Framework | xoscar (`n_process=0`, in-pool coroutines) |
| Structured Output | Pydantic + `format=json_schema` (via airframe `StructuredOutput`) |
| CLI | Click + Rich |
| VCS (writes) | Jujutsu (jj) in colocated mode |
| VCS (reads) | GitPython |
| Logging | structlog |
| Testing | pytest + pytest-asyncio |
| Linting | Ruff |

## Development

```bash
git clone https://github.com/get2knowio/maverick.git
cd maverick
uv sync
make check           # lint + format + test
make ci-coverage     # Full CI pipeline
uv run maverick --help
```

## License

MIT
