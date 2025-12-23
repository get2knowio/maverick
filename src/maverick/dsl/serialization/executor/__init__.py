"""Workflow file executor package.

This package provides the WorkflowFileExecutor for running WorkflowFile instances
using registered components. The implementation is split into:
- executor.py: Main coordinator
- checkpointing.py: Checkpoint handling
- conditions.py: Expression/condition evaluation
- context.py: Context management
- handlers/: Per-step-type execution handlers
"""

from __future__ import annotations

from maverick.dsl.serialization.executor.executor import WorkflowFileExecutor

__all__ = ["WorkflowFileExecutor"]
