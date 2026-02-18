# AGENTS.md

This document provides comprehensive guidance for developing agents in Maverick using the Claude Agent SDK.

## Overview

**Agents** in Maverick are autonomous components that provide AI-powered judgment and decision-making. They follow a strict separation of concerns: agents know **HOW** to do tasks (prompting, reasoning, tool selection), while workflows orchestrate **WHAT** and **WHEN**.

## Agent Architecture

### Directory Structure

```
src/maverick/agents/
├── base.py              # MaverickAgent abstract base class
├── code_reviewer.py     # CodeReviewerAgent
├── implementer.py       # ImplementerAgent
├── issue_fixer.py       # IssueFixerAgent
├── generator.py         # GeneratorAgent (stateless text generation)
└── ...                  # Other specialized agents
```

### Separation of Concerns

| Component  | Responsibility                                                      |
|------------|---------------------------------------------------------------------|
| **Agents** | HOW to do a task (system prompts, tool selection, Claude SDK interaction) |
| **Workflows** | WHAT to do and WHEN (orchestration, state management, sequencing) |
| **Tools** | Wrap external systems (GitHub CLI, git, notifications) |
| **TUI** | Present state and capture input (no business logic) |

## Core Principles for Agents

### 1. Judgment Only, No Side Effects

**Rule**: Agents provide judgment (implementation/review/fix suggestions). They MUST NOT own deterministic side effects like git commits/pushes or running validation.

```python
# ✅ GOOD: Agent provides recommendations
class CodeReviewerAgent(MaverickAgent):
    async def review(self, diff: str) -> ReviewResult:
        # Agent analyzes and returns structured findings
        return ReviewResult(issues=[...], suggestions=[...])

# ❌ BAD: Agent performs side effects
class CodeReviewerAgent(MaverickAgent):
    async def review_and_commit(self, diff: str):
        # DON'T: git commits belong in workflows/runners
        subprocess.run(["git", "commit", "-m", "Applied fixes"])
```

**Workflows** own deterministic execution, retries, checkpointing, and error recovery policies.

### 2. Async-First

All agent methods MUST be async. Use `asyncio` patterns; no threading for I/O.

```python
from __future__ import annotations

class MyAgent(MaverickAgent):
    async def process(self, input_data: str) -> ProcessResult:
        # All I/O operations must be async
        result = await self.client.query(prompt)
        return ProcessResult(...)
```

### 3. Dependency Injection

Agents receive configuration and dependencies at construction time, not from global state.

```python
class MyAgent(MaverickAgent):
    def __init__(
        self,
        api_key: str,
        allowed_tools: list[str] | None = None,
        config: AgentConfig | None = None,
    ):
        super().__init__(api_key, allowed_tools, config)
        # Dependencies are injected, not created internally
```

### 4. Extract and Structure Outputs

**Rule**: Extract and structure agent outputs; do not return raw text.

```python
from pydantic import BaseModel
from dataclasses import dataclass

# ✅ GOOD: Structured output
@dataclass(frozen=True)
class ReviewResult:
    issues: list[Issue]
    suggestions: list[Suggestion]
    summary: str

class CodeReviewerAgent(MaverickAgent):
    async def review(self, diff: str) -> ReviewResult:
        result = await self.client.query(...)
        # Parse and structure the output
        return self._parse_review_result(result)

# ❌ BAD: Raw text output
class CodeReviewerAgent(MaverickAgent):
    async def review(self, diff: str) -> str:
        return await self.client.query(...)  # Unstructured
```

### 5. Type Safety

Complete type hints required. Use `@dataclass` or Pydantic `BaseModel` over plain dicts.

```python
from pydantic import BaseModel

# ✅ GOOD: Typed models
class ReviewInput(BaseModel):
    diff: str
    context: str
    file_paths: list[str]

# ❌ BAD: Untyped dicts
def review(self, input_data: dict[str, Any]) -> dict[str, Any]:
    ...
```

### 6. Fail Gracefully

One agent failure MUST NOT crash the entire workflow. Capture and report errors with context.

