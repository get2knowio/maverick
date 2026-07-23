# Feature Specification: Spec Kit Ingestion Mode for Refuel

**Feature Branch**: `048-speckit-refuel-ingestion`
**Created**: 2026-07-23
**Status**: Draft
**Input**: User description: "Add a Spec Kit ingestion mode to refuel. Given a feature directory produced by GitHub Spec Kit (specs/NNN-name/ containing spec.md, plan.md, tasks.md, with templates vendored under .specify/), maverick refuel <feature> --speckit (or auto-detection of the directory shape) creates one epic bead for the spec and one task bead per task in tasks.md — preserving task IDs, phase grouping, [P] parallelism markers, file scope, and dependency ordering. New epics chain behind existing open epics exactly as refuel does today. Per-bead acceptance criteria come from the task text plus spec.md success criteria; an optional slim enrichment pass may attach verification commands, but there is no LLM decomposition — the parser replaces it for speckit-managed repos. Parsing targets the template version vendored in the target repo and fails with actionable errors when the format diverges. Dry-run behaves like existing refuel dry-run."

## Clarifications

### Session 2026-07-23

- Q: How should re-running ingestion behave for a feature that already has an open ingestion-created epic? → A: Delta ingestion — add work items only for tasks not previously ingested (e.g., converge-added ones), skip already-ingested and completed tasks; no duplicate epic.
- Q: When a task has no explicit dependency note, how are cross-phase dependencies derived? → A: Phase barrier + explicit notes — a task cannot start until the previous phase completes, plus any explicit "depends on Txxx" edges; within a phase, [P] tasks are mutually independent and unmarked tasks are serialized.
- Q: Which spec content becomes acceptance criteria on which work item? → A: Story-scoped — a task with a [USn] label gets task text + that story's acceptance scenarios; unlabeled tasks get task text only; the epic carries the feature-wide success criteria.
- Q: What does "targeting the vendored template version" mean operationally? → A: Fixed supported grammar + compatibility check — ingestion supports a declared range of Spec Kit template versions; the repo's vendored version is verified upfront and unsupported versions fail with a clear "unsupported version X, supported: Y" error.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ingest a Spec Kit feature into work items (Priority: P1)

A developer manages their repository with GitHub Spec Kit. They have already produced a feature directory (`specs/NNN-name/`) containing a specification, a plan, and a dependency-ordered task list. Instead of asking an AI model to re-decompose work that Spec Kit has already decomposed, they run `maverick refuel <feature> --speckit` and get one epic work item for the feature plus one task work item per entry in the task list — with the original task identifiers, phase grouping, parallelism markers, file scope, and dependency ordering carried over faithfully. The implementation workflow (`maverick fly`) can then pick up the work items exactly as it does for work items produced by today's refuel.

**Why this priority**: This is the core value of the feature — a deterministic, zero-model-cost path from a Spec Kit task list to executable work items. Without it, nothing else in this feature matters.

**Independent Test**: In a repository containing a well-formed Spec Kit feature directory, run the ingestion command and verify that the created work items match the task list one-for-one (identifiers, ordering, dependencies, phases) and that the epic chains behind any pre-existing open epic.

**Acceptance Scenarios**:

1. **Given** a repository with a well-formed Spec Kit feature directory containing a spec, a plan, and a task list with 20 tasks across 4 phases, **When** the user runs `maverick refuel <feature> --speckit`, **Then** exactly one epic work item and 20 task work items are created, each task work item carrying its original task identifier, phase, story label (if any), parallelism marker, and file scope.
2. **Given** the same feature directory, **When** ingestion completes, **Then** dependency ordering is preserved: no task can become ready before its preceding phase fully completes, explicit per-task dependency notes add further blocking edges, tasks marked parallel-eligible within a phase have no dependencies on one another, and unmarked tasks within a phase are ordered sequentially.
3. **Given** an existing open epic from a previous refuel run, **When** a Spec Kit ingestion creates a new epic, **Then** the new epic is blocked by the most recent existing open epic, identical to today's refuel chaining behavior.
4. **Given** a task list where some tasks are already checked off as complete, **When** ingestion runs, **Then** completed tasks are not turned into open work items and are reported as skipped.
5. **Given** each created task work item, **When** its acceptance criteria are inspected, **Then** they include the task's own text (including file scope), plus — for tasks labeled with a user story — that story's acceptance scenarios from the specification, so an implementer can verify completion without reading the Spec Kit artifacts. The epic work item carries the feature-wide success criteria.
6. **Given** a completed ingestion, **When** the user inspects usage or cost records, **Then** no AI model was invoked for decomposition.

