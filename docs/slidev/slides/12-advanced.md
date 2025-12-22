---
layout: section
---

# Part 12: Advanced Topics

Resilience, efficiency, and error handling patterns

---
layout: default
---

# Resilience Patterns

Building robust workflows that handle failures gracefully

<div class="grid grid-cols-2 gap-4 mt-8">

<div v-click>

## Retry with Exponential Backoff

```python
# 3 attempts: 1s → 2s → 4s delays
yield step("fetch_api_data") \
    .agent("data_fetcher") \
    .retry(max_attempts=3)
```

Handles transient failures (network, rate limits)

</div>

<div v-click>

## Checkpoint & Resume

```python
yield step("long_running_task") \
    .checkpoint()
# Workflow resumes from here on failure
```

Skip expensive operations already completed

</div>

<div v-click>

## Rollback on Failure

```python
yield step("db_migrate") \
    .with_rollback(rollback_migration)
# Rollbacks execute in reverse order
```

Automatic cleanup on errors

</div>

<div v-click>

## Graceful Degradation

- CodeRabbit unavailable → skip with warning
- Notification server down → log warning
- Test timeout → capture output, continue

Workflows continue despite non-critical failures

</div>

</div>

---
layout: default
---

# Token Efficiency Strategies

Minimizing costs while maximizing context

<div class="mt-8">

<div v-click>

## Context Truncation

```python
# Large files truncated intelligently
{
  "path": "src/large_module.py",
  "content": "... (truncated) ...\n",
  "_metadata": {
    "truncated": true,
    "original_lines": 5432,
    "strategy": "preserve_error_context"
  }
}
```

Preserve critical sections (errors, imports, class definitions)

</div>

<div v-click class="mt-6">

## Proportional Budget Allocation

```python
fit_to_budget(sections, budget=32000)
# Allocates tokens proportionally across sections
# High-priority sections get minimum quota
# Remaining budget distributed by importance
```

Ensures critical context never omitted

</div>

<div v-click class="mt-6">

## Chunked Analysis

```python
# Large diffs split into manageable chunks
chunks = split_diff(diff, max_lines=2000, max_files=50)
results = await asyncio.gather(*[review_chunk(c) for c in chunks])
merged = merge_results(results)
```

Parallel processing + reduced context per request

</div>

</div>

---
layout: default
---

# Exception Hierarchy

Type-safe error handling across all components

<div class="mt-4">

```python
MaverickError (base)
├── ConfigError                    # Invalid configuration
├── AgentError                     # Agent execution failures
│   ├── ProcessError               # Subprocess failures
│   ├── TimeoutError               # Operation timeout
│   ├── NetworkError               # API/network issues
│   ├── StreamingError             # SSE stream failures
│   ├── MalformedResponseError     # Invalid agent output
│   ├── InvalidToolError           # Tool not allowed/not found
│   └── DuplicateAgentError        # Agent ID conflict
├── GitError                       # Git operation failures
│   ├── GitNotFoundError           # git binary not found
│   ├── NotARepositoryError        # Not in a git repo
│   ├── BranchExistsError          # Branch already exists
│   ├── MergeConflictError         # Merge conflicts detected
│   ├── PushRejectedError          # Push rejected by remote
│   └── NothingToCommitError       # No changes to commit
├── WorkflowError                  # Workflow execution failures
│   ├── DuplicateStepNameError     # Step name collision
│   └── StagesNotFoundError        # Missing workflow stage
└── HookError                      # Hook execution failures
    ├── SafetyHookError            # Safety check failed
    └── HookConfigError            # Invalid hook configuration
```

</div>

<div v-click class="mt-4 text-sm">

**Usage Example:**

```python
try:
    await workflow.execute()
except GitError as e:
    logger.error(f"Git operation failed: {e}")
    # Handle git-specific failures
except AgentError as e:
    logger.error(f"Agent failed: {e}")
    # Handle agent failures differently
```

</div>
