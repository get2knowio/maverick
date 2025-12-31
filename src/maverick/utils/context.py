"""Context builder utilities for Maverick agents (compatibility shim).

This module provides backwards-compatible imports for context builder utilities
that have been refactored into focused modules.

All context builders are now in `maverick.utils.context_builders/`.
Helper utilities are in dedicated modules: text.py, secrets.py, paths.py,
files.py, budgets.py.

DEPRECATED: Import from the specific modules instead of this shim.
This module exists for backwards compatibility and may be removed in future versions.

Example (new style):
    ```python
    from maverick.utils.context_builders import build_implementation_context
    from maverick.utils.text import estimate_tokens
    from maverick.utils.secrets import detect_secrets
    ```

Example (old style, still works):
    ```python
    from maverick.utils.context import build_implementation_context
    from maverick.utils.context import estimate_tokens, detect_secrets
    ```
"""

from __future__ import annotations

# Re-export from new locations for backwards compatibility
from maverick.utils.budgets import fit_to_budget
from maverick.utils.context_builders import (
    build_fix_context,
    build_implementation_context,
    build_issue_context,
    build_review_context,
)
from maverick.utils.files import (
    _read_conventions,
    _read_file_safely,
    truncate_file,
)
from maverick.utils.paths import extract_file_paths
from maverick.utils.secrets import detect_secrets
from maverick.utils.text import estimate_tokens, truncate_line

__all__ = [
    "build_fix_context",
    "build_implementation_context",
    "build_issue_context",
    "build_review_context",
    "detect_secrets",
    "estimate_tokens",
    "extract_file_paths",
    "fit_to_budget",
    "truncate_file",
    "truncate_line",
]

# Private functions for backwards compatibility with tests
# These are not in __all__ but are available for import
__all__ += [
    "_read_conventions",
    "_read_file_safely",
]
