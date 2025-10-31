description: Perform a non-destructive functional and code-quality review scoped to current-branch changes (diff vs default) and the attached spec folder, enforcing Temporal determinism, CLI safety, and tasks/FR compliance.
---

You are the sole senior reviewer for this branch. Perform a complete functional and code quality review against the referenced specs. Your review gates merge.

Assumptions
- Scope: Review ONLY files changed on the current branch relative to the default branch, plus any new/modified files under `SPECS_ROOT`. Do not review unrelated files.
- Exactly one spec folder is attached under `#file:specs`.
- Infer `SPEC_ID` as the single child directory name under `#file:specs` and treat that folder as `SPECS_ROOT`.

Codebase layout target: `src/` (workflows, activities, models, workers, utils), `tests/` (unit, integration, contract)

## Reference Specs

Using the attached specs directory:
- Treat `SPECS_ROOT` as the only folder under `#file:specs`.
- Files to review within `SPECS_ROOT`:
  - `plan.md`
  - `spec.md`
  - `data-model.md`
  - `contracts/openapi.yaml` (if present)
  - `research.md`
  - `quickstart.md`
  - `tasks.md`

## Objectives

- Verify functional compliance with user stories and the FR list defined in the Spec (e.g., FR-001..FR-0NN).
- Enforce Temporal determinism and clean separation of concerns.
- Ensure robust, secure CLI/tool usage per spec (e.g., gh CLI), with correct error taxonomy.
- Validate code quality (Python 3.11), typing, structure, and observability.
- Confirm tasks in `tasks.md` are implemented or call out precise gaps.
- Apply all objectives strictly within the changed-file scope defined above; issues outside this scope are out-of-scope unless they are direct regressions introduced by the changed code.

## How To Review

- Read all spec files under `SPECS_ROOT`; treat them as the source of truth.
- Determine the changed files vs the default branch and limit exploration to those paths (and any directly invoked code they touch if strictly necessary for understanding/regression assessment).
- Run basic quality checks scoped to changed files only (preferring uv):
  - Run tests only for changed test files or tests directly exercising changed code; skip or xfail network-bound tests if needed.
  - Run linting only on changed files; report issues outside this set as out-of-scope unless caused by the change.
- If a git diff isn’t available in the environment, limit scope to code directly referenced by `SPECS_ROOT` and any new/modified files within it.
- If running isn’t possible, do a static review and note runtime validation steps.

## Functional Checklist

Apply ONLY within the changed-file scope; adjust or mark N/A to match the spec’s functional scope.

- Parameters (FR-…)
  - Workflow accepts parameters (e.g., `dict[str, Any]`) with required keys per spec (e.g., `github_repo_url`).
  - Typed accessor utility enforces required keys; clear error on missing/invalid.
- URL/Input Validation & Normalization (FR-…)
  - Accept expected input formats (e.g., HTTPS/SSH for GitHub) and reject unsupported hosts unless allowed by research.
  - Normalize to canonical pieces (e.g., `host`, `owner/repo`) before any external call.
- Verification Gate (FR-…)
  - Verification happens before dependent steps; failure halts workflow early.
- Auth Pre-checks (FR-…)
  - For external tools/services (e.g., `gh auth status` or host-specific auth), fail with actionable guidance if unauthenticated.
- Verification Command/Call
  - Uses documented, supported flags/arguments.
  - Interprets exit codes and stderr/stdout to distinguish `not_found`, `access_denied`, `transient_error`, etc.
- Error Taxonomy & Messaging (FR-…)
  - Result model has error_code like `none|validation_error|auth_error|not_found|access_denied|transient_error` (or as defined by spec).
  - Messages are actionable and do not leak secrets.
- Retry & Timeouts (FR-…)
  - Exactly one retry on transient errors with small backoff; per-attempt timeouts (~2s or as spec’d).
  - p95 ≤ target in spec is feasible from code paths and settings.
- Observability (FR-…)
  - Structured logs for start, normalized inputs, auth status, attempts, duration, status, error_code.
- User Stories
  - US1 (P1): Focus slice works independently.
  - US2 (P2): Steps access parameters via accessor; example step present.
  - US3 (P3): Clear failure handling; early halt; accurate state transitions.

## Temporal & Architecture Checklist

- Workflow code is deterministic: no direct I/O, system time, random; use `workflow.now()` and `workflow.random()` as needed.
- All network/CLI calls reside in activities only.
- Proper Temporal annotations (`@workflow.defn`, `@activity.defn`); specify `result_type` when deserializing dataclasses.
- Worker registers all workflows and activities in `src/workers/main.py` with a unified task queue.
- Clean file layout: `src/workflows/`, `src/activities/`, `src/models/`, `src/workers/`, `src/utils/`.

## Security & Robustness

