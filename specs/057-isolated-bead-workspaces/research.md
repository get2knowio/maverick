# Phase 0 Research: Isolated Bead Workspaces

**Feature**: 057-isolated-bead-workspaces | **Date**: 2026-08-20

Every decision below that touches jj mechanics was validated against a real jj
0.44 colocated repository before being written down. Commands and observed
output are quoted where the behavior is load-bearing.

---

## R1. How does an agent step get pointed at a workspace?

**Decision**: Hoist the spec chain's `os.chdir` seam into
`src/maverick/workspace/cwd_scope.py` and share it. One module-level
`asyncio.Lock` serializes every chdir-scoped agent execution in the process.

**Rationale**: airframe 0.9.2 — the installed version — still exposes no
working-directory field on the default provider:

```
ClaudeOptions          ['append_system_prompt', 'fork_session', 'strict_mcp_config']
CopilotOptions         ['available_tools', 'excluded_tools', 'skill_directories', 'working_directory']
OpenCodeServerOptions  ['provider_id', ..., 'working_directory', ...]
```

`Agent.__init__` already takes and stores `cwd`, but only `SpecChainAgent`
consumes it — via exactly this chdir pattern, already blessed by constitution
Appendix E. Every other agent inherits the process working directory, which is
why fly works today only because the process cwd *is* the checkout.

**Alternatives considered**:

- *Per-provider `working_directory`*: leaves the `claude` provider — the default
  binding — unable to isolate. Isolated mode would silently write to the
  checkout on the most common configuration. Rejected as worse than not
  shipping.
- *Upstream a `cwd` parameter to airframe*: the correct long-term fix, and the
  documented exit criterion in plan.md's Complexity Tracking. Blocks this
  feature on an external release, so not now.
- *Run the agent as a subprocess with `cwd=`*: airframe owns process management;
  reimplementing it violates Guardrail X.5.

**Consequence**: agent execution is process-serialized. FR-031 (serial beads)
and FR-048 (one isolated run per checkout) already require that, so the lock
costs nothing today — but it is the hard blocker for the concurrent dispatcher
(roadmap prompt 9), and that should be stated plainly rather than discovered
later.

---

## R2. How does a delta move from the workspace into the checkout?

**Decision**: `jj squash --from '<workspace>@' --into @ '<filesets>'`, executed
from the checkout.

**Rationale**: validated end to end. Setup — a colocated repo with a workspace
`ws1`, where the workspace modified `a.txt`, deleted `b.txt`, created `c.txt`,
and also touched `.maverick/runs/r.json`:

```
$ jj squash --from 'ws1@' --into @ '~.maverick'
Added 1 files, modified 1 files, removed 1 files

$ jj status
Working copy changes:
M a.txt
D b.txt
A c.txt
```

Three requirements fall out of the mechanism rather than needing code:

- **FR-010** (ignored paths must not fold back): jj does not track ignored
  paths, so `.beads/`, `.venv/`, `target/`, `*.jsonl` never enter the
  workspace's working-copy commit and cannot travel.
- **FR-011** (orchestrator state must not fold back): the fileset argument
  `'~.maverick'` excludes it explicitly. Verified — after the squash above the
  checkout's `.maverick/runs/r.json` still read `run`, not the workspace's
  `agentstate`. `/.maverick/runs` and `/.maverick/notify` are gitignored anyway;
  the fileset makes it a contract rather than an accident of `.gitignore`.
