# Research: Maverick Init with Claude-Powered Detection

**Feature**: 028-maverick-init | **Date**: 2025-12-29

## Research Summary

This document consolidates research findings for implementing the unified `maverick init` command with Claude-powered project detection and Anthropic API preflight validation.

---

## 1. Claude Agent SDK Usage for Project Detection

### Decision: Use `claude_agent_sdk.query()` for stateless, single-turn detection

### Rationale
- Project type detection is a single-shot query with no tool use required
- The `query()` function is designed for exactly this use case
- GeneratorAgent pattern already established in codebase (generators/base.py)
- Lower overhead than ClaudeSDKClient for stateful interactions

### Implementation Pattern
```python
from claude_agent_sdk import ClaudeAgentOptions, query

async def detect_project_type(project_context: str) -> ProjectDetectionResult:
    options = ClaudeAgentOptions(
        system_prompt=PROJECT_DETECTION_SYSTEM_PROMPT,
        model="claude-3-5-haiku-20241022",  # Fast, cheap, sufficient
        max_turns=1,
        allowed_tools=[],  # No tools needed
    )

    messages = []
    async for message in query(prompt=project_context, options=options):
        messages.append(message)

    # Extract structured response from AssistantMessage
    return parse_detection_response(messages)
```

### Alternatives Considered
1. **ClaudeSDKClient**: Rejected - overkill for single-turn, no tool use needed
2. **Direct Anthropic API**: Rejected - no SDK abstraction, manual message handling
3. **Hardcoded heuristics only**: Rejected - spec requires Claude analysis (FR-007)

---

## 2. Anthropic API Validation Method

### Decision: Send minimal completion request with max_tokens=1

### Rationale
- FR-005 explicitly specifies "minimal completion request (e.g., 'Hi' with max_tokens=1)"
- Validates API key is valid and has access to the configured model
- Minimal token usage (1 input + 1 output token)
- Same pattern used for health checks in other AI integrations

### Implementation Pattern
```python
from claude_agent_sdk import ClaudeAgentOptions, query

async def validate_anthropic_api(model: str = "claude-3-5-haiku-20241022") -> bool:
    """Validate Anthropic API access with minimal request.

    Returns:
        True if API is accessible and model is available.

    Raises:
        AnthropicAPIError: If validation fails with details.
    """
    options = ClaudeAgentOptions(
        model=model,
        max_turns=1,
        allowed_tools=[],
    )

    try:
        async for _ in query(prompt="Hi", options=options):
            pass  # Just need success, ignore response
        return True
    except Exception as e:
        raise AnthropicAPIError(f"API validation failed: {e}")
```

### Alternatives Considered
1. **List models endpoint**: Rejected - not available in Claude SDK
2. **Longer test prompt**: Rejected - wastes tokens, no additional validation
3. **Skip validation**: Rejected - spec requires preflight check (FR-005, FR-016, FR-017)

---

## 3. Project Type Detection Strategy

### Decision: Hybrid approach - marker files first, Claude for analysis and disambiguation

### Rationale
- Marker files provide fast, deterministic detection for common cases
- Claude provides intelligent analysis for ambiguous or monorepo scenarios
- Fallback to Python defaults if Claude unavailable (`--no-detect` flag)
- Supports spec requirement for Claude recommendation of "primary" type (Clarification session)

### Marker File Mappings

| Project Type | Marker Files | Priority |
|-------------|--------------|----------|
| Python | `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements.txt` | 1 |
| Node.js | `package.json` | 2 |
| Go | `go.mod` | 3 |
| Rust | `Cargo.toml` | 4 |
| Ansible Collection | `galaxy.yml` | 5 |
| Ansible Playbook | `requirements.yml`, `ansible.cfg`, `playbooks/` | 6 |

### Claude Detection Context
Send to Claude:
1. Directory tree (depth 2-3, excluding common ignores)
2. Content of detected marker files (truncated to ~2000 chars each)
3. Request structured JSON response with:
   - `detected_types`: List of detected project types
   - `primary_type`: Recommended primary type
   - `confidence`: high/medium/low
   - `findings`: List of evidence strings
   - `validation_commands`: Dict of recommended commands

### Alternatives Considered
1. **Claude only**: Rejected - slower, uses tokens for obvious cases
2. **Markers only**: Rejected - spec requires Claude analysis (FR-007)
3. **LLM fine-tuning**: Rejected - over-engineering, Haiku sufficient

---

## 4. Git Remote URL Parsing

### Decision: Reuse existing regex patterns from workflow modules

