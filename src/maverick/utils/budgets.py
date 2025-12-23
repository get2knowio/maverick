"""Token budget management utilities for Maverick.

This module provides utilities for managing token budgets when building
context for AI agents, ensuring content fits within model limits.
"""

from __future__ import annotations

from typing import Any

from maverick.utils.text import estimate_tokens

__all__ = [
    "fit_to_budget",
]

# Default values
DEFAULT_TOKEN_BUDGET = 32000
DEFAULT_MIN_SECTION_TOKENS = 100


def fit_to_budget(
    sections: dict[str, str],
    budget: int = DEFAULT_TOKEN_BUDGET,
    *,
    min_section_tokens: int = DEFAULT_MIN_SECTION_TOKENS,
) -> dict[str, Any]:
    """Proportionally truncate sections to fit within token budget.

    Allocates tokens to each section proportionally based on its original size,
    ensuring each section gets at least min_section_tokens.

    Args:
        sections: Dict mapping section names to their text content.
        budget: Total token budget (default 32000).
        min_section_tokens: Minimum tokens per section (default 100).

    Returns:
        Dict with same keys as input, values truncated to fit budget.
        Includes '_metadata' key with truncation info if any truncation occurred.

    Example:
        >>> sections = {'a': 'x' * 10000, 'b': 'y' * 5000}
        >>> fitted = fit_to_budget(sections, budget=3000)
        >>> estimate_tokens(fitted['a']) + estimate_tokens(fitted['b']) <= 3000
        True
    """
    if not sections:
        return {}

    # Estimate tokens for each section
    section_tokens: dict[str, int] = {
        name: estimate_tokens(content) for name, content in sections.items()
    }
    total_tokens = sum(section_tokens.values())

    # If under budget, return unchanged
    if total_tokens <= budget:
        return dict(sections)

    # Calculate proportional allocation
    result: dict[str, Any] = {}
    sections_affected: list[str] = []
    original_lines = 0
    kept_lines = 0

    for name, content in sections.items():
        original_tokens = section_tokens[name]
        original_lines += content.count("\n") + 1

        # Calculate this section's budget (proportional)
        if total_tokens > 0:
            section_budget = max(
                min_section_tokens,
                int(budget * original_tokens / total_tokens),
            )
        else:
            section_budget = min_section_tokens

        # If section fits in its budget, keep it unchanged
        if original_tokens <= section_budget:
            result[name] = content
            kept_lines += content.count("\n") + 1
        else:
            # Truncate to fit budget (estimate chars from tokens)
            max_chars = section_budget * 4
            truncated_content = content[:max_chars]
            if len(content) > max_chars:
                truncated_content += "\n... [content truncated to fit budget]"
            result[name] = truncated_content
            kept_lines += truncated_content.count("\n") + 1
            sections_affected.append(name)

    # Add metadata if truncation occurred
    if sections_affected:
        result["_metadata"] = {
            "truncated": True,
            "original_lines": original_lines,
            "kept_lines": kept_lines,
            "sections_affected": sections_affected,
        }

    return result
