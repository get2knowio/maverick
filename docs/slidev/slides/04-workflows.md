---
layout: section
class: text-center
---

# Part 4: Workflow System

Orchestrating Multi-Phase AI Development Workflows

---
layout: two-cols-header
---

# Python vs Claude Separation

The key orchestration pattern that reduces token usage by 40-60%

::left::

## Python Handles (Deterministic)

<div class="flex flex-col gap-2 mt-4">

<div v-click class="px-4 py-2 rounded-lg bg-blue-500/20 border border-blue-500 text-blue-300">
  <strong>Git Operations</strong>
  <div class="text-xs opacity-70">Branch management, commits, pushes</div>
</div>

<div v-click class="px-4 py-2 rounded-lg bg-blue-500/20 border border-blue-500 text-blue-300">
  <strong>File I/O</strong>
  <div class="text-xs opacity-70">Reading, writing, searching files</div>
</div>

<div v-click class="px-4 py-2 rounded-lg bg-blue-500/20 border border-blue-500 text-blue-300">
  <strong>Validation</strong>
  <div class="text-xs opacity-70">Format, lint, typecheck, test execution</div>
</div>

<div v-click class="px-4 py-2 rounded-lg bg-blue-500/20 border border-blue-500 text-blue-300">
  <strong>GitHub API</strong>
  <div class="text-xs opacity-70">Issue fetching, PR creation</div>
</div>

</div>

::right::

## Claude Handles (Judgment)

<div class="flex flex-col gap-2 mt-4">

<div v-click class="px-4 py-2 rounded-lg bg-indigo-500/20 border border-indigo-500 text-indigo-300">
  <strong>Implementation</strong>
  <div class="text-xs opacity-70">Writing code to satisfy requirements</div>
</div>

<div v-click class="px-4 py-2 rounded-lg bg-indigo-500/20 border border-indigo-500 text-indigo-300">
  <strong>Code Review</strong>
  <div class="text-xs opacity-70">Architecture analysis, convention checks</div>
</div>

<div v-click class="px-4 py-2 rounded-lg bg-indigo-500/20 border border-indigo-500 text-indigo-300">
  <strong>Text Generation</strong>
  <div class="text-xs opacity-70">Commit messages, PR descriptions</div>
</div>

<div v-click class="px-4 py-2 rounded-lg bg-indigo-500/20 border border-indigo-500 text-indigo-300">
  <strong>Error Analysis</strong>
  <div class="text-xs opacity-70">Understanding and fixing validation failures</div>
</div>

<div v-click class="mt-4 p-3 rounded-lg bg-green-500/20 border border-green-500 text-green-300 text-center">
  <strong>Result:</strong> 40-60% token reduction
</div>

</div>

<!--
The separation of concerns between Python and Claude is the foundation of efficient workflow orchestration.

Python handles all deterministic operations - things that have a single correct way to do them. Git operations, file I/O, running validation tools, and calling GitHub APIs are all handled by Python runners.

Claude is invoked only for tasks requiring judgment - writing code to meet requirements, reviewing architecture, generating human-readable text, and understanding complex error messages.

This separation delivers a 40-60% reduction in token usage compared to having Claude handle everything, while also improving reliability since deterministic operations don't have the variability of LLM responses.
-->

---
layout: default
---

# Fly Workflow - Feature Implementation

Complete spec-based development from tasks.md to pull request

<div class="text-sm text-yellow-300 mb-4">
<strong>Prerequisite:</strong> tasks.md must be generated via <code>/speckit.tasks</code> (<a href="https://speckit.org">speckit.org</a>)
</div>

<div class="grid grid-cols-2 gap-4 mt-8">

<div>
  <WorkflowStage v-click name="1. INIT" status="complete" description="Sync branch with origin/main, validate spec" />
</div>

<div>
  <WorkflowStage v-click name="2. IMPLEMENTATION" status="complete" description="Execute tasks phase-by-phase (Claude handles [P] parallelization)" />
</div>

