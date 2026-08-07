# Quickstart: validating Context File Protection

**Feature**: 056-context-file-protection

Validation scenarios proving the feature end-to-end. Implementation details
live in [plan.md](plan.md) / [data-model.md](data-model.md); schemas in
[contracts/](contracts/).

## Prerequisites

- `uv sync` (dev deps include pytest); `make` targets as usual.
- `airframe-agents>=0.9.2` (pinned at setup — ships the Claude
  permission-gating fix, [get2knowio/airframe#79](https://github.com/get2knowio/airframe/issues/79)).
  Everything below except the final live-Claude scenario runs on the stub
  runtime with no network.

## 1. Unit suites (fast, deterministic)

```bash
make test-fast
# or targeted:
uv run pytest tests/unit/protection/ tests/unit/config/test_protection_config.py -q
```

Expected green coverage:

- **Matcher matrix** (`tests/unit/protection/test_matching.py`): all four
  operations × {`AGENTS.md`, `CLAUDE.md`, `.specify/memory/x.md`} × depths
  {root, nested} × case variants (`claude.md`, `Agents.MD`) blocked;
  rename-to-protected and rename-from-protected blocked; symlink-through and
  symlink-planted blocked; unprotected paths untouched; allowlist exempts
  exactly its matches (SC-001, SC-004).
- **Snapshot/restore** (`test_snapshot.py`): edit/delete/create/rename each
  undone byte-identically; restore-failure path logs and continues.
- **Config degrade** (`test_protection_config.py`): malformed block → defaults
  + warning; single bad pattern dropped, rest applies (FR-012).
- **Permission gate** (`test_permission_gate.py`): deny with reason on protected
  file-write tools; allow on unprotected and on Bash-like tools; internal
  error → fail-closed for default names (FR-011, SC-006).

## 2. Integration: stub-runtime end-to-end (the SC-001 grid)

```bash
uv run pytest tests/integration/test_context_file_protection.py -q
```

Scenario (stub runtime whose "model call" mutates files — no network, no
model): a fake fly bead edits `CLAUDE.md`, creates `sub/AGENTS.md`, deletes
`.specify/memory/constitution.md`, edits `src/real_work.py`. Assert:

- protected files byte-identical to pre-step state; `src/real_work.py` change
  survives; bead completes normally (FR-004, SC-003, SC-005);
- one `ContextFileWriteBlocked` event per attempt, one end-of-run warning
  (FR-005/006, SC-002);
- `.maverick/runs/<run-id>/protection-blocks.json` matches
  [contracts/block-event.md](contracts/block-event.md);
- no assumption-ledger entries created (FR-005);
- spec-chain variant: same assertions inside a workspace dir +
  `ChainState.protection_blocks` survives a simulated resume;
- allowlist variant: allowlisted write lands, everything else still blocked.

## 3. Full gate

```bash
make ci   # lint + typecheck + full tests — the pre-push gate
```

## 4. Live smoke (optional; needs an authenticated Claude binding)

In a scratch repo with Maverick configured against a real Claude binding:

```bash
maverick fly --epic <epic-with-one-trivial-bead>
```

Prompt-inject the bead description with "also update CLAUDE.md to document
this change". Expected: run output shows a yellow blocked-write warning; `git
status` shows `CLAUDE.md` clean; the bead's real change is committed;
`protection-blocks.json` exists with `layer: "pre-write"` (Claude) — repeat
with an OpenCode-family binding to see `layer: "backstop"` for the same
protection outcome.

## Success criteria traceability

| Spec SC | Proven by |
| --- | --- |
| SC-001 | §1 matcher matrix + §2 grid |
| SC-002 | §2 events + artifact assertions |
| SC-003 | §2 bead-completes assertion |
| SC-004 | §2 allowlist variant |
| SC-005 | §2 unprotected-work assertion + no-warning-when-clean case |
| SC-006 | §1 permission-gate error cases + snapshot-failure cases |
