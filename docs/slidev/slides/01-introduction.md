---
layout: section
class: text-center
---

# Part 1: Introduction & Vision

Autonomous AI-Powered Development Workflow Orchestration

---
layout: center
class: text-center
---

# What is Maverick?

<div class="text-lg text-secondary mt-4 mb-8">
AI-Powered Development Workflow Orchestration
</div>

<div class="grid grid-cols-2 gap-3 mx-auto max-w-3xl text-left">
  <div v-click class="feature-card p-4">
    <div class="flex items-center gap-2 mb-2">
      <span class="text-xl">🤖</span>
      <h3 class="text-sm font-semibold text-primary">Autonomous Agents</h3>
    </div>
    <p class="text-xs text-muted leading-relaxed">
      AI agents that make decisions, handle failures, and work independently
    </p>
  </div>

  <div v-click class="feature-card p-4">
    <div class="flex items-center gap-2 mb-2">
      <span class="text-xl">⚡</span>
      <h3 class="text-sm font-semibold text-primary">Complete Automation</h3>
    </div>
    <p class="text-xs text-muted leading-relaxed">
      From task list to merged PR - implementation, review, and validation
    </p>
  </div>

  <div v-click class="feature-card p-4">
    <div class="flex items-center gap-2 mb-2">
      <span class="text-xl">🎯</span>
      <h3 class="text-sm font-semibold text-primary">Built on Claude</h3>
    </div>
    <p class="text-xs text-muted leading-relaxed">
      Powered by Claude Agent SDK + Textual for intelligent workflows
    </p>
  </div>

  <div v-click class="feature-card p-4">
    <div class="flex items-center gap-2 mb-2">
      <span class="text-xl">🔄</span>
      <h3 class="text-sm font-semibold text-primary">Resilient Operation</h3>
    </div>
    <p class="text-xs text-muted leading-relaxed">
      Self-healing workflows with retries, checkpointing, and recovery
    </p>
  </div>
</div>

<div v-click class="mt-8 flex justify-center gap-6 text-xs">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">YAML-Based DSL</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">MCP Tool Integration</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Interactive TUI</span>
  </div>
</div>

<!--
Maverick is not just another automation tool - it's a complete AI-powered development workflow orchestration system. Unlike simple scripts or CI/CD pipelines, Maverick uses autonomous AI agents that can make intelligent decisions, adapt to failures, and work independently.

Key differentiator: The agents don't just execute commands - they analyze situations, make judgment calls, and recover from failures without human intervention. This is what enables true unattended operation.

The status indicators at the bottom highlight the three pillars: YAML DSL for workflow definition, MCP tools for external integrations, and the Textual-based TUI for real-time visibility.
-->

---
layout: two-cols
---

# The Problem Maverick Solves

<div class="text-slate-300 text-sm mb-4">
Modern development workflows are stuck between two extremes
</div>

## Manual Workflows 😓

<div v-click class="space-y-2 text-xs">

**Repetitive & Time-Consuming**
- Create branch, sync with main
- Implement feature/fix
- Format, lint, test, fix issues
- Code review and create PR

<div class="p-2 bg-red-900/20 border border-red-700 rounded mt-2">
  <strong class="text-red-400">Problem:</strong> 30-60 min of repetitive work
</div>

</div>

<div v-click class="mt-4">

## The Gap 🎯

<div class="space-y-2 text-xs mt-2">

**What's Missing:**
- ✗ Unattended operation with judgment
- ✗ Failure recovery and self-healing
- ✗ End-to-end orchestration

<div class="p-2 bg-[hsl(var(--g2k-teal)/0.15)] border border-[hsl(var(--g2k-teal)/0.5)] rounded mt-2">
  <strong class="text-teal text-xs">Maverick bridges this gap</strong>
</div>

</div>

</div>

::right::

<div class="pl-6">

<div v-click>

## Traditional Automation 🤖

<div class="space-y-2 text-xs mt-2">

**Rigid & Brittle**
- CI/CD pipelines run checks
- Scripts automate specific tasks
- No judgment or adaptation
- Fails on unexpected conditions

<div class="p-2 bg-yellow-900/20 border border-yellow-700 rounded mt-2">
  <strong class="text-yellow-400">Problem:</strong> Cannot handle failures or make decisions
</div>

</div>

</div>

<div v-click class="mt-4 p-3 bg-slate-800/50 border border-slate-600 rounded">