- **Modify, create, and delete** all travel correctly in one application
  (FR-005's "single application").

**Alternatives considered**:

- *File-level staged copy* (what `spec_chain/landing.py` does today): would
  require reimplementing ignore-rule filtering, delete/rename handling, and a
  byte-level undo. jj already has all three. Rejected — but note the chain's
  scoped landing survives as a **fileset argument** (R6), so migration is a
  narrowing of this same call, not a replacement of it.
- *`jj rebase` / `jj new` + merge*: rewrites history rather than moving a
  working-copy delta, and would surface in the user's `jj log`.

---

## R3. The workspace must be snapshotted before fold-back

**Decision**: run a jj command *inside* the workspace (`jj status`, wrapped as
`JjClient.status()` bound to the workspace path) immediately before the squash.

**Rationale**: this is the sharpest edge in the whole mechanism and it fails
**silently**. jj auto-snapshots only the *current* workspace's working copy. A
squash issued from the checkout therefore moves whatever was last snapshotted
into `<ws>@` — which, for a workspace whose files were written by an agent and
never touched by a jj command, is *nothing*. Observed directly:

```
# ws2/a.txt edited by hand, no jj command run in ws2
$ jj squash --from 'ws2@' --into @ '~.maverick'
$ cat a.txt
hello
CHECKOUT EDIT          # <-- the workspace's line is missing, no error

# same edit, after running `jj status` inside ws2
$ jj squash --from 'ws2@' --into @ '~.maverick'
$ cat a.txt
hello
CHECKOUT EDIT
WS2 ADD                # <-- correct
```

A missing snapshot produces a successful, empty fold-back — indistinguishable
from "the agent changed nothing" (FR-006's legitimate empty-delta case). This
must be a single chokepoint in `foldback.py`, never a step a caller can forget,
and it needs its own regression test.

**Comparable precedent**: `workspace_forget` must precede directory removal or
jj strands an anonymous head in the user's graph — the same class of ordering
constraint, already documented in `workspace/spec_chain.py`.

---

## R4. Conflict detection

**Decision**: after the squash, query the existing `jj_list_conflicts` action;
a non-empty result means conflict → restore the captured operation → return
`FoldBackOutcome.CONFLICT` with the conflicting paths.

**Rationale**: jj does not fail on conflict, it *materializes* one. Validated
with a checkout edit and a workspace edit to the same file from a common base:

```
$ jj squash --from 'ws1@' --into @ '~.maverick'
Once the conflicts are resolved, you can inspect the result with `jj diff`.

$ jj status
Working copy  (@) : xwktyysp 44433777 (conflict) (no description set)
Warning: There are unresolved conflicts at these paths:
a.txt    2-sided conflict

$ jj log -r 'all() & conflicts()' --no-graph -T 'change_id.short()'
xwktyysppzzz
```

Treating a zero-exit-status squash as success is therefore wrong: **the exit
code is not the signal, the `conflicts()` revset is**. Conflicting paths come
from `jj resolve --list` (or the `jj status` warning block) and satisfy FR-008's
"naming the conflicting paths" and SC-005.

---

## R5. Undo

**Decision**: capture `JjClient.snapshot_operation()` in the checkout before the
squash; undo is `restore_operation(op_id)`.

**Rationale**: this is the transaction pattern 051-reconcile-changed-answers
already uses (its research R8), so FR-014 introduces no new mechanism — exactly
what the spec's Assumptions section anticipated. Validated for both the
clean-undo and post-conflict cases:

```
$ jj op restore 0a3c1bd7b8dc
$ jj status
The working copy has no changes.
$ cat a.txt b.txt
hello
keep                   # <-- byte-identical to pre-unit state
```

Two properties matter beyond the obvious one:

1. **The checkout's own uncommitted work survives.** In the conflict test the
   checkout held an unrelated edit (`CHECKOUT EDIT`) before the fold-back; after
   `op restore` it was back, unchanged. `op restore` rewinds the *operation*,
   not the working copy's content in isolation.
2. **The rejected delta returns to the workspace.** `op restore` rewinds the
   workspace's working-copy commit too, so after an undo the workspace still
   holds the full delta:

```
$ cd ../ws1 && jj status
Working copy changes:
M .maverick/runs/r.json
M a.txt
D b.txt
A c.txt
```

FR-017 ("the rejected delta and its verification output must be available to the
fix round") therefore costs nothing extra — the fix agent resumes in the same
workspace with its work intact. One mechanism, two requirements.

**Caveat to handle**: a squash abandons the source working-copy commit and jj
gives that workspace a fresh empty one, which can leave the workspace's on-disk
copy stale relative to the repo. After a *successful* fold-back the workspace is
torn down, so it does not matter; after an *undone* one the restore puts the
commit back. `jj workspace update-stale` is the recovery if a stale-working-copy
error ever surfaces, and `foldback.py` should handle that error rather than
letting it escape as an opaque `JjError`.

---

## R6. Where does verification run, and in what order?

**Decision**: map fly's existing checks onto the spec's FR-012 placements by the
spec's own criterion — does the check need state absent from committed history?

| fly check | Placement | Where it runs | Why |
| --- | --- | --- | --- |
| `ac_check` (file scope, diff overlap, grep commands) | artifact-level | workspace | Reads produced files and the working-copy diff. Needs no toolchain. |
| `spec_check` | artifact-level | workspace | Same. |
| `gate` (`format`, `lint`, `test` via `run_independent_gate`) | environment-level | checkout, after fold-back | Needs `.venv`/`uv` and the installed toolchain, which are gitignored and do not travel into a workspace. |
| `review` (agent) | n/a — agent step | workspace | FR-032: every agent step is isolated. |

**Consequence — an isolated-mode-only reordering.** Today the graph runs
`implement → gate → ac_check → spec_check → review → commit`. Under isolation
the gate cannot run until the delta is in the checkout, and every agent step
(including review and its fix rounds) must stay in the workspace. Interleaving
them would mean folding back and undoing repeatedly around each agent call. So
isolated mode runs:

```
implement(W) → ac_check(W) → spec_check(W) → review(W) [+ fix rounds in W]
    → fold_back → gate(checkout)
        ├─ pass → commit(checkout) → teardown(W)
        └─ fail → undo → gate fix(W) → fold_back → gate ...
```

**Rationale**: this yields exactly one fold-back per gate attempt, keeps every
agent step isolated (FR-032), bounds the unverified-delta window to the gate
itself (FR-015), and guarantees the gate result describes the tree that is
committed (FR-016).

**Alternatives considered**:

- *Keep gate first, undo unconditionally, re-fold at the end*: the gate would
  then describe a tree that later review fixes changed, so FR-016 would need a
  second gate run anyway. Strictly more work for a weaker guarantee.
- *Re-provision the workspace from `@` after each successful fold-back*: keeps
  the original ordering, but spends a provision per agent step and complicates
  the undo story. Rejected on the FR-050 budget.

**Cost, stated plainly**: in isolated mode a bead that would fail the gate now
pays for a review first. That is a real behavioral difference, confined to
isolated mode (FR-035 keeps the default path byte-identical), and it does not
affect SC-001 — the resulting *history* is what must match, not the internal
step order.

---

## R7. Workspace identity, reuse, and retention

**Decision**: workspaces live at
`~/.maverick/workspaces/<project>/<workflow>/<key>/`, with `(workflow, key)`
supplied by the consumer and a `retain_on_failure` policy flag.

| Consumer | key | reuse across steps | retained on failure |
| --- | --- | --- | --- |
| fly | bead id | n/a (one unit) | no — the bead is retried from the checkout |
| spec chain | feature slug | yes — all five steps share it | yes — it is the only copy of the failing step's partial output |

**Rationale**: the current `_workspace_dir(home, cwd, feature)` is already this
shape with `<workflow>` hardcoded to `spec-chain`. Adding the segment keeps
existing chain paths stable in meaning and prevents a bead named like a feature
from colliding with one. Retention policy is the one place the two consumers
genuinely differ, and the spec already encodes both sides (FR-024 vs FR-025), so
it belongs in the policy object rather than in either caller.

**Carried forward unchanged from `spec_chain.py`** (each already load-bearing,
each becoming a requirement):

- `workspace_forget` before `rmtree`, always — otherwise jj keeps tracking the
  name, blocking the next `workspace_add` *and* stranding an anonymous head in
  the user's `jj log` forever (FR-029).
- Forget even when the on-disk directory is already gone — a user who cleared
  `~/.maverick/workspaces` leaves jj-side registrations behind.
- Teardown is best-effort and never sinks a completed unit (FR-027).
- Sweep is per-entry isolated so one undeletable workspace cannot strand the
  rest (FR-027), and is scoped to this checkout's own root (FR-026).

---

## R8. Cross-run exclusion and interrupted applications

**Decision**: one pid-stamped advisory lockfile at
`.maverick/runs/isolation.lock` (FR-048) plus a separate journal file
`.maverick/runs/isolation-journal.json` (FR-049), both modeled byte-for-byte on
`workflows/reconcile/state.py`'s lock — including malformed-or-dead-pid
reclamation.

**Rationale**: the pattern exists twice already (reconcile, notify) and
Guardrail X.5 says use it rather than inventing a third. The two files are
deliberately separate concerns: the lock answers "is another run live?" and
dies with the process; the journal answers "did a previous run die
mid-application?" and must **survive** the process — that is its entire purpose.

**Contention semantics follow `reconcile`, not `notify`.** `notify` treats a
held lock as benign because overlapping cron fires are expected operation. Two
isolated fly runs in one checkout are not expected operation — they can destroy
each other's work inside the undo window — so a held lock is a hard refusal with
the holding pid named (FR-048).

**Journal lifecycle**: written before the squash and before an undo, cleared
after either completes. A run that starts and finds an uncleared record refuses
outright, reports the unit, the operation, and the captured operation id, and
tells the user how to recover. It does **not** roll back automatically —
FR-049's explicit position, and the right one: an automatic rollback would
discard whatever the user did in the checkout since the crash.

**Why not infer from the checkout's contents**: a dirty checkout is
indistinguishable from ordinary work in progress. The journal is the only
signal that cannot be confused with a legitimate state.

---

## R9. Enforcing the bd-stays-out invariant structurally

**Decision**: a single guard function in `workspace/session.py` that every bd,
ledger, and commit-graph entry point calls with its target directory; it raises
`IsolationBoundaryError` when the path resolves inside any live workspace root.
The live roots come from the session, not from a path-shape heuristic.

**Rationale**: FR-022 demands a contributor "have to actively defeat it, not
merely forget a convention". Three layers, cheapest first:

1. **Type-level** — `IsolationLease` exposes `workspace_path` but the bd/ledger
   helpers take `checkout: CheckoutPath`, a distinct `NewType`. Passing a
   workspace path is then a mypy error under strict mode, which is the layer
   that actually catches the mistake at authoring time.
2. **Runtime** — the guard above, so a dynamically-constructed path still fails
   loudly rather than silently writing to the wrong store.
3. **Test-level** — a repo-wide test asserting every bd/ledger/jj call site
   takes its directory from the checkout, satisfying FR-020 and SC-006 by
   inspection rather than by hope.

**Supporting evidence that the invariant is real**: `.beads/` is in
`.gitignore`, so bd's store provably does not travel into a `jj workspace add`
workspace. That is the exact failure that retired general-purpose workspaces —
the constraint is bd's, not the workspace's, which is the whole thesis of the
guardrail amendment.

---

## R10. Configuration surface

**Decision**: repurpose the existing but **entirely unused** `WorkspaceConfig`
(`config.py:365`) as isolation's config home: keep `root` and `reuse`, add
`enabled`, and delete `setup`/`teardown`/`env_files`.

**Rationale**: `grep -rn "config\.workspace\|WorkspaceConfig" src tests` returns
only the class definition, its `__all__` entry, and its field declaration —
nothing reads it. It is a fossil of the retired clone bridge whose `setup:`/
`teardown:` shell hooks describe a bootstrap step that no longer exists.
Introducing a second workspace-shaped block beside a dead one would be the worse
outcome; per the Operating Standard, the dead fields go.

`--isolated` / `--no-isolated` on `maverick fly` overrides
`workspace.enabled`, matching how comparable flags behave and satisfying
FR-030's "off by default, one explicit action to enable" plus SC-011.

---

## R11. Protection policy inside a workspace

**Decision**: build the `ProtectionPolicy` against the **workspace** root for
agent steps running there, and keep the fileset exclusion as a second layer on
fold-back.

**Rationale**: 056's Layer 2 backstop compares a snapshot manifest of protected
paths before and after each send. Rooted at the checkout while the agent writes
in a workspace, it would guard the wrong tree — protecting files the agent
cannot reach and ignoring the copies it can. `Squadron.open()` builds the policy
once from `cwd`; isolated mode must build it from the lease's workspace path
instead (FR-036).

Blocked writes are still reported on the run exactly as today: the
`BlockCollector` lives on the squadron, not the workspace, so
`protection_blocks` drains unchanged.

**Second layer**: even with the policy correctly rooted, the fold-back fileset
should exclude the protected set, so a protected file that somehow changed in a
workspace still cannot reach the checkout. Same belt-and-braces reasoning as
`landing.py`'s `_strip_protected_paths`, which this replaces.

---

## R12. Performance

**Decision**: budget ≤5 s per unit (FR-050); measure on this repository, in CI,
as an integration test asserting the ceiling.

**Rationale**: `jj workspace add` on a small scratch repo measured **0.024 s**.
That number is not the one that matters — the real cost is materializing the
tree into a fresh directory, which scales with repository size. The budget is
enforced as a test rather than asserted here, and the three costs it must cover
are provisioning, fold-back (one squash), and teardown (forget + `rmtree`).

**Risk if exceeded**: the mitigation is workspace reuse across beads rather than
per-bead provisioning — deliberately *not* designed in now, because per-unit
workspaces are what FR-002 requires and what the dispatcher will need. Pooling
would be a measured response to a measured problem.