---

### User Story 2 - Auto-detection of Spec Kit feature directories (Priority: P2)

A developer in a Spec Kit-managed repository runs `maverick refuel <feature>` without the explicit mode flag. Maverick recognizes that the named feature resolves to a Spec Kit-shaped directory (a `specs/NNN-name/` directory with a spec and task list, with Spec Kit templates vendored in the repository) and automatically uses the ingestion path instead of the AI-decomposition path.

**Why this priority**: Removes a footgun — users shouldn't need to remember a flag when the repository shape already makes the intent unambiguous. But the explicit flag from Story 1 already delivers the full value, so this is a convenience layer.

**Independent Test**: Run refuel without the flag against a Spec Kit feature directory and verify ingestion mode is chosen and announced; run it against a classic flight-plan name and verify existing behavior is untouched.

**Acceptance Scenarios**:

1. **Given** a repository with vendored Spec Kit templates and a feature directory containing a spec and task list, **When** the user runs `maverick refuel <feature>` without the mode flag, **Then** the ingestion path is selected automatically and the chosen mode is clearly announced in the output.
2. **Given** a feature name that resolves to a classic flight plan (`.maverick/plans/<name>/flight-plan.md`) and not to a Spec Kit directory, **When** the user runs refuel, **Then** the existing decomposition behavior runs unchanged.
3. **Given** a name that matches both a classic flight plan and a Spec Kit feature directory, **When** the user runs refuel without the flag, **Then** the command stops and asks the user to disambiguate (e.g., by passing the explicit flag) rather than silently picking one.
4. **Given** the explicit `--speckit` flag and a feature that does not resolve to a Spec Kit-shaped directory, **When** the user runs refuel, **Then** the command fails with an error stating what was looked for and where.

---

### User Story 3 - Preview ingestion without creating anything (Priority: P2)

Before committing to an ingestion, a developer runs the command in dry-run mode to see exactly which epic and task work items would be created — titles, identifiers, phases, dependency edges, and skipped completed tasks — without any work items being created or repository state changing.

**Why this priority**: Ingestion creates many linked work items at once; a preview builds trust and catches parsing surprises cheaply. It is not required for the core path to function.

**Independent Test**: Run dry-run against a valid feature directory, verify the printed plan matches the task list, and verify the work-item store is untouched afterward.

**Acceptance Scenarios**:

1. **Given** a valid Spec Kit feature directory, **When** the user runs the ingestion with dry-run, **Then** the full set of would-be work items (epic + tasks, with identifiers, phases, dependencies, and skipped tasks) is displayed and zero work items are created.
2. **Given** a malformed task list, **When** the user runs dry-run, **Then** the same actionable parse error is reported as a real run would produce — dry-run validates, not just previews.

---

### User Story 4 - Optional enrichment with verification commands (Priority: P3)

A developer opts into a slim enrichment pass at ingestion time. For each task work item, the enrichment attaches concrete verification commands (e.g., which test or check command proves the task done) derived from the repository's conventions. Enrichment never adds, removes, splits, or reorders tasks — the task list remains the single source of truth for decomposition.

**Why this priority**: Improves downstream implementation quality but the ingested work items are already actionable without it. Strictly additive.

**Independent Test**: Run ingestion with enrichment enabled and verify each work item gains verification commands while the set of work items, their identifiers, and their dependency graph are identical to an un-enriched run.

**Acceptance Scenarios**:

1. **Given** enrichment is enabled, **When** ingestion completes, **Then** the set of work items and their dependency graph are byte-for-byte identical to a non-enriched run except for the added verification metadata.
2. **Given** enrichment fails or is unavailable, **When** ingestion runs, **Then** the ingestion still completes successfully without enrichment and the degradation is reported as a warning, not an error.
3. **Given** enrichment is not requested, **When** ingestion runs, **Then** no AI model is invoked at any point.

---

### Edge Cases

