# First Run Fixes

Findings from the first end-to-end Maverick run against a real project
(Deacon, a Rust DevContainer CLI). The epic `consumer-core-completion`
processed 10 original beads + 2 follow-ups across ~4 hours of autonomous
fly time. All beads closed successfully, but several systemic issues
surfaced that need to be addressed before Maverick can reliably operate
without post-run human review.

**Test project:** get2knowio/deacon (Rust, Cargo workspace, ~20K LOC)
**Epic:** consumer-core-completion (5 PRD beads → 10 decomposed work units)
**Outcome:** All beads closed. Code compiles, clippy clean, tests pass.
Overall grade: B — moved the project forward but gaps in observability,
review fidelity, and curation quality need fixing.

---

## 1. Persist Actual Review Findings in Episodic Store — DONE

**Priority:** Critical — **COMPLETED 2026-03-22**
**Observed:** Every bead recorded `review_findings_count: 1` but
`review-findings.jsonl` was empty. The verbatim reviewer findings were
never persisted.

**Impact:** The runway can't learn from what reviewers flag. Future agents
operating on the same codebase get no benefit from past review history.
The consolidated insights had to infer finding categories from bead titles
instead of analyzing actual findings.

**Root cause:** `record_review_findings()` in
`src/maverick/library/actions/runway.py` is called but the review result
dict doesn't contain the individual `Finding` objects by the time it
reaches the recorder. The `GroupedReviewResult` (which has the actual
findings with file, line, severity, category, fix_hint) is consumed
inside `_run_dual_review` and discarded. Only the `ReviewAndFixReport`
summary survives, which has `issues_remaining: int` (a sentinel) and
`review_report: str` (markdown).

**Fix:** Either:
- (A) Propagate the `GroupedReviewResult.all_findings` list through
  `ReviewFixLoopResult` so individual `Finding` objects reach the
  runway recorder, or
- (B) Parse the `review_report` markdown in the recorder to extract
  structured findings back out (fragile, not recommended), or
- (C) Record the `review_report` markdown verbatim as a text blob in
  `review-findings.jsonl` — less structured but captures the content.

Option (A) is cleanest. It requires adding a `findings: list[Finding]`
field to `ReviewFixLoopResult` and populating it from the last
`_run_dual_review` pass.

**Files:**
- `src/maverick/library/actions/review.py` — propagate findings
- `src/maverick/library/actions/types.py` — add field to ReviewFixLoopResult
- `src/maverick/library/actions/runway.py` — use findings in recorder

---

## 2. Populate `files_changed` in Bead Outcomes — DONE

**Priority:** High — **COMPLETED 2026-03-22**
**Observed:** Every bead outcome has `files_changed: []`. The outcome
recorder never captures which files were modified.

**Impact:** The consolidated insights can't do real hotspot analysis — it
has to infer file involvement from bead titles and descriptions instead
of from actual diffs. This makes the "Frequently Problematic Files"
section in consolidated insights unreliable.

**Root cause:** `record_bead_outcome()` in
`src/maverick/library/actions/runway.py` receives `validation_result`
and `review_result` but neither contains a file list. The information
is available from `git diff --name-only` (or `jj diff --summary`) after
each bead commit.

**Fix:** After `commit_bead()` in `steps.py`, run
`jj diff --summary -r @` (or `git diff --name-only HEAD~1`) to get the
list of changed files. Pass it to `record_bead_outcome()` as a new
`files_changed` parameter.

**Files:**
- `src/maverick/workflows/fly_beads/steps.py` — capture file list after commit
- `src/maverick/library/actions/runway.py` — accept and store file list

---

## 3. Fix Reviewer Stop-at-First-Finding Behavior — DONE (partial)

**Priority:** High
**Observed:** Every single bead across the entire epic received exactly
1 review finding. The reviewer may have found multiple issues but only
1 is ever surfaced.

**Root cause:** Two compounding issues:
1. The review loop in `steps.py` uses `max_attempts=1` (single pass,
   no retry). The reviewer runs once and whatever it finds is final.
2. `generate_review_fix_report()` in `review.py` (line ~1009) generates
   `issues_remaining` as a sentinel: `0 if approved else 1`. It's not
   a count of actual remaining issues — it's a boolean disguised as
   an int.

