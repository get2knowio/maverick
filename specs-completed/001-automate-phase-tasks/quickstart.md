# Quickstart: Automated Phase Execution

## Prerequisites
- **Temporal Server**: Running locally (via `temporal server start-dev` or Docker Compose)
- **Dependencies**: Installed via `uv sync`
- **Speckit CLI**: `speckit.implement` command available and configured with necessary credentials
- **Repository**: Git repository with a properly formatted `tasks.md` file

## Setup

```bash
cd /workspaces/maverick
uv sync
```

## Start Temporal Infrastructure

**Option 1: Temporal CLI (Development)**
```bash
temporal server start-dev
```

**Option 2: Docker Compose (Production-like)**
```bash
# Uses docker-compose.yml in project root
docker-compose up -d
```

## Start the Worker

In a separate terminal:
```bash
uv run python -m src.workers.main
```

This worker registers all Temporal workflows and activities, including:
- `AutomatePhaseTasksWorkflow` - Phase automation orchestration
- `parse_tasks_md` - Task file parsing activity
- `run_phase` - Phase execution activity via speckit.implement
- `persist_phase_result` - Result persistence activity

## Execute Workflow

### Basic Usage

```bash
uv run python -m src.cli.readiness --workflow automate-phase-tasks \
  --tasks-md-path /path/to/specs/feature/tasks.md \
  --repo-path /path/to/repository \
  --branch feature-branch
```

### With Custom AI Settings

```bash
uv run python -m src.cli.readiness --workflow automate-phase-tasks \
  --tasks-md-path /path/to/specs/feature/tasks.md \
  --repo-path /path/to/repository \
  --branch feature-branch \
  --default-model "gpt-4" \
  --default-agent-profile "senior-engineer"
```

### With Custom Timeout and Retry Policy

```bash
uv run python -m src.cli.readiness --workflow automate-phase-tasks \
  --tasks-md-path /path/to/specs/feature/tasks.md \
  --repo-path /path/to/repository \
  --branch feature-branch \
  --timeout-minutes 45 \
  --retry-max-attempts 3
```

**Note**: The workflow accepts either a file path (`--tasks-md-path`) or file content inline. File path is recommended for standard usage.

## Resume After Failure

If a phase fails or times out:

1. **Review the failure**: Check logs or persisted phase results
2. **Fix the issue**: Address the root cause (code, configuration, etc.)
3. **Re-run the same command**: The workflow automatically:
   - Detects completed phases (via task checkboxes in `tasks.md`)
   - Skips completed work
   - Resumes from the first incomplete phase
   - Recalculates checkpoints if document content changed

```bash
# Same command - workflow handles resume automatically
uv run python -m src.cli.readiness --workflow automate-phase-tasks \
  --tasks-md-path /path/to/specs/feature/tasks.md \
  --repo-path /path/to/repository \
  --branch feature-branch
```

### Resume Behavior

| Scenario | Workflow Action |
|----------|----------------|
| No checkpoint exists | Run all phases from beginning |
| Checkpoint hash matches | Skip completed phases, resume from next |
| Checkpoint hash differs | Recalculate checkpoint from current `tasks.md`, resume from first incomplete |

**Hash Drift Detection**: The workflow detects when `tasks.md` content changes between runs and automatically recalculates which phases are complete by checking task checkboxes.

## Inspect Results

### Per-Phase JSON Results

Results are persisted to `/tmp/phase-results/<workflow-id>/<phase-id>.json`:

```bash
# View results for a specific phase
cat /tmp/phase-results/<workflow-id>/phase-1.json

# View all results for a workflow
ls -la /tmp/phase-results/<workflow-id>/
```

