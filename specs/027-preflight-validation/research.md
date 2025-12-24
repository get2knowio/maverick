# Research: Preflight Validation System

**Feature**: 027-preflight-validation  
**Date**: 2024-12-24  
**Status**: Complete

## Research Tasks

### 1. Async Parallel Validation Pattern

**Question**: What's the best pattern for running multiple validation checks in parallel with individual timeouts?

**Decision**: Use `asyncio.gather()` with `return_exceptions=True` combined with `asyncio.wait_for()` per-check timeouts.

**Rationale**:

- `asyncio.gather(return_exceptions=True)` collects all results/exceptions without short-circuiting
- Per-check `asyncio.wait_for()` ensures no single check blocks indefinitely
- Aligns with Constitution Principle I (Async-First) and IX (Hardening by Default)

**Alternatives Considered**:

1. Sequential validation - Rejected: Doesn't meet <2s performance goal
2. `asyncio.TaskGroup` - Considered but `gather` with `return_exceptions` is simpler for aggregating errors
3. Thread pool - Rejected: Constitution prohibits threading for I/O operations

**Code Pattern**:

```python
async def run_all_validations(
    validators: list[ValidatableRunner],
    timeout_per_check: float = 5.0,
) -> list[ValidationResult]:
    async def validate_with_timeout(validator: ValidatableRunner) -> ValidationResult:
        try:
            return await asyncio.wait_for(
                validator.validate(),
                timeout=timeout_per_check,
            )
        except asyncio.TimeoutError:
            return ValidationResult(
                success=False,
                component=validator.__class__.__name__,
                errors=[f"Validation timed out after {timeout_per_check}s"],
            )

    results = await asyncio.gather(
        *[validate_with_timeout(v) for v in validators],
        return_exceptions=True,
    )
    # Convert any uncaught exceptions to ValidationResult
    return [
        r if isinstance(r, ValidationResult)
        else ValidationResult(success=False, component="unknown", errors=[str(r)])
        for r in results
    ]
```

---

### 2. Protocol vs ABC for ValidatableRunner

**Question**: Should `ValidatableRunner` be a `Protocol` or an abstract base class?

**Decision**: Use `typing.Protocol` (structural subtyping).

**Rationale**:

