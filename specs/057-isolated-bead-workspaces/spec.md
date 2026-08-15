# Feature Specification: Isolated Bead Workspaces

**Feature Branch**: `057-isolated-bead-workspaces`

**Created**: 2026-08-12

**Status**: Draft

**Input**: User description: "Generalize the spec-chain's hidden-workspace mechanism into a reusable isolated-execution primitive, and amend Guardrail 0 from 'no workspaces' to 'no bd inside a workspace' — its actual load-bearing constraint."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A workflow runs an agent step in isolation (Priority: P1)

A workflow author needs an agent to make file changes without those changes
being visible in the user's checkout while the agent is working. They hand a
unit of work to the isolation primitive: it provisions an isolated copy of
the repository, runs the agent's file mutations there, and on success folds
the resulting delta into the user's checkout as one application. On failure
it discards everything, leaving the checkout exactly as it was.

**Why this priority**: This is the primitive itself. Everything else in the
feature is either a consumer of it or documentation about it. Without this,
nothing else can be built.

**Independent Test**: Drive the primitive directly with a stub unit of work
that writes known files. Verify the checkout is untouched while the agent
step is running, contains exactly the expected delta after success, and is
bit-for-bit unchanged after a forced failure.

**Acceptance Scenarios**:

1. **Given** a clean checkout and a unit of work that creates and edits
   files, **When** the unit runs to completion successfully, **Then** the
   checkout contains exactly those creations and edits and nothing else.
2. **Given** a unit of work whose agent step is still executing, **When** the
   checkout is inspected, **Then** none of the unit's file changes are
   present.
3. **Given** a unit of work that raises an error during its agent step,
   **When** the primitive handles the failure, **Then** the checkout is
   byte-identical to its pre-unit state and no isolated state remains
   referenced.
4. **Given** a unit of work whose delta cannot be applied cleanly to the
   checkout's current state, **When** fold-back is attempted, **Then** the
   unit fails with a diagnostic naming the conflicting paths, and the
   checkout is left unchanged.
5. **Given** a unit of work that needs an input file not present in
   committed history, **When** the caller seeds that input, **Then** the
   agent can read it inside the isolated copy.
6. **Given** a unit of work that produced no file changes, **When** it
   completes, **Then** fold-back succeeds as a no-op and reports zero
   changed paths.

---

### User Story 2 - A unit of work is verified before it is kept (Priority: P2)

A unit of work carries checks that decide whether its output is acceptable.
Cheap checks that only inspect the produced artifacts run before the delta
ever reaches the checkout. Checks that need the project's installed
toolchain run against the checkout immediately after fold-back — and if they
fail, the fold-back is undone and the checkout returns to its pre-unit state
before anything is committed or the next unit begins.

**Why this priority**: Without this, isolated mode is strictly less capable
than the normal path, because the normal path verifies its work. This is the
half of the contract that makes isolation adoptable rather than a
demonstration.

**Independent Test**: Run a unit whose environment verification is rigged to
fail, and assert the checkout is byte-identical to its pre-unit state
afterwards, nothing was committed, and the failure is attributed to
verification rather than to the agent.

**Acceptance Scenarios**:

1. **Given** a unit of work with artifact-level checks, **When** those checks
   fail, **Then** the delta is discarded without ever reaching the checkout.
2. **Given** a unit of work with environment-level checks, **When** the agent
   step completes, **Then** the delta is folded back and the checks run
   against the checkout.
3. **Given** environment-level checks that fail, **When** the failure is
   handled, **Then** the fold-back is undone, the checkout is byte-identical
   to its pre-unit state, and nothing is committed.
4. **Given** a unit that failed environment verification, **When** a fix
   round begins, **Then** the rejected delta and the verification output are
   both available to the fixing agent without it having to reproduce the
   work.
5. **Given** an undo that itself fails, **When** the failure is detected,
   **Then** the run halts immediately with a diagnostic naming the exact
   state the checkout is in and the action required to recover, and no
   further unit begins.
6. **Given** any unit of work, **When** it is committed, **Then** every check
   it declared has passed.

---

### User Story 3 - `maverick fly` runs each bead in isolation (Priority: P3)

