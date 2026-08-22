# Research: Standalone Code Review (`maverick critique`)

**Feature**: 058-standalone-code-review
**Date**: 2026-08-22

Every finding below was verified against the tree at `9de3a34`. Where a
decision rejected an alternative, the rejected option and its reason are
recorded — a later reader should not have to re-derive why.

---

## R1 — How to build the reviewer pair without forking it

**Question**: FR-007 forbids a second reviewer implementation. What is the
smallest correct way for a non-Burr CLI command to obtain the same two
reviewer lenses `fly` uses?

**Findings**:

- `ReviewerAgent` (`src/maverick/agents/reviewer.py:35`) is already
  persona-per-instance — `persona_name` is a constructor kwarg, deliberately
  not a `ClassVar` (`reviewer.py:40`). Nothing about it is fly-specific.
- The *only* construction site in `src/` is
  `FlySquadron._build_reviewer_pair` (`src/maverick/squadron/fly.py:95-127`).
  It makes two independent `runtime_for_agent("review", ...)` calls — one
  runtime per agent, never shared — and splats
  `**self._agent_protection_kwargs()` (`squadron/base.py:178-192`).
- With `reviewer_tiers=None`, `FlySquadron` builds exactly one pair under
  `DEFAULT_TIER` (`fly.py:145-161`), and `binding_for_complexity` returns
  `None` for `DEFAULT_TIER` (`squadron/tiers.py:68-87`), so the pair resolves
  to the role's base `agents.review` binding.

**Decision**: extract `fly.py`'s pair construction into a shared
`src/maverick/squadron/reviewers.py::build_reviewer_pair(...)`, and add a
thin `CritiqueSquadron` that builds exactly one pair from it.

**Rejected — reuse `FlySquadron` directly**: it also builds a `CodingAgent`,
which requires an `agents.implement` binding. A read-only review command
would then fail to start on a repository configured only for review. Wrong
failure mode, and it makes the command's dependency footprint a lie.

**Rejected — the ad-hoc pattern from `land.py:574-621`** (two
`runtime_for_agent` calls + `build_ad_hoc_protection` + direct construction):
correct, and it is the precedent for one-off agents, but it would be the
*second* copy of the pair-construction sequence. Debt Prevention rule 5 says
refactor to a shared utility on the second use. `CritiqueSquadron` also gets
cost telemetry and coordinated `open()`/`close()` for free.

---

## R2 — The reviewer prompt for a scope that is not a bead

**Question**: `ReviewerAgent` has two prompt builders — `review()` (per-bead,
stateful across fix rounds) and `aggregate()` (epic, one-shot). Neither fits
"review this diff / these paths".

**Findings**:

- `review()`'s round-1 prompt (`reviewer.py:150-170`) opens "Review the
  implementation already in the working directory **against the spec below**"
  and requires a work-unit or bead description. There is no spec in a
  standalone critique.
- `review()` is stateful: `self._review_count` makes round 2+ send "did you
  address my prior findings?" (`reviewer.py:171-176`). Reusing it for a
  one-shot command works only by accident of the counter starting at zero.
- `aggregate()` (`reviewer.py:112-128`) is the right *shape* — it rotates the
  session first, sends one prompt, returns one payload — but its prompt is
  hardcoded to cross-bead concerns and explicitly says "Do NOT re-review
  individual bead correctness".

**Decision**: add a third method, `ReviewerAgent.critique(scope_summary,
change_summary)`, that rotates the session and sends a scope-oriented prompt.
Same class, same `result_model`, same personas, same provenance stamping.

This is not a second implementation. FR-007 forbids a second reviewer
*agent*, prompt *family*, and result *shape*; a third prompt on the one
reviewer, returning `SubmitReviewPayload`, is none of those. The alternative —
bending a bead-shaped prompt around a diff — produces worse reviews and
couples the command to a counter it does not own.

---

## R3 — Locating an epic's commits

**Question**: FR-010 says resolve an epic scope "through the bead identity
recorded on those commits". What is actually recorded, and what can read it?

**Findings**:

- Bead commits are written with both a subject prefix and a trailer:
  `build_bead_commit_message` (`workflows/fly_beads/_commit.py:31`) produces
  `bead(<id>): <title>\n\nBead: <id>`.
- A second, unconsolidated writer exists on the DSL step path
  (`workflows/fly_beads/actions.py:1709-1714`) which may insert a `Tag:` line
  between the subject and the `Bead:` trailer.
- **The `Bead:` trailer is write-only today.** Nothing in `src/` parses it —
  `grep -rn "interpret-trailers" src/` hits only a docstring. The one reader
  of bead identity is land curation, and it parses the *subject prefix*:
  `_BEAD_PREFIX_RE = re.compile(r"^bead\(([^)]+)\):", re.MULTILINE)`
  (`library/actions/curation.py:43`), exposed as
  `extract_bead_ids(commit_description)` (`curation.py:133`).