### Rationale
- FlyWorkflow and RefuelWorkflow already have proven patterns
- SSH and HTTPS formats both supported
- Handles optional `.git` suffix
- Returns owner/repo format directly

### Implementation Pattern
```python
import re
from maverick.git import AsyncGitRepository

SSH_PATTERN = re.compile(r"git@[^:]+:([^/]+)/([^/]+?)(?:\.git)?$")
HTTPS_PATTERN = re.compile(r"https?://[^/]+/([^/]+)/([^/]+?)(?:\.git)?$")

async def parse_git_remote(repo: AsyncGitRepository) -> tuple[str | None, str | None]:
    """Extract owner and repo from git remote URL.

    Returns:
        Tuple of (owner, repo) or (None, None) if not parseable.
    """
    remote_url = await repo.get_remote_url()
    if not remote_url:
        return None, None

    for pattern in [SSH_PATTERN, HTTPS_PATTERN]:
        match = pattern.search(remote_url)
        if match:
            return match.group(1), match.group(2)

    return None, None
```

### Alternatives Considered
1. **New regex patterns**: Rejected - existing patterns proven in production
2. **gh CLI parsing**: Rejected - adds external dependency, slower
3. **GitPython remote parsing**: Rejected - doesn't extract owner/repo directly

---

## 5. Prerequisite Validation Structure

### Decision: Sequential validation with early termination on critical failures

### Rationale
- Git must be installed before checking if in a repo
- gh CLI must be installed before checking authentication
- ANTHROPIC_API_KEY must be set before API validation
- Fast failure saves time on obvious missing prerequisites

### Validation Sequence

```
1. git --version (installed?)
   └── Fail: "Git not installed. Install from https://git-scm.com/"

2. git rev-parse --git-dir (in repo?)
   └── Fail: "Not in a git repository. Run: git init"

3. gh --version (installed?)
   └── Fail: "GitHub CLI not installed. Install from https://cli.github.com/"

4. gh auth status (authenticated?)
   └── Fail: "GitHub CLI not authenticated. Run: gh auth login"

5. ANTHROPIC_API_KEY env var (set?)
   └── Fail: "ANTHROPIC_API_KEY not set. Run: export ANTHROPIC_API_KEY=sk-..."

6. Claude API ping (accessible?)
   └── Fail: "Anthropic API inaccessible. Check key permissions and plan limits."
```

### Alternatives Considered
1. **Parallel validation**: Rejected - dependencies require sequence
2. **Continue on failure**: Rejected - later checks would fail anyway
3. **Interactive prompts**: Rejected - FR-011 prohibits interactive prompts

---

## 6. Validation Command Defaults by Project Type

### Decision: Use ruff/pytest for Python, language-specific tools for others

### Rationale
- Maverick is a Python project, ruff/pytest are standard
- Other languages have canonical tooling
- Spec lists expected tools for Python and Ansible (acceptance scenarios)

### Default Command Mappings

| Project Type | format_cmd | lint_cmd | typecheck_cmd | test_cmd |
|-------------|------------|----------|---------------|----------|
| Python | `ruff format .` | `ruff check --fix .` | `mypy .` | `pytest -x --tb=short` |
| Node.js | `prettier --write .` | `eslint --fix .` | `tsc --noEmit` | `npm test` |
| Go | `gofmt -w .` | `golangci-lint run` | N/A (compiled) | `go test ./...` |
| Rust | `cargo fmt` | `cargo clippy --fix` | N/A (compiled) | `cargo test` |
| Ansible Collection | `yamllint .` | `ansible-lint` | N/A | `molecule test` |
| Ansible Playbook | `yamllint .` | `ansible-lint` | N/A | `ansible-playbook --syntax-check` |
| unknown | `ruff format .` | `ruff check --fix .` | `mypy .` | `pytest -x --tb=short` |

