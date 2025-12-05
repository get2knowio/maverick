# Development Workflow

Implement features from the task list, perform code review and cleanup, update project conventions, and manage the PR.

**Usage:** `/fly [branch-name]`
- If `branch-name` is provided, switch to that branch before starting
- If not provided, work on the current branch

---

## Part 0: Setup and Sync

Run `${CLAUDE_PLUGIN_ROOT}/scripts/sync-branch.sh $ARGUMENTS` and parse the JSON output.

The `$ARGUMENTS` variable contains the optional branch name passed to this command. If empty, the script uses the current branch.

**If status is "conflicts":**
- **Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/scripts/notify.sh error "Merge conflicts detected in: $branch"`
- Report the conflicting files to the user
- Pause and wait for human intervention
- After conflicts are resolved, user should run `git rebase --continue`

**If status is "error":**
- **Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/scripts/notify.sh error "Setup error: [error message]"`
- Report the error (missing spec directory or tasks file)
- Halt execution

**If status is "ok":**
- Store `branch`, `spec_dir`, and `tasks_file` for use in subsequent steps
- **Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/scripts/notify.sh spec_start "Starting spec: $branch"`
- Proceed to Part 1

---

## Part 1: Feature Implementation

Evaluate the tasks file at `{tasks_file}` (from Part 0). For each uncompleted task:

### Processing Rules

1. **Read the tasks file** and identify all incomplete tasks (not marked done)

2. **Process tasks serially by default**, with one exception:
   - Adjacent tasks marked with **"P"** can be processed in **parallel**
   - Each parallel task gets its own subagent

3. **For each task (or parallel batch), spawn subagent(s) that invoke the following slash-command:**
```
/speckit.implement

Task: {task_content}

Follow the specification in {spec_dir}/ for this task.
Report back with:
- What was implemented
- Any issues encountered
- Any deviations from spec (and why)
```

   Where `{task_content}` is the full text of the task from the tasks file.

4. **After each task/batch completes:**
   - Mark task(s) complete in `{tasks_file}`
   - Run appropriate build/check commands to verify compilation
   - Proceed to next task(s)

5. **Continue until all tasks are complete**

### Parallel Example

If tasks file contains:
```
- [ ] P: Implement user authentication
- [ ] P: Implement session management
- [ ] P: Add rate limiting middleware
- [ ] Integrate auth with existing endpoints
```

The first three (marked "P", adjacent) run in parallel, then the fourth runs after they complete.

---

## Part 2: Code Review and Improvement

Use the **code-review-workflow** skill to review and improve the implementation.

The skill will:
1. Run parallel CodeRabbit and architecture reviews
2. Consolidate and deduplicate findings
3. Execute improvements via subagents
4. Commit review fixes

**Additional context for this workflow:** Include specification compliance by reviewing against `{spec_dir}/` to verify implementation matches requirements.

After the code review skill completes, proceed to validation.

### Validation

Use the **validation-workflow** skill to verify all checks pass.

**Send notification before starting:** Run `${CLAUDE_PLUGIN_ROOT}/scripts/notify.sh testing "Entering testing phase for: $branch"`

The skill will:
1. Run format, lint, build, and test checks
2. Fix any failures (max 5 iterations)
3. Commit validation fixes

**If validation passes:** Proceed to Part 3

**If validation fails after max iterations:** Report blockers to user

---

## Part 3: Convention Update

Before creating/updating the PR, feed learnings back into project conventions.

### Synthesize Learnings

Review all issues found during code review and identify:

1. **Recurring patterns** - Issues that appeared multiple times
2. **Architectural anti-patterns** - Structural problems that could be prevented
3. **Specification gaps** - Areas where specs were ambiguous or incomplete
4. **Convention violations** - Inconsistencies that suggest missing guidelines

### Invoke Constitution Update

Run `/speckit.constitution` with a prompt structured like this:

```
Based on implementing {spec_dir}, the following issues were discovered during code review that could be prevented with better project conventions:

## Recurring Issues Found
[List patterns that appeared multiple times with examples]

## Architectural Concerns
[List structural issues that better guidelines could prevent]

## Suggested CLAUDE.md Updates
[Specific additions/changes to CLAUDE.md that would help Claude avoid these issues]
- Example: "Always use `thiserror` for error types, not manual `impl Error`"
- Example: "Prefer `&str` over `String` in function parameters unless ownership is needed"
- Example: "All public API functions must have doc comments with examples"

## Suggested Specification Conventions
[Patterns for writing clearer specs in the future]

## Suggested Code Conventions
[Project-specific coding standards to add to constitution]

Please update the project constitution and CLAUDE.md to incorporate these learnings.
```

**If no significant learnings:** Skip this step and note "No convention updates needed" in the final report.

---

## Part 4: PR Management

### Generate Final Report

Create the report (this becomes the PR description):

```markdown
## Summary

[One paragraph: what this PR accomplishes, main outcomes]

---

# Development & Review Summary

## Tasks Implemented
- Total tasks: X
- Completed: Y
- [List each task with brief summary]

## Code Review Findings
- CodeRabbit issues: X
- Architecture review issues: Y
- Total unique issues: Z

## Improvements Made
- Critical: X
- Major: Y
- Minor: Z
- Style: W

### Changes by File
- `path/to/file`: [summary]

## Validation Status
- Format check: pass/fail
- Lint check: pass/fail
- Build: pass/fail
- Tests: pass/fail (X passed, Y failed)

## Convention Updates
- [Summary of changes made to project conventions, or "None needed"]

## Remaining Issues
- [Any unresolved items]

## Recommendations
- [Suggested follow-up work]
```

### Create/Update PR

1. **Generate PR title** using conventional commits:
   - `feat(scope):` - New features
   - `fix(scope):` - Bug fixes
   - `refactor(scope):` - Code restructuring
   - `docs(scope):` - Documentation
   - `test(scope):` - Tests
   - `chore(scope):` - Maintenance

   Scope = branch name or primary area of change

2. **Save report to temp file:**
   ```bash
   echo "[FINAL REPORT]" > /tmp/pr-body.md
   ```

3. **Run PR script:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/scripts/manage-pr.sh "feat(scope): description" /tmp/pr-body.md
   ```

4. **Report the PR URL to the user**

5. **Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/scripts/notify.sh complete "Spec complete: $branch - PR created"`

---

## Execution Notes

- Commit after Part 1 (feature implementation)
- Commit after Part 2 (code review fixes) - handled by skills
- Commit after Part 3 (convention updates) if changes were made
- Subagent timeout: 5 minutes, then proceed
- Prefer many small subagents over few large ones
- When uncertain about parallelization, run sequentially
