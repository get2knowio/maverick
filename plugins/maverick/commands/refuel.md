# Tech Debt Refuel Workflow

Pick up to 3 non-conflicting tech-debt issues, implement fixes in parallel, review, validate, and deliver a complete PR.

**Usage:** `/refuel [label]`
- If `label` is provided, filter issues by that label instead of "tech-debt"
- Default label: `tech-debt`

---

## Part 0: Issue Discovery

Retrieve all open tech-debt issues:

```bash
gh issue list --label "${ARGUMENTS:-tech-debt}" --state open --json number,title,body,labels,createdAt,url,assignees --limit 50
```

**If the command fails:**
- **Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/scripts/notify.sh error "Failed to fetch issues: [error message]"`
- Report the error to user and halt

Parse the JSON output and filter out:
- Issues already assigned to someone
- Issues with "wontfix" or "blocked" labels

For remaining issues, note:
- Issue number and title
- Creation date (for prioritizing oldest issues)
- Labels (for identifying criticality and affected components)
- Issue body (for understanding scope and dependencies)

---

## Part 1: Codebase Impact Analysis

Analyze the issues to select up to 3 for parallel work.

For each candidate issue:
1. **Identify affected files/modules** - Search the codebase to find likely touch points
2. **Assess criticality** based on:
   - Security implications (highest priority)
   - Performance impact
   - Developer productivity impact
   - Code maintainability
3. **Estimate conflict potential** with other issues
4. **Consider age** - Older issues weighted higher when criticality is equal

### Selection Criteria

Select **up to 3 issues** that:
- Can be worked on in parallel without merge conflicts
- Have minimal overlapping file changes
- Balance criticality with isolation
- Favor older issues when criticality is equal
- Have clear problem statements (avoid vague issues)

### Create Analysis Report

Document your analysis:

```markdown
## Issue Analysis

### Selected Issues
| Issue | Title | Age | Criticality | Affected Files | Rationale |
|-------|-------|-----|-------------|----------------|-----------|
| #XXX  | ...   | Xd  | High/Med/Low | file1, file2  | ... |

### Not Selected (This Round)
| Issue | Title | Reason |
|-------|-------|--------|
| #YYY  | ...   | Conflicts with #XXX on module Z |

### Conflict Analysis
[Brief explanation of why selected issues can be worked in parallel]
```

**If no suitable issues found:**
- **Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/scripts/notify.sh complete "No actionable tech-debt issues found"`
- Report findings to user and halt

---

## Part 2: Branch and PR Setup

### Create Working Branch

```bash
# Generate branch name from timestamp
BRANCH_NAME="refuel/tech-debt-$(date +%Y%m%d-%H%M%S)"
git checkout -b "$BRANCH_NAME"
git push -u origin "$BRANCH_NAME"
```

### Create Placeholder PR

Build the PR body with issue references:

```markdown
## Tech Debt Refuel

This PR addresses the following tech-debt issues:

{{FOR EACH SELECTED ISSUE}}
- Fixes #XXX - [Issue Title]
{{END FOR}}

---

## Status: In Progress

Implementation is underway. This description will be updated upon completion.

---

### Selected Issues Analysis
[Include the analysis table from Part 1]
```

Create the PR:

```bash
gh pr create --title "refuel: address tech-debt issues" --body-file /tmp/pr-body.md --draft
```

**If PR creation fails:**
- **Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/scripts/notify.sh error "Failed to create PR for: $BRANCH_NAME"`
- Report the error to user and halt

**Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/scripts/notify.sh spec_start "Starting refuel: $BRANCH_NAME"`

Store the PR number for later updates.

---

## Part 3: Parallel Implementation

Spawn up to 3 subagents simultaneously using the `issue-implementer` agent, one for each selected issue:

**For each selected issue, spawn a subagent:**
```
Fix GitHub issue #XXX: [Issue Title]

Issue Body:
[Full issue body text]

Requirements:
- Fully resolve this issue - no deferring, no placeholders
- This is "later" - complete the work now
- Follow project conventions and patterns
- Write/update tests for changed behavior
- Run format, lint, and build checks before completing
- Report back with:
  - Summary of changes made
  - Files modified
  - Tests added/updated
  - Any issues encountered
  - Confirmation that the fix is complete
```

