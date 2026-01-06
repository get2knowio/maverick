"""Prompt templates for skill-aware agents.

This module provides templatized prompts that inject project-type-specific
guidance, enabling agents to leverage skills for the target tech stack.
"""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Any

import yaml

from maverick.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# Skill Mappings
# =============================================================================

#: Map project types to their relevant skills
PROJECT_TYPE_SKILLS: dict[str, list[str]] = {
    "python": [
        "maverick-python-testing",
        "maverick-python-typing",
        "maverick-python-async",
        "maverick-python-security",
        "maverick-python-performance",
        "maverick-python-peps",
    ],
    "rust": [
        "maverick-rust-testing",
        "maverick-rust-ownership",
        "maverick-rust-async",
        "maverick-rust-errors",
        "maverick-rust-clippy",
        "maverick-rust-performance",
        "maverick-rust-unsafe",
    ],
    "ansible_playbook": [
        "maverick-ansible",
    ],
    "ansible_collection": [
        "maverick-ansible",
    ],
    "nodejs": [],  # TODO: Add Node.js skills
    "go": [],  # TODO: Add Go skills
    "unknown": [],
}

#: Human-readable names for project types
PROJECT_TYPE_NAMES: dict[str, str] = {
    "python": "Python",
    "rust": "Rust",
    "ansible_playbook": "Ansible Playbook",
    "ansible_collection": "Ansible Collection",
    "nodejs": "Node.js",
    "go": "Go",
    "unknown": "Unknown",
}


# =============================================================================
# Skill Guidance Template
# =============================================================================

SKILL_GUIDANCE_TEMPLATE = """
## Project Type: $project_type_name

This is a **$project_type_name** project. When implementing or reviewing code,
apply best practices specific to this tech stack.

$skill_instructions
"""

SKILL_INSTRUCTIONS_WITH_SKILLS = """### Available Skills
The following skills are available for $project_type_name development:
$skill_list

**Important:** When you encounter patterns or challenges related to these areas,
use the appropriate skill to get expert guidance. Skills provide detailed best
practices, common patterns, and pitfalls to avoid.

To use a skill, reference it when you need domain-specific guidance for:
- Code patterns and idioms
- Testing strategies
- Error handling approaches
- Performance considerations
- Security best practices
"""

SKILL_INSTRUCTIONS_NO_SKILLS = """### Best Practices
Apply general software engineering best practices for $project_type_name:
- Follow language/framework conventions
- Write clear, maintainable code
- Include appropriate tests
- Handle errors gracefully
- Document complex logic
"""


# =============================================================================
# Public Functions
# =============================================================================


def get_project_type(config_path: Path | None = None) -> str:
    """Read project_type from maverick.yaml.

    Args:
        config_path: Path to maverick.yaml. If None, searches current directory.

    Returns:
        Project type string (e.g., "python", "ansible_playbook").
        Returns "unknown" if config not found or project_type not set.
    """
    if config_path is None:
        config_path = Path("maverick.yaml")

    if not config_path.exists():
        logger.debug(
            "Config not found at %s, using 'unknown' project type", config_path
        )
        return "unknown"

    try:
        config = yaml.safe_load(config_path.read_text())
        if not isinstance(config, dict):
            logger.debug("Config is not a dict, using 'unknown' project type")
            return "unknown"
        project_type: str = config.get("project_type", "unknown")
        logger.debug("Detected project type: %s", project_type)
        return project_type
    except Exception as e:
        logger.warning("Failed to read project type from %s: %s", config_path, e)
        return "unknown"


def get_skill_guidance(project_type: str) -> str:
    """Generate skill guidance section for a project type.

    Args:
        project_type: Project type (e.g., "python", "rust").

    Returns:
        Formatted skill guidance string to include in prompts.
    """
    project_type_name = PROJECT_TYPE_NAMES.get(project_type, project_type.title())
    skills = PROJECT_TYPE_SKILLS.get(project_type, [])

    if skills:
        skill_list = "\n".join(f"- `{skill}`" for skill in skills)
        skill_instructions = Template(SKILL_INSTRUCTIONS_WITH_SKILLS).substitute(
            project_type_name=project_type_name,
            skill_list=skill_list,
        )
    else:
        skill_instructions = Template(SKILL_INSTRUCTIONS_NO_SKILLS).substitute(
            project_type_name=project_type_name,
        )

    return Template(SKILL_GUIDANCE_TEMPLATE).substitute(
        project_type_name=project_type_name,
        skill_instructions=skill_instructions,
    )


def render_prompt(
    base_prompt: str,
    project_type: str | None = None,
    config_path: Path | None = None,
    extra_context: dict[str, Any] | None = None,
) -> str:
    """Render a prompt template with project-type skill guidance.

    Args:
        base_prompt: The base system prompt (may contain $skill_guidance placeholder).
        project_type: Explicit project type. If None, reads from maverick.yaml.
        config_path: Path to maverick.yaml for auto-detection.
        extra_context: Additional template variables to substitute.

    Returns:
        Rendered prompt with skill guidance injected.

    Example:
        >>> base = "You are an expert. $skill_guidance Do your task."
        >>> rendered = render_prompt(base, project_type="python")
        >>> "Python" in rendered
        True
    """
    # Get project type
    if project_type is None:
        project_type = get_project_type(config_path)

    # Generate skill guidance
    skill_guidance = get_skill_guidance(project_type)

    # Build substitution context
    context = {
        "skill_guidance": skill_guidance,
        "project_type": project_type,
        "project_type_name": PROJECT_TYPE_NAMES.get(project_type, project_type.title()),
    }

    if extra_context:
        context.update(extra_context)

    # Use safe_substitute to avoid errors on unmatched placeholders
    template = Template(base_prompt)
    return template.safe_substitute(context)
