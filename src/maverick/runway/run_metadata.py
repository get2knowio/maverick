"""Run metadata for organizing pipeline output per execution.

Each Maverick run (refuel → fly → land) gets a unique run_id.
All execution artifacts live under ``.maverick/runs/{run_id}/``.
The metadata file links the run to the flight plan and beads epic.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from maverick.logging import get_logger

__all__ = [
    "RunMetadata",
    "find_latest_run",
    "find_run_for_epic",
    "read_metadata",
    "write_metadata",
]

logger = get_logger(__name__)

_METADATA_FILE = "metadata.json"


@dataclass
class RunMetadata:
    """Per-run metadata linking run_id to plan and epic."""

    run_id: str
    plan_name: str
    epic_id: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(tz=UTC).isoformat())
    completed_at: str = ""
    status: str = "created"


def write_metadata(run_dir: Path, meta: RunMetadata) -> None:
    """Write metadata.json to a run directory."""
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / _METADATA_FILE
    path.write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")


def read_metadata(run_dir: Path) -> RunMetadata | None:
    """Read metadata.json from a run directory."""
    path = run_dir / _METADATA_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return RunMetadata(**data)
    except Exception as exc:
        logger.debug("run_metadata_read_failed", path=str(path), error=str(exc))
        return None


def find_run_for_epic(
    epic_id: str,
    base: Path | None = None,
) -> RunMetadata | None:
    """Find a run directory matching the given epic_id."""
    runs_dir = (base or Path.cwd()) / ".maverick" / "runs"
    if not runs_dir.is_dir():
        return None
    for candidate in sorted(runs_dir.iterdir(), reverse=True):
        meta = read_metadata(candidate)
        if meta and meta.epic_id == epic_id:
            return meta
    return None


def find_latest_run(
    plan_name: str,
    base: Path | None = None,
) -> RunMetadata | None:
    """Find the most recent run for a given plan name."""
    runs_dir = (base or Path.cwd()) / ".maverick" / "runs"
    if not runs_dir.is_dir():
        return None
    latest: RunMetadata | None = None
    for candidate in runs_dir.iterdir():
        meta = read_metadata(candidate)
        if (
            meta
            and meta.plan_name == plan_name
            and (latest is None or meta.started_at > latest.started_at)
        ):
            latest = meta
    return latest
