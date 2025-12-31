# Research: Utility MCP Tools

**Feature Branch**: `006-utility-mcp-tools`
**Date**: 2025-12-15
**Status**: Complete

## Research Areas

### 1. ntfy.sh Integration Patterns

**Question**: How should we integrate with ntfy.sh for reliable notifications?

**Decision**: Use aiohttp for async HTTP POST requests to ntfy.sh endpoint

**Rationale**:
- ntfy.sh uses a simple HTTP API: POST to `https://ntfy.sh/{topic}` with message body
- Headers control priority, title, tags, and actions
- Async HTTP aligns with Constitution Principle I (Async-First)
- Simple request/response model fits MCP tool pattern

**Alternatives Considered**:
- `requests` library: Rejected - synchronous, would block event loop
- `httpx`: Acceptable alternative, but aiohttp already used in ecosystem
- websocket subscription: Over-engineering for notification sending

**Implementation Notes**:
```python
# Priority mapping
NTFY_PRIORITIES = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}

# Request structure
headers = {
    "Title": title,
    "Priority": str(NTFY_PRIORITIES[priority]),
    "Tags": ",".join(tags) if tags else None,
}
# POST body is the message text
```

**Graceful Degradation**:
- If ntfy.sh unreachable, retry 1-2 times with 2s timeout
- After retries, return success with warning (workflow must not block)
- Log failure for debugging but do not raise exception

---

### 2. Git CLI Tool Patterns

**Question**: How should git utility tools interact with git CLI?

**Decision**: Reuse `_run_git_command` pattern from `maverick.utils.git`, adapted for MCP tool responses

**Rationale**:
- Existing pattern in `utils/git.py` handles timeouts, error classification
- MCP tools need structured JSON responses, not exceptions
- Constitution Principle VII (Simplicity) - don't reinvent existing patterns

**Alternatives Considered**:
- GitPython library: Rejected - adds dependency, subprocess is sufficient for our operations
- Direct subprocess without helper: Rejected - duplicates error handling logic
- libgit2 bindings: Over-engineering for simple CLI operations

**Implementation Notes**:
```python
# Reuse from utils/git.py
async def _run_git_command(*args, cwd, timeout) -> tuple[str, str, int]

# Tool-specific wrappers return MCP responses
async def git_current_branch(args: dict) -> dict[str, Any]:
    stdout, stderr, rc = await _run_git_command("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)
    if rc != 0:
        return _error_response(...)
    return _success_response({"branch": stdout})
```

**Detached HEAD Handling**:
- `git rev-parse --abbrev-ref HEAD` returns "HEAD" in detached state
- Tool returns `{"branch": "(detached)"}` per spec FR-019a
- `git_push` in detached state returns error with remediation hint

**Authentication Error Detection**:
- Check stderr for patterns: "authentication", "Permission denied", "fatal: could not read"
- Return `{"isError": true, "error_code": "authentication_required", "message": "Run 'gh auth login' or configure git credentials"}`

---

### 3. Conventional Commit Format

**Question**: How should `git_commit` format conventional commit messages?

**Decision**: Build message string from type, scope, message, and breaking flag

**Rationale**:
- Conventional commits format: `type(scope): message` or `type!: message` for breaking
- Simple string formatting, no external library needed
- Matches existing project conventions

**Format Rules**:
```
# With scope
feat(api): add new endpoint

# Without scope
fix: correct validation

# Breaking change
feat(api)!: breaking change
```

**Implementation**:
```python
def _format_commit_message(type: str, scope: str | None, message: str, breaking: bool) -> str:
    prefix = type
    if scope:
        prefix = f"{type}({scope})"
    if breaking:
        prefix = f"{prefix}!"
    return f"{prefix}: {message}"
```

---

### 4. Validation Output Parsing

**Question**: How should `parse_validation_output` extract structured errors?

**Decision**: Use regex patterns for ruff and mypy output formats

