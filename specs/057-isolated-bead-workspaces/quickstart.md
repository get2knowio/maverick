# Quickstart: Validating Isolated Bead Workspaces

**Feature**: 057-isolated-bead-workspaces | **Date**: 2026-08-20

How to prove this feature works end to end. Details live in
[contracts/](./contracts/) and [data-model.md](./data-model.md); this page is the
run guide.

---

## Prerequisites

- `jj` 0.44+ on `PATH`, and a **jj-colocated** checkout (`.jj/` present — run
  `maverick init` if not)
- `uv sync` completed
- A configured agent binding for the `implement` and `review` roles
- Some ready beads (`bd ready`) for the fly scenarios

---

## Scenario 1 — The primitive, without any workflow (US1)

The primitive is drivable on its own; this is the fastest way to see it work.

```bash
make test-integration ARGS="tests/integration/workspace -x"
```

Expected: provisioning, fold-back, conflict, and undo cases all pass. The two
tests worth watching specifically:

- **`test_fold_back_without_snapshot_is_empty`** — the R3 regression. It asserts
  that skipping the workspace snapshot produces an *empty* fold-back rather than
  an error, which is exactly why the snapshot lives in one chokepoint.
- **`test_undo_restores_unrelated_uncommitted_work`** — undo must not eat edits
  the user had in the checkout before the unit started.

### Watching it by hand

```bash
# In one shell: watch the checkout while a unit runs
watch -n 0.5 'jj status'

# In another: run an isolated bead
maverick fly --epic <id> --max-beads 1 --isolated
```

Expected: the checkout shows **no changes** for the entire implement/review
phase, then the bead's full delta appears at once, then a commit. You should
never observe a partially-implemented bead (SC-002).

---

## Scenario 2 — Isolated and normal runs agree (US3, SC-001)

The equivalence test is the load-bearing one for adoption.

```bash
make test-integration ARGS="tests/integration/fly/test_isolated_equivalence.py"
```

It runs the same beads from the same starting state twice — once normally, once
isolated — and compares commit subjects, trailers, ordering, and final file
contents. A diff in any of the four fails the test.

To run it manually against a scratch repo:

```bash
git clone <fixture-repo> /tmp/iso-a && git clone <fixture-repo> /tmp/iso-b
(cd /tmp/iso-a && maverick init && maverick fly --epic <id>)
(cd /tmp/iso-b && maverick init && maverick fly --epic <id> --isolated)
diff <(cd /tmp/iso-a && jj log -T 'description') \
     <(cd /tmp/iso-b && jj log -T 'description')
```

---

## Scenario 3 — Verification rejection and undo (US2)

The path that matters most, because undo is on the *normal* failure path here,
not an exceptional one.

```bash
make test-integration ARGS="tests/integration/fly/test_isolated_gate_failure.py"
```

Covers three shapes:

1. Gate fails → undo → fix round in the workspace → refold → gate passes →
   commit.
2. Gate fails with fix attempts exhausted → undo → bead abandoned → **checkout
   byte-identical to its pre-bead state**.
3. Undo itself fails → run halts, journal retained, recovery instructions
   printed, no further bead started.

Shape 3 is the one to read closely. It is the worst state this feature can
produce, and the assertion is that it is loud rather than silent.

---

## Scenario 4 — The bd-stays-out invariant (US4)

```bash
make test ARGS="tests/unit/workspace/test_boundary.py"
make typecheck        # CheckoutPath NewType catches the mistake at authoring time
```

Expected: a bd, ledger, or commit call given a workspace path raises
`IsolationBoundaryError`; mypy rejects passing a workspace path where a
`CheckoutPath` is required.

The concrete reason this matters is verifiable in one line:

```bash
grep -n '\.beads/' .gitignore
```

bd's store is gitignored, so it provably does not travel into a
`jj workspace add` workspace. That — not workspaces themselves — is the
constraint that retired hidden workspaces twice.

---

## Scenario 5 — No accumulated garbage (US5)

```bash
ls ~/.maverick/workspaces/$(basename $PWD)/fly/     # before
maverick fly --epic <id> --max-beads 2 --isolated   # then Ctrl-C mid-bead
maverick fly --epic <id> --max-beads 1 --isolated   # next run sweeps
ls ~/.maverick/workspaces/$(basename $PWD)/fly/     # after
jj log -r 'all()' | grep -c 'no description set'    # no stray anonymous heads
```

Expected: the abandoned workspace is gone after the next run, and no stray head
appears in `jj log` (FR-029 — the reason `workspace_forget` must precede
`rmtree`).

---

## Scenario 6 — Cross-run safety and crash recovery (FR-048, FR-049)

```bash
# Terminal 1
maverick fly --epic <id> --isolated

# Terminal 2, while the first is running
maverick fly --epic <other> --isolated
```

Expected: terminal 2 refuses immediately, naming the holding pid. It does not
queue, and it does not sweep terminal 1's live workspace.

For the interrupted-application case:

```bash
# Simulate: kill -9 during fold-back, then
maverick fly --epic <id> --isolated
```

Expected: refusal naming the unit, the operation that was in flight, and the
recovery step. **No automatic rollback** — whatever the user has done in the
checkout since the crash is theirs.

---

## Scenario 7 — Spec-chain parity (US6, SC-009)

```bash
make test-integration ARGS="tests/integration/spec_chain"
```

Expected: identical landed artifacts, identical resume behavior, identical exit
codes before and after migration — including `M6`, which resumes a **real
pre-migration checkpoint fixture**, not a synthesized one.

```bash
maverick spec <feature> --from-prd <file>   # full chain, unchanged
maverick spec <feature>                      # resume, unchanged
```

---

## Scenario 8 — Overhead budget (FR-050, SC-012)

```bash
make test-integration ARGS="tests/integration/workspace/test_overhead.py"
```

Asserts provision + fold-back + teardown stays within 5 s per unit **on this
repository**. The scratch-repo measurement (~0.02 s for `jj workspace add`) is
not the number that matters — tree materialization scales with repo size, which
is why the ceiling is a test and not a claim.

---

## Full gate

```bash
make format-fix && make ci
```

Run this before pushing. `make lint` does not include `ruff format --check`, but
CI does.