- Neither log helper exposes a commit *body*: `GitRepository.log()` returns
  `CommitInfo` whose `message` is the first line only
  (`git/repository.py:401`), and `JjClient.log()`'s template uses
  `description.first_line()` (`jj/client.py:638`).

**Decision**: resolve epic commits by subject prefix via the existing
`extract_bead_ids`, intersected with the epic's bead ids from
`BeadClient.children(epic_id)` (`beads/client.py:414`).

**Rejected — read the `Bead:` trailer**: it would require a new full-body log
accessor on either VCS helper, and the trailer is demonstrably less reliable
than the subject today (the second writer's `Tag:` interleaving, and no
existing reader to regression-test against). The subject prefix is what the
curator contract already depends on
(`agents/system_prompts/maverick.curator.md:20,42-43`), so it is the
load-bearing identity in practice. Recorded here so a future reader knows the
trailer was considered and why it lost.

---

## R4 — Combining a set of non-contiguous commits into one reviewable change

**Question**: an epic's commits need not be contiguous. What is "the combined
difference those commits introduced" (Story 2 scenario 1)?

**Options considered**:

| Option | Behavior | Verdict |
| --- | --- | --- |
| `diff(oldest^..newest)` | One range diff | **Rejected** — silently includes every unrelated commit interleaved in the range. Presents other people's work as the epic's. |
| Concatenate per-commit diffs (`diff(sha^, sha)` each) | Exactly the epic's changes, in order | **Chosen** |
| Three-dot merge-base diff | Same over-inclusion problem plus a merge-base that may not exist | Rejected |

**Decision**: concatenate per-commit diffs, each headed by its short SHA and
subject. The union of touched files is computed alongside and is what drives
the terminal grouping.

---

## R5 — Bounding an enormous scope

**Question**: the spec's edge case requires explicit truncation *or* refusal,
never silence. Which, and at what bound?