- Constitution Principle VI explicitly recommends Protocol for interfaces between components
- Avoids circular dependencies (runners don't need to import from a shared base)
- Existing codebase uses Protocol pattern (see `src/maverick/dsl/protocols.py`)
- Runners can satisfy the protocol without inheritance - more flexible for testing

**Alternatives Considered**:

1. ABC with abstract method - Rejected: Forces inheritance, creates import dependencies
2. Duck typing without Protocol - Rejected: Loses type checker benefits

**Code Pattern**:

```python
from typing import Protocol

class ValidatableRunner(Protocol):
    """Protocol for runners that support environment validation."""

    async def validate(self) -> ValidationResult:
        """Validate that required tools/config are available.

        Returns:
            ValidationResult with success status and any errors/warnings.
        """
        ...
```

---

### 3. ValidationResult Data Structure

**Question**: What should `ValidationResult` contain and how should it be structured?

**Decision**: Frozen dataclass with `to_dict()` for DSL serialization.

**Rationale**:

- Constitution Principle VI requires typed contracts with frozen dataclasses
- Needs: success flag, component name, error list, warning list
- Frozen ensures immutability (Constitution Principle VI)
- `to_dict()` enables DSL serialization (Constitution Principle VI)

**Alternatives Considered**:

1. Pydantic BaseModel - Considered but dataclass is simpler for this use case
2. TypedDict - Rejected: Less tooling support, no immutability
3. NamedTuple - Rejected: Less flexible, no default values

**Code Pattern**:

```python
from dataclasses import dataclass, field, asdict

@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of a single validation check."""

    success: bool
    component: str
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

---

### 4. Error Message Format

**Question**: How should validation error messages be formatted for actionability?

**Decision**: Structured error messages with issue, remediation, and optional link.

**Rationale**:

- FR-012 requires actionable messages with "what's wrong" + "how to fix"
- Consistent with existing Maverick console output patterns
- Should support both plain text and rich terminal output

**Pattern**:

```
[✗] GitHub CLI (gh) not found
    Install: brew install gh  (macOS)
            sudo apt install gh  (Linux)
    Docs: https://cli.github.com

[✗] Git user identity not configured
    Run: git config --global user.name "Your Name"
         git config --global user.email "you@example.com"
```

**Code Pattern**:

```python
@dataclass(frozen=True)
class ValidationError:
    """Structured validation error with remediation."""

    issue: str
    remediation: str | None = None
    docs_url: str | None = None

    def format(self) -> str:
        lines = [f"[✗] {self.issue}"]
        if self.remediation:
            lines.append(f"    {self.remediation}")
        if self.docs_url:
            lines.append(f"    Docs: {self.docs_url}")
        return "\n".join(lines)
```

---

### 5. Git Repository State Validation

**Question**: What git states should be validated and how?

**Decision**: Validate 4 conditions: git available, in repository, not mid-rebase/merge, user identity configured.

**Rationale**:

- FR-003 specifies these exact checks
- Existing `GitRunner` already has `CommandRunner` for subprocess execution
- Can reuse existing error patterns from `src/maverick/exceptions/git.py`

**Implementation Approach**:

1. `git --version` - check git is on PATH
2. `git rev-parse --git-dir` - check in a repository
3. Check for `.git/MERGE_HEAD`, `.git/REBASE_MERGE`, `.git/REBASE_APPLY` files
4. `git config user.name` and `git config user.email` - check identity

**Code Pattern**:

```python
async def validate(self) -> ValidationResult:
    errors = []
    warnings = []

    # Check git available
    if not shutil.which("git"):
        errors.append("Git not found on PATH")
        return ValidationResult(False, "GitRunner", tuple(errors))

    # Check in repository
    result = await self._command_runner.run(["git", "rev-parse", "--git-dir"])
    if not result.success:
        errors.append("Not in a git repository")
        return ValidationResult(False, "GitRunner", tuple(errors))

    # Check for conflict state
    git_dir = Path(result.stdout.strip())
    if (git_dir / "MERGE_HEAD").exists():
        errors.append("Repository is in merge conflict state")
    if (git_dir / "REBASE_MERGE").exists() or (git_dir / "REBASE_APPLY").exists():
        errors.append("Repository is in rebase state")

    # Check user identity
    name_result = await self._command_runner.run(["git", "config", "user.name"])
    email_result = await self._command_runner.run(["git", "config", "user.email"])
    if not name_result.success or not name_result.stdout.strip():
        errors.append("Git user.name not configured")
    if not email_result.success or not email_result.stdout.strip():
        errors.append("Git user.email not configured")

    return ValidationResult(
        success=len(errors) == 0,
        component="GitRunner",
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
```

---

### 6. GitHub CLI Authentication Validation

**Question**: How to validate GitHub CLI is properly authenticated with required scopes?

**Decision**: Use `gh auth status` for auth check; scope verification via `gh auth status --show-token` parsing.

**Rationale**:

- FR-004 requires checking auth status and token scopes
- `gh auth status` exits non-zero if not authenticated
- Scope information available via `gh auth status` output parsing
- Existing `GitHubCLIRunner` already has auth check pattern

**Implementation Approach**:

1. Check `gh` on PATH via `shutil.which`
2. Run `gh auth status` - validates login
3. Parse output for scope information (or use exit code 4 for auth required)

**Code Pattern**:

```python
async def validate(self) -> ValidationResult:
    errors = []

    # Check gh available
    if not shutil.which("gh"):
        errors.append("GitHub CLI (gh) not found")
        return ValidationResult(False, "GitHubCLIRunner", tuple(errors))

    # Check authentication
    result = await self._command_runner.run(["gh", "auth", "status"])
    if result.returncode == 4:  # GH_EXIT_AUTH_REQUIRED
        errors.append("GitHub CLI not authenticated. Run: gh auth login")
    elif not result.success:
        errors.append(f"GitHub CLI auth check failed: {result.stderr}")

    # Check for required scopes (repo, read:org)
    if result.success:
        # Parse auth status output for scopes
        if "repo" not in result.stdout.lower():
            errors.append("GitHub token missing 'repo' scope")

    return ValidationResult(
        success=len(errors) == 0,
        component="GitHubCLIRunner",
        errors=tuple(errors),
    )
```

---

### 7. Validation Tool Discovery

**Question**: How should ValidationRunner discover which tools to validate?

**Decision**: Use configured validation stages from `MaverickConfig.validation` to determine tools.

**Rationale**:

- FR-005 specifies validating configured tools
- Existing `ValidationConfig` already defines `format_cmd`, `lint_cmd`, `typecheck_cmd`, `test_cmd`
- Extract tool name from first element of each command list

**Implementation Approach**:

```python
async def validate(self) -> ValidationResult:
    errors = []
    tools_to_check = set()

    # Extract tool executables from configured commands
    for cmd in [self._format_cmd, self._lint_cmd, self._typecheck_cmd, self._test_cmd]:
        if cmd:
            tools_to_check.add(cmd[0])  # First element is the executable

    # Check each tool
    for tool in tools_to_check:
        if not shutil.which(tool):
            errors.append(f"Validation tool '{tool}' not found on PATH")

    return ValidationResult(
        success=len(errors) == 0,
        component="ValidationRunner",
        errors=tuple(errors),
    )
```

---

### 8. Workflow Integration Point

**Question**: Where should preflight validation be called in workflows?

**Decision**: Add `run_preflight()` method to `WorkflowDSLMixin` called before any state-changing operations.

**Rationale**:

- FR-007 requires preflight before any state changes
- FR-015 suggests shared method in mixin
- Both `FlyWorkflow` and `RefuelWorkflow` inherit from `WorkflowDSLMixin`
- Must run even in dry_run mode (FR-008)

**Implementation Approach**:

```python
class WorkflowDSLMixin:
    async def run_preflight(
        self,
        runners: list[ValidatableRunner],
        timeout_per_check: float = 5.0,
    ) -> PreflightResult:
        """Run preflight validation on all runners.

        Raises:
            PreflightValidationError: If any critical validation fails.
        """
        validator = PreflightValidator(
            runners=runners,
            timeout_per_check=timeout_per_check,
        )
        result = await validator.run()

        if not result.success:
            raise PreflightValidationError(result)

        return result
```

---

### 9. Custom Validator Configuration (P3)

**Question**: How should custom validators be configured in `maverick.toml`?

**Decision**: Add `[preflight.custom_tools]` section to config with tool name and optional version command.

**Rationale**:

- FR-005 mentions custom validation tools via config
- User Story 5 is P3 priority - design but don't implement fully
- Should follow existing config patterns

**Future Pattern** (for reference, not implemented in this feature):

```toml
[preflight]
timeout_seconds = 5

[preflight.custom_tools]
docker = { check_cmd = "docker --version" }
kubectl = { check_cmd = "kubectl version --client" }
```

---

## Summary of Decisions

| Topic               | Decision                                               |
| ------------------- | ------------------------------------------------------ |
| Parallel validation | `asyncio.gather` + `wait_for` timeouts                 |
| Interface type      | `typing.Protocol`                                      |
| Result structure    | Frozen dataclass with `to_dict()`                      |
| Error format        | Structured with issue + remediation + docs             |
| Git validation      | 4 checks: available, in-repo, not-conflicted, identity |
| GitHub validation   | PATH check + `gh auth status`                          |
| Tool discovery      | Extract from ValidationConfig commands                 |
| Integration point   | `WorkflowDSLMixin.run_preflight()`                     |
| Custom validators   | Future: `[preflight.custom_tools]` config              |

## Open Questions (None)

All technical questions resolved.
