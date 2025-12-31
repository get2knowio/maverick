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

```yaml
# 3 attempts: 1s → 2s → 4s delays
- name: fetch_api_data
  type: agent
  agent: data_fetcher
  retry:
    max_attempts: 3
    backoff: exponential
```

Handles transient failures (network, rate limits)

</div>

<div v-click>

## Checkpoint & Resume

```yaml
- name: long_running_task
  type: python
  action: expensive_operation
  checkpoint: true  # Resume from here
```

Skip expensive operations already completed

</div>

<div v-click>

## Rollback on Failure

```yaml
- name: db_migrate
  type: python
  action: run_migration
  rollback:
    action: rollback_migration
```

Automatic cleanup on errors (reverse order)

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

<div class="grid grid-cols-2 gap-4 mt-4">

<div v-click>

## Context Truncation

```python
{"path": "src/large.py",
 "content": "...(truncated)...",
 "_metadata": {"original_lines": 5432,
               "strategy": "preserve_errors"}}
```

Preserve critical sections (errors, imports, classes)

## Proportional Budget

```python
fit_to_budget(sections, budget=32000)
# High-priority gets minimum quota
```

</div>

<div v-click>

## Chunked Analysis

```python
chunks = split_diff(diff, max_lines=2000)
results = await asyncio.gather(
    *[review_chunk(c) for c in chunks])
```

Parallel processing + reduced context per request

## Key Strategies

- Smart truncation (keep error context)
- Budget allocation by importance
- Parallel chunk processing

</div>

</div>

---
layout: default
---

# Exception Hierarchy

<div class="grid grid-cols-2 gap-4 mt-2">

<div>

```python
MaverickError (base)
├── ConfigError
├── AgentError
│   ├── ProcessError
│   ├── TimeoutError
│   ├── NetworkError
│   ├── InvalidToolError
│   └── ...
├── GitError
│   ├── BranchExistsError
│   ├── MergeConflictError
│   └── PushRejectedError
├── WorkflowError
└── HookError
    └── SafetyHookError
```

</div>

<div v-click>

## Usage

```python
try:
    await workflow.execute()
except GitError as e:
    logger.error(f"Git: {e}")
except AgentError as e:
    logger.error(f"Agent: {e}")
```

## Key Categories

- **AgentError**: SDK/process failures
- **GitError**: Branch/commit/push issues
- **WorkflowError**: Step execution
- **HookError**: Safety/validation blocks

</div>

</div>
