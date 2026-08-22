# Contract: `maverick critique` (command surface + human output)

**Feature**: 058-standalone-code-review
**Status**: Normative

---

## Synopsis

```
maverick critique [--base REV] [--epic ID] [PATH...]
                  [--fail-on {critical,major,minor}] [--json]
```

## Scope selection (FR-002, FR-003, FR-004)

Exactly one scope per invocation:

| Invocation | Scope | Resolution |
| --- | --- | --- |
| `critique` | `diff` | working copy vs `main` |
| `critique --base <rev>` | `diff` | working copy vs `<rev>` |
| `critique --epic <id>` | `epic` | commits whose subject carries `bead(<id>):` for a bead under `<id>` |
| `critique <path>...` | `paths` | the named paths as they currently stand |

Combining `--epic` with `--base` or with positional paths, or `--base` with
positional paths, is a `validation` failure naming both selections. There is
no precedence rule — an ambiguous invocation is rejected, never guessed.

`--base` is accepted with the `diff` scope only. Its default is `main`,
matching `maverick land --base` exactly (research R6).

## Options

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `--base` | `str` | `main` | Base revision for the `diff` scope. |
| `--epic` | `str` | — | Epic id for the `epic` scope. |
| `--fail-on` | choice | off | Exit non-zero when a finding at or above this severity is present (FR-006). |
| `--json` | flag | off | Emit one JSON envelope on stdout; see `cli-critique-json.md`. |

`PATH...` are repo-relative or absolute paths; absolute paths outside the
repository are a `validation` failure.

## Exit codes (FR-020)

| Code | Condition |
| --- | --- |
| `0` | The review completed — including with findings, and including an empty scope. |
| `0` | Persistence of the artifact failed (warning only, FR-018). |
| `1` | The review could not be performed, or `--fail-on` was engaged and met. |
| `130` | Interrupted. |

**Findings are not failure.** A `critical` finding exits 0 unless
`--fail-on` says otherwise. This is the single most important behavioral
statement in this contract: `critique` is advisory, and a tool whose advice
fails your shell by default gets wrapped in `|| true` and stops being read.

## Human output

Ordered, and every section is always present in this order:

1. **Scope line** (FR-019) — what was reviewed, verbatim from
   `ResolvedScope.summary`:
   ```
   Reviewing working copy vs main — 4 files
   Reviewing epic mv-0041 (3 commits) — 11 files
   Reviewing paths: src/maverick/jj/ — 6 files
   ```
2. **Truncation notice**, when the embedded diff was cut (research R5):
   ```
   [yellow]Warning:[/yellow] diff exceeded the embedding budget; the reviewer
   was given the complete file list and read the remainder directly.
   ```
3. **Lens failure warning**, one line per failed lens (FR-011):
   ```
   [yellow]Warning:[/yellow] the completeness lens failed (<reason>); findings
   below are from the correctness lens only.
   ```
4. **Findings, grouped by file** (FR-015), files in ascending path order,
   findings within a file ordered critical → major → minor, then by lens,
   then by line:
   ```
   src/maverick/critique/scope.py
     [red]critical[/red]  L42  (correctness)  Unbounded read of the diff...
     [yellow]major[/yellow]    L88  (completeness) No test covers the empty-epic...
   ```
   Issue text is passed through `rich.markup.escape` before rendering.
   Findings with no `file` are grouped last under `(unattributed)`.
5. **Summary count line**:
   ```
   3 findings — 1 critical, 2 major, 0 minor
   ```
6. **Artifact line**, or the persistence warning:
   ```
   Report: .maverick/runs/a1b2c3d4/critique-report.md
   ```

### The two empty outcomes are distinguishable (FR-016)

| Situation | Output |
| --- | --- |
| Nothing was reviewed | `Nothing to review — working copy matches main.` and no findings section |
| Reviewed, nothing found | `Reviewing working copy vs main — 4 files` … `No findings.` |

A user must never have to guess whether the reviewer was silent or absent.

## Read-only guarantee (FR-012, FR-013, FR-014)

On every path, including every failure path and an interrupt:

- no commit is created, amended, or moved;
- no bead is created, updated, or closed (the epic scope *reads* beads);
- no tracked file's content changes;
- no assumption-ledger entry is created, and the land frontier is unaffected;
- the reviewer is invoked at most once per lens — there is no fix loop and no
  second round.

The only writes this command performs anywhere are
`.maverick/runs/<run-id>/critique-report.{json,md}`.

## Failure classification (FR-021)

See research R11. No new `ErrorKind` value is introduced. In human mode these
surface through `cli_error_handler()` as `Error: <message>`; the
classification is observable in `--json` mode only.
