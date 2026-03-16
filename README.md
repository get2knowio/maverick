# Maverick

Point your AI agents at a task list and let them fly. Maverick orchestrates
implementation, code review, fixes, and PR creation — the full development
lifecycle on autopilot.

## What is Maverick?

Maverick is a Python CLI application that orchestrates AI-powered development
workflows using the Agent Client Protocol (ACP). It automates the complete
development lifecycle — from PRD decomposition through implementation,
validation, code review, and commit management — using a **bead-driven**
execution model.

**Core idea**: Everything is a bead. A bead is a unit of work managed by the
`bd` CLI tool. The implementer agent doesn't know or care whether it's building
a feature, fixing a lint error, or addressing a review finding — the bead
description tells it what to do.

### Key Features

- **Full PRD-to-code pipeline** — Generate flight plans from PRDs, decompose
  into work units, create beads, implement, review, and ship
- **Bead-driven workflows** — All work is tracked as beads with dependencies,
  priorities, and lifecycle management via `bd`
- **Autonomous AI agents** — Agents make decisions, implement code, review
  changes, and recover from failures via ACP subprocess communication
- **Pre-Flight Briefing Room** — Parallel AI analysis (scopist, codebase
  analyst, criteria writer, contrarian) before plan generation and refueling
- **Jujutsu (jj) VCS** — Write-path VCS operations use jj in colocated mode for
  snapshot/rollback safety; GitPython handles read-only operations
- **Workspace isolation** — All fly work happens in a hidden
  `~/.maverick/workspaces/` clone; your working directory stays untouched
- **Runway knowledge store** — Episodic records of bead outcomes, review
  findings, and fix attempts build project-specific context over time
- **Resilient operation** — Automatic retries, validation-fix loops,
  review-fix cycles, and bead-level rollback on failure

## Quick Start

### Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) — Fast Python package manager (recommended)
- [GitHub CLI](https://cli.github.com/) (`gh`) for PR and issue management
- [Jujutsu](https://martinvonz.github.io/jj/) (`jj`) for VCS write operations
- [bd](https://beads.dev/) for bead/work-item management
- [claude-agent-acp](https://www.npmjs.com/package/@anthropic-ai/claude-agent-acp) — ACP agent subprocess
- Claude API access (set `ANTHROPIC_API_KEY` environment variable)
- Git repository with remote origin (jj runs in colocated mode)

### Installation

```bash
uv tool install maverick-cli
```

That's it. `maverick` lands on your PATH in its own isolated environment.

Alternatively, install from the repository:

```bash
uv tool install git+https://github.com/get2knowio/maverick.git
```

### Basic Usage

```bash
# Full PRD-to-code pipeline:
# 1. Generate a flight plan from a PRD
maverick plan generate my-feature --from-prd specs/my-feature/spec.md

# 2. Validate the generated plan
maverick plan validate my-feature

# 3. Decompose into work units and create beads
maverick refuel my-feature

# 4. Implement beads (in isolated workspace)
maverick fly --epic <epic-id> --max-beads 5

# 5. Curate history and merge into local repo
maverick land

# Alternative: create beads from a SpecKit specification
maverick refuel --from speckit 001-my-feature

# Other commands
maverick fly --skip-review --max-beads 5
maverick land --dry-run
maverick brief                  # Review queued beads
maverick brief --watch          # Live polling while fly runs
maverick runway seed            # Analyze codebase for runway context
maverick init                   # Initialize a new project
```

## Workflows

Maverick uses a beads-only workflow model. All development is driven by beads
(units of work managed by the `bd` CLI tool). Workflows are implemented as
Python async classes under `src/maverick/workflows/`.

### The PRD-to-Code Pipeline

The full pipeline takes a product requirements document and turns it into
shipped code:

```
PRD ──▶ plan generate ──▶ plan validate ──▶ refuel ──▶ fly ──▶ land
```

1. **Plan** — A Pre-Flight Briefing Room runs four parallel AI analysts, then a
   generator synthesizes the output into a phased flight plan
2. **Refuel** — Decomposes the plan into beads with dependencies wired up
3. **Fly** — Bead loop: implement → validate → review → fix → commit → next
4. **Land** — AI curator reorganizes commits, merges into your local repo

### `maverick plan generate` — Plan from PRD

Generates a flight plan from a product requirements document (PRD). Runs a
**Pre-Flight Briefing Room** — four parallel AI agents analyze the PRD before
a generator agent synthesizes the plan:

| Agent | Role |
|-------|------|
| **Scopist** | Defines scope boundaries, in/out decisions |
| **Codebase Analyst** | Maps relevant modules, patterns, dependencies |
| **Criteria Writer** | Drafts acceptance criteria and test scenarios |
| **Contrarian** | Identifies risks, blind spots, and over-engineering |

```bash
maverick plan generate my-feature --from-prd specs/my-feature/spec.md
```

### `maverick plan validate` — Validate Plan

Validates a generated flight plan for structural correctness.

```bash
maverick plan validate my-feature
```

### `maverick plan create` — Create Plan from Template

Creates a new flight plan file from a template for manual authoring.

```bash
maverick plan create my-feature
```

### `maverick refuel` — Decompose into Beads

Decomposes a flight plan into work units and creates beads. All artifacts
are stored in `.maverick/plans/<name>/`. Also runs a briefing room to
inform the decomposition.

Use `--from speckit` to load from a SpecKit specification instead.

```bash
maverick refuel my-feature
maverick refuel my-feature --dry-run
maverick refuel my-feature --skip-briefing
maverick refuel --from speckit 001-my-feature
```

### `maverick fly` — Bead-Driven Development

The primary execution command. Iterates over ready beads until done:

```
preflight ──▶ create_workspace ──▶ bead loop
                                      │
                                      ├── select next ready bead
                                      ├── snapshot (jj operation for rollback)
                                      ├── describe_change (bead → change description)
                                      ├── implement (ImplementerAgent via ACP)
                                      ├── sync_deps (install/update dependencies)
                                      ├── validate & fix (format/lint/typecheck/test, 3 attempts)
                                      ├── create fix beads (for remaining failures)
                                      ├── review & fix (UnifiedReviewerAgent, 2 cycles)
                                      ├── create review beads (for remaining findings)
                                      ├── verify completion gate
                                      ├── rollback on failure / commit on success
                                      ├── record runway data (outcome, review findings)
                                      ├── close bead
                                      └── check_done (exit or next bead)
```

After `fly` finishes, run `maverick land` to curate history and merge.

| Flag | Default | Description |
|------|---------|-------------|
| `--epic <id>` | (any) | Filter to beads under this epic |
| `--max-beads <n>` | 30 | Maximum beads to process |
| `--dry-run` | false | Preview mode — skip git and bd mutations |
| `--skip-review` | false | Skip code review step |
| `--auto-commit` | false | Auto-commit uncommitted changes before cloning workspace |
| `--list-steps` | false | List workflow steps and exit |
| `--session-log <path>` | (none) | Write session journal (JSONL) |

**How failures become beads**: When validation or review finds issues that can't
be auto-fixed, new beads are created under the same epic with high priority.
The outer loop picks them up on the next iteration.

### `maverick land` — Finalize and Ship

Curate commit history and merge into your local repo after `maverick fly`
completes. Uses an AI agent to intelligently reorganize commits (squash fix
commits, improve messages, reorder for logical flow), with user approval
before applying changes.

```bash
maverick land                    # Agent-curated history + merge
maverick land --dry-run          # Show plan without applying
maverick land --heuristic-only   # Heuristic curation (no agent)
maverick land --no-curate        # Skip curation, just merge
maverick land --yes              # Auto-approve the plan
maverick land --base develop     # Custom base revision
```

Three modes of operation:

| Mode | Command | Behavior |
|------|---------|----------|
| **Approve** (default) | `maverick land` | Curate → user approval → merge into local repo → cleanup workspace |
| **Eject** | `maverick land --eject` | Curate → create local preview branch → keep workspace |
| **Finalize** | `maverick land --finalize` | Merge preview branch → cleanup workspace |

| Flag | Default | Description |
|------|---------|-------------|
| `--no-curate` | false | Skip curation, just merge |
| `--dry-run` | false | Show plan without executing |
| `--yes` / `-y` | false | Auto-approve curation plan |
| `--base <rev>` | main | Base revision for curation scope |
| `--heuristic-only` | false | Use heuristic curation (no agent) |
| `--eject` | false | Create local preview branch, keep workspace |
| `--finalize` | false | Merge preview branch, cleanup workspace |
| `--no-consolidate` | false | Skip runway consolidation |
| `--branch <name>` | `maverick/<project>` | Custom branch name |

### `maverick brief` — Bead Dashboard

Review ready and blocked beads before starting a fly session. Use `--watch` for
live polling while `maverick fly` runs in another terminal.

### `maverick runway` — Knowledge Store

Manage the runway knowledge store — episodic records of bead outcomes, review
findings, and fix attempts that build project-specific context over time.

```bash
maverick runway init             # Initialize the runway store
maverick runway status           # Show store status and metrics
maverick runway seed             # AI-generated codebase analysis
maverick runway seed --dry-run   # Preview what would be generated
maverick runway consolidate      # Distill old records into summaries
maverick runway consolidate --force  # Run even if below thresholds
```

The `seed` command analyzes a brownfield codebase and pre-populates the runway
with architectural insights, making agents more effective from the first bead.

The `consolidate` command distills old episodic records into a semantic
`consolidated-insights.md` summary using an AI agent, then prunes the JSONL
files to keep only recent records. This runs automatically during
`maverick land` (disable with `--no-consolidate`) and can also be triggered
manually.

### `maverick init` — Project Setup

Initialize a new Maverick project with configuration files.

### `maverick workspace` — Workspace Management

Manage the hidden workspace used by `maverick fly`. The workspace lives in
`~/.maverick/workspaces/<project>/` and is a jj-colocated clone of your repo.

```bash
maverick workspace status           # Show workspace state for current project
maverick workspace clean            # Remove workspace for current project
maverick workspace clean --yes      # Skip confirmation prompt
```

## Architecture

Maverick follows a clean separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│  CLI Layer (Click + Rich)                                   │
│  maverick fly, refuel, plan, init, brief, land, runway      │
└─────────────────────────────────────────────────────────────┘
                          |
┌─────────────────────────────────────────────────────────────┐
│  Workflow Layer (Python async)                              │
│  FlyBeadsWorkflow, GenerateFlightPlanWorkflow,              │
│  RefuelMaverickWorkflow, RefuelSpeckitWorkflow              │
│  (orchestration, state management, bead lifecycle)          │
└─────────────────────────────────────────────────────────────┘
                          |
┌─────────────────────────────────────────────────────────────┐
│  ACP Executor Layer (Agent Client Protocol)                 │
│  MaverickAcpExecutor — spawns claude-agent-acp subprocess,  │
│  streams output, extracts structured JSON with schema       │
│  coercion and truncation repair                             │
└─────────────────────────────────────────────────────────────┘
                          |
┌─────────────────────────────────────────────────────────────┐
│  Agent Layer                                                │
│  ImplementerAgent, UnifiedReviewerAgent, FixerAgent,        │
│  CuratorAgent, PreFlight Briefing agents, Generators        │
│  (system prompts, tool selection, autonomous decisions)      │
└─────────────────────────────────────────────────────────────┘
                          |
┌─────────────────────────────────────────────────────────────┐
│  Tool & Runner Layer                                        │
│  MCP tools, CommandRunner, jj actions, GitPython,           │
│  PyGithub, validation runners, notifications                │
└─────────────────────────────────────────────────────────────┘
```

### Separation of Concerns

- **Agents** know HOW to do a task — system prompts, tool selection, structured
  output schemas. They provide judgment (implementation, review, fix suggestions).
- **Workflows** know WHAT to do and WHEN — orchestration, state management,
  sequencing. They own deterministic side effects (commits, validation, retries).
- **ACP Executor** bridges agents and workflows — spawns agent subprocesses via
  the Agent Client Protocol, streams conversational output for display, and
  extracts structured JSON from agent responses with schema coercion and
  truncation repair.
- **Tools** wrap external systems — GitHub API, VCS, notifications.

### Agent Execution via ACP

Agents run as `claude-agent-acp` subprocesses communicating over stdio via the
[Agent Client Protocol](https://github.com/anthropics/agent-client-protocol).
The executor handles:

- **Prompt construction** — Merges agent instructions, context, and output
  schema directives into a single prompt
- **Streaming output** — Agent text is streamed to the console in real-time
- **Structured extraction** — The last JSON block in the agent's conversational
  output is extracted and validated against a Pydantic schema
- **Schema coercion** — When agents produce rich objects where the schema
  expects strings, a recursive coercion pass converts mismatched types
- **Truncation repair** — When agents hit token limits mid-JSON, unclosed
  strings, arrays, and objects are automatically closed

### VCS: Jujutsu + Git

Maverick uses a dual-VCS approach in colocated mode (jj and git share the same
`.git` directory):

| Operation | Tool | Module |
|-----------|------|--------|
| Commit, push, branch, snapshot, rollback | **jj** | `maverick.jj.client.JjClient` |
| Diff, status, log, blame (read-only) | **GitPython** | `maverick.git` |

**Why jj?** Jujutsu provides snapshot/restore operations that enable safe
rollback when a bead fails verification. The `fly` workflow snapshots
before each bead, and restores to the snapshot if the verification gate fails.

### Runway Knowledge Store

The runway records episodic data as beads are processed:

- **Bead outcomes** — Success/failure status, implementation details, error context
- **Review findings** — What reviewers flagged, severity, resolution status
- **Fix attempts** — What was tried, what worked, what didn't

This data is stored as JSONL files with BM25-based retrieval. Over time, agents
can query the runway for context on past decisions, recurring patterns, and
known pitfalls. The `maverick runway seed` command bootstraps this store by
analyzing a brownfield codebase with an AI agent. Periodic consolidation
(automatic during `maverick land`, or manual via `maverick runway consolidate`)
distills old episodic records into semantic summaries, keeping the store bounded
in size and improving retrieval quality.

### Project Structure

See [CONTRIBUTING.md](CONTRIBUTING.md#directory-structure) for the full directory layout.

## Configuration

Maverick uses YAML configuration files with layered precedence:

1. Project config: `./maverick.yaml`
2. User config: `~/.config/maverick/config.yaml`
3. CLI arguments (highest precedence)

```yaml
# Project identity — used for skill guidance and prompt injection
project_type: python

# Project-specific conventions injected into agent prompts at runtime.
# Agents run as ACP subprocesses without access to CLAUDE.md, so any
# project-specific standards (canonical libraries, language style, async
# rules) must be declared here.
project_conventions: |
  ### Canonical Libraries
  - **Logging**: `structlog` via `get_logger()`
  - **Retry logic**: `tenacity` (`@retry`, `AsyncRetrying`)
  - **Validation**: Pydantic `BaseModel`

  ### Async-First
  - All workflows MUST be async.
  - Never call `subprocess.run` from `async def`.

github:
  owner: your-org
  repo: your-repo
  default_branch: main

model:
  model_id: claude-sonnet-4-5-20250929

validation:
  format_cmd: ["ruff", "format", "."]
  lint_cmd: ["ruff", "check", "--fix", "."]
  test_cmd: ["pytest", "-x", "--tb=short"]
  timeout_seconds: 300

notifications:
  enabled: false
  server: https://ntfy.sh
  topic: maverick-notifications
```

### Agent Convention Injection

Agents run as ACP subprocesses and do **not** see CLAUDE.md at runtime.
Convention guidance is injected into prompts via a two-tier model:

| Tier | Source | Scope |
|------|--------|-------|
| **Framework conventions** | Hardcoded in `FRAMEWORK_CONVENTIONS` | Universal orchestration principles (separation of concerns, hardening, testing, type safety, modularization) — always present |
| **Project conventions** | `project_conventions` field in `maverick.yaml` | Language-specific and project-specific standards (canonical libraries, async rules, naming, docstring style) — injected by `render_prompt()` |

This means Maverick works on any project type — Python, Rust, Node.js, Go,
Ansible — without baking language-specific assumptions into the agent core.
See [Agent Prompts Reference](docs/agent-prompts.md) for details.

## Technology Stack

| Category | Technology | Notes |
|----------|-----------|-------|
| Language | Python 3.11+ | `from __future__ import annotations` |
| Package Manager | uv | Fast, reproducible builds via `uv.lock` |
| Build System | Make | AI-friendly commands with minimal output |
| AI/Agents | Agent Client Protocol (ACP) | `agent-client-protocol` SDK + `claude-agent-acp` subprocess |
| CLI | Click + Rich | Auto TTY detection for output |
| Validation | Pydantic | Configuration and data models |
| VCS (writes) | Jujutsu (jj) | Colocated mode; `maverick.jj.client.JjClient` |
| VCS (reads) | GitPython | `maverick.git` (read-only) |
| GitHub API | PyGithub | `maverick.utils.github_client` |
| Logging | structlog | `maverick.logging.get_logger()` |
| Retry Logic | tenacity | `@retry` or `AsyncRetrying` |
| Knowledge Store | rank-bm25 | BM25-based retrieval for runway queries |
| Secret Detection | detect-secrets | Pre-commit secret scanning |
| Testing | pytest + pytest-asyncio | Parallel via xdist (`-n auto`) |
| Linting | Ruff | Fast, comprehensive Python linter |
| Type Checking | MyPy | Strict mode |

## Development

### Setup

```bash
git clone https://github.com/get2knowio/maverick.git
cd maverick
uv sync
uv run maverick --help
```

### Commands

```bash
make test           # Run all tests in parallel (errors only)
make test-fast      # Unit tests only, no slow tests (fastest)
make test-cov       # Run tests with coverage report
make lint           # Run ruff linter
make typecheck      # Run mypy
make format-fix     # Apply formatting fixes
make check          # Run all checks (lint, typecheck, test)
make ci             # CI mode: fail fast on any error
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development guidelines.

## Documentation

- [Agent Prompts Reference](docs/agent-prompts.md) — Complete catalog of all agent system prompts
- [Training Slides](https://get2knowio.github.io/maverick/slides/) — Technology and architecture deep dives
- [Training Curriculum](docs/curriculum.md) — Structured learning path

## License

MIT

## Links

- [Documentation Site](https://get2knowio.github.io/maverick/)
- [Contributing Guide](CONTRIBUTING.md)
- [Issue Tracker](https://github.com/get2knowio/maverick/issues)
- [Agent Client Protocol](https://github.com/anthropics/agent-client-protocol)
