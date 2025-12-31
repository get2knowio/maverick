---
name: maverick-python-typing
description: Python type hints, mypy, Protocol, and static typing best practices
version: 1.0.0
triggers:
  - "from typing import"
  - "from __future__ import annotations"
  - ": str"
  - ": int"
  - ": list["
  - ": dict["
  - "-> "
  - Protocol
  - TypeVar
  - Generic
  - mypy
  - "# type: ignore"
---

# Python Typing Skill

Expert guidance for Python type hints and static type checking.

## Modern Type Syntax

### Future Annotations (Python 3.7+)
```python
from __future__ import annotations

def process(items: list[str]) -> dict[str, int]:
    """Modern syntax without importing List, Dict."""
    return {item: len(item) for item in items}
```

### Union Types (Python 3.10+)
```python
# Modern
def func(value: str | None = None) -> int | float:
    pass

# Old style
from typing import Optional, Union
def func(value: Optional[str] = None) -> Union[int, float]:
    pass
```

## Type Hints Best Practices

### Function Signatures
```python
def greet(name: str, age: int) -> str:
    return f"Hello {name}, age {age}"
```

### Collections
```python
from collections.abc import Sequence, Mapping

def process_items(items: Sequence[str]) -> Mapping[str, int]:
    """Accept any sequence, return any mapping."""
    return {item: len(item) for item in items}
```

### Callable Types
```python
from collections.abc import Callable

def apply(func: Callable[[int], str], value: int) -> str:
    return func(value)
```

## Protocols (Structural Typing)

```python
from typing import Protocol

class Drawable(Protocol):
    def draw(self) -> None: ...

def render(obj: Drawable) -> None:
    """Accepts any object with draw() method."""
    obj.draw()
```

## Generics

```python
from typing import TypeVar, Generic

T = TypeVar('T')

class Stack(Generic[T]):
    def __init__(self) -> None:
        self._items: list[T] = []

    def push(self, item: T) -> None:
        self._items.append(item)

    def pop(self) -> T:
        return self._items.pop()
```

## Mypy Configuration

```ini
# pyproject.toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

## Review Severity

- **MAJOR**: Missing type hints on public APIs, using Any without justification
- **MINOR**: Missing return type hints, using old Union syntax
- **SUGGESTION**: Could use Protocol for duck typing, could use TypedDict