An operator enables isolated mode on a fly run. Each bead is implemented,
reviewed, and fixed inside its own isolated workspace; only when the bead is
complete and verified does its work stay in the checkout, committed with the
same message shape a normal run produces. The operator watching the checkout
never sees a partially-implemented bead.

**Why this priority**: This is the proof that the fold-back and undo
mechanics are real under the most demanding existing consumer, and it is the
capability the concurrent dispatcher will later depend on.

**Independent Test**: Run the same set of beads twice against equivalent
starting states — once in normal mode, once in isolated mode — and compare
the resulting commit history and file contents.

**Acceptance Scenarios**:

1. **Given** a set of ready beads, **When** they are flown in isolated mode
   and again in normal mode from the same starting state, **Then** the
   resulting commit history is identical in subjects, trailers, file
   contents, and order.
2. **Given** isolated mode is enabled, **When** a bead's implement, review,
   and fix rounds run, **Then** every agent step among them executes in
   isolation, and the checkout retains nothing from the bead until it is
   committed.
3. **Given** isolated mode is not enabled, **When** a fly run executes,
   **Then** its behavior is unchanged from today in every observable respect.
4. **Given** a bead whose delta conflicts on fold-back, **When** the conflict
   is detected, **Then** that bead fails with a diagnostic and the run's
   existing bead-failure policy applies to it; other beads are unaffected.
5. **Given** isolated mode is enabled, **When** a bead records an assumption
   or is marked complete, **Then** those bead and ledger writes occur against
   the user's checkout, not the workspace.

---

### User Story 4 - The bd-stays-out invariant is structurally enforced (Priority: P4)

A future contributor adds a workflow that uses isolation. They cannot
accidentally reintroduce the failure that retired hidden workspaces the first
time, because the shape of the primitive makes issuing a bead, ledger, or
commit-graph write against an isolated workspace something they have to go
out of their way to do — and it fails loudly if they do.

**Why this priority**: This converts a convention into a guarantee. It is
separable from the primitive's happy path, and the feature is still useful
without it — just more fragile.

**Independent Test**: Attempt, from a test, to perform a bead, ledger, or
commit operation scoped to an isolated workspace and assert it is refused
with a clear error rather than silently producing wrong state.

**Acceptance Scenarios**:

1. **Given** an isolated workspace, **When** any bead, ledger, or
   commit-graph operation is attempted with that workspace as its target
   directory, **Then** the operation is refused with an explicit error naming
   the violated invariant.
2. **Given** a unit of work executing in isolation, **When** the agent is
   given its working context, **Then** that context references only the
   isolated workspace and never the user's checkout path.
3. **Given** the codebase, **When** every bead, ledger, and commit-graph call
   site is examined, **Then** each one is demonstrably scoped to the user's
   checkout.

---

### User Story 5 - Isolation never accumulates garbage (Priority: P5)

An operator interrupts runs, loses power mid-bead, and abandons features.
Over weeks of this, their machine does not fill up with orphaned workspaces,
and their commit graph does not accumulate stray anonymous heads.

**Why this priority**: An unbounded leak is a real operational defect, but it
degrades slowly and does not block the feature's value.

**Independent Test**: Create workspaces, abandon them by simulating
interruption, run the sweep, and assert only workspaces backing genuinely
resumable work survive.

**Acceptance Scenarios**:

1. **Given** a unit of work that completed successfully, **When** it
   finishes, **Then** its workspace is torn down and no longer registered.
2. **Given** workspaces left behind by earlier interrupted runs, **When** a
   new run starts for the same project, **Then** those workspaces are swept
   unless they back work the system can still resume.
3. **Given** one workspace that cannot be deleted, **When** the sweep runs,
   **Then** every other eligible workspace is still collected and the failure
   is reported without aborting the run.
4. **Given** any set of surviving or missing workspaces, **When** the system
   next runs, **Then** correctness does not depend on any workspace having
   survived — all durable outcomes live in the user's checkout.

---

### User Story 6 - The headless spec chain runs on the shared primitive (Priority: P6)

An operator runs `maverick spec` exactly as before — including resuming a
halted chain — and observes no difference. Underneath, the chain no longer
carries its own workspace and landing implementation; it is a consumer of the
same primitive `maverick fly` uses.

