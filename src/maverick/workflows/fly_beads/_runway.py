"""Runway retrieval, recording, and provenance walking for fly-beads."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from maverick.library.actions.runway import (
    record_bead_outcome,
    record_review_findings,
    retrieve_runway_context,
)
from maverick.logging import get_logger
from maverick.workflows.fly_beads.models import BeadContext

if TYPE_CHECKING:
    from maverick.workflows.fly_beads.workflow import FlyBeadsWorkflow

logger = get_logger(__name__)


async def fetch_runway_context(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Fetch runway context for the current bead (best-effort).

    Queries the runway store for historical outcomes and semantically
    relevant passages. Sets ctx.runway_context if data is found.
    Never raises — logs a warning on failure.
    """
    try:
        runway_cfg = getattr(wf._config, "runway", None)
        if runway_cfg is None or not getattr(runway_cfg, "enabled", True):
            return

        retrieval_cfg = getattr(runway_cfg, "retrieval", None)
        max_passages = getattr(retrieval_cfg, "max_passages", 10) if retrieval_cfg else 10
        bm25_top_k = getattr(retrieval_cfg, "bm25_top_k", 20) if retrieval_cfg else 20
        max_context_chars = (
            getattr(retrieval_cfg, "max_context_chars", 4000) if retrieval_cfg else 4000
        )

        result = await retrieve_runway_context(
            title=ctx.title,
            description=ctx.description,
            epic_id=ctx.epic_id,
            max_passages=max_passages,
            bm25_top_k=bm25_top_k,
            max_context_chars=max_context_chars,
            cwd=ctx.cwd,
        )
        if result.context_text:
            ctx.runway_context = result.context_text
            logger.info(
                "runway_context_fetched",
                bead_id=ctx.bead_id,
                outcomes=result.outcomes_used,
                passages=result.passages_used,
            )
    except Exception as exc:
        logger.warning(
            "fetch_runway_context_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )


async def walk_discovered_from_chain(bead_id: str) -> list[str]:
    """Walk the discovered-from dependency chain back to the root.

    Returns a list of bead IDs from root to the bead that links to
    ``bead_id``.  An empty list means the bead has no discovered-from
    ancestry (it is an original bead, not a follow-up).

    Capped at 10 hops to prevent infinite loops on circular deps.
    """
    import json as _json

    from maverick.runners.command import CommandRunner

    runner = CommandRunner(cwd=Path.cwd())
    chain: list[str] = []
    current = bead_id
    seen: set[str] = set()

    for _ in range(10):
        try:
            result = await runner.run(
                ["bd", "dep", "list", current, "--json"],
            )
        except Exception:
            break

        if not result.stdout:
            break

        origin_id = ""
        try:
            deps = _json.loads(result.stdout)
            if isinstance(deps, list):
                for dep in deps:
                    if isinstance(dep, dict) and dep.get("dependency_type") == "discovered-from":
                        origin_id = dep.get("id", "")
                        break
        except (ValueError, TypeError) as exc:
            logger.warning("runway.chain_parse_failed", bead_id=current, error=str(exc))

        if not origin_id or origin_id in seen:
            break

        chain.append(origin_id)
        seen.add(origin_id)
        current = origin_id

    chain.reverse()  # root first
    return chain


async def resolve_provenance(ctx: BeadContext) -> None:
    """Enrich bead context with provenance from discovered-from links.

    Populates ``ctx.discovered_from_chain`` and appends a provenance
    section to ``ctx.description`` so the implementer agent can understand
    what was tried before and what the reviewer objected to.
    """
    import json as _json

    from maverick.runners.command import CommandRunner

    chain = await walk_discovered_from_chain(ctx.bead_id)
    ctx.discovered_from_chain = chain
    ctx.escalation_depth = len(chain)

    if not chain:
        return

    origin_id = chain[-1]  # most recent ancestor
    runner = CommandRunner(cwd=Path.cwd())

    try:
        origin_result = await runner.run(
            ["bd", "show", origin_id, "--json"],
        )
    except Exception:
        return

    if not origin_result.stdout:
        return

    try:
        origin = _json.loads(origin_result.stdout)
    except (ValueError, TypeError) as exc:
        logger.warning(
            "runway.provenance_parse_failed", bead_id=origin_id, error=str(exc)
        )
        return

    origin_title = origin.get("title", "")
    origin_desc = origin.get("description", "")

    provenance_section = (
        f"\n\n## Provenance\n\n"
        f"This bead was created to address unresolved review"
        f" findings from bead `{origin_id}`"
        f" ({origin_title}).\n"
    )
    if len(chain) > 1:
        provenance_section += (
            f"\nFull chain: {' → '.join(f'`{b}`' for b in chain)}"
            f" → `{ctx.bead_id}` (current)\n"
        )
    if origin_desc:
        desc_preview = origin_desc[:500]
        if len(origin_desc) > 500:
            desc_preview += "..."
        provenance_section += f"\n### Original Bead Description\n\n{desc_preview}\n"

    ctx.description = ctx.description + provenance_section


async def record_runway_outcome(
    wf: FlyBeadsWorkflow,
    ctx: BeadContext,
    files_changed: list[str] | None = None,
) -> None:
    """Record bead outcome to runway store (best-effort)."""
    try:
        await record_bead_outcome(
            bead_id=ctx.bead_id,
            epic_id=ctx.epic_id,
            title=ctx.title,
            flight_plan=ctx.flight_plan_name,
            validation_result=ctx.validation_result,
            review_result=ctx.review_result,
            files_changed=files_changed,
            cwd=ctx.cwd,
        )
    except Exception as exc:
        logger.warning(
            "runway_outcome_recording_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )


async def record_runway_review(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Record review findings to runway store (best-effort)."""
    if ctx.review_result is None:
        return
    try:
        await record_review_findings(
            bead_id=ctx.bead_id,
            review_result=ctx.review_result,
            cwd=ctx.cwd,
        )
    except Exception as exc:
        logger.warning(
            "runway_review_recording_failed",
            bead_id=ctx.bead_id,
            error=str(exc),
        )
