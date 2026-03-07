   ---
   layout: section
   class: text-center
   ---

   # 11. Project Overview & Philosophy

   <div class="text-lg text-secondary mt-4">
   Understanding Maverick's current architecture and design principles
   </div>

   <div class="mt-8 flex justify-center gap-6 text-sm">
     <div class="flex items-center gap-2">
       <span class="w-2 h-2 rounded-full bg-teal"></span>
       <span class="text-muted">7 Slides</span>
     </div>
     <div class="flex items-center gap-2">
       <span class="w-2 h-2 rounded-full bg-brass"></span>
       <span class="text-muted">Python Workflows</span>
     </div>
     <div class="flex items-center gap-2">
       <span class="w-2 h-2 rounded-full bg-coral"></span>
       <span class="text-muted">ACP Execution</span>
     </div>
   </div>

   ---
   ## layout: two-cols

   # 11.1 What is Maverick?

   <div class="pr-4">

   ## AI-Powered Workflow Orchestration

   Maverick is a Python CLI/TUI application that automates development workflows with a clear separation between orchestration, judgment, and deterministic execution.

   <div v-click class="mt-4">

   ## Key Differentiators

   <div class="space-y-2 mt-2">
     <div class="flex items-start gap-2">
       <span class="text-brass mt-1">●</span>
       <div>
         <span class="font-semibold">Python Workflow Engine</span>
         <p class="text-sm text-muted">Built-in workflows are Python classes, not YAML definitions</p>
       </div>
     </div>
     <div class="flex items-start gap-2">
       <span class="text-teal mt-1">●</span>
       <div>
         <span class="font-semibold">ACP-Based Agent Execution</span>
         <p class="text-sm text-muted">AI steps run through an ACP subprocess via <code>AcpStepExecutor</code></p>
       </div>
     </div>
     <div class="flex items-start gap-2">
       <span class="text-coral mt-1">●</span>
       <div>
         <span class="font-semibold">Component Registry</span>
         <p class="text-sm text-muted">Actions, agents, and generators are discovered by name</p>
       </div>
     </div>
   </div>

   </div>

   </div>

   ::right::

   <div class="pl-4">

   <div class="mt-12">

   ## Built With

   ```yaml
   language: Python 3.10+
   workflow_engine: PythonWorkflow
   agent_runtime: Agent Client Protocol (ACP)
   executor: AcpStepExecutor
   cli: Click
   tui: Textual
   config: Pydantic + YAML
   ```

   </div>

   <div v-click class="mt-6">

   ## Primary Commands

   ```bash
   maverick fly
   maverick land
   maverick refuel speckit <spec>
   maverick workspace status
   ```

   </div>

   </div>

   ---
   ## layout: default

   # 11.2 Architecture Overview

   <div class="mt-4">

   ```
   CLI Command
     -> PythonWorkflow (orchestration)
       -> Actions (deterministic steps: git, validation, beads)
       -> AcpStepExecutor (AI agent steps)
         -> ACP subprocess (claude-agent-acp)
           -> Claude API
   ```

   </div>

   <div class="grid grid-cols-5 gap-3 mt-6">
     <div class="p-3 rounded-lg bg-indigo-500/20 border border-indigo-500/50 text-center">
       <div class="text-2xl">🖥️</div>
       <div class="text-xs font-semibold mt-1">CLI</div>
       <div class="text-xs text-muted">Commands & rendering</div>
     </div>
     <div class="p-3 rounded-lg bg-purple-500/20 border border-purple-500/50 text-center">
      <div class="text-2xl">🧭</div>
       <div class="text-xs font-semibold mt-1">Workflows</div>
       <div class="text-xs text-muted">WHAT & WHEN</div>
     </div>
     <div class="p-3 rounded-lg bg-teal/20 border border-teal/50 text-center">
       <div class="text-2xl">⚙️</div>
       <div class="text-xs font-semibold mt-1">Actions</div>
       <div class="text-xs text-muted">Deterministic side effects</div>
     </div>
     <div class="p-3 rounded-lg bg-brass/20 border border-brass/50 text-center">
       <div class="text-2xl">🤖</div>
       <div class="text-xs font-semibold mt-1">Executor</div>
       <div class="text-xs text-muted">ACP session runtime</div>
     </div>
     <div class="p-3 rounded-lg bg-coral/20 border border-coral/50 text-center">
       <div class="text-2xl">🔧</div>
       <div class="text-xs font-semibold mt-1">Agents</div>
       <div class="text-xs text-muted">Prompt builders</div>
     </div>
   </div>

   <div v-click class="mt-6 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm text-center">
     <strong class="text-teal">Important</strong> — the YAML workflow DSL was removed. All live workflows are now Python classes under <code>src/maverick/workflows/</code>.
   </div>

   ---
   ## layout: two-cols

   # 11.3 Separation of Concerns

   <div class="pr-4">

   ## Agents: <strong>HOW</strong>

   <div class="p-3 bg-teal/10 border border-teal/30 rounded-lg mt-2 text-sm">
   - Build prompts from typed context
   - Declare instructions and allowed tools
   - Provide judgment only
   - Do <strong>not</strong> own commits, retries, or validation policies
   </div>

   <div v-click class="mt-4">

   ## Workflows: <strong>WHAT & WHEN</strong>

   <div class="p-3 bg-purple-500/10 border border-purple-500/30 rounded-lg mt-2 text-sm">
   - Sequence steps
   - Register rollbacks
   - Save checkpoints
   - Call deterministic actions and ACP-backed agent steps
   </div>

   </div>

   </div>

   ::right::

   <div class="pl-4 mt-8">

   ## TUI: <strong>Display Only</strong>

   <div class="p-3 bg-coral/10 border border-coral/30 rounded-lg mt-2 text-sm">
   - Renders the unified event stream
   - Captures user input
   - Never runs subprocesses or network calls itself
   </div>

   <div v-click class="mt-4">

   ## Actions & Tools: <strong>External Systems</strong>

   <div class="p-3 bg-brass/10 border border-brass/30 rounded-lg mt-2 text-sm">
   - Actions wrap deterministic operations
   - Optional MCP servers extend tool access
   - ACP permission handling controls what agents may invoke
   </div>

   </div>

   </div>

   ---
   ## layout: default

   # 11.4 What Changed in 041 + 042?

   <div class="grid grid-cols-2 gap-6 mt-6">
     <div class="p-4 bg-coral/10 border border-coral/30 rounded-lg">
       <div class="font-semibold text-coral">041 — YAML DSL removed</div>
       <ul class="text-sm text-muted mt-3 space-y-2">
         <li>• no YAML workflow definitions</li>
         <li>• no expression engine driving runtime flow</li>
         <li>• PythonWorkflow is now the orchestration base class</li>
       </ul>
     </div>
     <div class="p-4 bg-teal/10 border border-teal/30 rounded-lg">
       <div class="font-semibold text-teal">042 — ACP integration</div>
       <ul class="text-sm text-muted mt-3 space-y-2">
         <li>• no direct in-process Claude SDK execution</li>
         <li>• AI steps run through <code>claude-agent-acp</code></li>
         <li>• streaming, permissions, and retries moved into the executor layer</li>
       </ul>
     </div>
   </div>

   ---
   ## layout: default

   # 11.5 Core Principles

   <div class="grid grid-cols-2 gap-4 mt-4">
     <PrincipleCard number="1" title="Async-First" color="teal">
     All workflow execution and agent orchestration are async. No blocking subprocess work on the event loop.
     </PrincipleCard>
     <PrincipleCard number="2" title="Dependency Injection" color="purple">
     Config, registry, checkpoint store, and executor are passed into workflows explicitly.
     </PrincipleCard>
     <PrincipleCard number="3" title="Fail Gracefully" color="coral">
     Retry, checkpoint, and rollback behavior live in the workflow/executor layers so failures do not crash everything.
     </PrincipleCard>
     <PrincipleCard number="4" title="Typed Contracts" color="amber">
     Dataclasses and Pydantic models define events, results, config, and structured agent outputs.
     </PrincipleCard>
   </div>

   ---
   ## layout: default

   # 11.6 Project Structure Tour

   <div class="grid grid-cols-2 gap-6 mt-4">
   <div>

   ```
   src/maverick/
   ├── cli/                 # Click commands and rendering
   ├── workflows/           # Python workflow packages
   ├── executor/            # StepExecutor protocol + ACP adapter
agents/              # MaverickAgent classes    
   ├── registry/            # Component registries
   ├── checkpoint/          # File and memory stores
   ├── workspace/           # Hidden workspace lifecycle
   ├── jj/                  # Write-path VCS wrapper
   ├── git/                 # Read-path GitPython wrapper
   ├── events.py            # Progress events
   ├── results.py           # StepResult / WorkflowResult
   └── types.py             # StepType / StepMode / AutonomyLevel
   ```

   </div>

   <div class="space-y-4 text-sm">
     <div><strong>workflows/</strong><br><span class="text-muted">Pure Python orchestration, including fly, refuel, and flight-plan flows.</span></div>
     <div><strong>executor/</strong><br><span class="text-muted">Provider-agnostic execution contract plus ACP implementation.</span></div>
     <div><strong>registry/</strong><br><span class="text-muted">Action, agent, and generator lookup by name.</span></div>
     <div><strong>workspace/ + jj/</strong><br><span class="text-muted">Hidden workspace creation and write-path version control.</span></div>
   </div>
   </div>
