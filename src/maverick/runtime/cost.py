"""Cost telemetry record — vendor-agnostic.

Every :class:`maverick.runtime.protocol.Runtime` adapter produces a
:class:`CostRecord` on each :meth:`execute` call. The record is the
canonical input to Maverick's structured-log ``agent.cost`` row and to
the runway store's cost-tracking JSONL.

Adapters with vendor-computed cost (Claude Code SDK exposes
``total_cost_usd`` directly) populate ``cost_usd`` from the vendor's
report. Adapters without (raw Anthropic API, raw OpenAI API) compute
``cost_usd`` from token counts × a pricing table; see
:mod:`maverick.runtime.pricing` (added in Phase 1.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CostRecord:
    """One row of cost telemetry — captured from each runtime execute().

    Field names match the existing ``agent.cost`` structured-log row so
    legacy log parsers keep working unchanged.

    Attributes:
        provider_id: The vendor that served the call
            (``"anthropic"``, ``"openai"``, ``"github-copilot"``, etc.).
        model_id: The model identifier the vendor reports.
        cost_usd: USD cost for this call. ``None`` when the adapter
            can't compute it (no pricing table entry for the model).
        input_tokens: Prompt tokens consumed.
        output_tokens: Completion tokens generated.
        cache_read_tokens: Prompt tokens served from the provider's cache.
        cache_write_tokens: Prompt tokens written to the provider's cache.
        finish: The provider-reported stop reason (``"stop"``, ``"length"``,
            ``"tool_calls"``, ``"end_turn"``, etc.). ``None`` if not reported.
    """

    provider_id: str | None
    model_id: str | None
    cost_usd: float | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    finish: str | None

    def to_dict(self) -> dict[str, Any]:
        """Render as the ``agent.cost`` structured-log payload."""
        return {
            "providerID": self.provider_id,
            "modelID": self.model_id,
            "cost_usd": self.cost_usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "finish": self.finish,
        }


__all__ = ["CostRecord"]