### Alternatives Considered
1. **No defaults**: Rejected - poor UX, spec requires defaults (Edge Case #2)
2. **Auto-detect installed tools**: Rejected - adds complexity, slower
3. **Interactive selection**: Rejected - FR-011 prohibits interactive prompts

---

## 7. API Key Redaction for Output

### Decision: Show prefix and last 4 characters only

### Rationale
- FR-020 explicitly requires redaction showing "only prefix and last 4 characters"
- Pattern: `sk-ant-...xxxx` where xxxx is last 4 chars
- Existing security.py has full redaction, need partial redaction variant

### Implementation Pattern
```python
def redact_api_key(key: str) -> str:
    """Redact API key showing only prefix and last 4 chars.

    Example: sk-ant-abc123xyz → sk-ant-...xyz
    """
    if not key or len(key) < 10:
        return "***INVALID***"

    # Find prefix (sk-ant- or sk-)
    prefix_match = re.match(r"(sk-(?:ant-)?)", key)
    prefix = prefix_match.group(1) if prefix_match else "sk-"

    return f"{prefix}...{key[-4:]}"
```

### Alternatives Considered
1. **Full redaction**: Rejected - FR-020 requires partial visibility
2. **First 4 + last 4**: Rejected - spec says prefix + last 4
3. **No redaction**: Rejected - security risk, FR-020 requires it

---

## 8. Preflight Integration for Workflows

### Decision: Add AnthropicAPIValidator as ValidatableRunner in preflight

### Rationale
- Follows existing runner discovery pattern in WorkflowDSLMixin
- FR-016/FR-017 require API validation in fly/refuel preflight
- Validators are async with validate() method
- Integrates seamlessly with existing PreflightValidator

### Implementation Pattern
```python
@dataclass
class AnthropicAPIValidator:
    """Validates Anthropic API access for workflow preflight."""

    model: str = "claude-3-5-haiku-20241022"
    timeout: float = 10.0

    async def validate(self) -> ValidationResult:
        """Validate API access.

        Returns:
            ValidationResult with success status and any errors.
        """
        try:
            await validate_anthropic_api(self.model, timeout=self.timeout)
            return ValidationResult(
                success=True,
                component="AnthropicAPI",
                errors=(),
                warnings=(),
                duration_ms=...,
            )
        except AnthropicAPIError as e:
            return ValidationResult(
                success=False,
                component="AnthropicAPI",
                errors=(str(e),),
                warnings=(),
                duration_ms=...,
            )
```

### Alternatives Considered
1. **Separate preflight step**: Rejected - duplicates existing pattern
2. **Check in agent __init__**: Rejected - too late, workflow already started
3. **Config-time validation**: Rejected - API state can change

---

## 9. Deprecation Warning for `config init`

### Decision: Print warning to stderr, then delegate to new `init` command

### Rationale
- FR-019 requires deprecation warning
- Smooth migration: warning + actual execution
- One version cycle before removal

### Implementation Pattern
```python
@config.command("init")
@click.option("--force", is_flag=True)
@click.pass_context
def config_init(ctx: click.Context, force: bool) -> None:
    """[DEPRECATED] Use 'maverick init' instead."""
    click.echo(
        click.style(
            "⚠️  'maverick config init' is deprecated. Use 'maverick init' instead.",
            fg="yellow",
        ),
        err=True,
    )
    # Delegate to new init command
    ctx.invoke(init_command, force=force)
```

### Alternatives Considered
1. **Remove immediately**: Rejected - breaks existing users
2. **Silent redirect**: Rejected - users won't learn about change
3. **Keep both permanently**: Rejected - maintenance burden

---

## 10. Monorepo Primary Type Selection

### Decision: Claude recommends primary type; user can override with `--type`

### Rationale
- Clarification session specifies: "Detect multiple types but ask Claude to recommend a single 'primary' type"
- Claude analyzes project structure to determine which type is dominant
- `--type` flag provides escape hatch (FR-012)

### Claude Prompt Strategy
```
Analyze this project and identify all detected project types.
Recommend a PRIMARY type based on:
1. Root-level configuration files (pyproject.toml at root vs in subdirectory)
2. Main entry points (where is the primary executable/entrypoint?)
3. Package managers at root level
4. Most recent/active development (if discernible)

Return JSON with detected_types (list) and primary_type (string).
```

### Alternatives Considered
1. **User prompt**: Rejected - FR-011 prohibits interactive prompts
2. **First detected**: Rejected - arbitrary, not intelligent
3. **Separate monorepo mode**: Rejected - over-engineering

---

## Key Decisions Summary

| Area | Decision | Spec Reference |
|------|----------|----------------|
| Claude SDK usage | `query()` function, stateless | FR-007 |
| Detection model | claude-3-5-haiku-20241022 | Clarification #4 |
| API validation | Minimal "Hi" request, max_tokens=1 | FR-005 |
| Remote parsing | Reuse existing SSH/HTTPS regex | FR-006 |
| Prereq order | Sequential with early termination | FR-001 to FR-005 |
| Project defaults | Python defaults for unknown | Edge Case #2 |
| Key redaction | Prefix + last 4 chars | FR-020 |
| Preflight | ValidatableRunner pattern | FR-016, FR-017 |
| Deprecation | Warning + delegate | FR-019 |
| Monorepo | Claude primary recommendation | Clarification #1 |