```python
from maverick.exceptions import AgentError
from maverick.logging import get_logger

logger = get_logger(__name__)

class MyAgent(MaverickAgent):
    async def process(self, data: str) -> Result:
        try:
            return await self._internal_process(data)
        except Exception as e:
            logger.error("agent_process_failed", error=str(e), data=data)
            raise AgentError(f"Processing failed: {e}") from e
```

## Claude Agent SDK Patterns

### Tool Permissions (Principle of Least Privilege)

Always specify `allowed_tools` explicitly. Only grant access to tools the agent needs.

```python
class CodeReviewerAgent(MaverickAgent):
    def __init__(
        self,
        api_key: str,
        allowed_tools: list[str] | None = None,
    ):
        # Default to minimal required tools
        if allowed_tools is None:
            allowed_tools = [
                "get_diff",
                "read_file",
                "list_changed_files",
            ]
        super().__init__(api_key, allowed_tools)
```

### Stateful vs Stateless Interactions

- **`ClaudeSDKClient`**: Use for stateful/multi-turn interactions
- **`query()`**: Use for one-shot, stateless interactions

```python
# Stateful (conversation history maintained)
async with self.client:
    response1 = await self.client.query("Analyze this code...")
    response2 = await self.client.query("Now suggest improvements")

# Stateless (single query)
result = await self.client.query("Summarize this diff", one_shot=True)
```

### Custom Tools with MCP

Custom tools use the `@tool` decorator and `create_sdk_mcp_server()`:

```python
from claude_sdk import tool, create_sdk_mcp_server

@tool
async def analyze_complexity(file_path: str) -> dict:
    """Analyze code complexity metrics for a file."""
    # Implementation
    return {"cyclomatic_complexity": 5, ...}

# Create MCP server with custom tools
mcp_server = create_sdk_mcp_server([analyze_complexity])
```

### Hooks for Safety and Logging

Hooks are async functions matching the SDK's hook signature:

```python
from maverick.hooks import create_safety_hooks

hooks = create_safety_hooks(
    max_tokens_per_hour=100_000,
    enable_logging=True,
)

agent = MyAgent(
    api_key=api_key,
    hooks=hooks,
)
```

## Code Style for Agents

| Element   | Convention           | Example                            |
|-----------|----------------------|------------------------------------|
| Classes   | PascalCase           | `CodeReviewerAgent`, `ImplementerAgent` |
| Methods   | snake_case           | `execute_review`, `generate_impl`  |
| Constants | SCREAMING_SNAKE_CASE | `MAX_RETRIES`, `DEFAULT_TIMEOUT`   |
| Private   | Leading underscore   | `_build_prompt`, `_parse_result`   |

### Docstrings

Use Google-style docstrings for all public methods:

```python
class CodeReviewerAgent(MaverickAgent):
    async def review(self, diff: str, context: str) -> ReviewResult:
        """Review code changes and provide structured feedback.
        
        Args:
            diff: Git diff of changes to review
            context: Additional context (spec, guidelines, etc.)
            
        Returns:
            ReviewResult containing issues, suggestions, and summary
            
        Raises:
            AgentError: If review fails or times out
            ValueError: If diff is empty or invalid
        """
        ...
```

### Exception Hierarchy

All agent exceptions inherit from `AgentError`:

```python
from maverick.exceptions import MaverickError

class AgentError(MaverickError):
    """Base exception for all agent errors."""
    pass

class AgentTimeoutError(AgentError):
    """Agent operation timed out."""
    pass

class AgentValidationError(AgentError):
    """Agent input validation failed."""
    pass
```

## Third-Party Library Standards for Agents

### Logging with structlog

**Use for**: All logging in agent code

```python
from maverick.logging import get_logger

logger = get_logger(__name__)

class MyAgent(MaverickAgent):
    async def process(self, data: str) -> Result:
        logger.info("agent_processing_started", agent=self.__class__.__name__)
        try:
            result = await self._process(data)
            logger.info("agent_processing_completed", result_size=len(result))
            return result
        except Exception as e:
            logger.error("agent_processing_failed", error=str(e), data=data)
            raise
```

