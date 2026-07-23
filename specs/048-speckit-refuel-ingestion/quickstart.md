# Quickstart: Validating Spec Kit Ingestion

**Feature**: 048-speckit-refuel-ingestion

Runnable scenarios proving the feature end-to-end. Contracts: [cli-refuel-speckit.md](contracts/cli-refuel-speckit.md), [tasks-md-grammar.md](contracts/tasks-md-grammar.md), [bead-encoding.md](contracts/bead-encoding.md).

## Prerequisites

- `bd` on PATH and `.beads/` initialized in the target repo (`maverick init` / `bd init`)
- A Spec Kit feature dir `specs/NNN-name/` with `spec.md` + `tasks.md` (fixture generators: `spec_dir_with_tasks` / `spec_dir_with_deps` in `tests/unit/beads/conftest.py`)
- No provider auth needed except Scenario 6 (`--enrich`)

## Scenario 1 — Dry-run preview (safe first contact)

```bash
maverick refuel 048 --speckit --dry-run
```

Expect: mode announcement, per-task table (ID, title, phase, `[P]`, blockers), skipped-completed list, `Dry run — no beads created.`, exit 0. Verify zero writes: `bd query "type=epic AND status=open" --json` unchanged; no new `.maverick/runs/` entry.

## Scenario 2 — Fresh ingestion + fly handoff

```bash
maverick refuel 048 --speckit
bd show <epic-id> --json          # labels: ["speckit"], state.speckit_feature=<dir name>
bd list --parent <epic-id> --flat --json   # one task bead per unchecked task, titles "T###: …"
bd ready --parent <epic-id> --limit 10 --json  # ONLY phase-1 sources are ready
maverick fly --epic <epic-id> --max-beads 1    # implementer receives full work-unit markdown
```

Expect: summary (epic ID, N created, M skipped-completed, edge count), `Next: maverick fly --epic <id>` hint, exit 0. SC-002 check: created count + skipped count == total tasks in tasks.md; every ID present exactly once. SC-003 check: `bd ready` never surfaces a task whose phase predecessors or explicit deps are open.

## Scenario 3 — Epic chaining

With an open epic from a previous refuel (classic or speckit), run Scenario 2. Expect the new epic blocked by the previous open-epic tail: new tasks absent from `bd ready` until the prior epic closes.

## Scenario 4 — Delta re-run (converge-style growth)

```bash
maverick refuel 048 --speckit          # ingests T001–T0NN
# append "- [ ] T0XX [P] [US2] New task in src/new.py" to a later phase of tasks.md
maverick refuel 048 --speckit          # delta
maverick refuel 048 --speckit          # no-op
```

Expect: run 2 creates exactly one bead under the *same* epic (no second epic; `skipped_existing` lists prior IDs); run 3 exits 0 with `No new tasks to ingest…`. `bd query "type=epic AND status=open"` shows one epic for the feature throughout.

## Scenario 5 — Failure modes (each exits 1, no partial state)

| Setup | Expected error |
| --- | --- |
| Duplicate `T005` line in tasks.md | E06: both line numbers; zero beads created |
| `(depends on T999)` where T999 undefined | E06: referencing task + missing ID + line |
| Corrupt a task line (e.g. `- [ ] do stuff` inside a phase) | E05: file, line, expected pattern, suggested fix |
| Set `.specify/init-options.json` `speckit_version` to `"0.99.0"` | E04: `unsupported template version 0.99.0, supported: >=0.14,<0.15` |
| Name matches both a classic plan and a specs dir | E01: disambiguation instructions |
| All tasks checked `[x]` (first run) | E07: nothing to ingest; no epic created |

After each: verify no epic/tasks were created (validation precedes writes — FR-015).

## Scenario 6 — Optional enrichment

```bash
maverick refuel 048 --speckit --enrich          # requires provider auth for the "generate" tier
```

Expect: identical bead set/graph to Scenario 2; each new task bead's `## Verification` gains model-supplied commands. Then break provider auth and re-run (fresh feature): warning about enrichment degradation, ingestion still succeeds, exit 0.

## Scenario 7 — Zero-model guarantee

Run Scenarios 1–5 with no provider credentials configured. All behave identically (FR-010/SC-001). Any model-call attempt on the default path is a bug.

## Automated validation

```bash
make test-fast            # unit: parser grammar tables, build/delta logic, CLI dispatch
make test                 # + workflow tests with stubbed BeadClient runner
make ci                   # pre-push gate
```

Key suites (added by this feature): `tests/unit/speckit/`, `tests/unit/workflows/refuel_speckit/`, `tests/unit/cli/commands/refuel/`.
