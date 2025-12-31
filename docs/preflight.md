# Preflight Validation

Maverick performs preflight validation before executing workflows to ensure all required tools and configurations are in place. This prevents workflows from failing mid-execution due to missing dependencies.

## How It Works

When you run `maverick fly` or `maverick refuel`, the system:

1. **Discovers runners** - Scans workflow instance for components implementing `ValidatableRunner`
2. **Validates in parallel** - Runs all validations concurrently with configurable timeouts
3. **Aggregates errors** - Collects ALL validation failures before reporting
4. **Reports with hints** - Provides actionable remediation suggestions

## Built-in Validations

### GitRunner

- Git executable on PATH
- Inside a git repository
- Not in merge/rebase state
- User identity configured (name and email)

### GitHubCLIRunner

- `gh` CLI installed
- Authenticated with GitHub
- Required scopes available (repo, read:org)
- Token not expired

### ValidationRunner

- All configured validation tools available (ruff, mypy, pytest, etc.)

### CodeRabbitRunner (Optional)

- CodeRabbit CLI installed (warning only, not required)

## Configuration

Configure preflight validation in `maverick.yaml`:

```yaml
preflight:
  # Maximum seconds per validation check (default: 5.0)
  timeout_per_check: 10.0

  # Whether warnings should cause preflight to fail (default: false)
  fail_on_warning: false

  # Custom tools to validate
  custom_tools:
    - name: "Docker"
      command: "docker"
      required: true
      hint: "Install Docker from https://docker.com/"

    - name: "AWS CLI"
      command: "aws"
      required: false
      hint: "Install: pip install awscli"

    - name: "Setup Script"
      command: "./scripts/setup.sh"
      required: false
      hint: "Run: chmod +x ./scripts/setup.sh"
```

## Custom Tool Configuration

Each custom tool has the following fields:

| Field      | Type   | Required | Description                                                             |
| ---------- | ------ | -------- | ----------------------------------------------------------------------- |
| `name`     | string | Yes      | Human-readable name for the tool                                        |
| `command`  | string | Yes      | Command or path to check via `shutil.which()`                           |
| `required` | bool   | No       | If true, missing tool is an error; if false, a warning (default: false) |
| `hint`     | string | No       | Installation hint to show if tool is missing                            |

## Example Output

When preflight validation fails:

```
Preflight validation failed (2 components):

  ✗ [GitRunner] Git user.name is not configured. Run: git config --global user.name 'Your Name'
  ✗ [GitHubCLIRunner] gh CLI is not authenticated. Run 'gh auth login'.

Warnings:
  ⚠ [CodeRabbitRunner] CodeRabbit CLI not installed (optional)
  ⚠ [CustomTools] Tool 'Docker' (docker) not found on PATH. Install Docker from https://docker.com/
```

## Dry-Run Mode

Preflight validation runs even in `--dry-run` mode, allowing you to verify your environment is correctly configured before committing to a real run:

```bash
maverick fly my-feature --dry-run
```

## Performance

Preflight validation is designed to complete quickly:

- All checks run in parallel using `asyncio.gather`
- Each check has a configurable timeout (default: 5 seconds)
- With all tools present, validation typically completes in under 2 seconds

## Extending Validation

To add validation to a custom runner:

```python
from maverick.runners.preflight import ValidationResult
from maverick.runners.protocols import ValidatableRunner

class MyCustomRunner:
    async def validate(self) -> ValidationResult:
        errors = []
        warnings = []

        # Your validation logic here
        if not self._check_something():
            errors.append("Something is missing. Install: ...")

        return ValidationResult(
            success=len(errors) == 0,
            component="MyCustomRunner",
            errors=tuple(errors),
            warnings=tuple(warnings),
            duration_ms=0,
        )
```

The runner will be automatically discovered and validated if it's an attribute of a workflow class (with name ending in `_runner`).