**Findings**: the reviewer agent has working-directory file access — the
existing round-1 prompt relies on it ("Review the implementation already in
the working directory"). The embedded diff is therefore an *aid*, not the
agent's only source of truth.

**Decision**: always embed the full changed-file list and the diff stat
(both small and bounded by file count, not content size); embed the unified
diff up to `MAX_EMBEDDED_DIFF_CHARS = 200_000`. On truncation, say so
explicitly in the prompt, in the terminal output, and in the persisted
artifact, and tell the agent to read the remaining files directly.

Truncation is therefore never silent and never blinding — the agent retains a
complete list of what changed and the means to read all of it. Refusal was
rejected because the failure it prevents (a partial review presented as
complete) is already prevented by explicit reporting, and refusing would make
the command useless on exactly the large changes most worth reviewing.

---

## R6 — Default base revision

**Findings**: there is no trunk-resolution helper anywhere —
`grep -rn "trunk" src/` returns zero hits. The established convention is a
hardcoded `"main"` default threaded as a parameter:
`curate_history(base_revision: str = "main")` (`library/actions/jj.py:635`),
`gather_curation_context(...)` (`jj.py:746`), surfaced as
`maverick land --base` with `default="main", show_default=True`
(`cli/commands/land.py:77-81`).

**Decision**: `--base` defaulting to `main`, matching `land` exactly. A user
whose trunk is named otherwise passes the flag, same as they already do for
`land`. Introducing dynamic trunk detection here would make `critique` and
`land` disagree about what "base" means, which is worse than both being
explicit.

---

## R7 — Findings merge and provenance

**Findings**: fly does **not** merge payloads. It keeps a 2-tuple and derives
two scalars: approval as an AND over `_payload_approved`
(`workflows/fly_beads/actions.py:1433-1447`, used at `:1093`), and findings
flattened to `f"{severity}: {issue}"` strings by `_findings_list`
(`actions.py:1450-1475`). That flattening **drops the `reviewer` provenance
field** the agent just stamped.

**Decision**: critique keeps findings structured (`ReviewFindingPayload`)
end to end — FR-008 requires retaining the lens, and the persisted artifact
and `--json` mode both need severity/file/line as fields, not prose.

`_payload_approved` is genuinely shared logic, so it moves to
`maverick.payloads::review_payload_approved` and fly imports it from there.
`_findings_list` stays in fly — string flattening exists only to build the
implementer's fix prompt, which critique has no equivalent of (FR-013).

**Cross-lens de-duplication is deliberately not performed.** Two lenses
flagging the same line is signal, not noise (spec edge case). Both rows are
rendered, each attributed.

---

## R8 — Discovered defect: the aggregate review's diff stat

**Finding**: `_safe_diff_stat` (`workflows/fly_beads/actions.py:2097-2106`)
runs `git diff --stat HEAD~1..HEAD` — the single most recent commit. It feeds
`reviewer.aggregate(...)`, whose prompt says "Review the AGGREGATE changes
across all beads in this epic" (`agents/reviewer.py:186`), and the action only
runs when at least `AGGREGATE_REVIEW_THRESHOLD = 2` beads completed
(`actions.py:2030,80`).

So the aggregate review is handed a bead list naming N beads and a diff stat
covering one commit. It has been reviewing the last bead while being told it
is reviewing the epic.

**Decision**: fix it as part of this feature. R3+R4 build exactly the epic →
commits → combined-change resolver that `_safe_diff_stat` needed and did not
have; leaving fly on the broken one-commit stat while shipping the correct
resolver next door would be knowingly leaving a defect in place. Task T031
swaps `_safe_diff_stat` to the shared resolver with its own regression test.

Related, not fixed here (recorded so it is not lost): the same one-commit
assumption appears in `_vcs_queries.py:33` (`_get_files_changed`), and
`mid_flight.py:120` uses `JjClient.diff_stat` where `actions.py` uses `git
diff` — two diff-stat sources in one package. Neither is in this feature's
blast radius; both belong to a follow-up that consolidates fly's VCS reads.

---

## R9 — CLI shape

**Findings** (all from `cli/commands/notify.py`, the newest `--json` command):

- Registration is a lazy pointer in `_LAZY_COMMANDS`
  (`main.py:43-96`), value `("pkg.module:attr", short_help)`.
- Decorator order is `@click.command` → options → `@click.pass_context` →
  `@async_command` innermost (`notify.py:557-590`).
- `cwd = Path.cwd().resolve()` at the command body; there is no `--cwd`
  option anywhere (`notify.py:591`, `land.py:172`, `reconcile.py:405`).
- Config: `config = (ctx.obj or {}).get("config") ... or load_config()`
  (`notify.py:592-594`).
- The body is a thin dispatcher to `_run_*_json` / `_run_*_human` siblings,
  wrapped in `json_error_handler(verb)` and `cli_error_handler()`
  respectively (`notify.py:449`, `:542`).
- Every JSON terminal path is `emit_json(...)` then `raise SystemExit(...)`,
  never `return` (`notify.py:439-470`).
- Progress goes to `err_console` in JSON mode:
  `out = err_console if json_output else console` (`land.py:174-178`).
- Free text from agents is escaped with `rich.markup.escape` before
  rendering (`review/listing.py:148-157`, `land_gate.py:275-288`).

**Decision**: follow all of it exactly. `critique` is added to
`_LAZY_COMMANDS` but **not** to `commands_needing_config`
(`main.py:188-189`) — a missing `agents.review` binding should fail with the
binding error, not a config-file error — and not to `commands_needing_git_gh`
(it needs git, but read-only, and `gh` not at all).

---

## R10 — Run directory and artifact persistence

**Findings**:

- Run ids are `uuid.uuid4().hex[:8]`, minted at the CLI boundary
  (`land.py:174`, `reconcile.py:438`).
- The json+md artifact pair pattern is `persist_report`
  (`assumptions/land_report.py:280-293`): `atomic_write_json` +
  `atomic_write_text` from `utils/atomic.py`, which creates parents itself.
- Persistence failure is degraded to a warning by the caller, never a gate
  failure — `persist_report_json` (`cli/commands/land_gate.py:223-241`)
  returns `(paths, degraded)` with `None` paths on failure.
- Report models are frozen slotted dataclasses with `"schema_version": 1` as
  the first key of `to_dict()`, absent keys omitted rather than emitted as
  null (`land_report.py:114-181`), and a separate pure `render_markdown`.

**Decision**: mirror it exactly —
`.maverick/runs/<run-id>/critique-report.{json,md}`, `schema_version: 1`,
persistence failure → warning on `err_console`, exit code untouched
(FR-018).

---

## R11 — Failure taxonomy

FR-021 forbids adding a classification where an existing one fits. Mapping:

| Condition | `ErrorKind` |
| --- | --- |
| Conflicting scopes; unreadable `--fail-on`; path outside the repository | `VALIDATION` |
| Named path does not exist | `VALIDATION` (it is a bad argument, not a missing resource) |
| Named epic does not exist | `NOT_FOUND` |
| `bd` unavailable (epic scope only) | `BD_UNAVAILABLE` |
| Git read failure resolving the scope | `VCS` |
| Both lenses failed | `INTERNAL` |

No new `ErrorKind` value. Note `BD_UNAVAILABLE` is reachable only on the epic
scope — the diff and path scopes never touch `bd`, so a repository without
`bd` can still run the default invocation.
