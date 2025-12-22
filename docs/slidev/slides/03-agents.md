# Part 3: Agent System

---
layout: default
---

# MaverickAgent Base Class

Generic base class for all agents with type safety and tool constraints

```python {all|1-5|7-11|13-16|all}
from typing import Generic, TypeVar

# Type parameters for specialized contexts and results
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
        ...
```

<div v-click class="mt-8 p-4 bg-gradient-to-r from-cyan-500/10 to-cyan-600/10 border-l-4 border-cyan-500 rounded">

**Key Design Principles:**

- **Generic types** with variance (contravariant context, covariant result)
- **Tool allowlists** enforce principle of least privilege (FR-002)
- **Immutable results** via AgentResult dataclass
- **No retries** - workflows handle error recovery (FR-007)

</div>

---
layout: default
---

# Built-in Tools & Permissions

Claude Agent SDK tools available to agents based on role constraints

<div class="grid grid-cols-2 gap-4 mt-6">

<div v-click="1">

### Available Built-in Tools

```python
BUILTIN_TOOLS: frozenset[str] = frozenset({
    "Read",           # Read files
    "Write",          # Write new files
    "Edit",           # Edit existing files
    "Bash",           # Execute commands (restricted)
    "Glob",           # Pattern-based file search
    "Grep",           # Content search
    "NotebookEdit",   # Jupyter notebook editing
    "WebFetch",       # Fetch web content
    "WebSearch",      # Search the web
    "TodoWrite",      # Task tracking
})
```

</div>

<div v-click="2">

### Tool Validation

```python {all|4-7|9-13|15-18}
def _validate_tools(
    self,
    allowed_tools: list[str],
    mcp_servers: dict[str, Any],
) -> None:
    """Validate tools at construction time"""

    # Build MCP tool prefixes
    mcp_prefixes = {
        f"mcp__{server}__"
        for server in mcp_servers
    }

    for tool in allowed_tools:
        if tool not in BUILTIN_TOOLS:
            if not any(tool.startswith(p) for p in mcp_prefixes):
                raise InvalidToolError(tool, available)
```

</div>

</div>

<div v-click="3" class="mt-6 p-3 bg-amber-500/10 border-l-4 border-amber-500 rounded text-sm">

**Security Note:** Tools are validated at agent construction time, preventing runtime tool escalation.

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

Constrained tool sets based on principle of least privilege

::left::

<div v-click="1">

### Read-Only Agents

```python
# CodeReviewerAgent - analysis only
REVIEWER_TOOLS: frozenset[str] = frozenset({
    "Read",   # Read files for context
    "Glob",   # Find files by pattern
    "Grep",   # Search file contents
})
```

<div class="mt-4 text-sm text-slate-400">

**Why restricted?** Reviewers analyze code but must never modify it during review.

</div>

</div>

<div v-click="3" class="mt-8">

### Modification Agents

```python
# ImplementerAgent - code changes
IMPLEMENTER_TOOLS: frozenset[str] = frozenset({
    "Read", "Write", "Edit",  # File operations
    "Glob", "Grep",           # Search tools
    # Note: No Bash - validation handled by orchestration
})
```

<div class="mt-4 text-sm text-slate-400">

**Why no Bash?** Test execution and validation are orchestration concerns.

</div>

</div>

::right::

<div v-click="2">

### Targeted Fix Agents

```python
# FixerAgent - minimal permissions
FIXER_TOOLS: frozenset[str] = frozenset({
    "Read",   # Read files to understand context
    "Write",  # Create new files
    "Edit",   # Modify existing files
    # Note: No search - receives explicit file paths
})
```

<div class="mt-4 text-sm text-slate-400">

**Why minimal?** Fixers receive explicit paths, don't need search capabilities.

</div>

</div>

<div v-click="4" class="mt-8">

### Stateless Generators

```python
# Generator Agents - no tools
GENERATOR_TOOLS: frozenset[str] = frozenset()

# Examples:
# - CommitMessageGenerator
# - PRDescriptionGenerator
# - ErrorExplainerGenerator
```

<div class="mt-4 text-sm text-slate-400">

**Why empty?** Context is provided in prompts. No file access needed.

</div>

</div>

---
layout: default
---

# Agent Execution Flow

How agents interact with Claude SDK and return structured results

