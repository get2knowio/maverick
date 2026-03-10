# Maverick Agent Reference

Maverick uses a multi-agent architecture where specialized AI agents handle distinct phases of the development workflow. Each agent has a narrowly scoped role, a minimal tool set (principle of least privilege), and a typed output contract. Agents do not orchestrate themselves -- workflows coordinate agent execution, passing structured context in and extracting structured results out.

All agents inherit from `MaverickAgent` (defined in `src/maverick/agents/base.py`) and are executed via the ACP (Agent Client Protocol) executor. Generator agents inherit from `GeneratorAgent` and use single-shot `query()` calls with no tools.

## Quick Reference

| Registry Name | Class | Workflow | Tools | Output Model |
|---|---|---|---|---|
| `scopist` | `ScopistAgent` | Generate Flight Plan | Read, Glob, Grep | `ScopistBrief` |
| `codebase_analyst` | `CodebaseAnalystAgent` | Generate Flight Plan | Read, Glob, Grep | `CodebaseAnalystBrief` |
| `criteria_writer` | `CriteriaWriterAgent` | Generate Flight Plan | Read, Glob, Grep | `CriteriaWriterBrief` |
| `preflight_contrarian` | `PreFlightContrarianAgent` | Generate Flight Plan | Read, Glob, Grep | `PreFlightContrarianBrief` |
| `flight_plan_generator` | `FlightPlanGeneratorAgent` | Generate Flight Plan | Read, Glob, Grep | `FlightPlanOutput` |
| `navigator` | `NavigatorAgent` | Refuel Maverick | Read, Glob, Grep | `NavigatorBrief` |
| `structuralist` | `StructuralistAgent` | Refuel Maverick | Read, Glob, Grep | `StructuralistBrief` |
| `recon` | `ReconAgent` | Refuel Maverick | Read, Glob, Grep | `ReconBrief` |
| `contrarian` | `ContrarianAgent` | Refuel Maverick | Read, Glob, Grep | `ContrarianBrief` |
| `decomposer` | `DecomposerAgent` | Refuel Maverick | Read, Glob, Grep | `DecompositionOutput` |
| `implementer` | `ImplementerAgent` | Fly Beads | Read, Write, Edit, Glob, Grep, Task, Bash | `ImplementationResult` |
| `fixer` | `FixerAgent` | Fly Beads (validate-fix loop) | Read, Write, Edit | `FixerResult` |
| `completeness-reviewer` | `CompletenessReviewerAgent` | Fly Beads (review-fix, parallel) | Read, Glob, Grep | `GroupedReviewResult` |
| `correctness-reviewer` | `CorrectnessReviewerAgent` | Fly Beads (review-fix, parallel) | Read, Glob, Grep | `GroupedReviewResult` |
| `unified-reviewer` | `UnifiedReviewerAgent` | Legacy (superseded) | Read, Glob, Grep, Task | `GroupedReviewResult` |
| `simple-fixer` | `SimpleFixerAgent` | Fly Beads (review-fix) | Read, Write, Edit, Glob, Grep, Task | `list[FixOutcome]` |
| `curator` | `CuratorAgent` | Land | (none) | JSON plan (untyped) |
| `code-reviewer` | `CodeReviewerAgent` | Standalone / legacy | Read, Glob, Grep | `ReviewResult` |
| `issue-fixer` | `IssueFixerAgent` | Standalone / legacy | Read, Write, Edit, Glob, Grep | `FixResult` |

### Generator Agents (stateless, no tools)

| Name | Class | Purpose |
|---|---|---|
| `commit-message-generator` | `CommitMessageGenerator` | Conventional commit messages from diffs |
| `pr-description-generator` | `PRDescriptionGenerator` | Markdown PR descriptions |
| `pr-title-generator` | `PRTitleGenerator` | PR titles in conventional commit format |
| `bead-enricher` | `BeadEnricherGenerator` | Enrich sparse bead definitions with acceptance criteria |
| `dependency-extractor` | `DependencyExtractor` | Extract inter-story dependency pairs from prose |
| `code-analyzer` | `CodeAnalyzer` | Explain, review, or summarize code snippets |
| `error-explainer` | `ErrorExplainer` | Translate error output into actionable guidance |

---

## Generate Flight Plan Workflow

**Workflow**: `src/maverick/workflows/generate_flight_plan/workflow.py`
**Command**: `maverick refuel flight-plan`

Converts a PRD (Product Requirements Document) into a structured Maverick flight plan through a two-phase process: parallel preflight briefing followed by plan generation.

### Phase 1: Preflight Briefing (parallel)

Three specialist agents run concurrently, each analyzing the PRD against the codebase from a different angle. A fourth contrarian agent then synthesizes and challenges their outputs.

