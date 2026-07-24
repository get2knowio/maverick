"""Per-step artifact landing: workspace -> user checkout, atomically.

Only completed-step artifacts ever land (FR-016/FR-020). Landing is an
atomic staged copy — write the full current feature-dir tree to a temp
sibling, then rename it into place — so a crash mid-sync never leaves a
half-written file in the user's ``specs/`` tree.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from maverick.logging import get_logger
from maverick.workflows.spec_chain.constants import ChainStep

__all__ = ["land_step_artifacts", "resolve_feature_dir", "verify_step_artifacts"]

logger = get_logger(__name__)

#: Artifact(s) each step is responsible for, verified to exist in the
#: workspace's feature dir before the step counts as succeeded. Analyze is
#: read-only (FR-011) — it produces no new required artifact.
_STEP_ARTIFACTS: dict[ChainStep, tuple[str, ...]] = {
    ChainStep.SPECIFY: ("spec.md",),
    ChainStep.CLARIFY: ("spec.md",),
    ChainStep.PLAN: ("plan.md",),
    ChainStep.TASKS: ("tasks.md",),
    ChainStep.ANALYZE: (),
}


def resolve_feature_dir(*, workspace: Path, checkout_specs_before: set[str]) -> str | None:
    """Resolve the ``specs/NNN-<feature>`` directory the specify step
    allocated (R8).

    Diffs the workspace's ``specs/`` listing against the checkout's
    pre-specify listing; cross-checks ``.specify/feature.json`` when the
    diff is ambiguous (more than one new directory).

    Args:
        workspace: The hidden workspace, after the specify step ran.
        checkout_specs_before: Directory names under the checkout's
            ``specs/`` before the specify step started.

    Returns:
        The new feature directory's name (not a full path), or ``None``
        when nothing new was found.
    """
    specs_dir = workspace / "specs"
    if not specs_dir.is_dir():
        return None
    after = {p.name for p in specs_dir.iterdir() if p.is_dir()}
    new_dirs = after - checkout_specs_before

    if len(new_dirs) == 1:
        return next(iter(new_dirs))

    feature_json = workspace / ".specify" / "feature.json"
    if feature_json.is_file():
        try:
            data = json.loads(feature_json.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        feature_dir = data.get("feature_directory", "")
        if feature_dir:
            name = Path(feature_dir).name
            if name in after:
                return name

    if len(new_dirs) > 1:
        logger.warning("spec_chain_ambiguous_feature_dir", candidates=sorted(new_dirs))
    return None


def verify_step_artifacts(*, workspace: Path, feature_dir: str, step: ChainStep) -> list[str]:
    """Return this step's feature-dir-relative artifact paths, verified to
    exist on disk in the workspace.

    The filesystem is ground truth (R9) — a well-formed agent report with
    missing artifacts is still a step failure. An empty list for a
    non-analyze step means the step failed to produce what it must.
    """
    feature_path = workspace / "specs" / feature_dir
    return [name for name in _STEP_ARTIFACTS[step] if (feature_path / name).is_file()]


def land_step_artifacts(*, workspace: Path, checkout: Path, feature_dir: str) -> None:
    """Atomically sync ``specs/<feature_dir>/**`` from the workspace to the
    user's checkout, and nothing else.

    Always syncs the full current feature-dir tree (not just the latest
    step's new file) so steps that touch earlier artifacts (e.g. clarify
    rewriting ``spec.md``) land correctly too. Uses a staged
    copy-then-rename so a crash mid-sync never leaves a half-written
    directory in the checkout.

    Raises:
        OSError: The workspace feature dir is missing or the filesystem
            operation fails.
    """
    src_dir = workspace / "specs" / feature_dir
    if not src_dir.is_dir():
        raise FileNotFoundError(f"workspace feature dir missing: {src_dir}")

    dest_dir = checkout / "specs" / feature_dir
    dest_dir.parent.mkdir(parents=True, exist_ok=True)

    staged = dest_dir.with_name(f"{dest_dir.name}.landing-tmp")
    if staged.exists():
        shutil.rmtree(staged)
    shutil.copytree(src_dir, staged)

    if dest_dir.exists():
        backup = dest_dir.with_name(f"{dest_dir.name}.landing-prev")
        if backup.exists():
            shutil.rmtree(backup)
        dest_dir.rename(backup)
        staged.rename(dest_dir)
        shutil.rmtree(backup)
    else:
        staged.rename(dest_dir)

    logger.info("spec_chain_artifacts_landed", feature_dir=feature_dir, dest=str(dest_dir))
