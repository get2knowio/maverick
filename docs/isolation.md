# Isolated Execution

Two workflows run agent steps inside a short-lived, per-unit jj workspace
instead of the user's checkout: `maverick fly --isolated` (opt-in, off by
default — one workspace per bead) and the headless spec chain,
`maverick spec` (always isolated — one workspace per feature, shared across
its five steps). Both consume the same shared primitive,
`src/maverick/workspace/` (`IsolationSession`), which provisions a workspace,
lets an agent step run inside it, folds the resulting delta back into the
checkout, and tears the workspace down — or undoes the fold-back and retries
on failure. Everything that isn't an agent step — bd, the assumption ledger,
and every commit — always targets the checkout, never the workspace (see
`CLAUDE.md` Guardrail 0).

Provisioning, fold-back, and teardown pay for themselves only if the checks
that gate a bead or a chain step run in the right place. That placement
splits into two kinds.

## The two check placements

**Artifact-level** checks read the files an agent step produced, or the
working-copy diff — nothing more. They need no toolchain, so they can run
*inside* the workspace, before fold-back, without waiting for a delta to land
in the checkout.

**Environment-level** checks need the real toolchain — `.venv`, installed
dependencies, build state. Those are gitignored and do not travel into a
workspace (`jj workspace add` shares the backing repo, not the untracked
filesystem state a toolchain depends on), so these checks can only run
*after* fold-back, against the checkout.

## Why the split exists

A check can only see what its execution environment actually has. An
artifact-level check needs nothing beyond the files an agent just wrote, so
running it in the workspace costs nothing and lets a bead or chain step fail
fast, before anything reaches the checkout. An environment-level check needs
state that never exists in the workspace at all — the gitignored toolchain —
so it has no choice but to run after the delta has folded back.

This is also what decides *ordering*, not just placement. `maverick fly
--isolated` reorders its pipeline relative to the non-isolated path
specifically so environment-level work happens exactly once, after every
agent step (including review's fix rounds) has already run in the workspace:
folding back and undoing repeatedly around individual agent calls was
considered and rejected as strictly more work for a weaker guarantee. The
full reasoning, including the alternatives considered and their tradeoffs, is
in [research.md](../specs/057-isolated-bead-workspaces/research.md)'s R6,
[Where does verification run, and in what order?](../specs/057-isolated-bead-workspaces/research.md#r6-where-does-verification-run-and-in-what-order).

## Which checks land where

| Consumer | Check | Placement | Runs in |
| --- | --- | --- | --- |
| `fly --isolated` | `ac_check` (file scope, diff overlap, grep commands) | artifact-level | workspace |
| `fly --isolated` | `spec_check` | artifact-level | workspace |
| `fly --isolated` | `gate` (`format`, `lint`, `test`) | environment-level | checkout, after fold-back |
| `spec` (spec chain) | `verify_step_artifacts` | artifact-level | workspace |

The spec chain has no environment-level check at all — every one of its
checks reads produced files, so its fold-back only ever happens once a step
is verified complete, and the reordering problem `fly --isolated` solves
doesn't arise there. See
`specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md` and
`specs/057-isolated-bead-workspaces/contracts/fly-isolated-mode.md` for the
full mechanism, and `specs/057-isolated-bead-workspaces/contracts/spec-chain-migration.md`
for the spec chain's contract.
