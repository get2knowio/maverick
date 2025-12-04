# Development Workflow

Implement features from the task list, perform code review and cleanup, update project conventions, and manage the PR.

**Usage:** `/project:fly [branch-name]`
- If `branch-name` is provided, switch to that branch before starting
- If not provided, work on the current branch

---

## Part 0: Setup and Sync

Run `${CLAUDE_PLUGIN_ROOT}/src/scripts/sync-branch.sh $ARGUMENTS` and parse the JSON output.

The `$ARGUMENTS` variable contains the optional branch name passed to this command. If empty, the script uses the current branch.

**If status is "conflicts":**
- **Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/src/scripts/notify.sh error "Merge conflicts detected in: $branch"`
- Report the conflicting files to the user
- Pause and wait for human intervention
- After conflicts are resolved, user should run `git rebase --continue`

**If status is "error":**
- **Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/src/scripts/notify.sh error "Setup error: [error message]"`
- Report the error (missing spec directory or tasks file)
- Halt execution

**If status is "ok":**
- Store `branch`, `spec_dir`, and `tasks_file` for use in subsequent steps
- **Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/src/scripts/notify.sh spec_start "Starting spec: $branch"`
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

### Phase 2.1: Parallel Reviews

Launch two subagents simultaneously:

**Subagent 1: CodeRabbit Review**
```
Run `coderabbit review --prompt-only` and return the complete output.
Do not summarize - return everything.
```

**Subagent 2: Architecture & Specification Review**
```
Review all changes in this branch against clean code principles, clean architecture, and spec compliance.

First, run `${CLAUDE_PLUGIN_ROOT}/src/scripts/get-changed-files.sh` to identify changed files.

Review criteria:

1. **Clean Code**: Single responsibility, DRY, naming, function size, comments, error handling

2. **Clean Architecture**: Dependency direction, layer separation, abstraction boundaries, coupling, testability

3. **Specification Compliance**: Read all files in {spec_dir}/, verify implementation matches requirements

Return structured report with:
- File-by-file findings
- Severity (critical/major/minor/suggestion)
- Line numbers where applicable
- Concrete recommendations
```

### Phase 2.2: Consolidate Findings

Synthesize both reviews:

1. **Deduplicate** overlapping findings

2. **Categorize** each unique issue:
   - `[CRITICAL]` - Bugs, security issues, spec violations
   - `[MAJOR]` - Architecture/design problems
   - `[MINOR]` - Code quality improvements
   - `[STYLE]` - Formatting, naming

3. **Create prioritized TODO list**

4. **Analyze parallelization:**
   - Issues in different files → can parallelize
   - Same file or dependencies → must serialize
   - Max 3-4 parallel subagents

### Phase 2.3: Execute Improvements

For each batch of parallelizable issues, spawn subagents:
```
Task: Fix ISSUE-XXX

Issue: [description]
File(s): [files to modify]

Requirements:
- Minimal change for this specific issue
- Do NOT refactor unrelated code
- Run build/check commands before completing
- Note (don't fix) any new issues discovered
```

After each batch: review changes, resolve conflicts, update TODO, proceed.

### Phase 2.4: Validation

**Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/src/scripts/notify.sh testing "Entering testing phase for: $branch"`

Run `${CLAUDE_PLUGIN_ROOT}/src/scripts/run-validation.sh` and parse results.

**If `all_passed` is true:** Proceed to Part 3

**If any check failed:**
1. **Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/src/scripts/notify.sh error "Validation failed for: $branch"`
2. Parse error output from failed checks
3. Create TODO list of failures
4. Fix ALL failures (even if unrelated to our changes)
5. Priority: compilation → linting → tests → formatting
6. Iterate (max 5 times, then report blockers)

For test failures, spawn subagents:
```
Fix failing test: [test name]
Error: [error output]
File: [location]

Investigate whether it's a test bug or implementation bug.
Fix the actual issue - do NOT weaken assertions.
```

---

## Part 3: Convention Update

Before creating/updating the PR, feed learnings back into project conventions.

### Synthesize Learnings

Review all issues found during code review (Phase 2.1-2.3) and identify:

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
   ${CLAUDE_PLUGIN_ROOT}/src/scripts/manage-pr.sh "feat(scope): description" /tmp/pr-body.md
   ```

4. **Report the PR URL to the user**

5. **Send notification:** Run `${CLAUDE_PLUGIN_ROOT}/src/scripts/notify.sh complete "Spec complete: $branch - PR created"`

---

## Execution Notes

- Commit after Part 1 (feature implementation)
- Commit after Part 2 (code review fixes)
- Commit after Part 3 (convention updates) if changes were made
- Subagent timeout: 5 minutes, then proceed
- Prefer many small subagents over few large ones
- When uncertain about parallelization, run sequentially
