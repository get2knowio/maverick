# Feature Specification: Spec Delta Layer

**Feature Branch**: `059-spec-delta-layer`

**Created**: 2026-08-22

**Status**: Draft

**Input**: User description: "Add a delta layer for modifying existing specs, closing Spec Kit's known brownfield weakness: today, changing a shipped spec means editing spec.md in place, and `refuel --speckit`'s delta detection only handles tasks.md growth — there is no structured way to express 'this requirement changed' and have it flow deterministically into new work. Model the field's answer (OpenSpec): a change proposal is a structured artifact describing deltas against an existing spec — requirements added, modified, or removed — with a lifecycle of propose, apply, and archive. Propose: a delta document lives alongside the spec it modifies, expressing each change as ADDED, MODIFIED (with before/after), or REMOVED, in a format that is deterministically parseable (Guardrail 8: zero model calls to ingest). Apply: applying a delta rewrites spec.md and tasks.md to their new state, and refuel ingests the consequences deterministically — new tasks become new beads under the existing epic; removed requirements close their open, unstarted beads; modified requirements with in-flight or completed beads raise a flag for the human rather than silently mutating work. Archive: an applied delta is preserved as provenance — the spec's history of intentional change, distinct from git history. The spec must resolve whether this layer is purely additive on top of Spec Kit artifacts (preferred: our chain and ingestion continue to work on vanilla Spec Kit repos) or requires deviating from upstream Spec Kit conventions — and if the latter, what the compatibility story is. Out of scope: AI-authored delta proposals (a human or an upstream tool writes the delta; a later feature may generate them); retroactive reconstruction of deltas for past spec edits."

## Decisions

Recorded during specification. These were **not** produced by an interactive
`/speckit-clarify` round with a human — they are choices made while writing the
spec, kept in question form because that is how they were reasoned about. Two of
them were **revised after measurement** against this repository's own corpus;
the revisions are marked and the superseded reasoning is stated so a later
reader does not re-derive it.

