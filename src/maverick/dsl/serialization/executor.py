"""Import compatibility shim for WorkflowFileExecutor.

This module maintains backward compatibility for imports from the old location.
The actual implementation is now in the executor/ package.

DEPRECATED: Import from maverick.dsl.serialization.executor instead.
"""

from __future__ import annotations

# Re-export from new location
from maverick.dsl.serialization.executor.executor import WorkflowFileExecutor

__all__ = ["WorkflowFileExecutor"]
