# Contract: GitRunner

**Module**: `src/maverick/runners/git.py`
**Type**: Internal API (Python interface)

## Overview

GitRunner provides async git operations for workflow orchestration without AI involvement. It wraps git CLI commands via CommandRunner and returns structured results.

## Interface Definition

### GitResult

```python
@dataclass(frozen=True, slots=True)
class GitResult:
    """Result of a git operation."""
    success: bool          # True if exit code 0
    output: str            # stdout from git command
    error: str | None      # Error message if failed
    duration_ms: int       # Execution time
```

### GitRunner Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `create_branch` | branch_name: str, from_ref: str = "HEAD" | GitResult | Create and checkout new branch |
| `checkout` | ref: str | GitResult | Checkout existing branch/commit |
| `commit` | message: str, allow_empty: bool = False | GitResult | Create commit with staged changes |
| `push` | remote: str = "origin", branch: str \| None = None, force: bool = False, set_upstream: bool = False | GitResult | Push to remote |
| `diff` | base: str = "HEAD", staged: bool = True | str | Get diff output |
| `add` | paths: list[str] \| None = None, all: bool = False | GitResult | Stage files |
| `status` | - | GitResult | Get repository status |

## Usage Contract

### Preconditions

1. Working directory must be a git repository
2. git CLI must be installed and accessible
3. For push operations, remote must be configured

### Postconditions

1. `create_branch` with success=True guarantees branch exists and is checked out
2. `commit` with success=True guarantees commit was created
3. `push` with success=True guarantees commits were pushed to remote

### Error Handling

| Scenario | Behavior |
|----------|----------|
| Not a git repository | GitResult(success=False, error="Not a git repository") |
| Branch already exists | GitResult(success=False, error="Branch already exists") |
| Nothing to commit | GitResult(success=False, error="nothing to commit") |
| Push rejected | GitResult(success=False, error=<git error message>) |
| Command timeout | GitResult(success=False, error="Command timed out") |

### Branch Name Conflict Resolution (FR-001a)

```python
async def create_branch_with_fallback(
    self,
    branch_name: str,
    from_ref: str = "HEAD",
) -> GitResult:
    """Create branch with timestamp suffix fallback on conflict."""
    result = await self.create_branch(branch_name, from_ref)
    if not result.success and "already exists" in (result.error or ""):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        fallback_name = f"{branch_name}-{timestamp}"
        return await self.create_branch(fallback_name, from_ref)
    return result
```

## Test Contract

### Unit Test Requirements

1. Mock CommandRunner for all tests (no real git operations)
2. Test each method with success and failure scenarios
3. Verify command construction (correct git arguments)
4. Test timeout handling
5. Test error message parsing

### Example Test

```python
@pytest.mark.asyncio
async def test_create_branch_success():
    mock_runner = MagicMock()
    mock_runner.run = AsyncMock(return_value=CommandResult(
        returncode=0,
        stdout="Switched to a new branch 'feature-x'",
        stderr="",
        duration_ms=50,
    ))

    git = GitRunner(command_runner=mock_runner)
    result = await git.create_branch("feature-x")

    assert result.success is True
    mock_runner.run.assert_called_once_with(
        ["git", "checkout", "-b", "feature-x", "HEAD"]
    )
```
