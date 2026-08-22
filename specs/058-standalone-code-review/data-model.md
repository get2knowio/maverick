# Data Model: Standalone Code Review

**Feature**: 058-standalone-code-review
**Date**: 2026-08-22

All models are frozen (`@dataclass(frozen=True, slots=True)` for local types,
Pydantic where a payload crosses the agent boundary). Guardrail 3: no ad-hoc
`dict[str, Any]` blobs — every value below is a typed contract.

---

## Reused verbatim (no new model)

| Type | Home | Why reused |
| --- | --- | --- |
| `ReviewFindingPayload` | `maverick.payloads:240` | FR-007/SC-003 — critique findings must be *the same shape* fly produces. `severity`, `issue`, `file`, `line`, `reviewer`. |
| `SubmitReviewPayload` | `maverick.payloads:265` | The reviewer's result model. Unchanged. |
| `ReviewerAgent` | `maverick.agents.reviewer:35` | Gains one method (R2); no field or result-model change. |

---

## `CritiqueScopeKind` (StrEnum)

```python
class CritiqueScopeKind(StrEnum):
    DIFF = "diff"
    EPIC = "epic"
    PATHS = "paths"
```

Exactly three, per FR-002. The value is what appears in the JSON artifact and
the `--json` envelope, so it is a stable contract string.

---

## `ResolvedScope`

The answer to "what is being reviewed", produced before any agent runs.

| Field | Type | Notes |
| --- | --- | --- |
| `kind` | `CritiqueScopeKind` | |
| `summary` | `str` | One human line, e.g. `"working copy vs main"`, `"epic mv-0041 (3 commits)"`, `"paths: src/maverick/jj/"`. Rendered verbatim (FR-019). |
| `base` | `str \| None` | Set on `DIFF` only. |
| `epic_id` | `str \| None` | Set on `EPIC` only. |
| `commits` | `tuple[ScopedCommit, ...]` | Empty except on `EPIC`. |
| `paths` | `tuple[str, ...]` | Repo-relative. On `PATHS`, what the user named; on `DIFF`/`EPIC`, the changed-file union. |
| `diff_text` | `str` | Possibly truncated (R5). |
| `diff_truncated` | `bool` | True when `diff_text` was cut at `MAX_EMBEDDED_DIFF_CHARS`. |
| `diff_stat` | `str` | Raw `--stat` output; never truncated. |

**Invariants**:

- `is_empty` ⇔ `not paths and not diff_text`. FR-009 checks this *before* the
  agent is built, so an empty scope costs zero model calls.
- `paths` is always populated for a non-empty scope, even when `diff_text` is
  truncated — the agent must always know the complete file list (R5).
- `commits` is non-empty on `EPIC` unless the scope is empty.

---

## `ScopedCommit`

| Field | Type | Notes |
| --- | --- | --- |
| `sha` | `str` | Short SHA. |
| `subject` | `str` | First line. |
| `bead_ids` | `tuple[str, ...]` | From `extract_bead_ids` (R3), intersected with the epic's beads. |

Exists so the artifact can state *which* commits were attributed to the epic —
a reader must be able to check the attribution, not just trust the count.

---

## `LensOutcome`

One reviewer lens's result. Models FR-011's partial success.

| Field | Type | Notes |
| --- | --- | --- |
| `lens` | `Literal["correctness", "completeness"]` | |
| `findings` | `tuple[ReviewFindingPayload, ...]` | Empty on failure. |
| `approved` | `bool \| None` | `None` on failure — distinct from `False`. |
| `error` | `str \| None` | Set iff the lens failed. |

`failed` ⇔ `error is not None`. A `LensOutcome` never carries both findings
and an error.

---

## `CritiqueReport`

The complete outcome of one invocation.

| Field | Type | Notes |
| --- | --- | --- |
| `schema_version` | `int` | `1`. First key of `to_dict()`. |
| `run_id` | `str` | `uuid4().hex[:8]`. |
| `created_at` | `str` | `datetime.now(UTC).isoformat()`. |
| `scope` | `ResolvedScope` | |
| `lenses` | `tuple[LensOutcome, ...]` | Always both, in fixed order (correctness, completeness) so the artifact is stable. |
| `findings` | `tuple[ReviewFindingPayload, ...]` | Union across lenses, **not** de-duplicated (R7). Ordered: file asc, then severity critical→major→minor, then lens, then line. |
| `severity_counts` | `Mapping[str, int]` | All three keys always present, zeros included — a consumer must not have to distinguish "no critical findings" from "the key is missing". |
| `truncated` | `bool` | Mirrors `scope.diff_truncated`. |
| `degraded_persistence` | `bool` | True when the artifact could not be written (FR-018). |

**Derived**:

- `reviewed` ⇔ `not scope.is_empty` — distinguishes "no findings" from
  "nothing was reviewed" (FR-016).
- `lens_failures` — the failed `LensOutcome`s, for the warning line.
- `exceeds(severity)` — drives `--fail-on` (FR-006).

`to_dict()` follows `LandReport`'s conventions: absent optional keys are
omitted rather than emitted as `null`.

---

## Ordering, and why it is fixed

Finding order is deterministic and specified because three surfaces must
agree: the terminal grouping, the persisted JSON, and the `--json` envelope.
SC-006 asserts terminal and artifact contain the same findings; that assertion
is only checkable if both are ordered the same way. Severity ordering is
`critical < major < minor` by a module constant, never by string sort —
alphabetically, `critical < major < minor` happens to be correct today, which
is exactly the kind of accident that breaks when a severity is added.

---

## Relationships

```
CritiqueReport
├── ResolvedScope ──── ScopedCommit*        (EPIC scope only)
├── LensOutcome × 2 ── ReviewFindingPayload*  (reused from payloads.py)
└── findings ───────── ReviewFindingPayload*  (union of both lenses)
```

Nothing in this model references a bead, a ledger entry, or a commit the
command creates — there are none (FR-012, FR-014). `ScopedCommit` references
commits that already existed.