```python {all|1-7|9-14|16-21|23-28|all}
async def execute(self, context: ImplementerContext) -> ImplementationResult:
    """Execute implementation tasks"""
    # 1. Parse tasks from tasks.md or description
    if context.is_single_task:
        tasks = [Task(id="T000", description=context.task_description)]
    else:
        tasks = TaskFile.parse(context.task_file).pending_tasks

    # 2. Execute tasks (parallel batches where marked)
    task_results = []
    for task in tasks:
        messages = []
        async for msg in self.query(prompt, cwd=context.cwd):
            messages.append(msg)

        # 3. Extract structured output
        output = extract_all_text(messages)
        files_changed = await self._detect_file_changes(context.cwd)
        validation_results = await self._run_validation(context.cwd)
        commit_sha = await self._create_commit(task, context)
        task_results.append(TaskResult(...))

    # 4. Return aggregated result
    return ImplementationResult(
        success=all(r.succeeded for r in task_results),
        task_results=task_results,
        files_changed=all_files,
        commits=commits,
    )
```

<div v-click class="mt-6 p-4 bg-gradient-to-r from-emerald-500/10 to-emerald-600/10 border-l-4 border-emerald-500 rounded">

**Error Handling:** One task failure doesn't crash the entire workflow (Constitution IV: Fail Gracefully)

</div>

---
layout: default
---

# CodeReviewerAgent Deep Dive

Architecture review with severity categorization

<div class="grid grid-cols-2 gap-6 mt-6">

<div>

### Review Process

```python {all|1-3|5-9|11-15|17-20}
# 1. Check for merge conflicts
has_conflicts = await self._check_merge_conflicts(context)
if has_conflicts: raise AgentError("Resolve conflicts first")

# 2. Get diff stats and conventions (parallel)
diff_stats, conventions = await asyncio.gather(
    self._get_diff_stats(context),
    self._read_conventions(context),
)

# 3. Apply truncation if needed (FR-017)
if len(diff_stats["files"]) > MAX_DIFF_FILES:
    files_to_review = files[:MAX_DIFF_FILES]
    truncated = True
    logger.warning("Truncating large diff")

# 4. Get diff content and review
diff_content = await self._get_diff_content(context, files_to_review)
prompt = self._build_review_prompt(diff_content, conventions)
findings = await self._review_and_parse(prompt, context.cwd)
```

</div>

<div>

### Review Dimensions

<div v-click="1" class="mb-2">

```python
class ReviewSeverity(str, Enum):
    CRITICAL = "critical"    # Security, data loss
    MAJOR = "major"          # Logic errors, bugs
    MINOR = "minor"          # Style issues
    SUGGESTION = "suggestion" # Improvements
```

</div>

<div v-click="2">

```python
class ReviewFinding(BaseModel):
    severity: ReviewSeverity
    file: str
    line: int | None
    message: str
    suggestion: str
    convention_ref: str | None  # CLAUDE.md section
```

</div>

<div v-click="3" class="mt-4 p-3 bg-purple-500/10 border-l-4 border-purple-500 rounded text-sm">

**Actionable Feedback:** Every finding must include:
- Clear explanation of the issue
- Specific code example showing the fix
- Reference to conventions when applicable

</div>

</div>

</div>

---
layout: default
---

# Generator Agents

Stateless text generation from provided context

<div class="grid grid-cols-2 gap-6 mt-6">

<div v-click="1">

### CommitMessageGenerator

```python {all|1-5|7-12|14-18}
class CommitMessageGenerator(GeneratorAgent):
    """Generate conventional commit messages"""

    def __init__(self):
        super().__init__(name="commit-message", allowed_tools=[])

    async def execute(self, context: CommitContext) -> str:
        """Generate from diff stats and task description"""
        prompt = f"""
        Generate a conventional commit message for:
        - Task: {context.task_description}
        - Files changed: {context.files_changed}

        Format: <type>(<scope>): <description>
        """

        messages = [m async for m in self.query(prompt)]
        return extract_all_text(messages)
```

</div>

<div v-click="2">

### PRDescriptionGenerator

```python {all|1-5|7-15}
class PRDescriptionGenerator(GeneratorAgent):
    """Generate PR descriptions from commits"""

    def __init__(self):
        super().__init__(name="pr-description", allowed_tools=[])

    async def execute(self, context: PRContext) -> str:
        """Generate from commit history and diff"""
        prompt = f"""
        Generate PR description for:
        - Branch: {context.branch}
        - Commits: {context.commit_messages}
        - Files changed: {context.files_changed}
        """
        return await self._generate_text(prompt)
```

</div>

</div>

<div v-click="3" class="mt-6 p-4 bg-gradient-to-r from-cyan-500/10 to-cyan-600/10 border-l-4 border-cyan-500 rounded">

**Why No Tools?** Generators receive all context in their prompts:
- Commit messages from git log
- Diff stats from git commands
- Task descriptions from workflow state

No file system access needed - just text in, text out.

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