**Do NOT**: Use standard library `logging.getLogger(__name__)`

### Retry Logic with tenacity

**Use for**: All retry logic with exponential backoff

```python
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

class MyAgent(MaverickAgent):
    async def process_with_retry(self, data: str) -> Result:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
        ):
            with attempt:
                return await self._risky_operation(data)
```

**Do NOT**: Write manual `for attempt in range(retries):` loops

### Secret Detection

**Use for**: Detecting secrets/credentials before commits

```python
from maverick.utils.secrets import detect_secrets

findings = detect_secrets(file_content)
if findings:
    raise SecurityError(f"Potential secrets found: {findings}")
```

## Testing Requirements for Agents

### Test Coverage

Every agent MUST have tests covering:

1. **Happy path**: Normal successful operation
2. **Error handling**: Invalid inputs, timeouts, API failures
3. **Concurrency**: Multiple simultaneous calls (for async agents)
4. **Edge cases**: Empty inputs, malformed data, boundary conditions

### Test Structure

```python
import pytest
from unittest.mock import AsyncMock, patch

from maverick.agents.code_reviewer import CodeReviewerAgent

@pytest.fixture
async def reviewer_agent():
    """Create a CodeReviewerAgent for testing."""
    return CodeReviewerAgent(api_key="test-key")

@pytest.mark.asyncio
async def test_review_success(reviewer_agent):
    """Test successful code review."""
    diff = "diff --git a/file.py..."
    
    result = await reviewer_agent.review(diff)
    
    assert isinstance(result, ReviewResult)
    assert len(result.issues) >= 0

@pytest.mark.asyncio
async def test_review_empty_diff_raises_error(reviewer_agent):
    """Test that empty diff raises ValueError."""
    with pytest.raises(ValueError, match="diff cannot be empty"):
        await reviewer_agent.review("")

@pytest.mark.asyncio
async def test_review_timeout(reviewer_agent):
    """Test handling of timeout errors."""
    with patch.object(reviewer_agent.client, 'query', side_effect=TimeoutError):
        with pytest.raises(AgentTimeoutError):
            await reviewer_agent.review("diff...")
```

### Mock External Dependencies

Always mock Claude API, GitHub CLI, and filesystem operations:

```python
@pytest.fixture
def mock_claude_client():
    with patch('claude_sdk.ClaudeSDKClient') as mock:
        mock.return_value.query = AsyncMock(return_value="Mocked response")
        yield mock
```

## Hardening Requirements

All external calls in agents MUST have:

1. **Explicit timeouts**: No infinite waits
2. **Retry logic**: Exponential backoff for network operations
3. **Specific exception handling**: No bare `except Exception`

```python
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential
import asyncio

class MyAgent(MaverickAgent):
    DEFAULT_TIMEOUT = 30.0
    MAX_RETRIES = 3
    
    async def process(self, data: str) -> Result:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.MAX_RETRIES),
            wait=wait_exponential(multiplier=1, min=1, max=10),
        ):
            with attempt:
                try:
                    return await asyncio.wait_for(
                        self._process_internal(data),
                        timeout=self.DEFAULT_TIMEOUT,
                    )
                except asyncio.TimeoutError as e:
                    logger.error("agent_timeout", timeout=self.DEFAULT_TIMEOUT)
                    raise AgentTimeoutError(f"Timed out after {self.DEFAULT_TIMEOUT}s") from e
                except SpecificAPIError as e:
                    logger.error("api_error", error=str(e))
                    raise AgentError(f"API error: {e}") from e
```

## Modularization Guidelines for Agents

- **Soft limit**: Keep agent modules < ~500 LOC
- **Refactor trigger**: If an agent exceeds ~800 LOC, split into:
  - `agents/<name>/agent.py` - Main agent class
  - `agents/<name>/models.py` - Input/output models
  - `agents/<name>/prompts.py` - System prompts and templates
  - `agents/<name>/parsers.py` - Output parsing logic