<div>
  <WorkflowStage v-click name="3. VALIDATION" status="active" description="Format/lint/test with auto-fix (up to 3 retries)" />
</div>

<div>
  <WorkflowStage v-click name="4. CODE REVIEW" status="pending" description="Optional parallel reviews (CodeRabbit + architecture)" />
</div>

<div>
  <WorkflowStage v-click name="5. CONVENTION UPDATE" status="pending" description="Update CLAUDE.md if learnings found" />
</div>

<div>
  <WorkflowStage v-click name="6. PR CREATION" status="pending" description="Generate PR body, create via GitHub CLI" />
</div>

<div class="col-span-2">
  <WorkflowStage v-click name="7. COMPLETE" status="pending" description="Terminal state (COMPLETE or FAILED)" />
</div>

</div>

<div v-click class="mt-6 text-sm opacity-70">
  Usage: <code>maverick fly feature -i branch_name=025-feature-branch</code>
</div>

<!--
FlyWorkflow is Maverick's primary workflow for spec-based feature development. It takes you from a task list all the way to a pull request, handling all the intermediate steps.

IMPORTANT: The tasks.md file must be generated using Speckit (speckit.org) via the /speckit.tasks command. We do not support manually created tasks.md files - they follow a specific format that speckit generates from your spec.md and plan.md files.

Stage 1 - INIT: Ensures your workspace is ready by syncing your feature branch with the base branch and validating that spec files exist.

Stage 2 - IMPLEMENTATION: This is the key stage. The workflow iterates over each phase in tasks.md (e.g., "Phase 1: Setup", "Phase 2: Core"). For each phase, it hands ALL tasks in that phase to Claude in a single prompt. Claude then decides how to parallelize tasks marked with [P] using its Task tool. After each phase completes, the workflow runs validation, commits the phase changes, and checkpoints the progress. This phase-level approach gives Claude better context and produces atomic, meaningful commits per phase.

Stage 3 - VALIDATION: Runs format, lint, typecheck, and test stages. If validation fails, the workflow automatically invokes a fixer agent to attempt repairs, retrying up to 3 times.

Stage 4 - CODE REVIEW: Optional stage that can run architecture review and CodeRabbit analysis in parallel. Skippable for simple changes.

Stage 5 - CONVENTION UPDATE: Analyzes if significant patterns were learned during implementation and updates CLAUDE.md if needed.

Stage 6 - PR CREATION: Generates a comprehensive PR description based on commits, reviews, and task context, then creates the PR via GitHub CLI.

Stage 7 - Terminal states indicating success or failure with full context for debugging.

The workflow yields progress events as an async generator, enabling real-time TUI updates.
-->

---
layout: default
---

# Cleanup Workflow - Tech Debt Resolution

Batch processing of GitHub issues by label

<div class="mt-8">

```mermaid
graph LR
    A[Discovery] --> B[Selection]
    B --> C[Processing]
    C --> D[Results]

    style A fill:#334155,stroke:#64748b,stroke-width:2px,color:#e2e8f0
    style B fill:#334155,stroke:#64748b,stroke-width:2px,color:#e2e8f0
    style C fill:#334155,stroke:#64748b,stroke-width:2px,color:#e2e8f0
    style D fill:#334155,stroke:#64748b,stroke-width:2px,color:#e2e8f0
```

</div>

<div class="grid grid-cols-2 gap-6 mt-8">

<div v-click>
  <h3 class="text-indigo-300 mb-2">1. Discovery</h3>
  <div class="text-sm opacity-80">
    List issues by label (e.g., "tech-debt")<br/>
    Fetch issue metadata and comments
  </div>
</div>

<div v-click>
  <h3 class="text-indigo-300 mb-2">2. Selection</h3>
  <div class="text-sm opacity-80">
    Analyze and select up to 3 issues<br/>
    Check for conflicts and dependencies
  </div>
</div>