**Impact:** The system can't distinguish "reviewer found 1 minor style
issue" from "reviewer found 5 critical security vulnerabilities." Both
show as `issues_remaining: 1`. The follow-up bead and the consolidated
insights both see the same opaque "1 issues remaining" regardless of
severity or count.

**Fix:**
- Replace the sentinel with the actual count from
  `GroupedReviewResult.total_count` (already computed, just not used).
- Propagate the count through `ReviewAndFixReport.issues_remaining`.
- Consider making `max_attempts` in the review loop configurable via
  `maverick.yaml` so projects can choose how many review-fix passes
  to allow (default: 1 is probably fine, but 2 would catch more).

**Files:**
- `src/maverick/library/actions/review.py` — use real count, not sentinel
- `src/maverick/library/actions/types.py` — document that issues_remaining is a real count
- `src/maverick/workflows/fly_beads/steps.py` — optionally make max_attempts configurable

---

## 4. Constrain Verification and Quality-Gate Beads — DONE

**Priority:** Medium — **COMPLETED 2026-03-22**
**Observed:** Bead .9 (described as "verification-only, no code changes
expected") modified Python files: `conftest.py`,
`create_tech_debt_issue.py`, example scripts, `pyproject.toml`. Bead .10
(quality gate) had full Write/Edit/Bash access.

**Impact:** Verification beads that make unexpected changes undermine
trust in the commit history. A "verification-only" bead that modifies
files is confusing to review and may introduce unrelated changes.

**Root cause:** The implementer agent receives the bead description
(which says "no code changes expected") but has full tool access. The
agent interprets its task broadly — it "fixed" formatting issues in
files it read during verification.

**Fix:** Two options:
- (A) **Prompt-level:** When the bead description contains keywords
  like "verification-only", "no code changes", or "confirm", prepend
  a constraint to the implementer prompt: "This is a verification
  bead. Do NOT modify any files. Only read and report."
- (B) **Tool-level:** Add a `read_only: bool` field to the work unit
  spec. When true, the executor passes only read-only tools
  (`Read, Glob, Grep`) to the agent, physically preventing writes.

Option (B) is more reliable. It could be driven by a `verification`
flag in the work unit YAML or inferred from the bead title/description
by the decomposer.

**Files:**
- `src/maverick/workflows/fly_beads/steps.py` — detect read-only beads, restrict tools
- `src/maverick/library/actions/decompose.py` — optionally emit `read_only` flag in work unit spec
- `src/maverick/flight/models.py` — add `read_only` field to WorkUnitSpec

---

## 5. Exclude or Flag Snapshot Commits During Curation — DONE

**Priority:** High — **COMPLETED 2026-03-22**
**Observed:** The `--auto-commit` flag creates snapshot commits
containing all uncommitted changes in the working directory. In this
run, the first snapshot included ~16K lines of feature-authoring code
deletions from a prior session — completely unrelated to the PRD. The
curator agent said "history looks clean" and let them through.

**Impact:** Unrelated changes get mixed into the PR. Anyone reviewing
the landed branch sees massive deletions alongside the actual feature
work, making review difficult and polluting `git blame`.

**Root cause:** `snapshot_uncommitted` in the fly workflow does a
blanket `git add -A && git commit` without analyzing what's being
committed. The curator agent doesn't distinguish snapshot commits from
bead commits — it treats them all as intentional work.

**Fix:**
- (A) **At snapshot time:** Before committing, check the diff size.
  If the snapshot would commit more than N files or M lines of
  changes, warn the user and either refuse (requiring manual commit)
  or create a separate branch for the snapshot so it doesn't pollute
  the bead history.
- (B) **At curation time:** The curator should recognize
  `chore: snapshot uncommitted changes before fly` commits and flag
  them for review if they contain large diffs. It should suggest
  splitting them out or squashing them separately.
- (C) **At land time:** The `--eject` preview should explicitly list
  snapshot commits and their diff stats so the user can decide
  whether to include them.

Minimum viable fix: option (A) with a configurable threshold.

**Files:**
- `src/maverick/workflows/fly_beads/steps.py` — add diff-size check to snapshot step
- `src/maverick/agents/curator.py` — teach curator to flag large snapshot commits

---

## 6. Re-seed Runway with ACP Write-Tool Agent

**Priority:** Medium
**Observed:** The seed files are thin (~1.5-2KB each) because they
were generated from a prompt containing only the directory tree and
config files. The agent couldn't explore source code directly.

**Impact:** The briefing agents and implementer agents get shallow
codebase context. The architecture seed file lists abstractions by
name but doesn't explain their relationships, boundaries, or gotchas.

**Root cause:** The original seed agent had `allowed_tools=[]` and
received all context in the prompt. It was redesigned during this
session to use `allowed_tools=["Read", "Glob", "Grep", "Write"]`
and write files directly via ACP, which should produce much richer
output.

**Fix:** Re-run `maverick runway seed --force` on existing projects
to regenerate semantic files with the new tool-equipped agent. The
new agent can Read actual source files, Grep for patterns, and
produce more detailed analysis.

No code changes needed — the fix is already implemented. This item
is a reminder to re-seed existing projects.

---

## 7. Thread `flight_plan_name` Through Bead Outcomes

**Priority:** Low
**Observed:** Every bead outcome has `flight_plan: ""`. The link
between outcomes and the plan that generated them is broken.

**Impact:** Cross-epic analysis is impossible. The consolidated
insights can't group outcomes by flight plan or compare how
different plans performed.

**Root cause:** `record_bead_outcome()` receives `flight_plan_name`
but it's empty because the caller doesn't populate it. The
flight plan name IS available in `ctx.briefing_context` path
(loaded from `.maverick/plans/<name>/`) and in the epic's state
metadata (`state["flight_plan_name"]`).

**Fix:** In `record_runway_outcome()` (steps.py), extract the
flight plan name from `ctx.epic_id` via the epic's state, or
from the briefing context path. Pass it to `record_bead_outcome()`.

**Files:**
- `src/maverick/workflows/fly_beads/steps.py` — extract and pass flight_plan_name
- `src/maverick/library/actions/runway.py` — verify it's stored

---

## 8. Scope Reviewer to Bead-Relevant Files Only

**Priority:** Medium
**Observed:** The reviewer examines the full workspace diff, which
accumulates changes from all beads processed in the same fly run.
When bead .4 is reviewed, the reviewer may flag something from
bead .3's changes that are still in the workspace.

**Impact:** Review findings may not be actionable by the current
bead's implementer because they refer to code from a different
bead. This contributes to the "reviewer keeps requesting changes
the implementer can't fix" loop that caused beads .4 and .5 to
exhaust retries.

**Root cause:** `gather_local_review_context()` in `review.py`
collects the diff from the base branch, which includes all
prior bead commits in the workspace. There's no per-bead
scoping.

**Fix:** Pass the list of files the current bead actually modified
to the review context gatherer. Filter the diff to only those
files. This requires capturing `git diff --name-only` after
implementation (same data as fix #2) and threading it through
to the review step.

**Files:**
- `src/maverick/workflows/fly_beads/steps.py` — capture bead file list, pass to review
- `src/maverick/library/actions/review.py` — accept file scope filter in gather_local_review_context

---

## Implementation Priority

| # | Fix | Priority | Effort | Impact | Status |
|---|-----|----------|--------|--------|--------|
| 1 | Persist review findings | Critical | Medium | Unlocks runway learning | **DONE** |
| 3 | Reviewer count fidelity | High | Low | Accurate failure signals | **DONE** (sentinel replaced with real count; falls back to 1 when no findings captured) |
| 5 | Snapshot commit hygiene | High | Medium | Clean PR history | **DONE** |
| 8 | Scope reviewer to bead files | Medium | Medium | Fewer false-positive review failures | |
| 2 | Populate files_changed | High | Low | Real hotspot analysis | **DONE** |
| 4 | Constrain verification beads | Medium | Medium | Prevent scope creep | **DONE** |
| 7 | Thread flight_plan_name | Low | Low | Cross-epic analysis | |
| 6 | Re-seed runway | Medium | None | Richer agent context | |