- **Empty or all-complete task list**: the feature directory parses but contains zero open tasks — the command fails with a message explaining there is nothing to ingest (no orphan epic is created).
- **Missing plan file**: `plan.md` is absent but spec and tasks are present — ingestion proceeds (the plan is context, not structure) and notes the absence.
- **Duplicate task identifiers** in the task list — ingestion fails with an error naming the duplicated identifier and its line numbers.
- **Dependency references to unknown task identifiers** — ingestion fails naming the referencing task, the missing identifier, and the line.
- **Unsupported template version**: the repository's vendored Spec Kit version falls outside the supported range — ingestion fails upfront with "unsupported template version X, supported: Y" before reading any artifacts.
- **Template divergence**: the artifacts are from a supported version but don't match the expected structure (e.g., hand-edited section headings, unrecognized task-line format) — ingestion fails with an error that names the file, the line, what was expected, and what to fix; no partial set of work items is left behind.
- **Re-running ingestion for a feature that already has an open epic** — the run performs a delta ingestion: only tasks not previously ingested become new work items under the existing epic; if there are none, the run is a reported no-op. No duplicate epic or duplicate task work items are ever created.
- **Interrupted ingestion** (failure partway through creating work items) — the run reports which items were created; a subsequent run's delta ingestion picks up the remaining tasks under the same epic rather than starting over.
- **Feature reference ambiguity**: the argument matches multiple `specs/` directories (e.g., by partial name) — the command lists the candidates and asks the user to be precise.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The refuel command MUST accept a feature reference that resolves to a Spec Kit feature directory (`specs/NNN-name/`), matching by full directory name, by number prefix, or by exact name suffix.
- **FR-002**: The system MUST support an explicit Spec Kit mode flag on refuel; when set, refuel MUST use the ingestion path and MUST fail with an actionable error if the resolved directory is not Spec Kit-shaped.
- **FR-003**: When no mode flag is given, the system MUST auto-detect Spec Kit shape (feature directory with a spec file and task-list file, plus Spec Kit templates vendored in the repository) and select the ingestion path, announcing the selected mode. If the feature reference resolves to both a classic flight plan and a Spec Kit directory, the system MUST stop and ask the user to disambiguate.
- **FR-004**: Ingestion MUST create exactly one epic work item per run, derived from the feature's specification (title, summary, and success criteria), and MUST link it to the source feature directory for later traceability.
- **FR-005**: Ingestion MUST create exactly one task work item per open (unchecked) task in the task list, and MUST skip tasks already checked complete, reporting the skipped count.
- **FR-006**: Each task work item MUST preserve, from its source task line: the task identifier (e.g., T001), the phase it belongs to, its story label if present (e.g., US1), its parallelism marker if present ([P]), and the file paths named in the task text.
- **FR-007**: Ingestion MUST reproduce the task list's dependency ordering as work-item dependencies using a phase barrier plus explicit notes: no task may become ready until every task in the preceding phase is complete (the barrier wired efficiently, without a full cross-product of edges); explicit per-task dependency annotations (e.g., "depends on T012, T013") add further edges; within a phase, parallel-marked tasks carry no dependencies on one another and unmarked tasks are serialized in listed order. The implementation workflow's ready-work ordering over the ingested items MUST match a valid execution order of the task list.
- **FR-008**: Each task work item's acceptance criteria MUST include the full task text (including file scope); tasks carrying a story label MUST additionally include that user story's acceptance scenarios from the specification, so completion is verifiable from the work item alone. Unlabeled tasks (setup, foundational, polish) carry task text only. The feature-wide success criteria live on the epic work item, not on individual tasks.
- **FR-009**: A newly created epic MUST chain behind the most recent existing open epic exactly as today's refuel does (new epic blocked by the tail of the open-epic chain).
- **FR-010**: The ingestion path MUST NOT invoke any AI model for decomposition under any circumstances; parsing is fully deterministic.
- **FR-011**: An optional, explicitly requested enrichment pass MAY attach verification commands to task work items. Enrichment MUST NOT add, remove, split, merge, or reorder work items or dependencies, and enrichment failure MUST degrade to a warning, never fail the ingestion.
- **FR-012**: Ingestion MUST support a declared range of Spec Kit template versions (initially the 0.14.x shape) via a fixed parsing grammar. Before parsing, it MUST check the version vendored in the target repository against that range and fail upfront with "unsupported template version X, supported: Y" when outside it. When artifacts within a supported version diverge structurally from the grammar, ingestion MUST fail before creating any work items, with an error naming the file, line, the expected structure, and a suggested fix.
- **FR-013**: The command MUST offer a dry-run mode that performs full resolution, parsing, and validation and displays the complete set of would-be work items (epic, tasks, dependencies, skipped tasks) without creating any work items or modifying repository state.
- **FR-014**: If the resolved feature already has an open epic previously created by ingestion, the command MUST NOT create a second epic. Instead it MUST perform a delta ingestion: create work items only for open tasks not previously ingested under that epic (e.g., tasks appended to the task list after the first run), wire their dependencies into the existing graph, and report already-ingested and completed tasks as skipped. A delta run that finds no new tasks MUST succeed as a no-op and say so.
- **FR-015**: Ingestion failures after partial work-item creation MUST report exactly which items were created; validation failures (parse errors, unknown references, duplicates) MUST be detected before any work item is created.
- **FR-016**: Ingestion MUST record run metadata (including the created epic identifier) the same way today's refuel does, so follow-on commands (e.g., the "next: fly --epic <id>" hint and brief/status views) work unchanged.

