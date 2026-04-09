# Maverick: Future Opportunities

## Per-Epic jj Workspaces for Concurrent Human-Agent Execution

### Status: Designed, not implemented

### Problem

In watch mode (`maverick fly --watch`), fly creates a single jj workspace at startup and processes all beads in it. This creates tension when:

1. **Human review beads are pending** — epic A has a `needs-human-review` bead. Fly moves to epic B (optimistic execution), but epic A's workspace commits must stay intact for when the human rejects and spawns a correction bead.

2. **Workspace staleness** — the workspace is a snapshot from fly startup. New epics added by concurrent `plan/refuel` may reference code that doesn't exist in the workspace yet (e.g., code merged to main after fly started).

3. **Correction beads need their original context** — when a human rejects an assumption in epic A, the correction agent needs to work against epic A's commit state, not epic B's or main's.

### Solution: One jj Workspace Per Epic

jj natively supports multiple named workspaces pointing to different commits in the same DAG. Each workspace has its own working copy, and commits from one workspace are visible to others.

```
workspace: maverick/epic-a  →  commits for epic A (some pending human review)
workspace: maverick/epic-b  →  commits for epic B (in progress)
main                        →  where land merges completed work
```

#### How Fly Would Work

1. **Start epic A** → create workspace `maverick/epic-a` from current `main`
2. **Process beads** — implement, gate, spec, review, commit — all in `maverick/epic-a`
3. **Hit human escalation** on bead A.2 → create human review bead, commit optimistically
4. **Epic A has no more agent beads** → move on (don't tear down workspace)
5. **Pick up epic B bead** → create workspace `maverick/epic-b` from current `main` (which may now include landed work from other sources)
6. **Process epic B beads** in `maverick/epic-b`
7. **Human resolves A.2** → correction bead appears in `bd ready`
8. **Fly picks up correction bead** → detects it's for epic A → switches to `maverick/epic-a` workspace
9. **Correction agent works** against epic A's commit state, with the human's guidance
10. **All of epic A resolved** → `maverick land` can merge `maverick/epic-a` into `main`
11. **Epic B continues** uninterrupted in its own workspace

#### Why jj Makes This Feasible

- **Named workspaces** — `jj workspace add maverick/epic-a` creates a new working copy. No git worktree hacks.
- **Shared DAG** — commits in `maverick/epic-a` are visible from `maverick/epic-b` (same repo). If epic B depends on epic A, jj can rebase B onto A's tip.
- **Automatic rebasing** — when a correction agent edits an ancestor commit in epic A's workspace, jj propagates changes through all descendants in that workspace. No manual interactive rebase.
- **Conflict as signal** — if an ancestor edit in epic A creates conflicts in descendant commits, those conflicts are the blast radius made concrete. The correction agent resolves them one at a time with full context.

#### Connection to Assumption Architecture

This aligns with the human-in-the-loop assumption model:

- **Assumption-to-commit mapping** — each assumption is a discrete jj commit in the epic's workspace. The human review bead stores a pointer to that commit.
- **Blast radius is computable** — when a correction is needed, the descendant set of the assumption commit (in jj's DAG) tells you exactly what's affected.
- **Correction is surgical** — the correction agent checks out the specific commit, makes the fix, and jj cascades forward. Compare to git where you'd either interactive-rebase or make a new commit at HEAD that reworks everything.
- **One assumption = one commit boundary** — enforced by prompt guidance: "when you make an assumption, commit your current work first, then proceed."

#### What Changes

| Component | Current | Per-Epic Workspaces |
|-----------|---------|-------------------|
| Workspace lifecycle | Created at fly start, torn down by land | Created per epic, torn down when epic is fully resolved |
| Fly supervisor | Operates in one workspace | Tracks active workspace per epic, switches on bead selection |
| CommitActor | Commits to "the" workspace | Commits to the bead's epic workspace |
| Land | Merges one workspace → main | Merges each epic workspace independently when clean |
| `select_next_bead` | No workspace awareness | Returns epic_id, supervisor maps to workspace |
| Watch mode idle | Polls for any ready bead | Polls, and may switch workspace when crossing epic boundary |

#### Prerequisites

1. **jj workspace management utilities** — create, switch, list, and teardown functions in `maverick.library.actions.jj` or `maverick.library.actions.workspace`
2. **Epic-to-workspace mapping** — supervisor tracks `{epic_id: workspace_name}` dict
3. **Land per-epic** — land needs to handle individual epic merges, not just "the workspace"
4. **Commit discipline prompts** — implementer prompt includes "commit before and after each assumption" guidance

#### Future Connection to Juju

If Jujutsu's planned CRDT-based sync layer materializes, the human and agent could edit the same DAG concurrently — the human corrects an assumption in their working copy while the agent builds new work in its own working copy, and the sync layer handles merge semantics. The per-epic workspace model is a natural stepping stone to this.

---

## Runway Seed Agent Fix

### Status: Broken (pre-existing)

`maverick runway seed` runs the seed agent which should write architecture.md, conventions.md, review-patterns.md, and tech-stack.md to `.maverick/runway/semantic/`. The agent completes but no files are written. The ACP executor may not be passing the Write tool permission correctly, or the agent's prompt doesn't result in file creation.

**Workaround:** Manually populate semantic files from existing project documentation or memory files.

**Impact:** Without seed, the runway semantic layer starts empty and only gets `consolidated-insights.md` after fly+land cycles produce enough episodic data for consolidation.

---

## Conditional Verification in Land

### Status: Designed in architecture doc, not implemented

When beads are committed optimistically (with pending human review), land currently treats them as fully verified. The architecture doc proposes **conditional verification**: items contingent on unvalidated assumptions are flagged as "verified conditional on assumption AV-003 holding." When AV-003 is validated, conditional items become unconditional. When rejected, affected items are re-verified after correction.

**Depends on:** Per-epic workspaces, assumption-to-commit mapping.

---

## Variable Pipeline by Bead Type

### Status: Designed in architecture doc, not implemented

Not every bead needs the full implement→gate→spec→review→commit pipeline. The architecture doc proposes stage sequences that vary by bead type:

- **Implementation beads**: Full pipeline (plan → refuel → fly → land)
- **Assumption validation beads**: Lighter flow (human review → decide → optionally spawn correction)
- **Correction beads**: Full pipeline, scoped to fixing a specific assumption

All are beads in the same graph. They just process differently. The fly supervisor would check the bead's category/labels to determine which stages to run.

---

## Provider-Agnostic Interactive Review (Mode B)

### Status: Designed, deferred

`maverick review` currently captures structured decisions (approve/reject/defer). A future `--interactive` flag could launch a full conversational session with an ACP agent, pre-loaded with the bead's context. For Claude: `claude --append-system-prompt-file /tmp/bead-context.md`. For other providers: a thin ACP REPL loop.

This is for humans who want to dive deeper than the structured form allows — read code, ask questions, make edits — before rendering their judgment.

---

## Assumptions as Spec Quality Signal

### Status: Concept from architecture doc

A high assumption count during fly is an indirect signal that the spec had gaps or ambiguities. Tracking assumption frequency per flight plan and per spec section creates a feedback loop: assumption patterns inform better spec writing over time.

Could be implemented as a runway consolidation metric: "this flight plan generated N assumption beads, concentrated in sections X and Y."
