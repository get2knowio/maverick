# Contract: CLI surface

## `maverick spec <FEATURE> --from-prd <FILE>`

New lazy-registered command (`cli/commands/spec.py`; `_LAZY_COMMANDS["spec"]`).
Note: the existing `plan` command group is unaffected; `spec` is a sibling top-level command.

### Arguments & options

| Surface | Type | Required | Meaning |
|---------|------|----------|---------|
| `FEATURE` | arg, str | yes | Feature name (slug); resume key |
| `--from-prd FILE` | path | yes for fresh runs; optional on resume (state has the digest) | PRD input |
| `--session-log FILE` | path | no | same semantics as refuel/fly |

### Preflight (fail-fast, before workspace creation)

1. `verify_bd_ready()` — bd installed + `.beads/` present (ledger/finding writes need it).
   Reuses the existing shared preflight helper (`maverick.cli.common.verify_bd_ready`,
   Guardrail 5 one-canonical-wrapper) exactly as `refuel`/`fly` do — it exits with
   `ExitCode.FAILURE` (1), **not** 2, on failure. This is a deliberate deviation from
   the general "preflight → exit 2" framing below: changing `verify_bd_ready`'s exit
   code would change behavior for every other command that shares it. The checks
   below (2–4), which are specific to `maverick spec`, use exit 2 as originally
   specified.
2. Spec Kit installed in target repo (R7 check) — else exit 2 with install guidance (FR-018).
3. PRD exists/readable/non-empty (fresh runs) — else exit 2 (FR-001).
4. Feature-name collision rules (FR-015/FR-020): halted chain for FEATURE → resume;
   completed chain / foreign `specs/` dir conflict → exit 2 with explanation.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Chain completed (analyze ran; findings recorded — findings never affect exit code) |
| 1 | Chain halted at a step (clarify failure included), **or** the shared bd preflight failed; state persisted (chain case); resume hint printed (chain case) |
| 2 | `maverick spec`-specific preflight/usage error (checks 2–4 above) — nothing started, no state written |
| 130 | Interrupted (Ctrl-C); state persisted; resume hint printed |

### Output (Rich, per CLI output rules — human-readable phases, no emoji)

- One sequential completion line per step: `✓ Specify (142.3s)` / `✗ Clarify (88.1s)`.
- Final summary (FR-019): feature dir, steps completed, clarify questions answered
  (ledger entry count), remediation beads created, and on halt:
  `Resume: maverick spec <feature>`.
- Warnings (analyze failure, PRD digest mismatch on resume) via `[yellow]Warning:[/yellow]`.

## `maverick init` (extension)

- New advisory prerequisite: Spec Kit presence (`.specify/` + supported `speckit_version`).
- Interactive TTY + missing → Click confirm offer; accept runs the pinned installer via
  `CommandRunner`; decline → notice, init still exits 0 (FR-017).
- Non-interactive → notice only. Re-init idempotent: present+compatible → silent pass;
  present+incompatible version → warning with supported range.
- `InitResult` gains `speckit_installed: bool | None` (None = not applicable/declined).
