# Contract: `maverick critique --json`

**Feature**: 058-standalone-code-review
**Status**: Normative
**Depends on**: `specs/053-assumption-review-console/contracts/error-envelope.md`

---

## Verb

| Invocation | `verb` |
| --- | --- |
| `critique --json` (any scope) | `critique.run` |

One verb. Scope is a property of the result, not of the verb — a consumer
branching on scope reads `result.scope.kind`, which is stable, rather than
parsing the verb string.

## Envelope

The shared shape from `src/maverick/cli/json_output.py`. Exactly one JSON
document on stdout on every path (SC-005); all progress, warnings, and
diagnostics go to stderr.

### Success

```json
{
  "ok": true,
  "verb": "critique.run",
  "result": { ...CritiqueReport.to_dict()... }
}
```

`result` is exactly the persisted `critique-report.json` body — the same
projection, so the artifact and the envelope can never drift. See
`critique-report-schema.md`.

### Failure

```json
{
  "ok": false,
  "verb": "critique.run",
  "error": {
    "kind": "not-found",
    "message": "epic 'mv-9999' does not exist",
    "details": { "epic_id": "mv-9999" }
  }
}
```

| `kind` | Raised when |
| --- | --- |
| `validation` | conflicting scopes; a named path that does not exist or lies outside the repository; `--base` given with a non-diff scope |
| `not-found` | the named epic does not exist |
| `bd-unavailable` | `bd` is not available — **epic scope only** |
| `vcs` | a git read failed while resolving the scope |
| `internal` | both reviewer lenses failed |

No new `ErrorKind` value is introduced (FR-021). `bd-unavailable` follows the
precondition-check convention documented in `json_output.py`'s module
docstring: `verify_available()` returns `False` rather than raising, so the
command translates it into an envelope itself.

## Exit codes

Identical to the human contract: `0` on a completed review regardless of
findings; `1` when the review could not be performed or `--fail-on` is
engaged and met; `130` on interrupt. A failure envelope always accompanies a
non-zero exit **except** for the `--fail-on` case, which emits a *success*
envelope (the review completed) with a non-zero exit. A consumer must
therefore branch on `ok`, never on the exit code alone.

## Empty scope

An empty scope is a success, not a failure:

```json
{
  "ok": true,
  "verb": "critique.run",
  "result": {
    "schema_version": 1,
    "reviewed": false,
    "scope": { "kind": "diff", "summary": "working copy vs main", "base": "main",
               "paths": [], "commits": [] },
    "findings": [],
    "severity_counts": { "critical": 0, "major": 0, "minor": 0 },
    "lenses": []
  }
}
```

`reviewed: false` with empty `lenses` is how a consumer distinguishes "nothing
was reviewed" from "reviewed, found nothing" (which has `reviewed: true` and
two `lenses` entries). Exit code `0`.

## Partial success

One lens failing is reported inside a **success** envelope — the review
completed, degraded:

```json
{
  "ok": true,
  "verb": "critique.run",
  "result": {
    "reviewed": true,
    "lenses": [
      { "lens": "correctness",  "approved": false, "finding_count": 2 },
      { "lens": "completeness", "error": "runtime timeout after 600s" }
    ],
    "...": "..."
  }
}
```

A consumer that requires both lenses checks for any `lenses[*].error`. Making
this a failure envelope was rejected: the findings that *were* produced are
real and useful, and discarding them because the other lens timed out would
be strictly worse for the caller.
