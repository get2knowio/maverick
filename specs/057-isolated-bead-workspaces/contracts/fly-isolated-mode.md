# Contract: `maverick fly` Isolated Mode

**Feature**: 057-isolated-bead-workspaces
**Surface**: `maverick fly --isolated`, `maverick.yaml` `workspace.enabled`

---

## Invocation

```
maverick fly --epic <id> --isolated
maverick fly --epic <id> --no-isolated        # explicit off, overrides config
```

```yaml
# maverick.yaml
workspace:
  enabled: true                                # default: false
  root: ~/.maverick/workspaces                 # default
```

No `reuse` config key: `fly`'s `IsolationPolicy` always sets `reuse=False`
(one fresh workspace per bead, never shared) — load-bearing for G1-G9, not a
user-tunable setting. (An earlier draft of this contract exposed `reuse` as
config; `WorkspaceConfig` never actually wired it to either consumer, so it
was removed rather than implemented — see `src/maverick/config.py`'s
`WorkspaceConfig` docstring.)

**Resolution order**: `--isolated` / `--no-isolated` > `workspace.enabled` >
`false`. Absent both, behavior is byte-identical to today (FR-035, SC-011).

---

## Preconditions (FR-037)

Checked at the CLI boundary, before any bead is selected. Each refuses with an
actionable message and a non-zero exit:

| Condition | Message intent |
| --- | --- |
| `.jj/` absent | "run `maverick init`" — isolation needs a colocated repo |
| `jj` binary unavailable | name the missing binary |
| Another isolated run holds the lock | name the holding pid |
| Stale application journal present | name the unit, the operation, and the recovery step |

There is **no** silent fallback to non-isolated mode. A user who asked for
isolation and cannot have it is told so.

---

## Per-bead sequence

```
provision W (from @)
  → implement (agent, in W)
  → ac_check (artifact-level, in W)
  → spec_check (artifact-level, in W)
  → review (agent, in W) [+ review fix rounds, in W]
  → fold_back (W → checkout)
      ├─ CONFLICT → fail this bead, existing bead-failure policy applies
      └─ APPLIED/EMPTY → gate (environment-level, in the checkout)
              ├─ pass → record_assumptions → commit (checkout) → teardown W
              └─ fail → undo → gate fix (agent, in W) → fold_back → gate …
                        (bounded by MAX_GATE_FIX_ATTEMPTS, unchanged)
```

**Ordering note.** Non-isolated mode runs the gate immediately after
`implement`; isolated mode runs it after `review`. This is deliberate and is the
only observable ordering difference — see research.md R6. It does not affect
SC-001, which constrains the resulting *history*, not the internal step order.

---

## Guarantees

| # | Guarantee | Requirement |
| --- | --- | --- |
| G1 | Every agent step for a bead — implement, review, every fix round — runs in that bead's workspace | FR-032 |
| G2 | The checkout holds nothing from a bead whose agent step is executing | FR-007, SC-002 |
| G3 | Beads remain strictly serial; no unit begins while another's delta is unverified in the checkout | FR-015, FR-031 |
| G4 | Nothing is committed until every declared check has passed | FR-016, SC-004 |
| G5 | The commit carries the same `bead(<id>): <title>` subject and `Bead: <id>` trailer as the normal path, created by the orchestrator against the checkout | FR-033 |
| G6 | bead, ledger, and assumption writes target the checkout, never the workspace | FR-020, US3 scenario 5 |
| G7 | A fold-back conflict fails exactly one bead | FR-034, SC-005 |
| G8 | Context-file protection stays in force, rooted at the workspace, and blocked writes still drain to `protection_blocks` | FR-036 |
| G9 | Ctrl-C's two-stage contract, bead-failure policy, cost telemetry, and progress events are unchanged | spec Assumptions |

---

## New Burr state slots

Added to `build_fly_application(...).with_state(...)`, and to the `reads`/
`writes` of every consuming action (Guardrail: a slot added in one place and not
the other is the classic Burr bug):

| Slot | Type | Written by | Reset |
| --- | --- | --- | --- |
| `isolated` | `bool` | `init_state` (bound) | never |
| `workspace_path` | `str` | `process_bead_start` | per bead |
| `fold_back_result` | `dict \| None` | `fold_back` | per bead |
| `unverified_in_checkout` | `bool` | `fold_back` / `undo_fold_back` | per bead |
| `isolation_halt_reason` | `str` | `undo_fold_back` on failure | never — it ends the run |

`fold_back_result` is a separate slot from every fixer-feeding slot, per
Guardrail X.10's corollary: the fixer must never receive a condition it cannot
close.

---

## Failure taxonomy (FR-019)

Four outcomes that a naive implementation would collapse into "the bead failed",
and each must be separately observable in the run's output and logs:

| Outcome | Cause | Effect |
| --- | --- | --- |
| Agent failure | implement/review raised or returned unusable output | delta discarded, bead abandoned |
| Fold-back conflict | checkout moved under the bead | bead failed, conflicting paths named |
| Verification rejection | environment-level gate failed | undo, then fix round or abandon |
| Undo failure | `op restore` failed | **run halts**, journal retained, recovery instructions printed |

---

## Contract tests

| # | Test | Requirement |
| --- | --- | --- |
| F1 | Same beads, same start state: isolated and normal runs produce identical subjects, trailers, order, and file contents | SC-001 |
| F2 | Checkout polled throughout an isolated run never contains an in-flight bead's changes | FR-007, SC-002 |
| F3 | Without the flag or config, every observable behavior matches today | FR-035 |
| F4 | Gate failure → undo → fix in workspace → refold → pass → commit | FR-014, FR-017 |
| F5 | Gate failure with exhausted fix attempts → undo → bead abandoned → checkout clean | FR-014, SC-003 |
| F6 | Fold-back conflict fails one bead; the next bead proceeds | FR-034 |
| F7 | Assumptions recorded during an isolated bead land in the checkout's ledger and are stamped with the commit's change id | FR-020 |
| F8 | A protected-path write inside the workspace is blocked and reported | FR-036 |
| F9 | Preconditions refuse with actionable messages and no fallback | FR-037 |
| F10 | Undo failure halts the run and starts no further bead | FR-018 |
