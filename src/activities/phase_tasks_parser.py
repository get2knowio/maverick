"""Temporal activity for parsing Speckit tasks.md documents.

Logging Events (structured logger):
    - parse_started: Activity begins parsing tasks.md
    - parse_completed: Successfully parsed phases from tasks.md
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from temporalio import activity

from src.models.phase_automation import PhaseDefinition
from src.utils.logging import get_structured_logger
from src.utils.tasks_markdown import compute_tasks_md_hash, parse_tasks_markdown


logger = get_structured_logger("activity.parse_tasks_md")


@dataclass(frozen=True)
class ParseTasksMdRequest:
    """Inputs for parsing a tasks.md document."""

    tasks_md_path: str | Path | None = None
    tasks_md_content: str | None = None

    def __post_init__(self) -> None:
        has_path = self.tasks_md_path is not None
        has_content = self.tasks_md_content is not None
        if has_path == has_content:
            raise ValueError("Provide either tasks_md_path or tasks_md_content")

        if has_path:
            raw_path = Path(self.tasks_md_path or "")
            if not raw_path.is_absolute():
                raise ValueError("tasks_md_path must be absolute")
            object.__setattr__(self, "tasks_md_path", str(raw_path))


@dataclass(frozen=True)
class ParseTasksMdResult:
    """Parsed representation of a tasks.md document."""

    source_path: str | None
    source_content: str
    tasks_md_hash: str
    phases: Sequence[PhaseDefinition]

    def __post_init__(self) -> None:
        if not self.source_content:
            raise ValueError("source_content must be non-empty")
        if not self.tasks_md_hash:
            raise ValueError("tasks_md_hash must be non-empty")
        if self.source_path is not None:
            object.__setattr__(self, "source_path", str(self.source_path))
        object.__setattr__(self, "phases", tuple(self.phases))


@activity.defn(name="parse_tasks_md")
def parse_tasks_md(request: ParseTasksMdRequest) -> ParseTasksMdResult:
    """Parse Speckit tasks markdown into structured phase definitions."""

    logger.info(
        "parse_started",
        source="path" if request.tasks_md_path else "content",
    )

    if request.tasks_md_path is not None:
        path = Path(request.tasks_md_path)
        if not path.exists():
            raise FileNotFoundError(f"tasks.md path does not exist: {path}")
        content = path.read_text(encoding="utf-8")
        source_path = str(path)
    else:
        content = request.tasks_md_content or ""
        source_path = None

    phases = parse_tasks_markdown(content)
    tasks_md_hash = compute_tasks_md_hash(content)

    logger.info(
        "parse_completed",
        phase_count=len(phases),
        source="path" if source_path else "content",
    )

    return ParseTasksMdResult(
        source_path=source_path,
        source_content=content,
        tasks_md_hash=tasks_md_hash,
        phases=phases,
    )


__all__ = ["ParseTasksMdRequest", "ParseTasksMdResult", "parse_tasks_md"]
