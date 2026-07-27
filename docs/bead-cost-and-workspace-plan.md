# Workspace leaks, event-bead bloat, and write amplification — plan

**Audience:** Maverick maintainers; the implementation plan for the three cost defects filed from the first live Spec Kit walkthrough.
**Status:** Proposed. Not yet implemented. Supersedes the "Not in this PR" section of #175.
**Date:** 2026-07-27.
**Author:** derived from the live walkthrough of `spec → refuel --speckit → fly → land` against `sample-maverick-project` (#168).

## TL;DR

Three defects, all cost rather than correctness, all measured live. Land as three
sequenced PRs: workspace teardown + sweep; state-as-labels + one-shot graph creation;
read-path optimisation. Target: 28-task refuel from **278s and 161 event beads** to
roughly **15s and ~76 event beads**, and speckit ingestion back under its own SC-001 30s
bound.

Phase-barrier gate beads were considered and deliberately rejected — see
[Out of scope](#deliberately-out-of-scope).

## Context

The walkthrough (#168, fixes landed in #175) found four correctness defects and left
three cost defects filed but unbuilt. None breaks a run today; all three worsen with
every feature.

**Workspaces leak permanently.** `prepare_workspace(reuse=False)` only wipes on the next
run *of the same feature*, and a completed feature can never be re-run (the CLI's
collision check exits 2). Every feature ever specced therefore leaves a ~349K directory,
a registered `jj` workspace, **and a stray anonymous head in the user's own commit
graph**.

**Event beads outnumber real ones 3:1.** `bd set-state` is a state-machine primitive
(its own help gives `patrol:active`, `mode:degraded`) being used to store immutable
provenance — an event bead recording "T001 became T001", forever. Measured: 160 event
beads for ~50 real ones; `spec` produced 60 for 18, `refuel` added 100 more.

**Every write is its own subprocess.** 28 tasks cost ~204 `bd` invocations and 278s; a
136-task spec would cost ~1,200. Speckit ingestion already exceeds its SC-001 30s bound
(39.4s on a *four-task* fixture). That bound is the canary, not the problem.

## Verified facts

Confirmed against bd v1.1.0 (`8e4e59d39`) source and the installed binary. Do not
re-derive.

- **`bd create --graph <plan.json> --json`** creates an epic + N tasks + M edges in **one
  Dolt transaction**. Schema: `{commit_message?, nodes[], edges?}`; node `{key, title,
  type?, description?, assignee?, priority?, labels?[], metadata?{str:str}, parent_key?,
  parent_id?}`; edge `{from_key|from_id, to_key|to_id, type?}`. Returns
  `{"ids": {nodeKey: beadId}}`.
- **Edge direction is inverted from ours.** bd builds `Dependency{IssueID: from,
  DependsOnID: to}` — `to` blocks `from`. Our `plan.edges` are `(blocker, blocked)`, so
  **`from_key = blocked`, `to_key = blocker`**. Corroborated independently by
  `bd dep add --file`'s documented `{"from":"bd-42","to":"bd-41"}`, which is equivalent to
  the `bd dep add <blocked> --blocked-by <blocker>` we already emit.
- **Node `labels` is a JSON array**, so state seeds at creation with **no event bead** and
  none of `--labels`' comma-splitting hazard. `bd state list` derives state purely from
  labels, so a create-time label is indistinguishable on readback from a `set-state` one.
- **Graph children do NOT inherit parent labels**, unlike `bd create --parent` (which does
  by default). This silently fixes a latent bug: assumption beads created under a speckit
  epic today inherit `speckit_feature` as their own state dimension.
- **Unknown fields are silently dropped** with a greppable stderr warning
  (`has unknown field(s)`), not an error.
- `bd set-state` is `cobra.ExactArgs(2)` — one dimension per invocation, definitively.
- **`--graph --dry-run` prints human text, not JSON.** Useless as a probe.

**One assumption is unverified and gates everything:** that `--json` is honoured alongside
`--graph` and emits `{"ids": …}` on success. The `IDs json:"ids"` struct exists, but this
could not be proven read-only. **Verify before writing any translator code** — in a
throwaway `bd init` directory, run a two-node plan and confirm both the `ids` map and that
`bd dep tree` shows `a` blocking `b`, not the reverse.

## PR 1 — Workspace teardown and sweep

Self-contained; no bd involvement.

The workspace holds nothing durable. Landing copies workspace → checkout after every step,
nothing is committed inside it, `prepare_workspace` already treats a missing directory as
ordinary (`workspace/spec_chain.py:65`), and `_reseed_workspace_from_checkout`
(`workflows/spec_chain/workflow.py:417`) exists to rebuild it from the checkout on resume.
Resume depends on the checkpoint and the landed artifacts — never the workspace.

- Add `teardown_workspace(*, cwd, feature, jj_client, home=None)` to
  `src/maverick/workspace/spec_chain.py`, beside `prepare_workspace`. `jj workspace forget
  <name>` **then** `shutil.rmtree` — that order, or the stray head survives. Best-effort:
  log a warning, never raise. A completed chain must not fail because cleanup did.
- Call it from `workflows/spec_chain/workflow.py` on the `status == "completed"` path only,
  after the final checkpoint. **Keep the workspace on halt or Ctrl-C** — it is the only copy
  of the failing step's partial output, and resume reuses it.
- Add `sweep_stale_workspaces(*, cwd, jj_client, home=None)`, called at the top of
  `prepare_workspace`. Enumerate `~/.maverick/workspaces/<project>/spec-chain/*`; forget +
  remove any whose feature has no resumable chain state. Reuse `discover_resumable`
  (`workflows/spec_chain/state.py:50`) as the predicate — it already answers exactly "is
  this feature resumable?", so no new policy is invented.

The sweep is what bounds growth: teardown-on-completion never fires for the abandoned
Ctrl-C chains that are the realistic leak.

## PR 2 — State as creation labels, and one-shot graph creation

The risky one. Steps 1–4 are additive dead code; only step 5 changes behaviour, so the
behavioural change is a single `git revert`.

**1. `src/maverick/beads/state.py`** (new). `state_to_labels(Mapping[str,str]) -> list[str]`
(sorted by key, `"k:v"`), its inverse `labels_to_state`, and `validate_state_pair` rejecting
empty key/value, `:` in the key, and `,` in either. Separately harden `create_bead`
(`beads/client.py:163`) to raise on a label containing `,` — `--labels` is comma-joined and
repeating the flag does not help, so validation is the only correct fix.

**Do not add a `state` field to `BeadDefinition`.** `create_bead` cannot honour it correctly
(comma-joining), so the field would mean different things depending on which method received
it. Keep `PlannedBead.state` (`speckit/build.py:31-38`) as-is and merge it into node labels
at translation time; `build.py` and `tests/unit/speckit/test_build_plan.py` stay untouched.

**2. `src/maverick/beads/graph.py`** (new) — frozen Pydantic `GraphPlan`/`GraphNode`/`GraphEdge`
with `extra="forbid"` and `exclude_none=True`, so Maverick structurally *cannot* emit a field
bd does not know. Model only what we emit, not everything bd accepts. `validate_local()`
mirrors bd's checks (unique non-empty keys, edge endpoint resolution, exactly one of
`parent_key`/`parent_id`, no edge duplicating a parent-child pair) so failures surface in
Maverick's vocabulary before a subprocess is spawned.

**3. `BeadClient.create_graph(plan) -> dict[str, str]`** — argv is exactly
`["bd","create","--graph",<path>,"--json"]` and nothing else; every other flag conflicts.
Write the plan to a `NamedTemporaryFile` in the *system* temp dir (not the user's repo),
unlink in `finally`. New `BD_GRAPH_TIMEOUT = 180.0`. Parse tolerantly (`{"ids":…}` or
`[{"ids":…}]`), as `show`/`close` already do. New `BeadGraphUnsupportedError(BeadError)`
raised **only** on stderr matching `unknown flag: --graph`; everything else is a real error.
On success, scan stderr for `has unknown field(s)` and surface it as a warning — never fail,
since by then the transaction has committed.

**4. `src/maverick/speckit/graph.py`** (new) — `build_graph_plan(plan, *, feature_name)`.
Node keys are the Spec Kit task IDs verbatim (`T001`, …) plus `EPIC`, so `created_map`
reconstruction is a one-liner and bd's own errors speak Spec Kit vocabulary.

Put the direction inversion in **one** function, named in our vocabulary
(`_blocks_edge(blocker=…, blocked=…)`), with the `bd dep add --file` corroboration in its
docstring. This is the single most likely bug in the change. An `_endpoint` helper picks
`*_key` when the identifier is a plan node and `*_id` otherwise, replacing `_resolve_bead_id`
(`refuel_speckit/workflow.py:46`) — strictly better than the `_TASK_ID_RE` regex, because it
fails loudly instead of passing a stale task ID through as a bead ID.

**One plan handles both fresh and delta runs.** They differ only in that the epic node is
absent on delta and tasks use `parent_id` rather than `parent_key`, and that a delta edge's
`to` side may be `to_id`. `bd dep add --file` is unnecessary — graph edges already accept
`from_id`/`to_id`.

**5. Wire the workflow** (`refuel_speckit/workflow.py`). Steps 6/7/8 collapse: step 6 calls
`create_graph`; **step 7's `set_state` loop (`:320-324`) is deleted**; step 8 keeps its event
bracket but its body becomes `wired_count = len(plan.edges)`, since the edges were created in
the same transaction and "wired" is now exact rather than best-effort. Extract today's loop
verbatim into `_create_beads_serially` as a fallback behind a one-line
`_GRAPH_FALLBACK_ENABLED`, so deleting it later is trivial. Assert every planned task appears
in the returned `ids` — the cheap defence against a silently dropped node. Steps 9–11
(`_chain_epic`, `_adopt_remediation_beads`, `_record_run`, commit) are unchanged.

**Behaviour change to flag in review:** creation becomes atomic. Today a mid-loop failure
leaves partial beads with a message listing them; under a graph plan nothing is created. That
is an improvement, but `TestMidCreationFailure`
(`tests/unit/workflows/refuel_speckit/test_workflow.py:252-281`) asserts the old semantics and
must be rewritten — keep its body as a `TestSerialFallback` test.

## PR 3 — Read path

After PR 2, creation is no longer the bottleneck: `_adopt_remediation_beads` alone would be
~57 of the ~61 remaining subprocesses, because it `show`s every open task bead in the repo and
**`show` costs two subprocesses**.

- **`BeadClient.show`** (`beads/client.py:369-373`) calls `_state_dict`, which spawns
  `bd state list` purely to decode `dim:value` labels that `bd show --json` already returned.
  Replace with `labels_to_state(data["labels"])` — the PR 2 helper, run backwards. This halves
  every `show`, and `show` sits in every hot loop in the ledger, brief, review, land, and
  reconcile. Verify first that bd treats every colon-bearing label as a state dimension.
- **Filter server-side.** `_adopt_remediation_beads` (`refuel_speckit/workflow.py:554`) queries
  all open tasks then filters on a label it could have queried for:
  `client.query("type=task AND status=open AND label=spec-remediation")`. `_find_existing_epic`
  (`:423-457`) has the same shape and can filter on `label=speckit_feature:<name>` precisely
  *because* PR 2 writes that label at creation.

## Deliberately out of scope

**Gate beads.** Collapsing the phase barrier's `S×R` cross-product to `S+R` with a synthetic
per-boundary bead was considered and rejected. With `create --graph`, 688 edges cost the same
as 1, which removes most of the motivation — while the blast radius is six integration points:
`select_next_bead`'s hardcoded `limit=10` (`library/actions/beads.py:287`); a deadlock unless
something auto-closes the gate; distorted counts in `brief` (`cli/commands/brief.py:390-391`)
and `open_bead_analysis` (`:197-203`); delta runs unable to rediscover prior gates (they carry
no `speckit_task_id`); and `_defer_dependent_beads` (`fly_beads/_commit.py:408-449`) walking
only one hop, so a stuck task would stop deferring downstream work. Revisit with real numbers
after PR 2, as its own spec.

**Migrating the other seven `create_bead` sites** to creation-time labels. The ledger's values
are free text containing commas and colons, and most of its dimensions (`assumption_status`,
`assumption_severity`, `assumption_answer`, all five `assumption_reconcile_*`) are genuinely
mutable and must keep `set_state` — an event log earns its cost there. They get
`state_to_labels` when they migrate; not here.

## Verification

**Before any translator code:** confirm `bd create --graph <plan> --json` returns `{"ids": …}`
and that `bd dep tree` shows the direction we expect. Everything rests on it.

**Unit** (no bd required): the edge-direction test written twice in two vocabularies, so a
copy-paste inversion cannot pass both; a golden serialization of the full
`tests/unit/speckit/conftest.py` fixture; an allow-list assertion that every emitted key is in
the schema constant; parent wiring for fresh vs delta; `validate_local` negatives; exact argv
and temp-file *contents* for `create_graph`; `unknown flag` → `BeadGraphUnsupportedError`. The
highest-leverage single edit is giving
`tests/unit/workflows/refuel_speckit/conftest.py::make_mock_bead_client` a `create_graph` mock
that derives IDs from the submitted plan, so workflow tests assert against a real `GraphPlan`
rather than a call list.

**Integration** (`tests/integration/test_speckit_refuel.py`): assert the direction *in the
database* — after a fresh ingest, a phase-2 task's blocker must be the phase-1 task, not the
reverse. The existing `bd ready` check would pass even if every edge were symmetrically
inverted within a barrier. Also assert a delta-created child carries no `speckit_feature`
dimension (documenting the intentional inheritance change), and count event beads before and
after.

**Numbers that prove it worked**, against the recorded baseline:

| Measure | Before | Target |
| --- | --- | --- |
| Event beads, 28-task feature | 161 | ~76 (PR 2) |
| `bd` invocations, 28 tasks | ~204 | ~61 (PR 2) → ~15 (PR 3) |
| Refuel wall clock, 28 tasks | 278s | ~90s → ~15s |
| SC-001 four-task fixture | 39.4s (warns) | <30s, and turn the `warnings.warn` at `:105-112` into a hard assert |

**End to end:** re-run the walkthrough against `sample-maverick-project` — `maverick spec` on
a second feature (which also exercises epic chaining and the `high`-severity blocks edge that
feature 001 could not reach), then `refuel --speckit`, then `jj workspace list` to confirm no
workspace or stray head survives. `make ci` green before each push.
