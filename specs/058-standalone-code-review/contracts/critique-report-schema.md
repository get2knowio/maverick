# Contract: `critique-report.json` schema

**Feature**: 058-standalone-code-review
**Status**: Normative
**Location**: `.maverick/runs/<run-id>/critique-report.json`
**Sibling**: `.maverick/runs/<run-id>/critique-report.md` (human rendering of
the same data — never a different set of findings)

---

## Conventions

Inherited from `land-report` (`specs/052-conditional-landing/contracts/land-report-schema.md`):

- `schema_version` is the first key. Currently `1`. Additive evolution only.
- Optional keys are **omitted when absent**, never emitted as `null`.
- `created_at` is a UTC ISO-8601 timestamp.
- The document is written with `atomic_write_json` — a reader never observes a
  partial file.

## Top level

| Key | Type | Presence | Notes |
| --- | --- | --- | --- |
| `schema_version` | int | always | `1` |
| `run_id` | string | always | 8 hex chars |
| `created_at` | string | always | |
| `reviewed` | bool | always | `false` ⇔ empty scope |
| `scope` | object | always | below |
| `lenses` | array | always | empty when `reviewed` is false; otherwise exactly 2, ordered correctness then completeness |
| `findings` | array | always | union across lenses, **not** de-duplicated |
| `severity_counts` | object | always | all three keys, zeros included |
| `truncated` | bool | always | the embedded diff was cut |
| `degraded_persistence` | bool | in the `--json` envelope only | absent from the on-disk file, which by definition persisted |

## `scope`

| Key | Type | Presence |
| --- | --- | --- |
| `kind` | `"diff"` \| `"epic"` \| `"paths"` | always |
| `summary` | string | always |
| `paths` | array of string | always (may be empty) |
| `base` | string | `kind == "diff"` only |
| `epic_id` | string | `kind == "epic"` only |
| `commits` | array of object | `kind == "epic"` only |

Each `commits[]` entry: `{ "sha": str, "subject": str, "bead_ids": [str] }`.
`bead_ids` lets a reader verify the attribution rather than trust the count.

`diff_text` is **not** persisted. It can be hundreds of kilobytes, it is
reconstructible from `scope` plus the repository, and a report artifact whose
size is dominated by a diff nobody reads is a bad artifact. `truncated`
records that the *agent's* copy was cut.

## `lenses[]`

| Key | Type | Presence |
| --- | --- | --- |
| `lens` | `"correctness"` \| `"completeness"` | always |
| `approved` | bool | success only |
| `finding_count` | int | success only |
| `error` | string | failure only |

A lens entry never carries both `approved` and `error`.

## `findings[]`

Exactly the `ReviewFindingPayload` projection — same fields fly produces
(SC-003):

| Key | Type | Presence |
| --- | --- | --- |
| `severity` | `"critical"` \| `"major"` \| `"minor"` | always |
| `issue` | string | always |
| `file` | string | always (may be `""`) |
| `line` | int | when known |
| `reviewer` | `"correctness"` \| `"completeness"` | always for critique findings |

Ordering is fixed (data-model.md): file ascending, then severity
critical → major → minor, then lens, then line. The markdown sibling and the
terminal output use this same order, which is what makes SC-006 checkable.

## `severity_counts`

```json
{ "critical": 0, "major": 2, "minor": 1 }
```

All three keys always present. A consumer must never have to distinguish "no
critical findings" from "the `critical` key is missing".

## Example

```json
{
  "schema_version": 1,
  "run_id": "a1b2c3d4",
  "created_at": "2026-08-22T18:04:11.913204+00:00",
  "reviewed": true,
  "scope": {
    "kind": "epic",
    "summary": "epic mv-0041 (3 commits)",
    "epic_id": "mv-0041",
    "paths": ["src/maverick/critique/scope.py", "tests/unit/critique/test_scope.py"],
    "commits": [
      { "sha": "9de3a34", "subject": "bead(mv-0042): resolve epic scope", "bead_ids": ["mv-0042"] }
    ]
  },
  "lenses": [
    { "lens": "correctness",  "approved": false, "finding_count": 1 },
    { "lens": "completeness", "approved": true,  "finding_count": 0 }
  ],
  "findings": [
    {
      "severity": "major",
      "issue": "Epic scope resolution reads the full log without a bound.",
      "file": "src/maverick/critique/scope.py",
      "line": 88,
      "reviewer": "correctness"
    }
  ],
  "severity_counts": { "critical": 0, "major": 1, "minor": 0 },
  "truncated": false
}
```
