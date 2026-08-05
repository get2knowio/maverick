"""Feature-dir resolution, shape detection, and template version gating.

See ``specs/048-speckit-refuel-ingestion/research.md`` D5 and D11 for the
rationale, and ``contracts/cli-refuel-speckit.md`` for the NAME
resolution table this module implements.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from maverick.speckit.errors import AmbiguousFeatureError

#: Bump when a new Spec Kit template shape is verified against
#: :mod:`maverick.speckit.parser`. 0.15 and 0.16 were verified: the
#: `## Phase N:` headings, `- [ ] T### [P] [US#]` task lines, the
#: `# Feature Specification:` title, and the `**SC-###**:` bullets this
#: package parses are all unchanged from 0.14 — the 0.15/0.16 template
#: deltas are prose and formatting only. What *did* change at 0.14 is
#: the agent surface (`.claude/commands/speckit.*.md` became
#: `.claude/skills/speckit-*/SKILL.md`); that is handled in
#: :mod:`maverick.workflows.spec_chain.steps`, not here.
SUPPORTED_SPECKIT_RANGE = ">=0.14,<0.17"

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?")
_RANGE_CLAUSE_RE = re.compile(r"^(>=|<=|>|<|==)\s*(.+)$")
_NNN_PREFIX_RE = re.compile(r"^\d{3,}-")

#: Default base directory for classic flight plans, relative to the repo
#: root. Mirrors ``maverick.cli.commands.flight_plan._group.DEFAULT_PLANS_DIR``
#: without importing the CLI layer into this pure artifact module.
_DEFAULT_PLANS_DIR = ".maverick/plans"


class TemplateCompatibility(BaseModel):
    """Result of checking the vendored Spec Kit template version."""

    model_config = ConfigDict(frozen=True)

    vendored_version: str | None = None
    supported_range: str = SUPPORTED_SPECKIT_RANGE
    status: Literal["supported", "unsupported", "unknown"]


class FeatureResolution(BaseModel):
    """CLI-boundary dispatch result for a ``maverick refuel <name>`` call."""

    model_config = ConfigDict(frozen=True)

    query: str
    speckit_dir: Path | None = None
    flight_plan_path: Path | None = None
    mode: Literal["speckit", "classic", "ambiguous", "unresolved"]


def _parse_version(version: str) -> tuple[int, int, int]:
    m = _VERSION_RE.match(version.strip())
    if not m:
        raise ValueError(f"unparseable version: {version!r}")
    major, minor, patch = m.group(1), m.group(2), m.group(3) or "0"
    return int(major), int(minor), int(patch)


def _version_satisfies(version: tuple[int, int, int], range_str: str) -> bool:
    for part in range_str.split(","):
        clause_m = _RANGE_CLAUSE_RE.match(part.strip())
        if not clause_m:
            continue
        op, bound_str = clause_m.group(1), clause_m.group(2)
        bound = _parse_version(bound_str)
        if op == ">=" and not version >= bound:
            return False
        if op == "<=" and not version <= bound:
            return False
        if op == ">" and not version > bound:
            return False
        if op == "<" and not version < bound:
            return False
        if op == "==" and version != bound:
            return False
    return True


def check_template_compatibility(cwd: Path) -> TemplateCompatibility:
    """Read ``.specify/init-options.json`` and gate on ``speckit_version``.

    Absent file/field -> ``"unknown"`` (warn and proceed structurally,
    per D5). Unparseable version -> ``"unknown"``. Outside
    :data:`SUPPORTED_SPECKIT_RANGE` -> ``"unsupported"`` (caller should
    fail upfront with E04).

    Args:
        cwd: Repository root (not the feature dir — version metadata is
            per-repo).

    Returns:
        A :class:`TemplateCompatibility`.
    """
    init_options_path = cwd / ".specify" / "init-options.json"
    if not init_options_path.is_file():
        return TemplateCompatibility(vendored_version=None, status="unknown")

    try:
        data = json.loads(init_options_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return TemplateCompatibility(vendored_version=None, status="unknown")

    version = data.get("speckit_version") if isinstance(data, dict) else None
    if not version:
        return TemplateCompatibility(vendored_version=None, status="unknown")

    try:
        parsed = _parse_version(str(version))
    except ValueError:
        return TemplateCompatibility(vendored_version=str(version), status="unknown")

    status: Literal["supported", "unsupported"] = (
        "supported" if _version_satisfies(parsed, SUPPORTED_SPECKIT_RANGE) else "unsupported"
    )
    return TemplateCompatibility(vendored_version=str(version), status=status)


def _has_speckit_shape(path: Path) -> bool:
    return path.is_dir() and (path / "spec.md").is_file() and (path / "tasks.md").is_file()


def _find_speckit_dir(cwd: Path, query: str) -> Path | None:
    """Resolve *query* to a single ``specs/NNN-name/`` directory.

    Match order: exact directory name, then (unique) ``NNN`` prefix or
    exact name suffix among shape-valid directories.

    Raises:
        AmbiguousFeatureError: More than one directory matches (E03).
    """
    specs_dir = cwd / "specs"
    if not specs_dir.is_dir():
        return None

    exact = specs_dir / query
    if _has_speckit_shape(exact):
        return exact

    candidates: list[Path] = []
    for child in sorted(specs_dir.iterdir()):
        if not _has_speckit_shape(child):
            continue
        name = child.name
        if name == query:
            continue
        prefix_match = (
            query.isdigit() and _NNN_PREFIX_RE.match(name) and name.startswith(f"{query}-")
        )
        if prefix_match or name.endswith(f"-{query}"):
            candidates.append(child)

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    raise AmbiguousFeatureError(
        f"multiple Spec Kit feature directories match {query!r}: "
        + ", ".join(str(c) for c in candidates),
        query=query,
        candidates=tuple(str(c) for c in candidates),
    )


def resolve_feature(
    query: str, *, cwd: Path, plans_dir: str = _DEFAULT_PLANS_DIR
) -> FeatureResolution:
    """Resolve *query* against both classic and Spec Kit dispatch shapes.

    Args:
        query: The ``NAME`` argument as given on the command line.
        cwd: Repository root.
        plans_dir: Base directory (absolute, or relative to *cwd*) where
            classic flight plans live. Must match the CLI's ``--plans-dir``
            so a plan under a non-default directory still resolves as
            ``"classic"``.

    Returns:
        A :class:`FeatureResolution` describing which mode(s) matched.

    Raises:
        AmbiguousFeatureError: Multiple Spec Kit directories match (E03).
    """
    speckit_dir = _find_speckit_dir(cwd, query)

    plans_input = Path(plans_dir)
    plans_base = plans_input if plans_input.is_absolute() else cwd / plans_input
    flight_plan_path: Path | None = None
    candidate_fp = plans_base / query / "flight-plan.md"
    if candidate_fp.is_file():
        flight_plan_path = candidate_fp

    mode: Literal["speckit", "classic", "ambiguous", "unresolved"]
    if speckit_dir is not None and flight_plan_path is not None:
        mode = "ambiguous"
    elif speckit_dir is not None:
        mode = "speckit"
    elif flight_plan_path is not None:
        mode = "classic"
    else:
        mode = "unresolved"

    return FeatureResolution(
        query=query,
        speckit_dir=speckit_dir,
        flight_plan_path=flight_plan_path,
        mode=mode,
    )


__all__ = [
    "SUPPORTED_SPECKIT_RANGE",
    "FeatureResolution",
    "TemplateCompatibility",
    "check_template_compatibility",
    "resolve_feature",
]
