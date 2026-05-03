# Maverick Architecture: Pull-Work-Push Model

**Status:** Draft specification. Captures the architectural model converged on through discussion 2026-05-02, revised 2026-05-03 across multiple passes to incorporate: two-plane model (code + beads); publish-only branches; continuous-sync forward-compatibility constraints; bead-graph-as-durable-structure (initiative concept dropped; single working branch per project); epics-as-landable-seams (no separate boundary bead type); four-state bead machine (`open / in-progress / implemented / closed`); env-aware ready check; multi-PR-per-epic as interim land semantics with wip-ref consolidation as the future upgrade path; explicit acknowledgment that pour-during-grab concurrency is a continuous-sync future, not a near-term reality; **two publishing verbs** — `maverick commit` (raw, for structural artifacts; restored after a previous over-correction had removed it) and `maverick land` (curated, for fly's implementation slab) — restoring per-subcommand pull-work-push self-containment so any workflow can run on a different env than its predecessor. Replaces the current "user checkout + hidden workspace" pattern.

---

## 1. Goals

This specification addresses three problems with the current architecture:

1. **State divergence between user checkout and hidden workspace.** Maverick currently maintains two copies of project state — the user's local clone and a hidden `~/.maverick/workspaces/<project>/` jj clone. They drift apart whenever workflow output isn't perfectly round-tripped, producing the cluster of bugs we hit during the 2026-05-02 e2e session (workspace identity mismatch, sync.remote routing stale dolt, commit-hook clobbering JSONL).

2. **Brittleness around `init`.** Today's `init` writes config that downstream commands then have to repair (`model.model_id: sonnet` failing doctor, missing `.maverick/workspace.json` gitignore entry, bd's auto-set `sync.remote` derailing workspace bootstrap). Init doesn't deliver a state subsequent commands can rely on; every command has to be defensive.

3. **Misalignment with the multi-agent future.** The long-term goal is multiple maverick environments collaborating on the same project — different agents, different machines, sharing bd federation state. The current architecture has no clean path there.

### Status (2026-05-03)

The 044-opencode-substrate branch landed a deliberately minimum slice — collapse Maverick to single-repo (CWD-based) operation so the OpenCode substrate is e2e-testable today — that incidentally chips against the goals above:

- **Goal 1 (state divergence)** — structurally moot for now. There is only one copy: the user's CWD. The hidden `~/.maverick/workspaces/<project>/` clone pattern is gone (`cf11db4`). When the architecture's per-environment `~/.maverick/<project>/` materializes, Goal 1 returns as a property to preserve, not a bug to fix.
- **Goal 2 (init brittleness)** — the three specific bugs named here are all fixed on this branch (`0ae955d`): the legacy `model.model_id: sonnet` write is removed; `_strip_bd_sync_remote()` neutralizes bd's auto-set `sync.remote`; `_untrack_bd_local_state()` removes `.beads/backup/` from tracking. The fourth named bug — missing `.maverick/workspace.json` gitignore entry — is moot because the marker file no longer exists. Init's broader pull-work-push restructuring (item 8 in §13) is untouched.
- **Goal 3 (multi-agent future)** — untouched. Single-CWD operation is, if anything, a step away from the per-env target. The architecture work still needs to happen.

---

## 2. Mental model

**A maverick project** is a GitHub repository that has been configured for use with maverick (has `maverick.yaml`, has bd federation initialized).

**A maverick environment** is a machine that runs maverick commands. An environment has a local working directory per project at `~/.maverick/<project>/`.

**Every maverick command is an instance of pull-work-push**:

1. **Pull** the current state from GitHub into the local working directory.
2. **Work**: do the command's specific job locally (write files, generate beads, implement code).
3. **Push** the resulting state back to GitHub — heterogeneous by plane (see below).

The local working directory is **maverick's, not the user's**. There is no separate "user checkout" — the user does not `cd` into a project directory to use maverick. They invoke maverick commands from anywhere, and maverick maintains its own local materialization of the project.

> **2026-05-03 status:** This still describes the eventual state. On `044-opencode-substrate` the user *does* `cd` into a maverick-managed git repo and that CWD *is* the working directory — every workflow runs in `Path.cwd()` (`cf11db4`). The CWD-based interim is **not** the goal; it is the operating reality until the per-environment `~/.maverick/<project>/` materialization in §4–5 is built. Treat any CLAUDE.md text about "user invokes from anywhere" as aspirational on this branch.

### Two sync planes

Code and beads live in different ref namespaces and sync independently:

