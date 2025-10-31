# Quickstart: Containerized Validation with Docker Compose

This guide shows how to run the Maverick readiness workflow with Docker Compose integration, enabling validations to execute inside a containerized environment.

## Prerequisites

- Docker Compose V2 (`docker compose` plugin) installed and accessible
- Temporal dev server running locally (or connection to remote Temporal cluster)
- `uv` installed (project uses uv for all dependency and script execution)
- Python 3.11+
- Maverick worker running (see Worker Setup below)

## Quick Example

### 1. Create a Docker Compose File

Create `my-compose.yml` with a service that includes a health check:

```yaml
services:
  app:
    image: python:3.11-slim
    command: sleep infinity
    healthcheck:
      test: ["CMD", "python", "--version"]
      interval: 5s
      timeout: 3s
      retries: 3
    working_dir: /workspace
```

**Important**: The target service MUST define a `healthcheck`. The workflow will fail if health checks are missing.

### 2. Run the Readiness Workflow

Using the CLI:

```bash
uv run readiness-check \
  https://github.com/owner/repo \
  --compose-file ./my-compose.yml \
  --target-service app
```

Or invoke the workflow directly via Temporal client:

```python
from temporalio.client import Client
from src.workflows.readiness import ReadinessWorkflow
from src.models.parameters import Parameters
from src.models.compose import ComposeConfig
import yaml

# Load and parse compose file
with open("my-compose.yml", "r") as f:
    yaml_content = f.read()
parsed_config = yaml.safe_load(yaml_content)

# Create workflow parameters
config = ComposeConfig(
    yaml_content=yaml_content,
    parsed_config=parsed_config,
    target_service="app",
    startup_timeout_seconds=300,
    validation_timeout_seconds=60
)

params = Parameters(
    github_repo_url="https://github.com/owner/repo",
    compose_config=config
)

# Connect to Temporal and start workflow
client = await Client.connect("localhost:7233")
result = await client.execute_workflow(
    ReadinessWorkflow.run,
    params,
    id=f"readiness-{datetime.now().isoformat()}",
    task_queue="maverick-task-queue"
)

print(f"Workflow status: {result.overall_status}")
if result.target_service:
    print(f"Target service: {result.target_service}")
```

### 3. Check Results

**On Success**:
- Workflow returns `overall_status="ready"`
- All checks pass
- Docker Compose environment cleaned up automatically
- No manual intervention required

**On Failure**:
- Workflow returns `overall_status="not_ready"` with failed check details
- Docker Compose environment **preserved indefinitely** for troubleshooting
- Result includes `cleanup_instructions` with manual cleanup command
- Inspect containers: `docker compose -p <project_name> logs`
- Clean up manually: `docker compose -p <project_name> down -v`

## Configuration Options

### ComposeConfig Parameters

- **yaml_content** (required): Original YAML as string, max 1 MB
- **parsed_config** (required): Parsed dict structure with `services` key
- **target_service** (optional): Service name for validation execution
  - If omitted and exactly 1 service exists: uses that service
  - If omitted and multiple services: uses service named "app"
  - If omitted, multiple services, no "app": fails with instruction
- **startup_timeout_seconds** (default: 300): Max time for environment startup and health checks
- **validation_timeout_seconds** (default: 60): Max time per validation step

### Target Service Selection Examples

**Single Service** (automatic):
```yaml
services:
  backend:  # This will be used automatically
    image: node:20
    healthcheck: ...
```

**Multiple Services with "app"** (automatic):
```yaml
services:
  db:
    image: postgres:15
  app:  # This will be used automatically
    image: python:3.11
    healthcheck: ...
```

**Multiple Services, explicit selection** (required):
```yaml
services:
  frontend:
    image: nginx
  backend:  # Must specify --target-service backend
    image: python:3.11
    healthcheck: ...
```

## Worker Setup

The Docker Compose activities are registered in the main worker. Ensure the worker is running:

```bash
# From project root
uv run maverick-worker
```

The worker will output:
```
temporal_connected target_host=localhost:7233 status=success
worker_registered task_queue=maverick-task-queue workflows=['ReadinessWorkflow'] activities=['compose_up_activity', 'compose_down_activity', ...]
```

## Workflow Behavior

