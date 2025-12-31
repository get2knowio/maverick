---
layout: section
class: text-center
---

# Part 3: Agent System

AI-Powered Task Execution with Type Safety and Least Privilege

---
layout: default
---

# MaverickAgent Base Class

<div class="text-sm text-slate-400 -mt-2 mb-3">Generic base class for all agents with type safety and tool constraints</div>

```python {all|1-3|5-9|11-13}
from typing import Generic, TypeVar
TContext = TypeVar("TContext", contravariant=True)
TResult = TypeVar("TResult", covariant=True)

class MaverickAgent(ABC, Generic[TContext, TResult]):
    name: str                    # Unique identifier
    system_prompt: str           # Claude behavior definition
    allowed_tools: list[str]     # Explicit tool allowlist
    model: str                   # Claude model ID

    @abstractmethod
    async def execute(self, context: TContext) -> TResult:
        """Execute agent task with specialized context/result types"""
```

<div v-click class="mt-4 p-3 bg-gradient-to-r from-cyan-500/10 to-cyan-600/10 border-l-4 border-cyan-500 rounded text-sm">

**Key Design Principles:** Generic types with variance | Tool allowlists enforce least privilege (FR-002) | Immutable results via AgentResult | No retries - workflows handle recovery (FR-007)

</div>

---
layout: default
---

# Built-in Tools & Permissions

<div class="text-sm text-slate-400 -mt-2 mb-3">Claude Agent SDK tools available to agents based on role constraints</div>

<div class="grid grid-cols-2 gap-4">

<div v-click="1">

### Available Built-in Tools

```python
BUILTIN_TOOLS: frozenset[str] = frozenset({
    "Read", "Write", "Edit",   # File operations
    "Bash",                    # Execute commands
    "Glob", "Grep",            # Search tools
    "NotebookEdit",            # Jupyter editing
    "WebFetch", "WebSearch",   # Web access
    "TodoWrite",               # Task tracking
})
```

</div>

<div v-click="2">

### Tool Validation

```python {all|3-5|7-9}
def _validate_tools(self, allowed_tools, mcp_servers):
    """Validate tools at construction time"""
    mcp_prefixes = {
        f"mcp__{s}__" for s in mcp_servers
    }
    for tool in allowed_tools:
        if tool not in BUILTIN_TOOLS:
            if not any(tool.startswith(p) for p in mcp_prefixes):
                raise InvalidToolError(tool)
```

</div>

</div>

<div v-click="3" class="mt-3 p-2 bg-amber-500/10 border-l-4 border-amber-500 rounded text-sm">

**Security Note:** Tools validated at agent construction time, preventing runtime tool escalation.

</div>

---
layout: default
---

# Built-in Agents

Four specialized agent types for different workflow phases

<div class="grid grid-cols-2 gap-4 mt-6">

<div v-click="1">

<AgentCard
  name="ImplementerAgent"
  type="implementer"
  description="Executes tasks from tasks.md files using TDD approach with parallel task support"
  :tools="['Read', 'Write', 'Edit', 'Glob', 'Grep']"
/>

</div>

<div v-click="2">

<AgentCard
  name="CodeReviewerAgent"
  type="reviewer"
  description="Analyzes git diffs and categorizes findings by severity (CRITICAL/MAJOR/MINOR/SUGGESTION)"
  :tools="['Read', 'Glob', 'Grep']"
/>

</div>

<div v-click="3">

<AgentCard
  name="IssueFixerAgent"
  type="fixer"
  description="Resolves GitHub issues automatically by investigating and applying targeted fixes"
  :tools="['Read', 'Write', 'Edit', 'Glob', 'Grep']"
/>

</div>

<div v-click="4">

<AgentCard
  name="Generator Agents"
  type="generator"
  description="Generate commit messages, PR descriptions, and error explanations (stateless text generation)"
  :tools="[]"
/>

</div>

</div>

<div v-click="5" class="mt-6 p-4 bg-gradient-to-r from-purple-500/10 to-purple-600/10 border-l-4 border-purple-500 rounded">

**Separation of Concerns:** Agents know **HOW** to do tasks. Workflows know **WHEN** to do them.

</div>

---
layout: two-cols-header
---

# Agent Tool Permissions

<div class="text-sm text-slate-400 -mt-2 mb-2">Constrained tool sets based on principle of least privilege</div>

::left::

<div v-click="1">

### Read-Only Agents

```python
# CodeReviewerAgent - analysis only
REVIEWER_TOOLS = frozenset({"Read", "Glob", "Grep"})
```

<div class="mt-2 text-xs text-slate-400">Reviewers analyze but never modify code.</div>

</div>

<div v-click="3" class="mt-4">

### Modification Agents

```python
# ImplementerAgent - code changes
IMPLEMENTER_TOOLS = frozenset({
    "Read", "Write", "Edit", "Glob", "Grep"
})  # No Bash - validation by orchestration
```

<div class="mt-2 text-xs text-slate-400">Test execution is an orchestration concern.</div>

</div>

::right::

<div v-click="2">

### Targeted Fix Agents

```python
# FixerAgent - minimal permissions
FIXER_TOOLS = frozenset({"Read", "Write", "Edit"})
# No search - receives explicit file paths
```

