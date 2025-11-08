# Data Model: Automated Review & Fix Loop

## ReviewLoopInput
- **Description**: Activity input describing the target branch run context.
- **Fields**:
  - `branch_ref: str` – Fully qualified branch identifier (`origin/feature-x`); MUST be non-empty.
  - `commit_range: list[str]` – Ordered commit SHAs included in the review; MAY be empty to imply "HEAD only".
  - `implementation_summary: str | None` – Optional human-readable context from prior automation phases; trimmed to <= 2k characters.
  - `validation_command: list[str] | None` – Override for default validation (`uv run cargo test --all --locked`); when provided, MUST start with `uv` to satisfy constitution.
  - `retry_metadata: RetryMetadata | None` – Carries prior attempt fingerprints/results when retrying.
  - `enable_fixes: bool` – If `False`, activity only performs CodeRabbit review and emits findings.

## RetryMetadata
- **Description**: Records previous attempt context to support idempotent retries.
- **Fields**:
  - `previous_fingerprint: str` – Hex-encoded fingerprint from last run; MUST be 64 hex chars.
  - `attempt_counter: int` – Number of attempts already taken; MUST be >= 0.
  - `last_status: str` – Enum-like literal (`"clean" | "fixed" | "failed"`); ensures downstream comparison.
  - `artifacts_path: str | None` – Optional reference to persisted artifacts from prior run.

## CodeReviewFindings
- **Description**: Normalized result of running CodeRabbit CLI.
- **Fields**:
  - `issues: list[CodeReviewIssue]` – Structured list extracted from transcript; sorted by severity.
  - `transcript: str` – Full, raw transcript captured before sanitization for fingerprinting; stored securely.
  - `sanitized_prompt: str` – Transcript after redaction/truncation; safe to forward to OpenCode.
  - `summary: str` – Short summary text from CodeRabbit (first paragraph / CLI summary section).
  - `raw_hash: str` – SHA-256 hash of the raw transcript for auditing.
  - `generated_at: datetime` – Timestamp recorded via activity wall clock at capture time.

## CodeReviewIssue
- **Fields**:
  - `title: str` – Issue headline extracted from CLI.
  - `severity: Literal["blocker", "major", "minor"]` – Normalized severity buckets.
  - `details: str` – Supporting explanation, may include code fences.
  - `anchor: str | None` – Optional file/line reference from CLI output.

## FixAttemptRecord
- **Description**: Metadata describing an OpenCode remediation attempt.
- **Fields**:
  - `request_id: str` – Unique identifier returned by OpenCode CLI or generated UUID.
  - `sanitized_prompt: str` – Prompt sent to OpenCode (post-sanitization).
  - `applied_changes: list[str]` – List of files touched or commit SHAs produced by OpenCode.
  - `stdout: str` / `stderr: str` – Captured outputs with `errors='replace'`.
  - `exit_code: int` – CLI exit status.
  - `started_at: datetime` / `completed_at: datetime` – Activity wall-clock timestamps.

## ValidationResult
- **Description**: Outcome of validation command (default `cargo test`).
- **Fields**:
  - `command: list[str]` – Executed command (with `uv`).
  - `stdout: str`
  - `stderr: str`
  - `exit_code: int`
  - `started_at: datetime`
  - `completed_at: datetime`

## ReviewLoopOutcome
- **Description**: Activity result the workflow consumes.
- **Fields**:
  - `status: Literal["clean", "fixed", "failed"]` – Overall classification.
  - `issues_fixed: int` – Number of issues addressed in successful fix runs.
  - `code_review_findings: CodeReviewFindings | None` – Present when review completed.
  - `fix_attempt: FixAttemptRecord | None` – Populated when OpenCode ran.
  - `validation_result: ValidationResult | None` – Populated when validation executed.
  - `fingerprint: str` – Final fingerprint derived from commit range + findings.
  - `artifacts_path: str` – Reference for persisted logs/prompts.
  - `completed_at: datetime` – Activity wall-clock completion time.

## Relationships & Invariants
- A `ReviewLoopOutcome` MUST include `code_review_findings` unless the activity fails before CodeRabbit executes.
- When `status == "clean"`, `fix_attempt` MUST be `None` and `issues_fixed == 0`.
- When `status == "fixed"`, both `fix_attempt` and `validation_result` MUST be present and `issues_fixed > 0`.
- `RetryMetadata.previous_fingerprint` MUST equal `ReviewLoopOutcome.fingerprint` for skipped retries.
- `CodeReviewFindings.sanitized_prompt` MUST be a filtered version of `transcript`; any redactions are logged with metadata in the activity output.
