# Quickstart: `maverick critique`

**Feature**: 058-standalone-code-review

---

## Prerequisites

An `agents.review` binding in `maverick.yaml` — the same one `maverick fly`
already uses for its reviewer:

```yaml
agents:
  review:
    provider: claude-code
    model_id: claude-opus-5
```

That is the whole setup. `critique` needs no beads, no epic, no flight plan,
and no `.maverick/` state. On the `diff` and `paths` scopes it does not touch
`bd` at all, so it works in a repository that has never been refuelled.

## The common case

```bash
$ maverick critique
Reviewing working copy vs main — 4 files

src/maverick/critique/scope.py
  critical  L42  (correctness)   Diff is read fully into memory before the
                                 truncation check, so the bound never applies.
  major     L88  (completeness)  No test covers an epic whose beads produced
                                 zero commits.

src/maverick/cli/commands/critique.py
  minor     L15  (correctness)   `--base` is accepted with `--epic` but ignored.

3 findings — 1 critical, 1 major, 1 minor
Report: .maverick/runs/a1b2c3d4/critique-report.md
```

Exit code `0`. Findings are advice, not failure.

## The other two scopes

```bash
# Everything an epic's beads committed
$ maverick critique --epic mv-0041
Reviewing epic mv-0041 (3 commits) — 11 files
...

# A subsystem as it currently stands, regardless of what changed
$ maverick critique src/maverick/jj/
Reviewing paths: src/maverick/jj/ — 6 files
...

# Against a different base
$ maverick critique --base origin/main
```

## Scripting it

```bash
$ maverick critique --json | jq '.result.severity_counts'
{
  "critical": 0,
  "major": 1,
  "minor": 0
}

# Which files have critical findings?
$ maverick critique --json \
    | jq -r '.result.findings[] | select(.severity=="critical") | .file' \
    | sort -u
```

Gate a pre-push hook on severity — opt in explicitly, because the default is
advisory:

```bash
$ maverick critique --fail-on critical || echo "blocked"
```

## Reading the report later

```bash
$ ls .maverick/runs/a1b2c3d4/
critique-report.json
critique-report.md

$ gh pr create --body-file .maverick/runs/a1b2c3d4/critique-report.md
```

## What it will not do

- It will not commit, amend, or move anything.
- It will not create, update, or close a bead — the epic scope only reads them.
- It will not fix anything. There is no fix loop; the findings are yours.
- It will not block `maverick land`. Critique findings never reach the
  assumption ledger or the landing frontier.

## Interpreting partial results

If one reviewer lens fails, you still get the other one's findings plus a
warning naming the failure. The exit code is still `0` — a timed-out
completeness lens does not invalidate the correctness findings that came back.
In `--json`, look for `lenses[*].error`.

## Distinguishing the two quiet outcomes

```bash
$ maverick critique
Nothing to review — working copy matches main.
```

means the reviewer never ran. Whereas:

```bash
$ maverick critique
Reviewing working copy vs main — 4 files

No findings.
```

means it ran and had nothing to say. In `--json`, `result.reviewed`
distinguishes them.
