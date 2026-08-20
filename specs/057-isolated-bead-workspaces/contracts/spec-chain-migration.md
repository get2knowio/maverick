# Contract: Spec-Chain Migration onto the Shared Primitive

**Feature**: 057-isolated-bead-workspaces (US6, FR-038–043)
**Surface**: `maverick spec` — behavior **unchanged**; implementation replaced

This contract is unusual: its entire content is a promise that nothing observable
changes. It exists because US6 puts a shipped, resumable workflow at risk, and
"no change" is only verifiable if it is written down first.

---

## What migrates

| Today | After |
| --- | --- |
| `workspace/spec_chain.py::prepare_workspace` | `IsolationSession.lease()` with `policy.reuse=True`, `retain_on_failure=True` |
| `workspace/spec_chain.py::teardown_workspace` | lease exit |
| `workspace/spec_chain.py::sweep_stale_workspaces` | `IsolationSession.sweep(keep=...)` |
| `spec_chain/landing.py::land_step_artifacts` (staged copy + rename) | `IsolationSession.fold_back()` with `fold_scope=("specs/<feature-dir>",)` |
| `landing.py::_strip_protected_paths` | `policy.fold_exclusions` (R11) |
| `agents/spec_chain.py`'s `os.chdir` block + module lock | `workspace/cwd_scope.py` (shared) |

**Stays chain-specific** (not workspace mechanics, so FR-039 does not touch it):
`resolve_feature_dir`, `verify_step_artifacts`, checkpointing, clarify policy,
and the resume logic.

---

## Unit mapping

| Concept | Value |
| --- | --- |
| Unit of work | one chain step (`specify`, `clarify`, `plan`, `tasks`, `analyze`) |
| Workspace key | the **feature slug** — all five steps share one workspace, as today |
| `reuse` | `True` — a resumable chain reuses its workspace |
| `retain_on_failure` | `True` — a halted chain's workspace is the only copy of the failing step's partial output |
| Check placement | **artifact-level only** — `verify_step_artifacts` reads the produced files and needs no toolchain |

Because every chain check is artifact-level, fold-back happens **only after the
step is verified complete**. The chain's "nothing lands until it is complete"
guarantee — the reason spec 050 exists — survives migration untouched (FR-042).
This is the concrete payoff of the FR-012 verification split.

---

## Guarantees

| # | Guarantee | Requirement |
| --- | --- | --- |
| S1 | The same artifacts land, at the same per-step granularity | FR-040 |
| S2 | Terminal output and exit-code semantics are unchanged, including analyze's degrade-to-warning | FR-040 |
| S3 | Resume works: first incomplete step, already-landed artifacts re-verified | FR-041 |
| S4 | A failed step lands no partial artifacts | FR-042 |
| S5 | No chain-specific provisioning, fold-back, or teardown implementation remains | FR-039, SC-008 |
| S6 | Protection blocks still drain per step into `ChainState.protection_blocks` and survive checkpoint/resume | FR-036 |

---

## Checkpoint compatibility (FR-043 — the sharp edge)

A checkpoint written by the pre-migration chain
(`.maverick/runs/<run-id>/spec-chain.json`) may be resumed by the post-migration
one.

**Rule**: resume either succeeds correctly or fails with an explicit, actionable
message. It may never silently misbehave.

**Mechanism**: `ChainState` gains a `schema_version`. Absent (pre-migration) is
read as version 0 and accepted when — and only when — its landed artifacts still
verify on disk, which resume already re-checks today. A checkpoint that cannot
be interpreted refuses with "re-run `maverick spec <feature> --from-prd <file>`"
rather than guessing.

**Test**: a fixture checkpoint captured from the pre-migration code path, resumed
by the new one. Not a synthesized dict — a real file, committed as a fixture.

---

## Contract tests

| # | Test | Requirement |
| --- | --- | --- |
| M1 | Full chain end to end: landed artifacts byte-identical to the pre-migration baseline | FR-040, SC-009 |
| M2 | Halted chain resumes from the first incomplete step | FR-041 |
| M3 | Failed step leaves no partial artifacts in the checkout | FR-042 |
| M4 | Halted chain's workspace is retained; completed chain's is torn down | FR-025, FR-024 |
| M5 | `grep` for chain-specific workspace/landing implementations returns nothing | FR-039, SC-008 |
| M6 | Pre-migration checkpoint fixture resumes correctly, or refuses explicitly | FR-043 |
| M7 | Fold-back scoped to `specs/<feature-dir>` — a workspace change outside it does not land | FR-040 |
