# Example: Containerized Validation with Docker Compose

This example demonstrates how to run the Maverick readiness workflow with Docker Compose integration, allowing all validation checks to execute inside a containerized environment.

## What This Example Does

1. **Starts a Docker container** from the provided `docker-compose.yml` configuration
2. **Waits for health checks** to confirm the container is ready
3. **Executes all validation steps** inside the container (GitHub CLI checks, repo verification, etc.)
4. **Returns structured results** with the same format as non-containerized runs
5. **Cleans up automatically** on success, or preserves the environment on failure for debugging

## Prerequisites

Before running this example, ensure you have:

- **Docker Compose V2** installed (`docker compose` command available)
- **Temporal dev server** running:
  ```bash
  temporal server start-dev
  ```
- **Maverick worker** running:
  ```bash
  uv run maverick-worker
  ```
- **Python 3.11+** and **uv** package manager installed

## Files in This Example

- **`docker-compose.yml`**: Docker Compose configuration with a Python 3.11 container
- **`README.md`**: This file - instructions for running the example
- **`invoke_workflow.py`**: Python script to programmatically invoke the workflow

## Quick Start: Using the CLI

The simplest way to run this example is via the CLI:

```bash
# Navigate to this example directory
cd examples/containerized-validation

# Run the readiness check with Docker Compose integration
uv run readiness-check \
  https://github.com/get2knowio/maverick \
  --compose-file ./docker-compose.yml \
  --target-service app
```

### Expected Output

**On Success:**
```
Readiness workflow started: workflow_id=readiness-20251030-123456
Overall Status: ready
Target Service: app

Checks:
  ✓ GitHub CLI (gh): pass - Authenticated as username
  ✓ Copilot CLI (copilot): pass - Available
  ✓ Repository Access: pass - Repository accessible

Environment: Validated in containerized environment
Cleanup: Environment cleaned up successfully
```

**On Failure:**
```
Readiness workflow started: workflow_id=readiness-20251030-123456
Overall Status: not_ready
Target Service: app

Checks:
  ✗ GitHub CLI (gh): fail - Not authenticated
  ...

Environment: Validated in containerized environment (preserved)
Cleanup Instructions:
  Manual cleanup required:
  docker compose -p maverick-<workflow_id>-<run_id> down -v
```

## Advanced: Programmatic Invocation

For more control, use the Python script to invoke the workflow programmatically:

```bash
# From this example directory
python invoke_workflow.py
```

This script demonstrates:
- Loading and parsing the Docker Compose YAML
- Creating workflow parameters with explicit configuration
- Starting the workflow via Temporal client
- Handling results and cleanup instructions

## Understanding the Docker Compose Configuration

### Required: Health Check

The most critical part of the configuration is the **health check**:

```yaml
healthcheck:
  test: ["CMD", "python", "--version"]  # Command that verifies service health
  interval: 5s                          # Check every 5 seconds
  timeout: 3s                           # Each check must complete in 3s
  retries: 3                            # Allow 3 failures before marking unhealthy
  start_period: 10s                     # Grace period for slow startup
```

**Why it's required:** The workflow needs to know when the container is ready before running validations. Without a health check, the workflow will fail with a clear error message.

### Service Selection

The Docker Compose file defines a service named `app`. This follows the default selection policy:
- ✓ Single service: Automatically selected
- ✓ Multiple services with "app": "app" service selected
- ✗ Multiple services without "app": Must specify `--target-service <name>`

## Customizing the Example

### Change the Base Image

To test with a different environment:

```yaml
services:
  app:
    image: ubuntu:22.04  # Use Ubuntu instead of Python
    command: sleep infinity
    healthcheck:
      test: ["CMD", "test", "-f", "/etc/os-release"]
      interval: 5s
      timeout: 3s
      retries: 3
```

### Add Dependencies

Install tools needed for validation:

```yaml
services:
  app:
    image: python:3.11-slim
    command: bash -c "apt-get update && apt-get install -y curl git && sleep infinity"
    healthcheck:
      test: ["CMD", "which", "git"]
      interval: 5s
      timeout: 3s
      retries: 3
```

### Multi-Service Setup

Add supporting services:

```yaml
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: example
    healthcheck:
      test: ["CMD", "pg_isready"]
      interval: 5s
      timeout: 3s
      retries: 3
  
  app:
    image: python:3.11-slim
    depends_on:
      db:
        condition: service_healthy
    command: sleep infinity
    healthcheck:
      test: ["CMD", "python", "--version"]
      interval: 5s
      timeout: 3s
      retries: 3
```

**Note:** When using multiple services, validations run in the `app` service only (or the service you specify with `--target-service`).

## Troubleshooting

### Health Check Fails

**Problem:** Workflow fails with `health_check_timeout` error

**Solutions:**
1. Verify health check command works: `docker compose up -d && docker compose exec app python --version`
2. Increase `start_period` if container needs more startup time
3. Check container logs: `docker compose logs app`

### Port Conflicts

**Problem:** `docker compose up` fails with "port already allocated"

**Solutions:**
1. Check for conflicting containers: `docker ps`
2. Stop conflicting services
3. Change ports in docker-compose.yml (if applicable)

### Image Pull Timeout

**Problem:** Workflow times out while pulling large images

**Solutions:**
1. Pre-pull the image: `docker compose pull`
2. Increase `startup_timeout_seconds` in the workflow parameters
3. Use a locally cached image

### Validation Tools Missing

**Problem:** Validations fail because `gh` or other tools aren't in the container

**Solution:** Install tools in the Dockerfile or use an image that includes them:

```yaml
services:
  app:
    build:
      context: .
      dockerfile_inline: |
        FROM python:3.11-slim
        RUN apt-get update && \
            apt-get install -y curl && \
            curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
            dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
            chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg && \
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | \
            tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
            apt-get update && \
            apt-get install -y gh git
    command: sleep infinity
    healthcheck:
      test: ["CMD", "gh", "--version"]
      interval: 5s
      timeout: 3s
      retries: 3
```

## Next Steps

- **Modify docker-compose.yml** to match your target environment
- **Add volumes** to mount your local workspace into the container
- **Configure environment variables** that your validations need
- **Test different failure scenarios** to understand workflow behavior
- **Integrate into CI/CD** by parameterizing the compose file path

## Related Documentation

- Main project README: `../../README.md`
- Feature specification: `../../specs/001-docker-compose-runner/spec.md`
- Detailed quickstart: `../../specs/001-docker-compose-runner/quickstart.md`
- Activity implementation: `../../src/activities/compose.py`
- Workflow implementation: `../../src/workflows/readiness.py`
