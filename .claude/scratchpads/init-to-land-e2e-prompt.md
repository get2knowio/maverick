# Maverick init → land e2e test against sample-maverick-project

You are picking up a paused e2e test on the `044-opencode-substrate` branch of `/workspaces/maverick`. The branch just landed a substantial cleanup pass (commit `32dcf44`) that wasn't yet exercised end-to-end. Goal: drive `maverick init → plan generate → refuel → fly → land` against `/workspaces/sample-maverick-project` and report what worked and what broke.

## State going in

- **Branch:** `044-opencode-substrate` at commit `32dcf44 refactor: pre-xoscar cleanup + cross-provider DEFAULT_TIERS`. 3,622 unit tests passing, mypy clean, ruff clean, branch is pushed.
- **Sample project:** `/workspaces/sample-maverick-project` — a Python project with an existing `greet` CLI. Use a feature branch (e.g. `003-version-flag-e2e`) so you don't touch `main`. Verify with `git remote -v` and `pwd` before any push.
- **OpenCode:** v1.14.x on PATH at `/home/vscode/.opencode/bin/opencode`. Five providers connected per `~/.local/share/opencode/auth.json`: `github-copilot`, `openai`, `openrouter`, `opencode-go`, plus the auto-connected `opencode` (Zen). The user pays per-token only on OpenRouter — every other provider is a flat-rate subscription.
- **`DEFAULT_TIERS`** (in `src/maverick/runtime/opencode/tiers.py`) now spreads load across `github-copilot`/`openai`/`opencode-go`/`opencode` for primary lanes and uses OpenRouter free models only as last-resort fallback. `maverick init` writes those tiers verbatim into the generated `maverick.yaml::provider_tiers.tiers`.

## What this run is validating

The cleanup changed several load-bearing surfaces. The e2e test is the first end-to-end exercise of the new code path. Specifically watch:

1. **OpenCode-driven init.** `init` now spawns `opencode serve`, hits `GET /provider`, populates `agent_providers:` from the connected list, and writes the cross-provider `DEFAULT_TIERS` into `provider_tiers:`. The legacy `--providers`/`--skip-providers`/`--models`/`--no-detect` flags are gone. Verify the generated yaml has 5 entries under `agent_providers:` and a populated `provider_tiers.tiers` block.
2. **Refuel duplicate-epic fix.** The supervisor's `BeadCreatorActor` is now the only writer of beads; the workflow consumes `epic_id` / `work_beads` / `created_map` from `ctx`. After refuel, `bd list --type epic` should show **one** new epic, not two.
3. **Cascade now covers Pydantic validation.** When a primary binding emits a payload that fails `result_model.model_validate(...)`, `_send_with_model` should fall over to the next binding instead of killing the call. (We saw this happen with gemini-3.1-pro-preview emitting `success_criteria: [null, null, ...]` in the prior run.) The new `DEFAULT_TIERS` puts `claude-sonnet-4.6` first for `generate`, so the gemini path is now the tertiary fallback — but if anything in your cascade still fails validation, watch for the cascade to engage.
4. **`Path.cwd()` purge.** Every bd action in `library/actions/beads.py` now requires an explicit `cwd=`. Workspace operations should write to the workspace's `.beads/`, not the user repo's. The "workspace identity mismatch" warning we saw last run should be **gone**.
5. **Fly `--auto-commit` on plain-git.** The user repo isn't jj-colocated. Last run, `--auto-commit` called `jj diff --stat` against the user repo and crashed. **This bug was NOT fixed in the cleanup pass** — it's still outstanding. Plan to commit user-repo changes manually before fly, or fix it as part of this run (Tier C bug #3 in the cleanup proposal).

## Reference: known issues from the previous attempt (paused 2026-05-02)

- A stale `maverick/sample-maverick-project` branch in the user repo blocks `plan generate`'s finalize step (jj's "Non-tracking remote bookmark" error). Delete with `cd /workspaces/sample-maverick-project && git branch -D maverick/sample-maverick-project` if it exists.
- `maverick workspace clean --yes` reports success but doesn't always remove `~/.maverick/workspaces/sample-maverick-project/`. Force it with `rm -rf ~/.maverick/workspaces/sample-maverick-project` if you see "active" state lingering.
- `.beads/backup/backup_state.json` and `.maverick/runs/<run-id>/metadata.json` get touched by every bd / workflow run. They're tracked but `.gitignore`'d patterns may catch them — easiest is to commit them along with the test setup.