### After All Subagents Complete

1. **Review subagent reports** - Collect summaries of what was implemented

2. **Verify no conflicts** - Check for overlapping changes
   - **If conflicts detected:** Run `${CLAUDE_PLUGIN_ROOT}/scripts/notify.sh error "Implementation conflicts in: $BRANCH_NAME"` and resolve before continuing

3. **If any subagent failed to complete its issue:**
   - **Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/scripts/notify.sh error "Implementation incomplete for issue #X"`
   - Document which issues were not completed
   - Continue with completed work or halt based on severity

4. **Stage all changes:**
   ```bash
   git add -A
   ```
5. **Create implementation commit:**
   ```bash
   git commit -m "fix: address tech-debt issues #X, #Y, #Z

   - Issue #X: [brief summary]
   - Issue #Y: [brief summary]
   - Issue #Z: [brief summary]

   🤖 Generated with [Claude Code](https://claude.com/claude-code)

   Co-Authored-By: Claude <noreply@anthropic.com>"
   ```
6. **Push changes:**
   ```bash
   git push
   ```

---

## Part 4: Code Review and Validation

### Code Review

Use the **code-review-workflow** skill to review and improve the implementation.

The skill will:
1. Run parallel CodeRabbit and architecture reviews
2. Consolidate and deduplicate findings
3. Execute improvements via subagents
4. Commit review fixes

**Note:** No specification compliance check for refuel (issues define requirements, not specs).

### Validation

Use the **validation-workflow** skill to verify all checks pass.

**Send notification before starting:** Run `${CLAUDE_PLUGIN_ROOT}/scripts/notify.sh testing "Running validation for: $BRANCH_NAME"`

The skill will:
1. Run format, lint, build, and test checks
2. Fix any failures (max 5 iterations)
3. Commit validation fixes

**If validation passes:** Proceed to Part 5

**If validation fails after max iterations:** Report blockers to user

---

## Part 5: Finalize PR

### Update PR Description

Build the final PR body:

```markdown
## Tech Debt Refuel

This PR addresses the following tech-debt issues:

{{FOR EACH SELECTED ISSUE}}
- Fixes #XXX - [Issue Title]
{{END FOR}}

---

## Summary

[One paragraph: what this PR accomplishes, main outcomes]

---

## Implementation Details

### Issue #XXX: [Title]
- **Problem:** [Brief description of the issue]
- **Solution:** [Summary of changes made]
- **Files Changed:** [List of files]

[Repeat for each issue]

---

## Code Review Summary

- CodeRabbit issues found: X
- Architecture review issues found: Y
- Total issues addressed: Z

### Key Improvements Made
- [List significant review-driven improvements]

---

## Validation Status

- Format check: ✅ pass
- Lint check: ✅ pass
- Build: ✅ pass
- Tests: ✅ pass (X passed)

---

## Files Changed

[List all files with brief description of changes]
```

Update the PR:
```bash
gh pr edit [PR_NUMBER] --title "refuel: fix #X, #Y, #Z" --body-file /tmp/pr-body-final.md
gh pr ready [PR_NUMBER]
```

### Report Completion

**Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/scripts/notify.sh complete "Refuel complete: $BRANCH_NAME - PR ready for review"`

Report the PR URL to the user with a summary:
- Issues addressed
- Total commits
- Files changed
- Test status

---

## Execution Notes

- Maximum 3 issues per refuel run to maintain focus and review quality
- Issues already assigned should be skipped
- If fewer than 3 non-conflicting issues exist, work with what's available
- Prefer issues with clear problem statements and well-defined scope
- This is "later" - complete the work fully, no deferring
- Subagent timeout: 10 minutes (these are significant tasks)
- Commits handled by skills after review and validation phases
- When uncertain about parallelization, run sequentially
