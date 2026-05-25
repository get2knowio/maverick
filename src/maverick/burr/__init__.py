"""Apache Burr orchestration substrate for maverick workflows.

This package supplies the shared building blocks that per-workflow Burr
applications use to surface progress and run end-to-end:

* :class:`BurrWorkflowDriver` — drives an ``Application.arun()`` and
  yields :class:`maverick.events.ProgressEvent` instances from a queue
  the actions emit into.
* :class:`ProgressEventHook` — Burr lifecycle hook that translates
  ``pre_run_step`` / ``post_run_step`` into ``StepStarted`` /
  ``StepCompleted`` and signals end-of-stream when a terminal action
  completes.

Per-workflow graphs live next to the workflow they implement
(``src/maverick/workflows/<name>/burr_graph.py``). This module only
holds the cross-cutting plumbing.
"""

from __future__ import annotations

from maverick.burr.driver import BurrWorkflowDriver
from maverick.burr.hooks import ProgressEventHook

__all__ = ["BurrWorkflowDriver", "ProgressEventHook"]
