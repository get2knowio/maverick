# Design Brief: Workspace Isolation with Hidden jj

## Goal

Design a workspace isolation model where Maverick performs all VCS-heavy work in a hidden jj workspace (`~/.maverick/workspaces/`), keeping jj entirely invisible to the user. The user's repository remains pure git. jj becomes a Maverick implementation detail — powerful history editing under the hood, standard git commits as output.

## Core Insight: jj as a Hidden Engine

The user should never need to install, learn, or interact with jj. Maverick uses jj internally for its superior history editing capabilities (squash, absorb, split, conflict-as-data, lock-free concurrency, operation log undo). At the `land` boundary, jj commits are translated into git commits and pushed to the user's repo. From the user's perspective, Maverick created some git commits on a branch — how it got there is invisible.

## Why Not jj in the User's Repo?

The current colocated model (jj + git sharing `.git/` in the user's repo) has significant friction:

- User must install jj
- User must understand (or at least tolerate) jj
- `.jj/` directory appears in their repo
- jj auto-import/export can surprise users
- IDE jj support is immature
- Colocated mode has edge cases and known bugs

The hidden workspace model eliminates all of these. jj is a bundled tool Maverick manages, versioned and upgraded independently of anything the user has installed.

## Why Not jj Workspaces?

jj has native workspace support (`jj workspace add`) that shares the object store and operation log across workspaces. However, secondary workspaces created from a colocated repo **do not inherit `.git/`** — they become pure jj repos. This breaks git-native tools (GitPython, `gh` CLI, IDE git integration) in the secondary workspace.

Since the hidden workspace model uses pure jj internally (no colocated mode needed), and only interacts with git at the clone/push boundaries, this limitation is irrelevant. Maverick uses jj natively in its workspace and git is only the transport protocol.

If jj resolves the secondary-workspace colocation issue in the future, jj workspaces could replace the `jj git clone` approach — but the user-facing architecture would be identical.

## Architecture

```
User's repo (pure git)                 Maverick's workspace (hidden)
~/project/                             ~/.maverick/workspaces/project-fly/

  .git/                                  .jj/   (pure jj, no colocated mode)
  src/                                   .git/  (jj's git backend, not user-facing)
  ...                                    src/
                                         ...
  (never sees jj)
                        jj git clone
                    ──────────────────>   (user's repo = git remote "origin")

                        jj git push
                    <──────────────────  (jj commits → git branch in user's repo)
```

### Workspace Lifecycle

```
created     →  jj git clone ~/project ~/.maverick/workspaces/project-fly/
bootstrapped →  workspace setup hook runs (e.g., "uv sync")
used        →  fly works: file edits, jj commits, jj squash, jj op restore
extracted   →  land does jj git push (curated jj commits → git branch)
discarded   →  rm -rf ~/.maverick/workspaces/project-fly/
```

### What Works Where

| Operation | Where | Tool |
|-----------|-------|------|
| File edits during fly | Hidden workspace | jj (auto-snapshot) |
| Commits, squash, rebase | Hidden workspace | jj |
| Diffs, log, blame (reads) | Hidden workspace | jj (replaces GitPython) |
| Rollback on failure | Hidden workspace | jj op restore |
| History curation | Hidden workspace | jj squash/absorb/split |
| Push curated result | Hidden workspace → user's repo | jj git push |
| PR creation | User's repo | PyGithub or gh CLI |
| User code edits (post-eject) | User's repo | git, IDE, Claude Code |

## GitPython Elimination

Inside the hidden workspace, Maverick uses jj for **everything** — reads and writes. No colocated mode, no GitPython, no compatibility concerns. The only git interaction is `jj git clone` at startup and `jj git push` at land.

Current GitPython read operations and their jj equivalents:

| GitPython (current) | jj equivalent |
|---------------------|---------------|
| `repo.diff("main")` | `jj diff --from main` |
| `repo.status()` | `jj status` / `jj diff --stat` |
| `repo.log()` | `jj log` |
| `repo.show(commit)` | `jj show <change>` |
| `repo.blame(file)` | `jj file annotate <file>` |

## Concurrent fly + refuel

A key product requirement: the user should be able to run `maverick refuel speckit` (creating beads) while `maverick fly` (consuming beads) is running. This is the "keep filling the tank while draining it" model.

### Why This Works Without Additional Isolation

| Resource | fly (drain) | refuel speckit (fill) |
|----------|-------------|----------------------|
| Source files | Writes (in hidden workspace) | Reads (in user's repo, maybe) |
| Bead queue (bd) | Reads next, marks done | Creates new beads |
| Spec files (.specify/) | Reads | Reads (parses tasks.md) |
| jj operations | Heavy (commit, squash) | None |
| Working tree (user's repo) | Not touching it | Not modifying source files |

These two commands operate on **different resources**. fly writes source code in the hidden workspace. refuel writes bead metadata. The shared state is the bead queue managed by `bd` — a classic producer/consumer pattern.

Requirements for this to work:
1. **bd concurrent access** — bead store handles producer + consumer simultaneously
2. **fly bead polling** — fly periodically checks for new ready beads, not just at startup
3. **Dependency awareness** — fly re-evaluates "what's ready?" after completing each bead

No workspace isolation is needed for this specific concurrency scenario.

## The `land` Experience

### Command Flow

```
maverick land
  │
  ├─ approve  → jj git push, create PR, cleanup workspace. Done.
  │
  └─ eject    → jj git push to preview branch, user takes the stick
                  │
                  │  user works in their repo
                  │  (IDE, Claude Code, git — their tools)
                  │
                  ▼
               maverick land --finalize → create PR, cleanup workspace
```

### Approve Path (Happy Path)

1. `maverick land` curates history in the hidden jj workspace (agent-driven, one-shot — not a conversation)
2. Shows preview: commit graph, diffs, stats, test status
3. User approves
4. `jj git push` translates curated jj commits → git branch in user's repo
5. Create PR via PyGithub
6. Clean up hidden workspace (`rm -rf`)

### Eject Path (User Needs to Intervene)

"Eject" — the pilot ejects from the Maverick when they need to take manual control.

1. `maverick land` curates and shows preview
2. User ejects (doesn't like the curation, spots a bug, wants to rethink something)
3. `jj git push` materializes current state as a preview branch (`maverick/preview/feature-x`) in user's repo
4. The jj workspace is now **spent** — its value has been extracted
5. User works on the git branch with their own tools: IDE, Claude Code, `git commit`, whatever
6. User runs `maverick land --finalize`
7. `land --finalize` works **entirely in the user's git repo** (no jj involved):
   - Verify branch state (tests pass, etc.)
   - Create PR
   - Clean up the hidden jj workspace (`rm -rf`)
   - Optionally clean up the preview branch

### Curation Options (No Conversation Needed)

Rather than building a rich agent conversation UI for history curation (which would mean rebuilding Claude Code), `land` offers curation strategies via flags:

```bash
# Default: agent curates automatically (one-shot, best effort)
maverick land

# User provides guidance upfront
maverick land --strategy "one commit per bead"
maverick land --strategy "squash into single commit"
maverick land --strategy "group by area"

# Skip curation entirely
maverick land --no-curate
```

If the agent's curation isn't what they want, they eject and use their existing tools (`git rebase -i`, Claude Code, etc.) to reorganize.

### Why land Is Not a Conversation

Building a rich iterative user-agent editing loop inside `maverick land` would require rebuilding Claude Code — a conversational agent with tool use, file editing, and rich previews. The user already has Claude Code. Land's job is narrow:

- **Curate once** (agent does its best)
- **Preview** (show the result)
- **Ship or eject** (approve or give the user a git branch)

When a human needs to be in the loop, Maverick produces artifacts (git branches, PRs) that work with the human's existing tools, then gets out of the way.

## Thematic Language

| Term | Meaning |
|------|---------|
| **fly** | Automated bead execution (the jet is flying) |
| **land** | Bring the work down cleanly (automated landing) |
| **eject** | Bail out to manual control (user takes the stick) |
| **finalize** | Ground crew cleanup after touchdown |
| **refuel** | Fill the bead tank while flying |

## Environment Bootstrapping

A fresh `jj git clone` produces a bare working copy. Maverick needs a configurable setup hook:

```yaml
# maverick.yaml
workspace:
  setup: "uv sync"          # run after clone
  teardown: "make clean"    # run before cleanup (optional)
```

For a `uv`-managed Python project this is fast (~seconds). For larger ecosystems (JS monorepos, native builds), this is the primary cost of the workspace model. It is a bounded, solvable problem.

## What This Unlocks (Future)

With workspace isolation established, the architecture supports:

1. **Background fly** (`maverick fly --background`) — user keeps coding while fly works
2. **Parallel bead execution** — multiple hidden workspaces, one per agent, each working a bead
3. **User + fly simultaneous work** — user edits in their repo, fly edits in its workspace, no conflicts
4. **Managed jj versioning** — Maverick bundles or pins its own jj binary, independent of user's system

## Open Questions

1. **jj binary management**: Bundle jj with Maverick? Use a pinned version via a package manager? Expect it on PATH?
2. **Workspace reuse**: Create a fresh workspace per fly session, or reuse across sessions? Fresh is simpler; reuse avoids bootstrap cost.
3. **Large repo performance**: `jj git clone` of a large repo could be slow. Investigate `--depth` or partial clone options.
4. **Secret handling**: The hidden workspace needs access to the same secrets/env as the user's repo for tests to pass. How to propagate `.env` safely?
5. **bd concurrency guarantees**: What locking/atomicity does bd's data store provide for concurrent producer/consumer access?
6. **Notification on eject**: Should `maverick fly` notify the user (via ntfy or similar) when land requires an eject decision?

## Relevant Codebase Locations

- `src/maverick/library/actions/jj.py` — current jj action wrappers (write-path)
- `src/maverick/git/` — current GitPython wrappers (read-path, to be replaced)
- `src/maverick/cli/commands/fly.py` — fly CLI entry point
- `src/maverick/cli/commands/land.py` — land CLI entry point
- `src/maverick/library/workflows/` — workflow YAML definitions
- `src/maverick/beads/` — bead models, client, speckit
- `src/maverick/runners/command.py` — CommandRunner for subprocess execution
