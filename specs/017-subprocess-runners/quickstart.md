# Quickstart: Subprocess Execution Module

**Feature**: 017-subprocess-runners
**Date**: 2025-12-18

## Overview

The subprocess execution module (`maverick.runners`) provides safe, async command execution with timeout handling, streaming output, and specialized runners for validation, GitHub CLI, and CodeRabbit.

## Installation

The module uses only stdlib dependencies (asyncio, dataclasses, pathlib). No additional installation required beyond Maverick itself.

---

## Basic Usage

### Running a Simple Command

```python
import asyncio
from maverick.runners import CommandRunner, CommandResult

async def main():
    runner = CommandRunner()

    # Run a simple command
    result: CommandResult = await runner.run(["echo", "hello world"])

    print(f"Success: {result.success}")
    print(f"Output: {result.stdout}")
    print(f"Duration: {result.duration_ms}ms")

asyncio.run(main())
```

### Running with Custom Options

```python
from pathlib import Path
from maverick.runners import CommandRunner

async def main():
    runner = CommandRunner(
        cwd=Path("/path/to/project"),     # Working directory
        timeout=60.0,                      # Default timeout (seconds)
        env={"PYTHONPATH": "src"},         # Extra environment variables
    )

    # Commands inherit runner defaults
    result = await runner.run(["pytest", "tests/"])

    # Override per-command
    result = await runner.run(
        ["npm", "install"],
        timeout=120.0,  # Longer timeout for npm
        cwd=Path("/path/to/frontend"),
    )
```

---

## Streaming Output

For long-running commands, stream output line-by-line instead of waiting for completion:

```python
from maverick.runners import CommandRunner

async def main():
    runner = CommandRunner()

    # Stream stdout as lines become available
    async for line in runner.stream(["npm", "install"]):
        print(f"[npm] {line.content}")
        # line.stream indicates 'stdout' or 'stderr'
        # line.timestamp_ms shows when line was received
```

### Combined Streaming with Final Result

```python
async def main():
    runner = CommandRunner()

    lines = []
    async for line in runner.stream(["cargo", "build"]):
        lines.append(line.content)
        print(line.content)

    # Get final result after streaming completes
    result = await runner.wait()
    print(f"Build {'succeeded' if result.success else 'failed'}")
```

---

## Validation Runner

Run validation stages (format, lint, test) with automatic fix attempts:

```python
from maverick.runners import ValidationRunner, ValidationStage

async def main():
    # Define validation stages
    stages = [
        ValidationStage(
            name="format",
            command=("ruff", "format", "--check", "."),
            fixable=True,
            fix_command=("ruff", "format", "."),
        ),
        ValidationStage(
            name="lint",
            command=("ruff", "check", "."),
            fixable=True,
            fix_command=("ruff", "check", "--fix", "."),
        ),
        ValidationStage(
            name="typecheck",
            command=("mypy", "src/"),
            fixable=False,  # Type errors need manual fixing
        ),
        ValidationStage(
            name="test",
            command=("pytest", "tests/"),
            timeout_seconds=600.0,  # Tests may take longer
        ),
    ]

    runner = ValidationRunner(stages=stages)
    output = await runner.run()

    print(f"Validation {'passed' if output.success else 'failed'}")
    print(f"Stages: {output.stages_passed}/{output.stages_run} passed")

    for stage in output.stages:
        status = "PASS" if stage.passed else "FAIL"
        print(f"  [{status}] {stage.stage_name} ({stage.duration_ms}ms)")
        if stage.fix_attempts > 0:
            print(f"         Fixed after {stage.fix_attempts} attempt(s)")
```

### Parsing Validation Errors

Errors from known tools are automatically parsed:

```python
for stage in output.stages:
    if not stage.passed and stage.errors:
        print(f"Errors in {stage.stage_name}:")
        for error in stage.errors:
            print(f"  {error.file}:{error.line}: {error.message}")
            if error.code:
                print(f"    Code: {error.code}")
```

---

## GitHub CLI Runner

Interact with GitHub issues and pull requests:

```python
from maverick.runners import GitHubCLIRunner

async def main():
    runner = GitHubCLIRunner()  # Raises GitHubCLINotFoundError if gh not installed

    # List issues with a specific label
    issues = await runner.list_issues(label="bug", state="open", limit=10)
    for issue in issues:
        print(f"#{issue.number}: {issue.title}")

    # Get issue details
    issue = await runner.get_issue(42)
    print(f"Issue #{issue.number}: {issue.title}")
    print(f"Labels: {', '.join(issue.labels)}")
    print(f"Body: {issue.body[:200]}...")

    # Create a pull request
    pr = await runner.create_pr(
        title="Fix: resolve login timeout issue",
        body="## Summary\nFixes the login timeout by increasing the default timeout...",
        base="main",
        head="fix/login-timeout",
        draft=True,
    )
    print(f"Created PR #{pr.number}: {pr.url}")

    # Get PR check statuses
    checks = await runner.get_pr_checks(pr.number)
    for check in checks:
        status = "PASS" if check.passed else ("PENDING" if check.pending else "FAIL")
        print(f"  [{status}] {check.name}")
```