**Why this priority**: This is the payoff that makes the primitive genuinely
shared rather than a second mechanism sitting beside the first. It ranks low
in delivery order because it puts a shipped, resumable workflow at risk and
should follow a primitive that is already proven by another consumer.

**Independent Test**: Run a full chain and a resumed halted chain before and
after migration, and compare landed artifacts, checkpoint contents, and
terminal output.

**Acceptance Scenarios**:

1. **Given** a spec chain run end to end, **When** it completes, **Then** the
   artifacts landed in the checkout are the same as before migration.
2. **Given** a chain halted partway, **When** it is re-run, **Then** it
   resumes from the first incomplete step exactly as before migration.
3. **Given** a chain step that fails, **When** the failure is handled,
   **Then** no partial artifacts from that step are present in the checkout.
4. **Given** the migrated chain, **When** the codebase is inspected, **Then**
   there is no workspace provisioning, fold-back, or teardown implementation
   specific to the spec chain.
5. **Given** a checkpoint written before the migration, **When** a chain is
   resumed after it, **Then** the resume either succeeds or fails with an
   explicit, actionable message — never silently misbehaves.

---

### User Story 7 - The constitution describes the system that exists (Priority: P7)

A contributor — human or agent — reads Guardrail 0 and can correctly answer
"may my workflow run an agent in an isolated workspace?" without consulting
source code or spec history.

**Why this priority**: Stale governance text actively misleads agents that
read it as instruction. It ranks last only because it depends on the final
shape of everything above.

**Independent Test**: Read the amended Guardrail 0 and the workspace appendix
cold and check them against the delivered behavior for contradictions and for
the now-removed "one documented exception" framing.

**Acceptance Scenarios**:

1. **Given** the amended constitution, **When** Guardrail 0 is read, **Then**
   it states the single-repo model, the bd-stays-out invariant, and that
   isolated agent-side execution is permitted under this feature's contract.
2. **Given** the amended constitution, **When** it is searched for the
   framing that treats the spec chain as a one-off exception, **Then** that
   framing is gone.
3. **Given** the amendment, **When** it is checked against the governance
   section's own amendment process, **Then** the version, ratification
   metadata, and impact record follow that process.

---

### Edge Cases

- **Environment verification fails**: the delta is in the checkout and must
  come back out. The undo path is a first-class, exercised path, not a
  best-effort cleanup.
- **Undo itself fails**: the checkout is left holding unverified work. This
  is the worst state the feature can produce, so it must halt the run
  immediately and tell the user precisely what is present and how to recover.
  It must never be swallowed, retried silently, or followed by another unit.
- **Fold-back conflict**: the checkout moved underneath a long-running unit
  of work — a concurrent human edit, or a prior unit touching the same lines.
  The unit fails with the conflicting paths named; no resolution is attempted
  and no partial delta lands.
- **Provisioning failure**: isolation cannot be created — a name collision
  with a previously-registered-but-deleted workspace, an unwritable workspace
  root, or exhausted disk. The unit must fail before the agent runs, with a
  diagnostic distinguishing "could not isolate" from "the work failed".
- **Hard interruption during fold-back or undo**: the process is killed
  mid-application. The checkout must be recoverable to either the pre-unit or
  the post-unit state, and the next run must detect and report the situation
  rather than proceeding on top of it.
- **Ignored paths**: the agent creates build output, virtual environments, or
  other ignored artifacts inside the isolated copy. These must not fold back.
- **Orchestrator-owned state**: run metadata, bead storage, and ledger state
  must not fold back from a workspace even if the agent touched them.
- **Repository not prepared for isolation**: the checkout lacks the
  version-control state isolation requires. The command must refuse with an
  actionable message rather than silently falling back.
- **Two runs in one checkout**: a second run starts while another holds
  isolated workspaces for the same project. The second must not sweep or
  reuse the first's live workspaces, and must not fold back over an in-flight
  verification window belonging to the first.
- **Protected context files**: existing agent-context-file protection must
  remain in force inside isolation, and blocked writes must still be reported
  on the run.
- **Empty delta**: a unit completes having changed nothing. Fold-back is a
  successful no-op, not an error.

## Requirements *(mandatory)*

### Functional Requirements

#### The isolation primitive

