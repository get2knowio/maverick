# Agent Prompts Reference

This document catalogs every system prompt, prompt template, and shared fragment
used by Maverick's AI agents. Agents run via the Claude Agent SDK and do **not**
have access to CLAUDE.md or the Claude Code system prompt at runtime — the
conventions they need are injected directly into their prompts.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Shared Prompt Fragments](#shared-prompt-fragments)
  - [Tool Usage Fragments](#tool-usage-fragments)
  - [Code Quality Principles](#code-quality-principles)
  - [Conventions (Two-Tier Model)](#conventions-two-tier-model)
- [Core Agents](#core-agents)
  - [ImplementerAgent](#implementeragent)
  - [UnifiedReviewerAgent](#unifiedrevieweragent)
  - [CodeReviewerAgent](#coderevieweragent)
  - [FixerAgent](#fixeragent)
  - [SimpleFixerAgent](#simplefixeragent)
  - [IssueFixerAgent](#issuefixeragent)
- [Generator Agents](#generator-agents)
  - [CommitMessageGenerator](#commitmessagegenerator)
  - [PRTitleGenerator](#prtitlegenerator)
  - [PRDescriptionGenerator](#prdescriptiongenerator)
  - [ErrorExplainer](#errorexplainer)
  - [CodeAnalyzer](#codeanalyzer)
  - [BeadEnricherGenerator](#beadenrichergenerator)
  - [DependencyExtractor](#dependencyextractor)
- [Prompt Composition](#prompt-composition)
  - [Skill Guidance Injection](#skill-guidance-injection)
  - [Tool Permission Model](#tool-permission-model)

---

## Architecture Overview

All agents inherit from `MaverickAgent[TContext, TResult]`, a generic base class
that enforces typed context/result contracts. The prompt architecture follows
these principles:

1. **Constrained role** — Each agent is told what the orchestration layer
   handles (commits, validation, PR creation) so it stays in its lane.
2. **Composable fragments** — Shared constants (`TOOL_USAGE_*`,
   `CODE_QUALITY_PRINCIPLES`, `FRAMEWORK_CONVENTIONS`) are imported and
   interpolated into system prompts. Project-specific conventions are
   injected at runtime via the `$project_conventions` placeholder.
3. **Skill guidance injection** — The `render_prompt()` function injects
   project-type-specific guidance via a `$skill_guidance` placeholder.
4. **Least-privilege tooling** — Each agent gets only the tools it needs
   (see [Tool Permission Model](#tool-permission-model)).

```
common.py fragments ──────────┐
  TOOL_USAGE_*, CODE_QUALITY  │
  FRAMEWORK_CONVENTIONS       ├──▶  render_prompt()  ──▶  Agent System Prompt
                              │         ▲    ▲                    │
skill_prompts.py ─────────────┘         │    │                    ▼
  $skill_guidance (by project_type)  ───┘    │            Claude Agent SDK
                                             │                    │
maverick.yaml ───────────────────────────────┘        ┌───────────┼───────────┐
  $project_conventions (runtime injection)            ▼           ▼           ▼
                                                    Read       Write       Edit  ...
```

---

## Shared Prompt Fragments

**Source**: `src/maverick/agents/prompts/common.py`

These constants are imported by multiple agents. They ensure consistent guidance
across the agent fleet.

### Tool Usage Fragments

Each fragment provides concise, agent-appropriate guidance for a single tool.

| Constant | Tool | Key Guidance |
|----------|------|-------------|
| `TOOL_USAGE_READ` | Read | Must read before editing; suitable for reviewing specs and conventions |
| `TOOL_USAGE_EDIT` | Edit | Primary modification tool; `old_string` must be unique; preserve indentation |
| `TOOL_USAGE_WRITE` | Write | For new files only; prefer Edit for existing files; minimize file creation |
| `TOOL_USAGE_GLOB` | Glob | Find files by pattern; use instead of guessing paths |
| `TOOL_USAGE_GREP` | Grep | Search contents by regex; find definitions, usages, imports |
| `TOOL_USAGE_TASK` | Task | Spawn subagents for parallel work; provide clear, detailed prompts |

### Code Quality Principles

**Constant**: `CODE_QUALITY_PRINCIPLES`

General quality guidelines injected into implementation-oriented agents:

- Avoid over-engineering — minimum complexity for the current task
- Keep it simple — three similar lines beat a premature abstraction
- Security awareness — no command injection, XSS, SQL injection
- No magic values — extract to named constants
- Read before writing — understand existing code first
- Minimize file creation — prefer editing existing files
- Clean boundaries — match surrounding code style

### Conventions (Two-Tier Model)

Conventions are split into two tiers to support polyglot projects:

#### Tier 1: Framework Conventions (hardcoded)

**Constant**: `FRAMEWORK_CONVENTIONS`

Universal orchestration principles that apply regardless of language or stack.
These are always injected into agent prompts at import time via f-string
interpolation.

Covers:

- **Separation of concerns** — Agents provide judgment; workflows own side effects
- **Hardening** — Timeouts, retry with backoff, specific exception handling
- **Testing** — TDD; every public function tested; test error states
- **Type safety** — Complete type hints; typed data structures over untyped dicts
- **Code style** — Follow project conventions (from CLAUDE.md); no magic values
- **Modularization** — Aim <500 LOC; refactor at ~800 LOC

A backward-compatibility alias `PROJECT_CONVENTIONS = FRAMEWORK_CONVENTIONS` is
provided for importers that haven't migrated yet.

#### Tier 2: Project-Specific Conventions (runtime, from `maverick.yaml`)

**Placeholder**: `$project_conventions`

Project-specific conventions (e.g., canonical libraries, language-specific style
rules) are loaded at runtime from the `project_conventions` field in
`maverick.yaml`. The `render_prompt()` function reads this field and substitutes
the `$project_conventions` placeholder in agent prompt templates.

If the field is non-empty, it is wrapped with a `## Project-Specific Conventions`
header. If absent or empty, the placeholder is replaced with an empty string.

**Example `maverick.yaml`**:

```yaml
project_type: python

project_conventions: |
  ### Canonical Third-Party Libraries
  - **Logging**: `structlog` via `get_logger()`
  - **Retry logic**: `tenacity` (`@retry`, `AsyncRetrying`)
  - **Validation**: Pydantic `BaseModel`

  ### Async-First
  - All workflows MUST be async.
  - Never call `subprocess.run` from `async def`.
```

---

## Core Agents

### ImplementerAgent

**Source**: `src/maverick/agents/implementer.py`
**Class**: `ImplementerAgent`
**Context**: `ImplementerContext` | **Result**: `ImplementationResult`
**Tools**: Read, Write, Edit, Glob, Grep, Task (+ `run_validation` MCP tool if available)

The primary agent for executing beads — units of work that may be feature tasks,
validation fixes, or review findings.

#### System Prompt (`IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE`)

The system prompt is rendered with project-type skill guidance via
`render_prompt()`.

**Role framing**:
> You implement beads — units of work that may be feature tasks, validation
> fixes, or review findings. The bead description tells you what to do; you do
> not need to know or care about the broader workflow context.

**Orchestration boundaries** (what the agent does NOT do):
- Git operations (commits created after work completes)
- Validation execution (format/lint/test pipelines run after implementation)
- Branch management and PR creation
- Bead lifecycle (selection, closing, creating follow-up beads)

**Core approach**:
1. Read CLAUDE.md for project conventions
2. Read relevant existing code before writing
3. Understand the task fully
4. Write tests for every source file (mandatory, not optional)
5. Make small, incremental changes
6. Ensure code is ready for validation

**Injected fragments**: `TOOL_USAGE_READ`, `TOOL_USAGE_WRITE`, `TOOL_USAGE_EDIT`,
`TOOL_USAGE_GLOB`, `TOOL_USAGE_GREP`, `TOOL_USAGE_TASK`,
`CODE_QUALITY_PRINCIPLES`, `FRAMEWORK_CONVENTIONS`, `$project_conventions`

#### Task Prompt (`_build_task_prompt`)

Built dynamically for each bead/task. Includes:
- Task ID and description
- Instructions to read CLAUDE.md and existing source files first
- TDD implementation approach (understand, test, implement, verify)

Does **not** include branch information (workflow handles branches).

#### Phase Prompt (`PHASE_PROMPT_TEMPLATE`) — Deprecated

Speckit-era template for executing tasks from `tasks.md` files phase by phase.
Still present for `refuel speckit` compatibility but not used by the bead-driven
`fly` workflow.

---

### UnifiedReviewerAgent

**Source**: `src/maverick/agents/reviewers/unified_reviewer.py`
**Class**: `UnifiedReviewerAgent`
**Context**: `dict[str, Any]` | **Result**: `ReviewResult`
**Tools**: Read, Glob, Grep, Task

Comprehensive code reviewer that spawns parallel subagents for different
review perspectives.

#### System Prompt (`UNIFIED_REVIEWER_PROMPT_TEMPLATE`)

**Role framing**:
> You are a comprehensive code reviewer within an orchestrated workflow.

**Orchestration boundaries**:
- Diffs and changed file lists are provided
- A separate fixer agent handles applying fixes
- The review-fix iteration cycle is managed externally

**Review quality principles**:
- Read before commenting — use full file context, not just diff fragments
- Be specific and actionable — exact file, line, and fix description
- Focus on substance over style nitpicks
- Verify assumptions with Grep/Glob before reporting
- Active security awareness (OWASP top 10)

**Review perspectives** (two parallel subagents):

1. **Python Expert** — Idiomatic Python, type hints, async patterns, Pydantic
   usage, canonical library compliance, error handling, hardening (timeouts,
   tenacity, specific exceptions)

2. **Requirements Expert** — Reviews against the bead description and acceptance
   criteria: Does the implementation satisfy the stated objective? Missing edge
   cases? Adequate tests? Canonical library standards? Typed contracts?

**Injected fragments**: `TOOL_USAGE_READ`, `TOOL_USAGE_GLOB`, `TOOL_USAGE_GREP`,
`TOOL_USAGE_TASK`, `FRAMEWORK_CONVENTIONS`, `$project_conventions`

**Output format**: JSON with grouped findings, each containing `id`, `file`,
`line`, `issue`, `severity` (critical/major/minor), `category`
(requirements_gap, library_standards, clean_code, type_hints, testing,
data_model, security, performance), and optional `fix_hint`.

---

### CodeReviewerAgent

**Source**: `src/maverick/agents/code_reviewer/prompts.py`
**Class**: `CodeReviewerAgent`
**Tools**: Code-review-specific read-only tools

The original code reviewer, which operates on pre-gathered context (diffs and
file contents are provided, not fetched by the agent).

#### System Prompt (`SYSTEM_PROMPT`)

**Role framing**:
> You are an expert code reviewer specializing in Python development. You
> analyze pre-gathered code changes within an orchestrated workflow.

**Review dimensions**:
1. **Correctness** — Logic errors, edge cases, error handling
2. **Security** — Injection vulnerabilities, secrets exposure, unsafe patterns
3. **Style & Conventions** — Adherence to CLAUDE.md
4. **Performance** — Inefficient algorithms, resource leaks
5. **Testability** — Coverage implications, dependency injection

**Severity levels**: CRITICAL, MAJOR, MINOR, SUGGESTION

Each finding must include actionable before/after code examples and optional
`convention_ref` linking to the relevant CLAUDE.md section.

---

### FixerAgent

**Source**: `src/maverick/agents/fixer.py`
**Class**: `FixerAgent`
**Context**: `AgentContext` | **Result**: `AgentResult`
**Tools**: Read, Write, Edit (minimal set)

The most constrained agent — applies targeted validation fixes with the smallest
possible tool set.

#### System Prompt (`FIXER_SYSTEM_PROMPT`)

**Role framing**:
> You are a validation fixer. You apply targeted corrections to specific files
> within an orchestrated workflow.

**Key constraints**:
- Receives explicit file paths — does not search for files
- Minimal changes only — no refactoring, no feature additions
- Must match existing code style
- Read and understand context before modifying

---

### SimpleFixerAgent

**Source**: `src/maverick/agents/reviewers/simple_fixer.py`
**Class**: `SimpleFixerAgent`
**Tools**: Read, Write, Edit, Glob, Grep, Task

Fixes code review findings with accountability tracking and parallel execution
for independent issues.

#### System Prompt (`SIMPLE_FIXER_PROMPT`)

**Role framing**:
> You are a code fixer within an orchestrated workflow.

**Outcome types**:
- **fixed** — Code changes made successfully
- **blocked** — Cannot fix due to valid technical reason (missing dependency,
  architectural constraint, file deleted)
- **deferred** — Needs more context; will retry in next iteration

**Accountability rules**:
1. Must report on EVERY finding (no silent skipping)
2. "Fixed" means actually fixed (code changes made, not just described)
3. "Blocked" requires valid technical justification
4. "Deferred" items get retried in the next iteration

**Output**: JSON listing outcomes for each finding ID.

---

### IssueFixerAgent

**Source**: `src/maverick/agents/issue_fixer.py`
**Class**: `IssueFixerAgent`
**Context**: `IssueFixerContext` | **Result**: `FixResult`
**Tools**: Read, Write, Edit, Glob, Grep

Resolves GitHub issues with minimal, targeted code changes.

#### System Prompt (`ISSUE_FIXER_SYSTEM_PROMPT`)

**Role framing**:
> You are an expert software engineer. You focus on minimal, targeted bug fixes
> within an orchestrated workflow.

**Fix guidelines**:
- Change only what's necessary (target <100 lines)
- Don't "improve" surrounding code
- Don't add features while fixing bugs
- Add a test that reproduces the bug (if feasible)

**Output**: JSON with `issue_number`, `root_cause`, `fix_description`,
`files_changed`, and `verification`.

---

## Generator Agents

Generators are stateless, single-shot text generators. They inherit from
`GeneratorAgent` (which extends `MaverickAgent`) and have **no tools** — all
input comes via the prompt. Their output is strictly formatted (often a single
line or specific markdown structure).

### CommitMessageGenerator

**Source**: `src/maverick/agents/generators/commit_message.py`
**Prompt constant**: `COMMIT_MESSAGE_SYSTEM_PROMPT`

Generates conventional commit messages from git diffs.

**Format**: `type(scope): description`
**Rules**: Imperative mood, lowercase, no period, <72 characters
**Output**: ONLY the commit message, nothing else

### PRTitleGenerator

**Source**: `src/maverick/agents/generators/pr_title.py`
**Prompt constant**: `PR_TITLE_SYSTEM_PROMPT`

Generates PR titles in conventional commit format.

**Format**: `type(scope): description`
**Output**: ONLY the title (no preamble, no explanation)

### PRDescriptionGenerator

**Source**: `src/maverick/agents/generators/pr_description.py`
**Prompt method**: `_build_system_prompt()`

Generates markdown PR descriptions with configurable sections (default: Summary,
Changes, Testing).

**Output**: Markdown starting with `## Summary`, no preamble

### ErrorExplainer

**Source**: `src/maverick/agents/generators/error_explainer.py`
**Prompt constant**: `SYSTEM_PROMPT`

Translates cryptic error messages into clear, actionable guidance.

**Output structure**:
- **What happened** — Plain English (1-2 sentences)
- **Why this occurred** — Root cause in simple terms
- **How to fix** — Actionable numbered steps
- **Code example** — Corrected snippet (if applicable)

### CodeAnalyzer

**Source**: `src/maverick/agents/generators/code_analyzer.py`
**Prompt constants**: `SYSTEM_PROMPT_EXPLAIN`, `SYSTEM_PROMPT_REVIEW`,
`SYSTEM_PROMPT_SUMMARIZE`

Analyzes code snippets in one of three modes:
- **explain** — What it does, how it works, implementation details
- **review** — Bugs, edge cases, performance, security, best practices
- **summarize** — Brief overview of purpose and structure (2-4 sentences)

### BeadEnricherGenerator

**Source**: `src/maverick/agents/generators/bead_enricher.py`
**Prompt constant**: `BEAD_ENRICHER_SYSTEM_PROMPT`

Transforms sparse bead definitions into self-contained work items.

**Output sections**: Objective, Acceptance Criteria (checkbox format), Key Files,
Conventions, Dependency Context

**Enrichment scale by category**:
- FOUNDATION: Heavy (full conventions, all file paths, detailed criteria)
- USER_STORY: Medium (focused criteria, relevant files)
- CLEANUP: Light (Objective + Acceptance Criteria only)

### DependencyExtractor

**Source**: `src/maverick/agents/generators/dependency_extractor.py`
**Prompt constant**: `DEPENDENCY_EXTRACTOR_SYSTEM_PROMPT`

Parses free-form prose from a "User Story Dependencies" section into structured
`[dependent, dependency]` pairs.

**Output**: JSON array of 2-element arrays (e.g., `[["US3","US1"],["US7","US1"]]`)

---

## Prompt Composition

### Convention & Skill Injection

**Source**: `src/maverick/agents/skill_prompts.py`

The `render_prompt()` function is the single entry point for resolving all
runtime placeholders in agent prompt templates. It handles three substitutions:

| Placeholder | Source | Purpose |
|-------------|--------|---------|
| `$skill_guidance` | `PROJECT_TYPE_SKILLS` dict + `project_type` from `maverick.yaml` | Language-specific skill areas (e.g., Python testing, Rust ownership) |
| `$project_conventions` | `project_conventions` field in `maverick.yaml` | Project-specific canonical libraries, style rules, async patterns |
| `$project_type` / `$project_type_name` | `project_type` from `maverick.yaml` | Raw type key and human-readable name |

```python
from maverick.agents.skill_prompts import render_prompt

# All three placeholders are resolved in a single call
system_prompt = render_prompt(
    IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE,
    project_type="python",           # or auto-detected from maverick.yaml
    config_path=Path("maverick.yaml"),  # optional, defaults to cwd
)
```

**How it works**:

1. `get_project_type()` reads `project_type` from `maverick.yaml` (default: `"unknown"`)
2. `get_skill_guidance()` maps the project type to skill areas via `PROJECT_TYPE_SKILLS`
3. `get_project_conventions()` reads the `project_conventions` field from `maverick.yaml`
4. If conventions are non-empty, they're wrapped with a `## Project-Specific Conventions` header
5. All values are passed to `Template.safe_substitute()` — unmatched placeholders are left as-is

**For polyglot support**: A project that uses Go instead of Python simply sets
`project_type: go` and writes Go-specific conventions in `project_conventions`.
No agent code changes needed — the framework conventions (hardcoded) stay the
same, and the project conventions (runtime) adapt automatically.

### Tool Permission Model

Each agent type has a frozen set of allowed tools defined in
`src/maverick/agents/tools.py`. Tools are granted on a least-privilege basis:

| Agent | Read | Write | Edit | Glob | Grep | Task | MCP Tools |
|-------|:----:|:-----:|:----:|:----:|:----:|:----:|:---------:|
| ImplementerAgent | x | x | x | x | x | x | run_validation |
| UnifiedReviewerAgent | x | | | x | x | x | |
| CodeReviewerAgent | x | | | | | | |
| FixerAgent | x | x | x | | | | |
| SimpleFixerAgent | x | x | x | x | x | x | |
| IssueFixerAgent | x | x | x | x | x | | |
| Generators | (none) | | | | | | |

**Key principle**: Agents that only analyze (reviewers, generators) get read-only
tools. Agents that modify code get Write/Edit. Only agents that need parallelism
get Task. No agent gets Bash — the orchestration layer handles command execution.
