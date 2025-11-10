# Quickstart: PR CI Automation

## Prerequisites
- Temporal worker environment with Python 3.11 and `uv` installed.
- Authenticated GitHub CLI (`gh auth status` succeeds for the target repository).
- Access to the `001-pr-ci-automation` Temporal workflow deployment branch.

## Setup
1. Install dependencies: `uv sync` (from repository root).
2. Export required environment variables:
   - `TEMPORAL_HOST` (e.g., `localhost:7233` for dev).
   - `TEMPORAL_CONNECTION_TIMEOUT` (seconds, default `10`).
   - `GITHUB_REPOSITORY` (e.g., `owner/name`).
3. Ensure the Temporal dev server (or target namespace) is running.

## Running Tests
- Unit tests: `timeout 15 uv run pytest tests/unit/test_pr_ci_automation_activity.py` (to be added with implementation).
- Integration tests: `timeout 15 uv run pytest tests/integration/test_pr_ci_automation_workflow.py`.
- Linting: `uv run ruff check .`.

## Execution
1. Start the Temporal worker: `uv run python -m src.workers.main`.
2. Trigger the workflow phase that invokes the PR CI automation activity (via existing orchestration or Temporal CLI).
3. Monitor worker logs for structured entries:
   - `ci_poll_started`
   - `ci_poll_update`
   - `ci_poll_completed`
   - `pr_merge_attempt`

## Flow Examples

### Success Flow (Merged PR)

**Scenario**: CI passes, PR merges automatically

1. **Branch Validation**: Activity checks source branch exists on remote
2. **Target Resolution**: Resolves default branch or uses explicit target
3. **PR Discovery/Creation**: Finds existing PR or creates new one
4. **Base Branch Validation**: Confirms PR targets the correct base branch
5. **CI Polling**: Monitors checks with exponential backoff
   - Logs: `ci_poll_started`, `ci_poll_update` (per poll)
   - Detects: All checks completed successfully
6. **Merge Execution**: Merges PR using `gh pr merge --merge --auto`
7. **Result**: Returns `status="merged"` with merge commit SHA
   - Example log: `pr_merge_sla_metrics` with merge duration

**Expected Output**:
```python
PullRequestAutomationResult(
    status="merged",
    pull_request_number=123,
    pull_request_url="https://github.com/owner/repo/pull/123",
    merge_commit_sha="abc123def456...",
    polling_duration_seconds=120,
)
```

**Logs to monitor**:
- `pr_ci_automation_started` → activity begins
- `remote_branch_checked` → source branch validated
- `existing_pr_found` or `pr_created` → PR ready
- `base_branch_validated` → target alignment confirmed
- `ci_poll_started` → polling begins
- `ci_poll_update` → status checks (periodic)
- `ci_poll_completed_success` → all checks passed
- `pull_request_merged` → merge completed
- `pr_merge_sla_metrics` → merge timing recorded

---

### Failure Flow (CI Fails)

**Scenario**: One or more CI checks fail

1. **Branch Validation**: Confirms source branch exists
2. **PR Discovery/Creation**: Reuses or creates PR
3. **CI Polling**: Detects failing checks
   - Parses check names, statuses, log URLs
   - Aggregates failures by job name (latest attempt only)
4. **Result**: Returns `status="ci_failed"` with failure details
   - No merge attempt occurs

**Expected Output**:
```python
PullRequestAutomationResult(
    status="ci_failed",
    pull_request_number=123,
    pull_request_url="https://github.com/owner/repo/pull/123",
    polling_duration_seconds=90,
    ci_failures=[
        CiFailureDetail(
            job_name="build",
            attempt=1,
            status="failure",
            summary="failure",
            log_url="https://github.com/owner/repo/actions/runs/123456",
            completed_at=datetime(...),
        ),
    ],
)
```

**Logs to monitor**:
- `pr_ci_automation_started`
- `remote_branch_checked`
- `existing_pr_found` or `pr_created`
- `base_branch_validated`
- `ci_poll_started`
- `ci_poll_update` (shows `ci_status="in_progress"` then `"failure"`)
- `ci_poll_completed_failure` → failure detected
- `ci_poll_sla_metrics` → polling duration recorded

**Downstream Action**:
- Workflow can invoke remediation phase with `ci_failures` evidence
- Logs and URLs enable automated or manual debugging

---

### Timeout Flow (CI Incomplete)

**Scenario**: CI checks don't complete within timeout (default: 45 minutes)

1. **Branch Validation**: Confirms source branch exists
2. **PR Discovery/Creation**: Reuses or creates PR
3. **CI Polling**: Monitors until timeout exceeded
   - Checks remain in `queued` or `in_progress` state
4. **Result**: Returns `status="timeout"` with elapsed time
   - No merge or failure classification