#### `scopist`

- **Class**: `ScopistAgent` (`src/maverick/agents/preflight_briefing/scopist.py`)
- **Purpose**: Analyzes the PRD to determine what should be in scope and out of scope. Explores the codebase to understand what already exists before drawing boundaries.
- **Input**: Prompt string containing the PRD content and codebase context.
- **Output**: `ScopistBrief` (`src/maverick/preflight_briefing/models.py`) -- in-scope items, out-of-scope items, boundaries, and scope rationale.

#### `codebase_analyst`

- **Class**: `CodebaseAnalystAgent` (`src/maverick/agents/preflight_briefing/codebase_analyst.py`)
- **Purpose**: Maps PRD requirements to the existing codebase. Identifies relevant modules, existing patterns, integration points, and provides a complexity assessment.
- **Input**: Prompt string containing the PRD content and codebase context.
- **Output**: `CodebaseAnalystBrief` (`src/maverick/preflight_briefing/models.py`) -- relevant modules, existing patterns, integration points, complexity assessment.

#### `criteria_writer`

- **Class**: `CriteriaWriterAgent` (`src/maverick/agents/preflight_briefing/criteria_writer.py`)
- **Purpose**: Drafts measurable, independently verifiable success criteria and a clear objective for the flight plan. Grounds criteria in codebase reality (existing tests, validation commands).
- **Input**: Prompt string containing the PRD content and codebase context.
- **Output**: `CriteriaWriterBrief` (`src/maverick/preflight_briefing/models.py`) -- success criteria, objective draft, measurability notes.

#### `preflight_contrarian`

- **Class**: `PreFlightContrarianAgent` (`src/maverick/agents/preflight_briefing/contrarian.py`)
- **Purpose**: Devil's advocate. Receives the three specialist briefs and challenges assumptions -- scope items that are too broad or narrow, unmeasurable criteria, missing edge cases. Also identifies consensus points worth preserving.
- **Input**: Prompt string containing all three prior briefs and the original PRD.
- **Output**: `PreFlightContrarianBrief` (`src/maverick/preflight_briefing/models.py`) -- scope challenges, criteria challenges, missing considerations, consensus points.

### Phase 2: Generation

#### `flight_plan_generator`

- **Class**: `FlightPlanGeneratorAgent` (`src/maverick/agents/flight_plan_generator.py`)
- **Purpose**: Converts the PRD into a structured flight plan, incorporating all briefing outputs. Produces a plan with objective, success criteria, scope boundaries, context, and constraints.
- **Input**: Prompt string containing the PRD and synthesized briefing context.
- **Output**: `FlightPlanOutput` (`src/maverick/workflows/generate_flight_plan/models.py`) -- objective, success criteria, scope (in/out/boundaries), context, constraints.

---

## Refuel Maverick Workflow

**Workflow**: `src/maverick/workflows/refuel_maverick/workflow.py`
**Command**: `maverick refuel maverick`

Decomposes a flight plan into granular work units (beads) through a two-phase process: parallel briefing room followed by decomposition.

### Phase 1: Briefing Room (parallel)

Three specialist agents run concurrently, analyzing the flight plan from different angles. A contrarian agent then synthesizes their outputs.

#### `navigator`

- **Class**: `NavigatorAgent` (`src/maverick/agents/briefing/navigator.py`)
- **Purpose**: Architecture and module layout specialist. Analyzes architectural implications, proposes file/directory structure for new code, and identifies integration points with existing systems.
- **Input**: Prompt string containing the flight plan and codebase context.
- **Output**: `NavigatorBrief` (`src/maverick/briefing/models.py`) -- architecture decisions (with rationale and alternatives), module structure, integration points.

#### `structuralist`

- **Class**: `StructuralistAgent` (`src/maverick/agents/briefing/structuralist.py`)
- **Purpose**: Data modeling and type design specialist. Proposes data models/classes with fields and relationships, and defines protocols/interfaces at component boundaries.
- **Input**: Prompt string containing the flight plan and codebase context.
- **Output**: `StructuralistBrief` (`src/maverick/briefing/models.py`) -- entities (with fields, types, relationships), interfaces (with methods and consumers).

#### `recon`

- **Class**: `ReconAgent` (`src/maverick/agents/briefing/recon.py`)
- **Purpose**: Risk analyst and testing strategist. Identifies risks with severity ratings and mitigations, flags underspecified areas in the flight plan, and proposes testing strategy with concrete patterns.
- **Input**: Prompt string containing the flight plan and codebase context.
- **Output**: `ReconBrief` (`src/maverick/briefing/models.py`) -- risks (with severity and mitigations), ambiguities (with resolutions), testing strategy, suggested cross-plan dependencies.