### Key Entities

- **Spec Kit feature directory**: A directory `specs/NNN-name/` produced by Spec Kit, containing a specification (`spec.md`, with success criteria and user stories), an optional plan (`plan.md`), and a task list (`tasks.md`).
- **Task entry**: One line of the task list — identifier (T-number), completion checkbox, optional parallelism marker `[P]`, optional story label `[USn]`, description text including file paths, and membership in a phase.
- **Phase**: A named, ordered grouping of task entries (e.g., Setup, Foundational, per-story phases, Polish) with declared cross-phase dependency rules.
- **Epic work item**: The single parent bead created per ingestion, carrying the feature's title, summary, success criteria, and a link to the source directory; chained behind existing open epics.
- **Task work item**: A child bead created from one open task entry, carrying preserved task metadata, acceptance criteria, and dependency edges; consumable by the implementation workflow unchanged.
- **Dependency edge**: A blocking relationship between two work items derived from the phase barrier (a task starts only after the preceding phase completes), intra-phase sequencing of unmarked tasks, and any explicit per-task dependency notes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a well-formed feature directory, ingestion completes in under 30 seconds and invokes zero AI models (zero token cost) — compared to today's multi-minute, model-driven decomposition.
- **SC-002**: 100% of open tasks in the task list appear as work items with their original identifiers; zero tasks are dropped, duplicated, or renamed across a corpus of representative Spec Kit feature directories.
- **SC-003**: For every ingested feature, the order in which the implementation workflow surfaces ready work items is a valid execution order of the source task list (no task surfaces before its declared prerequisites) in 100% of cases.
- **SC-004**: 100% of malformed-input failures identify the offending file and line and state what was expected; zero malformed runs leave partially created work items behind.
- **SC-005**: Dry-run creates zero work items and zero repository changes in 100% of runs, while its preview matches the subsequent real run's output exactly for an unchanged input.
- **SC-006**: A user who has never read the Spec Kit artifacts can determine, from a single task work item alone, what to do and how to verify completion (task text, file scope, and — for story-labeled tasks — the story's acceptance scenarios are all present on the item).

## Assumptions

- **Refuel has no dry-run today**: the current refuel command exposes `--list-steps` but no `--dry-run`. "Behaves like existing refuel dry-run" is interpreted as: introduce a dry-run consistent with Maverick's existing dry-run conventions (e.g., `land --dry-run`) — full validation and a complete preview, zero mutations.
- **Completed tasks are skipped**: tasks checked `[x]` in the task list are treated as already done and are not ingested as open work items. They are reported, not silently ignored.
- **Plan file is optional**: `plan.md` provides context only; its absence does not block ingestion. The spec file and task-list file are both required.
- **Delta re-runs**: re-ingesting a feature with an existing open ingestion-created epic adds only not-yet-ingested tasks under that epic (task lists legitimately grow, e.g., via convergence assessments that append tasks). Task identity for delta detection is the task identifier within the feature's epic.
- **Supported template baseline**: ingestion ships a fixed grammar for a declared range of Spec Kit template versions (initially the 0.14.x shape: `Phase N:` headings, `- [ ] T### [P?] [US?] description` task lines, a Dependencies & Execution Order section). The version vendored in the target repository (e.g., recorded by Spec Kit's init metadata) is checked upfront; unsupported versions fail fast per FR-012 rather than being parsed adaptively.
- **Explicit dependency notes**: free-text per-task dependency annotations (e.g., "depends on T012, T013") are honored as additional dependency edges when present and parseable; phase ordering and intra-phase sequencing remain the structural baseline.
- **Enrichment scope**: the optional enrichment pass is the only model-touching step, is off by default, and attaches only verification metadata (commands/checks), never structural changes.
