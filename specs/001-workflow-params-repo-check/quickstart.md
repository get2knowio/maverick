````markdown
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

## Parameter Keys and Format

### Required Parameters

- **`github_repo_url`** (string, required): GitHub repository URL in HTTPS or SSH format
  - **HTTPS Format**: `https://<host>/<owner>/<repo>` or `https://<host>/<owner>/<repo>.git`
    - Examples:
      - `https://github.com/openai/openai-python`
      - `https://github.com/temporalio/sdk-python.git`
      - `https://ghe.example.com/acme/widget` (GitHub Enterprise)
  - **SSH Format**: `git@<host>:<owner>/<repo>` or `git@<host>:<owner>/<repo>.git`
    - Examples:
      - `git@github.com:openai/openai-python`
      - `git@github.com:temporalio/sdk-python.git`
      - `git@ghe.example.com:acme/widget` (GitHub Enterprise)

### URL Normalization

The workflow automatically normalizes repository URLs to extract:
- **Host**: `github.com`, or your GitHub Enterprise Server hostname
- **Repository Slug**: `owner/repo` format (e.g., `openai/openai-python`)

### Supported Hosts

- **GitHub.com**: `github.com` (default)
- **GitHub Enterprise Server**: Any GHES hostname detected from the URL
  - Ensure `gh` is authenticated for your GHES instance using `gh auth login -h <host>`

## Start a workflow run

```bash
# Example CLI call (placeholder) to start the run with parameters
curl -X POST \
  -H 'Content-Type: application/json' \
  -d '{"parameters":{"github_repo_url":"https://github.com/openai/openai-python"}}' \
  http://localhost:8000/workflows/start
```

### Additional Examples

**HTTPS URL:**
```json
{
  "parameters": {
    "github_repo_url": "https://github.com/temporalio/sdk-python"
  }
}
```

**SSH URL:**
```json
{
  "parameters": {
    "github_repo_url": "git@github.com:temporalio/sdk-python"
  }
}
```

**GitHub Enterprise Server:**
```json
{
  "parameters": {
    "github_repo_url": "https://ghe.example.com/acme/widget"
  }
}
```

Expected behavior:
- Workflow normalizes the repo URL, checks `gh` auth, verifies repo with `gh repo view`.
- On success, workflow proceeds to downstream steps.
- On failure, workflow halts with a clear error message.

## Error Handling

### Common Error Codes

- **`validation_error`**: Malformed URL or unsupported host
- **`auth_error`**: `gh` CLI not installed or not authenticated for target host
  - Run `gh auth login` (or `gh auth login -h <host>` for GHES)
- **`not_found`**: Repository does not exist at the specified URL
- **`access_denied`**: Repository exists but you don't have access
- **`transient_error`**: Temporary network or API issue (automatically retried once)