- **FR-001**: The system MUST provide a single reusable isolated-execution
  primitive that any workflow can use to run an agent step against an
  isolated copy of the repository.
- **FR-002**: The primitive MUST provision isolation per unit of work, keyed
  so that two units — whether sequential or overlapping — never share an
  isolated copy.
- **FR-003**: The isolated copy MUST present the repository's committed state
  so the agent sees the same source tree it would see in the checkout.
- **FR-004**: The primitive MUST allow the caller to seed additional inputs
  into the isolated copy that are not part of committed history.
- **FR-005**: On successful completion of a unit's agent step and its
  artifact-level checks, the primitive MUST fold the unit's file delta into
  the user's checkout as a single application.
- **FR-006**: On failure, error, or abort of the agent step, the primitive
  MUST discard the unit's delta entirely, leaving the checkout byte-identical
  to its pre-unit state.
- **FR-007**: While a unit's agent step is executing, none of that unit's
  file changes may be visible in the user's checkout.
- **FR-008**: When a delta cannot be applied cleanly, the primitive MUST fail
  the unit with a diagnostic naming the conflicting paths, and MUST NOT
  attempt resolution.
- **FR-009**: The primitive MUST report each unit's outcome as a typed result
  distinguishing success, discard-on-failure, fold-back conflict, and
  verification rejection, and MUST include the set of paths applied.
- **FR-010**: Paths ignored by the repository's ignore rules MUST NOT be
  folded back into the checkout.
- **FR-011**: Orchestrator-owned state — run metadata, bead storage, and
  ledger state — MUST NOT be folded back from an isolated workspace under any
  circumstances.

#### Verification and undo

- **FR-012**: A unit of work MUST be able to declare checks at two
  placements: artifact-level checks that run inside isolation before
  fold-back, and environment-level checks that run against the checkout after
  fold-back.
- **FR-013**: Artifact-level checks MUST NOT require any state absent from
  committed history; a unit whose artifact-level checks fail MUST have its
  delta discarded without ever reaching the checkout.
- **FR-014**: When environment-level checks fail, the system MUST undo the
  fold-back, restoring the checkout byte-identical to its pre-unit state.
- **FR-015**: The window in which an unverified delta is present in the
  checkout MUST be bounded by that unit's environment-level checks, and no
  other unit may begin during it.
- **FR-016**: Nothing MUST be committed until every check the unit declared
  has passed.
- **FR-017**: A rejected delta and its verification output MUST be preserved
  and made available to a subsequent fix round, so the fixing agent does not
  have to reproduce the work.
- **FR-018**: If an undo fails, the system MUST halt the run immediately with
  a diagnostic naming what the checkout now contains and the action required
  to recover, and MUST NOT begin another unit of work.
- **FR-019**: A verification rejection MUST be reported distinctly from an
  agent failure and from a fold-back conflict.

#### The isolation boundary

- **FR-020**: Bead, ledger, and commit-graph writes MUST occur only in the
  orchestrating process against the user's checkout.
- **FR-021**: Any attempt to perform a bead, ledger, or commit-graph
  operation targeting an isolated workspace MUST be refused with an explicit
  error naming the violated invariant, rather than executing.
- **FR-022**: The enforcement in FR-021 MUST be structural — a contributor
  must have to actively defeat it, not merely forget a convention.
- **FR-023**: An agent executing in isolation MUST receive only the isolated
  workspace as its working context, never the user's checkout path.

#### Lifecycle

- **FR-024**: An isolated workspace MUST be created for a unit of work and
  torn down when that unit completes successfully.
- **FR-025**: A workspace backing work the system can still resume MUST be
  retained; all others MUST be eligible for collection.
- **FR-026**: The system MUST sweep abandoned workspaces belonging to the
  current project on subsequent runs, and MUST NOT touch workspaces belonging
  to other checkouts.
- **FR-027**: A workspace that cannot be collected MUST NOT prevent the
  collection of others, and MUST NOT fail the run.
- **FR-028**: System correctness MUST NOT depend on any isolated workspace
  surviving between runs; all durable outcomes live in the user's checkout.
- **FR-029**: Tearing down a workspace MUST leave no residual registration or
  stray head visible in the user's commit graph.

#### `maverick fly` isolated mode

