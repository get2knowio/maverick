# Data Model: PR CI Automation

## Entities

### PullRequestAutomationRequest
- **Description**: Input payload supplied by the workflow to drive PR integration.
- **Fields**:
  - `source_branch` (str, required): Git branch containing AI-authored changes.
  - `target_branch` (str, optional, default `main`): Merge destination specified by workflow.
  - `summary` (str, required): AI-generated PR description body.
  - `workflow_attempt_id` (str, required): Temporal workflow attempt identifier for idempotency keys.
  - `polling` (`PollingConfiguration`, optional): Overrides for interval/backoff/timeout behavior.
  - `metadata` (dict[str, str], optional): Arbitrary key-value context passed through to logging/metrics.

### PollingConfiguration
- **Description**: Caller-provided overrides for polling cadence and retry behavior.
- **Fields**:
  - `interval_seconds` (int, default 30): Delay between status polls; MUST be >0.
  - `timeout_minutes` (int, default 45): Maximum duration to wait for CI terminal state; MUST be >0.
  - `max_retries` (int, default 5): Upper bound on transient retry attempts before surfacing failure.
  - `backoff_coefficient` (float, default 2.0): Multiplier for exponential backoff when handling transient errors; MUST be ≥1.

### PullRequestAutomationResult
- **Description**: Deterministic activity response provided to downstream workflow phases.
- **Fields**:
  - `status` (`Literal["merged", "ci_failed", "timeout", "error"]`, required): Terminal outcome category.
  - `pull_request_number` (int, optional): Numeric identifier when PR exists.
  - `pull_request_url` (str, optional): Web URL for PR when available.
  - `merge_commit_sha` (str, optional): SHA recorded when status is `merged`.
  - `ci_failures` (list[`CiFailureDetail`], optional): Present when status is `ci_failed`.
  - `polling_duration_seconds` (int, required): Time spent from first poll to terminal outcome.
  - `retry_advice` (str, optional): Machine-readable guidance for remediation or retriable failures.
  - `error_detail` (str, optional): Human-readable error when status is `error`.

### CiFailureDetail
- **Description**: Per-job failure record returned to remediation workflows.
- **Fields**:
  - `job_name` (str, required): GitHub Actions job name.
  - `attempt` (int, required): Latest attempt index observed for the job.
  - `status` (`Literal["queued", "in_progress", "failure", "cancelled", "timed_out"]`, required): Terminal or current job status.
  - `summary` (str, optional): Short description or conclusion string from GitHub.
  - `log_url` (str, optional): Direct link to job logs or artifacts.
  - `completed_at` (datetime, optional): ISO 8601 timestamp of latest attempt completion.

## Relationships & Invariants

- `PullRequestAutomationRequest.polling` references a `PollingConfiguration` struct; when omitted, defaults MUST be applied inside the activity.
- `PullRequestAutomationResult.ci_failures` MUST be empty unless `status == "ci_failed"`.
- `PullRequestAutomationResult.merge_commit_sha` MUST be populated when `status == "merged"`.
- `PullRequestAutomationResult.error_detail` MUST be populated when `status == "error"`.
- `CiFailureDetail.log_url` SHOULD point to the latest attempt's logs when available; omit rather than provide stale URLs.
- Status transitions: `merged`, `ci_failed`, `timeout`, and `error` are mutually exclusive terminal states. Once returned, the workflow MUST treat the activity as complete and decide follow-up behavior.
