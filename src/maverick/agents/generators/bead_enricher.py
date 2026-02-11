"""BeadEnricherGenerator for enriching bead descriptions with acceptance criteria.

Uses a single-shot LLM call to transform sparse bead definitions into
self-contained work items with objectives, acceptance criteria, key files,
conventions, and dependency context.
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

BEAD_ENRICHER_SYSTEM_PROMPT = """\
You are a bead description enricher. You receive a bead definition (title, \
category, tasks, checkpoints) along with spec and plan excerpts, and produce \
an enriched description that makes the bead a self-contained work item.

**Output format** (use these exact headings):

## Objective
1-2 sentence summary of what this bead delivers.

## Acceptance Criteria
Binary pass/fail criteria derived from the checkpoints and spec. Use checkbox \
format:
- [ ] Criterion 1
- [ ] Criterion 2

## Key Files
File paths extracted from task descriptions and plan (if identifiable):
- `path/to/file.py` — brief purpose

## Conventions
Relevant coding conventions from the plan (only those relevant to THIS bead). \
Omit this section if no conventions apply.

## Dependency Context
What predecessor beads provide that this bead can rely on. Omit if no \
dependencies are described.

**Rules**:
1. Output ONLY the enriched description in the format above
2. Do not invent acceptance criteria beyond what the spec/checkpoints describe
3. Scale detail by category:
   - FOUNDATION: Heavy enrichment (full conventions, all file paths, detailed criteria)
   - USER_STORY: Medium enrichment (focused criteria, relevant files)
   - CLEANUP: Light enrichment (just Objective + Acceptance Criteria)
4. If information for a section is not available, omit that section entirely
5. Keep the total output concise — aim for 150-300 words
"""


class BeadEnricherGenerator(GeneratorAgent):
    """Enrich bead descriptions with acceptance criteria and context.

    Uses a single-shot LLM call to transform sparse bead definitions into
    self-contained work items with objectives, acceptance criteria, and context.

    Example:
        ```python
        enricher = BeadEnricherGenerator()
        result = await enricher.generate({
            "title": "Implement greeting CLI",
            "category": "USER_STORY",
            "tasks": "- Add click command\\n- Add tests",
            "checkpoints": "- greet command exists\\n- tests pass",
            "spec_content": "...",
            "plan_content": "...",
        })
        # Returns enriched markdown description
        ```
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        """Initialize the BeadEnricherGenerator.

        Args:
            model: Claude model ID (default: claude-sonnet-4-5-20250929).
        """
        super().__init__(
            name="bead-enricher",
            system_prompt=BEAD_ENRICHER_SYSTEM_PROMPT,
            model=model,
        )

    async def generate(
        self,
        context: dict[str, Any],
        return_usage: bool = False,
    ) -> str | tuple[str, AgentUsage]:
        """Enrich a bead description with acceptance criteria and context.

        Args:
            context: Input context containing:
                - title (str): Bead title.
                - category (str): Bead category (FOUNDATION, USER_STORY, CLEANUP).
                - tasks (str): Task descriptions for this bead.
                - checkpoints (str): Checkpoints/verification criteria.
                - spec_content (str, optional): Spec file excerpt.
                - plan_content (str, optional): Plan file excerpt.
                - dependency_context (str, optional): What predecessor beads provide.
            return_usage: If True, return (text, usage) tuple.

        Returns:
            Enriched markdown description,
            or (description, usage) if return_usage is True.

        Raises:
            GeneratorError: If generation fails.
        """
        title = context.get("title", "")
        category = context.get("category", "USER_STORY")
        tasks = context.get("tasks", "")
        checkpoints = context.get("checkpoints", "")
        spec_content = context.get("spec_content", "")
        plan_content = context.get("plan_content", "")
        dependency_context = context.get("dependency_context", "")

        # If we have nothing to work with, return a minimal description
        if not title and not tasks and not checkpoints:
            logger.debug("empty_bead_context")
            empty_result = ""
            if return_usage:
                return empty_result, AgentUsage(
                    input_tokens=0,
                    output_tokens=0,
                    total_cost_usd=None,
                    duration_ms=0,
                )
            return empty_result

        # Truncate large inputs
        max_spec = 10240  # 10KB
        spec_content = self._truncate_input(spec_content, max_spec, "spec_content")
        plan_content = self._truncate_input(plan_content, max_spec, "plan_content")

        # Build prompt
        parts = [
            "Enrich the following bead definition into a self-contained work item.\n",
            f"**Title**: {title}",
            f"**Category**: {category}",
        ]

        if tasks:
            parts.append(f"\n**Tasks**:\n{tasks}")
        if checkpoints:
            parts.append(f"\n**Checkpoints**:\n{checkpoints}")
        if spec_content:
            parts.append(f"\n**Spec Excerpt**:\n{spec_content}")
        if plan_content:
            parts.append(f"\n**Plan Excerpt**:\n{plan_content}")
        if dependency_context:
            parts.append(f"\n**Dependency Context**:\n{dependency_context}")

        prompt = "\n".join(parts)

        logger.debug(
            "enriching_bead",
            title=title,
            category=category,
            prompt_length=len(prompt),
        )

        if return_usage:
            result, usage = await self._query_with_usage(prompt)
            return result.strip(), usage

        result = await self._query(prompt)
        return result.strip()
