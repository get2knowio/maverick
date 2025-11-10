# Quickstart: Multi-Task Orchestration Workflow

**Feature**: Multi-Task Orchestration Workflow  
**Branch**: `001-multi-task-orchestration`  
**Audience**: Developers implementing or using the orchestration workflow

## Overview

The Multi-Task Orchestration Workflow enables automated, sequential processing of multiple task files through all phases (initialize, implement, review/fix, PR/CI/merge). This guide provides quick setup instructions and usage examples.

## Prerequisites

- Python 3.11+
- uv (dependency manager)
- Temporal cluster running (local dev server or Docker Compose)
- Existing phase workflows registered:
  - `AutomatePhaseTasksWorkflow`
  - `ReadinessWorkflow`
- Worker process running with orchestration workflow registered

## Quick Start

### 1. Start Temporal Cluster

**Local dev server**:
```bash
temporal server start-dev
```

**Or Docker Compose**:
```bash
docker-compose up temporal
```

### 2. Start Worker Process

```bash
cd /workspace/maverick
uv run python -m src.workers.main
```

The worker automatically registers all workflows including `MultiTaskOrchestrationWorkflow`.

### 3. Create Task Files

Task files follow standard markdown format with phase sections:

```markdown
# tasks/feature-001.md

## Phase 1: Initialize
- [ ] T001: Create feature branch
- [ ] T002: Set up project structure

## Phase 2: Implement
- [ ] T003: Implement core functionality
- [ ] T004: Add unit tests

## Phase 3: Review & Fix
- [ ] T005: Address code review comments

## Phase 4: PR/CI/Merge
- [ ] T006: Open pull request
- [ ] T007: Wait for CI checks
```

### 4. Execute Orchestration Workflow

**Using Python SDK** (recommended for automation):

```python
from temporalio.client import Client
from src.models.orchestration import OrchestrationInput, OrchestrationResult

async def run_orchestration():
    # Connect to Temporal
    client = await Client.connect("localhost:7233")
    
    # Define workflow input
    workflow_input = OrchestrationInput(
        task_file_paths=(
            "tasks/feature-001.md",
            "tasks/feature-002.md",
            "tasks/feature-003.md",
        ),
        interactive_mode=False,  # Automated execution
        retry_limit=3,           # Max retries per phase
        repo_path="/workspace/myrepo",
        branch="main",
        default_model="gpt-4",
    )
    
    # Start workflow
    handle = await client.start_workflow(
        "MultiTaskOrchestrationWorkflow",
        workflow_input,
        id="orchestration-batch-001",
        task_queue="maverick-task-queue",
    )
    
    print(f"Started workflow: {handle.id}")
    
    # Wait for result
    result: OrchestrationResult = await handle.result()
    
    print(f"Completed: {result.successful_tasks}/{result.total_tasks} tasks successful")
    print(f"Failed: {result.failed_tasks}")
    print(f"Early termination: {result.early_termination}")
    
    return result
```

**Using Temporal CLI** (for manual testing):

```bash
temporal workflow start \
  --type MultiTaskOrchestrationWorkflow \
  --task-queue maverick-task-queue \
  --workflow-id orchestration-batch-001 \
  --input '{
    "task_file_paths": ["tasks/feature-001.md", "tasks/feature-002.md"],
    "interactive_mode": false,
    "retry_limit": 3,
    "repo_path": "/workspace/myrepo",
    "branch": "main",
    "default_model": "gpt-4"
  }'
```

### 5. Monitor Progress

**Query workflow progress**:

```python
# Using Python SDK
progress = await handle.query("get_progress")
print(f"Current task: {progress['current_task_index']}/{progress['total_tasks']}")
print(f"Current phase: {progress['current_phase']}")
print(f"Is paused: {progress['is_paused']}")
```

**Using Temporal CLI**:

```bash
temporal workflow query \
  --workflow-id orchestration-batch-001 \
  --name get_progress
```

**View Temporal Web UI**:
```
http://localhost:8233
```

## Interactive Mode Usage

