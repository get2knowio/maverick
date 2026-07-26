"""``actors.<workflow>.<actor>.tiers`` is parsed and reaches the squadrons.

The Burr migration deleted the per-workflow supervisors, and with them
the only code that parsed the ``tiers:`` block. :class:`ActorConfig`
kept accepting the key as an untyped pass-through, so a configured
``tiers:`` block loaded, validated, and did nothing at all — for all
three tierable actors (#135).

These tests pin both halves: the resolver reads the block, and the
production call sites actually pass what it returns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from maverick.config import (
    DecomposerTiersConfig,
    ImplementerTiersConfig,
    MaverickConfig,
    ReviewerTiersConfig,
    lookup_tiers_config,
)


def _config(actors: dict[str, Any]) -> MaverickConfig:
    return MaverickConfig(actors=actors)


_TIER_BLOCK = {
    "trivial": {"provider": "anthropic", "model_id": "claude-haiku-4-5-20251001"},
    "complex": {"provider": "anthropic", "model_id": "claude-opus-5"},
}


class TestLookupTiersConfig:
    def test_implementer_tiers_parsed(self) -> None:
        config = _config({"fly": {"implementer": {"tiers": _TIER_BLOCK}}})

        tiers = lookup_tiers_config(config, "fly-beads", "implementer")

        assert isinstance(tiers, ImplementerTiersConfig)
        assert tiers.trivial is not None
        assert tiers.trivial.model_id == "claude-haiku-4-5-20251001"
        assert tiers.complex is not None
        assert tiers.complex.model_id == "claude-opus-5"
        # Undeclared tiers stay undeclared — no silent filling-in.
        assert tiers.simple is None

    def test_reviewer_tiers_parsed(self) -> None:
        config = _config({"fly": {"reviewer": {"tiers": _TIER_BLOCK}}})

        tiers = lookup_tiers_config(config, "fly-beads", "reviewer")

        assert isinstance(tiers, ReviewerTiersConfig)

    def test_decomposer_tiers_parsed(self) -> None:
        config = _config({"refuel": {"decomposer": {"tiers": _TIER_BLOCK}}})

        tiers = lookup_tiers_config(config, "refuel-maverick", "decomposer")

        assert isinstance(tiers, DecomposerTiersConfig)

    def test_tiers_coexist_with_top_level_actor_fields(self) -> None:
        """The whole reason ``tiers`` is a pass-through on ActorConfig is
        so one YAML block can carry both."""
        config = _config(
            {
                "fly": {
                    "implementer": {
                        "provider": "anthropic",
                        "model_id": "claude-sonnet-5",
                        "tiers": _TIER_BLOCK,
                    }
                }
            }
        )

        tiers = lookup_tiers_config(config, "fly-beads", "implementer")

        assert tiers is not None
        assert tiers.complex is not None  # type: ignore[union-attr]

    def test_absent_block_returns_none(self) -> None:
        config = _config({"fly": {"implementer": {"model_id": "claude-sonnet-5"}}})

        assert lookup_tiers_config(config, "fly-beads", "implementer") is None

    def test_absent_actor_returns_none(self) -> None:
        assert lookup_tiers_config(_config({}), "fly-beads", "implementer") is None

    def test_untierable_actor_returns_none(self) -> None:
        """Only actors in the registry support tiering; a ``tiers:`` block
        on anything else is inert by design, not by accident."""
        config = _config({"plan": {"scopist": {"tiers": _TIER_BLOCK}}})

        assert lookup_tiers_config(config, "generate-flight-plan", "scopist") is None

    def test_malformed_tiers_degrade_to_none(self) -> None:
        """A typo in one tier must not take down workflow startup — the
        caller's no-tiers path is always a valid fallback."""
        config = _config(
            {"fly": {"implementer": {"tiers": {"trivial": {"timeout": -5}}}}},
        )

        assert lookup_tiers_config(config, "fly-beads", "implementer") is None

    def test_non_dict_tiers_degrade_to_none(self) -> None:
        config = _config({"fly": {"implementer": {"tiers": ["trivial"]}}})

        assert lookup_tiers_config(config, "fly-beads", "implementer") is None


