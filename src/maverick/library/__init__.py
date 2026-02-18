"""Built-in workflow library.

This module provides access to Maverick's built-in workflows, fragments,
and scaffolding templates.

Submodules:
- workflows: Built-in workflow YAML definitions
- fragments: Reusable workflow fragments
- templates: Jinja2 scaffolding templates
- agents: Agent registration functions
- generators: Generator registration functions
"""

from __future__ import annotations

from maverick.library.agents import register_all_agents
from maverick.library.builtins import (
    BUILTIN_FRAGMENTS,
    BUILTIN_WORKFLOWS,
    COMMIT_AND_PUSH_FRAGMENT_INFO,
    CREATE_PR_WITH_SUMMARY_FRAGMENT_INFO,
    FLY_BEADS_WORKFLOW_INFO,
    REFUEL_SPECKIT_WORKFLOW_INFO,
    VALIDATE_AND_FIX_FRAGMENT_INFO,
    BuiltinFragmentInfo,
    BuiltinWorkflowInfo,
)
from maverick.library.generators import register_all_generators
from maverick.library.scaffold import (
    InvalidNameError,
    OutputExistsError,
    ScaffoldError,
    ScaffoldRequest,
    ScaffoldResult,
    ScaffoldService,
    TemplateFormat,
    TemplateInfo,
    TemplateRenderError,
    TemplateType,
    create_scaffold_service,
    get_default_output_dir,
    validate_workflow_name,
)

__all__ = [
    # Enums
    "TemplateType",
    "TemplateFormat",
    # Models - Scaffold
    "TemplateInfo",
    "ScaffoldRequest",
    "ScaffoldResult",
    # Models - Builtin
    "BuiltinWorkflowInfo",
    "BuiltinFragmentInfo",
    # Constants
    "BUILTIN_WORKFLOWS",
    "BUILTIN_FRAGMENTS",
    # Workflow info constants
    "FLY_BEADS_WORKFLOW_INFO",
    "REFUEL_SPECKIT_WORKFLOW_INFO",
    # Fragment info constants
    "VALIDATE_AND_FIX_FRAGMENT_INFO",
    "COMMIT_AND_PUSH_FRAGMENT_INFO",
    "CREATE_PR_WITH_SUMMARY_FRAGMENT_INFO",
    # Exceptions
    "ScaffoldError",
    "InvalidNameError",
    "OutputExistsError",
    "TemplateRenderError",
    # Services
    "ScaffoldService",
    # Functions
    "validate_workflow_name",
    "get_default_output_dir",
    "create_scaffold_service",
    # Registration functions
    "register_all_agents",
    "register_all_generators",
]
