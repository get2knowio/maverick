# maverick Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-10-28

## Active Technologies

- Python 3.11 + Temporal Python SDK; uv for dependency management; pytest (tests) (001-cli-prereq-check)

## Project Structure

```text
src/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.11: Follow standard conventions

## Temporal Workflow Best Practices

### Determinism Requirements
- **NEVER use `time.time()`** - Use `workflow.now()` instead (returns datetime)
- **NEVER use `datetime.now()`** - Use `workflow.now()` for current workflow time
- **NEVER use `random.random()`** - Use `workflow.random()` for deterministic randomness
- Duration calculation: Use `(workflow.now() - start_time).total_seconds()` for timedelta math

### Common Patterns
```python
# Correct: Deterministic time tracking
start_time = workflow.now()  # Returns datetime
# ... workflow logic ...
end_time = workflow.now()
duration_ms = int((end_time - start_time).total_seconds() * 1000)

# Incorrect: Non-deterministic (will fail)
import time
start_time = time.time()  # ❌ RestrictedWorkflowAccessError
```

### Activity Result Deserialization
- **Always specify `result_type`** when calling activities that return dataclasses
- Without `result_type`, Temporal deserializes to dict instead of dataclass

```python
# Correct: Specify result_type for proper deserialization
result = await workflow.execute_activity(
    "my_activity",
    start_to_close_timeout=timedelta(seconds=30),
    result_type=MyDataClass,  # ✓ Returns MyDataClass instance
)

# Incorrect: Missing result_type
result = await workflow.execute_activity(
    "my_activity",
    start_to_close_timeout=timedelta(seconds=30),
)  # ❌ Returns dict, causes AttributeError on attribute access
```

### Enum Serialization
- **DO NOT use Enums for Temporal data models** - Enums require custom serialization
- **Use `Literal` types with string values** - Works seamlessly with Temporal's JSON converter

```python
# Correct: Literal types for type safety
from typing import Literal

CheckStatus = Literal["pass", "fail"]

@dataclass
class PrereqCheckResult:
    tool: str
    status: CheckStatus  # ✓ Type-safe, serializes naturally
    message: str

# Incorrect: Enum requires custom serializer
class CheckStatus(Enum):  # ❌ Needs custom data converter
    PASS = "pass"
    FAIL = "fail"
```

### Why This Matters
Temporal workflows must be **deterministic** to support replay. Non-deterministic operations like system time calls will cause `RestrictedWorkflowAccessError` and prevent workflow execution. Proper type hints ensure correct deserialization and type safety.

## Recent Changes

- 001-cli-prereq-check: Added Python 3.11 + Temporal Python SDK; uv for dependency management; pytest (tests)

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
