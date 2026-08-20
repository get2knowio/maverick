"""Per-step artifact resolution and verification (chain logic, not
workspace mechanics).

Landing itself — moving a step's `specs/<feature-dir>/**` delta from the
workspace into the user's checkout — now goes through the shared isolation
primitive's `IsolationSession.fold_back()` (057-isolated-bead-workspaces,
contracts/spec-chain-migration.md), scoped per call to
`specs/<feature-dir>`. What stays here is chain-specific: resolving which
`specs/NNN-<feature>` directory the specify step allocated, and verifying a
step's required artifacts exist before it counts as succeeded — both read
the filesystem, neither moves anything.
"""

from __future__ import annotations

import json
from pathlib import Path

from maverick.logging import get_logger
from maverick.workflows.spec_chain.constants import ChainStep

__all__ = ["resolve_feature_dir", "verify_step_artifacts"]

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
