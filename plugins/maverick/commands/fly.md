---
description: Implement features, perform code review, update conventions, and manage the PR
---

# Development Workflow

Implement features from the task list, perform code review, validate, and manage the PR.

**Usage:** `/fly [branch-name]`

---

## Workflow Activation

```bash
touch /tmp/maverick-workflow-active
```

---

## Part 0: Setup

Run sync and store the result:
```bash
${CLAUDE_PLUGIN_ROOT}/scripts/sync-branch.sh $ARGUMENTS
```

**On "conflicts" or "error":** Report to user and halt.
**On "ok":** Store `branch`, `spec_dir`, `tasks_file`, proceed.

---

## Part 1: Feature Implementation

Read `{tasks_file}` and identify all incomplete tasks with their phase boundaries.

### Task Processing

For each task (or batch of adjacent "P" tasks):

1. **Spawn subagent(s):**
   ```
   /speckit.implement

   Task: {task_content}
   Follow the specification in {spec_dir}/.
   ```

2. **Mark task(s) complete** in `{tasks_file}`

3. **On phase boundary** (last task in a phase), invoke hook:
   ```bash
   echo '{
     "phase": PHASE_NUM,
     "phase_name": "PHASE_NAME",
     "tasks_completed": N,
     "tasks_remaining": M,
     "total_phases": TOTAL,
     "branch": "BRANCH",
     "clean_cmd": "DETECTED_CLEAN_CMD"
   }' | ${CLAUDE_PLUGIN_ROOT}/scripts/hooks/on-phase-complete.sh
   ```

4. **Continue** until all tasks complete

### After All Tasks

Invoke hook with implementation summary:
```bash
echo '{
  "branch": "BRANCH",
  "spec_dir": "SPEC_DIR",
  "tasks_file": "TASKS_FILE",
  "total_tasks": N,
  "phases_completed": M
}' | ${CLAUDE_PLUGIN_ROOT}/scripts/hooks/on-implementation-done.sh
```

---

## Part 2: Code Review

Use the **code-review-workflow** skill.

Additional context: Include specification compliance against `{spec_dir}/`.

### After Review

Invoke hook with review summary:
```bash
echo '{
  "branch": "BRANCH",
  "spec_dir": "SPEC_DIR",
  "review_summary": {
    "coderabbit_issues": X,
    "architecture_issues": Y,
    "total_unique": Z,
    "issues_fixed": A,
    "issues_deferred": B
  }
}' | ${CLAUDE_PLUGIN_ROOT}/scripts/hooks/on-review-done.sh
```

---

## Part 3: Validation

Use the **validation-workflow** skill.

### After Validation

Invoke hook with validation result:
```bash
echo '{
  "branch": "BRANCH",
  "spec_dir": "SPEC_DIR",
  "validation_result": {
    "all_passed": true|false,
    "iterations": N
  },
  "fixes_applied": M
}' | ${CLAUDE_PLUGIN_ROOT}/scripts/hooks/on-validation-done.sh
```

**If validation blocked:** Report blockers and halt.

---

## Part 4: Convention Update

Review code review findings for recurring patterns, architectural anti-patterns, or specification gaps.

**If significant learnings found:** Run `/speckit.constitution` with a prompt summarizing the learnings and suggested CLAUDE.md updates.

**If no learnings:** Skip.

---

## Part 5: PR Management

### Generate Report

Create PR body at `/tmp/pr-body.md`:

```markdown
## Summary
[What this PR accomplishes]

---
# Development & Review Summary

## Tasks Implemented
- Total: X, Completed: Y

## Code Review
- Issues found: X, Fixed: Y

## Validation Status
- Format/Lint/Build/Test: pass/fail

## Convention Updates
- [Summary or "None"]
```

### Create/Update PR

Generate conventional commit title (`feat|fix|refactor(scope): description`).

Invoke hook:
```bash
echo '{
  "branch": "BRANCH",
  "spec_dir": "SPEC_DIR",
  "pr_title": "PR_TITLE",
  "pr_body_file": "/tmp/pr-body.md"
}' | ${CLAUDE_PLUGIN_ROOT}/scripts/hooks/on-pr-ready.sh
```

Report the PR URL to user.

---

## Workflow End

Invoke cleanup hook:
```bash
echo '{
  "workflow": "fly",
  "branch": "BRANCH",
  "spec_dir": "SPEC_DIR",
  "status": "success|failed|blocked",
  "pr_url": "PR_URL"
}' | ${CLAUDE_PLUGIN_ROOT}/scripts/hooks/on-workflow-end.sh
```

---

## Execution Notes

- Subagent timeout: 5 minutes
- Adjacent "P" tasks run in parallel
- When uncertain, run sequentially
- If workflow interrupted, marker file may need manual cleanup