| Plane     | Where it lives                    | Who pushes, when                              |
|-----------|-----------------------------------|-----------------------------------------------|
| **Code**  | git refs (`refs/heads/...`)       | `maverick commit` (raw push) or `maverick land` (curated push + PR). Fly never pushes code directly; structural workflows (plan generate, init) may auto-invoke `maverick commit` at completion. |
| **Beads** | bd federation (dolt refs)         | Bead-producing workflows (refuel, fly's claim and implemented transitions) push inline as part of their normal operation. |

This is asymmetric on purpose: bead state is the coordination plane and must replicate continuously; code is the publishing plane and replicates only when a workflow's artifact is durably ready (structural commit) or when the user explicitly publishes a curated slab (land).

### Design commitments

These principles bound every architectural decision below. Future contributors: violating any of these is a signal to redesign, not to special-case.

1. **Branches are publish-only.** Agents do not coordinate via branches. Branches exist so humans can review on GitHub. Any pattern that uses a branch as a hand-off mechanism between agents is wrong.
2. **Bd federation is the only coordinator.** All claims, locks, and arbitration go through bd metadata. No file locks, advisory branches, in-memory queues, or external services.
3. **Single source of truth per data type.** Code lives in the local jj working tree. Bead state lives in bd federation. Workflow scratch lives in `.maverick/.cache/` (local-only, never replicated). No reconciliation logic between these.
4. **Every subcommand is self-contained pull-work-push.** Each workflow pulls fresh state, does its work, and pushes its durable artifact so that any other env can pick up from the result. Fly is the deliberate exception: its implementation commits stay local because they need curation before going to GitHub. Code reaches GitHub through `maverick commit` (raw push, used inline by structural workflows like plan generate and init) or `maverick land` (curated push + PR, used for fly's accumulated slab).
5. **Curator rewrites shape, not content.** Squash, reorder, and message-rewrite are safe. Editing file content during land is forbidden — it invalidates assumptions in other agents' working state and in already-merged work.
6. **Polling is hidden behind a subscription-shaped API.** Agent code consumes ready beads via an iterator (`async for bead in coordinator.ready_beads()`). Implementation may be `bd federation pull` on a timer today; the agent contract doesn't change when it becomes a real subscription.

---

## 3. Why pull-work-push is universal

Every meaningful operation maverick performs fits this pattern:

| Command         | Pull                              | Work (command-specific)                                          | Push                                                |
|-----------------|-----------------------------------|------------------------------------------------------------------|-----------------------------------------------------|
| `init`          | clone repo + bd federation        | scaffold maverick.yaml + bd config                               | structural commit (auto-invoked) + adopt-maverick PR  |
| `plan generate` | clone + federation                | read PRD, run briefing/structuralist/recon agents, write flight plan | flight plan committed locally; `maverick commit` auto-invoked at completion to push to `maverick/<project>` |
| `refuel`        | clone + federation                | decompose plan into beads                                        | bd federation push (inline; no code)                |
| `fly`           | clone + federation                | implement beads as local jj commits; never touch GitHub          | bd federation push for claim and implemented transitions only (close happens on PR merge) |
| `commit`        | clone + federation                | none — pure publish step                                         | push local jj commits on `maverick/<project>` to remote, as-is, no curator |
| `land`          | clone + federation                | curator rewrites local implementation slab; open PR              | curated code push to `maverick/<project>` + open or update PR |

The differences are confined to step 2. Step 3's shape varies by plane and artifact type: bead-producing workflows push bd federation inline; structural code artifacts (flight plans, configs) reach GitHub via `maverick commit`; fly's implementation slab waits in local jj for `maverick land` to curate and PR.

> **2026-05-03 status — interim deltas vs. the table above:**
>
> - **Pull column** is uniformly "operate on `Path.cwd()` (the user's checkout)" today. There is no clone step; bd federation pull happens inside individual workflows where it always did, not as a harness step. (`cf11db4`)
> - **Push column for code is "user pushes manually"** for everything except `fly --auto-commit`, which now snapshots local changes via the vcs-neutral `snapshot_uncommitted_changes()` helper — jj-snapshot on jj checkouts, plain `git add -A && git commit` on git-only checkouts (`82fcedd`). `maverick commit` does not exist; `maverick land` exists but does not push or open PRs (it curates locally and prints next-step hints — see §6). Structural workflows (plan generate, init) do not auto-publish.
> - **Push column for beads** matches the table — bd federation pushes happen inline in refuel/fly today and have for some time.
> - **Bead trailer** in fly's commit message is now wired (`82fcedd`): subject `bead(<id>): <title>` plus a blank line plus `Bead: <id>` git trailer. This is forward-compat groundwork for the env-aware ready check; nothing reads the trailer yet.

---

## 4. Directory layout

### Per environment

```
~/.maverick/
└── <project>/                       ← one directory per project, lazy-created
    ├── (project files, normal git checkout from GitHub)
    ├── .git/
    ├── .maverick/
    │   ├── plans/<plan-name>/       ← persistent (will be pushed)
    │   │   ├── flight-plan.md
    │   │   ├── work-units/
    │   │   └── ...
    │   ├── runway/                  ← persistent (will be pushed)
    │   └── .cache/                  ← gitignored (per-command scratch)
    │       ├── refuel/<plan>/
    │       ├── fly/<epic>/
    │       └── ...
    └── .beads/                       ← bd state, federated via dolt
```

### Project naming

The directory under `~/.maverick/` is named by the GitHub repo's slug (e.g., `~/.maverick/get2knowio-sample-maverick-project/`) or by a user-friendly project name. Naming convention to be pinned down during implementation; it must be unambiguous when the same machine has multiple projects.

### What's tracked vs. cached

| Path                                  | Status                | Lifecycle                                              |
|---------------------------------------|-----------------------|--------------------------------------------------------|
| `<project>/`                          | git/jj working tree   | refreshed via `git fetch`; never destructively reset    |
| `<project>/maverick.yaml`             | tracked               | persistent project config                              |
| `<project>/.maverick/plans/`          | tracked               | persistent — flight plans, work-unit specs             |
| `<project>/.maverick/runway/`         | tracked               | persistent knowledge store                             |
| `<project>/.maverick/.cache/`         | **gitignored**        | per-command scratch; survives across runs for resumption |
| `<project>/.beads/issues.jsonl`       | tracked               | persistent bd state snapshot                           |
| `<project>/.beads/embeddeddolt/`      | gitignored            | local dolt working dir                                 |
| `<project>/.beads/backup/`            | gitignored            | local bd backup                                        |
| `<project>/.beads/metadata.json`      | tracked               | bd federation identity                                 |

The `.maverick/.cache/` line is the only gitignore addition this architecture requires beyond bd's stock template.

---

## 5. The pull-work-push cycle

> **2026-05-03 status:** No harness exists today. Each workflow opens a fresh xoscar pool inside `Path.cwd()` (`cf11db4`), runs its actors, and exits. There is no shared lazy-create / fetch / cache-resumption wrapper. Cache-style scratch in `.maverick/.cache/` exists per-workflow but is not orchestrated by a harness. The text below describes target behavior; treat the wrapper-pseudocode as a build target, not a description of running code.

### Universal harness

Every workflow command runs through this wrapper:

```
1. Ensure local directory:
       if ~/.maverick/<project>/ doesn't exist:
           git clone <github-url> ~/.maverick/<project>/

2. Sync with remote (NO destructive reset):
       cd ~/.maverick/<project>/
       git fetch origin

3. Run the command's work in this directory.
   The workflow:
       - May read .maverick/.cache/<command>/ for resumption hints from a prior failed attempt.
       - Writes new state to .maverick/.cache/<command>/ as it goes.
       - Writes persistent artifacts to their durable locations:
           * Flight plans, work units → tracked files in .maverick/
           * Code changes → local jj commits (never pushed)
           * Bead state → bd federation (pushed inline by bd as part of normal operation)

4. Exit with status code.
   - Status 0: work durably persisted (local jj commits + cache + bd federation).
   - Status != 0: work incomplete; cache and partial state remain for inspection.
```

The harness never pushes code itself. Code publishing happens through `maverick commit` (raw push, often auto-invoked by structural workflows at their end) or `maverick land` (curated push for implementation slabs). Bd federation pushes happen inline as part of bd-touching workflows; the harness is not involved.

### Why no automatic destructive reset

Earlier drafts had the harness do `git reset --hard origin/<branch>` on every command. That was wrong: it would destroy uncommitted work from a failed prior attempt. Under this architecture, **prior failed work is preserved** so the next attempt can resume.

If a workflow needs a clean slate, it asks the harness for one explicitly (a `reset_to_remote()` helper). Default behavior is "fetch and let the workflow handle local divergence."

### Why no `runs/<uuid>/` tracking

Each command operates on a single per-project directory. There is no cross-run state to enumerate. A "run" is a verb — what happens between `git fetch` and the next workflow's start — not a noun that needs tracking. Failure inspection happens by `cd`-ing into the project directory; there's no run-history index to maintain.

---

## 6. Command surface

> **2026-05-03 status (per-verb):**
>
> | Verb | Exists? | Behaves as described? | Interim delta |
> |---|---|---|---|
> | `init` | yes | partial | Runs in user CWD. Writes `maverick.yaml`, initializes bd, runs init helpers — but does **not** push, does **not** open an "Adopt maverick" PR, does **not** materialize a per-env directory. (`0ae955d`, `cf11db4`) |
> | `plan generate` | yes | partial | Runs in `Path.cwd()`. Writes flight plan locally. Does **not** auto-invoke `maverick commit` at completion (no such verb). User pushes manually. (`cf11db4`) |
> | `refuel` | yes | partial | Runs in `Path.cwd()`. Bd federation push happens inline as before. (`cf11db4`) |
> | `fly` | yes | mostly | Runs in `Path.cwd()`. `--auto-commit` now works on plain-git checkouts via `snapshot_uncommitted_changes()` (`82fcedd`). Commits carry the `Bead: <id>` trailer (`82fcedd`). Three-state bd machine still in use; the four-state `implemented` split is unbuilt. |
> | `land` | yes | minimal | Curates locally, then prints mode-specific next-step hints. `--approve`/`--eject`/`--finalize` flags exist but collapse to "curate, then advise" — no automated push, no PR creation. (`cf11db4`) |
> | `commit` | **no** | n/a | Verb does not exist. Pushing is manual. |
> | `migrate` | **no** | n/a | Verb does not exist. Early adopters with orphaned `~/.maverick/workspaces/<project>/` directories must `rm -rf` manually (see §12). |
> | `workspace status\|clean` | **removed** | n/a | Command group de-registered in `main.py` and the package deleted (`cf11db4`). |
> | `brief`, `doctor`, `runway`, `use`, `reclaim` | brief/doctor/runway exist; `use` and `reclaim` do not | partial | brief/doctor/runway operate on CWD. |

### Workflow commands

```bash
maverick init <github-url>
maverick plan generate <name> --from-prd <path>
maverick refuel <plan>
maverick fly --epic <id> [--watch] [--max-beads <n>]
```

Each does its work in `~/.maverick/<project>/` and exits. None push code. `refuel` and `fly`'s claim/close transitions push bd federation inline. `fly --watch` keeps polling bd federation for new ready beads (via the subscription-shaped iterator) and exits gracefully on signal.

### Publishing commands

```bash
maverick commit [-m "msg"]
maverick land   [--epic <id>]
```

These are the two commands that push code to GitHub. They differ by whether the curator runs:

**`maverick commit`** — pushes local jj commits on `maverick/<project>` to the remote, as-is. No curator. No PR. Used for structural artifacts (flight plans, configs, bootstrap files) where shape rewriting isn't useful and the artifact wants to reach GitHub immediately so that another env can pull it. Structural workflows (plan generate, init) auto-invoke `maverick commit` at completion by default; `--no-commit` opts out for inspection.

**`maverick land [--epic <id>]`** — runs the curator over the local implementation slab, rebases onto `maverick/<project>`, pushes, opens or updates a PR, and tracks bead state through PR merge. Used for fly's accumulated implementation work. `land` does, in order:

1. Read the local jj history slab (commits the current env produced since the last `commit`/`land`).
2. Run the curator agent to rewrite the slab into a presentable shape (squash, reorder, message-rewrite — never content edits).
3. Rebase the curated slab onto `origin/maverick/<project>` and push.
4. Open or update a PR `maverick/<project>` → `main`.
5. Mark the bundled beads `closed` when the PR merges (via webhook or poll).

Default cut for land: HEAD at land time. `--epic <id>` cuts at the commit where epic `<id>`'s last bead reached `implemented`.

The two verbs split cleanly by use case: commit is for the per-subcommand pull-work-push push-step (every workflow's natural ending if it produced a tracked artifact); land is the deliberate curated-publish moment for implementation work.

### Read-only commands

```bash
maverick brief                        # bead status + local commit slab not yet landed
maverick doctor                       # diagnostic
```

### Auxiliary

```bash
maverick runway seed|consolidate      # knowledge store maintenance
maverick use <github-url>             # set active project for subsequent commands
maverick reclaim <bead-id>            # manual recovery of a stale claim (see §11)
```

`maverick use` is optional — workflow commands take a `--project <github-url>` flag, defaulting to the most-recently-used project if omitted.

### Total surface

Nine user-facing verbs (init, plan, refuel, fly, commit, land, brief, doctor, runway), plus the auxiliaries `use` and `reclaim`. No `clone`, no `attach`, no `workspace`, no `adopt` — those concepts collapse into other commands or are implementation details of the pull-work-push cycle.

---

## 7. The `init` contract

> **2026-05-03 status:** Init does most of what's described — writes `maverick.yaml`, initializes bd, scaffolds `.maverick/` — but operates **in the user's CWD**, not in `~/.maverick/<project>/`. Init does not push, does not open an "Adopt maverick" PR, and does not take a `<github-url>` argument; it adopts whatever git repo the user is `cd`'d into. The three brittleness bugs called out in §1 are fixed (`0ae955d`): no `model.model_id` write, `sync.remote` neutralized, `.beads/backup/` untracked. The broader pull-work-push restructuring (item 8 in §13) is unbuilt.

After `maverick init <github-url>` completes successfully:

1. The repo at `<github-url>` is a valid maverick project — `maverick.yaml` is committed, bd federation is initialized.
2. This environment has `~/.maverick/<project>/` populated and current with GitHub.
3. `maverick doctor` returns 0.
4. Every workflow command's preflight check passes without manual intervention.

`init` is the only command that creates structural state in GitHub (commits `maverick.yaml`, initializes bd federation). All other commands operate against a project that is already initialized.

### Behavior by repo state

| Repo state                                       | What `init` does                                         |
|--------------------------------------------------|----------------------------------------------------------|
| Repo exists on GitHub, no maverick state          | Scaffold maverick.yaml + bd config, push as PR titled "Adopt maverick"  |
| Repo exists on GitHub, has maverick state         | Refresh local working directory; idempotent no-op on the GitHub side    |
| Repo doesn't exist on GitHub                      | Error: "create the GitHub repo first (`gh repo create foo/bar`), then re-run." |

### What `init` does NOT do

- Does not create GitHub repos. Use `gh repo create` first.
- Does not configure user-level state (auth, prefs) — those are separate user-level commands not yet specified.

`init` produces structural artifacts (`maverick.yaml`, bd config) and uses `maverick commit` semantics to push them, plus opens an "Adopt maverick" PR via gh. It is a one-shot operation per project; subsequent runs of `init` against an already-initialized project are idempotent no-ops. Init's PR-opening is the only exception to "PRs come from `land`" — see H5 for whether to keep that exception or fold it through `land`.

---

## 8. Workflow handlers

### Interface

A workflow handler is a function:

```python
def workflow(project_dir: Path, args: WorkflowArgs) -> int:
    """
    Run the workflow's work in `project_dir`.
    Returns exit status: 0 if work durably persisted, non-zero if incomplete.
    """
```

The harness calls the handler after pull (step 1-2). On success, the handler has persisted its outputs (local jj commits + bd federation pushes inline + tracked files in `.maverick/`). On failure, the harness leaves everything in place for inspection and resumption.

### Handler responsibilities

- **Read inputs** from `args` (PRD path, plan name, epic id, etc.) and from the local project directory state.
- **Check cache** at `.maverick/.cache/<command>/<primary-input-key>/` for resumption hints from a prior attempt.
- **Do work**, writing intermediate state to cache as it progresses.
- **Persist outputs** to durable locations:
  - Files (flight plans, work units) → tracked paths in `.maverick/`.
  - Code changes → local jj commits. **Every commit produced by `fly` MUST include the bead ID in a commit-message trailer** (e.g., `Bead: bd-a1b2`). This enables `jj log` filters and the env-aware ready check (§11) to map beads ↔ commits. Typically one commit per bead. Structural workflows (plan generate, init) produce commits without bead trailers since they're not bead-driven; a `Type: structural` (or similar) trailer can be used for filtering — exact convention pending U7.
  - Bead state changes → bd federation, pushed inline via the bd CLI.
- **Return exit status**. 0 means all durable outputs are persisted (locally or in federation). Non-zero means work is incomplete; cache reflects how far we got.

### What handlers don't do

- Don't push code via raw git/jj. Code reaches GitHub through `maverick commit` (raw) or `maverick land` (curated). Structural workflows that want to publish their artifact may invoke `maverick commit` as their final step (auto-on by default for plan generate, init); fly never auto-invokes anything — its slab waits for the user to run `maverick land`.
- Don't access GitHub for code refs directly. The harness handles clone/fetch; bd handles federation.
- Don't worry about preflight environment setup — the harness has done the lazy-create of the project directory before the handler runs.
- Don't reach into another env's project directory or working tree. Cross-env coordination is exclusively via bd federation (for bead state) and pushed branches (for tracked artifacts).

---

## 9. Cache and resumption

### Lifecycle

- **Cache lives at** `<project>/.maverick/.cache/<command>/<primary-input-key>/`.
- **Cache is gitignored.** The single gitignore rule `.maverick/.cache/` covers the whole tree.
- **Cache survives across runs on failure.** When a command fails, its cache stays intact so the next attempt can resume.
- **Cache is wiped on success** by the workflow itself, as a final step. There is no separate `commit` verb to wipe it.
- **Explicit overrides:** `--no-resume` on a workflow wipes its cache before starting; `rm -rf ~/.maverick/<project>/.maverick/.cache/` is always safe.

### Resumption pattern

A workflow handler that supports resumption looks like:

```python
def refuel(project_dir, args):
    cache_dir = project_dir / ".maverick/.cache/refuel" / args.plan_name

    if not (cache_dir / "briefing.json").exists():
        briefing = run_briefing(...)
        write_json(cache_dir / "briefing.json", briefing)
    else:
        briefing = read_json(cache_dir / "briefing.json")

    if not (cache_dir / "decompose-outline.json").exists():
        outline = run_decompose_outline(briefing)
        write_json(cache_dir / "decompose-outline.json", outline)
    else:
        outline = read_json(cache_dir / "decompose-outline.json")

    # ... and so on
```

Each stage writes to cache when it completes. A subsequent run skips stages whose cached results exist.

### Cache invalidation

- **By success:** when a workflow completes cleanly, it clears its own `.cache/<command>/<key>/` subtree as a final step. (No separate `commit` does this.)
- **By explicit flag:** `--no-resume` on the workflow command clears its cache before running.
- **By manual cleanup:** `rm -rf ~/.maverick/<project>/.maverick/.cache/`.
- **By input change:** workflow handlers may hash their inputs (PRD content, etc.) and invalidate cache when inputs change. Optional per-handler.

### Cache is per-environment, never replicated

The cache exists only in this environment's local directory. Other environments running the same project never see this cache, ever — it is not in the federation, not in any branch, and not in any reference the architecture might add later. This is a hard rule; failure inspection is local, remediation is local.

---

## 10. Publish semantics

### Plan is transient; the bead graph is durable

A plan is the PRD-to-beads decomposition pipeline. Once refuel completes, the plan's role is done — the durable structure is the bead graph (work beads grouped into epics with dependency links). Multiple plans can pour into the same project's bead graph over time. There is no separate "initiative" concept; the bead graph itself is the structure.

### Branch model

Branches are publish-only constructs (commitment 1). They exist for human review on GitHub; agents never coordinate via branches.

| Branch                       | Purpose                                                        |
|------------------------------|----------------------------------------------------------------|
| `<default>` (e.g., `main`)   | The project's main branch on GitHub. Final destination.         |
| `maverick/<project>`         | The project's working branch. Each `land` opens or updates a PR against `main` from this branch. |

Single working branch per project. The rare multi-stream case (parallel feature efforts that want independent PR targets) is deferred — when it becomes a real need, branch routing can be added back via an explicit per-bead override or a separate-pour-target mechanism.

### Bead graph as the publishing structure

Cut points come from the bead graph, not from branches:

- **Epics** are the landable seams. Each epic is a coherent shippable chunk — that's already how decomposition produces them. We use this directly rather than introducing a parallel "boundary" concept.
- **Land scope** in the interim is "this env's local slab" (HEAD-cut on local jj). Epic scope tracing — landing exactly the dep tree of a specific epic — is a future capability that depends on cross-env code visibility (wip refs or continuous-sync).

### Two publishing verbs

Code reaches GitHub through one of two verbs, distinguished by whether the curator runs:

| Verb              | Curator? | PR? | Use case                                                                                 |
|-------------------|----------|-----|------------------------------------------------------------------------------------------|
| `maverick commit` | No       | No  | Structural artifacts (flight plans, configs, bootstrap files). Auto-invoked by structural workflows. |
| `maverick land`   | Yes      | Yes | Implementation slab from fly. User-invoked at coherent shipping points.                   |

The split is by *what the artifact needs*, not by *who invokes it*. Both verbs push to the same `maverick/<project>` working branch. Land additionally curates and opens a PR.

### What `maverick commit` does

Pure publish, no curation:

1. Pull (harness step): clone + fetch + check out `maverick/<project>` (creating from `main` if it doesn't exist on the remote yet).
2. Identify local commits not yet on the remote — `jj log -r 'mine() & ~remote_branches()'`.
3. `jj git push origin maverick/<project>`. Fast-forward if possible; rebase locally first if not.
4. No PR opened. No bead state changes (commit doesn't know about beads — it just publishes whatever's local).

When invoked at the end of plan generate or init, `commit` publishes the workflow's structural artifact so other envs can pull it.

### What `maverick land` does (interim semantics)

Curated publish for fly's implementation slab:

1. Identify the slab — `jj log -r 'mine() & ~remote_branches()'` gives the local commits this env produced since the last `commit`/`land`. Each commit's bead ID comes from its commit-message trailer (§8).
2. Run the curator agent over the slab. Curator may **squash, reorder, rewrite messages**. Curator may **not** edit file content — content fixes go through a new bead, not through curation.
3. Rebase the curated slab onto `origin/maverick/<project>` (or `main` if the working branch doesn't exist yet).
4. Push to `maverick/<project>`. Open or update a PR `maverick/<project>` → `main`.
5. Mark the bundled beads' state transitions: `implemented` → `closed` happens when their commits reach `main` (PR-merge webhook or poll). An epic auto-closes via federation when all its work beads reach `closed`.

### Why concurrent `land` (or `commit`) is impossible by construction

Two envs cannot land or commit the same work because each env only has its own local commits. env-A cannot rewrite or push commits authored by env-B — env-B's commits aren't in env-A's local jj history. This dissolves the concurrent-publish race entirely; no advisory lock needed.

env-A and env-B can both publish *their own* slabs against the same `maverick/<project>` branch concurrently. The second one fast-forwards or rebases on top of the first's push. Standard distributed-VCS semantics handle it; jj's first-class conflicts make rebase non-blocking.

### Multi-PR per epic in the interim

When N envs each contributed to the work beads of a single epic, each env's `land` produces its own PR. Result: **N PRs against `main`, one per contributing env**, scoped to that env's local slab. The epic itself closes via federation when all its work beads have reached `closed` (i.e., all the contributing PRs have merged).

This is honest about the interim transport limitation — env-A cannot land env-B's commits because it doesn't have them. The user-visible cost is review surface area scaling with contributing envs. `maverick doctor` should warn when an epic has multi-env contributions in flight so the user isn't surprised.

The future upgrade path: **wip-ref pushing**. Each env pushes its local commits to `refs/maverick/wip/<env-id>/...` when it implements a bead. Land can then fetch all relevant wip refs, union the commits, and produce one PR scoped to the epic's full work-bead set. Same infrastructure also resolves H3 (durability) and the cross-env dep-chain serialization (see §11). Build it once these become pressing.

### Cut points and seams

The seam between "what was previously published" (by either `commit` or `land`) and "what this publish covers" is implicit: it's wherever local-only commits start in this env's jj log. There is no shared `last_published_commit` pointer, no checkpoint metadata, no synchronization needed. Each env's local jj state knows its own seam.

Default cut for both verbs: HEAD at invocation time. `land --epic <id>` cuts at the commit where epic `<id>`'s last bead reached `implemented`. Publishing more often is always safe; the slab is just smaller.

### Curator hard rule (worth restating)

**Curator does not change file contents.** History-shape changes are safe (squash, reorder, message-rewrite). Content edits are forbidden because:

- Other agents have local working state (uncommitted edits, in-flight beads) built against the pre-curated content.
- Already-merged work in `main` or in other envs' jj history references the original content via hashes/blames.
- jj will surface textual conflicts on rebase, but will not catch semantic surprises (a function whose body changed silently breaks callers in other agents' work).

If curator wants a content change, file a new bead. The next fly run picks it up. The next land publishes it.

### Commit message strategy

Workflow commands leave breadcrumbs in `.maverick/.cache/<command>/` indicating what work was produced. Each commit produced by fly carries a `Bead: <id>` trailer (§8) that links it to the bead it implements. Curator reads those trailers plus the cache breadcrumbs and bead metadata to construct PR description and per-commit messages. Specifics per workflow are TBD (D1).

---

## 11. Multi-agent considerations

### Producer/consumer over the bd federation

The architecture is a producer/consumer queue with bd federation as the queue:

- **Pour agents** (`refuel`) decompose PRDs into beads, push them to bd federation, exit. They produce no code.
- **Grab agents** (`fly`, often `--watch`) ask the maverick coordinator for ready beads, claim, implement locally, repeat. Eventually a human (or a meta-agent) runs `land` to publish their accumulated local slab.

A pour agent and N grab agents can run in different environments concurrently with no coordination beyond bd federation. New beads appearing mid-stream is just "the queue got longer"; grabbers don't notice or care.

**Interim reality vs. architectural capability.** The architecture *supports* pour-during-grab concurrency, but in the request-response interim the dominant pattern is sequential: refuel produces one epic + its work beads, exits; fly drains them; user lands; next refuel adds another epic; etc. True concurrent pour-while-watch (a pour agent streaming new beads into the federation while a grab agent's `--watch` discovers them in real time) is a continuous-sync future capability — not because anything is mechanically broken today, but because (a) refuel is a one-shot decomposition pass, not a service, and (b) federation pull cadence is poll-bound. The producer/consumer framing is the right model for the long term; near-term usage will mostly be sequential.

### Bead types

Two bead categories serve different roles in the graph:

| Type     | Role                                                                                                   |
|----------|--------------------------------------------------------------------------------------------------------|
| **Work** | Atomic unit of implementation. A grab agent claims, implements, transitions through states.            |
| **Epic** | Grouping with shared dependency boundaries. Acts as the landable seam — each epic is a coherent shippable chunk. Auto-closes via federation when all its work beads reach `closed`. |

We considered adding a separate "boundary" bead type to mark landable seams but dropped it: epics already serve that role, and a parallel concept just renames what the bead graph already encodes. If a project wants a finer-grained landable seam than its epics, the right answer is to split the epic, not to introduce a new bead type.

**Epic scope tracing** — landing exactly the work beads of a specific epic in one PR — is a future capability that requires cross-env code visibility (wip refs or continuous-sync). Until then, multi-env contributions to an epic produce N PRs (§10).

### Bead state machine

Four states. The earlier three-state proposal (`open / in-progress / closed`) conflated "actively being worked," "implementation done locally awaiting publish," and "agent crashed" — which broke stale-claim recovery, the env-aware ready check, and `fly --watch` exit semantics. The four-state model splits the load-bearing distinction.

| State          | Meaning                                                                                                      |
|----------------|--------------------------------------------------------------------------------------------------------------|
| `open`         | Not yet claimed.                                                                                             |
| `in-progress`  | Some env claimed it; work is in flight. Owner field identifies which env.                                    |
| `implemented`  | Owner finished the work locally. Code commits exist in owner's local jj history (and, when wip-refs are built, in the owner's wip ref). Awaiting `land` + PR merge. |
| `closed`       | Code for this bead is in `main`. Set on PR merge, not earlier.                                              |

Transitions:

- `open` → `in-progress` — fly claims the bead.
- `in-progress` → `implemented` — fly finishes the work, makes the local jj commit (with the `Bead:` trailer).
- `implemented` → `closed` — PR carrying the code merges to `main`. Closure is a federation update, not an env-local action.
- Stale recovery: `in-progress` (or `implemented`) → `open` via `maverick reclaim` if the owner is gone.

Note that `implemented` is operationally meaningful even though no other env can act on it: it lets stale-claim heuristics distinguish "agent crashed mid-work" from "agent done, awaiting PR review," and it gives the env-aware ready check a clean signal for "owner has the code locally."

### Bead claim

Claim is just a status push:

```
bd update <bead> --status in-progress --owner <env-id>
bd federation push
```

First writer to push wins. The second pusher's status update conflicts on the `status` column under dolt merge semantics; reconciliation = "see the bead is already claimed, pick a different one." This is the entire claim protocol — there is no separate lock primitive (commitment 2).

### Env-aware ready check

bd's native `bd ready` is strict: a bead is ready when its status is `open` and all its deps' statuses are `closed`. This strict view is correct for cross-env safety — env-B never sees beads with in-progress deps as ready, so env-B can't accidentally claim a bead whose dep is owned by env-A.

But strict-only would prevent the owning env from chaining through its own dep tree (env-A can't continue from bead-X to bead-Y if bead-X is `in-progress`/`implemented` in env-A's own queue, even though env-A has the code locally). The maverick coordinator layer adds an env-aware relaxation:

```python
def ready_for(bead, this_env, local_jj) -> bool:
    if bead.status != "open":
        return False
    for dep in bead.deps:
        dep_state = federation.get(dep)
        if dep_state.status == "closed":
            continue                         # in main, visible to all envs
        if dep_state.owner == this_env \
           and dep_state.status in {"in-progress", "implemented"} \
           and local_jj.has_commit_for(dep): # mapped via the Bead: trailer
            continue                         # I have the code locally
        return False
    return True
```

| Query                                  | Semantics                                                                  | Used by                  |
|----------------------------------------|----------------------------------------------------------------------------|--------------------------|
| `bd ready` (native)                    | Strict: all deps `closed`.                                                 | Any env not asking maverick (and any non-maverick tool). |
| `coordinator.ready_beads(env=this)`    | Augmented: deps `closed` OR (`in-progress`/`implemented` owned by `this` AND code present locally). | maverick fly.            |

The asymmetry is safe by construction. env-B's strict view will never include a bead whose dep is `in-progress` or `implemented` (regardless of owner), so concurrent-claim races on dependent beads can't open. Only the owner's augmented view relaxes the gate, and only for that owner.

### Stale claims

If env-X crashes mid-bead, its claim sits as `in-progress`/`implemented` indefinitely. With dep chains, this also blocks downstream cross-env work (env-B can't claim beads whose deps env-X owns). Stale claim recovery is therefore load-bearing not just for queue health but for unblocking dep chains.

- **Manual:** `maverick reclaim <bead-id>` — operator-invoked, drops the claim back to `open`. Start here.
- **Automatic:** heartbeat mechanism — claimed beads carry a `claim_expires_at` field; fly refreshes it periodically; expired claims are stealable. Promote when multi-agent traffic or unattended `--watch` runs make the manual path painful.

### Code-level concurrency

env-A and env-B both running `fly --watch` against the same project:

- Each picks **independent dep chains** — the env-aware ready check naturally clusters dependent work within the env that started the chain. Two envs alternating on a single dep chain is structurally suppressed.
- Each makes local jj commits. Neither pushes code.
- Their working trees may both touch the same files (cross-chain). Neither sees the other's edits during fly.

Conflicts surface only at `land` time, when each env publishes its own slab to `maverick/<project>`. Standard rebase semantics apply; jj's first-class conflicts mean a divergent edit produces a resolvable conflict revision, not a blocked push.

### `fly --watch` exit semantics

The agent-facing API is subscription-shaped (commitment 6):

```python
async for bead in coordinator.ready_beads(env=this_env, epic=epic_id):
    await claim_and_implement(bead)
```

Implementation today: federation pull on a 10–30s timer, env-aware filter, yield. The iterator hides this. Future implementations (real subscription, event stream) replace the impl without touching agent code.

Exit conditions (in priority order):

1. **Hard cancel** (second Ctrl-C / SIGTERM): drop the in-flight bead; revert its status from `in-progress` to `open`; exit.
2. **Graceful stop** (first Ctrl-C / SIGINT): finish the current bead through `implemented`; do not claim another; exit.
3. **Empty queue**: `coordinator.ready_beads(env=this)` yields nothing — either every reachable epic is fully implemented locally, or remaining work is blocked by cross-env dep ownership. Exit cleanly. On exit, fly reports a summary: beads implemented this session, epics now fully implemented in this env, suggestion to run `maverick land`. The user can re-invoke `fly --watch` after landing to keep going.
4. **`--max-beads <n>` cap**: stop after N beads. Safety cap for unattended runs.

### What does not exist in this architecture

- No file locks, OS-level locks, or process-level mutexes outside the local jj/bd state (one carveout per §14: an intra-env file lock to prevent two maverick commands stomping the same project dir).
- No GitHub branch advisories or "in-flight" markers.
- No external coordination service (Redis, ZK, etc.).
- No agent-to-agent direct messaging, RPC, or hand-off protocols.
- No reading another env's working tree.

If a coordination need arises across envs, the answer is bd metadata or it doesn't get built (commitment 2).

---

## 12. Migration from current state

> **Note (2026-05-03)**: `WorkspaceManager` and the hidden
> `~/.maverick/workspaces/<project>/` clone pattern were retired
> *before* this architecture lands, on the 044-opencode-substrate
> branch (`refactor: collapse to single-repo (CWD) workflow model`).
> All long-running ops now operate directly in the user's checkout —
> a strict subset of the future state. The leftover concern for early
> adopters is on-disk: `~/.maverick/workspaces/<project>/` directories
> from the legacy code path are now orphaned. The future
> `maverick migrate` command should detect and clean them up (or
> reuse the directory shape if it ends up converging with the new
> per-environment layout). Until migrate exists, users can `rm -rf
> ~/.maverick/workspaces/` safely — the contained jj clones held only
> derived state.

Existing maverick projects have:
- A user checkout with `.beads/`, `maverick.yaml`, `.maverick/`, all locally
- Possibly bd state pushed to GitHub via `refs/dolt/data`
- Local state diverged from any other environment
- *Possibly* an orphaned `~/.maverick/workspaces/<project>/` from the
  pre-collapse era.

### Migration command

A one-time command to move from old architecture to new:

```bash
maverick migrate <github-url>
```

What it does:

1. Verify GitHub repo has the maverick state expected (maverick.yaml, etc.).
2. Push any local-only bd state up to GitHub federation.
3. Optionally `git rm --cached -r .beads/backup/` and other bd local-only files that shouldn't be tracked.
4. Create `~/.maverick/<project>/` populated from GitHub.
5. Print: "Migration complete. You can `rm -rf` the local checkout — maverick now operates entirely from `~/.maverick/<project>/`. Future commands don't need a CWD inside a project."

### Backward compatibility

For one release cycle, maverick supports both old (CWD-based) and new (URL-based) command forms. New commands accept `--project <url>` or fall back to detecting CWD-based usage. The old form prints a deprecation warning.

After the transition window, only the new form is supported.

---

## 13. Implementation notes

### What needs to be built

> **2026-05-03 status legend:** **[done]** = landed on `044-opencode-substrate`. **[partial]** = some scaffolding/groundwork landed; substantive work remains. **[unbuilt]** = no work yet. Items not annotated are unbuilt.

1. **Universal harness** — wraps every command with the pull-work-push cycle. Probably a decorator or context manager around workflow handlers. *[unbuilt]*
2. **Workflow handler refactor** — each existing workflow (plan generate, refuel, fly, land) is restructured to:
   - Take a project directory + args
   - Use cache for resumption
   - Return an exit status
   - Produce local jj commits for code (with `Bead: <id>` commit-message trailers); push bd federation inline for bead state; never push code

   *[partial]* The CWD-threading half is in place: every workflow now operates on `Path.cwd()` and the WorkspaceManager dance is gone (`cf11db4`). Fly's commits carry `Bead: <id>` trailers (`82fcedd`). The cache/resumption restructuring and exit-status discipline are unbuilt.
3. **Four-state bead machine** — `open / in-progress / implemented / closed`. fly's `claim_and_implement` flow drives `open → in-progress → implemented`. PR-merge handler drives `implemented → closed`. `maverick reclaim` reverts `in-progress`/`implemented` → `open`. *[unbuilt]*
4. **Epic-as-seam wiring** — epics auto-close via federation when all their work beads reach `closed`. `fly --watch` exits when its ready queue is empty (no special boundary handling). Land's `--epic <id>` cuts at the commit where the epic's last bead reached `implemented`. *[unbuilt]*
5. **`maverick commit`** — raw publishing verb. Pushes local jj commits on `maverick/<project>` to remote, no curator, no PR. Auto-invoked by structural workflows (plan generate, init) at completion; user-invoked otherwise. See §10. *[unbuilt]*
6. **`maverick land`** — curated publishing verb for implementation slabs. Reads local jj slab, runs curator (shape-only), pushes, opens or updates PR. See §10. *[partial]* `land` exists but currently curates locally and prints next-step hints — no automated push, no PR creation (`cf11db4`).
7. **Subscription-shaped coordinator API** — `coordinator.ready_beads(env=this, ...)` async iterator implementing the env-aware ready check (§11). Maps beads ↔ commits via the `Bead:` commit trailer; consults bd federation for state and local jj for code presence. Today: federation poll + filter. Tomorrow: real subscription. *[partial]* Bead trailers are now produced by fly (`82fcedd`); nothing reads them yet.
8. **`maverick init`** rewrite — restructured to fit the pull-work-push pattern. Init produces structural artifacts and pushes them via `maverick commit` semantics; init's PR-opening is the carveout pending H5. *[partial]* Init no longer writes the legacy `model.model_id` field, strips bd's auto-set `sync.remote`, and untracks `.beads/backup/` (`0ae955d`) — the three brittleness bugs from §1. The broader pull-work-push restructuring is unbuilt.
9. **Cache structure** — establish `.maverick/.cache/<command>/<primary-input-key>/` convention; ensure `.maverick/.cache/` is in projects' `.gitignore`.
10. **Local directory naming** — decide convention for `~/.maverick/<project>/`. Slug from URL, sanitized.
11. **`maverick use`** — optional convenience for context-set. Stores last-used project; subsequent commands default to it.
12. **`maverick reclaim`** — manual bead-claim recovery (covers stale `in-progress` and `implemented` claims). Heartbeat-based automatic reclaim is deferred until multi-agent traffic justifies it.
13. **`maverick doctor` multi-env-per-epic check** — warn when an epic has multi-env contributions in flight (different envs own different work beads in the same epic). In the interim that means N PRs at land time; user should expect this or consolidate manually.
14. **`maverick migrate`** — one-shot migration command for existing maverick projects. *[unbuilt — but more pressing now that legacy `~/.maverick/workspaces/<project>/` directories from the pre-collapse era are orphaned on early-adopter machines; see §12.]*

### Already done ahead of the architecture (on `044-opencode-substrate`)

- **WorkspaceManager retirement.** The doc's Phase 2 (§13 Sequencing) implied this as part of per-workflow migration; we did it ahead of schedule as a lump-sum collapse to single-repo (CWD) operation (`cf11db4`). Net −3064 LOC. The per-environment `~/.maverick/<project>/` materialization that should replace it remains unbuilt.
- **Cross-VCS uncommitted-changes snapshot.** `snapshot_uncommitted_changes()` in `library/actions/jj.py` detects `.jj/` and dispatches to either `jj_snapshot_changes` or plain `git add -A && git commit` (`82fcedd`). This was on the punch list as a fly-`--auto-commit` bug fix; under the architecture it becomes the obvious primitive for "snapshot whatever the local VCS is."
- **`Bead: <id>` commit trailer.** Fly's bead commits now carry the trailer alongside the existing `bead(<id>): <title>` subject (`82fcedd`). Forward-compat with the env-aware ready check (§11), curator scope tracing (§10), and slab attribution at land time. Trailer key is exactly `Bead:`; format details in U7 still need pinning down.

### Future build items (deferred until pressing)

- **Wip-ref pushing** (`refs/maverick/wip/<env-id>/...`). Solves three things at once: H3 durability backstop, cross-env dep-chain unblocking, and one-PR-per-epic consolidation. The minute one of these becomes painful, this is the single piece of infrastructure to add.
- **Heartbeat-based stale-claim auto-recovery**. Attaches a `claim_expires_at` field; fly refreshes it; expired claims are stealable.

### What gets deleted

1. **`WorkspaceManager` and the `~/.maverick/workspaces/<project>/` pattern** — replaced by the per-environment directory at `~/.maverick/<project>/`.
2. **`.maverick/runs/<uuid>/` infrastructure** — no run tracking needed.
3. **`workspace status|clean` commands** — no workspace concept to manage.
4. **`_strip_bd_sync_remote`, `_untrack_bd_local_state`** (the helpers we built this session) — under the new architecture, these belong in `migrate`, not `init`. New projects don't have the underlying problems.
5. **The `.maverick/workspace.json` marker** — no per-checkout marker needed when there's no separate user checkout.
6. **The legacy `model.model_id` field** — superseded by `provider_tiers`; init should stop writing it.
7. **Any code that pushes a "stream branch" or shared-coordination branch** — branches are publish-only (commitment 1). If a draft proposes an agent-shared branch, redesign it.

### Sequencing

A reasonable phased rollout:

- **Phase 1: Add the universal harness alongside today's behavior.** Subscription-shaped coordinator API lands here so workflow handlers can adopt it incrementally. Workflow commands gain `--local-only` flag that opts into the new "no code push" pattern.
- **Phase 2: Migrate one workflow at a time.** Refuel first (smallest blast radius — bd-only push, no code at all), then plan generate, then fly, then land. Each migration restructures the workflow to local-jj-commits + cache + return exit status; old behavior preserved behind a feature flag.
- **Phase 3: Move directory layout.** Add `~/.maverick/<project>/` as the new home; deprecate `~/.maverick/workspaces/<project>/`. Provide `maverick migrate`.
- **Phase 4: Drop deprecated paths.** Remove old harness, old workspace concept, old gitignore entries. Cleanup pass.

---

## 14. Open questions

### Resolved

| #  | Question                       | Resolution                                                                                                                                                  |
|----|--------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1  | Branch strategy                | Single `maverick/<project>` working branch. Initiative concept dropped — the bead graph (work beads grouped into epics) carries the durable structure. Branches remain publish-only (commitment 1). |
| 4  | Concurrency locking            | All cross-env locks live in bd metadata (commitment 2). For two commands accidentally running in the same env on the same project: a local file-lock at `~/.maverick/<project>/.maverick/.lock` is acceptable since it's intra-env. |
| 5  | Bead claim semantics           | Status push to bd federation; first-writer-wins via dolt merge on `status`. Stale claims: manual `maverick reclaim` first; heartbeat/TTL added when traffic justifies it. |
| 6  | Cache GC policy                | Local concern; aggressive cleanup is fine. No federation involvement. Add an opt-in sweep (e.g., 7d default) when the cache grows enough to matter.         |
| 7  | User-level state               | Local concern; never federated. `~/.maverick/state.json` for last-used project + prefs.                                                                     |
| H1 | Bead state granularity         | Four states: `open / in-progress / implemented / closed`. The new `implemented` state separates "owner finished work locally" from "actively working" and from "code in main." Drives stale-claim heuristics, env-aware ready checks, and the cross-env dep-blocking story (§11). |
| H2 | Initiative branch lifecycle    | Moot — initiative concept is removed. Single `maverick/<project>` working branch; lifecycle is whatever the user wants (long-lived between merges, recreated after each merge, etc.). Multi-stream parallel branches deferred until a real need surfaces. |
| U1 | bd metadata extensibility for `target_branch` | Moot — `target_branch` is no longer load-bearing. Single working branch per project means no per-bead branch routing.                                |
| U6 | `fly --watch` exit semantics   | Four ordered exit conditions in §11: hard cancel (drop in-flight, revert claim), graceful stop (finish current bead through `implemented`), empty queue (no ready work for this env — natural stopping point for landing), `--max-beads` cap. |

### Still open: high-stakes

These need a decision before the relevant section can be implemented. Choices made here cascade into multiple downstream sections.

| #  | Question                              | Notes                                                                                                                                                       |
|----|---------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|
| H3 | Durability gap when env dies          | Fly is local-only; dead laptop = lost code + zombie beads. Manual reclaim restores bead state but not work. The unblock path is **wip-ref pushing** (`refs/maverick/wip/<env-id>/...`) — same infrastructure also gives one-PR-per-epic consolidation and unblocks cross-env dep chains. Build when any of those three pressures becomes real. |
| H4 | Fly's local branch parent             | Doc says fly makes local jj commits but doesn't say what they're parented on. `main` requires land to rebase onto `maverick/<project>`; `maverick/<project>` requires the branch to exist before first fly. Affects the harness's pull step too. |
| H5 | The init carveout                     | Init opens an "Adopt maverick" PR directly, which is the one PR-opening that doesn't go through `land`. Init's structural commit itself is fine (uses `commit` semantics like plan generate). The open question is the PR-opening: does init keep its own gh-based PR creation, or does it route through `land --no-curator` so that all PRs come from one code path? |
| H6 | Multi-env-per-epic detection          | When N envs each contribute work beads to a single epic, interim semantics produce N PRs at land time. `maverick doctor` should warn when this is in flight so the user isn't surprised. Open: what's the warning text, when does it fire, does it block any action? |

### Still open: underspecified

Real design surface to fill in during implementation. The shape of the answer matters.

| #  | Question                              | Notes                                                                                                                                                       |
|----|---------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|
| U2 | Subscription-shaped API surface       | `coordinator.ready_beads(env=this, ...)` is asserted as the abstraction; yield types, error handling, disconnect/reconnect, backpressure, filter-scope semantics, and the "augmented vs strict" mode toggle are all undefined.                                              |
| U3 | PR-merge → bead-closed mechanism      | "Webhook or poll." Webhook needs GitHub App infra we don't have. Polling burns API quota and adds latency. Pick at implementation time and document the tradeoff.                                              |
| U4 | Curator's "no content edits" rule     | Strict reading forbids ruff/prettier/gofmt during curation. Loose reading is a slippery slope. Probably needs an explicit allowlist for mechanical autofix; otherwise users will route around the rule. |
| U5 | Coordinator carveout language         | Commitment 2 reads as absolute but the resolved table carved out a local intra-env file lock. Either tighten commitment 2 to "cross-env coordination" or drop the file-lock carveout in favor of bd metadata for intra-env too. |
| U7 | Bead-ID commit trailer format         | The `Bead: bd-a1b2` trailer is now load-bearing (env-aware ready check, curator scope tracing, land slab attribution). Pin down: exact trailer key, ID format (short hash vs full), `jj log` filter syntax, behavior when a commit has zero or multiple bead IDs. |

### Still open: deferrable

Decisions that can wait until the relevant module is implemented; they don't shape other choices.

| #  | Question                              | Notes                                                                                                                                                       |
|----|---------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|
| D1 | Per-workflow commit message format    | Curator agent reads cache breadcrumbs + bead metadata; specific format per workflow TBD.                                                                    |
| D2 | Project directory naming              | Slug from GitHub URL, sanitized. Pin down ambiguity-resolution rule when implementing.                                                                      |
| D3 | Greenfield UX                         | Convenience `maverick init --create-github-repo <slug>` wrapping `gh repo create`. Probably yes; decide when implementing init.                             |
| D4 | Migration backward-compat window      | How long to support old (CWD-based) command forms alongside new (URL-based). One release cycle is the strawman; revisit when migrate lands.                 |

---

## 15. Summary

This architecture replaces the current "two-copy" model (user checkout + hidden workspace) with a "one-copy, two-plane" model:

- Maverick owns one local working directory per project, at `~/.maverick/<project>/`.
- Every command pulls fresh state from GitHub and does its work locally.
- **Two planes sync independently:** code (held local until `land`) and beads (pushed to bd federation inline).
- **Bd federation is the producer/consumer queue and the only cross-env coordinator.** Pour agents pour beads in; grab agents drain ready beads via the env-aware ready check.
- **Bead graph carries the durable structure.** Work beads grouped into epics describe the work; branches don't. Epics double as landable seams — no separate "boundary" bead type. Single `maverick/<project>` working branch suffices.
- **Two publishing verbs:** `maverick commit` (raw push, used by structural workflows for flight plans / configs) and `maverick land` (curated push + PR, used for fly's implementation slab). Every workflow's pull-work-push is self-contained: structural workflows auto-publish via `commit` so the next workflow on any env can pull the artifact.
- The cache survives failures so retries can resume; it is local-only and never replicated.

Bead state is four-stage: `open → in-progress → implemented → closed`. The `implemented` state separates "owner has the code locally" from "code is in main," which is what makes env-aware ready checks, stale-claim heuristics, and PR-pending lifecycles all clean.

The command surface is small: nine user-facing verbs, organized as workflows + publishing + diagnostics + auxiliary. Composition via `&&` for the common multi-step flow.

Migration is bounded: existing projects use `maverick migrate` once; the old workspace pattern is deprecated and removed.

The architecture is forward-compatible with continuous-sync collaboration (live CRDT replication of bead state and code): branches stay publish-only, coordination stays in bd federation, single-source-of-truth per data type holds. The implementation today uses request-response transport (bd federation push, GitHub fetch); the abstractions don't change when transport upgrades. Wip-ref pushing is the one piece of intermediate infrastructure that, when added, collapses three interim limitations at once (durability, cross-env dep chains, one-PR-per-epic).

---

## 16. Glossary

Terms are listed alphabetically. Only terms with maverick-specific interpretation, or where the common meaning would mislead, are defined here. Common English / programming terms (commit, branch, push, pull, etc.) carry their normal meaning unless qualified.

| Term                          | Definition                                                                                                                                       |
|-------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| **Bead**                      | An atomic unit tracked in bd federation. Carries type (work or epic), status, owner, and dependency links.                                        |
| **Bead federation**           | bd's dolt-backed cross-environment sync layer. The architecture's queue and only cross-env coordinator.                                           |
| **Bead trailer**              | The `Bead: <id>` line in a commit message that links a code commit to the bead it implements. Load-bearing for env-aware ready checks, curator scope tracing, and land slab attribution. Format details in U7. |
| **Cache**                     | Workflow scratch at `<project>/.maverick/.cache/`. Local-only, gitignored, never replicated. Single source of scratch; not a synchronization layer.|
| **Claim**                     | The act of marking a bead `in-progress` with the current env-id. Implemented as a status push to bd federation; arbitrated by dolt merge semantics.|
| **Closed**                    | Bead state: code is in `main`. Set by federation update on PR merge, not by any env-local action.                                                 |
| **Commit (verb)**             | `maverick commit` — pushes local jj commits on `maverick/<project>` to remote, as-is, no curator, no PR. Used for structural artifacts (flight plans, configs). Auto-invoked by structural workflows; user-invoked otherwise. Distinct from `land`, which adds curator + PR. Distinct from a plain jj/git commit, which is the local commit operation underneath. |
| **Commitment (principle)**    | A numbered design principle from §2 (1–6). Bounds architectural decisions; violating one signals a redesign, not a special case.                   |
| **Coordinator**               | The maverick agent-facing layer over bd federation. Provides the subscription-shaped `ready_beads(env=this, ...)` iterator and implements the env-aware ready check. Consults bd state and local jj presence; introduces no new coordination primitives.|
| **Curator**                   | The agent that runs during `maverick land` to rewrite the local commit slab into a presentable shape. May rewrite history shape; may not edit content.|
| **Environment** (env)         | A machine running maverick. Has its own `~/.maverick/<project>/` per project. Distinct from a process / shell environment. Identified by env-id.    |
| **Env-aware ready check**     | The augmented readiness predicate used by maverick fly: a bead is ready when its deps are `closed` OR (`in-progress`/`implemented` owned by this env AND the dep's commit is present locally). Strict `bd ready` is used by everything else.|
| **Epic**                      | A bead type for grouping work beads with shared dependency boundaries. Doubles as the landable seam — each epic is a coherent shippable chunk; auto-closes via federation when all its work beads reach `closed`. (We considered a separate "boundary" bead type and dropped it: epics already serve that role.) |
| **Fly**                       | The grab workflow. Asks the coordinator for ready beads, claims, implements as local jj commits, repeats. Never pushes code.                       |
| **Grab agent**                | An env running `fly` (often `--watch`). Drains beads from the federation queue and produces local code commits.                                    |
| **Handler**                   | A workflow's specific work function (`def workflow(project_dir, args) -> int`). Called by the harness after the pull step.                         |
| **Harness**                   | The universal pull-work-push wrapper around handlers. Lazy-creates the project directory, fetches, calls the handler, returns exit status.         |
| **Implemented**               | Bead state: owner finished the work locally; code commits exist in owner's local jj history. Distinct from `closed` (code is in `main`) and from `in-progress` (work in flight). The state that makes env-aware ready checks and stale-claim heuristics tractable.|
| **In-progress**               | Bead state: claimed by an env, work in flight but not yet locally complete.                                                                        |
| **Land**                      | `maverick land` — runs the curator over the env's local implementation slab, pushes the curated result to `maverick/<project>`, opens or updates a PR. Used for fly's accumulated work. Distinct from `commit`, which is raw publish (no curator, no PR). |
| **Open**                      | Bead state: not yet claimed.                                                                                                                       |
| **Plan**                      | The transient PRD-to-beads decomposition pipeline. Once refuel completes, the plan's role is done; the bead graph carries the durable structure.   |
| **Plane**                     | A sync layer. The architecture has two: code plane (git refs, branch-scoped) and bead plane (bd federation, project-scoped). They sync independently.|
| **Pour agent**                | An env running `refuel`. Decomposes a PRD into work beads grouped into one or more epics, and pushes them to bd federation. Produces no code.       |
| **Project**                   | A GitHub repo configured for maverick (has `maverick.yaml`, has bd federation initialized).                                                        |
| **Publish**                   | Pushing code to GitHub. Two flavors: `maverick commit` (raw, for structural artifacts) and `maverick land` (curated + PR, for implementation slabs).|
| **Refuel**                    | The pour workflow. Reads a flight plan, runs decomposition agents, writes work beads + epic groupings to bd federation. Pushes inline; produces no code.|
| **Slab**                      | The range of local jj commits in a single env's history that haven't been landed yet. `land` curates and publishes the slab.                       |
| **Subscription-shaped API**   | An iterator-based agent contract (`async for bead in coordinator.ready_beads(env=this)`) that hides the underlying transport — poll today, real subscription later.|
| **Wip ref**                   | Future-state coordination ref at `refs/maverick/wip/<env-id>/...` where envs push their local code commits before land. Not built yet; the future fix that simultaneously addresses H3 (durability), cross-env dep-chain unblocking, and one-PR-per-epic consolidation. |
| **Work bead**                 | The default bead type. Atomic unit of implementation; a grab agent claims, implements, transitions through states.                                  |
| **Workflow**                  | A maverick command handler (init, plan generate, refuel, fly, land). Not a BPMN-style orchestration; each workflow is one function invocation that does its work and returns.|