## Agent Examples

### Minimal Agent Template

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.exceptions import AgentError
from maverick.logging import get_logger

logger = get_logger(__name__)

@dataclass(frozen=True)
class MyAgentInput:
    """Input data for MyAgent."""
    data: str
    context: str

@dataclass(frozen=True)
class MyAgentOutput:
    """Output from MyAgent."""
    result: str
    confidence: float

class MyAgent(MaverickAgent):
    """Agent that does something useful.
    
    This agent analyzes input data and provides recommendations
    based on the provided context.
    """
    
    SYSTEM_PROMPT = """You are an expert assistant that..."""
    
    def __init__(
        self,
        api_key: str,
        allowed_tools: list[str] | None = None,
    ):
        if allowed_tools is None:
            allowed_tools = ["read_file", "get_context"]
        super().__init__(api_key, allowed_tools)
    
    async def process(self, input_data: MyAgentInput) -> MyAgentOutput:
        """Process input and return structured output.
        
        Args:
            input_data: Input data with context
            
        Returns:
            MyAgentOutput with result and confidence
            
        Raises:
            AgentError: If processing fails
        """
        try:
            prompt = self._build_prompt(input_data)
            response = await self.client.query(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error("agent_process_failed", error=str(e))
            raise AgentError(f"Processing failed: {e}") from e
    
    def _build_prompt(self, input_data: MyAgentInput) -> str:
        """Build the prompt for Claude."""
        return f"{self.SYSTEM_PROMPT}\n\nData: {input_data.data}\n\nContext: {input_data.context}"
    
    def _parse_response(self, response: Any) -> MyAgentOutput:
        """Parse Claude's response into structured output."""
        # Parse response and extract structured data
        return MyAgentOutput(result=response, confidence=0.95)
```

## Common Anti-Patterns (Avoid These)

### ❌ Agents Performing Side Effects

```python
# BAD: Agent does git operations
class ImplementerAgent(MaverickAgent):
    async def implement_and_commit(self, task: str):
        code = await self._generate_code(task)
        subprocess.run(["git", "add", "."])  # NO!
        subprocess.run(["git", "commit", "-m", "..."]) # NO!
```

### ❌ Returning Unstructured Data

```python
# BAD: Returns raw string
async def review(self, diff: str) -> str:
    return await self.client.query(f"Review: {diff}")

# GOOD: Returns structured data
async def review(self, diff: str) -> ReviewResult:
    response = await self.client.query(f"Review: {diff}")
    return self._parse_review(response)
```

### ❌ Global State or Mutable Class Variables

```python
# BAD: Mutable class state
class MyAgent(MaverickAgent):
    cache = {}  # Shared across instances!
    
# GOOD: Instance state
class MyAgent(MaverickAgent):
    def __init__(self, ...):
        super().__init__(...)
        self._cache: dict[str, Any] = {}
```

### ❌ Blocking I/O in Async Methods

```python
# BAD: Blocking call in async method
async def process(self, data: str) -> Result:
    result = subprocess.run(["ls", "-l"])  # Blocks event loop!
    
# GOOD: Use async subprocess or CommandRunner
async def process(self, data: str) -> Result:
    from maverick.runners.command import CommandRunner
    runner = CommandRunner()
    result = await runner.run(["ls", "-l"])
```

## References

- **Claude Agent SDK**: `claude-agent-sdk` package documentation
- **Architecture**: `.specify/memory/constitution.md` (authoritative reference)
- **Code Style**: `CLAUDE.md` (general coding guidelines)
- **Testing**: `tests/agents/` (example test patterns)

## Recent Agent Implementations

- `002-base-agent`: MaverickAgent abstract base class with Claude Agent SDK integration
- `003-code-reviewer-agent`: CodeReviewerAgent with structured review output
- `004-implementer-issue-fixer-agents`: ImplementerAgent and IssueFixerAgent
- `019-generator-agents`: GeneratorAgent for stateless text generation
