# Part 1: Introduction & Vision

---
layout: center
class: text-center
---

# What is Maverick?

<div class="text-xl text-slate-300 mt-8 mb-12">
AI-Powered Development Workflow Orchestration
</div>

<div v-click class="grid grid-cols-2 gap-4 mx-auto max-w-4xl text-left">
  <div class="p-6 rounded-lg bg-slate-800/50 border border-slate-700">
    <div class="text-3xl mb-3">🤖</div>
    <h3 class="text-lg font-semibold mb-2 text-white">Autonomous Agents</h3>
    <p class="text-sm text-slate-400">
      AI agents that make decisions, handle failures, and work independently
    </p>
  </div>

  <div v-click class="p-6 rounded-lg bg-slate-800/50 border border-slate-700">
    <div class="text-3xl mb-3">⚡</div>
    <h3 class="text-lg font-semibold mb-2 text-white">Complete Automation</h3>
    <p class="text-sm text-slate-400">
      From task list to merged PR - implementation, review, validation, and deployment
    </p>
  </div>

  <div v-click class="p-6 rounded-lg bg-slate-800/50 border border-slate-700">
    <div class="text-3xl mb-3">🎯</div>
    <h3 class="text-lg font-semibold mb-2 text-white">Built on Claude</h3>
    <p class="text-sm text-slate-400">
      Powered by Claude Agent SDK + Textual for intelligent, interactive workflows
    </p>
  </div>

  <div v-click class="p-6 rounded-lg bg-slate-800/50 border border-slate-700">
    <div class="text-3xl mb-3">🔄</div>
    <h3 class="text-lg font-semibold mb-2 text-white">Resilient Operation</h3>
    <p class="text-sm text-slate-400">
      Self-healing workflows with retries, checkpointing, and graceful degradation
    </p>
  </div>
</div>

<div v-click class="mt-12">
  <Terminal :commands="[
    { command: 'maverick fly', output: '✓ Implementing feature from spec...\n✓ Running parallel code reviews...\n✓ Fixing validation issues...\n✓ Creating pull request #142' }
  ]" />
</div>

<!--
Maverick is not just another automation tool - it's a complete AI-powered development workflow orchestration system. Unlike simple scripts or CI/CD pipelines, Maverick uses autonomous AI agents that can make intelligent decisions, adapt to failures, and work independently.

Key differentiator: The agents don't just execute commands - they analyze situations, make judgment calls, and recover from failures without human intervention. This is what enables true unattended operation.

The terminal example shows the simplicity from a user perspective - one command triggers an entire workflow from implementation through PR creation.
-->

---
layout: two-cols
---

# The Problem Maverick Solves

<div class="text-slate-300 mb-6">
Modern development workflows are stuck between two extremes
</div>

## Manual Workflows 😓

<div v-click class="space-y-4 text-sm">

**Repetitive & Time-Consuming**
- Create branch, sync with main
- Implement feature/fix
- Format, lint, test, fix issues
- Code review (self + peer)
- Create PR, write description
- Address review feedback

<div class="p-3 bg-red-900/20 border border-red-700 rounded mt-4">
  <strong class="text-red-400">Problem:</strong> 30-60 minutes of repetitive work per feature
</div>

</div>

::right::

<div class="pl-8">

<div v-click>

## Traditional Automation 🤖

<div class="space-y-4 text-sm mt-6">

**Rigid & Brittle**
- CI/CD pipelines run checks
- Scripts automate specific tasks
- No judgment or adaptation
- Fails on unexpected conditions

<div class="p-3 bg-yellow-900/20 border border-yellow-700 rounded mt-4">
  <strong class="text-yellow-400">Problem:</strong> Cannot handle failures or make decisions
</div>

</div>

</div>

<div v-click class="mt-12">

## The Gap 🎯

<div class="space-y-3 text-sm mt-6">

**What's Missing:**
- ✗ Unattended operation with judgment
- ✗ Failure recovery and self-healing
- ✗ Adaptability to edge cases
- ✗ End-to-end orchestration

<div class="p-4 bg-indigo-900/20 border border-indigo-500 rounded-lg mt-6">
  <strong class="text-indigo-300">Maverick bridges this gap</strong> with autonomous agents that think, adapt, and recover
</div>

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
  description="Work from structured specifications with automated task generation and tracking"
/>

</div>

<div v-click class="mt-12 flex justify-center gap-8 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-3 h-3 rounded-full bg-green-500"></span>
    <span class="text-slate-400">Production Ready</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-3 h-3 rounded-full bg-blue-500"></span>
    <span class="text-slate-400">Fully Async</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-3 h-3 rounded-full bg-purple-500"></span>
    <span class="text-slate-400">Type Safe</span>
  </div>
</div>

<div v-click class="mt-8">
  <FlowDiagram :steps="[
    { name: 'Spec', class: 'bg-indigo-600 text-white' },
    { name: 'Implement', class: 'bg-blue-600 text-white' },
    { name: 'Review', class: 'bg-purple-600 text-white' },
    { name: 'Validate', class: 'bg-green-600 text-white' },
    { name: 'PR', class: 'bg-teal-600 text-white' }
  ]" />
</div>

<!--
This slide showcases Maverick's six core capabilities that make it a complete solution:

1. **Autonomous Agent Execution**: Not just running commands, but making intelligent decisions. Agents can analyze code, determine what to fix, and iterate until tests pass.

2. **Smart Workflow Orchestration**: The DSL enables complex workflows with parallel execution (run multiple reviews simultaneously), conditional logic (skip validation if no code changed), and checkpoint recovery (resume from failure).

3. **Interactive TUI**: Built on Textual, provides a rich terminal interface with live updates, log streaming, and the ability to pause/resume workflows.

4. **Resilient Operation**: Enterprise-grade reliability with automatic retries (with exponential backoff), checkpointing (so you don't lose progress), graceful degradation (continue with partial failures), and comprehensive error handling.

5. **Extensible Architecture**: Clean separation of concerns (agents vs workflows vs tools) makes it easy to add custom behavior. Write a new agent, define a new workflow, or integrate a new tool.

6. **Spec-Driven Development**: Start with a structured specification, automatically generate implementation tasks, and track progress. Ensures consistency and documentation.

The bottom flow diagram shows the typical end-to-end journey - from spec to merged PR.
-->
