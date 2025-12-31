---
description: Pick up to 3 tech-debt issues, implement fixes in parallel, review, and deliver a PR
---

# Tech Debt Refuel Workflow

Pick up to 3 non-conflicting tech-debt issues, implement in parallel, review, validate, and deliver a PR.

**Usage:** `/refuel [label]` (default: `tech-debt`)

---

## Workflow Activation

```bash
touch /tmp/maverick-workflow-active
```

---

## Part 0: Issue Discovery

```bash
gh issue list --label "${ARGUMENTS:-tech-debt}" --state open --json number,title,body,labels,createdAt,url,assignees --limit 50
```

Filter out: assigned issues, "wontfix"/"blocked" labels.

**If no issues:** Notify and halt.

---

## Part 1: Analysis & Selection

For each candidate:
1. Identify affected files/modules
2. Assess criticality (security > performance > maintainability)
3. Estimate conflict potential
4. Weight older issues higher

**Select up to 3** that can safely parallelize (minimal file overlap).

Document selection rationale.

---

## Part 2: Branch & PR Setup

```bash
BRANCH_NAME="refuel/tech-debt-$(date +%Y%m%d-%H%M%S)"
git checkout -b "$BRANCH_NAME"
git push -u origin "$BRANCH_NAME"
```

Create draft PR:
```bash
gh pr create --title "refuel: address tech-debt issues" --body "..." --draft
```

---

## Part 3: Parallel Implementation

Spawn up to 3 `issue-implementer` subagents simultaneously:

```
Fix GitHub issue #XXX: [Title]

Issue Body: [body]

Requirements:
- Fully resolve - no deferring
- Follow project conventions
- Write/update tests
- Run format, lint, build before completing
```

### After Subagents Complete

1. Verify no conflicts
2. Stage and commit:
   ```bash
   git add -A && git commit -m "fix: address tech-debt issues #X, #Y, #Z"
   ```

Invoke hook:
```bash
echo '{
  "branch": "BRANCH",
  "issues_fixed": [X, Y, Z],
  "total_issues": 3
}' | ${CLAUDE_PLUGIN_ROOT}/scripts/hooks/on-implementation-done.sh
```

---

## Part 4: Code Review & Validation

### Code Review

Use **code-review-workflow** skill (no spec compliance check for refuel).

Invoke hook after:
```bash
echo '{
  "branch": "BRANCH",
  "review_summary": {...}
}' | ${CLAUDE_PLUGIN_ROOT}/scripts/hooks/on-review-done.sh
```

### Validation

Use **validation-workflow** skill.

Invoke hook after:
```bash
echo '{
  "branch": "BRANCH",
  "validation_result": {...}
}' | ${CLAUDE_PLUGIN_ROOT}/scripts/hooks/on-validation-done.sh
```

---

## Part 5: Finalize PR

Generate final PR body at `/tmp/pr-body.md`:

```markdown
## Tech Debt Refuel

Fixes #X, #Y, #Z

## Summary
[outcomes]

## Implementation Details
[per-issue summary]

## Validation Status
- Format/Lint/Build/Test: pass
```

Invoke hook:
```bash
echo '{
  "branch": "BRANCH",
  "pr_title": "refuel: fix #X, #Y, #Z",
  "pr_body_file": "/tmp/pr-body.md"
}' | ${CLAUDE_PLUGIN_ROOT}/scripts/hooks/on-pr-ready.sh
```

Mark PR ready:
```bash
gh pr ready [PR_NUMBER]
```

---

## Workflow End

```bash
echo '{
  "workflow": "refuel",
  "branch": "BRANCH",
  "status": "success|failed|blocked",
  "pr_url": "PR_URL"
}' | ${CLAUDE_PLUGIN_ROOT}/scripts/hooks/on-workflow-end.sh
```

---

## Execution Notes

- Max 3 issues per refuel
- Subagent timeout: 10 minutes
- This is "later" - complete fully, no deferring
