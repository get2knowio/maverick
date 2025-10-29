# Quickstart

## Prerequisites

- Python 3.11+
- uv (dependency manager)
- Temporal dev server (Docker or `temporalio/auto-setup`)
- GitHub CLI (`gh`) installed and authenticated for your host

## Setup

```bash
# From repo root
uv sync

# Start Temporal dev server (example via Docker)
docker run --rm -d -p 7233:7233 --name temporal-dev temporalio/auto-setup:latest

# Verify gh is authenticated for github.com (or your GHES host)
gh auth status
```

## Run workers

```bash
# Example: run workflow/activities worker (placeholder command)
uv run python -m src.workers.main
```

## Start a workflow run

```bash
# Example CLI call (placeholder) to start the run with parameters
curl -X POST \
  -H 'Content-Type: application/json' \
  -d '{"parameters":{"github_repo_url":"https://github.com/openai/openai-python"}}' \
  http://localhost:8000/workflows/start
```

Expected behavior:
- Workflow normalizes the repo URL, checks `gh` auth, verifies repo with `gh repo view`.
- On success, workflow proceeds to downstream steps.
- On failure, workflow halts with a clear error message.