- Shelling to external tools is safely quoted; no injection via user-controlled inputs.
- Input validation rejects malformed inputs early; logs do not leak secrets/tokens.
- Defensive parsing: handle `.git` suffix, redirects as spec-appropriate; reject unsupported hosts with validation errors.
- Subprocess decoding uses `errors='replace'` to avoid UnicodeDecodeError.

## Code Quality

- Python 3.11; consistent typing, dataclasses, and `Literal` statuses where appropriate.
- Small, cohesive functions; clear names; docstrings where helpful.
- No unused code; no dead config; `ruff` clean or justified suppressions.
- Logging via structured logger for activities/workers; workflows use `workflow.logger` only.

## Contracts Alignment (if applicable)

If the spec includes an HTTP API, align endpoints to `contracts/openapi.yaml`:
- `POST /workflows/start` aligns with parameters + initial domain result.
- `GET /workflows/{run_id}` returns state and domain result (e.g., `VerificationResult`).
- If API is out-of-scope for MVP, note deferral and ensure no conflicting scaffolds.

## Quickstart Validation

- Steps in `quickstart.md` match current code:
  - Worker entrypoint `src/workers/main.py` runs.
  - Behavior descriptions match logs and outcomes (by static reasoning if not executed).

## Tasks Coverage

- Cross-check all items in `tasks.md` against implementation.
- For incomplete items, list exact file deltas to complete MVP (prioritize P1/US1).

## Deliverables (Your Output)

- Summary: pass/fail for functional compliance and code quality.
- Blocking issues: list with exact locations and fixes.
- Non-blocking recommendations: list with rationale.
- Spec traceability: for each FR and each user story, cite evidence or specify the gap.
- If passing: brief merge recommendation and any post-merge hardening tasks.
- AI-fix prompts: a series of atomic prompts (one per issue) that an AI agent can use to implement fixes. Each prompt must contain a clear explanation of the problem and exactly one recommended fix.

## Issue Format

- Severity: [BLOCKER|MAJOR|MINOR]
- Category: [Functional|Temporal|Security|Performance|Quality|Style|Docs]
- Location: path:line (e.g., `src/activities/repo_verification.py:42`)
- Reference: FR/US/Spec section (e.g., `FR-010`, `US1`)
- Problem: concise description
- Fix: actionable change (exact code or config where possible)

### Example

- BLOCKER | Functional | src/workflows/repo_verification_workflow.py:35 | FR-003
  - Problem: Workflow proceeds to next step even when verification fails.
  - Fix: Branch on `VerificationResult.status == "fail"` → set state to failed and return early.

## AI Agent Fix Prompts Output

At the end of your review, output a section titled "Prompts for AI agent" that contains a series of prompts—one prompt per issue—to drive an automated fixing agent. These prompts are in addition to the standard issue list and MUST follow the rules below.

### Rules for AI-fix prompts

- One prompt per issue; keep each prompt atomic and focused on a single change.
- Each prompt MUST include:
  - Title: `[Severity] | [Category] | path:line | FR/US ref` — short descriptive name
  - Problem: 1–3 sentences explaining what is wrong and why it violates the spec/guidelines (cite FR/US or best practice)
  - Recommended fix: one concrete change with precise file path(s), location hints, and exact code or configuration guidance. Avoid multi-step or alternative branches.
  - Acceptance criteria: 2–3 bullets describing how to verify the fix (tests, lints, determinism conditions)
  - Constraints: reiterate relevant constraints (e.g., Temporal determinism, logging rules, CLI safety)
- Do not include multiple fixes in a single prompt; split into separate prompts if needed.
- Keep prompts self-contained—no external context required beyond repository files and the cited spec reference.

### Output format

- Start the section with `### Prompts for AI agent`.
- Enumerate prompts as `Prompt 1`, `Prompt 2`, …
- For each prompt, use this template:

Prompt N
- Title: [SEVERITY | CATEGORY | path:line | FR/US]
- Problem: <clear, concise explanation>
- Recommended fix: <single, concrete change with exact file path and code/config guidance>
- Acceptance criteria:
  - <criterion 1>
  - <criterion 2>
  - <criterion 3 (optional)>
- Constraints: <e.g., use workflow.now(), specify result_type, tolerant decoding>

### Example AI-fix prompt

Prompt 1
- Title: BLOCKER | Temporal | src/workflows/readiness.py:42 | FR-010 — Non-deterministic time source
- Problem: The workflow calls `datetime.now()` directly, which violates Temporal determinism and will fail on replay.
- Recommended fix: In `src/workflows/readiness.py`, replace `datetime.now()` with `workflow.now()` and compute durations using `(workflow.now() - start_time).total_seconds()`.
- Acceptance criteria:
  - No direct `time.time()` or `datetime.now()` calls remain in workflow code.
  - Unit tests pass and any determinism-related tests/linters succeed.
  - Logs show timing derived from `workflow.now()`.
- Constraints: Workflow code must not perform direct I/O or use non-deterministic sources; use `workflow.logger` for logging.
