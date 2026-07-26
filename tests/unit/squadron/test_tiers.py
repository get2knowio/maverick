"""Shared per-complexity tier helpers (:mod:`maverick.squadron.tiers`).

Covers the invariant #135 was really about: a tier is only worth
escalating to if it resolves to a *different* provider/model binding.
Before this module existed, every ladder was a hardcoded five-name list
and every name resolved to the same binding, so "escalation" was a retry
with extra logging.
"""

from __future__ import annotations

from maverick.config import (
    DecomposerTiersConfig,
    ImplementerTierConfig,
    ImplementerTiersConfig,
    ReviewerTiersConfig,
)
from maverick.squadron.tiers import (
    DEFAULT_TIER,
    TIER_ORDER,
    binding_for_complexity,
    defined_tiers,
    escalation_ladder,
    merge_tier_config,
)


def _tier(**kwargs: object) -> ImplementerTierConfig:
    return ImplementerTierConfig(**kwargs)  # type: ignore[arg-type]


class TestTierOrder:
    def test_default_sentinel_is_not_a_real_tier(self) -> None:
        """``_default`` means "the role's base binding", which may sit
        anywhere on the capability scale — treating it as a rung would
        make ordering claims that aren't true."""
        assert DEFAULT_TIER not in TIER_ORDER

    def test_order_is_cheapest_first(self) -> None:
        assert TIER_ORDER == ("trivial", "simple", "moderate", "complex")


class TestBindingForComplexity:
    def test_full_binding_flows_through(self) -> None:
        binding = binding_for_complexity(
            "complex", _tier(provider="anthropic", model_id="claude-opus-5")
        )

        assert binding is not None
        assert binding.provider == "anthropic"
        assert binding.model_id == "claude-opus-5"

    def test_default_sentinel_never_overrides(self) -> None:
        """The base binding is the role's own; a tier override would be
        a contradiction in terms."""
        assert (
            binding_for_complexity(
                DEFAULT_TIER, _tier(provider="anthropic", model_id="claude-opus-5")
            )
            is None
        )

    def test_none_override(self) -> None:
        assert binding_for_complexity("complex", None) is None

    def test_half_specified_binding_is_rejected(self) -> None:
        """Provider without model (or vice versa) must not be pieced
        together with the role default — that silently pairs one tier's
        provider with another tier's model."""
        assert binding_for_complexity("complex", _tier(provider="anthropic")) is None
        assert binding_for_complexity("complex", _tier(model_id="claude-opus-5")) is None

    def test_non_binding_fields_do_not_make_a_binding(self) -> None:
        """timeout/max_tokens/temperature are Maverick-only knobs the
        agent factory doesn't consume."""
        assert binding_for_complexity("complex", _tier(timeout=90, max_tokens=1000)) is None


class TestDefinedTiers:
    def test_none_config(self) -> None:
        assert defined_tiers(None) == ()

    def test_empty_config(self) -> None:
        assert defined_tiers(ImplementerTiersConfig()) == ()

    def test_sparse_config_keeps_capability_order(self) -> None:
        """Sparse configs are the documented common case — declaring
        only the two tiers you care about must not reorder them."""
        config = ImplementerTiersConfig(
            complex=_tier(provider="anthropic", model_id="opus"),
            trivial=_tier(provider="anthropic", model_id="haiku"),
        )

        assert defined_tiers(config) == ("trivial", "complex")

    def test_all_tiers(self) -> None:
        config = ImplementerTiersConfig(
            trivial=_tier(model_id="a"),
            simple=_tier(model_id="b"),
            moderate=_tier(model_id="c"),
            complex=_tier(model_id="d"),
        )

        assert defined_tiers(config) == TIER_ORDER


class TestEscalationLadder:
    def test_no_config_yields_no_escalation(self) -> None:
        """The #135 invariant: with one binding there is nowhere to
        escalate *to*, so the ladder must not manufacture rungs."""
        assert escalation_ladder(None) == (DEFAULT_TIER,)

    def test_empty_config_yields_no_escalation(self) -> None:
        assert escalation_ladder(ImplementerTiersConfig()) == (DEFAULT_TIER,)

    def test_ladder_starts_at_base_binding(self) -> None:
        """Unescalated work runs on the role's own binding, so that is
        always rung zero."""
        config = ImplementerTiersConfig(complex=_tier(provider="anthropic", model_id="opus"))

        assert escalation_ladder(config)[0] == DEFAULT_TIER

    def test_ladder_climbs_only_defined_tiers(self) -> None:
        config = ImplementerTiersConfig(
            simple=_tier(provider="anthropic", model_id="haiku"),
            complex=_tier(provider="anthropic", model_id="opus"),
        )

        assert escalation_ladder(config) == (DEFAULT_TIER, "simple", "complex")

    def test_max_steps_caps_the_ladder(self) -> None:
        config = DecomposerTiersConfig(
            trivial=_tier(model_id="a"),
            simple=_tier(model_id="b"),
            moderate=_tier(model_id="c"),
        )

        assert escalation_ladder(config, max_steps=1) == (DEFAULT_TIER, "trivial")

    def test_max_steps_zero_disables_escalation(self) -> None:
        config = DecomposerTiersConfig(complex=_tier(model_id="opus"))

        assert escalation_ladder(config, max_steps=0) == (DEFAULT_TIER,)

    def test_max_steps_beyond_defined_tiers_is_not_padded(self) -> None:
        """Asking for more steps than there are tiers must not repeat or
        invent rungs."""
        config = DecomposerTiersConfig(complex=_tier(model_id="opus"))

        assert escalation_ladder(config, max_steps=5) == (DEFAULT_TIER, "complex")

    def test_escalation_threshold_is_not_read_implicitly(self) -> None:
        """The field means "escalation steps" on DecomposerTiersConfig but
        "fix rounds before promoting" on ImplementerTiersConfig. Reading
        it here would silently apply one meaning to both.
        """
        config = DecomposerTiersConfig(
            trivial=_tier(model_id="a"),
            simple=_tier(model_id="b"),
            escalation_threshold=1,
        )

        # Uncapped unless the caller passes max_steps explicitly.
        assert escalation_ladder(config) == (DEFAULT_TIER, "trivial", "simple")

    def test_reviewer_tiers_have_no_threshold_field(self) -> None:
        """Reviewers are documented as non-escalating by config, but the
        ladder shape itself is still well-defined."""
        config = ReviewerTiersConfig(complex=_tier(model_id="opus"))

        assert escalation_ladder(config) == (DEFAULT_TIER, "complex")


class TestMergeTierConfig:
    def test_none_base_builds_from_override(self) -> None:
        merged = merge_tier_config(None, _tier(provider="anthropic", model_id="opus", timeout=42))

        assert merged.provider == "anthropic"
        assert merged.model_id == "opus"
        assert merged.timeout == 42

    def test_set_fields_replace_base(self) -> None:
        from maverick.executor.config import StepConfig

        base = StepConfig(provider="openai", model_id="gpt", timeout=10)
        merged = merge_tier_config(base, _tier(model_id="opus"))

        assert merged.model_id == "opus"
        # Unset override fields fall through rather than clearing base.
        assert merged.provider == "openai"
        assert merged.timeout == 10

    def test_all_none_override_returns_base_identity(self) -> None:
        from maverick.executor.config import StepConfig

        base = StepConfig(provider="openai", model_id="gpt")

        assert merge_tier_config(base, _tier()) is base