- **FR-030**: `maverick fly` MUST support an opt-in isolated mode, disabled
  by default, requiring one explicit user action to enable.
- **FR-031**: In isolated mode, each bead MUST execute in its own workspace,
  and beads MUST still run strictly serially.
- **FR-032**: Every agent step belonging to a bead — implement, review, and
  each fix round — MUST execute in isolation.
- **FR-033**: The commit produced for a bead in isolated mode MUST carry the
  same subject prefix and bead trailer the in-checkout path produces, and
  MUST be created by the orchestrator against the user's checkout.
- **FR-034**: A fold-back conflict MUST fail only the bead that caused it;
  the run's existing bead-failure policy MUST govern what happens next.
- **FR-035**: With isolated mode disabled, fly's behavior MUST be unchanged
  from today in every observable respect.
- **FR-036**: Existing agent-context-file protection MUST remain in force for
  agents running inside isolation, and blocked writes MUST be reported on the
  run as they are today.
- **FR-037**: The system MUST refuse to run in isolated mode, with an
  actionable message, when the repository is not in a state that supports
  isolation.

#### Spec-chain migration

- **FR-038**: The headless spec chain MUST be rebuilt on the shared
  primitive, including its per-step artifact landing.
- **FR-039**: After migration, no workspace provisioning, fold-back, or
  teardown implementation specific to the spec chain may remain.
- **FR-040**: The chain's user-visible behavior MUST be unchanged: the same
  artifacts land, at the same per-step granularity, with the same terminal
  output and exit-code semantics.
- **FR-041**: Chain resume MUST continue to work, resuming from the first
  incomplete step and re-verifying already-landed artifacts as it does today.
- **FR-042**: A chain step's artifacts MUST continue to reach the checkout
  only after that step is verified complete, using artifact-level checks per
  FR-012.
- **FR-043**: A checkpoint written before the migration MUST either resume
  correctly afterwards or fail with an explicit, actionable message — never
  silently misbehave.

#### Governance

- **FR-044**: Guardrail 0 MUST be amended to state the single-repo model, the
  bd-stays-out invariant, and that isolated agent-side execution is permitted
  under this feature's contract.
- **FR-045**: The amended text MUST NOT describe the headless spec chain as a
  one-off exception.
- **FR-046**: Supporting governance material describing workspace isolation
  MUST be updated to describe the general primitive rather than a single
  workflow's mechanism.
- **FR-047**: The amendment MUST follow the constitution's own documented
  amendment process, including its versioning and impact-record requirements.

### Key Entities

- **Unit of Work**: the smallest thing that is isolated and folded back as
  one. A bead in fly; a chain step in the spec chain. Carries an identity,
  the inputs it needs seeded, the agent step to execute, and the checks it
  declares at each placement.
- **Isolated Workspace**: a provisioned, per-unit copy of the repository's
  committed state, in which agent file mutations occur. Holds nothing durable
  and is disposable by design.
- **Fold-Back Result**: the typed outcome of applying a unit's delta —
  success with the applied path set, discard after failure, conflict with the
  conflicting path set, or verification rejection.
- **Rejected Delta**: a unit's file changes plus the verification output that
  rejected them, preserved for a subsequent fix round.
- **Isolation Boundary**: the enforced separation between what may run inside
  a workspace (agent file mutations, artifact-level checks) and what may not
  (bead, ledger, and commit-graph writes).
- **Workspace Registry**: the record of which workspaces exist, which unit
  each backs, and which are eligible for collection.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For an identical set of beads and starting state, an
  isolated-mode run and a normal-mode run produce identical resulting history
  — same commit subjects, trailers, ordering, and final file contents.
- **SC-002**: Across a complete isolated-mode run, the user's checkout is
  observed to contain changes from a unit whose agent step is still executing
  zero times.
- **SC-003**: For every failure mode exercised — agent error, artifact-check
  failure, environment-check failure, interruption, fold-back conflict — the
  checkout is left byte-identical to its pre-unit state 100% of the time.
- **SC-004**: Zero commits are produced for units that did not pass every
  check they declared.
- **SC-005**: A fold-back conflict names every conflicting path in its
  diagnostic, and affects exactly one unit of work.