<div v-click>
  <h3 class="text-indigo-300 mb-2">3. Processing</h3>
  <div class="text-sm opacity-80">
    For each issue: branch → fix → validate → commit → PR<br/>
    Parallel execution (configurable)
  </div>
</div>

<div v-click>
  <h3 class="text-indigo-300 mb-2">4. Results</h3>
  <div class="text-sm opacity-80">
    Aggregate outcomes (fixed, failed, skipped)<br/>
    Usage stats and error reports
  </div>
</div>

</div>

<div v-click class="mt-6 text-sm opacity-70">
  Usage: <code>maverick fly cleanup -i label=tech-debt -i limit=5</code>
</div>

<!--
The Cleanup workflow is designed for batch processing of technical debt and small fixes. It's the workflow you use when you want to knock out multiple GitHub issues in one go.

Discovery phase: Queries GitHub for all open issues with the specified label. Fetches full issue context including comments and labels.

Selection phase: Analyzes the discovered issues to select up to N issues (default 5) that are non-conflicting and can be worked on safely in parallel.

Processing phase: For each selected issue, creates a dedicated branch, implements the fix using IssueFixerAgent, runs validation, commits the changes, and creates a PR. This can happen in parallel for maximum efficiency.

Results phase: Aggregates all outcomes and provides a summary of what was fixed, what failed, and what was skipped, along with token usage statistics.

This workflow is particularly powerful for sprint planning - you can label 20 tech debt issues, run cleanup with limit=5, and have 5 PRs ready for review in one workflow execution.
-->

---
layout: default
---

# Workflow DSL Overview

Declarative workflow definitions with YAML serialization

<div class="grid grid-cols-2 gap-6 mt-6">

<div>

## Step Types

<div class="flex flex-col gap-2 mt-3">
  <div v-click class="px-3 py-2 rounded bg-slate-700/50 text-sm">
    <strong class="text-blue-300">Python</strong> - Execute deterministic operations
  </div>
  <div v-click class="px-3 py-2 rounded bg-slate-700/50 text-sm">
    <strong class="text-indigo-300">Agent</strong> - Invoke AI agent for judgment tasks
  </div>
  <div v-click class="px-3 py-2 rounded bg-slate-700/50 text-sm">
    <strong class="text-purple-300">Generate</strong> - Text generation (commits, PRs)
  </div>
  <div v-click class="px-3 py-2 rounded bg-slate-700/50 text-sm">
    <strong class="text-green-300">Validate</strong> - Run validation stages
  </div>
  <div v-click class="px-3 py-2 rounded bg-slate-700/50 text-sm">
    <strong class="text-yellow-300">Subworkflow</strong> - Compose workflows
  </div>
  <div v-click class="px-3 py-2 rounded bg-slate-700/50 text-sm">
    <strong class="text-orange-300">Checkpoint</strong> - Enable resumption
  </div>
</div>

</div>

<div>

## Flow Control

<div class="flex flex-col gap-2 mt-3">
  <div v-click class="px-3 py-2 rounded bg-slate-700/50 text-sm">
    <strong class="text-blue-300">when:</strong> - Conditional execution
  </div>
  <div v-click class="px-3 py-2 rounded bg-slate-700/50 text-sm">
    <strong class="text-indigo-300">retry:</strong> - Automatic retry with backoff
  </div>
  <div v-click class="px-3 py-2 rounded bg-slate-700/50 text-sm">
    <strong class="text-purple-300">on_failure:</strong> - Fallback handlers
  </div>
  <div v-click class="px-3 py-2 rounded bg-slate-700/50 text-sm">
    <strong class="text-green-300">type: parallel</strong> - Concurrent step groups
  </div>
  <div v-click class="px-3 py-2 rounded bg-slate-700/50 text-sm">
    <strong class="text-yellow-300">$&#123;&#123; &#125;&#125;</strong> - Template expressions, ternary conditionals
  </div>
</div>

</div>

</div>

<div v-click class="mt-6">

## Example: Simple Validation Workflow

