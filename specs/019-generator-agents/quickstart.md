# Quickstart: Generator Agents

**Branch**: `019-generator-agents` | **Date**: 2025-12-18

## Overview

Generator Agents are lightweight, single-purpose text generators that use the Claude Agent SDK's `query()` function for stateless, tool-free text generation. They're designed to be fast, focused, and easy to integrate into workflows.

## Prerequisites

- Python 3.10+
- Claude Agent SDK (`claude-agent-sdk`)
- `ANTHROPIC_API_KEY` environment variable set

## Installation

Generators are part of the Maverick package. No additional installation required.

```bash
# Ensure Maverick is installed
pip install -e .

# Verify Claude Agent SDK
python -c "from claude_agent_sdk import query; print('OK')"
```

## Quick Examples

### Generate a Commit Message

```python
import asyncio
from maverick.agents.generators import CommitMessageGenerator

async def main():
    generator = CommitMessageGenerator()

    # Provide diff and file stats from git
    context = {
        "diff": """
diff --git a/src/auth.py b/src/auth.py
index 1234567..abcdefg 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,6 +10,12 @@ class AuthService:
     def login(self, username: str, password: str) -> bool:
         return self._validate(username, password)

+    def reset_password(self, email: str) -> bool:
+        \"\"\"Send password reset email.\"\"\"
+        user = self._find_user_by_email(email)
+        if user:
+            return self._send_reset_email(user)
+        return False
""",
        "file_stats": {
            "files_changed": 1,
            "insertions": 6,
            "deletions": 0,
        },
    }

    message = await generator.generate(context)
    print(message)
    # Output: feat(auth): add password reset functionality

asyncio.run(main())
```

### Generate a PR Description

```python
import asyncio
from maverick.agents.generators import PRDescriptionGenerator

async def main():
    generator = PRDescriptionGenerator()

    context = {
        "commits": [
            {"hash": "abc1234", "message": "feat(auth): add password reset", "author": "dev"},
            {"hash": "def5678", "message": "test(auth): add reset tests", "author": "dev"},
        ],
        "diff_stats": {
            "files_changed": 3,
            "insertions": 120,
            "deletions": 5,
        },
        "task_summary": "Implement password reset functionality for user authentication",
        "validation_results": {
            "passed": True,
            "stages": [
                {"name": "lint", "passed": True},
                {"name": "test", "passed": True},
                {"name": "build", "passed": True},
            ],
        },
    }

    description = await generator.generate(context)
    print(description)
    # Output: Markdown with Summary, Changes, Testing sections

asyncio.run(main())
```

### Analyze Code

```python
import asyncio
from maverick.agents.generators import CodeAnalyzer

async def main():
    analyzer = CodeAnalyzer()

    context = {
        "code": """
def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
""",
        "analysis_type": "review",  # or "explain", "summarize"
        "language": "python",
    }

    analysis = await analyzer.generate(context)
    print(analysis)
    # Output: Review with performance concerns, suggestions

asyncio.run(main())
```

### Explain an Error

```python
import asyncio
from maverick.agents.generators import ErrorExplainer

async def main():
    explainer = ErrorExplainer()

    context = {
        "error_output": """
TypeError: unsupported operand type(s) for +: 'int' and 'str'
  File "main.py", line 10, in calculate
    return value + suffix
""",
        "source_context": """
def calculate(value: int, suffix: str) -> str:
    return value + suffix  # Bug: missing str()
""",
        "error_type": "type",
    }

    explanation = await explainer.generate(context)
    print(explanation)
    # Output: Explanation with fix suggestion

asyncio.run(main())
```

## Integration with Workflows

Generators are designed to be called by workflows at specific points:

```python
# In FlyWorkflow
async def _create_commit_message(self, diff: str, stats: dict) -> str:
    generator = CommitMessageGenerator()
    return await generator.generate({
        "diff": diff,
        "file_stats": stats,
    })

# In PR creation phase
async def _create_pr_description(self, ...) -> str:
    generator = PRDescriptionGenerator()
    return await generator.generate({
        "commits": commits,
        "diff_stats": stats,
        "task_summary": summary,
        "validation_results": results,
    })
```

## Error Handling

Generators raise `GeneratorError` on failure:

```python
from maverick.exceptions import GeneratorError

try:
    message = await generator.generate(context)
except GeneratorError as e:
    print(f"Generation failed: {e.message}")
    print(f"Generator: {e.generator_name}")
    # Caller handles retry logic
```

## Input Constraints

| Generator | Max Input | Truncation Behavior |
|-----------|-----------|---------------------|
| CommitMessageGenerator | 100KB diff | Truncates with warning |
| PRDescriptionGenerator | N/A | No truncation |
| CodeAnalyzer | 10KB code | Truncates with warning |
| ErrorExplainer | 10KB source | Truncates with warning |

## Testing

Generators are fully testable with mocked Claude responses:

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_commit_message_generator():
    with patch("maverick.agents.generators.base.query") as mock_query:
        # Mock Claude response
        mock_query.return_value = AsyncMock()
        mock_query.return_value.__aiter__.return_value = [
            # Mock AssistantMessage with TextBlock
        ]

        generator = CommitMessageGenerator()
        result = await generator.generate({
            "diff": "...",
            "file_stats": {"insertions": 10, "deletions": 0},
        })

        assert result.startswith(("feat", "fix", "docs"))
```

## Best Practices

1. **Keep contexts minimal**: Only include necessary fields
2. **Let workflows retry**: Generators fail fast; workflows handle retry
3. **Validate output**: Consumers should validate generator output format
4. **Log for debugging**: Enable DEBUG logging to see inputs/outputs

## Next Steps

- See [data-model.md](./data-model.md) for detailed type definitions
- See [contracts/generator_api.py](./contracts/generator_api.py) for interface contracts
- See [spec.md](./spec.md) for full requirements and acceptance criteria
