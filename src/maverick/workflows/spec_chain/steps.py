"""Per-step prompt builders for the spec-chain workflow.

Each chain step's prompt instructs the agent to run the target
repository's own ``/speckit.*`` slash command (R1/FR-003). When the
command's definition file is present in the workspace, its body is
inlined too — a fallback for providers whose agent surface can't invoke
slash commands natively, and a belt-and-suspenders reinforcement for
providers that can. Either way the instructions still come from the
target repository's own files, not from Maverick.
"""

from __future__ import annotations

from pathlib import Path

from maverick.workflows.spec_chain.constants import ChainStep

__all__ = ["SLASH_COMMANDS", "build_step_prompt", "read_command_body"]

#: Slash command name per chain step — the target repo's own `/speckit.*`
#: surface.
SLASH_COMMANDS: dict[ChainStep, str] = {
    ChainStep.SPECIFY: "/speckit.specify",
    ChainStep.CLARIFY: "/speckit.clarify",
    ChainStep.PLAN: "/speckit.plan",
    ChainStep.TASKS: "/speckit.tasks",
    ChainStep.ANALYZE: "/speckit.analyze",
}

#: Command-definition file, relative to the workspace root, per step.
_COMMAND_FILE: dict[ChainStep, str] = {
    step: f".claude/commands/speckit.{step.value}.md" for step in ChainStep
}

_STRUCTURED_REPORT_INSTRUCTION = (
    "When finished, report your outcome via the StructuredOutput tool per "
    "the schema provided — status, artifact paths you wrote or updated, "
    "any clarify questions and the answers you adopted, any analyze "
    "findings, and a short detail summary."
)


def read_command_body(workspace: Path, step: ChainStep) -> str | None:
    """Read *step*'s command-definition markdown from the workspace.

    Returns ``None`` when no known command file exists there (the inline
    fallback is simply omitted from the prompt in that case).
    """
    candidate = workspace / _COMMAND_FILE[step]
    if not candidate.is_file():
        return None
    return candidate.read_text(encoding="utf-8")


def build_step_prompt(
    step: ChainStep,
    *,
    workspace: Path,
    feature: str,
    prd_content: str | None = None,
) -> str:
    """Build the prompt for one chain step.

    Args:
        step: The chain step to run.
        workspace: The hidden workspace (cwd the agent operates in) — used
            to look up the step's command-definition file for the inline
            fallback.
        feature: The feature name/slug this run is producing.
        prd_content: The PRD body. Only consumed by the specify step
            (R1) — ignored for every other step.

    Returns:
        The full prompt text for this step.
    """
    command = SLASH_COMMANDS[step]
    parts: list[str] = []

    if step is ChainStep.SPECIFY:
        parts.append(
            f'Run `{command}` for the feature "{feature}" using the '
            "following product requirements document as input:\n\n"
            f"---\n{prd_content or ''}\n---"
        )
    else:
        parts.append(f'Run `{command}` for the current feature ("{feature}").')

    body = read_command_body(workspace, step)
    if body:
        parts.append(
            f"If your environment cannot invoke `{command}` as a slash "
            "command directly, follow these instructions instead — they "
            f"are `{command}`'s own definition from this repository:\n\n"
            f"{body}"
        )

    parts.append(_STRUCTURED_REPORT_INSTRUCTION)

    return "\n\n".join(parts)
