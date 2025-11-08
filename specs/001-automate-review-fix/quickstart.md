# Quickstart: Automated Review & Fix Loop

## Prerequisites
- Temporal worker environment with Python 3.11, uv, CodeRabbit CLI, OpenCode CLI, and Rust toolchain installed.
- Auth tokens for CodeRabbit and OpenCode configured via environment variables consumed by their CLIs.
- Feature branch with AI-generated Rust changes pushed to remote.
- Temporal server running and accessible (default: localhost:7233)

## Run the Activity Through Temporal Workflow

### Via Phase Automation Workflow
The review-fix activity is integrated into the phase automation workflow:

```bash
# Start the Temporal worker (in one terminal)
uv run python -m src.workers.main

# Trigger workflow with review-fix phase (in another terminal)
uv run python -m src.cli.readiness \
  --repo github.com/owner/repo \
  --branch feature-ai-fixes \
  --phases review-fix
```

The workflow orchestrates the activity execution with proper error handling and retry logic.

## Manual Activity Testing (Development)

### 1. Create Input Payload
Create a JSON file (e.g., `payload.json`) with the activity input:

```json
{
  "branch_ref": "origin/feature-ai-fixes",
  "commit_range": ["abc1234", "def5678"],
  "implementation_summary": "Auto-generated fixes for telemetry module",
  "validation_command": null,
  "retry_metadata": null,
  "enable_fixes": true
}
```

### 2. Test via Python REPL or Script
The CLI stub (`src/cli/review_fix.py`) is a placeholder. For development testing:

```python
import asyncio
from src.activities.review_fix import run_review_fix_loop
from src.models.review_fix import ReviewLoopInput

async def test_activity():
    input_data = ReviewLoopInput(
        branch_ref="origin/feature-ai-fixes",
        commit_range=["abc1234", "def5678"],
        implementation_summary="Test invocation",
        validation_command=None,
        retry_metadata=None,
        enable_fixes=True
    )
    
    outcome = await run_review_fix_loop(input_data)
    print(f"Status: {outcome.status}")
    print(f"Issues fixed: {outcome.issues_fixed}")
    print(f"Fingerprint: {outcome.fingerprint}")
    print(f"Artifacts: {outcome.artifacts_path}")
    
    return outcome

# Run the test
result = asyncio.run(test_activity())
```

### 3. Inspect Artifacts
Artifacts are stored in `/tmp/maverick-artifacts/{fingerprint}/`:

- `sanitized_prompt_{fingerprint}.txt` - Sanitized CodeRabbit findings
- `fix_summary_{fingerprint}.txt` - OpenCode execution summary
- `diagnostics_{fingerprint}.txt` - Failure diagnostics (if status="failed")
- `review_outcome.json` - Complete outcome structure

```bash
# View artifacts for a specific run
FINGERPRINT="abc123..."
ls -la /tmp/maverick-artifacts/${FINGERPRINT}/
cat /tmp/maverick-artifacts/${FINGERPRINT}/review_outcome.json
```

## Expected Outcomes
- `status="clean"` - CodeRabbit found no actionable issues
- `status="fixed"` - OpenCode applied fixes and validation passed
- `status="failed"` - Any step failed (check diagnostics file)

## Retry Workflow

### Automatic Retry Detection
The activity automatically detects duplicate retries:

```python
input_with_retry = ReviewLoopInput(
    branch_ref="origin/feature-ai-fixes",
    commit_range=["abc1234", "def5678"],
    retry_metadata={
        "previous_fingerprint": "0123abcd...",
        "attempt_counter": 1,
        "last_status": "failed",
        "artifacts_path": "/tmp/maverick-artifacts/0123abcd..."
    },
    enable_fixes=True
)

# If fingerprint matches, returns cached result immediately
outcome = await run_review_fix_loop(input_with_retry)
```

### Retry Behavior
1. **Fingerprint computation**: Based on commit range + findings hash
2. **Duplicate detection**: If fingerprint matches retry_metadata, return cached result
3. **Fresh retry**: If fingerprint differs, proceed with full execution

## Validation Command Override

Override the default validation command (`uv run cargo test --all --locked`):

```python
input_data = ReviewLoopInput(
    branch_ref="origin/feature-ai-fixes",
    commit_range=["abc1234"],
    validation_command=["uv", "run", "cargo", "nextest", "run", "--all"],
    enable_fixes=True
)
```

**Important**: Commands MUST start with `uv` per development constitution.

## Review-Only Mode

Disable automatic fixes to only review code:

```python
input_data = ReviewLoopInput(
    branch_ref="origin/feature-ai-fixes",
    commit_range=["abc1234"],
    enable_fixes=False  # Only run CodeRabbit, no OpenCode
)

outcome = await run_review_fix_loop(input_data)
# outcome.status will be "clean" or "failed" (never "fixed")
# outcome.fix_attempt will be None
```

## Troubleshooting

### CLI Not Found Errors
Ensure CodeRabbit and OpenCode CLIs are installed and on PATH:
```bash
which coderabbit
which opencode
```

### Timeout Issues
Default timeouts:
- CodeRabbit: 120 seconds
- OpenCode: 300 seconds  
- Validation: 600 seconds

Adjust in `src/activities/review_fix.py` if needed.

### Permission Errors
Ensure `/tmp/maverick-artifacts` directory is writable:
```bash
mkdir -p /tmp/maverick-artifacts
chmod 755 /tmp/maverick-artifacts
```

### Viewing Structured Logs
The activity emits structured JSON logs via `src/utils/logging`:
```bash
# Filter activity logs
grep "activity.review_fix" worker.log | jq .
```
