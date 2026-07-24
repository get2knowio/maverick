# Quickstart Validation: Headless Spec Kit Chain

Runnable scenarios proving the feature end-to-end. Contracts:
[cli-spec.md](contracts/cli-spec.md), [chain-state.md](contracts/chain-state.md),
[ledger-and-beads.md](contracts/ledger-and-beads.md); entities in
[data-model.md](data-model.md).

## Prerequisites

- A Spec Kit-initialized target repo (e.g. `/workspaces/sample-maverick-project`) with
  `maverick init` run (jj colocated, `.beads/` present) and a configured `generate`
  provider binding in `maverick.yaml`.
- A sample PRD, e.g. `docs/sample-prd.md` (any non-empty markdown works; a deliberately
  vague PRD exercises clarify).

## Scenario 1 — Full chain, hands-off (US1, SC-001)

```bash
cd /workspaces/sample-maverick-project
maverick spec demo-feature --from-prd docs/sample-prd.md
echo $?          # expect 0
```

Expected: five sequential step-completion lines, no interactive prompt at any point;
`specs/NNN-demo-feature/` exists in the checkout containing `spec.md`, `plan.md`,
`tasks.md` (plain markdown, `git status` shows them as ordinary untracked files);
summary reports ledger-entry and remediation-bead counts.

## Scenario 2 — Clarify decisions on the record (US2, SC-002)

```bash
maverick brief            # per-spec assumption counts include NNN-demo-feature
bd list --label assumption --json | jq '.[].state.assumption_owner_spec'
maverick review <entry-id>   # answer/waive flow works on a chain-filed entry
```

Expected: every clarify question from Scenario 1 has one open ledger entry
(question/adopted/alternatives/severity in the bead description+state); severities are
`low` unless the question was scope/security-impacting.

## Scenario 3 — Halt on failed clarify + resume (US3, FR-009/FR-020)

```bash
# Induce failure: run with the clarify step forced to fail (test hook / invalid
# provider binding swap after specify), or Ctrl-C during clarify.
maverick spec demo-two --from-prd docs/sample-prd.md   # exits 1 (or 130 on Ctrl-C)
test -f specs/*demo-two*/spec.md && ls specs/*demo-two*/plan.md 2>&1  # spec.md yes, plan.md absent
cat .maverick/runs/*/spec-chain.json | jq 'select(.feature=="demo-two") | .status, .steps'
maverick spec demo-two --from-prd docs/sample-prd.md   # resumes at clarify, no re-specify
```

Expected: halt report names clarify; plan/tasks/analyze never ran; resume skips specify
(no regeneration) and continues.

## Scenario 4 — Analyze findings become beads, never blockers (US4, SC-004)

```bash
bd list --label spec-remediation --json | jq '.[].state.speckit_feature'
maverick refuel demo-feature --speckit
bd show <remediation-id>    # now parented/adopted under the demo-feature epic
```

Expected: chain exit was 0 regardless of findings; each finding is one bead keyed
`speckit_feature=NNN-demo-feature`; refuel adopts them under the new epic.

## Scenario 5 — Init verification (US5)

```bash
cd <repo-without-speckit> && maverick init      # offers Spec Kit install
# decline → init exits 0 with notice; then:
maverick spec x --from-prd README.md            # exits 2 with install guidance
```

## Automated coverage

- `make test-fast` — unit suites for state/models/clarify/landing/ledger extension.
- `make test-integration` — full-chain scenario against stubbed airframe runtimes in a
  tmp jj+git repo fixture (asserts Scenarios 1–4 invariants without live models).
- `make ci` — pre-push gate, includes format check.