**Rationale**:
- Ruff output: `file.py:10:5: E501 Line too long`
- Mypy output: `file.py:10: error: Type annotation needed [type-arg]`
- Regex parsing is straightforward and doesn't require external dependencies
- Patterns can be extended for other linters

**Ruff Pattern**:
```python
# Ruff format: path:line:col: code message
RUFF_PATTERN = r"^(.+):(\d+):(\d+): (\w+) (.+)$"

# Example: src/main.py:10:5: E501 Line too long (89 > 88)
# Groups: (file, line, col, code, message)
```

**Mypy Pattern**:
```python
# Mypy format: path:line: severity: message [code]
MYPY_PATTERN = r"^(.+):(\d+): (error|warning|note): (.+?)(?: \[(.+)\])?$"

# Example: src/main.py:10: error: Incompatible types [arg-type]
# Groups: (file, line, severity, message, code)
```

**Output Truncation**:
- Default limit: 50 errors
- Include summary: `{"errors": [...], "total_count": 1247, "truncated": true}`

---

### 5. Validation Command Configuration

**Question**: How should validation commands be configured?

**Decision**: Use existing `maverick.config` pattern with ValidationConfig model

**Rationale**:
- Existing `NotificationConfig` provides template for nested config
- Commands default to standard Python tooling (ruff, mypy, pytest)
- Override via maverick.yaml for project-specific commands

**Config Model**:
```python
class ValidationConfig(BaseModel):
    """Settings for validation commands."""
    format_cmd: list[str] = ["ruff", "format", "."]
    lint_cmd: list[str] = ["ruff", "check", "--fix", "."]
    typecheck_cmd: list[str] = ["mypy", "."]
    test_cmd: list[str] = ["pytest", "-x", "--tb=short"]
    timeout_seconds: int = Field(default=300, ge=30, le=600)  # 5 min default, max 10 min
```

**Existing Validation Utilities**:
- `maverick.utils.validation` already has `VALIDATION_COMMANDS` dict
- `run_validation_step()` handles subprocess execution with timeout
- MCP tools can wrap these existing utilities

---

### 6. MCP Tool Response Format

**Question**: What is the correct MCP response format for tools?

**Decision**: Follow established pattern from `github.py`

**Rationale**:
- Existing `_success_response()` and `_error_response()` helpers in `github.py`
- Consistent with MCP protocol expectations
- Enables Claude to parse and act on structured responses

**Success Response**:
```python
{
    "content": [
        {"type": "text", "text": '{"key": "value", ...}'}
    ]
}
```

**Error Response**:
```python
{
    "content": [
        {
            "type": "text",
            "text": '{"isError": true, "message": "...", "error_code": "..."}'
        }
    ]
}
```

---

### 7. Prerequisite Verification Strategy

**Question**: Should new tool servers verify prerequisites like `github.py`?

**Decision**: Different strategies per server

**Rationale**:
- Git tools: Yes, verify git is installed and we're in a repo (like github.py)
- Notification tools: No - graceful degradation handles missing config
- Validation tools: No - individual commands handle missing tools

**Git Tools Prerequisites**:
```python
async def _verify_git_prerequisites(cwd: Path) -> None:
    """Verify git is installed and we're in a repository."""
    # Check git installed
    # Check inside git repo (git rev-parse --git-dir)
    # Do NOT check for remote (unlike github tools)
```

**Notification Tools**:
- No prerequisites - if not configured, tools return success with "disabled" message
- If configured but unreachable, tools return success with warning

---

## Summary of Key Decisions

| Area | Decision | Key Reason |
|------|----------|------------|
| HTTP Client | aiohttp | Async-first, simple API |
| Git Operations | Reuse _run_git_command | Simplicity, existing pattern |
| Commit Format | String formatting | No external deps needed |
| Output Parsing | Regex patterns | Standard formats, extensible |
| Config | Pydantic models | Existing pattern |
| Error Responses | JSON with isError flag | MCP protocol compliance |
| Prerequisites | Server-specific | Match operational requirements |

## Open Questions Resolved

All questions from Technical Context have been resolved. No NEEDS CLARIFICATION items remain.