#### `contrarian`

- **Class**: `ContrarianAgent` (`src/maverick/agents/briefing/contrarian.py`)
- **Purpose**: Devil's advocate and simplification expert. Challenges assumptions and over-engineering from the other three briefs, proposes simpler alternatives, and identifies consensus points.
- **Input**: Prompt string containing all three specialist briefs and the original flight plan.
- **Output**: `ContrarianBrief` (`src/maverick/briefing/models.py`) -- challenges (with counter-arguments and recommendations), simplifications (with tradeoffs), consensus points.

### Phase 2: Decomposition

#### `decomposer`

- **Class**: `DecomposerAgent` (`src/maverick/agents/decomposer.py`)
- **Purpose**: Breaks down the flight plan (with briefing context) into ordered, right-sized work units (beads). Each unit has a kebab-case ID, sequence number, dependencies, acceptance criteria, file scope, and verification commands.
- **Input**: Prompt string containing the flight plan and synthesized briefing context.
- **Output**: `DecompositionOutput` (`src/maverick/workflows/refuel_maverick/models.py`) -- list of work unit specifications with dependencies and execution order.

---

## Fly Beads Workflow

**Workflow**: `src/maverick/workflows/fly_beads/workflow.py`
**Command**: `maverick fly`

Iterates over ready beads (units of work) inside a hidden jj workspace. For each bead: implement, validate, fix, review, fix again, commit, close.

#### `implementer`

- **Class**: `ImplementerAgent` (`src/maverick/agents/implementer.py`)
- **Purpose**: Expert software engineer that implements bead work using TDD. Reads CLAUDE.md and existing code first, writes tests alongside implementation, and follows project conventions. Has the broadest tool set including Bash for running commands and Task for spawning subagents.
- **Input**: `ImplementerContext` (or dict with `task_description` and `cwd`) -- the bead description and workspace path.
- **Output**: `ImplementationResult` (`src/maverick/models/implementation.py`) -- task outcomes and file changes.
- **Tools**: Read, Write, Edit, Glob, Grep, Task, Bash

#### `fixer`

- **Class**: `FixerAgent` (`src/maverick/agents/fixer.py`)
- **Purpose**: Applies minimal, targeted validation fixes (lint errors, type errors, formatting). Has the smallest tool set -- receives explicit file paths and error information, does not search for files. Used in the validate-and-fix retry loop after implementation.
- **Input**: `AgentContext` with `extra["prompt"]` containing the file path, error details, and fix instructions.
- **Output**: `FixerResult` (`src/maverick/models/fixer.py`) -- success flag, summary, files mentioned, error details.
- **Tools**: Read, Write, Edit

#### `completeness-reviewer`

- **Class**: `CompletenessReviewerAgent` (`src/maverick/agents/reviewers/completeness_reviewer.py`)
- **Purpose**: Requirements-focused reviewer that verifies faithful, complete coverage of the task's requirements, acceptance criteria, and briefing expectations. Checks that all requirements are addressed, edge cases from requirements are handled, tests cover required behavior, and architecture decisions from briefing are followed.
- **Input**: Dict with `changed_files`, `diff`, `feature_name`, `bead_description`, optional `briefing_context`.
- **Output**: `GroupedReviewResult` (`src/maverick/models/review_models.py`) -- groups of findings focused on requirements gaps, missing tests, and briefing deviations.
- **Tools**: Read, Glob, Grep

#### `correctness-reviewer`

- **Class**: `CorrectnessReviewerAgent` (`src/maverick/agents/reviewers/correctness_reviewer.py`)
- **Purpose**: Technical quality reviewer that checks for correctness, security, idiomatic patterns, and best practices. Reviews for proper type usage, canonical library compliance, error handling, hardening (timeouts, retries), and OWASP top 10 vulnerabilities.
- **Input**: Dict with `changed_files`, `diff`, `feature_name`, `bead_description`.
- **Output**: `GroupedReviewResult` (`src/maverick/models/review_models.py`) -- groups of findings focused on clean code, security, type hints, and library standards.
- **Tools**: Read, Glob, Grep

Both reviewers run in parallel via `asyncio.gather()` in `_run_dual_review()`. Their findings are merged with de-duplicated IDs before being passed to the fixer.

#### `unified-reviewer` (legacy)

- **Class**: `UnifiedReviewerAgent` (`src/maverick/agents/reviewers/unified_reviewer.py`)
- **Purpose**: Superseded by the parallel completeness/correctness pair above. Previously spawned two subagents via the Task tool within a single agent session.
- **Tools**: Read, Glob, Grep, Task

#### `simple-fixer` (review fixer)

