"""Context file protection — prevent agents from mutating protected paths.

Two enforcement layers work together to make the guarantee universal:

* **Pre-write** (:mod:`maverick.protection.policy`'s ``PermissionGate``) —
  denies file-write tool calls targeting protected paths, on providers
  whose airframe adapter supports ``session(on_permission=...)``.
* **Backstop** (:mod:`maverick.protection.snapshot`) — snapshots protected
  files before every agent execution and restores any unauthorized
  mutation after, regardless of provider or write channel.

See ``specs/056-context-file-protection/`` for the full contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from maverick.protection.policy import ProtectionPolicy
from maverick.protection.records import BlockCollector

if TYPE_CHECKING:
    from maverick.config import MaverickConfig

__all__ = ["BlockCollector", "ProtectionPolicy", "build_ad_hoc_protection"]


def build_ad_hoc_protection(
    cwd: Path | str, config: MaverickConfig
) -> tuple[ProtectionPolicy, BlockCollector]:
    """One-shot policy + collector for an agent built outside a Squadron.

    Most agents are built by a :class:`~maverick.squadron.base.Squadron`
    subclass, which builds the run's :class:`ProtectionPolicy` once in
    :meth:`~maverick.squadron.base.Squadron.open` (including a baseline
    manifest capture for the capture-failure fallback). A handful of
    workflow call sites construct a single :class:`~maverick.agents.base.Agent`
    directly instead — ``land`` curation (``CuratorAgent``), ``refuel
    --enrich`` (``SpeckitEnrichmentAgent``), runway seed/consolidate
    (``RunwaySeedAgent``/``ConsolidatorAgent``), and the validation fix
    loop (``ValidationFixerAgent``). This helper gives them the same
    policy construction with one line, per FR-009 ("every role, every
    workflow"). No baseline manifest is captured here — these agents run
    once rather than across many bead boundaries, so the fallback
    optimization doesn't pay for itself; a per-step capture failure for
    one of these simply skips that one step's post-compare (documented
    degrade in ``Agent._capture_snapshot``).

    Args:
        cwd: The agent's working directory — the policy root.
        config: The loaded :class:`~maverick.config.MaverickConfig`.

    Returns:
        A fresh ``(policy, collector)`` pair to pass as
        ``protection_policy=``/``block_collector=`` to the ``Agent``
        constructor.
    """
    from maverick.protection.config import lookup_protection_config

    policy = ProtectionPolicy.build(Path(cwd), lookup_protection_config(config))
    return policy, BlockCollector()
