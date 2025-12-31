---
name: maverick-python-peps
description: Python Enhancement Proposals (PEPs) and style guidelines
version: 1.0.0
triggers:
  - PEP
  - PEP 8
  - style
  - naming
  - import
  - docstring
  - snake_case
  - PascalCase
---

# Python PEPs Skill

Python Enhancement Proposals reference and style guidelines.

## PEP 8 - Style Guide

### Naming Conventions
- **modules**: `lowercase`, `lower_with_under`
- **packages**: `lowercase` (no underscores)
- **classes**: `PascalCase`
- **functions/methods**: `snake_case`
- **constants**: `SCREAMING_SNAKE_CASE`
- **private**: `_leading_underscore`

### Imports
```python
# Standard library
import os
import sys
from pathlib import Path

# Third-party
import requests
from pydantic import BaseModel

# Local
from myapp.models import User
from myapp.utils import helper
```

### Line Length
- Limit lines to 88-100 characters (Black default: 88)
- Break long lines at logical points

### Docstrings (PEP 257)
```python
def function(arg1: str, arg2: int) -> bool:
    """One-line summary.

    Detailed description if needed.

    Args:
        arg1: Description of arg1.
        arg2: Description of arg2.

    Returns:
        Description of return value.

    Raises:
        ValueError: When validation fails.
    """
```

## Key PEPs

- **PEP 8**: Style Guide
- **PEP 20**: Zen of Python
- **PEP 257**: Docstring Conventions
- **PEP 484**: Type Hints
- **PEP 585**: Type Hinting Generics In Standard Collections (list[str])
- **PEP 604**: Union Operator (str | None)
- **PEP 3134**: Exception Chaining (raise...from)

## Review Severity

- **MINOR**: PEP 8 violations (naming, import order, line length)
- **SUGGESTION**: Could follow PEP 257 for docstrings