**Maverick's Solution:**
<div class="text-xs text-slate-300 mt-1">
Autonomous AI agents that think, adapt, and recover - enabling true unattended operation from task list to merged PR.
</div>

</div>

</div>

<!--
This slide establishes the core problem that Maverick solves. The development workflow bottleneck is real - developers spend significant time on repetitive tasks that require some judgment but not deep creative thinking.

Traditional automation (CI/CD, scripts) handles the "dumb" parts but fails when anything goes wrong. It can't make decisions like:
- "This test failed, but it's flaky - should I retry?"
- "The linter wants this formatted differently - should I fix it?"
- "This code review suggests a refactor - is it worth doing now?"

Maverick's autonomous agents fill this gap by bringing AI-powered decision-making to automation. They can handle the unexpected, make judgment calls, and recover from failures - enabling true unattended operation.
-->

---
layout: center
class: text-center
---

# Key Features Overview

<div class="text-xl text-slate-300 mt-4 mb-12">
Six capabilities that make Maverick powerful and extensible
</div>

<div class="grid grid-cols-3 gap-4 max-w-6xl mx-auto text-left">

<FeatureCard
  v-click
  icon="🤖"
  title="Autonomous Agent Execution"
  description="AI agents handle implementation, review, and fixes independently with decision-making capabilities"
/>

<FeatureCard
  v-click
  icon="⚡"
  title="Smart Workflow Orchestration"
  description="DSL-based workflows with parallel execution, conditional logic, and checkpoint recovery"
/>

<FeatureCard
  v-click
  icon="📺"
  title="Interactive TUI"
  description="Real-time visibility into agent operations with live logs, metrics, and control"
/>

<FeatureCard
  v-click
  icon="🛡️"
  title="Resilient Operation"
  description="Automatic retries, checkpointing, graceful degradation, and comprehensive error handling"
/>

<FeatureCard
  v-click
  icon="🔧"
  title="Extensible Architecture"
  description="Custom workflows, agents, and MCP tools with clear separation of concerns"
/>

<FeatureCard
  v-click
  icon="📋"
  title="Spec-Driven Development"
  description="Work from structured specifications with task generation via Speckit (speckit.org)"
/>

</div>

<div v-click class="mt-12 flex justify-center gap-8 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-3 h-3 rounded-full bg-[hsl(var(--g2k-success))]"></span>
    <span class="text-muted">Production Ready</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-3 h-3 rounded-full bg-[hsl(var(--g2k-teal))]"></span>
    <span class="text-muted">Fully Async</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-3 h-3 rounded-full bg-[hsl(var(--g2k-coral))]"></span>
    <span class="text-muted">Type Safe</span>
  </div>
</div>

<div v-click class="mt-8">
  <FlowDiagram :steps="[
    { name: 'Spec', class: 'bg-[hsl(var(--g2k-brass))] text-[hsl(var(--g2k-bg-base))]' },
    { name: 'Implement', class: 'bg-[hsl(var(--g2k-teal))] text-white' },
    { name: 'Review', class: 'bg-[hsl(var(--g2k-coral))] text-white' },
    { name: 'Validate', class: 'bg-[hsl(var(--g2k-success))] text-white' },
    { name: 'PR', class: 'bg-[hsl(var(--g2k-copper))] text-white' }
  ]" />
</div>

<!--
This slide showcases Maverick's six core capabilities that make it a complete solution:

1. **Autonomous Agent Execution**: Not just running commands, but making intelligent decisions. Agents can analyze code, determine what to fix, and iterate until tests pass.

2. **Smart Workflow Orchestration**: The DSL enables complex workflows with parallel execution (run multiple reviews simultaneously), conditional logic (skip validation if no code changed), and checkpoint recovery (resume from failure).

3. **Interactive TUI**: Built on Textual, provides a rich terminal interface with live updates, log streaming, and the ability to pause/resume workflows.

4. **Resilient Operation**: Enterprise-grade reliability with automatic retries (with exponential backoff), checkpointing (so you don't lose progress), graceful degradation (continue with partial failures), and comprehensive error handling.

5. **Extensible Architecture**: Clean separation of concerns (agents vs workflows vs tools) makes it easy to add custom behavior. Write a new agent, define a new workflow, or integrate a new tool.

6. **Spec-Driven Development**: Start with a structured specification, use Speckit (speckit.org) to generate tasks.md via the /speckit.tasks command, and track progress. Manual creation of tasks.md is not supported - Speckit ensures the correct format.

The bottom flow diagram shows the typical end-to-end journey - from spec to merged PR.
-->