- **Class**: `SimpleFixerAgent` (`src/maverick/agents/reviewers/simple_fixer.py`)
- **Purpose**: Fixes code review findings with parallel execution. Receives grouped findings from the unified reviewer, spawns subagents for independent fixes, and reports outcomes with accountability (every finding must be addressed as fixed, blocked, or deferred).
- **Input**: Dict with `findings`, `groups`, `iteration`, and `cwd`.
- **Output**: `list[FixOutcome]` (`src/maverick/models/review_models.py`) -- per-finding outcome (fixed/blocked/deferred) with explanation.
- **Tools**: Read, Write, Edit, Glob, Grep, Task

---

## Land Workflow

**Command**: `maverick land`

Curates commit history and pushes finalized work.

#### `curator`

- **Class**: `CuratorAgent` (`src/maverick/agents/curator.py`)
- **Purpose**: One-shot history rewrite planner. Receives pre-gathered `jj log` and per-commit diff stats, then produces a JSON plan of jj commands (squash, describe, rebase) to reorganize commits into cleaner history. Conservative by design -- only proposes changes with clear benefit.
- **Input**: Dict with `commits` (list of change_id/description/stats) and `log_summary`.
- **Output**: JSON array of `{command, args, reason}` objects. Returns `[]` if history is already clean.
- **Tools**: None (all context provided in prompt)
- **Base class**: `GeneratorAgent` (not `MaverickAgent`)

---

## Standalone / Legacy Agents

These agents exist as full implementations but are not currently wired into the primary workflows. They may be used directly or serve as the foundation for newer agents.

#### `code-reviewer`

- **Class**: `CodeReviewerAgent` (`src/maverick/agents/code_reviewer/agent.py`)
- **Purpose**: Automated code review of feature branches. Analyzes git diffs with diff chunking for large changes. Checks correctness, security, style/conventions, performance, and testability. Superseded by `UnifiedReviewerAgent` in the fly workflow.
- **Output**: `ReviewResult` (`src/maverick/models/review.py`)

#### `issue-fixer`

- **Class**: `IssueFixerAgent` (`src/maverick/agents/issue_fixer.py`)
- **Purpose**: Resolves GitHub issues with minimal, targeted code changes. Receives pre-fetched issue data, identifies root cause, implements the minimum fix, and adds regression tests.
- **Output**: `FixResult` (`src/maverick/models/issue_fix.py`)

---

## Generator Agents

Generators are lightweight, stateless, single-shot text producers that use `query()` with no tools. They all inherit from `GeneratorAgent` (`src/maverick/agents/generators/base.py`).

| Generator | File | Purpose |
|---|---|---|
| `CommitMessageGenerator` | `generators/commit_message.py` | Produces conventional commit messages (`type(scope): description`) from git diffs and file stats. |
| `PRDescriptionGenerator` | `generators/pr_description.py` | Produces markdown PR descriptions with configurable sections (Summary, Changes, Testing). |
| `PRTitleGenerator` | `generators/pr_title.py` | Produces concise PR titles in conventional commit format. |
| `BeadEnricherGenerator` | `generators/bead_enricher.py` | Enriches sparse bead definitions into self-contained work items with objectives, acceptance criteria, key files, conventions, and dependency context. |
| `DependencyExtractor` | `generators/dependency_extractor.py` | Parses free-form prose from SpecKit dependency sections into structured `[dependent, dependency]` pairs. Used by the Refuel SpecKit workflow. |
| `CodeAnalyzer` | `generators/code_analyzer.py` | Analyzes code snippets in three modes: explain, review, or summarize. |
| `ErrorExplainer` | `generators/error_explainer.py` | Translates cryptic error messages into structured explanations with root cause and fix steps. |

---

## Tool Sets

Agents receive tools via named permission sets defined in `src/maverick/agents/tools.py`:

| Tool Set | Tools | Used By |
|---|---|---|
| `PLANNER_TOOLS` | Read, Glob, Grep | All briefing and planning agents |
| `REVIEWER_TOOLS` | Read, Glob, Grep | `CompletenessReviewerAgent`, `CorrectnessReviewerAgent`, `CodeReviewerAgent` |
| `IMPLEMENTER_TOOLS` | Read, Write, Edit, Glob, Grep, Task, Bash | `ImplementerAgent` |
| `FIXER_TOOLS` | Read, Write, Edit | `FixerAgent` |
| `ISSUE_FIXER_TOOLS` | Read, Write, Edit, Glob, Grep | `IssueFixerAgent`, `SimpleFixerAgent` (+ Task) |
| `GENERATOR_TOOLS` | (empty) | All generator agents |
| `CURATOR_TOOLS` | (empty) | `CuratorAgent` |