class TestSquadronsReceiveTiers:
    """The resolver existing isn't enough — it has to be *called*."""

    def test_refuel_squadron_reads_tiers_from_config(self) -> None:
        """``RefuelSquadron`` resolves its own tiers, so the workflow has
        nothing to thread and can't forget to."""
        from maverick.squadron.refuel import RefuelSquadron
        from maverick.squadron.tiers import DEFAULT_TIER

        config = _config({"refuel": {"decomposer": {"tiers": _TIER_BLOCK}}})
        squadron = RefuelSquadron(cwd=Path("."), config=config)

        # Capped at one escalation step by DecomposerTiersConfig's
        # default ``escalation_threshold``.
        assert squadron.decomposer_escalation_ladder() == (DEFAULT_TIER, "trivial")

    def test_refuel_squadron_without_tiers_does_not_escalate(self) -> None:
        from maverick.squadron.refuel import RefuelSquadron
        from maverick.squadron.tiers import DEFAULT_TIER

        squadron = RefuelSquadron(cwd=Path("."), config=_config({}))

        assert squadron.decomposer_escalation_ladder() == (DEFAULT_TIER,)

    def test_explicit_decomposer_tiers_beat_config(self) -> None:
        """An explicit argument is the caller deciding; only ``None``
        means "go look at the config"."""
        from maverick.squadron.refuel import RefuelSquadron
        from maverick.squadron.tiers import DEFAULT_TIER

        config = _config({"refuel": {"decomposer": {"tiers": _TIER_BLOCK}}})
        squadron = RefuelSquadron(
            cwd=Path("."),
            config=config,
            decomposer_tiers=DecomposerTiersConfig(),
        )

        assert squadron.decomposer_escalation_ladder() == (DEFAULT_TIER,)

    async def test_fly_bead_loop_passes_both_tier_blocks(self) -> None:
        """Regression for the exact #135 gap: ``FlySquadron`` has always
        accepted ``implementer_tiers``/``reviewer_tiers``; the production
        call site was passing neither, so the whole surface was inert.

        Asserting on the constructor kwargs rather than on a manually
        built squadron is the point — a squadron that resolves tiers
        correctly is worthless if nothing hands them over.
        """
        from maverick.squadron.tiers import DEFAULT_TIER
        from maverick.workflows.fly_beads import workflow as wf

        config = _config(
            {
                "fly": {
                    "implementer": {"tiers": _TIER_BLOCK},
                    "reviewer": {"tiers": _TIER_BLOCK},
                }
            }
        )
        captured: dict[str, Any] = {}

        class _StopHereError(RuntimeError):
            pass

        def _capture(**kwargs: Any) -> Any:
            captured.update(kwargs)
            raise _StopHereError

        class _Workflow:
            _config = config

        # ``_run_bead_loop`` imports FlySquadron lazily, so patch it at
        # its definition site rather than on the workflow module.
        with (
            patch("maverick.squadron.fly.FlySquadron", _capture),
            patch.object(wf, "_cost_sink_for_cwd", lambda _cwd: None),
        ):
            try:
                await wf._run_bead_loop(
                    _Workflow(),
                    epic_id="e-1",
                    cwd=Path("."),
                    max_beads=1,
                    completed_bead_ids=(),
                )
            except _StopHereError:
                pass

        from maverick.squadron.tiers import escalation_ladder

        assert escalation_ladder(captured["implementer_tiers"]) == (
            DEFAULT_TIER,
            "trivial",
            "complex",
        )
        assert escalation_ladder(captured["reviewer_tiers"]) == (
            DEFAULT_TIER,
            "trivial",
            "complex",
        )