### Phase 1: Environment Startup
1. Validate compose config (size, structure, health checks)
2. Resolve target service using default selection policy
3. Generate unique project name: `maverick-<workflow_id>-<run_id>`
4. Create temporary compose file in isolated directory
5. Execute: `docker compose -p <project> -f <temp_file> up -d`
6. Poll health status using exponential backoff (1s, 2s, 4s, ..., max 30s)
7. Wait for target service to report "healthy" status

### Phase 2: Validation Execution
1. For each validation step (gh_status, repo_verification, etc.):
   - Execute: `docker compose -p <project> exec <service> <command>`
   - Capture stdout/stderr with tolerant decoding (`errors='replace'`)
   - Record results with timing and status

### Phase 3: Cleanup
**Success Path**:
- Execute: `docker compose -p <project> down -v`
- Remove all containers, networks, and volumes
- Log cleanup success

**Failure Path**:
- Skip teardown (preserve environment)
- Log manual cleanup instructions
- Include project name in workflow result

## Troubleshooting

### Environment Fails to Start

**Symptom**: Workflow fails with `error_type="startup_failed"`

**Causes & Solutions**:
- **Port conflicts**: Another service using required ports
  - Check: `docker ps` to see conflicting containers
  - Fix: Stop conflicting services or change ports in compose file
- **Image pull failures**: Network issues or rate limiting
  - Check: Look for "manifest not found" in stderr_excerpt
  - Fix: Pre-pull images or use locally cached images
- **Invalid YAML**: Syntax errors in compose file
  - Check: stderr_excerpt will show parsing errors
  - Fix: Validate YAML syntax with `docker compose -f <file> config`

### Health Check Never Succeeds

**Symptom**: Workflow fails with `error_type="health_check_timeout"`

**Causes & Solutions**:
- **Health check not defined**: Target service missing healthcheck section
  - Fix: Add healthcheck to service definition (required by spec)
- **Health check command fails**: Test command returns non-zero
  - Debug: `docker compose -p <project> exec <service> <healthcheck_command>`
  - Fix: Update healthcheck test command
- **Slow startup**: Service needs more time than timeout allows
  - Fix: Increase `startup_timeout_seconds` parameter

### Validation Fails Inside Container

**Symptom**: Validation steps fail that work on host

**Causes & Solutions**:
- **Missing tools**: Required executables not in container
  - Fix: Update container image to include gh, git, etc.
- **Network issues**: Container can't reach external services
  - Fix: Check Docker network configuration
- **File access**: Validation needs files not mounted
  - Fix: Add volume mounts to compose file

### Resources Not Cleaned Up

**Symptom**: Old containers/networks remain after failures

**Manual Cleanup**:
```bash
# List maverick projects
docker compose ls | grep maverick

# Clean up specific project
docker compose -p maverick-<workflow_id>-<run_id> down -v

# Nuclear option: remove all maverick resources
docker ps -a --filter "name=maverick-" --format "{{.Names}}" | xargs -r docker rm -f
docker network ls --filter "name=maverick-" --format "{{.Name}}" | xargs -r docker network rm
```

## Best Practices

1. **Pre-pull Images**: Pull images before running workflow to avoid timeout during pull
   ```bash
   docker compose -f my-compose.yml pull
   ```

2. **Use Minimal Images**: Smaller images start faster and pull quicker
   ```yaml
   services:
     app:
       image: python:3.11-slim  # Not python:3.11 (smaller)
   ```

3. **Optimize Health Checks**: Fast, reliable health checks reduce startup time
   ```yaml
   healthcheck:
     test: ["CMD", "python", "-c", "print('healthy')"]
     interval: 2s  # Check frequently
     timeout: 1s   # Fail fast
     retries: 3    # Don't be too strict
   ```

4. **Set Appropriate Timeouts**: Balance speed vs reliability
   - Fast local images: `startup_timeout_seconds=60`
   - Large images or slow network: `startup_timeout_seconds=600`

5. **Clean Up Failed Runs**: Don't let failed environments accumulate
   - Check periodically: `docker compose ls`
   - Clean old failures: See manual cleanup above

## Next Steps

All features are now implemented! You can:

- Try containerized validation with your own Docker Compose files
- Experiment with multi-service configurations and target service selection
- Review implementation details in `src/activities/compose.py` and `src/workflows/readiness.py`
- Write additional tests for specific scenarios
- Integrate containerized validation into your CI/CD pipelines