- **SC-006**: The number of bead, ledger, or commit-graph operations issued
  against a workspace path is zero, verifiable by inspecting every such call
  site.
- **SC-007**: After any sequence of interrupted and abandoned runs, a
  subsequent run leaves behind only the workspaces backing genuinely
  resumable work — no orphans accumulate across runs.
- **SC-008**: There is exactly one implementation of provisioning, fold-back,
  and teardown in the codebase, consumed by both `maverick fly`'s isolated
  mode and the headless spec chain.
- **SC-009**: The headless spec chain's landed artifacts, per-step
  granularity, resume behavior, and exit codes are unchanged before and after
  migration.
- **SC-010**: A reader can determine from the amended Guardrail 0 alone,
  without consulting source or spec history, whether a given workflow may run
  an agent in isolation.
- **SC-011**: Isolated mode is off by default and requires exactly one
  explicit user action to enable; no existing invocation changes behavior.

## Clarifications

### Session 2026-08-12

- **Q**: Where do a unit of work's verification commands run, given the
  isolated copy carries only committed state and development toolchains are
  not committed? → **A**: Fold back first, verify against the checkout, and
  undo on failure.
- **Q**: How much of the headless spec chain migrates onto the primitive? →
  **A**: Full migration, including its per-step landing.

### Resolution of the tension between the two answers

Taken literally, these two answers conflict. The spec chain exists precisely
so that *only verified artifacts reach the checkout*; verify-after-fold-back
would invert that and expose half-written spec artifacts, which is the
behavior spec 050 was written to prevent.

The spec resolves this by splitting verification into two placements
(FR-012), distinguished by an objective criterion rather than by workflow
preference: **does the check need state that is absent from committed
history?**

- **Artifact-level checks** need nothing uncommitted — they inspect the files
  the unit produced. They run inside isolation, before fold-back. The spec
  chain's step verification is entirely of this kind (FR-042), so its
  "nothing lands until it is complete" guarantee survives migration intact.
- **Environment-level checks** need the installed toolchain. They run against
  the checkout after fold-back, with undo on failure (FR-014). `maverick
  fly`'s test, lint, and type checks are of this kind.

This keeps the chosen answer to Q1 where it is actually needed, and confines
its cost — a bounded window in which an unverified delta sits in the checkout
(FR-015) — to the consumer that requires it.

## Assumptions

- The repository is prepared for isolation by existing project
  initialization; the feature does not introduce a new setup step, and
  refuses rather than falling back when that state is absent (FR-037).
- Isolated workspaces live outside the user's checkout, under the same
  per-project location the headless spec chain already uses, so the checkout
  never contains them.
- The undo required by FR-014 builds on the project's existing
  capture-a-restore-point-then-restore transaction pattern rather than
  introducing a new one; that pattern is already used to make multi-step
  history corrections recoverable.
- Isolated mode is enabled by both a command-line flag and a configuration
  key, with the flag taking precedence — matching how comparable options
  behave today.
- Conflict *resolution* is out of scope. This feature detects conflicts and
  fails the affected unit; resolution machinery arrives with the concurrent
  dispatcher.
- Concurrency is out of scope. Isolated fly mode remains strictly serial;
  this feature only removes the structural obstacle to concurrency.
- Fly's existing two-stage interrupt contract, bead-failure policy, cost
  telemetry, and progress-event surface are unchanged by isolated mode.
- The assumption ledger, the land frontier gate, and the reconcile detection
  path are unaffected — those all read state written in the checkout.
- Whether the constitution amendment is a major or minor revision is
  determined by the governance section's own criteria at plan time, not
  presumed here.
- No new external dependency is required; isolation builds on version-control
  capabilities the project already relies on.

## Out of Scope

- Resolving fold-back conflicts automatically, interactively, or by agent.
- Running beads concurrently, or any dispatcher, scheduler, or work-stealing
  behavior.
- Making isolated mode the default for `maverick fly`.
- Provisioning development toolchains or installed dependencies into an
  isolated workspace — the verification split (FR-012) exists so this is not
  required.
- Running bead storage inside a workspace, or federating it across
  workspaces.
- Containerized or remote execution environments.
- Isolating any workflow other than `maverick fly` and the headless spec
  chain in this feature.