<div class="mt-2 text-xs text-slate-400">Fixers receive explicit paths from workflows.</div>

</div>

<div v-click="4" class="mt-4">

### Stateless Generators

```python
# Generator Agents - no tools at all
GENERATOR_TOOLS = frozenset()
# CommitMessageGenerator, PRDescriptionGenerator
```

<div class="mt-2 text-xs text-slate-400">Context provided in prompts, no file access needed.</div>

</div>

---
layout: default
---

# Agent Execution Flow

<div class="text-sm text-slate-400 -mt-2 mb-3">How agents interact with Claude SDK and return structured results</div>

```python {all|1-4|6-9|11-15}
async def execute(self, context: ImplementerContext) -> ImplementationResult:
    # 1. Parse tasks from tasks.md
    tasks = TaskFile.parse(context.task_file).pending_tasks

    # 2. Execute each task via Claude SDK
    task_results = []
    for task in tasks:
        messages = [m async for m in self.query(prompt, cwd=context.cwd)]
        output = extract_all_text(messages)
        # 3. Extract structured output and commit
        files_changed = await self._detect_file_changes(context.cwd)
        commit_sha = await self._create_commit(task, context)
        task_results.append(TaskResult(output, files_changed, commit_sha))

    return ImplementationResult(success=all(r.ok for r in task_results), ...)
```

<div v-click class="mt-4 p-3 bg-gradient-to-r from-emerald-500/10 to-emerald-600/10 border-l-4 border-emerald-500 rounded text-sm">

**Error Handling:** One task failure does not crash the entire workflow (Constitution IV: Fail Gracefully)

</div>

---
layout: default
---

# CodeReviewerAgent Deep Dive

<div class="text-sm text-slate-400 -mt-2 mb-2">Architecture review with severity categorization</div>

<div class="grid grid-cols-2 gap-4">

<div>

### Review Process

```python
# 1. Check conflicts, get diff + conventions
has_conflicts = await self._check_merge_conflicts(ctx)
diff_stats, conventions = await asyncio.gather(
    self._get_diff_stats(ctx), self._read_conventions(ctx))
# 2. Apply truncation, then review
files = diff_stats["files"][:MAX_DIFF_FILES]
findings = await self._review_and_parse(...)
```

</div>

<div>

### Review Dimensions

<div v-click="1" class="mb-1">

```python
class ReviewSeverity(str, Enum):
    CRITICAL = "critical"   # Security, data loss
    MAJOR = "major"         # Logic errors
    MINOR = "minor"         # Style issues
    SUGGESTION = "suggestion"
```

</div>

<div v-click="2">

```python
class ReviewFinding(BaseModel):
    severity: ReviewSeverity
    file: str; line: int | None
    message: str; suggestion: str
```

</div>

<div v-click="3" class="mt-2 p-2 bg-purple-500/10 border-l-4 border-purple-500 rounded text-sm">

**Actionable Feedback:** Explanation, code fix, convention reference.

</div>

</div>

</div>

---
layout: default
---

# Generator Agents

<div class="text-sm text-slate-400 -mt-2 mb-2">Stateless text generation from provided context</div>

<div class="grid grid-cols-2 gap-4">

<div v-click="1">

### CommitMessageGenerator

```python
class CommitMessageGenerator(GeneratorAgent):
    def __init__(self):
        super().__init__("commit-message", allowed_tools=[])

    async def execute(self, ctx: CommitContext) -> str:
        prompt = f"Generate commit: {ctx.task_description}"
        msgs = [m async for m in self.query(prompt)]
        return extract_all_text(msgs)
```

</div>

<div v-click="2">

### PRDescriptionGenerator

```python
class PRDescriptionGenerator(GeneratorAgent):
    def __init__(self):
        super().__init__("pr-description", allowed_tools=[])

    async def execute(self, ctx: PRContext) -> str:
        prompt = f"Generate PR for: {ctx.branch}"
        return await self._generate_text(prompt)
```

</div>

</div>

<div v-click="3" class="mt-4 p-3 bg-gradient-to-r from-cyan-500/10 to-cyan-600/10 border-l-4 border-cyan-500 rounded">

**Why No Tools?** Generators receive all context in prompts (commit messages, diff stats, task descriptions). No file access needed - text in, text out.

</div>

---
layout: center
class: text-center
---

# Agent System Summary

<div class="grid grid-cols-3 gap-6 mt-12">

<div v-click="1" class="p-6 bg-gradient-to-br from-cyan-500/20 to-cyan-600/10 border-l-4 border-cyan-500 rounded-xl">

### Type Safety

Generic base class with contravariant context and covariant result types

</div>

<div v-click="2" class="p-6 bg-gradient-to-br from-purple-500/20 to-purple-600/10 border-l-4 border-purple-500 rounded-xl">

### Least Privilege

Tool permissions constrained by role with validation at construction time

</div>

<div v-click="3" class="p-6 bg-gradient-to-br from-emerald-500/20 to-emerald-600/10 border-l-4 border-emerald-500 rounded-xl">

### Separation of Concerns

Agents know HOW, workflows know WHEN, TUI presents state

</div>

</div>

<div v-click="4" class="mt-12 text-2xl text-slate-300">

Next: **Workflow Orchestration** - How agents compose into multi-phase pipelines

</div>