- Q: Is this layer purely additive on top of Spec Kit artifacts, or does it deviate from upstream conventions? → A: **Purely additive, and structurally so.** Delta documents live in a new `deltas/` subdirectory inside the feature directory, a location upstream Spec Kit neither writes nor reads. `spec.md` and `tasks.md` keep their exact upstream format after a delta is applied — a delta's *output* is an ordinary Spec Kit artifact, indistinguishable from one a human edited by hand. A repository with no `deltas/` directory behaves exactly as it does today, and every existing command works unchanged on a vanilla Spec Kit repository. The compatibility story is therefore "there is nothing to be compatible with": upstream never sees the delta layer.
- Q: What happens when a delta modifies a requirement whose beads are already in flight or closed? → A: The apply step refuses to complete silently. It applies every unambiguous part of the delta, and for each affected requirement whose beads are not open-and-unstarted, it records a structured **impact entry** naming the requirement, the affected beads, and their states — then reports them and exits non-zero without archiving. The human resolves each impact (accept, or amend the delta) and re-runs. Silently mutating in-flight work, or silently skipping the requirement, are both worse than stopping.
- Q: Should this be built as a Spec Kit plugin rather than in Maverick? → A: **The merge logic lives in Maverick; publishing a plugin later stays open.** Spec Kit 1.0 has a real plugin architecture — installable extensions with catalog priority resolution, buildable bundles, a resumable workflow step graph with custom step types, presets, and `event run`. What it does not yet have is a *proven deterministic dispatch path* for third-party code: `provides.scripts[].runtimes` is informational only and explicitly not used to invoke the script, so extension dispatch remains agent-mediated (a hook renders a slash command; the command's markdown tells the agent to run the script). The one channel with genuine deterministic dispatch — custom workflow step types — has zero entries in either step catalog and runs only under `specify workflow run`, which resolves the project root itself and would hand orchestration to Spec Kit's engine instead of Burr, colliding with Guardrails 0 and 7. Add no stability guarantee in the 1.0.0 notes, a catalog whose maintainers state plainly that they "do not review, audit, or test the extension code itself", and discovery-only distribution, and the merge belongs where deterministic execution and orchestration already live. This is a decision about *where the logic runs*, not about whether to share it: the `speckit-inventory` extension (deterministic Python emits a requirement-ID map as JSON; the agent consumes it) is a shipping precedent for packaging the parse half as a plugin later, and nothing in this design forecloses that.
- Q: Is a changed requirement identifier a REMOVE plus an ADD? → A: No — **RENAMED is a fourth operation**. Modelling a rename as remove-plus-add destroys the requirement's bead lineage: the old requirement's beads close, new ones are created, and the continuity between them is lost even though nothing about the work changed. RENAMED carries `FROM`/`TO` and preserves coverage.
- Q: Does applying a delta run refuel automatically? → A: No. Apply rewrites the artifacts and records what changed; `refuel --speckit` remains the only thing that writes beads, and it runs as a separate, explicit step. Keeping them separate preserves `refuel --dry-run` as a preview of the bead consequences, and keeps the artifact-mutation step reviewable before any bead is touched.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Express a requirement change as a structured document (Priority: P1)

A developer needs to change a requirement in a spec that has already shipped beads. Instead of editing `spec.md` in place — losing the fact that a change happened and leaving `refuel` unable to tell what is new — they write a delta document alongside the spec that names each change: this requirement is ADDED, this one is MODIFIED (carrying its complete before and after blocks), this one is REMOVED, this one is RENAMED — and, where the change means work changes, which task lines are added and which task ids are withdrawn. The document is validated: it must reference requirements that actually exist (for MODIFIED and REMOVED), must not collide with existing requirement identifiers (for ADDED and for a RENAMED entry's target), and must parse without ambiguity.

**Why this priority**: Without a structured way to *state* the change, nothing downstream is possible. This story alone — write a delta, have it validated against the spec it targets — already delivers value as a review artifact, even before anything applies it.

**Independent Test**: Can be fully tested by writing a delta document against an existing spec and running validation, verifying that a well-formed delta passes and each malformed case (dangling reference, duplicate identifier, unparseable entry) fails with a message naming the offending entry.

**Acceptance Scenarios**:

1. **Given** a spec with requirements FR-001 through FR-005, **When** the developer writes a delta modifying FR-003 and adding one new requirement, **Then** validation passes and reports the change counts by kind.
2. **Given** a delta whose MODIFIED entry names a requirement absent from the target spec, **When** it is validated, **Then** validation fails naming the dangling identifier and the spec it was checked against.
3. **Given** a delta whose ADDED entry reuses an identifier the spec already defines, **When** it is validated, **Then** validation fails naming the collision.
4. **Given** a delta whose MODIFIED after-block omits an acceptance criterion the current spec still carries, **When** it is validated, **Then** validation fails naming the dropped criterion — an author working from a stale copy must not silently erode the spec.
5. **Given** a delta whose RENAMED entry targets an identifier the spec already defines, **When** it is validated, **Then** validation fails naming the collision.
6. **Given** any delta document, **When** it is parsed, **Then** parsing completes with zero model calls.

---

### User Story 2 - Apply a delta to produce the spec's new state (Priority: P1)

Having written and reviewed a delta, the developer applies it. The spec's requirement set is rewritten to its post-delta state, and the task list is updated to match: tasks covering added requirements appear, tasks covering removed requirements are marked as withdrawn, and the whole thing remains an ordinary Spec Kit artifact set that any other tool can read.

**Why this priority**: Applying is what makes the delta consequential rather than documentary. Together with Story 1, it is the minimum viable feature: a developer can state a change and get correct artifacts out.

**Independent Test**: Can be fully tested by applying a delta to a fixture spec and comparing the resulting `spec.md`/`tasks.md` byte-for-byte against expected output, then re-parsing them with the existing parsers to confirm they are still valid Spec Kit artifacts.

**Acceptance Scenarios**:

1. **Given** a validated delta with one ADDED, one MODIFIED, one REMOVED, and one RENAMED requirement, **When** it is applied, **Then** the spec's requirement set reflects all four changes and no other requirement's text changed.
1a. **Given** a delta naming the same requirement through two operations, **When** it is applied, **Then** the outcome follows the fixed RENAMED → REMOVED → MODIFIED → ADDED order, not the order the entries appear in the document.
2. **Given** an applied delta, **When** the resulting artifacts are parsed by the existing ingestion parsers, **Then** they parse successfully with no new format required.
3. **Given** a delta that has already been applied, **When** it is applied again, **Then** the operation is a reported no-op and the artifacts are unchanged.
4. **Given** an apply that fails partway (an unwritable file, an impact that stops it), **When** it exits, **Then** the artifacts are left in their pre-apply state, not a partial state.

---

### User Story 3 - Delta consequences flow into beads deterministically (Priority: P1)

After applying a delta, the developer re-runs ingestion. New tasks become new beads under the epic that already exists — no duplicate epic. Withdrawn tasks have their open, unstarted beads closed. Nothing that a human or an agent has already started is touched.

**Why this priority**: This is the actual problem statement — "have it flow deterministically into new work". Stories 1 and 2 produce correct artifacts; this story is what makes them change the work.

**Independent Test**: Can be fully tested by applying a delta that adds two task lines and withdraws one, running ingestion, and verifying exactly two new beads exist under the existing epic and exactly one previously-open bead is closed, with zero model calls.

**Acceptance Scenarios**:

1. **Given** an applied delta adding tasks, **When** ingestion runs, **Then** the new tasks become beads under the existing epic and no second epic is created.
2. **Given** an applied delta withdrawing tasks whose beads are open and unstarted, **When** ingestion runs, **Then** exactly those beads are closed with a reason citing the delta, and no other bead changes state.
3. **Given** an ingestion of delta consequences, **When** it completes, **Then** zero model calls were made.
4. **Given** a preview run, **When** it completes, **Then** every bead consequence is reported and zero writes occurred.

---

### User Story 4 - In-flight work stops the apply rather than being mutated (Priority: P1)

A developer applies a delta that withdraws or changes a task whose bead is already closed, or currently being worked. The apply does not silently rewrite and move on. It reports each such collision — which task, which bead, what state it is in — and stops without archiving, leaving the developer to decide.

**Why this priority**: This is the safety property that makes the whole layer trustworthy. A delta layer that can silently invalidate completed work is worse than editing `spec.md` by hand, because it looks authoritative while doing damage.

**Independent Test**: Can be fully tested by constructing a spec with one closed bead and one in-progress bead, applying a delta that withdraws both of their tasks, and verifying the command reports both impacts, exits non-zero, and left the artifacts and beads untouched.

**Acceptance Scenarios**:

1. **Given** a delta withdrawing a task whose bead is closed, **When** it is applied, **Then** an impact is reported naming the task, the bead, and its state, and the command exits non-zero.
2. **Given** a delta withdrawing a task whose bead is in progress, **When** it is applied, **Then** the same reporting and refusal occurs.
3. **Given** a reported impact, **When** the developer explicitly acknowledges it and re-runs, **Then** the apply proceeds and the acknowledgement is recorded in the archive.
4. **Given** any refused apply, **When** it exits, **Then** no artifact was rewritten and no bead changed state.

---

### User Story 5 - Applied deltas are preserved as provenance (Priority: P2)

Months later, someone asks "why does this requirement say X when the original spec said Y?". The answer lives in the spec's own directory: an archive of every delta ever applied, in order, each recording what changed, when it was applied, and any impacts the human acknowledged.

**Why this priority**: Genuinely valuable — it is the difference between a spec directory that records intent over time and one that records only its current state — but the feature is already correct and useful without it. Git history is a lossy fallback that exists today.

**Independent Test**: Can be fully tested by applying two deltas in sequence and verifying the archive contains both, in application order, each with its recorded application time and change set.

**Acceptance Scenarios**:

1. **Given** an applied delta, **When** the apply completes, **Then** the delta is moved to the archive with its application record attached, and is no longer listed as pending.
2. **Given** several applied deltas, **When** the spec's change history is listed, **Then** they appear in application order with their change counts.
3. **Given** an archived delta, **When** anyone reads it, **Then** it states what changed, when it was applied, and which impacts were acknowledged — without reference to git history.

---

### Edge Cases

- **Delta against a spec that has never been ingested**: there are no beads to collide with. The apply proceeds normally and ingestion behaves as a first run.
- **Two pending deltas against the same spec**: applying them must be ordered and deterministic. Applying one must re-validate the other against the new state rather than assuming it still applies.
- **A delta that removes every requirement**: permitted but must be reported prominently — this is spec withdrawal, and the resulting artifact set must still be structurally valid.
- **MODIFIED entry whose "before" text does not match the spec's current text**: a stale delta. It must fail validation naming the mismatch, not apply against the wrong baseline.
- **A requirement change with no task consequence**: the overwhelmingly common case, since most tasks cite no requirement at all. The delta rewrites `spec.md` and touches no bead. This must be an ordinary, quiet outcome — not a warning.
- **A withdrawn task whose bead lost its recorded identity**: possible today, because ingestion writes bead identity one key at a time and a process death between creating a bead and stamping it leaves the bead unstamped. Such a bead is invisible to withdrawal detection; FR-020 requires reporting it rather than closing or ignoring it silently.
- **Applying a delta to a spec whose `tasks.md` a human has edited by hand since ingestion**: the apply must not clobber the hand edits it does not own; only the regions the delta touches are rewritten.
- **A delta document that is syntactically valid but semantically empty** (zero change entries): rejected at validation, since applying it can only be a no-op that pollutes the archive.
- **Interruption mid-apply**: leaves the pre-apply state, per Story 2's atomicity scenario.

## Requirements *(mandatory)*

### Functional Requirements

#### The delta document

- **FR-001**: The system MUST define a delta document format that expresses each change as one of exactly four kinds: ADDED, MODIFIED, REMOVED, or RENAMED, each naming the requirement it concerns.
- **FR-002**: A MODIFIED entry MUST carry the **entire** requirement block in both its before and after form — never a partial excerpt or a line diff. Partial content is the field's known failure mode: what the entry omits is silently dropped from the requirement at apply time, so the delta looks like a small change and lands as a large deletion.
- **FR-002b**: A requirement block MUST be defined as: the requirement's own line, plus every following continuation line and sub-bullet indented beneath it, up to the next requirement line or the next section heading of any level `##` or `###`. Specifically: a `####` heading inside the requirements section is an in-block **grouping marker and MUST NOT terminate a block**, and a **blank line MUST NOT terminate a block** — both forms occur in this repository's existing specs, and treating either as a terminator silently truncates requirements that are currently correct.
- **FR-002a**: A RENAMED entry MUST carry the old and new identifiers, and MUST preserve the requirement's existing coverage — its beads are re-pointed, never closed and recreated.
- **FR-003**: The format MUST be deterministically parseable with zero model calls, and parsing MUST fail loudly on ambiguity rather than guessing.
- **FR-004**: Delta documents MUST live inside the feature directory they target, in a location upstream Spec Kit neither reads nor writes, so a repository without deltas is byte-identical to a vanilla Spec Kit repository.
- **FR-004a**: Applying MUST process operations in a fixed order — RENAMED, then REMOVED, then MODIFIED, then ADDED — so that a delta touching the same requirement through more than one operation has one defined outcome rather than an order-of-appearance outcome.
- **FR-005**: The system MUST validate a delta against its target spec, rejecting: a MODIFIED or REMOVED entry naming a requirement the spec does not define; an ADDED entry whose identifier the spec already defines; a MODIFIED entry whose before-text does not match the spec's current text; a delta with zero change entries; and a requirement named by two conflicting operations (MODIFIED and REMOVED, say).
- **FR-005a**: Validation MUST additionally apply a **content-loss guard** to every MODIFIED entry: reject when the after-block drops sub-bullets the before-block carries, or shrinks past a proportional threshold, unless the delta marks the reduction as intentional. This is the guard that separates a delta layer safe to adopt from one that quietly erodes specs — an author working from an older copy of a requirement loses everything added since, and nothing about the resulting document looks wrong. **Revised from an acceptance-criteria guard after measurement**: requirements in this repository carry no per-requirement acceptance criteria to compare (see Assumptions), so the guard is defined over block content, which does exist.

#### Applying

- **FR-006**: Applying a delta MUST rewrite the target spec's requirement set to its post-delta state, leaving every requirement the delta does not name byte-identical.
- **FR-007**: Applying a delta MUST apply the delta's **task entries** to `tasks.md` — added task lines appear, withdrawn task ids are removed — leaving every task line the delta does not name byte-identical.
- **FR-007a**: The system MUST NOT attempt to derive which tasks a requirement covers. A delta that changes work states its task consequences explicitly; the tool applies what the delta says and never infers a requirement-to-task mapping.
- **FR-008**: The artifacts an apply produces MUST remain ordinary Spec Kit artifacts, parseable by the existing ingestion parsers with no new format and no new parser mode.
- **FR-009**: Applying MUST be atomic with respect to the artifact set: a failure at any point leaves the pre-apply state, never a partial rewrite.
- **FR-010**: Applying an already-applied delta MUST be a reported no-op.
- **FR-011**: Applying MUST NOT write beads. Bead consequences MUST come from a separate, explicit ingestion run.
- **FR-012**: Applying MUST offer a preview mode that reports every artifact change and every impact with zero writes.

#### Impacts on existing work

- **FR-013**: Before rewriting anything, the apply MUST determine, for every **task** the delta withdraws or changes, the state of that task's bead — resolved by the task identity already recorded on the bead at ingestion.
- **FR-014**: The apply MUST refuse to complete — reporting every impact and exiting non-zero, having written nothing — when a withdrawn or changed task's bead is in any state other than open-and-unstarted.
- **FR-015**: The system MUST provide an explicit acknowledgement path by which a human accepts reported impacts and re-runs the apply, and MUST record the acknowledgement in the archive.
- **FR-016**: The system MUST NOT close, reopen, or edit any bead that a human or agent has started or completed, on any path.

#### Ingestion of consequences

- **FR-017**: Ingestion after an applied delta MUST add new tasks as beads under the existing epic, creating no second epic.
- **FR-018**: Ingestion MUST close the open, unstarted beads of withdrawn tasks — identified exactly as the task ids recorded on existing beads that no longer appear in the reparsed task list — with a recorded reason citing the delta that withdrew them.
- **FR-019**: Ingestion of delta consequences MUST make zero model calls.
- **FR-020**: Ingestion MUST leave untouched, and report, any existing bead carrying no recorded task identity — a bead whose identity write did not complete is invisible to withdrawal detection, and closing or ignoring it silently are both wrong.

#### Archive

- **FR-021**: An applied delta MUST be preserved in an archive within the feature directory, recording what changed, when it was applied, and which impacts were acknowledged.
- **FR-022**: The archive MUST be readable as the spec's history of intentional change without reference to version-control history.
- **FR-023**: Archived deltas MUST be ordered by application, and a pending delta MUST be distinguishable from an applied one by location alone.

#### Compatibility

- **FR-024**: Every existing command MUST behave identically on a repository with no delta documents.
- **FR-025**: The delta layer MUST NOT change the format of `spec.md` or `tasks.md` as produced by upstream Spec Kit, and MUST NOT require upstream Spec Kit to know the layer exists.

### Key Entities

- **Delta document**: a proposed change set against one spec — an ordered list of change entries, each ADDED, MODIFIED, REMOVED, or RENAMED, plus enough identity to name its target spec unambiguously.
- **Requirement entry**: one requirement-level change to `spec.md` — its kind, the requirement identifier, and the text involved (after-block for ADDED, complete before and after blocks for MODIFIED, before-block for REMOVED, old and new identifiers for RENAMED).
- **Task entry**: one task-level change to `tasks.md` — an added task line, or a withdrawn task id. Stated by the delta's author, never derived from a requirement entry.
- **Impact**: a collision between a task entry and existing work — the task, its bead, and that bead's state. Produced by the apply step, resolved by a human.
- **Application record**: what an apply produced — the delta applied, when, the resulting change counts, and any acknowledged impacts. Attached to the delta in the archive.
- **Task identity**: the Spec Kit task id recorded on each bead at ingestion. This is the *only* join between artifacts and beads the delta layer uses, and it is exact — task ids are structurally required, uniqueness-enforced at parse time, and durably stored.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can express any requirement-level change — addition, modification, or removal — as a delta document and have it validated against the target spec, without editing `spec.md` by hand.
- **SC-002**: Applying a delta and re-ingesting produces exactly the bead changes the delta implies: new beads for added tasks, closed beads for withdrawn ones, nothing else — verifiable by comparing complete bead-state snapshots before and after.
- **SC-003**: Parsing, validating, applying, and ingesting a delta together make zero model calls, verifiable by asserting no agent invocation occurred across the whole sequence.
- **SC-004**: On a repository containing no delta documents, every existing command produces byte-identical output to its behavior before this feature — verifiable by running the existing test suite unchanged.
- **SC-005**: No bead that a human or agent has started or completed is ever modified by this feature, on any path including every failure path — verifiable by comparing bead states across every apply scenario including the refusal ones.
- **SC-006**: A reader can reconstruct a spec's complete history of intentional change from its archive alone, without consulting version-control history.
- **SC-007**: Artifacts produced by an apply parse successfully with the existing ingestion parsers in 100% of cases, with no parser change.
- **SC-008**: No apply ever reduces a requirement block's content without the author having said so explicitly — verifiable by applying a delta whose MODIFIED after-block drops a sub-bullet the current spec carries, and asserting the apply refuses rather than completes.
- **SC-009**: A renamed requirement leaves every bead untouched — verifiable by comparing complete bead-state snapshots across a RENAMED apply. A rename changes an identifier in `spec.md`; it has no task consequence unless the delta states one.
- **SC-010**: The requirement-block parser round-trips every `spec.md` in this repository — parse then re-render reproduces the file byte-identically for all of them. This is the proof that the block definition in FR-002b matches the corpus rather than an idealized version of it.

## Assumptions

- Requirement identifiers in `spec.md` serve as the delta's anchors. Measured across this repository's 54 specs: 1,139 requirement lines, **all** matching one grammar, ids unique within each spec, no gaps, always three-digit-padded, and a letter suffix (`FR-019c`) on 34 of them. A parser must accept the suffix form; an ordering must not assume ids sort numerically.
- **Requirement-to-task coverage is NOT derivable and this design does not attempt it.** Measured: of 2,878 task lines across the corpus, 184 cite a requirement id — **6.4%** — and 24 of 54 feature directories cite none at all. Where citations exist they are freeform prose in three inconsistent shapes. An earlier draft of this spec assumed coverage was derivable; it is not, and any design resting on it would work on three specs and fail silently on the rest. The join to beads is therefore made at **task** identity, which is structural, uniqueness-enforced, and recorded on every bead at ingestion.
- **Requirements carry no per-requirement acceptance criteria in this corpus.** Measured: 247 acceptance-scenario blocks across 54 specs, **all 247** under a user-story heading, **none** inside the requirements section — and the upstream template defines them only under user stories. Requirements and user stories are not cross-referenced, so which scenarios belong to a given requirement cannot be derived mechanically either. FR-005a is defined over block content for this reason.
- The delta layer operates at requirement granularity, not at arbitrary-prose granularity. Changing a spec's narrative sections remains an ordinary edit; only requirements have deltas.
- Deltas are authored by a human or an upstream tool. Generating them is explicitly out of scope, and nothing in this feature's design should assume a generator will or will not exist.
- Applying rewrites `spec.md` and `tasks.md` only in the regions the delta names, preserving hand edits elsewhere. This is what makes the layer safe to adopt in a repository whose specs and task lists have been curated.
- Bead state is read through the existing bead client and the existing epic/task relationships established by ingestion. No new bead metadata is introduced.
- The existing ingestion layer parses task lists but **not** requirements — the spec parser today returns only title, success criteria, and user-story scenarios. A requirement-block parser is new work, and FR-002b plus SC-010 exist to keep it honest against the real corpus.
- One delta targets exactly one spec. Cross-spec changes are expressed as one delta per spec.
- The delta document's vocabulary (ADDED / MODIFIED / REMOVED / RENAMED, whole-block replacement, the scenario-loss guard, the fixed operation order) is adopted from OpenSpec rather than invented. Two tools in this space converging on one delta notation is worth more than a marginally better bespoke one, and it leaves a conversion path open in either direction — which today does not exist for anyone.
