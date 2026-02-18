"""DependencyExtractor for extracting inter-story dependencies.

Uses a single-shot LLM call to parse free-form prose from SpecKit's
"User Story Dependencies" section into structured dependency pairs.
"""

from __future__ import annotations

from typing import Any

from maverick.agents.generators.base import DEFAULT_MODEL, GeneratorAgent
from maverick.agents.result import AgentUsage
from maverick.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# System Prompt
# =============================================================================

DEPENDENCY_EXTRACTOR_SYSTEM_PROMPT = """\
You are a dependency extraction tool. You receive a text block describing \
dependencies between user stories and extract structured dependency pairs.

**Input**: A text block from a "User Story Dependencies" section. It may \
contain prose, bullet points, tables, or mixed formats describing which \
user stories depend on which others.

**Output**: A JSON array of 2-element arrays. Each inner array is \
[dependent, dependency] where both are user story IDs like "US1", "US3", etc.

The first element depends on the second element. For example, if US3 depends \
on US1, output ["US3", "US1"].

**Rules**:
1. Output ONLY the JSON array, nothing else (no markdown fencing, no explanation)
2. If a story depends on multiple others, output one pair per dependency
3. If no inter-story dependencies are found, output an empty array: []
4. Only extract dependencies between user stories (USN format)
5. Ignore dependencies on foundation/setup phases (those are structural)
6. Normalize all IDs to uppercase "US" followed by the number (e.g., "US1")

**Examples**:

Input: "US3 depends on US1 for the data model. US7 needs US1 and US3."
Output: [["US3","US1"],["US7","US1"],["US7","US3"]]

Input: "All stories are independent."
Output: []

Input: "Story 5 requires Story 2's API. Story 8 builds on Stories 2 and 5."
Output: [["US5","US2"],["US8","US2"],["US8","US5"]]
"""


class DependencyExtractor(GeneratorAgent):
    """Extract inter-story dependencies from free-form text.

    Uses a single-shot LLM call to parse the "User Story Dependencies"
    section of tasks.md into structured [dependent, dependency] pairs.

    Example:
        ```python
        extractor = DependencyExtractor()
        result = await extractor.generate({
            "dependency_section": "US3 depends on US1. US7 needs US1 and US3."
        })
        # Returns: '[["US3","US1"],["US7","US1"],["US7","US3"]]'
        ```
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        """Initialize the DependencyExtractor.

        Args:
            model: Claude model ID (default: claude-sonnet-4-5-20250929).
        """
        super().__init__(
            name="dependency-extractor",
            system_prompt=DEPENDENCY_EXTRACTOR_SYSTEM_PROMPT,
            model=model,
        )

    async def generate(
        self,
        context: dict[str, Any],
        return_usage: bool = False,
    ) -> str | tuple[str, AgentUsage]:
        """Extract dependency pairs from a dependency section.

        Args:
            context: Input context containing:
                - dependency_section (str): Text from the dependencies section.
            return_usage: If True, return (text, usage) tuple.

        Returns:
            JSON string of dependency pairs, e.g. '[["US3","US1"]]',
            or (json_string, usage) if return_usage is True.

        Raises:
            GeneratorError: If generation fails.
        """
        dependency_section = context.get("dependency_section", "")

        # If section is empty, return empty array without calling LLM
        if not dependency_section or not dependency_section.strip():
            logger.debug("empty_dependency_section")
            empty_result = "[]"
            if return_usage:
                return empty_result, AgentUsage(
                    input_tokens=0,
                    output_tokens=0,
                    total_cost_usd=None,
                    duration_ms=0,
                )
            return empty_result

        prompt = (
            "Extract inter-story dependency pairs from this text:\n\n"
            f"{dependency_section}\n\n"
            "Output ONLY the JSON array of [dependent, dependency] pairs."
        )

        logger.debug(
            "extracting_dependencies",
            section_length=len(dependency_section),
        )

        if return_usage:
            result, usage = await self._query_with_usage(prompt)
            return result.strip(), usage

        result = await self._query(prompt)
        return result.strip()