**Expected Output**:
```python
PullRequestAutomationResult(
    status="timeout",
    pull_request_number=123,
    pull_request_url="https://github.com/owner/repo/pull/123",
    polling_duration_seconds=2700,  # 45 minutes
    retry_advice="CI checks did not complete within timeout",
)
```

**Logs to monitor**:
- `pr_ci_automation_started`
- `remote_branch_checked`
- `existing_pr_found` or `pr_created`
- `base_branch_validated`
- `ci_poll_started`
- `ci_poll_update` (multiple, showing elapsed time)
- `ci_poll_timeout` → timeout exceeded

**Downstream Action**:
- Workflow can decide to retry with extended timeout
- Manual investigation via `gh pr checks <pr_number>`

---

### Error Flow (Base Branch Mismatch)

**Scenario**: PR targets different base than workflow expects

1. **Branch Validation**: Confirms source branch exists
2. **PR Discovery**: Finds existing PR
3. **Base Branch Validation**: Detects mismatch
   - Expected: `main`
   - Actual: `develop`
4. **Result**: Returns `status="error"` with clear message
   - No polling or merge occurs

**Expected Output**:
```python
PullRequestAutomationResult(
    status="error",
    pull_request_number=123,
    pull_request_url="https://github.com/owner/repo/pull/123",
    polling_duration_seconds=0,
    error_detail="Base branch mismatch: PR targets 'develop' but expected 'main'",
    retry_advice="Update target branch to match PR base",
)
```

**Logs to monitor**:
- `pr_ci_automation_started`
- `remote_branch_checked`
- `existing_pr_found`
- `base_branch_mismatch` → validation failed
- `base_branch_validation_error`

**Downstream Action**:
- Workflow should surface error to operator
- Operator updates PR base branch or workflow target parameter

---

### Resume Flow (Idempotent Rerun)

**Scenario**: Activity rerun after interruption or workflow replay

1. **Branch Validation**: Confirms source branch (idempotent check)
2. **PR Discovery**: Finds existing PR (no duplicate creation)
   - Log: `existing_pr_found`
3. **Base Branch Validation**: Confirms alignment (cached result)
4. **Description Update**: Updates PR body if summary changed
   - Non-blocking operation
5. **CI Polling**: Resumes from current state
   - If already merged: Polling short-circuits with existing merge SHA
   - If in progress: Polls from fresh state
6. **Result**: Consistent output regardless of rerun count

**Key Behaviors**:
- **PR Creation**: `find_or_create_pr` always checks for existing PR first
- **Description Updates**: `update_pr_description` is non-blocking (logs warnings on failure)
- **Merge Detection**: Polling detects already-merged PRs and returns success
- **Deterministic Results**: Same inputs yield same outputs across replays

**Logs to monitor**:
- `existing_pr_found` → PR reused (not recreated)
- `pr_description_updated` or `pr_description_update_failed` → non-blocking update
- Polling logs show resumed state

---

## Troubleshooting

### Rate Limits
- **Symptom**: `gh` commands return rate-limit errors
- **Solution**: Verify PAT scopes and network stability
- **Behavior**: Activity auto-retries within configured budget before returning `error` or `timeout`

### Timeouts
- **Symptom**: Activity returns `status="timeout"`
- **Solution**: 
  - Inspect `polling_duration_seconds` in result payload
  - Run `gh pr checks <pr_number>` to check current CI state
  - Consider increasing `polling.timeout_minutes` in request
- **Common Causes**: Slow CI infrastructure, stuck jobs, misconfigured workflows

### Base Branch Mismatches
- **Symptom**: Activity returns `status="error"` with "Base branch mismatch" message
- **Solution**: 
  - Update PR base branch via `gh pr edit <pr_number> --base <target>`
  - Or update workflow's `target_branch` parameter to match PR
- **Prevention**: Ensure consistent branch naming across workflow and PR

### Missing Source Branch
- **Symptom**: Activity returns `status="error"` with "Source branch not found on remote"
- **Solution**: 
  - Verify branch exists: `git ls-remote --heads origin <branch>`
  - Push branch to remote: `git push origin <branch>`
- **Common Cause**: Local branch not pushed to remote before automation

### CI Never Completes
- **Symptom**: Timeout status with checks stuck in `queued` or `in_progress`
- **Solution**:
  - Check GitHub Actions runner availability
  - Verify workflow YAML syntax and trigger conditions
  - Review GitHub Actions usage limits for account
- **Investigation**: Use `gh run view <run_id>` to inspect specific runs

### Merge Failures
- **Symptom**: Activity returns `status="error"` after successful CI polling
- **Solution**:
  - Check PR mergeable state: `gh pr view <pr_number> --json mergeable`
  - Resolve merge conflicts manually
  - Ensure required status checks are configured correctly
- **Logs**: Search for `merge_execution_failed` in worker logs