### Enable Interactive Mode

Set `interactive_mode=True` to pause after each phase:

```python
workflow_input = OrchestrationInput(
    task_file_paths=("tasks/feature-001.md",),
    interactive_mode=True,  # Enable pauses
    retry_limit=3,
    repo_path="/workspace/myrepo",
    branch="feature-branch",
)
```

### Send Approval Signals

**Continue to next phase**:

```python
# Using Python SDK
await handle.signal("continue_to_next_phase")
```

```bash
# Using Temporal CLI
temporal workflow signal \
  --workflow-id orchestration-batch-001 \
  --name continue_to_next_phase
```

**Skip current task**:

```python
# Using Python SDK
await handle.signal("skip_current_task")
```

```bash
# Using Temporal CLI
temporal workflow signal \
  --workflow-id orchestration-batch-001 \
  --name skip_current_task
```

## Common Use Cases

### Use Case 1: Automated Batch Processing

Process multiple features fully automated:

```python
workflow_input = OrchestrationInput(
    task_file_paths=(
        "tasks/feature-001.md",
        "tasks/feature-002.md",
        "tasks/feature-003.md",
        "tasks/feature-004.md",
        "tasks/feature-005.md",
    ),
    interactive_mode=False,
    retry_limit=3,
    repo_path="/workspace/myrepo",
    branch="main",
    default_model="gpt-4",
)

result = await client.execute_workflow(
    "MultiTaskOrchestrationWorkflow",
    workflow_input,
    id=f"batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
    task_queue="maverick-task-queue",
)

# Result contains complete summary
print(f"Total: {result.total_tasks}")
print(f"Success: {result.successful_tasks}")
print(f"Failed: {result.failed_tasks}")
print(f"Duration: {result.total_duration_seconds}s")
```

### Use Case 2: Interactive Development

Process single task with manual approval gates:

```python
workflow_input = OrchestrationInput(
    task_file_paths=("tasks/complex-feature.md",),
    interactive_mode=True,  # Pause after each phase
    retry_limit=5,          # More retries for complex tasks
    repo_path="/workspace/myrepo",
    branch="feature-branch",
    default_model="gpt-4-turbo",
    default_agent_profile="senior-developer",
)

handle = await client.start_workflow(
    "MultiTaskOrchestrationWorkflow",
    workflow_input,
    id="interactive-dev-session",
    task_queue="maverick-task-queue",
)

# Monitor and approve interactively
while True:
    progress = await handle.query("get_progress")
    
    if not progress["is_paused"]:
        await asyncio.sleep(10)  # Check again soon
        continue
    
    print(f"Paused at phase: {progress['current_phase']}")
    approval = input("Continue? (y/n/skip): ")
    
    if approval.lower() == "y":
        await handle.signal("continue_to_next_phase")
    elif approval.lower() == "skip":
        await handle.signal("skip_current_task")
    elif approval.lower() == "n":
        print("Workflow remains paused")
    
    # Check if workflow completed
    try:
        result = await asyncio.wait_for(handle.result(), timeout=1.0)
        print("Workflow completed!")
        break
    except asyncio.TimeoutError:
        continue  # Still running
```

### Use Case 3: Resume After Failure

Workflows automatically resume after worker restarts. No manual intervention needed:

```python
# Original execution fails mid-processing
handle = await client.start_workflow(
    "MultiTaskOrchestrationWorkflow",
    workflow_input,
    id="resilient-batch-001",
    task_queue="maverick-task-queue",
)

# Worker crashes...
# Worker restarts...

# Workflow automatically resumes from last completed task
# Just wait for result:
result = await handle.result()  # Picks up where it left off
```

## Configuration Options

### Retry Limits

Control retry behavior per workflow:

```python
workflow_input = OrchestrationInput(
    # ... other params ...
    retry_limit=5,  # Try each phase up to 5 times
)
```

Recommended values:
- **Development**: 5-10 (more tolerance for environment issues)
- **CI/CD**: 3 (fail fast on persistent problems)
- **Production**: 3-5 (balance reliability and speed)