## Suggested test scope

Use a **small additive PRD** to keep fly bounded — last attempt used a `--version` flag (~2 beads, ~15min). The PRD `docs/version-flag-prd.md` already exists in the sample project from the prior attempt; reuse it or write your own. Don't redo the full greet CLI — that's an 8-bead, multi-hour run.

## Step plan

```bash
# Setup
cd /workspaces/sample-maverick-project
git checkout main && git pull
git checkout -b 003-version-flag-e2e
git branch -D maverick/sample-maverick-project 2>/dev/null  # cleanup stale ref
rm -rf ~/.maverick/workspaces/sample-maverick-project       # cleanup stale workspace
rm -f maverick.yaml                                          # force fresh init

# 1. Init
uv run --project /workspaces/maverick maverick init --force -v
# Verify: agent_providers has 5 entries (github-copilot/openai/openrouter/opencode-go/opencode),
# provider_tiers.tiers has 5 roles each with 4 bindings, NO actors: block.
cat maverick.yaml | head -80

# 2. Doctor — sanity check provider connectivity
uv run --project /workspaces/maverick maverick doctor

# 3. Plan generate
uv run --project /workspaces/maverick maverick plan generate add-version-flag \
    --from-prd docs/version-flag-prd.md --skip-briefing
# Verify: plan generated successfully (was failing on gemini before the fix)

# 4. Refuel
uv run --project /workspaces/maverick maverick refuel add-version-flag
# Verify: bd list --type epic shows ONE epic for add-version-flag, not two
bd list --type epic

# 5. Fly
# NOTE: --auto-commit assumes jj-colocated user repo; sample is plain git.
# Either commit pending churn manually, or skip --auto-commit and clean the tree first.
git add -A && git commit -m "chore: e2e test setup" || true
EPIC_ID=$(bd list --type epic --json | jq -r '.[] | select(.title=="add-version-flag") | .id')
uv run --project /workspaces/maverick maverick fly --epic "$EPIC_ID" --max-beads 5

# 6. Land
uv run --project /workspaces/maverick maverick land --yes
```

## What to report

Capture and report:
1. **Did each stage succeed?** init, doctor, plan generate, refuel, fly, land — pass/fail per stage with the failing step name and error.
2. **Provider distribution.** Cost telemetry per actor: which provider/model each call landed on (look for `opencode_actor.cost` log lines or `.maverick/runs/<run>/cost-telemetry.jsonl`). The point of the cross-provider cascade is load distribution — verify it actually happened.
3. **Single epic per refuel.** Confirm with `bd list --type epic`. If two epics appear, the duplicate-epic fix regressed.
4. **Cascade engagement.** If any tier's primary binding failed (auth, model-not-found, validation), did the cascade fall over and complete the call? Grep verbose logs for `opencode.cascade_fallback`.
5. **Workspace isolation.** Are there any `workspace identity mismatch` warnings? There shouldn't be.
6. **Anything else surprising.** New bugs, unhelpful error messages, opportunities for cleanup.

## Constraints

- **Don't push the sample project's test branch** unless the user explicitly asks. Keep it local.
- **Don't merge into main** of either repo.
- If you find a bug in maverick code, fix it and add a regression test — but pause to confirm if the fix is more than ~50 LOC or touches the cascade/init/refuel core.
- The user wants a tight, reproducible cycle. Keep the PRD minimal (~1-2 beads). If fly takes more than 30 minutes, stop and reduce scope.

## Architecture pointers (CLAUDE.md is canonical)

- `src/maverick/runtime/opencode/tiers.py::DEFAULT_TIERS` — the cascade map.
- `src/maverick/init/opencode_discovery.py` — new `/provider`-driven discovery.
- `src/maverick/init/config_generator.py::generate_config` — yaml synthesis.
- `src/maverick/workflows/refuel_maverick/workflow.py` — refuel flow (line ~536 onward is the post-decompose bookkeeping that consumes supervisor's bead-creation outputs from `ctx`).
- `src/maverick/actors/xoscar/refuel_supervisor.py` + `bead_creator.py` — supervisor side.
- `src/maverick/library/actions/beads.py` — bd actions, all now require `cwd=`.
- `src/maverick/actors/xoscar/opencode_mixin.py::_send_with_model` — cascade with embedded payload validation hook.

Read CLAUDE.md once before you start — Architectural Guardrail 7 (workspace isolation) is the rule that drove the `Path.cwd()` purge.
