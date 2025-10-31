# Maverick Examples

This directory contains complete, runnable examples demonstrating Maverick's capabilities.

## Available Examples

### [Containerized Validation](./containerized-validation/)

Demonstrates how to run the readiness workflow with Docker Compose integration, allowing all validation checks to execute inside an isolated containerized environment.

**What you'll learn:**
- Setting up Docker Compose for containerized validation
- Configuring health checks (required)
- Running validations inside containers
- Handling cleanup on success and failure
- Invoking workflows via CLI and programmatically

**Files:**
- `docker-compose.yml` - Docker Compose configuration with health checks
- `README.md` - Detailed instructions and troubleshooting
- `invoke_workflow.py` - Python script for programmatic workflow invocation

**Quick start:**
```bash
cd containerized-validation
uv run readiness-check https://github.com/get2knowio/maverick --compose-file ./docker-compose.yml
```

## Running Examples

### Prerequisites

All examples require:
- **Python 3.11+** and **uv** package manager
- **Temporal dev server** running:
  ```bash
  temporal server start-dev
  ```
- **Maverick worker** running:
  ```bash
  uv run maverick-worker
  ```

Some examples have additional requirements (e.g., Docker Compose V2 for containerized validation).

### General Pattern

1. **Start dependencies** (Temporal server, worker)
2. **Navigate to example directory** (`cd examples/<example-name>`)
3. **Read the example README** for specific instructions
4. **Run the example** using CLI or Python script
5. **Explore and modify** to understand the behavior

## Contributing Examples

When adding new examples:

1. Create a dedicated subdirectory under `examples/`
2. Include a detailed `README.md` with:
   - Clear explanation of what the example demonstrates
   - Prerequisites and setup instructions
   - Step-by-step usage guide
   - Expected output (success and failure cases)
   - Troubleshooting section
3. Provide working configuration files (compose files, etc.)
4. Include a Python script for programmatic invocation (if applicable)
5. Test the example end-to-end before committing
6. Update this top-level README with a link to the new example

## Related Documentation

- Main project README: `../README.md`
- Development guidelines: `../AGENTS.md`
- Feature specifications: `../specs/`