```yaml
version: "1.0"
name: quick-validate
inputs:
  stages: { type: array, required: true }

steps:
  - name: format
    type: python
    action: run_validation_stage
    kwargs:
      stage: format
    when: ${{ 'format' in inputs.stages }}

  - name: lint
    type: python
    action: run_validation_stage
    kwargs:
      stage: lint
    when: ${{ 'lint' in inputs.stages }}
    retry:
      max_attempts: 2
      backoff: exponential
```

</div>

<!--
The Workflow DSL provides a declarative way to define complex multi-step workflows in YAML, making them easy to understand, version, and share.

Step Types cover all the patterns you need:
- Python steps for deterministic operations like git commands or file operations
- Agent steps invoke AI agents for tasks requiring judgment
- Generate steps are specialized for text generation like commit messages
- Validate steps run validation stages with automatic retry
- Subworkflow steps enable composition and reuse
- Checkpoint steps save state to enable workflow resumption

Flow Control gives you powerful orchestration:
- Conditional execution with when clauses using expression syntax
- Automatic retry with configurable backoff strategies
- Error handling with fallback steps
- Parallel step groups for concurrent execution
- Template expressions to reference inputs and previous step outputs

The example shows a simple validation workflow that conditionally runs format and lint stages based on inputs. The lint stage has retry enabled with exponential backoff.

This DSL enables you to define complex workflows without writing Python code, while still having the full power of the SDK available when you need it.
-->

---
layout: default
---

# DSL Expression Syntax

<div class="grid grid-cols-2 gap-4 mt-4">

<div>

## Basic References

<div class="flex flex-col gap-1 mt-2 text-sm">
  <div v-click class="px-2 py-1 rounded bg-slate-700/50">
    <code class="text-blue-300">$&#123;&#123; inputs.name &#125;&#125;</code> - Input values
  </div>
  <div v-click class="px-2 py-1 rounded bg-slate-700/50">
    <code class="text-indigo-300">$&#123;&#123; steps.x.output &#125;&#125;</code> - Step outputs
  </div>
  <div v-click class="px-2 py-1 rounded bg-slate-700/50">
    <code class="text-purple-300">$&#123;&#123; item &#125;&#125;</code> / <code class="text-green-300">$&#123;&#123; index &#125;&#125;</code> - Loop vars
  </div>
</div>

## Operators

<div class="flex flex-col gap-1 mt-2 text-sm">
  <div v-click class="px-2 py-1 rounded bg-slate-700/50">
    <code class="text-yellow-300">not</code>, <code class="text-orange-300">and</code>, <code class="text-orange-300">or</code> - Boolean ops
  </div>
  <div v-click class="px-2 py-1 rounded bg-slate-700/50">
    <code class="text-red-300">x if cond else y</code> - Ternary
  </div>
</div>

</div>

<div>

## Ternary Example

```yaml
steps:
  - name: create_pr
    type: python
    action: create_github_pr
    kwargs:
      title: ${{ inputs.title if inputs.title
                else steps.gen.output }}
      base: ${{ 'develop' if inputs.env == 'staging'
                else 'main' }}
```

<div v-click class="mt-2 p-2 bg-green-500/20 border border-green-500 rounded text-xs">
<strong>Syntax:</strong> <code>value if condition else fallback</code>
</div>

</div>

</div>

<!--
The DSL expression syntax provides powerful templating capabilities within workflow definitions.

Basic References:
- inputs.name accesses workflow input parameters
- steps.x.output references the output of a previous step named "x"
- item and index are available within for_each loops

Operators for complex conditions:
- not for boolean negation (e.g., not inputs.skip)
- and/or for combining conditions (e.g., inputs.a and inputs.b)
- Ternary if/else for inline value selection

The ternary expression follows Python syntax: value_if_true if condition else value_if_false

This is particularly useful for:
- Providing fallback values when inputs are optional
- Selecting between different configurations based on conditions
- Avoiding separate branch steps for simple value selection

The example shows using ternary expressions to select PR title (use provided or fallback to generated) and base branch (develop for staging, main otherwise).
-->
