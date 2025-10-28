# Quickstart: CLI Prerequisite Check

This feature defines a Temporal workflow that verifies two prerequisites:
- GitHub CLI is installed and authenticated
- Standalone Copilot CLI binary is available

## Prerequisites

- Python 3.11
- uv (https://docs.astral.sh/uv/)
- Temporal server (local dev server or Docker Compose)

## Install dependencies (planned)

A `pyproject.toml` will define dependencies and scripts. Once added, install with:

```bash
uv sync
```

## Run Temporal locally (dev server)

- Option A: Temporal CLI dev server
- Option B: Docker Compose (if provided in repo)

## Execute readiness workflow (planned uv script)

Once `pyproject.toml` is in place, a script will be available:

```bash
uv run workflows:readiness
```

This will:
1) Start a worker (if not already running)
2) Execute the readiness workflow
3) Print human‑readable summary and exit non‑zero on failure

## Testing

Run tests (unit + integration) with:

```bash
uv run pytest -q
```

Temporal tests will:
- Unit-test activity functions (gh auth status parsing; copilot help presence)
- Integration-test workflow orchestration and summary mapping
