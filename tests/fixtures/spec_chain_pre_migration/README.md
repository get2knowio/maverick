# Pre-migration spec-chain baseline fixtures

Captured for spec `057-isolated-bead-workspaces`, User Story 6, task T094 —
a baseline proving what the **current** (pre-migration)
`SpecChainWorkflow`/`prepare_workspace`/`land_step_artifacts` mechanism
actually produces, before it is replaced by the shared `IsolationSession`
primitive (see `specs/057-isolated-bead-workspaces/contracts/spec-chain-migration.md`,
"Checkpoint compatibility"). Task `T098` (checkpoint-compat integration
test) consumes these fixtures after migration to prove nothing observable
changed.

**Generated from commit**: `9f45296a1dfbef457d2445a098b1c4cad76ad75a`
(the tip of `main` at capture time; `src/maverick/workflows/spec_chain/`
and `src/maverick/workspace/spec_chain.py` were unmodified pre-migration
code at that point). These are **real** artifacts and a **real** checkpoint
produced by actually running `SpecChainWorkflow` end to end against a
stubbed airframe runtime (no live model calls) — not hand-written or
synthesized data.

## How these were generated

A throwaway script (not committed) reused the existing integration-test
harness verbatim:

- `tests/integration/spec_chain/conftest.py` — `build_speckit_repo`,
  `ConfigurableSpeckitRuntime`, `stub_runtime_factory`, `make_config`.
- The same invocation pattern as
  `tests/integration/spec_chain/test_full_chain.py` (full run) and
  `tests/integration/spec_chain/test_halt.py`'s
  `TestClarifyFailureHalts.test_clarify_blocked_halts_before_plan` (halt,
  via a `ChainStep.CLARIFY` handler returning `status: "blocked"`) /
  `tests/integration/spec_chain/test_resume.py` (resume with a default
  handler after the halt).

Reproduction sketch (this is not a committed file — recreate it if you
need to regenerate the fixtures):

```python
# 1. Full chain:
#    - build_speckit_repo() into a real (non-pytest-tmp_path) directory
#    - stub_runtime_factory(monkeypatch) with no overrides (all steps
#      succeed via ConfigurableSpeckitRuntime's defaults)
#    - SpecChainWorkflow(config=make_config()).execute(inputs) to
#      completion, run_id="baseline-full-chain"
#    - copy specs/001-widget-export/** out of the checkout

# 2. Halted + resumed chain (separate checkout, same run_id both runs):
#    - Run 1: stub_runtime_factory(monkeypatch,
#        step_handlers={ChainStep.CLARIFY: lambda *_: {"status": "blocked", ...}})
#      -> chain halts after specify succeeds, clarify fails, plan/tasks/
#         analyze are skipped. Copy .maverick/runs/<run_id>/spec-chain.json.
#    - Run 2 (same run_id, same checkout): stub_runtime_factory(monkeypatch)
#      with no overrides -> resumes from clarify, completes.
#      Copy specs/001-widget-export/** out of the checkout.
```

Both runs used the standard `bd`-stubbing pattern (`BeadClient.query` /
`create_bead` / `set_state` patched, `library.actions.beads.defer_bead`
mocked) from `tests/integration/spec_chain/conftest.py`'s `bd_stubs`
fixture — no real `bd` install was involved, matching how the existing
integration suite runs.

Feature slug used throughout: `widget-export` (`FEATURE`), landing at
`specs/001-widget-export` (`FEATURE_DIR`) — the same constants
`tests/integration/spec_chain/conftest.py` defines, chosen so a later
test reading these fixtures doesn't have to guess.

## Contents

- `full_chain/specs/001-widget-export/` — the complete landed artifact
  tree (`spec.md`, `plan.md`, `tasks.md`) from a full, uninterrupted
  5-step chain run (specify → clarify → plan → tasks → analyze), all
  steps `succeeded` and `landed=True`. `spec.md` includes the
  `## Clarifications` section clarify appended, matching Spec Kit's
  non-interactive convention.

- `halted_checkpoint/spec-chain.json` — the **real** checkpoint file
  (`.maverick/runs/<run-id>/spec-chain.json`) captured at the moment a
  chain halted: `status: "halted"`, `specify` succeeded, `clarify`
  failed (agent reported `status: "blocked"`), `plan`/`tasks`/`analyze`
  all `skipped`. Its `workspace_path` field points at a temp directory
  from the capture run (`/tmp/spec_chain_baseline_capture/...`) that will
  not exist when this fixture is loaded later — this is intentional,
  stale-path realism a genuine pre-migration checkpoint would have, and
  must **not** be hand-edited to "fix" it (T098 is exactly the test that
  exercises what resume does with a checkpoint like this).

- `resumed_chain/specs/001-widget-export/` — the complete landed
  artifact tree after the same run resumed (same `run_id`, same
  checkout) from the halted checkpoint above and ran to completion. All
  five steps end `succeeded`/`landed=True`; `specify` was not re-invoked
  on resume.

## Verifying

```bash
find tests/fixtures/spec_chain_pre_migration -type f
python3 -c "
import json
d = json.load(open('tests/fixtures/spec_chain_pre_migration/halted_checkpoint/spec-chain.json'))
print(d['status'], {k: v['status'] for k, v in d['steps'].items()})
"
```

Expected: `halted {'specify': 'succeeded', 'clarify': 'failed', 'plan': 'skipped', 'tasks': 'skipped', 'analyze': 'skipped'}`