**Result Structure**:
```json
{
  "phase_id": "phase-1",
  "status": "success",
  "completed_task_ids": ["T001", "T002", "T003"],
  "started_at": "2025-11-08T10:30:00Z",
  "finished_at": "2025-11-08T10:35:00Z",
  "duration_ms": 300000,
  "tasks_md_hash": "abc123...",
  "stdout_path": "/workspaces/maverick/logs/phase-results/phase-1/stdout-20251108T103000.log",
  "stderr_path": "/workspaces/maverick/logs/phase-results/phase-1/stderr-20251108T103000.log",
  "artifact_paths": [...],
  "summary": ["Phase completed successfully", "..."],
  "error": null
}
```

### Workflow Results via Temporal CLI

```bash
# List workflow executions
temporal workflow list --namespace default

# Get workflow result
temporal workflow show --workflow-id <workflow-id> --namespace default
```

### Structured Logs

Activity and worker logs are emitted as structured JSON:

```bash
# View worker logs (if redirected to file)
tail -f /tmp/maverick-worker.log | jq .

# Filter for specific events
tail -f /tmp/maverick-worker.log | jq 'select(.event == "phase_activity_succeeded")'
```

## Testing

### Unit Tests

```bash
# Test parsing logic
timeout 15 uv run pytest tests/unit/test_phase_tasks_parser.py

# Test phase automation models
timeout 15 uv run pytest tests/unit/test_phase_automation_models.py

# Test markdown utilities
timeout 15 uv run pytest tests/unit/test_tasks_markdown_utils.py

# Test phase results storage
timeout 15 uv run pytest tests/unit/test_phase_results_store.py

# Test resume logic
timeout 15 uv run pytest tests/unit/test_phase_resume.py
```

### Integration Tests

```bash
# Test full phase automation workflow
timeout 15 uv run pytest tests/integration/test_phase_automation_workflow.py

# Run all tests with coverage
timeout 15 uv run pytest --cov=src --cov-report=term-missing
```

## Troubleshooting

### Worker Not Connecting

```bash
# Check Temporal server status
temporal server status

# Verify worker logs
uv run python -m src.workers.main  # Should show connection success
```

### Phase Execution Timeout

- Increase timeout via `--timeout-minutes` (default: 30 minutes)
- Check `speckit.implement` execution in standalone mode
- Review phase complexity and task count

### Checkpoint Not Resuming

- Verify task checkboxes are properly marked `[X]` in `tasks.md`
- Check that file path is consistent between runs
- Review structured logs for resume planning events

### Permission Errors

```bash
# Ensure result directories exist and are writable
mkdir -p /tmp/phase-results
chmod 755 /tmp/phase-results

# Ensure repo logs directory exists
mkdir -p logs/phase-results
```

## Advanced Usage

### Per-Phase AI Overrides

Add metadata to phase headings in `tasks.md`:

```markdown
## Phase 2: Implement Core Logic
<!-- model: gpt-4 -->
<!-- agent-profile: senior-engineer -->
<!-- env: DEBUG=true -->

- [ ] T004 Implement feature X
- [ ] T005 Add tests for feature X
```

The workflow automatically applies these overrides when executing Phase 2.

### Custom Retry Policies

```bash
uv run python -m src.cli.readiness --workflow automate-phase-tasks \
  --tasks-md-path /path/to/tasks.md \
  --repo-path /path/to/repo \
  --branch feature-branch \
  --retry-max-attempts 5 \
  --retry-initial-interval 10 \
  --retry-max-interval 300
```

### Query Phase Results Programmatically

```python
from temporalio.client import Client

async def get_phase_results(workflow_id: str):
    client = await Client.connect("localhost:7233")
    handle = client.get_workflow_handle(workflow_id)
    
    # Query for all phase results
    results = await handle.query("get_phase_results")
    
    # Query for persisted file paths
    paths = await handle.query("get_persisted_paths")
    
    return results, paths
```

## Next Steps

- Review the [specification](./spec.md) for complete feature details
- Check the [implementation plan](./plan.md) for architecture details
- Explore the [data model](./data-model.md) for entity relationships
- Read the [research findings](./research.md) for design decisions
