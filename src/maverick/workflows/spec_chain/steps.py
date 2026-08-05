"""Per-step prompt builders for the spec-chain workflow.

Each chain step's prompt instructs the agent to run the target
repository's own Spec Kit command (R1/FR-003). When that command's
definition file is present in the workspace, its body is inlined too — a
fallback for providers whose agent surface can't invoke slash commands
natively, and a belt-and-suspenders reinforcement for providers that
can. Either way the instructions still come from the target repository's
own files, not from Maverick.

Spec Kit 0.14 renamed that surface: `.claude/commands/speckit.<step>.md`
(invoked `/speckit.<step>`) became `.claude/skills/speckit-<step>/SKILL.md`
(invoked `/speckit-<step>`). Rather than hardcode either shape, every
lookup here probes the workspace and reports the name matching whatever
it actually finds — so a repo on 0.14+ and a repo still carrying the
pre-0.14 layout each get a prompt naming a command that exists there.
"""

from __future__ import annotations

from pathlib import Path

from maverick.workflows.spec_chain.constants import ChainStep

__all__ = [
    "SLASH_COMMANDS",
    "build_step_prompt",
    "read_command_body",
    "resolve_command",
]

#: Default slash command per chain step — the Spec Kit 0.14+ skill form,
#: used when the workspace carries neither surface on disk. Prefer
#: :func:`resolve_command`, which reports what the workspace actually has.
SLASH_COMMANDS: dict[ChainStep, str] = {step: f"/speckit-{step.value}" for step in ChainStep}

#: Skill-definition file (Spec Kit >= 0.14), relative to the workspace root.
_SKILL_FILE: dict[ChainStep, str] = {
    step: f".claude/skills/speckit-{step.value}/SKILL.md" for step in ChainStep
}

#: Command-definition file (Spec Kit < 0.14), relative to the workspace root.
_COMMAND_FILE: dict[ChainStep, str] = {
    step: f".claude/commands/speckit.{step.value}.md" for step in ChainStep
}

_STRUCTURED_REPORT_INSTRUCTION = (
    "When finished, report your outcome via the StructuredOutput tool per "
    "the schema provided — status, artifact paths you wrote or updated, "
    "any clarify questions and the answers you adopted, any analyze "
    "findings, and a short detail summary."
)


def resolve_command(workspace: Path, step: ChainStep) -> tuple[str, str | None]:
    """Resolve *step*'s slash command and definition body in *workspace*.

    Probes the Spec Kit >= 0.14 skill layout first, then the pre-0.14
    command layout, so the returned name always matches the surface
    actually installed there.

    Args:
        workspace: The workspace root to probe.
        step: The chain step to resolve.

    Returns:
        A ``(slash_command, body)`` pair. ``body`` is ``None`` when
        neither definition file exists, in which case ``slash_command``
        falls back to :data:`SLASH_COMMANDS`.
    """
    for relative_path, command in (
        (_SKILL_FILE[step], f"/speckit-{step.value}"),
        (_COMMAND_FILE[step], f"/speckit.{step.value}"),
    ):
        candidate = workspace / relative_path
        if candidate.is_file():
            return command, candidate.read_text(encoding="utf-8")

    return SLASH_COMMANDS[step], None


def read_command_body(workspace: Path, step: ChainStep) -> str | None:
    """Read *step*'s command-definition markdown from the workspace.

    Returns ``None`` when neither the skill nor the command definition
    exists there (the inline fallback is simply omitted from the prompt
    in that case).
    """
    return resolve_command(workspace, step)[1]


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
    command, body = resolve_command(workspace, step)
    parts: list[str] = []

    if step is ChainStep.SPECIFY:
        parts.append(
            f'Run `{command}` for the feature "{feature}" using the '
            "following product requirements document as input:\n\n"
            f"---\n{prd_content or ''}\n---"
        )
    else:
        parts.append(f'Run `{command}` for the current feature ("{feature}").')

    if body:
        parts.append(
            f"If your environment cannot invoke `{command}` as a slash "
            "command directly, follow these instructions instead — they "
            f"are `{command}`'s own definition from this repository:\n\n"
            f"{body}"
        )

    parts.append(_STRUCTURED_REPORT_INSTRUCTION)

    return "\n\n".join(parts)
