# Quickstart: Preflight Validation System

**Feature**: 027-preflight-validation  
**Date**: 2024-12-24

## Overview

The Preflight Validation System validates all required tools and configurations **before** Maverick workflows create branches or modify state. This prevents mid-execution failures and provides actionable error messages.

## Quick Usage

### Automatic (Recommended)

Preflight validation runs automatically when executing workflows:

```bash
# Preflight runs automatically before any state changes
maverick fly --branch feature/my-feature

# Example output if gh is not installed:
# ✗ Preflight validation failed (1 component)
#   [GitHubCLIRunner] GitHub CLI (gh) not found
#     Install: brew install gh  (macOS)
#              sudo apt install gh  (Linux)
#     Docs: https://cli.github.com
```

### Manual Check

Check environment without running a workflow:

```bash
# Coming in future: maverick preflight
# For now, validation happens automatically on workflow start
```

## What Gets Validated

| Component            | Checks                                                                 |
| -------------------- | ---------------------------------------------------------------------- |
| **Git**              | git on PATH, in a repo, not mid-merge/rebase, user identity configured |
| **GitHub CLI**       | gh on PATH, authenticated, has required scopes                         |
| **Validation Tools** | Configured tools (ruff, mypy, pytest) are available                    |
| **CodeRabbit**       | coderabbit CLI available (warning only, not blocking)                  |

## Error Messages

All errors include remediation hints:

```
✗ Preflight validation failed (2 components):

  [GitRunner] Git user.name not configured
    Run: git config --global user.name "Your Name"

  [GitHubCLIRunner] GitHub CLI not authenticated
    Run: gh auth login

Warnings:
  ⚠ [CodeRabbitRunner] CodeRabbit CLI not installed (optional)
    Install: https://coderabbit.ai/docs/cli
```

## Programmatic Usage

### Using PreflightValidator directly

```python
from pathlib import Path
from maverick.runners import GitRunner, GitHubCLIRunner, ValidationRunner
from maverick.runners.preflight import PreflightValidator, PreflightConfig

async def check_environment():
    # Create runners
    git = GitRunner(cwd=Path.cwd())
    github = GitHubCLIRunner()

    # Run preflight validation
    validator = PreflightValidator(
        runners=[git, github],
        timeout_per_check=5.0,
    )
    result = await validator.run()

    if result.success:
        print("✓ All checks passed!")
    else:
        print(f"✗ Failed: {result.failed_components}")
        for error in result.all_errors:
            print(f"  - {error}")
```

### In a Custom Workflow

```python
from maverick.workflows.base import WorkflowDSLMixin
from maverick.exceptions import PreflightValidationError

class MyWorkflow(WorkflowDSLMixin):
    async def execute(self, inputs):
        # Preflight validation - runs before any state changes
        try:
            await self.run_preflight(
                runners=[self._git_runner, self._github_runner],
            )
        except PreflightValidationError as e:
            # Handle validation failure
            print(e.result.all_errors)
            return

        # Proceed with workflow...
```

## Configuration

Preflight timeout can be configured:

```python
# Default: 5 seconds per check
validator = PreflightValidator(runners=runners, timeout_per_check=5.0)

# For slow environments (CI):
validator = PreflightValidator(runners=runners, timeout_per_check=10.0)
```

## Dry Run Mode

Preflight validation runs even in `--dry-run` mode:

```bash
# Validation still runs in dry-run mode
maverick fly --branch test --dry-run

# This ensures dry-run accurately previews what would happen
```

## Extending with Custom Validators

(Future feature - P3 priority)

```toml
# maverick.toml (future)
[preflight.custom_tools]
docker = { check_cmd = "docker --version" }
```

## Troubleshooting

### "Git not found on PATH"

```bash
# macOS
brew install git

# Linux (Debian/Ubuntu)
sudo apt-get install git

# Verify installation
git --version
```

### "GitHub CLI not authenticated"

```bash
# Login to GitHub
gh auth login

# Verify authentication
gh auth status
```

### "GitHub token missing 'repo' scope"

```bash
# Re-authenticate with correct scopes
gh auth login --scopes repo,read:org
```

### "Validation timed out"

The default timeout is 5 seconds per check. For slow networks or CI environments, this may need adjustment in code.

## Architecture

```
Workflow Start
      │
      ▼
┌─────────────────┐
│ run_preflight() │ ◄── Runs before any state changes
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│ PreflightValidator  │
│  - parallel checks  │
│  - timeout handling │
│  - error aggregation│
└────────┬────────────┘
         │
    ┌────┴────┬────────┬────────┐
    ▼         ▼        ▼        ▼
┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐
│GitRun │ │GitHub │ │Valid. │ │CodeR. │
│ner   │ │CLIRun │ │Runner │ │Runner │
│.valid │ │.valid │ │.valid │ │.valid │
│ate() │ │ate()  │ │ate()  │ │ate()  │
└───┬───┘ └───┬───┘ └───┬───┘ └───┬───┘
    │         │        │        │
    └────┬────┴────────┴────────┘
         │
         ▼
┌─────────────────┐
│ PreflightResult │
│ - aggregated    │
│ - all errors    │
└────────┬────────┘
         │
    Success?
    /     \
   Yes     No
    │       │
    ▼       ▼
Continue   Raise
Workflow   PreflightValidationError
```
