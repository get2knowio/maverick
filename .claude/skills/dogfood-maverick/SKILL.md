---
name: "dogfood-maverick"
description: "Keep maverick-on-maverick dogfooding sessions disciplined: bootstrap checks, dry-run-first, live-invocation pre-flight, and a durable bugs-vs-features journal. Load this whenever a maverick CLI command is about to run against this repo for real."
argument-hint: "Optional: which track (fix/build), or a specific maverick command you're about to run"
compatibility: "This repo (get2knowio/maverick) only. Dev-only tooling — never packaged into the maverick wheel."
metadata:
  author: "get2knowio/maverick"
  scope: "repo-local, not shipped"
user-invocable: true
disable-model-invocation: false
---

## Why this exists

Maverick is now mature enough (Tier 1 of `docs/specify-prompts-orchestration-roadmap.md`
complete) that we want to try running `maverick` itself against its own repository —
instead of driving Spec Kit by hand through raw `/speckit-*` slash commands and Claude
Code as the implementer, the way every spec through 059 was built.

The moment we do that, two kinds of work start happening in the same repo at the same
time:

- **Track A — tool-fixing**: a bug or gap in maverick itself, surfaced *by* dogfooding
  it.
- **Track B — feature-building**: using maverick to build the next roadmap item (Tier 2:
  host-daemon, task-container, dispatcher, credential pooling; Tier 3; the smaller
  follow-ons).

These two tracks are easy to let blur together — a Track B `fly` run can surface a
Track A bug in `fly`'s own gate logic mid-run. Silently patching it and moving on
throws away the one thing dogfooding is actually for: the finding. This skill's only
job is to keep the two tracks apart and keep a durable record, not to do the dogfooding
itself.

**Load this skill whenever a `maverick` command is about to run against this checkout
for real (not `--help`, not reading docs).** It is not part of the actual dogfooding
work — it's the process discipline wrapped around it.

## One-time bootstrap gate

Before the *first* live `maverick` invocation in this repo, verify — don't assume —
each of the following, and **stop and confirm with the human explicitly** before doing
either of the two one-way-door actions (marked ⚠️):

1. **jj colocation**: `ls .jj/` (or `jj status` if the CLI is preferred). If absent,
   `maverick init` will run `jj git init --colocate` on the first command that needs
   it. ⚠️ **Confirm before this happens** — it changes this checkout's VCS write path
   for everything maverick touches from then on.
2. **`agents:` binding**: `maverick.yaml` currently has no `agents:` block, so every
   role (`implement`/`review`/`briefing`/`decompose`/`generate`) is unbound and any
   model-calling command fails at squadron-open. ⚠️ **Confirm the binding before
   writing it** — e.g. `provider: claude` reusing this session's own Claude Code auth,
   or something else the human prefers. Note which roles get which tier if the
   conversation calls for per-complexity routing.
3. **beads**: `bd list` / `bd where` to check whether a beads database exists yet in
   this repo. If not, note that `refuel` is expected to establish it — verify this
   against `src/maverick/workflows/refuel_speckit/` rather than assuming.
4. **Branch discipline**: confirm the working branch is a feature branch, never `main`,
   before any live command that writes.

Re-run this check at the start of every new dogfooding *session* (not every command) —
state can drift between sessions (a prior session may have partially bootstrapped and
stopped).

## Before every live (non-dry-run) invocation

1. **Say which track it's for** — Track A or Track B — before running it. If it's
   ambiguous, that's a sign to stop and figure out which one it actually is first.
2. **Prefer the read-only / dry form first** when the command has one: `--dry-run`,
   `--status`, `--json` query verbs (`land --status --json`, `delta validate`,
   `delta apply --dry-run`, etc.). Only escalate to the writing form once the dry
   form's output looks right.
3. **Prefer `fly --isolated`** for anything touching maverick's own source — the
   fold-back-on-success-only contract (spec 057) is exactly the blast-radius control
   we want while the tool is still shaking out bugs on itself.
4. **Watch the event stream live.** Don't background a long `fly`/`spec` run and walk
   away, especially in early dogfooding sessions — we don't yet have a track record of
   what "normal" looks like in this repo.
5. **Know the stop contract going in**: first Ctrl-C is graceful (finishes the current
   bead, exits clean), second is a hard cancel. Decide which one is warranted *before*
   you need it, not while panicking.
6. Context-file protection (spec 056) already blocks agent writes to `CLAUDE.md`/
   `AGENTS.md`/`.specify/memory/**` regardless of provider — a real safety net here,
   not just for end users. Don't defeat it via `protection.allowlist` for a dogfood run
   without a specific reason.

## When dogfooding finds a bug in maverick itself (Track A)

1. **Log it to the journal first** (`docs/dogfooding-log.md`, see below) — date,
   command run, repro, symptom — *before* deciding how to fix it. Even a one-line fix
   gets a journal entry. The finding is the point; skipping this because "it was
   trivial" is exactly how the evidence disappears.
2. **Decide the fix path**:
   - Small, local, obviously correct → fix directly in this session, same as any other
     bugfix, then note the fix in the journal entry.
   - Non-trivial or design-affecting → give it its own bead/spec cycle rather than an
     inline patch, same as any other feature work.
3. **Re-verify before the next live Track B invocation** if the fix touched code the
   dogfooding loop itself depends on (`workflows/fly_beads/`, `runtime/`, `squadron/`,
   `burr/`). The *currently running* process won't pick up the change mid-run (it's
   already-imported Python), but the *next* invocation will — run at least the
   targeted tests before trusting it live again.

## When using maverick to build the next feature (Track B)

Use the real tool, not a shortcut — that's the whole point:

- Spec it via `maverick spec <feature> --from-prd <file>` this time, not raw
  `/speckit-*` slash commands (that path is itself what's being dogfooded).
- `maverick refuel --speckit`, then `maverick fly --isolated`, watched live per above.
- Land through the real `maverick land` assumption-ledger gate — no "it's just a
  dogfood run" bypass. A finding that the gate itself misbehaves is a Track A bug, not
  a reason to skip it.

## The journal — `docs/dogfooding-log.md`

Committed, append-only, one entry per notable session (not per command). This is what
survives across context compaction and separate sessions — my own memory of a prior
dogfooding run doesn't persist otherwise. Create the file on first use with this shape:

```markdown
# Maverick Dogfooding Log

## 2026-08-23 — bootstrap

- Ran: `maverick init` / `agents:` block added (provider: claude, roles: ...)
- Track: bootstrap
- Result: ...
- Bugs found: none / [link]
```

Each subsequent entry: date, track(s) touched, commands run, what happened, bugs found
(with links to the bead/PR/commit that fixed them), features advanced. Keep entries
short — this is a log, not a report.