### AI Model Selection

Specify default model for all phases:

```python
workflow_input = OrchestrationInput(
    # ... other params ...
    default_model="gpt-4-turbo",        # Fast, cost-effective
    # default_model="gpt-4",            # High quality, slower
    # default_model="claude-3-opus",    # Alternative provider
)
```

### Agent Profile

Customize agent behavior:

```python
workflow_input = OrchestrationInput(
    # ... other params ...
    default_agent_profile="senior-developer",  # Conservative, thorough
    # default_agent_profile="junior-developer", # Faster, less thorough
)
```

## Troubleshooting

### Workflow Stuck in Paused State

**Symptom**: Workflow shows `is_paused=True` but you didn't enable interactive mode.

**Solution**: Send continue signal to resume:
```bash
temporal workflow signal \
  --workflow-id <workflow-id> \
  --name continue_to_next_phase
```

### Task Failed After Retries

**Symptom**: `failed_tasks > 0` in result, `early_termination=True`.

**Diagnosis**: Check task result for failure reason:
```python
result = await handle.result()
for task_result in result.task_results:
    if task_result.overall_status == "failed":
        print(f"Task: {task_result.task_file_path}")
        print(f"Reason: {task_result.failure_reason}")
        for phase_result in task_result.phase_results:
            if phase_result.status == "failed":
                print(f"  Phase: {phase_result.phase_name}")
                print(f"  Error: {phase_result.error_message}")
                print(f"  Retries: {phase_result.retry_count}")
```

**Solution**: Fix underlying issue (code bug, environment problem) and restart workflow.

### Event History Too Large

**Symptom**: Workflow fails with event history size error.

**Solution**: Reduce task count per workflow execution (recommended max: 20 tasks).

Split large batches:
```python
# Instead of 50 tasks in one workflow:
all_tasks = ["tasks/f001.md", ..., "tasks/f050.md"]

# Split into 3 workflows of ~17 tasks each:
batch_size = 17
for i in range(0, len(all_tasks), batch_size):
    batch = all_tasks[i:i+batch_size]
    workflow_input = OrchestrationInput(
        task_file_paths=tuple(batch),
        # ... other params ...
    )
    await client.start_workflow(
        "MultiTaskOrchestrationWorkflow",
        workflow_input,
        id=f"batch-{i//batch_size}",
        task_queue="maverick-task-queue",
    )
```

## Testing

### Unit Tests

Test workflow logic in isolation:

```python
import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

@pytest.mark.asyncio
async def test_orchestration_workflow_success():
    """Test successful execution of 2 tasks."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        # Register workflow and activities
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[MultiTaskOrchestrationWorkflow],
            activities=[parse_task_file],
        ):
            # Execute workflow
            workflow_input = OrchestrationInput(
                task_file_paths=("tests/fixtures/task1.md", "tests/fixtures/task2.md"),
                interactive_mode=False,
                retry_limit=3,
                repo_path="/test/repo",
                branch="main",
            )
            
            result = await env.client.execute_workflow(
                "MultiTaskOrchestrationWorkflow",
                workflow_input,
                id="test-orchestration",
                task_queue="test-queue",
            )
            
            # Assertions
            assert result.total_tasks == 2
            assert result.successful_tasks == 2
            assert result.failed_tasks == 0
            assert not result.early_termination
```

### Integration Tests

Test with real Temporal server:

```bash
# Start temporal dev server
temporal server start-dev &

# Run integration tests
uv run pytest tests/integration/test_multi_task_orchestration.py
```

## Next Steps

- Review [data-model.md](./data-model.md) for complete entity schemas
- Check [workflow-interface.yaml](./contracts/workflow-interface.yaml) for API contract
- See [spec.md](./spec.md) for detailed requirements and acceptance criteria
- Consult [research.md](./research.md) for design decisions and alternatives

## Support

- Temporal Python SDK docs: https://docs.temporal.io/dev-guide/python
- Constitution: See `AGENTS.md` for development standards
- Issues: Create issue in repository with `orchestration` label