### Error Handling

```python
from maverick.runners import GitHubCLIRunner
from maverick.exceptions import GitHubCLINotFoundError, GitHubAuthError

try:
    runner = GitHubCLIRunner()
except GitHubCLINotFoundError:
    print("Please install GitHub CLI: https://cli.github.com/")
except GitHubAuthError:
    print("Please authenticate: gh auth login")
```

---

## CodeRabbit Runner

Run CodeRabbit code reviews (optional tool):

```python
from pathlib import Path
from maverick.runners import CodeRabbitRunner

async def main():
    runner = CodeRabbitRunner()

    # Review specific files
    result = await runner.run_review(
        files=[Path("src/auth.py"), Path("src/api.py")]
    )

    if result.warnings:
        for warning in result.warnings:
            print(f"Warning: {warning}")

    if result.has_findings:
        print(f"Found {len(result.findings)} issues:")
        for finding in result.findings:
            print(f"  {finding.file}:{finding.line} [{finding.severity}]")
            print(f"    {finding.message}")
            if finding.suggestion:
                print(f"    Suggestion: {finding.suggestion}")
    else:
        print("No issues found!")
```

---

## Timeout and Error Handling

### Handling Timeouts

```python
from maverick.runners import CommandRunner
from maverick.exceptions import CommandTimeoutError

async def main():
    runner = CommandRunner(timeout=30.0)

    result = await runner.run(["slow-command"])

    if result.timed_out:
        print(f"Command timed out after {runner.timeout}s")
    elif not result.success:
        print(f"Command failed with code {result.returncode}")
        print(f"stderr: {result.stderr}")
```

### Working Directory Errors

```python
from pathlib import Path
from maverick.runners import CommandRunner
from maverick.exceptions import WorkingDirectoryError

try:
    runner = CommandRunner(cwd=Path("/nonexistent/path"))
    await runner.run(["ls"])
except WorkingDirectoryError as e:
    print(f"Directory not found: {e.path}")
```

### Command Not Found

```python
from maverick.runners import CommandRunner
from maverick.exceptions import CommandNotFoundError

result = await runner.run(["nonexistent-command"])
# Result will have command_not_found=True in stderr
```

---

## Integration with Workflows

The runners are designed to integrate with Maverick workflows:

```python
from maverick.runners import ValidationRunner, GitHubCLIRunner
from maverick.workflows import FlyWorkflow

async def run_workflow():
    validation_runner = ValidationRunner(stages=MY_STAGES)
    github_runner = GitHubCLIRunner()

    workflow = FlyWorkflow(
        validation_runner=validation_runner,
        github_runner=github_runner,
    )

    async for progress in workflow.run():
        print(f"{progress.phase}: {progress.message}")
```

---

## Environment Variables

Runners inherit the parent process environment and allow overrides:

```python
runner = CommandRunner(
    env={
        "PYTHONPATH": "src",
        "DEBUG": "1",
        "API_KEY": "test-key",
    }
)

# These variables are merged with os.environ
result = await runner.run(["python", "script.py"])
```

---

## Best Practices

1. **Always use list form for commands**: Never pass shell strings
   ```python
   # Good
   await runner.run(["grep", "-r", "pattern", "src/"])

   # Bad - shell injection risk
   await runner.run(["sh", "-c", f"grep -r {user_input} src/"])
   ```

2. **Use streaming for long commands**: Prevents memory issues with large output
   ```python
   # Good for long-running commands
   async for line in runner.stream(["cargo", "build"]):
       log(line.content)
   ```

3. **Set appropriate timeouts**: Different commands need different limits
   ```python
   # Quick commands
   await runner.run(["git", "status"], timeout=10.0)

   # Build commands
   await runner.run(["npm", "run", "build"], timeout=300.0)

   # Test suites
   await runner.run(["pytest"], timeout=600.0)
   ```

4. **Handle optional tools gracefully**: Check availability before use
   ```python
   if await runner.is_available():
       result = await runner.run_review(files)
   else:
       logger.warning("CodeRabbit not available, skipping review")
   ```

---

## API Reference

See `maverick.runners` module documentation for complete API details:

- `CommandRunner` - Base command execution
- `ValidationRunner` - Validation stage orchestration
- `GitHubCLIRunner` - GitHub CLI wrapper
- `CodeRabbitRunner` - CodeRabbit integration
- `CommandResult` - Command execution result
- `ValidationOutput` - Validation results
- `GitHubIssue` / `PullRequest` / `CheckStatus` - GitHub entities
- `CodeRabbitResult` / `CodeRabbitFinding` - CodeRabbit entities
